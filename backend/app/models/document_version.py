"""Document version history."""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimeStampedModel


class DocumentType(str, enum.Enum):
    """Supported versioned document types."""

    prd = "prd"
    srs = "srs"


class DocumentVersion(TimeStampedModel):
    """Immutable snapshot of a PRD or SRS at a point in time."""

    __tablename__ = "document_versions"

    document_type: Mapped[DocumentType] = mapped_column(
        Enum(
            DocumentType,
            name="document_type",
            values_callable=lambda types: [t.value for t in types],
        ),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    change_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DocumentVersion type={self.document_type} "
            f"doc={self.document_id} v={self.version}>"
        )
