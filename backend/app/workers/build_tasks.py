"""Celery tasks for code-generation builds."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.build import Build, BuildStatus
from app.services.ai.model_override import clear_model_override, set_model_override
from app.services.build.service import (
    build_scaffold,
    generate_build_code,
    generate_single_task_code,
)

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _project_info(db, build: Build) -> dict[str, Any]:
    from app.models.project import Project  # noqa: PLC0415
    project = db.query(Project).filter(Project.id == build.project_id).first()
    return {
        "name": project.name if project else "Project",
        "description": (project.description if project else "") or "",
    }


def _remember_model(db, build: Build, provider: str | None, model: str | None) -> None:
    """Persist the user's model pick so the autonomous CI-repair loop can reuse it
    (otherwise auto-repair would always fall back to the free chain)."""
    if not provider and not model:
        return
    report = dict(build.quality_report or {})
    report["preferred_model"] = {"provider": provider, "model": model}
    build.quality_report = report


@celery_app.task(bind=True, name="build.scaffold")
def scaffold_build_task(
    self,
    build_id: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Stage 0 — generate the repo skeleton."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    build: Build | None = None
    try:
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        db.commit()
        return _run_async(build_scaffold(UUID(build_id), db, _project_info(db, build)))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scaffold failed")
        if build is not None:
            build.status = BuildStatus.failed
            build.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


_AUTO_RESUME_MAX = 8          # how many times to auto re-enqueue before giving up
_AUTO_RESUME_COOLDOWN = 150   # seconds between auto-resumes (lets free quotas reset)


def _schedule_auto_resume(self, build_id: str, model_provider, model_id):
    """Re-enqueue this build (resume=True) so generation continues automatically
    from the last completed task — no manual click. Bounded by _AUTO_RESUME_MAX."""
    raise self.retry(
        kwargs={
            "build_id": build_id,
            "resume": True,
            "model_provider": model_provider,
            "model_id": model_id,
        },
        countdown=_AUTO_RESUME_COOLDOWN,
        max_retries=_AUTO_RESUME_MAX,
    )


@celery_app.task(bind=True, name="build.generate", max_retries=_AUTO_RESUME_MAX)
def generate_build_task(
    self,
    build_id: str,
    resume: bool = False,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Stage 1 — resumable chunked code generation for all tasks.

    Auto-continues: if a run stops because every model was momentarily
    exhausted, the task re-enqueues itself with resume=True after a cooldown
    and picks up from the last completed task. The user never clicks Resume.
    """
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    build: Build | None = None
    result: dict[str, Any] | None = None
    needs_resume = False
    try:
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        _remember_model(db, build, model_provider, model_id)
        db.commit()
        result = _run_async(generate_build_code(UUID(build_id), db, resume=resume))
        # Result-level failure (in-run retries exhausted) → auto-resume.
        if isinstance(result, dict) and result.get("status") == "failed":
            needs_resume = True
            # Show "waiting to auto-resume" rather than a hard failure.
            build.status = BuildStatus.generating
            build.generation_progress = {
                **(build.generation_progress or {}),
                "phase": "retrying",
                "message": "Models busy — auto-resuming shortly, continuing from where it stopped.",
            }
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Build code generation crashed")
        needs_resume = True
        if build is not None:
            build.can_resume = True
            build.last_error = str(exc)[:500]
            build.generation_progress = {
                **(build.generation_progress or {}),
                "phase": "retrying",
                "message": "Interrupted — auto-resuming shortly.",
            }
            db.commit()
        result = {"error": str(exc)[:500], "status": "failed"}
    finally:
        db.close()
        clear_model_override()

    if needs_resume:
        try:
            _schedule_auto_resume(self, build_id, model_provider, model_id)
        except self.MaxRetriesExceededError:
            # Truly exhausted after many auto-resumes — leave it resumable for a manual retry.
            db2 = SyncSessionLocal()
            try:
                b = db2.query(Build).filter(Build.id == UUID(build_id)).first()
                if b is not None:
                    b.status = BuildStatus.failed
                    b.can_resume = True
                    db2.commit()
            finally:
                db2.close()
            return result or {"error": "exhausted auto-resume"}
    return result


