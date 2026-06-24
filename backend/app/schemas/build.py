"""Pydantic schemas for the code-generation build domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── AI structured-output models (used with ai_call) ──────────────────────────

class GeneratedFileSpec(BaseModel):
    """One file the AI produces for a task."""
    path: str
    content: str
    language: str = ""


class GeneratedFileSet(BaseModel):
    """Code-generation output for a single chunk (one task)."""
    files: list[GeneratedFileSpec] = Field(default_factory=list)


class ScaffoldFile(BaseModel):
    path: str
    content: str
    language: str = ""


class ScaffoldPlan(BaseModel):
    """Stage-0 repo skeleton: config files + dependency/script manifest."""
    files: list[ScaffoldFile] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    scripts: dict[str, str] = Field(default_factory=dict)
    notes: str = ""


# ── API request bodies ───────────────────────────────────────────────────────

class BuildCreateRequest(BaseModel):
    project_id: UUID
    architecture_id: Optional[UUID] = None


class FileUpdateRequest(BaseModel):
    content: str


class FileAiEditRequest(BaseModel):
    instruction: str


# ── API responses ────────────────────────────────────────────────────────────

class GeneratedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: Optional[UUID] = None
    path: str
    content: str
    language: str
    status: str
    checksum: Optional[str] = None


class GeneratedFileListItem(BaseModel):
    """Lightweight file row (no content) for the tree."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: Optional[UUID] = None
    path: str
    language: str
    status: str


class BuildResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    architecture_id: Optional[UUID] = None
    status: str
    version: int
    display_name: Optional[str] = None
    repo_url: Optional[str] = None
    github_full_name: Optional[str] = None
    default_branch: str = "main"
    quality_score: Optional[float] = None
    quality_report: Optional[dict[str, Any]] = None
    generation_progress: Optional[dict[str, Any]] = None
    generation_task_id: Optional[str] = None
    can_resume: bool = False
    last_error: Optional[str] = None
    file_count: int = 0
    created_at: datetime
    updated_at: datetime


class BuildDetailResponse(BuildResponse):
    files: list[GeneratedFileListItem] = Field(default_factory=list)


# ── Local UI test (Stage 4) ────────────────────────────────────────────────────

class UiChecklistItem(BaseModel):
    key: str               # f"{task_id}:{index}"
    task_title: str
    criterion: str


class UiChecklistResponse(BaseModel):
    repo_url: Optional[str] = None
    clone_cmd: str = ""
    run_cmd: str = ""
    items: list[UiChecklistItem] = Field(default_factory=list)


class UiTestResult(BaseModel):
    key: str
    status: str = "pending"   # pending | pass | fail
    note: str = ""


class UiTestSaveRequest(BaseModel):
    results: list[UiTestResult] = Field(default_factory=list)
    signed_off: bool = False
