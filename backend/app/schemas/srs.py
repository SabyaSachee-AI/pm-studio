from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FunctionalRequirement(BaseModel):
    fr_number: str  # FR-001, FR-002...
    title: str
    description: str
    priority: str  # must, should, nice
    test_criteria: list[str]


class NonFunctionalRequirement(BaseModel):
    category: str  # Performance, Security, Usability, etc.
    description: str
    metric: str
    threshold: str  # e.g. "< 300ms P95"


class SRSSchema(BaseModel):
    introduction: str
    scope: str
    definitions: list[str]
    functional_requirements: list[FunctionalRequirement]
    nonfunctional_requirements: list[NonFunctionalRequirement]
    assumptions: list[str]
    constraints: list[str]
    references: list[str]


class SRSResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    prd_id: UUID
    version: int
    status: str
    content_json: Optional[dict] = None
    generated_by_id: UUID
    approved_by_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
