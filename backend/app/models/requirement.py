"""Requirement document database model."""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class RequirementStatus(enum.Enum):
    """Processing lifecycle status for a requirement document."""

    uploaded = "uploaded"
    extracting = "extracting"
    analyzing = "analyzing"
    analyzed = "analyzed"
    failed = "failed"


class Requirement(TimeStampedModel):
    """Uploaded requirement document linked to a project."""

    __tablename__ = "requirements"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RequirementStatus] = mapped_column(
        Enum(
            RequirementStatus,
            name="requirement_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=RequirementStatus.uploaded,
    )
    analysis_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="requirements")
    uploaded_by: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<Requirement id={self.id} filename={self.original_filename} "
            f"status={self.status}>"
        )
