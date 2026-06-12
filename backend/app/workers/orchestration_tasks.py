"""Celery task for project orchestration spec generation."""

import asyncio
import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.knowledge_base_item import KnowledgeBaseItem, KnowledgeItemType, KnowledgeSourceType
from app.models.project import Project
from app.models.task import Task
from app.models.task_spec import TaskSpec, TaskSpecStatus
from app.services.ai.orchestration_service import generate_orchestration_ai

logger = logging.getLogger(__name__)


@celery_app.task(name="orchestration.generate")
def generate_orchestration_task(project_id: str, requested_by_id: str) -> dict:
    """Synthesise all task specs + architecture into a master orchestration document."""
    db = SyncSessionLocal()
    try:
        project = db.query(Project).filter(Project.id == UUID(project_id)).first()
        if not project:
            return {"error": "Project not found"}

        # Load finalized or confirmed architecture
        arch = (
            db.query(Architecture)
            .filter(
                Architecture.project_id == UUID(project_id),
                Architecture.status == ArchitectureStatus.finalized,
                Architecture.deleted_at.is_(None),
            )
            .order_by(Architecture.created_at.desc())
            .first()
        )
        if arch is None:
            arch = (
                db.query(Architecture)
                .filter(
                    Architecture.project_id == UUID(project_id),
                    Architecture.deleted_at.is_(None),
                )
                .order_by(Architecture.created_at.desc())
                .first()
            )

        arch_summary: dict = {}
        if arch:
            arch_summary = {
                "doc_system_arch": arch.doc_system_arch or {},
                "doc_database": arch.doc_database or {},
                "doc_api": arch.doc_api or {},
                "doc_frontend": arch.doc_frontend or {},
                "doc_security": arch.doc_security or {},
            }

        # Load all tasks with ready specs
        tasks = (
            db.query(Task)
            .filter(Task.project_id == UUID(project_id), Task.deleted_at.is_(None))
            .order_by(Task.order_index.asc())
            .all()
        )

        task_ids = [t.id for t in tasks]
        specs = (
            db.query(TaskSpec)
            .filter(
                TaskSpec.task_id.in_(task_ids),
                TaskSpec.status == TaskSpecStatus.ready,
                TaskSpec.deleted_at.is_(None),
            )
            .all()
        )
        spec_by_task = {s.task_id: s for s in specs}

        task_specs_payload = []
        for task in tasks:
            spec = spec_by_task.get(task.id)
            task_specs_payload.append(
                {
                    "task": {
                        "order_index": task.order_index,
                        "title": task.title,
                        "module_name": task.module_name or "",
                        "priority": task.priority.value if hasattr(task.priority, "value") else str(task.priority),
                        "suggested_file": task.suggested_file or "",
                        "fr_references": task.fr_references or [],
                    },
                    "spec": spec.content_json if spec and spec.content_json else {},
                }
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                generate_orchestration_ai(
                    project_name=project.name,
                    architecture_summary=arch_summary,
                    task_specs=task_specs_payload,
                )
            )
        finally:
            loop.close()

        content = result.model_dump()

        # Store as a knowledge base item (reuses existing infrastructure, no new migration)
        existing = (
            db.query(KnowledgeBaseItem)
            .filter(
                KnowledgeBaseItem.project_id == UUID(project_id),
                KnowledgeBaseItem.item_type == KnowledgeItemType.spec,
                KnowledgeBaseItem.title == f"{project.name} — Project Orchestration",
                KnowledgeBaseItem.deleted_at.is_(None),
            )
            .first()
        )

        if existing:
            existing.content_json = content
            existing.description = f"Master orchestration spec with {len(tasks)} tasks and {len(specs)} detailed specs."
            db.commit()
            db.refresh(existing)
            item_id = str(existing.id)
        else:
            item = KnowledgeBaseItem(
                project_id=UUID(project_id),
                item_type=KnowledgeItemType.spec,
                source_type=KnowledgeSourceType.manual,
                title=f"{project.name} — Project Orchestration",
                description=f"Master orchestration spec with {len(tasks)} tasks and {len(specs)} detailed specs.",
                content_json=content,
                tags=["orchestration", "master-spec", "cursor-prompt"],
                saved_by_id=UUID(requested_by_id),
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            item_id = str(item.id)

        return {
            "project_id": project_id,
            "knowledge_item_id": item_id,
            "tasks_included": len(tasks),
            "specs_included": len(specs),
            "status": "completed",
        }

    except Exception as exc:
        logger.exception("Orchestration generation failed", extra={"project_id": project_id})
        return {"error": str(exc)[:500]}
    finally:
        db.close()
