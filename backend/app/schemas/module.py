"""Module extraction schemas for PRD + SRS → Kanban tasks."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractedTaskItem(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    fr_references: list[str] = Field(default_factory=list)
    effort_hours: Optional[float] = None


class ExtractedModule(BaseModel):
    name: str
    description: str = ""
    tasks: list[ExtractedTaskItem] = Field(default_factory=list)


class ModuleListSchema(BaseModel):
    modules: list[ExtractedModule] = Field(default_factory=list)


class ModuleExtractRequest(BaseModel):
    project_id: UUID
    srs_id: UUID
