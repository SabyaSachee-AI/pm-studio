"""Knowledge base saved documents and artifacts."""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimeStampedModel


class KnowledgeItemType(str, enum.Enum):
    document = "document"
    module = "module"
    spec = "spec"


class KnowledgeSourceType(str, enum.Enum):
    prd = "prd"
    srs = "srs"
    spec = "spec"
    manual = "manual"


class KnowledgeBaseItem(TimeStampedModel):
    """Reusable saved artifact from a completed project phase."""

    __tablename__ = "knowledge_base_items"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True
    )
    item_type: Mapped[KnowledgeItemType] = mapped_column(
        Enum(KnowledgeItemType, name="knowledge_item_type"), nullable=False
    )
    source_type: Mapped[KnowledgeSourceType] = mapped_column(
        Enum(KnowledgeSourceType, name="knowledge_source_type"), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    saved_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
