"""Task (Kanban work item) database model."""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class TaskStatus(str, enum.Enum):
    """Kanban column / lifecycle status for a task."""

    backlog = "backlog"
    assigned = "assigned"
    in_progress = "in_progress"
    in_review = "in_review"
    done = "done"


class TaskType(str, enum.Enum):
    """Category of work represented by a task."""

    feature = "feature"
    bug = "bug"
    improvement = "improvement"
    research = "research"
    devops = "devops"


class TaskPriority(str, enum.Enum):
    """Priority level for scheduling and triage."""

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class Task(TimeStampedModel):
    """Project task derived from SRS functional requirements."""

    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    srs_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("srs_documents.id"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(
            TaskType,
            name="task_type",
            values_callable=lambda types: [t.value for t in types],
        ),
        nullable=False,
        default=TaskType.feature,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            name="task_priority",
            values_callable=lambda priorities: [p.value for p in priorities],
        ),
        nullable=False,
        default=TaskPriority.medium,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            values_callable=lambda statuses: [s.value for s in statuses],
        ),
        nullable=False,
        default=TaskStatus.backlog,
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    effort_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    fr_references: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    module_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped["Project"] = relationship("Project")
    assigned_to: Mapped["User | None"] = relationship("User")
    spec: Mapped["TaskSpec | None"] = relationship(
        "TaskSpec",
        back_populates="task",
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Task id={self.id} title={self.title[:30]} status={self.status}>"
        )
