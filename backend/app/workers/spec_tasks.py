"""Celery tasks for technical spec generation."""

import asyncio
import logging
import time
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.prd import PRD
from app.models.project import Project
from app.models.srs import SRS
from app.models.task import Task
from app.models.task_spec import TaskSpec, TaskSpecStatus
from app.services.ai.job_progress import publish_job_progress
from app.services.ai.model_override import clear_model_override, get_model_override, set_model_override
from app.services.spec.service import (
    build_spec_progress_payload,
    generate_spec_ai,
    parse_spec_resume_state,
    strip_spec_progress,
)
from app.services.task.system_prompts import SYSTEM_TASK_ORDERS, build_git_commit_block

logger = logging.getLogger(__name__)


def _git_commit_block_for(db, task: Task) -> str | None:
    """Return the git commit block for this spec, or None when it should be omitted.

    Modules with 3+ tasks get the block only on the last task (highest
    order_index) to batch commits per module; smaller modules get it on
    every task.
    """
    if task.order_index in SYSTEM_TASK_ORDERS:
        return None

    module_name = task.module_name or ""
    if module_name:
        module_tasks: list[Task] = (
            db.query(Task)
            .filter(
                Task.project_id == task.project_id,
                Task.module_name == module_name,
                Task.deleted_at.is_(None),
                Task.order_index.notin_(list(SYSTEM_TASK_ORDERS)),
            )
            .all()
        )
    else:
        module_tasks = [task]

    is_last_in_module = task.order_index == max(
        (t.order_index for t in module_tasks), default=task.order_index
    )
    if len(module_tasks) >= 3 and not is_last_in_module:
        return None

    return build_git_commit_block(
        task_title=task.title,
        task_type=task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type),
        module_name=module_name or "general",
        suggested_file=task.suggested_file,
        is_last_in_module=is_last_in_module,
    )


# Hand off to a fresh job before Celery's 90 min soft / 2 h hard limits — each
# finished spec is already saved, so the chain runs until every task has a spec.
_ALL_SPECS_BATCH_SEC = 4200  # 70 min (50 min buffer before soft limit)


def _enqueue_spec_generate_all(
    project_id: str,
    *,
    model_provider: str | None,
    model_id: str | None,
    chain_depth: int,
) -> str:
    """Start the next generate-all batch (only_missing=True). Returns new task id."""
    nxt = generate_all_specs_task.apply_async(
        kwargs={
            "project_id": project_id,
            "only_missing": True,
            "model_provider": model_provider,
            "model_id": model_id,
            "chain_depth": chain_depth + 1,
        },
        countdown=5,
    )
    return nxt.id


