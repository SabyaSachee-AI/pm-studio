"""SRS (Software Requirements Specification) database model."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class SRSStatus(enum.Enum):
    """Approval lifecycle status for an SRS document."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class SRS(TimeStampedModel):
    """Software Requirements Specification linked to a project and PRD."""

    __tablename__ = "srs_documents"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    prd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prds.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[SRSStatus] = mapped_column(
        Enum(
            SRSStatus,
            name="srs_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=SRSStatus.draft,
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
    prd: Mapped["PRD"] = relationship("PRD")
    generated_by: Mapped["User"] = relationship("User", foreign_keys=[generated_by_id])
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])

    def __repr__(self) -> str:
        return (
            f"<SRS id={self.id} project_id={self.project_id} "
            f"version={self.version} status={self.status}>"
        )
