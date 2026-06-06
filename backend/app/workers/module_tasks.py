"""Celery tasks for module extraction and Kanban task seeding."""

import asyncio
import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.prd import PRD
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.models.task import Task, TaskPriority, TaskStatus, TaskType
from app.services.ai.modules import generate_modules_ai

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {
    "critical": TaskPriority.critical,
    "high": TaskPriority.high,
    "medium": TaskPriority.medium,
    "low": TaskPriority.low,
}


@celery_app.task(name="modules.extract")
def extract_modules_task(project_id: str, srs_id: str) -> dict:
    """Extract modules from PRD+SRS and create Kanban tasks."""
    db = SyncSessionLocal()
    try:
        srs = db.query(SRS).filter(SRS.id == UUID(srs_id)).first()
        if not srs or not srs.content_json:
            return {"error": "SRS not found or has no content"}
        if srs.status != SRSStatus.approved:
            return {"error": "SRS must be approved before module extraction"}

        prd = db.query(PRD).filter(PRD.id == srs.prd_id).first()
        prd_content = prd.content_json if prd and prd.content_json else {}

        project = db.query(Project).filter(Project.id == UUID(project_id)).first()
        project_name = project.name if project else "Unknown"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                generate_modules_ai(
                    project_name=project_name,
                    prd_content=prd_content,
                    srs_content=srs.content_json,
                )
            )
        finally:
            loop.close()

        created_ids: list[str] = []
        order = 0
        for module in result.modules:
            for item in module.tasks:
                priority = _PRIORITY_MAP.get(
                    item.priority.lower(), TaskPriority.medium
                )
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
                    module_name=module.name,
                    order_index=order,
                )
                order += 1
                db.add(task)
                db.flush()
                created_ids.append(str(task.id))

        db.commit()
        return {
            "project_id": project_id,
            "srs_id": srs_id,
            "modules_count": len(result.modules),
            "tasks_created": len(created_ids),
            "task_ids": created_ids,
        }
    except Exception as exc:
        logger.exception(
            "Module extraction failed",
            extra={"project_id": project_id, "srs_id": srs_id},
        )
        return {"error": str(exc)[:500]}
    finally:
        db.close()