@celery_app.task(bind=True, name="spec.generate_all")
def generate_all_specs_task(
    self,
    project_id: str,
    only_missing: bool = True,
    model_provider: str | None = None,
    model_id: str | None = None,
    chain_depth: int = 0,
) -> dict[str, object]:
    """Generate specs for every task in a project, one at a time (serially).

    Reuses the exact per-task generator (`generate_spec_task`) so each spec is
    produced identically to the individual button. Runs entirely on the worker,
    so it keeps going even if the browser tab is closed. Reports live progress
    via Celery task meta (current/total) for the status bar.

    Every generated spec is persisted immediately. When the batch runs close to
    Celery's time limit it re-enqueues itself (only_missing=True) and returns
    ``continued_task_id`` so the UI keeps following the new job.
    """
    db = SyncSessionLocal()
    started = time.monotonic()
    try:
        tasks = (
            db.query(Task)
            .filter(
                Task.project_id == UUID(project_id),
                Task.deleted_at.is_(None),
                Task.order_index.notin_(list(SYSTEM_TASK_ORDERS)),
            )
            .order_by(Task.order_index.asc())
            .all()
        )
        total = len(tasks)
        generated = failed = skipped = 0

        def _emit(i: int, title: str) -> None:
            self.update_state(state="PROGRESS", meta={
                "current": i, "total": total,
                "message": f"Spec {i}/{total}: {title}",
                "generated": generated, "failed": failed, "skipped": skipped,
                "current_model": (f"{model_provider} / {model_id}"
                                  if model_provider and model_id else "Auto model chain"),
            })

        def _continue_later(done_index: int) -> dict[str, object]:
            """Persisted work is safe — hand the rest to a fresh task."""
            continued_id = _enqueue_spec_generate_all(
                project_id,
                model_provider=model_provider,
                model_id=model_id,
                chain_depth=chain_depth,
            )
            logger.info(
                "Generate-all specs continuing in new job %s (%s/%s done this batch)",
                continued_id, done_index, total,
            )
            return {
                "status": "completed",
                "continued_task_id": continued_id,
                "total": total,
                "generated": generated, "failed": failed, "skipped": skipped,
                "message": (
                    f"Spec {done_index}/{total} — auto-continuing remaining specs…"
                ),
            }

        for i, task in enumerate(tasks, 1):
            spec = (
                db.query(TaskSpec)
                .filter(TaskSpec.task_id == task.id, TaskSpec.deleted_at.is_(None))
                .first()
            )
            # Skip tasks that already have a finished spec (unless regenerating all).
            if only_missing and spec is not None \
                    and spec.status == TaskSpecStatus.ready and spec.content_json:
                skipped += 1
                _emit(i, task.title)
                continue

            # Batch time is up — persist-and-continue instead of dying on the
            # Celery hard limit (TimeLimitExceeded kills the process mid-spec).
            if time.monotonic() - started > _ALL_SPECS_BATCH_SEC:
                return _continue_later(i - 1)

            # Ensure a usable spec row (create or reset) — mirrors _queue_spec_generation.
            if spec is None:
                spec = TaskSpec(task_id=task.id, status=TaskSpecStatus.pending, content_json=None)
                db.add(spec)
            else:
                spec.deleted_at = None
                if spec.status != TaskSpecStatus.failed or not (spec.content_json or {}).get("_generation_progress"):
                    spec.content_json = None if spec.status != TaskSpecStatus.failed else spec.content_json
                spec.status = TaskSpecStatus.pending
                spec.generation_task_id = None
            db.commit()
            db.refresh(spec)

            _emit(i, task.title)
            try:
                result = generate_spec_task(str(spec.id), model_provider, model_id)  # in-process, serial
            except SoftTimeLimitExceeded:
                # Celery soft limit fired mid-spec — the finished specs are already
                # saved; continue the rest in a fresh job.
                return _continue_later(i - 1)
            if isinstance(result, dict) and result.get("error"):
                failed += 1
            else:
                generated += 1

        return {
            "status": "completed", "total": total,
            "generated": generated, "failed": failed, "skipped": skipped,
            "message": f"Done — {generated} generated, {skipped} skipped, {failed} failed.",
        }
    except SoftTimeLimitExceeded:
        logger.warning("Generate-all specs hit soft time limit — auto-continuing", extra={"project_id": project_id})
        continued_id = _enqueue_spec_generate_all(
            project_id,
            model_provider=model_provider,
            model_id=model_id,
            chain_depth=chain_depth,
        )
        return {
            "status": "completed",
            "continued_task_id": continued_id,
            "message": "Time limit reached — auto-continuing remaining specs…",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Generate-all specs failed", extra={"project_id": project_id})
        return {"error": str(exc)[:500], "status": "failed"}
    finally:
        db.close()


@celery_app.task(name="spec.generate")
def generate_spec_task(
    task_spec_id: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, str]:
    """Background task to generate a technical spec for a task."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    task_spec: TaskSpec | None = None
    try:
        task_spec = (
            db.query(TaskSpec).filter(TaskSpec.id == UUID(task_spec_id)).first()
        )
        if not task_spec:
            return {"error": "TaskSpec not found"}

        task = db.query(Task).filter(Task.id == task_spec.task_id).first()
        if not task:
            task_spec.status = TaskSpecStatus.failed
            db.commit()
            return {"error": "Task not found"}

        srs_content: dict = {}
        srs = None
        if task.srs_id:
            srs = db.query(SRS).filter(SRS.id == task.srs_id).first()
            if srs and srs.content_json:
                srs_content = srs.content_json

        prd_content: dict = {}
        if srs is not None:
            prd = db.query(PRD).filter(PRD.id == srs.prd_id).first()
            if prd and prd.content_json:
                from app.services.prd.source import resolve_prd_for_downstream

                prd_content, _ = resolve_prd_for_downstream(prd)

        arch = (
            db.query(Architecture)
            .filter(
                Architecture.project_id == task.project_id,
                Architecture.status == ArchitectureStatus.finalized,
                Architecture.deleted_at.is_(None),
            )
            .order_by(Architecture.created_at.desc())
            .first()
        )
        arch_content: dict | None = None
        if arch is not None:
            arch_content = {
                "doc_system_arch": arch.doc_system_arch or {},
                "doc_database": arch.doc_database or {},
                "doc_api": arch.doc_api or {},
                "doc_frontend": arch.doc_frontend or {},
                "doc_security": arch.doc_security or {},
                "doc_uiux": arch.doc_uiux or {},
            }

        project = db.query(Project).filter(Project.id == task.project_id).first()

        task_spec.status = TaskSpecStatus.generating
        db.commit()
        publish_job_progress(
            phase="starting",
            message="Starting spec generation…",
            current_model=(
                f"{model_provider} / {model_id}"
                if model_provider and model_id
                else "Auto model chain"
            ),
        )

        resume_partial, resume_completed = parse_spec_resume_state(task_spec.content_json)
        completed_phases: list[str] = list(resume_completed)

        def on_phase_complete(phase: str, partial: dict) -> None:
            if phase not in completed_phases:
                completed_phases.append(phase)
            task_spec.content_json = build_spec_progress_payload(
                partial,
                completed_phases,
                current_phase=phase,
            )
            db.commit()
            phase_labels = {
                "core": "Phase 1/2: structured spec fields",
                "summary": "Phase 2/2: implementation summary",
            }
            override = get_model_override()
            model_label = (
                f"{override[0]} / {override[1]}"
                if override
                else "Auto model chain"
            )
            publish_job_progress(
                phase=phase,
                message=phase_labels.get(phase, phase),
                current_model=model_label,
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            spec_data = loop.run_until_complete(
                generate_spec_ai(
                    task_title=task.title,
                    task_description=task.description or "",
                    module_name=task.module_name or "",
                    fr_references=task.fr_references or [],
                    linked_fr=task.linked_fr or "",
                    suggested_file=task.suggested_file,
                    suggested_endpoint=task.suggested_endpoint,
                    suggested_table=task.suggested_table,
                    srs_content=srs_content,
                    prd_content=prd_content,
                    arch_content=arch_content,
                    project_name=project.name if project else "Unknown",
                    resume_partial=resume_partial,
                    resume_completed_phases=completed_phases,
                    on_phase_complete=on_phase_complete,
                )
            )
        finally:
            loop.close()

        content = strip_spec_progress(spec_data.model_dump())
        commit_block = _git_commit_block_for(db, task)
        if commit_block:
            content["cursor_prompt"] = (content.get("cursor_prompt") or "") + commit_block
        task_spec.content_json = content
        task_spec.status = TaskSpecStatus.ready
        db.commit()

        return {"task_spec_id": task_spec_id, "status": TaskSpecStatus.ready.value}

    except Exception as exc:
        logger.exception(
            "Spec generation failed",
            extra={"task_spec_id": task_spec_id},
        )
        if task_spec is not None:
            task_spec.status = TaskSpecStatus.failed
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()
