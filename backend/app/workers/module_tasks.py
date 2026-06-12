"""Celery tasks for module extraction and Kanban task seeding."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.prd import PRD
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.models.task import Task, TaskPriority, TaskStatus, TaskType
from app.models.task_spec import TaskSpec
from app.services.ai.modules import generate_modules_ai

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {
    "critical": TaskPriority.critical,
    "high": TaskPriority.high,
    "medium": TaskPriority.medium,
    "low": TaskPriority.low,
}


def _build_arch_content(arch: Architecture) -> dict[str, Any]:
    return {
        "doc_system_arch": arch.doc_system_arch or {},
        "doc_database": arch.doc_database or {},
        "doc_api": arch.doc_api or {},
        "doc_frontend": arch.doc_frontend or {},
        "doc_security": arch.doc_security or {},
        "doc_uiux": arch.doc_uiux or {},
    }


def _covered_frs(tasks: list[Task]) -> set[str]:
    """Return the set of FR numbers that have at least one task."""
    covered: set[str] = set()
    for t in tasks:
        if t.linked_fr:
            covered.add(t.linked_fr)
        for fr in (t.fr_references or []):
            covered.add(fr)
    return covered


@celery_app.task(name="modules.extract")
def extract_modules_task(
    project_id: str,
    srs_id: str,
    architecture_id: str | None = None,
    replace_existing: bool = False,
    fill_gaps_only: bool = False,
) -> dict:
    """Extract modules from SRS + Architecture and create Kanban tasks.

    replace_existing=True  → soft-delete all current tasks (+ their specs) then regenerate
    fill_gaps_only=True    → only generate tasks for FRs that have no coverage yet
    """
    db = SyncSessionLocal()
    try:
        srs = db.query(SRS).filter(SRS.id == UUID(srs_id)).first()
        if not srs or not srs.content_json:
            return {"error": "SRS not found or has no content"}

        meta = (srs.content_json or {}).get("_meta") or {}
        srs_eligible = (
            srs.status == SRSStatus.approved
            or meta.get("workflow_finalized")
            or meta.get("workflow_confirmed")
            or srs.status == SRSStatus.submitted
        )
        if not srs_eligible:
            return {"error": "SRS must be approved or finalized before task generation"}

        all_frs: list[str] = [
            fr.get("fr_number", "")
            for fr in (srs.content_json or {}).get("functional_requirements", [])
            if fr.get("fr_number")
        ]

        prd = db.query(PRD).filter(PRD.id == srs.prd_id).first()
        prd_content = prd.content_json if prd and prd.content_json else {}

        project = db.query(Project).filter(Project.id == UUID(project_id)).first()
        project_name = project.name if project else "Unknown"

        # Load architecture
        arch: Architecture | None = None
        if architecture_id:
            arch = db.query(Architecture).filter(
                Architecture.id == UUID(architecture_id),
                Architecture.deleted_at.is_(None),
            ).first()
        if arch is None:
            arch = (
                db.query(Architecture)
                .filter(
                    Architecture.project_id == UUID(project_id),
                    Architecture.status == ArchitectureStatus.finalized,
                    Architecture.deleted_at.is_(None),
                )
                .first()
            )

        arch_content = _build_arch_content(arch) if arch else None
        arch_used = str(arch.id) if arch else None

        # Fetch existing tasks
        existing_tasks: list[Task] = (
            db.query(Task)
            .filter(Task.project_id == UUID(project_id), Task.deleted_at.is_(None))
            .all()
        )

        if replace_existing and existing_tasks:
            # Soft-delete existing tasks and their specs
            task_ids = [t.id for t in existing_tasks]
            specs = (
                db.query(TaskSpec)
                .filter(TaskSpec.task_id.in_(task_ids), TaskSpec.deleted_at.is_(None))
                .all()
            )
            now = datetime.now(timezone.utc)
            for spec in specs:
                spec.deleted_at = now
            for task in existing_tasks:
                task.deleted_at = now
            db.commit()
            existing_tasks = []

        # For fill_gaps: determine which FRs already have coverage
        already_covered: set[str] = _covered_frs(existing_tasks)
        uncovered_frs: list[str] = [f for f in all_frs if f not in already_covered]

        if fill_gaps_only and not uncovered_frs:
            return {
                "project_id": project_id,
                "srs_id": srs_id,
                "tasks_created": 0,
                "message": "All FRs already have task coverage — nothing to fill.",
                "fr_coverage": {"total": len(all_frs), "covered": len(all_frs), "missing": []},
            }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                generate_modules_ai(
                    project_name=project_name,
                    prd_content=prd_content,
                    srs_content=srs.content_json,
                    arch_content=arch_content,
                    target_frs=uncovered_frs if fill_gaps_only else None,
                )
            )
        finally:
            loop.close()

        # Determine starting order index
        max_order = max((t.order_index for t in existing_tasks), default=-1) + 1

        created_ids: list[str] = []
        order = max_order
        for module in result.modules:
            for item in module.tasks:
                priority = _PRIORITY_MAP.get(item.priority.lower(), TaskPriority.medium)
                task = Task(
                    project_id=UUID(project_id),
                    srs_id=UUID(srs_id),
                    title=item.title,
                    description=item.description or None,
                    task_type=TaskType.feature,
                    priority=priority,
                    status=TaskStatus.backlog,
                    effort_hours=item.effort_hours,
                    fr_references=item.fr_references or None,
                    linked_fr=item.linked_fr or None,
                    module_name=module.name,
                    order_index=order,
                    suggested_file=item.suggested_file or None,
                    suggested_endpoint=item.suggested_endpoint or None,
                    suggested_table=item.suggested_table or None,
                )
                order += 1
                db.add(task)
                db.flush()
                created_ids.append(str(task.id))

        db.commit()

        # Recompute coverage after creation
        all_tasks_after: list[Task] = (
            db.query(Task)
            .filter(Task.project_id == UUID(project_id), Task.deleted_at.is_(None))
            .all()
        )
        covered_after = _covered_frs(all_tasks_after)
        missing_frs = [f for f in all_frs if f not in covered_after]

        response: dict = {
            "project_id": project_id,
            "srs_id": srs_id,
            "modules_count": len(result.modules),
            "tasks_created": len(created_ids),
            "task_ids": created_ids,
            "fr_coverage": {
                "total": len(all_frs),
                "covered": len(covered_after),
                "missing": missing_frs,
            },
        }
        if arch_used:
            response["architecture_id"] = arch_used
        else:
            response["warning"] = "No finalized architecture — tasks extracted from SRS only"
        return response

    except Exception as exc:
        logger.exception(
            "Module extraction failed",
            extra={"project_id": project_id, "srs_id": srs_id},
        )
        return {"error": str(exc)[:500]}
    finally:
        db.close()
