"""Module extraction schemas for PRD + SRS → Kanban tasks."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractedTaskItem(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    fr_references: list[str] = Field(default_factory=list)
    linked_fr: Optional[str] = None
    effort_hours: Optional[float] = None
    suggested_file: Optional[str] = None
    suggested_endpoint: Optional[str] = None
    suggested_table: Optional[str] = None


class ExtractedModule(BaseModel):
    name: str
    description: str = ""
    tasks: list[ExtractedTaskItem] = Field(default_factory=list)


class ModuleListSchema(BaseModel):
    modules: list[ExtractedModule] = Field(default_factory=list)


class ModuleExtractRequest(BaseModel):
    project_id: UUID
    srs_id: UUID
    replace_existing: bool = False
    fill_gaps_only: bool = False
