"""Pydantic schemas for the 6-document architecture suite."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArchitectureDocSchema(BaseModel):
    """Flexible architecture document with required overview and Mermaid diagrams."""

    model_config = ConfigDict(extra="allow")

    overview: str = ""
    diagrams: dict[str, str] = Field(default_factory=dict)


class ArchitectureGenerateRequest(BaseModel):
    project_id: UUID
    srs_id: UUID


class ArchitectureDocGenerateRequest(BaseModel):
    doc_key: str


class ArchitectureDocRegenerateRequest(BaseModel):
    doc_key: str
    instructions: str = ""


class ArchitectureDocSaveRequest(BaseModel):
    doc_key: str
    content: dict[str, Any]


class ArchitectureListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    srs_id: UUID
    status: str
    version: int
    display_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    doc_system_arch_status: Optional[str] = None
    doc_database_status: Optional[str] = None
    doc_api_status: Optional[str] = None
    doc_frontend_status: Optional[str] = None
    doc_security_status: Optional[str] = None
    doc_uiux_status: Optional[str] = None


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
    doc_task_ids: Optional[dict[str, Any]] = None
    generation_progress: Optional[dict[str, Any]] = None
    doc_cancel_flags: Optional[dict[str, Any]] = None
    can_resume: bool = False
    last_error: Optional[str] = None
    resume_from: Optional[str] = None
    suite_canon: Optional[dict[str, Any]] = None
    consistency_report: Optional[dict[str, Any]] = None
    doc_system_arch: Optional[dict[str, Any]] = None
    doc_database: Optional[dict[str, Any]] = None
    doc_api: Optional[dict[str, Any]] = None
    doc_frontend: Optional[dict[str, Any]] = None
    doc_security: Optional[dict[str, Any]] = None
    doc_uiux: Optional[dict[str, Any]] = None
    doc_system_arch_status: Optional[str] = None
    doc_database_status: Optional[str] = None
    doc_api_status: Optional[str] = None
    doc_frontend_status: Optional[str] = None
    doc_security_status: Optional[str] = None
    doc_uiux_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime
