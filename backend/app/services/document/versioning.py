"""Document version history helpers."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_version import DocumentType, DocumentVersion


async def save_document_version(
    db: AsyncSession,
    *,
    document_type: DocumentType,
    document_id: uuid.UUID,
    version: int,
    content_json: dict[str, Any],
    created_by_id: uuid.UUID,
    change_note: str | None = None,
) -> DocumentVersion:
    """Persist an immutable document version snapshot."""
    record = DocumentVersion(
        document_type=document_type,
        document_id=document_id,
        version=version,
        content_json=content_json,
        created_by_id=created_by_id,
        change_note=change_note,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record
