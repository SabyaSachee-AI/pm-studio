"""Pydantic schemas for Architecture Suite documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TechStackItem(BaseModel):
    name: str
    version: str = ""
    reason: str = ""


class SystemComponent(BaseModel):
    name: str
    type: str = ""
    responsibility: str = ""
    communicates_with: list[str] = Field(default_factory=list)
    port: Optional[int] = None


class SystemArchSchema(BaseModel):
    overview: str = ""
    architecture_pattern: str = ""
    tech_stack: dict[str, TechStackItem | dict[str, Any]] = Field(default_factory=dict)
    components: list[SystemComponent] = Field(default_factory=list)
    data_flow: list[str] = Field(default_factory=list)
    infrastructure: dict[str, Any] = Field(default_factory=dict)
    diagrams: dict[str, str] = Field(default_factory=dict)


class DbColumn(BaseModel):
    name: str
    type: str
    pk: bool = False
    nullable: bool = True
    default: str = ""


class DbTable(BaseModel):
    name: str
    purpose: str = ""
    linked_srs_entity: str = ""
    columns: list[DbColumn] = Field(default_factory=list)
    indexes: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    overview: str = ""
    database: str = "PostgreSQL 16"
    conventions: dict[str, str] = Field(default_factory=dict)
    tables: list[DbTable] = Field(default_factory=list)
    relationships: list[dict[str, str]] = Field(default_factory=list)
    migration_order: list[str] = Field(default_factory=list)
    diagrams: dict[str, str] = Field(default_factory=dict)


class ApiEndpoint(BaseModel):
    id: str = ""
    module: str = ""
    method: str = ""
    path: str = ""
    full_path: str = ""
    description: str = ""
    linked_fr: str = ""
    mvp_scope: str = "v1"
    auth_required: bool = True
    request_body: dict[str, Any] = Field(default_factory=dict)
    response_200: dict[str, Any] = Field(default_factory=dict)
    response_errors: dict[str, str] = Field(default_factory=dict)
    cookies_set: list[str] = Field(default_factory=list)
    file: str = ""


class ApiSchema(BaseModel):
    overview: str = ""
    base_url: str = "/api/v1"
    auth: str = ""
    versioning: str = ""
    response_format: dict[str, Any] = Field(default_factory=dict)
    global_headers: dict[str, str] = Field(default_factory=dict)
    endpoints: list[ApiEndpoint] = Field(default_factory=list)
    diagrams: dict[str, str] = Field(default_factory=dict)


class ApiShellSchema(BaseModel):
    """API doc shell — everything except endpoints (chunked generation, call 1)."""
    overview: str = ""
    base_url: str = "/api/v1"
    auth: str = ""
    versioning: str = ""
    response_format: dict[str, Any] = Field(default_factory=dict)
    global_headers: dict[str, str] = Field(default_factory=dict)
    diagrams: dict[str, str] = Field(default_factory=dict)


class ApiChunkSchema(BaseModel):
    """Endpoints for one FR group (chunked generation, calls 2..N)."""
    endpoints: list[ApiEndpoint] = Field(default_factory=list)


class FrontendPage(BaseModel):
    path: str = ""
    file: str = ""
    description: str = ""
    components: list[str] = Field(default_factory=list)
    api_calls: list[str] = Field(default_factory=list)
    protected: bool = True


class FrontendSchema(BaseModel):
    overview: str = ""
    framework: str = ""
    state_management: dict[str, str] = Field(default_factory=dict)
    styling: str = ""
    api_client: str = ""
    auth: str = ""
    pages: list[FrontendPage] = Field(default_factory=list)
    folder_structure: dict[str, Any] = Field(default_factory=dict)
    diagrams: dict[str, str] = Field(default_factory=dict)


class SecuritySchema(BaseModel):
    overview: str = ""
    auth_mechanism: dict[str, Any] = Field(default_factory=dict)
    rbac: dict[str, Any] = Field(default_factory=dict)
    api_security: list[dict[str, str]] = Field(default_factory=list)
    owasp_checklist: list[dict[str, str]] = Field(default_factory=list)
    diagrams: dict[str, str] = Field(default_factory=dict)


class UiUxSchema(BaseModel):
    overview: str = ""
    design_system: dict[str, Any] = Field(default_factory=dict)
    pages: list[dict[str, Any]] = Field(default_factory=list)
    ux_rules: list[str] = Field(default_factory=list)
    diagrams: dict[str, str] = Field(default_factory=dict)


class ArchitectureFullSchema(BaseModel):
    system_arch: SystemArchSchema
    database: DatabaseSchema
    api: ApiSchema
    frontend: FrontendSchema
    security: SecuritySchema
    uiux: UiUxSchema


class ArchitectureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    srs_id: UUID
    status: str
    version: int
    display_name: Optional[str] = None
    created_by_id: UUID
    confirmed_by_id: Optional[UUID] = None
    confirmed_at: Optional[datetime] = None
    generation_task_id: Optional[str] = None
    doc_task_ids: dict[str, str] = Field(default_factory=dict)
    generation_progress: Optional[dict[str, Any]] = None
    can_resume: bool = False
    last_error: Optional[str] = None
    resume_from: Optional[str] = None
    suite_canon: Optional[dict[str, Any]] = None
    consistency_report: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    doc_system_arch: Optional[dict] = None
    doc_database: Optional[dict] = None
    doc_api: Optional[dict] = None
    doc_frontend: Optional[dict] = None
    doc_security: Optional[dict] = None
    doc_uiux: Optional[dict] = None
    doc_system_arch_status: str = "pending"
    doc_database_status: str = "pending"
    doc_api_status: str = "pending"
    doc_frontend_status: str = "pending"
    doc_security_status: str = "pending"
    doc_uiux_status: str = "pending"


class ArchitectureListItem(BaseModel):
    id: UUID
    project_id: UUID
    srs_id: UUID
    status: str
    version: int
    display_name: str
    created_at: datetime
    source_srs_display_name: Optional[str] = None
    docs_generated: int = 0
    docs_total: int = 6
