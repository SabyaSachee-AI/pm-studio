"""Celery tasks for module extraction and Kanban task seeding."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.architecture import Architecture, ArchitectureStatus
from app.services.prd.source import prd_eligible_for_downstream, resolve_prd_for_downstream
from app.models.prd import PRD
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.models.task import Task, TaskPriority, TaskStatus, TaskType
from app.models.task_spec import TaskSpec, TaskSpecStatus
from app.services.ai.modules import generate_modules_ai
from app.services.ai.job_progress import publish_job_progress
from app.services.task.coverage import covered_fr_ids as _covered_frs, extract_fr_ids
from app.services.task.system_prompts import (
    CODE_AUDIT_ORDER,
    DEPLOY_ORDER,
    LOCAL_UI_TEST_ORDER,
    PROJECT_BIBLE_ORDER,
    SYSTEM_TASK_ORDERS,
    build_code_audit_prompt,
    build_deploy_prompt,
    build_local_ui_test_prompt,
)

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
        "_capabilities": getattr(arch, "capabilities", None) or {},
    }


def _prd_eligible(prd: PRD) -> bool:
    return prd_eligible_for_downstream(prd)


def _ensure_system_tasks(
    db: Any,
    project_id: UUID,
    srs_id: UUID,
    project_name: str,
    prd_content: dict[str, Any],
    srs_content: dict[str, Any],
    arch_content: dict[str, Any] | None,
    task_titles: list[str],
) -> list[str]:
    """Create the pinned system tasks if missing. Returns created task ids."""
    existing_orders = {
        t.order_index
        for t in db.query(Task)
        .filter(
            Task.project_id == project_id,
            Task.order_index.in_(list(SYSTEM_TASK_ORDERS)),
            Task.deleted_at.is_(None),
        )
        .all()
    }

    definitions: list[dict[str, Any]] = [
        {
            "order_index": PROJECT_BIBLE_ORDER,
            "title": "Project bible",
            "priority": TaskPriority.critical,
            "module_name": "⚙ SETUP — complete before all other tasks",
            "cursor_prompt": None,
        },
        {
            "order_index": CODE_AUDIT_ORDER,
            "title": "Code audit — coverage check, gap detection and test writing",
            "priority": TaskPriority.critical,
            "module_name": "✅ FINAL STEP 1 — run after all features are coded",
            "cursor_prompt": build_code_audit_prompt(
                project_name, srs_content, arch_content, task_titles
            ),
        },
        {
            "order_index": LOCAL_UI_TEST_ORDER,
            "title": "Local UI test — run the application and verify every feature",
            "priority": TaskPriority.critical,
            "module_name": "✅ FINAL STEP 2 — run after code audit passes",
            "cursor_prompt": build_local_ui_test_prompt(
                project_name, prd_content, srs_content, arch_content
            ),
        },
        {
            "order_index": DEPLOY_ORDER,
            "title": "Git push and deploy — GitHub, CI/CD pipeline and VPS",
            "priority": TaskPriority.high,
            "module_name": "🚀 DEPLOY — after local test passes",
            "cursor_prompt": build_deploy_prompt(project_name),
        },
    ]

    created_ids: list[str] = []
    for definition in definitions:
        if definition["order_index"] in existing_orders:
            continue
        task = Task(
            project_id=project_id,
            srs_id=srs_id,
            title=definition["title"],
            task_type=TaskType.devops,
            priority=definition["priority"],
            status=TaskStatus.backlog,
            module_name=definition["module_name"],
            order_index=definition["order_index"],
        )
        db.add(task)
        db.flush()
        if definition["cursor_prompt"] is not None:
            db.add(
                TaskSpec(
                    task_id=task.id,
                    content_json={"cursor_prompt": definition["cursor_prompt"]},
                    status=TaskSpecStatus.ready,
                )
            )
        created_ids.append(str(task.id))
    db.commit()
    return created_ids


@celery_app.task(name="modules.extract")
def extract_modules_task(
    project_id: str,
    srs_id: str,
    architecture_id: str | None = None,
    replace_existing: bool = False,
    fill_gaps_only: bool = False,
) -> dict:
    """Extract modules from PRD + SRS + Architecture and create Kanban tasks.

    replace_existing=True  → soft-delete all current tasks (+ their specs) then regenerate
    fill_gaps_only=True    → only generate tasks for FRs that have no coverage yet
    """
    db = SyncSessionLocal()
    try:
        publish_job_progress(
            phase="starting",
            message="Extracting modules from PRD + SRS + architecture…",
            current_model="Auto model chain",
        )
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

        all_frs: list[str] = extract_fr_ids(srs.content_json)

        prd = db.query(PRD).filter(PRD.id == srs.prd_id).first() if srs.prd_id else None
        if not srs.prd_id or prd is None or not _prd_eligible(prd):
            return {"error": "An approved or finalized PRD linked to the SRS is required"}
        prd_content, prd_source = resolve_prd_for_downstream(prd)
        if not prd_content:
            return {"error": "An approved or finalized PRD linked to the SRS is required"}
        logger.info(
            "Module extract PRD source: %s v%s",
            prd_source.get("type"),
            prd_source.get("version"),
        )

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

        # Determine starting order index (system tasks excluded so their
        # pinned order_index values never shift regular task ordering)
        regular_existing = [
            t for t in existing_tasks if t.order_index not in SYSTEM_TASK_ORDERS
        ]
        max_order = max((t.order_index for t in regular_existing), default=-1) + 1

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

        # Pin the system tasks (project bible, code audit, local UI test, deploy)
        regular_titles = [
            t.title for t in all_tasks_after if t.order_index not in SYSTEM_TASK_ORDERS
        ]
        system_task_ids = _ensure_system_tasks(
            db,
            UUID(project_id),
            UUID(srs_id),
            project_name,
            prd_content,
            srs.content_json or {},
            arch_content,
            regular_titles,
        )
        covered_after = _covered_frs(all_tasks_after)
        missing_frs = [f for f in all_frs if f not in covered_after]

        response: dict = {
            "project_id": project_id,
            "srs_id": srs_id,
            "modules_count": len(result.modules),
            "tasks_created": len(created_ids),
            "task_ids": created_ids,
            "system_tasks_created": len(system_task_ids),
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
