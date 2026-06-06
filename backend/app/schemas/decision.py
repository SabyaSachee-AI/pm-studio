"""Decision registry schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DecisionCreate(BaseModel):
    project_id: UUID
    title: str = Field(min_length=1, max_length=500)
    decision: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    alternatives: Optional[list[str]] = None


class DecisionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    decision: Optional[str] = None
    reason: Optional[str] = None
    alternatives: Optional[list[str]] = None


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str
    decision: str
    reason: str
    alternatives: Optional[list]
    decided_by_id: UUID
    decided_at: datetime
    created_at: datetime
    updated_at: datetime
