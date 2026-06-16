"""Architecture suite database model (6 JSONB documents + per-doc status)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel

DOC_FIELDS = (
    "doc_system_arch",
    "doc_database",
    "doc_api",
    "doc_frontend",
    "doc_security",
    "doc_uiux",
)

DOC_STATUS_FIELDS = tuple(f"{field}_status" for field in DOC_FIELDS)


class DocGenerationStatus(enum.Enum):
    """Per-document generation lifecycle."""

    pending = "pending"
    generating = "generating"
    completed = "completed"
    failed = "failed"
    generated = "generated"
    saved = "saved"


class ArchitectureStatus(enum.Enum):
    """Lifecycle status for an architecture suite."""

    draft = "draft"
    confirmed = "confirmed"
    finalized = "finalized"


class Architecture(TimeStampedModel):
    """Six-document technical architecture suite linked to a project and SRS."""

    __tablename__ = "architectures"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    srs_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("srs_documents.id"),
        nullable=False,
    )
    status: Mapped[ArchitectureStatus] = mapped_column(
        Enum(
            ArchitectureStatus,
            name="architecture_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=ArchitectureStatus.draft,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generation_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doc_task_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=lambda: {}
    )
    generation_progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    doc_cancel_flags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=lambda: {}
    )
    can_resume: Mapped[bool] = mapped_column(nullable=False, default=False)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    resume_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suite_canon: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    consistency_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    doc_system_arch: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    doc_database: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    doc_api: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    doc_frontend: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    doc_security: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    doc_uiux: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    doc_system_arch_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocGenerationStatus.pending.value, server_default="pending"
    )
    doc_database_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocGenerationStatus.pending.value, server_default="pending"
    )
    doc_api_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocGenerationStatus.pending.value, server_default="pending"
    )
    doc_frontend_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocGenerationStatus.pending.value, server_default="pending"
    )
    doc_security_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocGenerationStatus.pending.value, server_default="pending"
    )
    doc_uiux_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocGenerationStatus.pending.value, server_default="pending"
    )

    project: Mapped["Project"] = relationship("Project")
    srs: Mapped["SRS"] = relationship("SRS")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    confirmed_by: Mapped["User | None"] = relationship("User", foreign_keys=[confirmed_by_id])

    def __repr__(self) -> str:
        return (
            f"<Architecture id={self.id} project_id={self.project_id} "
            f"version={self.version} status={self.status}>"
        )
