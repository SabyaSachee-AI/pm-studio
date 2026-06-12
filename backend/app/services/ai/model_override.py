"""Per-request user model override — set by Celery tasks / routes, read by the AI router.

A user can pick a specific model in the UI dropdown before pressing an AI action
button. The chosen (provider, model) is carried through a ContextVar so service
code does not need to thread it through every function signature. If the chosen
model fails, the router falls back to the normal tier chain.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_model_override: ContextVar[tuple[str, str] | None] = ContextVar(
    "ai_model_override", default=None
)


def set_model_override(provider: str | None, model: str | None) -> None:
    if provider and model:
        _model_override.set((provider, model))
    else:
        _model_override.set(None)


def get_model_override() -> tuple[str, str] | None:
    return _model_override.get()


def clear_model_override() -> None:
    _model_override.set(None)


@contextmanager
def model_override_scope(
    provider: str | None,
    model: str | None,
) -> Iterator[None]:
    """Set a one-shot model override for the current async task or Celery worker."""
    set_model_override(provider, model)
    try:
        yield
    finally:
        clear_model_override()
