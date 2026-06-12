"""Technical task specification API endpoints."""

from datetime import datetime, timezone
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
    SpecRegenerateRequest,
    SpecUpdateRequest,
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


async def _get_task_spec_row(db: AsyncSession, task_id: UUID) -> TaskSpec | None:
    result = await db.execute(select(TaskSpec).where(TaskSpec.task_id == task_id))
    return result.scalar_one_or_none()


async def _queue_spec_generation(
    db: AsyncSession,
    task_id: UUID,
    *,
    replace: bool,
    model_provider: str | None,
    model_id: str | None,
) -> dict[str, str]:
    """Reuse the single task_specs row for a task (unique on task_id)."""
    spec = await _get_task_spec_row(db, task_id)

    if spec is not None and spec.deleted_at is None and not replace:
        if spec.status == TaskSpecStatus.ready:
            raise HTTPException(
                status_code=400,
                detail="Spec already exists for this task. Use regenerate to replace it.",
            )
        if spec.status == TaskSpecStatus.failed:
            has_partial = bool(
                (spec.content_json or {}).get("_generation_progress")
            )
            if not has_partial:
                spec.content_json = None
            spec.status = TaskSpecStatus.pending
            spec.generation_task_id = None
        elif spec.status in (TaskSpecStatus.pending, TaskSpecStatus.generating):
            spec.status = TaskSpecStatus.pending
        await db.commit()
        await db.refresh(spec)
    elif spec is not None:
        spec.deleted_at = None
        spec.status = TaskSpecStatus.pending
        spec.content_json = None
        spec.generation_task_id = None
        await db.commit()
        await db.refresh(spec)
    else:
        spec = TaskSpec(
            task_id=task_id,
            status=TaskSpecStatus.pending,
            content_json=None,
        )
        db.add(spec)
        await db.commit()
        await db.refresh(spec)

    celery_task = generate_spec_task.delay(
        str(spec.id),
        model_provider=model_provider,
        model_id=model_id,
    )
    spec.generation_task_id = celery_task.id
    await db.commit()

    return {
        "spec_id": str(spec.id),
        "task_id": str(task_id),
        "task_id_celery": celery_task.id,
    }


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_spec(
    body: SpecGenerateRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
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

    return await _queue_spec_generation(
        db,
        body.task_id,
        replace=False,
        model_provider=model_provider,
        model_id=model_id,
    )


@router.post("/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_spec_by_task(
    body: SpecRegenerateRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Soft-delete existing spec and queue a fresh generation for a task."""
    task_result = await db.execute(
        select(Task).where(
            Task.id == body.task_id,
            Task.deleted_at.is_(None),
        )
    )
    if task_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    payload = await _queue_spec_generation(
        db,
        body.task_id,
        replace=True,
        model_provider=model_provider,
        model_id=model_id,
    )
    payload["status"] = "regenerating"
    return payload


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


@router.patch("/{spec_id}", response_model=TaskSpecResponse)
async def update_spec(
    spec_id: UUID,
    body: SpecUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> TaskSpecResponse:
    """Update spec content (manual edits to the generated spec)."""
    result = await db.execute(
        select(TaskSpec).where(
            TaskSpec.id == spec_id,
            TaskSpec.deleted_at.is_(None),
        )
    )
    spec = result.scalar_one_or_none()
    if spec is None:
        raise HTTPException(status_code=404, detail="Spec not found")

    spec.content_json = body.content_json
    await db.commit()
    await db.refresh(spec)
    return _to_spec_response(spec)


@router.delete("/{spec_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spec(
    spec_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> None:
    """Soft-delete a spec so a fresh one can be generated."""
    result = await db.execute(
        select(TaskSpec).where(
            TaskSpec.id == spec_id,
            TaskSpec.deleted_at.is_(None),
        )
    )
    spec = result.scalar_one_or_none()
    if spec is None:
        raise HTTPException(status_code=404, detail="Spec not found")

    spec.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/{spec_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_spec(
    spec_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Re-queue technical spec generation."""
    result = await db.execute(
        select(TaskSpec).where(
            TaskSpec.id == spec_id,
            TaskSpec.deleted_at.is_(None),
        )
    )
    spec = result.scalar_one_or_none()
    if spec is None:
        raise HTTPException(status_code=404, detail="Spec not found")

    spec.content_json = None
    spec.status = TaskSpecStatus.pending
    await db.commit()

    celery_task = generate_spec_task.delay(
        str(spec.id),
        model_provider=model_provider,
        model_id=model_id,
    )
    spec.generation_task_id = celery_task.id
    await db.commit()

    return {
        "spec_id": str(spec.id),
        "task_id": str(spec.task_id),
        "task_id_celery": celery_task.id,
        "status": "regenerating",
    }
