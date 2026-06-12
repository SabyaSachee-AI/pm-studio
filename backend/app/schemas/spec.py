from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SpecColumn(BaseModel):
    name: str
    type: str = ""


class SpecTable(BaseModel):
    name: str
    relevant_columns: list[SpecColumn] = Field(default_factory=list)


class SpecDatabase(BaseModel):
    tables: list[SpecTable] = Field(default_factory=list)


class SpecApiEndpoint(BaseModel):
    method: str = ""
    path: str = ""
    request_body: str = ""
    response_schema: str = ""
    status_code: str = "200"


class SpecCoreSchema(BaseModel):
    """Phase 1 — structured fields (smaller token budget, saved before prompt phase)."""

    task_scope: str
    linked_fr: str = ""
    linked_prd_feature: str = ""
    files_to_create: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    database: SpecDatabase = Field(default_factory=SpecDatabase)
    api_endpoints: list[SpecApiEndpoint] = Field(default_factory=list)
    frontend_route: str = ""
    frontend_component: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    technical_notes: str = ""


class SpecPromptSchema(BaseModel):
    """Phase 2 — implementation summary only."""

    cursor_prompt: str


class TaskSpecSchema(BaseModel):
    task_scope: str
    linked_fr: str = ""
    linked_prd_feature: str = ""
    files_to_create: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    database: SpecDatabase = Field(default_factory=SpecDatabase)
    api_endpoints: list[SpecApiEndpoint] = Field(default_factory=list)
    frontend_route: str = ""
    frontend_component: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    technical_notes: str = ""
    cursor_prompt: str
    # Legacy fields — optional fallbacks for older specs
    implementation_steps: list[str] = Field(default_factory=list)
    files_reference_only: list[str] = Field(default_factory=list)
    backend_requirements: Optional[str] = None
    frontend_requirements: Optional[str] = None
    database_requirements: Optional[str] = None
    security_requirements: list[str] = Field(default_factory=list)
    test_requirements: list[str] = Field(default_factory=list)
    strict_rules: list[str] = Field(default_factory=list)
    expected_output: list[str] = Field(default_factory=list)
    manual_test_checklist: list[str] = Field(default_factory=list)


class SpecGenerateRequest(BaseModel):
    task_id: UUID


class SpecRegenerateRequest(BaseModel):
    task_id: UUID


class SpecAssignRequest(BaseModel):
    assigned_to_id: UUID


class SpecUpdateRequest(BaseModel):
    content_json: dict


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
