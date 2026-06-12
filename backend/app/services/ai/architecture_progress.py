"""Live generation progress for architecture docs (Celery + DB)."""

from __future__ import annotations

import contextvars
import logging
from typing import Any
from uuid import UUID

from app.services.ai.providers import model_display_name

_PROVIDER_ICONS: dict[str, str] = {
    "anthropic": "🟣",
    "openai": "🟢",
    "openrouter": "🔵",
    "groq": "⚡",
    "gemini": "✨",
    "cerebras": "🔶",
    "deepseek": "🌊",
    "together": "🤝",
}

logger = logging.getLogger(__name__)

_architecture_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "architecture_id", default=None
)
_doc_field: contextvars.ContextVar[str | None] = contextvars.ContextVar("doc_field", default=None)


def set_architecture_context(architecture_id: UUID | None, doc_field: str | None) -> None:
    _architecture_id.set(architecture_id)
    _doc_field.set(doc_field)


def clear_architecture_context() -> None:
    _architecture_id.set(None)
    _doc_field.set(None)


def _display_model(provider: str, model: str) -> str:
    icon = _PROVIDER_ICONS.get(provider, "")
    return f"{icon} {model_display_name(model)}".strip()


def notify_model_attempt(
    provider: str,
    model: str,
    attempt: int,
    *,
    phase: str = "generating",
    message: str = "",
) -> None:
    """Push model info to Celery meta and architecture.generation_progress."""
    display = _display_model(provider, model)
    meta: dict[str, Any] = {
        "current_model": display,
        "current_provider": provider,
        "attempt": attempt,
        "phase": phase,
        "message": message or f"Generating with {model_display_name(model)}…",
    }
    arch_id = _architecture_id.get()
    doc_field = _doc_field.get()
    if doc_field:
        meta["current_doc"] = doc_field

    try:
        from celery import current_task  # noqa: PLC0415

        task = current_task._get_current_object()  # type: ignore[attr-defined]
        if task and getattr(task, "request", None) and task.request.id:
            task.update_state(state="PROGRESS", meta=meta)
    except Exception:
        pass

    if arch_id is None:
        return

    try:
        from app.core.database import SyncSessionLocal  # noqa: PLC0415
        from app.models.architecture import Architecture  # noqa: PLC0415

        db = SyncSessionLocal()
        try:
            arch = db.query(Architecture).filter(Architecture.id == arch_id).first()
            if arch is None:
                return
            progress = dict(arch.generation_progress or {})
            progress.update(
                {
                    "current_doc": doc_field,
                    "current_model": display,
                    "phase": phase,
                    "attempt": attempt,
                    "message": meta["message"],
                }
            )
            arch.generation_progress = progress
            if doc_field:
                status_field = f"{doc_field}_status"
                if hasattr(arch, status_field):
                    if phase == "rate_limited":
                        setattr(arch, status_field, "rate_limited")
                        arch.last_error = (
                            message or f"Rate limit on {model_display_name(model)} — switching model…"
                        )
                    elif phase == "generating":
                        setattr(arch, status_field, "processing")
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.debug("Could not persist architecture generation progress", exc_info=True)


def notify_rate_limit_switch(
    provider: str,
    model: str,
    attempt: int,
    next_provider: str | None,
    next_model: str | None,
) -> None:
    current_name = model_display_name(model)
    if next_model:
        next_name = model_display_name(next_model)
        message = (
            f"Rate limit on {current_name} — switching to {next_name} in 1s…"
        )
    else:
        message = f"Rate limit on {current_name} — trying next model in 1s…"
    notify_model_attempt(
        provider,
        model,
        attempt,
        phase="rate_limited",
        message=message,
    )
