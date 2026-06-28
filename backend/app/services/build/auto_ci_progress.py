"""Live auto-CI progress + stale detection for the build screen.

Every auto-CI update writes heartbeat_at. If the worker dies mid-repair, the next
GET /builds/{id} (or worker startup) clears the stale phase and releases the Redis
lock so the user can retry with Fix with AI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models.build import Build

logger = logging.getLogger(__name__)

_ACTIVE_PHASES = frozenset({"watching", "repairing", "repushed"})

# Max silence before we treat the worker as dead (seconds).
_STALE_SEC = {
    "repairing": 10 * 60,   # _live() heartbeats every batch; 10 min silence = dead worker
    "watching": 40 * 60,
    "repushed": 40 * 60,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _heartbeat_age_sec(auto: dict[str, Any]) -> float | None:
    ts = auto.get("heartbeat_at") or auto.get("at")
    parsed = _parse_iso(str(ts) if ts else None)
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def is_auto_ci_stale(auto: dict[str, Any] | None) -> bool:
    """True when auto_ci claims to be active but the worker has gone silent."""
    if not auto:
        return False
    phase = auto.get("phase")
    if phase not in _ACTIVE_PHASES:
        return False
    age = _heartbeat_age_sec(auto)
    if age is None:
        return False
    limit = _STALE_SEC.get(str(phase), 20 * 60)
    return age > limit


def patch_auto_ci(db, build: Build, *, reset_at: bool = False, **extra: Any) -> None:
    """Merge fields into quality_report.auto_ci; always refreshes heartbeat_at."""
    report = dict(build.quality_report or {})
    auto = dict(report.get("auto_ci") or {})
    if reset_at or not auto.get("at"):
        auto["at"] = _now_iso()
    auto["heartbeat_at"] = _now_iso()
    auto.update(extra)
    report["auto_ci"] = auto
    build.quality_report = report
    db.commit()


# Live-activity fields that must not linger once auto-repair stops/passes.
_ACTIVITY_FIELDS = (
    "activity_step", "activity_detail", "batch_current", "batch_total",
    "files_fixed_so_far", "files_targeted", "current_model", "model_attempt",
    "repair_cycle", "repair_cycle_max",
)


def set_auto_ci_phase(
    db, build: Build, phase: str, message: str, **extra: Any,
) -> None:
    """Start or switch an auto-CI phase (resets the elapsed timer).

    On a terminal phase (stopped/passed) clear the live-activity fields so no
    stale "AI fixing…" / batch progress lingers in the UI.
    """
    extra.setdefault("stale", False)
    if phase not in _ACTIVE_PHASES:
        for k in _ACTIVITY_FIELDS:
            extra.setdefault(k, None)
    patch_auto_ci(
        db, build,
        reset_at=True,
        phase=phase,
        message=message,
        **extra,
    )


def clear_stale_auto_ci(db, build: Build) -> bool:
    """If auto_ci is orphaned, mark stopped and release the Redis lock. Returns True if cleared."""
    report = dict(build.quality_report or {})
    auto = dict(report.get("auto_ci") or {})
    if not is_auto_ci_stale(auto):
        return False

    from app.services.build.push_lock import release_auto_ci  # noqa: PLC0415

    phase = auto.get("phase", "unknown")
    age = _heartbeat_age_sec(auto)
    logger.warning(
        "Clearing stale auto_ci for build %s (phase=%s, silent %.0fs)",
        build.id, phase, age or 0,
    )
    release_auto_ci(str(build.id))
    set_auto_ci_phase(
        db, build, "stopped",
        "Auto-repair was interrupted — click Fix with AI & re-push to continue.",
        activity_step="stopped",
        activity_detail=(
            f"Worker stopped responding during {phase} "
            f"(no update for {int(age or 0)}s). Safe to retry."
        ),
        stale=True,
        stale_cleared_at=_now_iso(),
    )
    return True


def reconcile_auto_ci(db, build: Build) -> str:
    """Ensure auto_ci reflects reality. Returns: ok | active | stale_cleared | lock_released."""
    from app.services.build.push_lock import auto_ci_lock_held, release_auto_ci  # noqa: PLC0415

    report = dict(build.quality_report or {})
    auto = dict(report.get("auto_ci") or {})
    phase = auto.get("phase")
    build_id = str(build.id)

    if auto_ci_lock_held(build_id) and phase not in _ACTIVE_PHASES:
        release_auto_ci(build_id)
        return "lock_released"

    if phase not in _ACTIVE_PHASES:
        return "ok"
    if is_auto_ci_stale(auto):
        clear_stale_auto_ci(db, build)
        return "stale_cleared"
    return "active"


def touch_auto_ci_heartbeat(db, build: Build, **extra: Any) -> None:
    """Lightweight heartbeat during long polls (no full message rewrite)."""
    patch_auto_ci(db, build, **extra)
