from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FeatureItem(BaseModel):
    title: str
    description: str
    priority: str  # must-have, should-have, nice-to-have


class UserStory(BaseModel):
    as_a: str
    i_want_to: str
    so_that: str
    acceptance_criteria: list[str]


class PRDSchema(BaseModel):
    executive_summary: str
    problem_statement: str
    target_users: list[str]
    features: list[FeatureItem]
    user_stories: list[UserStory]
    out_of_scope: list[str]
    success_metrics: list[str]
    assumptions: list[str]


class PRDResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    requirement_id: Optional[UUID]
    version: int
    status: str
    content_json: Optional[dict]
    generated_by_id: UUID
    approved_by_id: Optional[UUID]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
