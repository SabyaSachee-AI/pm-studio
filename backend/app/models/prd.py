"""PRD (Product Requirements Document) database model."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class PRDStatus(enum.Enum):
    """Approval lifecycle status for a PRD."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class PRD(TimeStampedModel):
    """Product Requirements Document linked to a project."""

    __tablename__ = "prds"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requirements.id"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[PRDStatus] = mapped_column(
        Enum(
            PRDStatus,
            name="prd_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=PRDStatus.draft,
    )
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    generated_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generation_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped["Project"] = relationship("Project")
    requirement: Mapped["Requirement | None"] = relationship("Requirement")
    generated_by: Mapped["User"] = relationship("User", foreign_keys=[generated_by_id])
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])

    def __repr__(self) -> str:
        return (
            f"<PRD id={self.id} project_id={self.project_id} "
            f"version={self.version} status={self.status}>"
        )
