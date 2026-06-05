"""Project database model."""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class ProjectStatus(enum.Enum):
    """Lifecycle status for a project."""

    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    archived = "archived"


class Project(TimeStampedModel):
    """Project managed for a client in PM Studio."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(
            ProjectStatus,
            name="project_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=ProjectStatus.active,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id"),
        nullable=False,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    client: Mapped["Client"] = relationship("Client", back_populates="projects")
    created_by: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name} status={self.status}>"
