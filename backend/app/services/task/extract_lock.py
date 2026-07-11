"""Redis mutex — one module-extract job per project at a time.

Clears stale locks when Celery is no longer running ``modules.extract`` for the
project (worker crash, deploy mid-job, etc.).
"""

from __future__ import annotations

import logging

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_EXTRACT_TTL_SEC = 3600
_KEY_PREFIX = "extract:project:"


def _client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def _key(project_id: str) -> str:
    return f"{_KEY_PREFIX}{project_id}"


def _celery_extract_running(project_id: str) -> bool:
    """True if a worker is actively running modules.extract for this project."""
    try:
        from celery.result import AsyncResult

        from app.core.celery_app import celery_app

        stored = _client().get(_key(project_id))
        if stored and stored not in ("1", "pending"):
            status = AsyncResult(stored, app=celery_app).status
            if status in ("PENDING", "STARTED", "RETRY", "PROGRESS"):
                return True
            if status in ("SUCCESS", "FAILURE"):
                return False

        insp = celery_app.control.inspect(timeout=2.0)
        for bucket in (insp.active() or {}, insp.reserved() or {}):
            for worker_tasks in bucket.values():
                for task in worker_tasks:
                    if task.get("name") != "modules.extract":
                        continue
                    args = task.get("args") or []
                    if args and str(args[0]) == project_id:
                        return True
    except Exception:  # noqa: BLE001
        logger.debug("Could not inspect Celery for extract job", exc_info=True)
    return False


def clear_stale_extract_lock(project_id: str) -> bool:
    """Drop Redis lock if no live extract task. Returns True if lock was cleared."""
    try:
        client = _client()
        if not client.exists(_key(project_id)):
            return False
        if _celery_extract_running(project_id):
            return False
        client.delete(_key(project_id))
        logger.info("Cleared stale extract lock for project %s", project_id)
        return True
    except Exception:  # noqa: BLE001
        return False


def try_acquire_extract(project_id: str) -> bool:
    """Return True if this caller may start extraction for the project."""
    try:
        client = _client()
        if client.exists(_key(project_id)):
            if _celery_extract_running(project_id):
                return False
            client.delete(_key(project_id))
            logger.info("Replacing stale extract lock for project %s", project_id)
        return bool(client.set(_key(project_id), "pending", nx=True, ex=_EXTRACT_TTL_SEC))
    except Exception:  # noqa: BLE001
        logger.warning("Could not acquire extract lock for %s — allowing run", project_id)
        return True


def bind_extract_task(project_id: str, task_id: str) -> None:
    """Store Celery task id on the lock for accurate stale detection."""
    try:
        _client().set(_key(project_id), task_id, ex=_EXTRACT_TTL_SEC)
    except Exception:  # noqa: BLE001
        pass


def release_extract(project_id: str) -> None:
    try:
        _client().delete(_key(project_id))
    except Exception:  # noqa: BLE001
        pass
