"""Technical task specification API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_screen_permission
from app.core.database import get_db
from app.models.task import Task
from app.models.task_spec import TaskSpec, TaskSpecStatus
from app.models.user import User
from app.schemas.spec import (
    SpecAssignRequest,
    SpecGenerateRequest,
    TaskSpecResponse,
)
from app.services.notification.service import create_notification
from app.workers.spec_tasks import generate_spec_task

router = APIRouter(prefix="/specs", tags=["Specs"])


def _to_spec_response(spec: TaskSpec) -> TaskSpecResponse:
    return TaskSpecResponse(
        id=spec.id,
        task_id=spec.task_id,
        status=spec.status.value,
        content_json=spec.content_json,
        assigned_to_id=spec.assigned_to_id,
        generation_task_id=spec.generation_task_id,
        created_at=spec.created_at,
        updated_at=spec.updated_at,
    )


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_spec(
    body: SpecGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Queue technical spec generation for a task."""
    task_result = await db.execute(
        select(Task).where(
            Task.id == body.task_id,
            Task.deleted_at.is_(None),
        )
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    existing = await db.execute(
        select(TaskSpec).where(
            TaskSpec.task_id == body.task_id,
            TaskSpec.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=400,
            detail="Spec already exists for this task",
        )

    task_spec = TaskSpec(
        task_id=body.task_id,
        status=TaskSpecStatus.pending,
        content_json=None,
    )
    db.add(task_spec)
    await db.commit()
    await db.refresh(task_spec)

    celery_task = generate_spec_task.delay(str(task_spec.id))
    task_spec.generation_task_id = celery_task.id
    await db.commit()

    return {
        "spec_id": str(task_spec.id),
        "task_id": str(body.task_id),
        "task_id_celery": celery_task.id,
    }


@router.get("/{spec_id}", response_model=TaskSpecResponse)
async def get_spec(
    spec_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "view")),
) -> TaskSpecResponse:
    """Return a task spec by id."""
    result = await db.execute(
        select(TaskSpec).where(
            TaskSpec.id == spec_id,
            TaskSpec.deleted_at.is_(None),
        )
    )
    spec = result.scalar_one_or_none()
    if spec is None:
        raise HTTPException(status_code=404, detail="Spec not found")
    return _to_spec_response(spec)


@router.get("/task/{task_id}", response_model=TaskSpecResponse)
async def get_spec_by_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "view")),
) -> TaskSpecResponse:
    """Return the task spec for a specific task."""
    result = await db.execute(
        select(TaskSpec).where(
            TaskSpec.task_id == task_id,
            TaskSpec.deleted_at.is_(None),
        )
    )
    spec = result.scalar_one_or_none()
    if spec is None:
        raise HTTPException(status_code=404, detail="Spec not found")
    return _to_spec_response(spec)


@router.patch("/{spec_id}/assign", response_model=TaskSpecResponse)
async def assign_spec(
    spec_id: UUID,
    body: SpecAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> TaskSpecResponse:
    """Assign a spec to a developer."""
    result = await db.execute(
        select(TaskSpec).where(
            TaskSpec.id == spec_id,
            TaskSpec.deleted_at.is_(None),
        )
    )
    spec = result.scalar_one_or_none()
    if spec is None:
        raise HTTPException(status_code=404, detail="Spec not found")

    spec.assigned_to_id = body.assigned_to_id
    await db.commit()
    await db.refresh(spec)

    await create_notification(
        db,
        user_id=body.assigned_to_id,
        title="Technical spec assigned",
        message=f"A technical specification has been assigned to you.",
        link=f"/tasks?spec={spec.id}",
    )
    return _to_spec_response(spec)