@celery_app.task(bind=True, name="build.push")
def push_build_to_github_task(self, build_id: str) -> dict[str, Any]:
    """Push generated files to GitHub in one commit (triggers CI)."""
    db = SyncSessionLocal()
    build: Build | None = None
    try:
        from app.services.build.github import push_build  # noqa: PLC0415
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        # A user-initiated push is a fresh start: reset the auto-repair budget and
        # clear any "auto-repair stopped" notice so the loop can try again.
        report = dict(build.quality_report or {})
        report["repair_attempts"] = 0
        report.pop("auto_ci", None)
        build.quality_report = report
        db.commit()
        result = _run_async(push_build(UUID(build_id), db, _project_info(db, build)["name"]))
        # Kick off the autonomous CI loop: watch CI → on failure AI-repair + re-push,
        # repeat until green or repair attempts run out. No manual clicks.
        if isinstance(result, dict) and result.get("status") == "pushed":
            auto_ci_watch_task.apply_async((build_id, 0), countdown=25, queue="build")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("GitHub push failed")
        if build is not None:
            build.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()


@celery_app.task(bind=True, name="build.deploy")
def deploy_build_task(self, build_id: str, port: int | None = None) -> dict[str, Any]:
    """Stage 7 — set VPS secrets + trigger the deploy workflow on the repo."""
    db = SyncSessionLocal()
    try:
        from app.services.build.deploy import deploy_build  # noqa: PLC0415
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        db.commit()
        return _run_async(deploy_build(UUID(build_id), db, port=port))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Deploy failed")
        return {"error": str(exc)[:500]}
    finally:
        db.close()


@celery_app.task(bind=True, name="build.generate_tests")
def generate_tests_task(self, build_id: str, model_provider: str | None = None, model_id: str | None = None) -> dict[str, Any]:
    """Stage 3 — generate automated tests from acceptance criteria."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    build: Build | None = None
    try:
        from app.services.build.service import generate_build_tests  # noqa: PLC0415
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        db.commit()
        return _run_async(generate_build_tests(UUID(build_id), db))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Test generation failed")
        if build is not None:
            build.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


@celery_app.task(bind=True, name="build.polish")
def polish_build_task(
    self, build_id: str, scope: str = "critical",
    model_provider: str | None = None, model_id: str | None = None,
) -> dict[str, Any]:
    """Quality polish pass — uses the selected model (or the code_polish chain)."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    build: Build | None = None
    try:
        from app.services.build.service import polish_build  # noqa: PLC0415
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        db.commit()
        return _run_async(polish_build(UUID(build_id), db, scope=scope))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Polish failed")
        if build is not None:
            build.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


@celery_app.task(bind=True, name="build.repair")
def repair_build_task(
    self, build_id: str,
    model_provider: str | None = None, model_id: str | None = None,
) -> dict[str, Any]:
    """One AI repair cycle from the failed CI logs, then re-push (triggers CI).

    Honors an optional model override so the user can run repair on a stronger
    model (e.g. Claude) for accuracy, even while generation stays on the free chain.
    """
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    build: Build | None = None
    try:
        from app.services.build.service import repair_build_from_ci  # noqa: PLC0415
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        # Manual "Fix with AI" = user intent → give a fresh repair budget even if
        # the auto-loop had stopped at the limit.
        report = dict(build.quality_report or {})
        report["repair_attempts"] = 0
        build.quality_report = report
        _remember_model(db, build, model_provider, model_id)
        db.commit()
        result = _run_async(
            repair_build_from_ci(UUID(build_id), db, _project_info(db, build)["name"])
        )
        # Resume the autonomous watcher after a manual fix re-push.
        if isinstance(result, dict) and result.get("status") == "repaired":
            auto_ci_watch_task.apply_async((build_id, 0), countdown=30, queue="build")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("CI repair failed")
        if build is not None:
            build.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()


_AUTO_CI_POLL = 20        # seconds between CI status polls
_AUTO_CI_MAX_POLLS = 90   # ~30 min hard cap waiting for one CI run to finish


