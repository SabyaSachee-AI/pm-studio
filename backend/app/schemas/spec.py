from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TaskSpecSchema(BaseModel):
    task_scope: str
    implementation_steps: list[str]
    files_to_modify: list[str]
    files_reference_only: list[str]
    backend_requirements: Optional[str] = None
    frontend_requirements: Optional[str] = None
    database_requirements: Optional[str] = None
    security_requirements: list[str]
    test_requirements: list[str]
    strict_rules: list[str]
    expected_output: list[str]
    manual_test_checklist: list[str]
    cursor_prompt: str


class SpecGenerateRequest(BaseModel):
    task_id: UUID


class SpecAssignRequest(BaseModel):
    assigned_to_id: UUID


class TaskSpecResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    status: str
    content_json: Optional[dict]
    assigned_to_id: Optional[UUID]
    generation_task_id: Optional[str]
    created_at: datetime
    updated_at: datetime
