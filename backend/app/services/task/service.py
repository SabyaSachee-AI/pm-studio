"""Task (Kanban) business logic."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskPriority, TaskStatus, TaskType
from app.models.task_status_log import TaskStatusLog
from app.schemas.task import TaskCreate, TaskUpdate


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def get_kanban_board(
    db: AsyncSession,
    project_id: UUID,
) -> dict[str, list[Task]]:
    """Return tasks grouped by status for Kanban board."""
    result = await db.execute(
        select(Task)
        .where(Task.project_id == project_id, Task.deleted_at.is_(None))
        .order_by(Task.order_index.asc())
    )
    tasks = result.scalars().all()

    board: dict[str, list[Task]] = {
        "backlog": [],
        "assigned": [],
        "in_progress": [],
        "in_review": [],
        "done": [],
    }
    for task in tasks:
        status_key = _enum_value(task.status)
        if status_key in board:
            board[status_key].append(task)
    return board


async def get_task_by_id(db: AsyncSession, task_id: UUID) -> Task | None:
    """Return a non-deleted task by id."""
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def create_task(db: AsyncSession, data: TaskCreate) -> Task:
    """Create and persist a new task."""
    payload = data.model_dump()
    task = Task(**payload)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task_status(
    db: AsyncSession,
    task: Task,
    new_status: str,
    changed_by_id: UUID,
    note: Optional[str] = None,
) -> Task:
    """Update task status and log the change."""
    old_status = _enum_value(task.status)

    log = TaskStatusLog(
        task_id=task.id,
        from_status=old_status,
        to_status=new_status,
        changed_by_id=changed_by_id,
        note=note,
    )
    db.add(log)
    task.status = TaskStatus(new_status)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(
    db: AsyncSession,
    task: Task,
    data: TaskUpdate,
) -> Task:
    """Apply partial updates to a task."""
    updates = data.model_dump(exclude_unset=True)
    enum_fields = {
        "status": TaskStatus,
        "task_type": TaskType,
        "priority": TaskPriority,
    }
    for key, value in updates.items():
        if key in enum_fields and value is not None:
            enum_val = value.value if hasattr(value, "value") else value
            setattr(task, key, enum_fields[key](enum_val))
        else:
            setattr(task, key, value)
    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task: Task) -> None:
    """Soft-delete a task."""
    task.deleted_at = datetime.now(timezone.utc)
    await db.commit()
