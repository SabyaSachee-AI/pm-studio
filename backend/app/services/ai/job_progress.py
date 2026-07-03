"""Publish live job metadata for Celery tasks and synchronous API AI calls."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_sync_progress_key: ContextVar[str | None] = ContextVar("sync_progress_key", default=None)
_PROGRESS_TTL_SEC = 3600


def set_sync_progress_key(key: str | None) -> Token[str | None]:
    """Bind a Redis progress key for the current async request context."""
    return _sync_progress_key.set(key)


def reset_sync_progress_key(token: Token[str | None]) -> None:
    """Restore the previous sync progress key."""
    _sync_progress_key.reset(token)


@contextmanager
def sync_progress_scope(progress_id: str | None) -> Iterator[None]:
    """Publish AI router progress to Redis while handling a sync HTTP request."""
    token = set_sync_progress_key(progress_id)
    try:
        if progress_id:
            publish_job_progress(
                phase="starting",
                message="Starting…",
                attempt=0,
            )
        yield
    finally:
        reset_sync_progress_key(token)
        if progress_id:
            clear_sync_progress(progress_id)


def _write_sync_progress(progress_id: str, meta: dict[str, Any]) -> None:
    try:
        import redis  # type: ignore[import-untyped]

        from app.core.config import get_settings

        client = redis.from_url(get_settings().redis_url, decode_responses=True)
        client.setex(f"ai_progress:{progress_id}", _PROGRESS_TTL_SEC, json.dumps(meta))
    except Exception:
        logger.debug("Could not write sync job progress", exc_info=True)


def clear_sync_progress(progress_id: str) -> None:
    """Remove Redis progress after a sync AI call finishes."""
    try:
        import redis  # type: ignore[import-untyped]

        from app.core.config import get_settings

        client = redis.from_url(get_settings().redis_url, decode_responses=True)
        client.delete(f"ai_progress:{progress_id}")
    except Exception:
        logger.debug("Could not clear sync job progress", exc_info=True)


async def read_sync_progress(progress_id: str) -> dict[str, Any] | None:
    """Return live progress meta for a synchronous API AI call."""
    try:
        import redis.asyncio as redis  # type: ignore[import-untyped]

        from app.core.config import get_settings

        client = redis.from_url(get_settings().redis_url, decode_responses=True)
        raw = await client.get(f"ai_progress:{progress_id}")
        await client.aclose()
        if not raw:
            return None
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        logger.debug("Could not read sync job progress", exc_info=True)
        return None


def publish_job_progress(**meta: Any) -> None:
    """Update Celery PROGRESS meta and/or Redis sync progress for the UI."""
    try:
        from celery import current_task  # noqa: PLC0415

        task = current_task
        if task and getattr(task, "request", None) and task.request.id:
            task.update_state(state="PROGRESS", meta=meta)
    except Exception:
        logger.debug("Could not publish Celery job progress", exc_info=True)

    try:
        from app.services.build.job_progress import persist_build_job_meta  # noqa: PLC0415

        persist_build_job_meta(meta)
    except Exception:
        logger.debug("Could not persist build job progress", exc_info=True)

    progress_id = _sync_progress_key.get()
    if progress_id:
        _write_sync_progress(progress_id, meta)
