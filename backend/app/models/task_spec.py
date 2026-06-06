"""AI-generated task specification attached to a task."""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class TaskSpecStatus(str, enum.Enum):
    """Generation lifecycle for a task spec."""

    pending = "pending"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class TaskSpec(TimeStampedModel):
    """Structured task specification generated from SRS context."""

    __tablename__ = "task_specs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id"),
        nullable=False,
        unique=True,
    )
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[TaskSpecStatus] = mapped_column(
        Enum(
            TaskSpecStatus,
            name="task_spec_status",
            values_callable=lambda statuses: [s.value for s in statuses],
        ),
        nullable=False,
        default=TaskSpecStatus.pending,
    )
    generation_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    task: Mapped["Task"] = relationship("Task", back_populates="spec")

    def __repr__(self) -> str:
        return f"<TaskSpec task_id={self.task_id} status={self.status}>"