def _set_auto_ci(db, build: Build, phase: str, message: str) -> None:
    """Record autonomous-CI progress so the UI can show it live."""
    report = dict(build.quality_report or {})
    report["auto_ci"] = {
        "phase": phase, "message": message,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    build.quality_report = report
    db.commit()


@celery_app.task(bind=True, name="build.auto_ci", max_retries=None)
def auto_ci_watch_task(self, build_id: str, polls: int = 0) -> dict[str, Any]:
    """Autonomous CI loop: watch the latest CI run; on failure read the logs,
    AI-fix the code, and re-push; repeat until CI is green or repair attempts run
    out. Re-schedules itself (never blocks a worker)."""
    from app.services.build.github import get_qa_status  # noqa: PLC0415
    from app.services.build.service import (  # noqa: PLC0415
        _MAX_REPAIR_ATTEMPTS,
        repair_build_from_ci,
    )

    db = SyncSessionLocal()
    try:
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build or not build.github_full_name:
            return {"stop": "no build/repo"}

        qa = _run_async(get_qa_status(UUID(build_id), db))
        status = qa.get("status")
        conclusion = qa.get("conclusion")

        # CI status unreadable (token issues) → stop, leave for the user.
        if status in ("blocked", "auth_failed", "error"):
            _set_auto_ci(db, build, "stopped",
                         f"Auto-CI stopped — {qa.get('error') or 'cannot read CI status'}.")
            return {"stop": status}

        # Not finished yet → poll again later.
        if conclusion is None:
            if polls >= _AUTO_CI_MAX_POLLS:
                _set_auto_ci(db, build, "stopped", "Auto-CI stopped — CI did not finish in time.")
                return {"stop": "timeout"}
            _set_auto_ci(db, build, "watching", "Waiting for CI to finish on GitHub…")
            auto_ci_watch_task.apply_async(
                (build_id, polls + 1), countdown=_AUTO_CI_POLL, queue="build"
            )
            return {"wait": status}

        # CI passed.
        if conclusion == "success":
            _set_auto_ci(db, build, "passed", "CI passed — build is ready.")
            return {"done": "passed"}

        # CI failed → AI-repair if attempts remain.
        report = dict(build.quality_report or {})
        attempts = int(report.get("repair_attempts") or 0)
        if attempts >= _MAX_REPAIR_ATTEMPTS:
            _set_auto_ci(db, build, "stopped",
                         f"Auto-repair tried {attempts}× and CI still fails — manual review needed.")
            return {"stop": "limit"}

        from app.models.project import Project  # noqa: PLC0415
        project = db.query(Project).filter(Project.id == build.project_id).first()
        pname = project.name if project else "project"
        # Reuse the model the user picked for this build (else the free chain).
        pref = (report.get("preferred_model") or {}) if isinstance(report, dict) else {}
        _set_auto_ci(db, build, "repairing",
                     f"CI failed — AI reading logs & fixing (attempt {attempts + 1}/{_MAX_REPAIR_ATTEMPTS})…")
        set_model_override(pref.get("provider"), pref.get("model"))
        try:
            result = _run_async(repair_build_from_ci(UUID(build_id), db, pname))
        finally:
            clear_model_override()
        if isinstance(result, dict) and "error" in result:
            _set_auto_ci(db, build, "stopped", f"Auto-repair could not continue — {result['error']}")
            return {"stop": result["error"]}

        # Repair re-pushed → a fresh CI run is starting; watch it from scratch.
        _set_auto_ci(db, build, "repushed",
                     f"Fixed {result.get('files_fixed', 0)} file(s) & re-pushed — watching new CI run…")
        auto_ci_watch_task.apply_async((build_id, 0), countdown=30, queue="build")
        return {"repaired": attempts + 1}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Auto-CI watcher crashed")
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


@celery_app.task(bind=True, name="build.generate_task")
def generate_task_code_task(
    self,
    build_id: str,
    task_id: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Re/generate code for a single task."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    try:
        return _run_async(
            generate_single_task_code(UUID(build_id), UUID(task_id), db)
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Single-task code generation failed")
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()
