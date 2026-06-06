"""Celery tasks for technical spec generation."""

import asyncio
import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.project import Project
from app.models.srs import SRS
from app.models.task import Task
from app.models.task_spec import TaskSpec, TaskSpecStatus
from app.services.spec.service import generate_spec_ai

logger = logging.getLogger(__name__)


@celery_app.task(name="spec.generate")
def generate_spec_task(task_spec_id: str) -> dict[str, str]:
    """Background task to generate a technical spec for a task."""
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
        if task.srs_id:
            srs = db.query(SRS).filter(SRS.id == task.srs_id).first()
            if srs and srs.content_json:
                srs_content = srs.content_json

        project = db.query(Project).filter(Project.id == task.project_id).first()

        task_spec.status = TaskSpecStatus.generating
        db.commit()

        spec_data = asyncio.run(
            generate_spec_ai(
                task_title=task.title,
                task_description=task.description or "",
                module_name=task.module_name or "",
                fr_references=task.fr_references or [],
                srs_content=srs_content,
                project_name=project.name if project else "Unknown",
            )
        )

        task_spec.content_json = spec_data.model_dump()
        task_spec.status = TaskSpecStatus.ready
        db.commit()

        return {"task_spec_id": task_spec_id, "status": TaskSpecStatus.ready.value}

    except Exception as exc:
        logger.error("Spec generation failed: %s", exc)
        if task_spec is not None:
            task_spec.status = TaskSpecStatus.failed
            db.commit()
        return {"error": str(exc)}
    finally:
        db.close()
