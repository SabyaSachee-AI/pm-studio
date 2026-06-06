"""PM task management API (Kanban)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_screen_permission
from app.core.database import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    KanbanBoard,
    TaskCreate,
    TaskResponse,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.task.service import (
    create_task,
    delete_task,
    get_kanban_board,
    get_task_by_id,
    update_task,
    update_task_status,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _to_task_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        srs_id=task.srs_id,
        title=task.title,
        description=task.description,
        task_type=task.task_type.value,
        priority=task.priority.value,
        status=task.status.value,
        assigned_to_id=task.assigned_to_id,
        effort_hours=task.effort_hours,
        fr_references=task.fr_references,
        module_name=task.module_name,
        order_index=task.order_index,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/kanban/{project_id}", response_model=KanbanBoard)
async def get_kanban(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("projects", "view")),
) -> KanbanBoard:
    """Return tasks grouped by status for a Kanban board."""
    board = await get_kanban_board(db, project_id)
    return KanbanBoard(
        backlog=[_to_task_response(t) for t in board["backlog"]],
        assigned=[_to_task_response(t) for t in board["assigned"]],
        in_progress=[_to_task_response(t) for t in board["in_progress"]],
        in_review=[_to_task_response(t) for t in board["in_review"]],
        done=[_to_task_response(t) for t in board["done"]],
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task_endpoint(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("projects", "edit")),
) -> TaskResponse:
    """Create a new task."""
    task = await create_task(db, body)
    return _to_task_response(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_endpoint(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("projects", "view")),
) -> TaskResponse:
    """Return a task by id."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_task_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task_endpoint(
    task_id: UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("projects", "edit")),
) -> TaskResponse:
    """Partially update a task."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await update_task(db, task, body)
    return _to_task_response(updated)


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status_endpoint(
    task_id: UUID,
    body: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("projects", "edit")),
) -> TaskResponse:
    """Update task status and record the change in the audit log."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await update_task_status(
        db,
        task,
        body.status.value,
        current_user.id,
        body.note,
    )
    return _to_task_response(updated)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("projects", "edit")),
) -> None:
    """Soft-delete a task."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await delete_task(db, task)
