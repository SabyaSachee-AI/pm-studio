"""Task status change audit log."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class TaskStatusLog(TimeStampedModel):
    """Records each task status transition for audit and history."""

    __tablename__ = "task_status_logs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["Task"] = relationship("Task")
    changed_by: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<TaskStatusLog task_id={self.task_id} "
            f"{self.from_status} → {self.to_status}>"
        )
