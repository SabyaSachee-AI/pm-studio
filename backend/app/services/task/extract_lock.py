"""Redis mutex — one module-extract job per project at a time."""

from __future__ import annotations

import logging

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_EXTRACT_TTL_SEC = 3600
_KEY_PREFIX = "extract:project:"


def _client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def try_acquire_extract(project_id: str) -> bool:
    """Return True if this caller may start extraction for the project."""
    try:
        return bool(
            _client().set(f"{_KEY_PREFIX}{project_id}", "1", nx=True, ex=_EXTRACT_TTL_SEC)
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not acquire extract lock for %s — allowing run", project_id)
        return True


def release_extract(project_id: str) -> None:
    try:
        _client().delete(f"{_KEY_PREFIX}{project_id}")
    except Exception:  # noqa: BLE001
        pass
