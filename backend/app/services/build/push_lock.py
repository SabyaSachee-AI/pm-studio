"""Redis-backed mutex for GitHub pushes and auto-CI watchers.

Prevents concurrent pushes to the same repo (the main cause of GitHub 422
non-fast-forward errors when duplicate workers or overlapping repair cycles run).
"""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from typing import Iterator

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PUSH_TTL_SEC = 180
_PUSH_WAIT_SEC = 90
_AUTO_CI_TTL_SEC = 3600


def _client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def _release(key: str, token: str) -> None:
    script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    try:
        _client().eval(script, 1, key, token)
    except Exception:  # noqa: BLE001
        pass


@contextlib.contextmanager
def build_push_lock(build_id: str) -> Iterator[bool]:
    """Yield True when the push lock is held, False if wait timed out."""
    key = f"build:push:{build_id}"
    token = str(uuid.uuid4())
    deadline = time.monotonic() + _PUSH_WAIT_SEC
    acquired = False
    try:
        client = _client()
        while time.monotonic() < deadline:
            if client.set(key, token, nx=True, ex=_PUSH_TTL_SEC):
                acquired = True
                break
            time.sleep(0.5)
        if not acquired:
            logger.warning("Push lock timeout for build %s", build_id)
        yield acquired
    finally:
        if acquired:
            _release(key, token)


def try_acquire_auto_ci(build_id: str) -> bool:
    """Return True if this process may start/resume an auto-CI watcher chain."""
    return bool(_client().set(f"build:auto_ci:{build_id}", "1", nx=True, ex=_AUTO_CI_TTL_SEC))


def auto_ci_lock_held(build_id: str) -> bool:
    try:
        return bool(_client().exists(f"build:auto_ci:{build_id}"))
    except Exception:  # noqa: BLE001
        return False


def release_auto_ci(build_id: str) -> None:
    try:
        _client().delete(f"build:auto_ci:{build_id}")
    except Exception:  # noqa: BLE001
        pass


def refresh_auto_ci(build_id: str) -> None:
    """Extend the auto-CI lock while a watcher chain is active."""
    try:
        _client().expire(f"build:auto_ci:{build_id}", _AUTO_CI_TTL_SEC)
    except Exception:  # noqa: BLE001
        pass
