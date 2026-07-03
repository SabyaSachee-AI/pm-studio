"""Live build-job progress — DB heartbeats + Celery meta for the Build UI."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import UUID

_build_id: ContextVar[str | None] = ContextVar("build_job_id", default=None)


def set_active_build_id(build_id: str | None) -> Token[str | None]:
    return _build_id.set(build_id)


def reset_active_build_id(token: Token[str | None]) -> None:
    _build_id.reset(token)


@contextmanager
def build_job_scope(build_id: str) -> Iterator[None]:
    token = set_active_build_id(build_id)
    try:
        yield
    finally:
        reset_active_build_id(token)


def persist_build_job_meta(meta: dict[str, Any]) -> None:
    """Mirror Celery PROGRESS meta into ``build.generation_progress`` for polling."""
    build_id = _build_id.get()
    if not build_id:
        return
    try:
        from app.core.database import SyncSessionLocal
        from app.models.build import Build

        db = SyncSessionLocal()
        try:
            build = db.query(Build).filter(
                Build.id == UUID(build_id), Build.deleted_at.is_(None),
            ).first()
            if not build:
                return
            gp = dict(build.generation_progress or {})
            for key in ("phase", "message", "current_model", "attempt", "current_task", "current_index"):
                if key in meta and meta[key] is not None:
                    gp[key] = meta[key]
            gp["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
            build.generation_progress = gp
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


def emit_build_task_progress(task: Any, *, phase: str, message: str, **extra: Any) -> None:
    """Publish Celery PROGRESS + DB heartbeat at the start of a build task."""
    meta: dict[str, Any] = {"phase": phase, "message": message, **extra}
    try:
        task.update_state(state="PROGRESS", meta=meta)
    except Exception:
        pass
    persist_build_job_meta(meta)
