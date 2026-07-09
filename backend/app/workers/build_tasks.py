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
from app.services.build.job_progress import build_job_scope, emit_build_task_progress

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


def _notify_build_event(db, build: Build, title: str, message: str) -> None:
    """In-app notification for the build's creator (bell icon) on key events.

    Sync (workers). Best-effort — a notification failure must never break a build.
    """
    try:
        from app.models.notification import Notification  # noqa: PLC0415
        from app.models.user import User, UserRole  # noqa: PLC0415

        user_ids = []
        if build.created_by_id:
            user_ids = [build.created_by_id]
        else:
            owners = db.query(User.id).filter(
                User.deleted_at.is_(None), User.role == UserRole.studio_owner
            ).all()
            user_ids = [u.id for u in owners]
        for uid in user_ids:
            db.add(Notification(
                user_id=uid,
                title=title,
                message=message[:900],
                link=f"/build/{build.id}",
                is_read=False,
            ))
        db.commit()
    except Exception:  # noqa: BLE001
        logger.debug("Build notification failed (non-fatal)", exc_info=True)


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
    emit_build_task_progress(
        self, phase="scaffolding", message="Scaffolding repository…",
    )
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
        with build_job_scope(build_id):
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
    # build_id must go through `args` only. The task is originally invoked with
    # build_id as a POSITIONAL arg, and self.retry() re-uses request.args; also
    # passing build_id in kwargs makes Celery raise
    # "got multiple values for argument 'build_id'", which crashed every resume.
    raise self.retry(
        args=(build_id,),
        kwargs={
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
    emit_build_task_progress(
        self, phase="generating", message="Starting code generation…",
    )
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
        with build_job_scope(build_id):
            result = _run_async(generate_build_code(UUID(build_id), db, resume=resume))
        if isinstance(result, dict) and result.get("status") == "completed":
            _notify_build_event(
                db, build, "Code generation finished",
                f"All {result.get('tasks', '?')} tasks generated "
                f"({result.get('file_count', '?')} files). Next: push to GitHub.",
            )
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
                    _notify_build_event(
                        db2, b, "Code generation needs attention",
                        "Generation paused after repeated retries (AI quotas). "
                        "Open the build and press Resume, or switch to a premium model.",
                    )
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
        from app.services.build.push_lock import release_auto_ci  # noqa: PLC0415
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        build.generation_task_id = self.request.id
        release_auto_ci(build_id)
        # A user-initiated push is a fresh start: reset the auto-repair budget and
        # clear any "auto-repair stopped" notice so the loop can try again.
        report = dict(build.quality_report or {})
        report["repair_attempts"] = 0
        report.pop("auto_ci", None)
        build.quality_report = report
        db.commit()
        result = _run_async(push_build(UUID(build_id), db, _project_info(db, build)["name"]))
        # Push only — CI is now a separate, manual step (workflow_dispatch). This
        # gives the user a window to clone/test/commit locally before running CI.
        # The "Run CI/QA" button (run_ci_task) dispatches CI and starts the watcher.
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("GitHub push failed")
        if build is not None:
            build.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()


def _dispatch_ci_run(full_name: str | None, branch: str | None) -> bool:
    """Manually trigger the CI workflow (workflow_dispatch). Returns True if queued.

    CI no longer runs on push — every push (initial or an auto-repair re-push)
    that needs CI must call this so a run actually starts on GitHub.
    """
    if not full_name:
        return False
    from app.services.build.github import trigger_workflow  # noqa: PLC0415
    try:
        return _run_async(trigger_workflow(full_name, "ci.yml", branch or "main"))
    except Exception:  # noqa: BLE001
        logger.exception("CI dispatch failed for %s", full_name)
        return False


@celery_app.task(bind=True, name="build.run_ci")
def run_ci_task(self, build_id: str) -> dict[str, Any]:
    """Stage 4 — manually start CI/QA: dispatch the CI workflow, then watch it.

    Separate from push so the user can clone, test and re-push locally first,
    then start CI when they are ready. On failure the watcher AI-repairs and
    re-pushes (re-dispatching CI) until green or the repair budget runs out.
    """
    db = SyncSessionLocal()
    build: Build | None = None
    try:
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build:
            return {"error": "Build not found"}
        if not build.github_full_name:
            return {"error": "Not pushed to GitHub yet — push first"}
        build.generation_task_id = self.request.id
        # A user-initiated CI run is a fresh start: reset the auto-repair budget.
        report = dict(build.quality_report or {})
        report["repair_attempts"] = 0
        report.pop("auto_ci", None)
        build.quality_report = report
        db.commit()
        dispatched = _dispatch_ci_run(build.github_full_name, build.default_branch)
        if not dispatched:
            build.last_error = "Could not start CI on GitHub (workflow_dispatch failed)."
            db.commit()
            return {"error": "CI dispatch failed"}
        # Give GitHub a moment to register the run, then start the watcher loop.
        _schedule_auto_ci(build_id, polls=0, countdown=25)
        return {"status": "ci_started", "repo": build.github_full_name}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Run CI failed")
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
        # Resume the autonomous watcher after a manual fix re-push. CI no longer
        # runs on push, so dispatch it explicitly for the new commit.
        if isinstance(result, dict) and result.get("status") == "repaired":
            _dispatch_ci_run(build.github_full_name, build.default_branch)
            _schedule_auto_ci(build_id, polls=0, countdown=30)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("CI repair failed")
        if build is not None:
            build.last_error = str(exc)[:500]
            report = dict(build.quality_report or {})
            report["repair_plan"] = {"targeted": [], "fixed": 0, "error": str(exc)[:200]}
            build.quality_report = report
            auto = dict(report.get("auto_ci") or {})
            if auto.get("phase") in ("watching", "repairing", "repushed"):
                from app.services.build.auto_ci_progress import set_auto_ci_phase  # noqa: PLC0415
                from app.services.build.push_lock import release_auto_ci  # noqa: PLC0415

                set_auto_ci_phase(
                    db, build, "stopped",
                    f"Repair failed — {str(exc)[:120]}",
                    activity_step="stopped",
                )
                release_auto_ci(build_id)
            else:
                db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


_AUTO_CI_POLL = 20        # seconds between CI status polls
_AUTO_CI_MAX_POLLS = 90   # ~30 min hard cap waiting for one CI run to finish


def _schedule_auto_ci(
    build_id: str,
    polls: int = 0,
    countdown: int = 25,
    *,
    continue_chain: bool = False,
) -> str | None:
    """Enqueue auto-CI watcher with deduplication (one chain per build).

    Use continue_chain=True when re-scheduling mid-chain (e.g. after repush) — the
    Redis lock is already held and must not be re-acquired with SET NX.
    """
    from app.services.build.auto_ci_progress import (  # noqa: PLC0415
        clear_stale_auto_ci,
        is_auto_ci_stale,
    )
    from app.services.build.push_lock import (  # noqa: PLC0415
        refresh_auto_ci,
        release_auto_ci,
        try_acquire_auto_ci,
    )

    if continue_chain or polls > 0:
        refresh_auto_ci(build_id)
    elif not try_acquire_auto_ci(build_id):
        stale_db = SyncSessionLocal()
        try:
            stale_build = stale_db.query(Build).filter(
                Build.id == UUID(build_id), Build.deleted_at.is_(None),
            ).first()
            if stale_build:
                auto = dict((stale_build.quality_report or {}).get("auto_ci") or {})
                if is_auto_ci_stale(auto):
                    clear_stale_auto_ci(stale_db, stale_build)
                    if not try_acquire_auto_ci(build_id):
                        logger.info("Auto-CI lock still held for build %s after stale clear", build_id)
                        return None
                else:
                    logger.info(
                        "Auto-CI already active for build %s — skipping duplicate watcher", build_id,
                    )
                    return None
            else:
                return None
        finally:
            stale_db.close()
    try:
        result = auto_ci_watch_task.apply_async(
            (build_id, polls), countdown=countdown, queue="build",
        )
        return result.id
    except Exception:  # noqa: BLE001
        if polls == 0 and not continue_chain:
            release_auto_ci(build_id)
        raise


def resume_orphaned_build_jobs() -> int:
    """Re-enqueue scaffold/generate jobs lost when the build worker restarted."""
    from celery.result import AsyncResult  # noqa: PLC0415

    from app.core.celery_app import celery_app  # noqa: PLC0415

    def _task_is_live(task_id: str) -> bool:
        try:
            insp = celery_app.control.inspect(timeout=2.0)
            for bucket in (insp.active() or {}, insp.reserved() or {}):
                for worker_tasks in bucket.values():
                    for t in worker_tasks:
                        if t.get("id") == task_id:
                            return True
        except Exception:  # noqa: BLE001
            pass
        return False

    db = SyncSessionLocal()
    resumed = 0
    now = datetime.now(timezone.utc)
    try:
        builds = db.query(Build).filter(
            Build.deleted_at.is_(None),
            Build.status.in_([BuildStatus.scaffolding, BuildStatus.generating]),
        ).all()
        for build in builds:
            tid = build.generation_task_id
            if not tid or _task_is_live(tid):
                continue
            ar = AsyncResult(tid, app=celery_app)
            if ar.status in ("SUCCESS", "FAILURE"):
                continue
            gp = dict(build.generation_progress or {})
            hb = gp.get("heartbeat_at")
            stale = False
            if isinstance(hb, str):
                try:
                    hb_dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
                    stale = (now - hb_dt).total_seconds() > 120
                except ValueError:
                    stale = True
            else:
                updated = build.updated_at
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                stale = (now - updated).total_seconds() > 180
            if not stale:
                continue
            if build.status == BuildStatus.scaffolding:
                task = scaffold_build_task.delay(str(build.id))
            else:
                task = generate_build_task.delay(str(build.id), resume=True)
            build.generation_task_id = task.id
            gp["message"] = "Resuming after worker restart…"
            build.generation_progress = gp
            db.commit()
            resumed += 1
            logger.info("Re-enqueued orphaned build job for %s (was %s)", build.id, tid)
    finally:
        db.close()
    return resumed


@celery_app.task(name="build.orphan_sweep")
def orphan_sweep_task() -> dict[str, int]:
    """Periodic self-healing (beat): resume builds/watchers whose task died.

    The startup-time resume misses builds that were updated seconds before a
    restart (not yet "stale"); this sweep catches them on the next tick, so a
    build can never sit in "generating" forever with no live task.
    """
    n_build = resume_orphaned_build_jobs()
    n_ci = resume_orphaned_auto_ci()
    if n_build or n_ci:
        logger.info("Orphan sweep resumed %s build(s), %s auto-CI watcher(s)", n_build, n_ci)
    return {"builds": n_build, "auto_ci": n_ci}


def resume_orphaned_auto_ci() -> int:
    """Re-enqueue auto-CI watchers for builds interrupted by a worker restart."""
    from app.services.build.auto_ci_progress import (  # noqa: PLC0415
        clear_stale_auto_ci,
        is_auto_ci_stale,
    )
    from app.services.build.push_lock import auto_ci_lock_held  # noqa: PLC0415

    db = SyncSessionLocal()
    resumed = 0
    try:
        builds = db.query(Build).filter(
            Build.deleted_at.is_(None),
            Build.github_full_name.isnot(None),
        ).all()
        for build in builds:
            report = dict(build.quality_report or {})
            auto = dict(report.get("auto_ci") or {})
            if auto.get("phase") not in ("watching", "repairing", "repushed"):
                continue
            if is_auto_ci_stale(auto):
                clear_stale_auto_ci(db, build)
                logger.info("Cleared stale auto-CI for build %s on worker startup", build.id)
                continue
            continuing = auto_ci_lock_held(str(build.id))
            if _schedule_auto_ci(
                str(build.id), polls=0, countdown=5, continue_chain=continuing,
            ):
                resumed += 1
                logger.info("Resumed auto-CI watcher for build %s", build.id)
    finally:
        db.close()
    return resumed


def _set_auto_ci(db, build: Build, phase: str, message: str, **extra: object) -> None:
    """Record autonomous-CI progress so the UI can show it live."""
    from app.services.build.auto_ci_progress import set_auto_ci_phase  # noqa: PLC0415

    set_auto_ci_phase(db, build, phase, message, **extra)


def _sync_auto_ci_ai_meta(db, build: Build) -> None:
    """Copy live AI model/attempt from the running Celery task into auto_ci."""
    try:
        from celery import current_task  # noqa: PLC0415
        from celery.result import AsyncResult  # noqa: PLC0415
        from app.services.build.auto_ci_progress import patch_auto_ci  # noqa: PLC0415

        tid = getattr(getattr(current_task, "request", None), "id", None)
        if not tid:
            return
        info = AsyncResult(tid).info
        if not isinstance(info, dict):
            return
        extra: dict[str, object] = {}
        if info.get("current_model"):
            extra["current_model"] = info["current_model"]
        if info.get("attempt"):
            extra["model_attempt"] = info["attempt"]
        if info.get("message"):
            extra["activity_detail"] = info["message"]
        if extra:
            patch_auto_ci(db, build, **extra)
    except Exception:  # noqa: BLE001
        pass


def _preferred_model_label(report: dict) -> str | None:
    pref = report.get("preferred_model") or {}
    if isinstance(pref, dict) and pref.get("model"):
        provider = pref.get("provider") or ""
        model = pref.get("model") or ""
        return f"{provider} / {model}".strip(" /") if provider else str(model)
    return None


@celery_app.task(bind=True, name="build.auto_ci", max_retries=None)
def auto_ci_watch_task(self, build_id: str, polls: int = 0) -> dict[str, Any]:
    """Autonomous CI loop: watch the latest CI run; on failure read the logs,
    AI-fix the code, and re-push; repeat until CI is green or repair attempts run
    out. Re-schedules itself (never blocks a worker)."""
    from app.services.build.github import get_qa_status  # noqa: PLC0415
    from app.services.build.push_lock import release_auto_ci  # noqa: PLC0415
    from app.services.build.service import (  # noqa: PLC0415
        _MAX_REPAIR_ATTEMPTS,
        repair_build_from_ci,
    )

    db = SyncSessionLocal()
    build: Build | None = None
    try:
        build = db.query(Build).filter(
            Build.id == UUID(build_id), Build.deleted_at.is_(None)
        ).first()
        if not build or not build.github_full_name:
            release_auto_ci(build_id)
            return {"stop": "no build/repo"}

        qa = _run_async(get_qa_status(UUID(build_id), db))
        status = qa.get("status")
        conclusion = qa.get("conclusion")

        # CI status unreadable (token issues) → stop, leave for the user.
        if status in ("blocked", "auth_failed", "error"):
            _set_auto_ci(db, build, "stopped",
                         f"Auto-CI stopped — {qa.get('error') or 'cannot read CI status'}.")
            release_auto_ci(build_id)
            return {"stop": status}

        # Not finished yet → poll again later.
        if conclusion is None:
            if polls >= _AUTO_CI_MAX_POLLS:
                _set_auto_ci(db, build, "stopped", "Auto-CI stopped — CI did not finish in time.")
                release_auto_ci(build_id)
                return {"stop": "timeout"}
            _set_auto_ci(
                db, build, "watching", "Waiting for CI to finish on GitHub…",
                activity_step="waiting_ci",
                activity_detail="Polling GitHub Actions for the latest run…",
            )
            _schedule_auto_ci(build_id, polls + 1, countdown=_AUTO_CI_POLL)
            return {"wait": status}

        # CI passed.
        if conclusion == "success":
            _set_auto_ci(db, build, "passed", "CI passed — build is ready.")
            release_auto_ci(build_id)
            _notify_build_event(
                db, build, "CI passed ✅",
                "All quality gates are green. Next: Local UI test or Deploy to VPS.",
            )
            return {"done": "passed"}

        # CI failed → AI-repair if attempts remain.
        report = dict(build.quality_report or {})
        attempts = int(report.get("repair_attempts") or 0)
        if attempts >= _MAX_REPAIR_ATTEMPTS:
            _set_auto_ci(db, build, "stopped",
                         f"Auto-repair tried {attempts}× and CI still fails — manual review needed.")
            release_auto_ci(build_id)
            _notify_build_event(
                db, build, "CI still failing after auto-repair",
                f"Auto-repair tried {attempts}x and CI is still red. "
                "Open the build to review the failure and fix manually or with AI.",
            )
            return {"stop": "limit"}

        from app.models.project import Project  # noqa: PLC0415
        project = db.query(Project).filter(Project.id == build.project_id).first()
        pname = project.name if project else "project"
        pref = (report.get("preferred_model") or {}) if isinstance(report, dict) else {}
        model_label = _preferred_model_label(report) or "Auto (free model chain)"
        build.generation_task_id = self.request.id
        db.commit()
        _set_auto_ci(
            db, build, "repairing",
            f"CI failed — AI reading logs & fixing (attempt {attempts + 1}/{_MAX_REPAIR_ATTEMPTS})…",
            current_model=model_label,
            repair_cycle=attempts + 1,
            repair_cycle_max=_MAX_REPAIR_ATTEMPTS,
            activity_step="read_logs",
            activity_detail="Downloading CI logs from GitHub…",
        )
        set_model_override(pref.get("provider"), pref.get("model"))
        try:
            result = _run_async(repair_build_from_ci(UUID(build_id), db, pname))
            _sync_auto_ci_ai_meta(db, build)
        finally:
            clear_model_override()
        if isinstance(result, dict) and "error" in result:
            _set_auto_ci(db, build, "stopped", f"Auto-repair could not continue — {result['error']}")
            release_auto_ci(build_id)
            return {"stop": result["error"]}

        # CI no longer auto-runs on push — dispatch a fresh run for the fix commit.
        _dispatch_ci_run(build.github_full_name, build.default_branch)
        _set_auto_ci(
            db, build, "repushed",
            f"Fixed {result.get('files_fixed', 0)} file(s) & re-pushed — watching new CI run…",
            activity_step="waiting_ci",
            activity_detail="Push complete — waiting for GitHub to start a new CI run…",
            files_fixed=result.get("files_fixed", 0),
        )
        _schedule_auto_ci(build_id, polls=0, countdown=30, continue_chain=True)
        return {"repaired": attempts + 1}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Auto-CI watcher crashed")
        if build is not None:
            _set_auto_ci(db, build, "stopped", f"Auto-CI crashed — {str(exc)[:120]}")
            db.commit()
        release_auto_ci(build_id)
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
