"""Knowledge base API schemas."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeItemCreate(BaseModel):
    project_id: Optional[UUID] = None
    item_type: str = Field(pattern="^(document|module|spec)$")
    source_type: str = Field(pattern="^(prd|srs|spec|manual)$")
    source_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    content_json: dict[str, Any]
    tags: Optional[list[str]] = None


class KnowledgeItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: Optional[UUID]
    item_type: str
    source_type: str
    source_id: Optional[UUID]
    title: str
    description: Optional[str]
    content_json: Optional[dict]
    tags: Optional[list]
    saved_by_id: UUID
    created_at: datetime
    updated_at: datetime


class ReusableModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    content_json: dict[str, Any]
    knowledge_base_item_id: Optional[UUID] = None


class ReusableModuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_item_id: Optional[UUID]
    name: str
    description: Optional[str]
    content_json: Optional[dict]
    saved_by_id: UUID
    created_at: datetime
    updated_at: datetime


class SaveFromSourceRequest(BaseModel):
    """Save an existing PRD/SRS/spec into the knowledge base."""

    source_type: str = Field(pattern="^(prd|srs|spec)$")
    source_id: UUID
    title: Optional[str] = None
    tags: Optional[list[str]] = None
