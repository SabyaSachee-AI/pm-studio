from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskStatusEnum(str, Enum):
    backlog = "backlog"
    assigned = "assigned"
    in_progress = "in_progress"
    in_review = "in_review"
    done = "done"


class TaskTypeEnum(str, Enum):
    feature = "feature"
    bug = "bug"
    improvement = "improvement"
    research = "research"
    devops = "devops"


class TaskPriorityEnum(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TaskCreate(BaseModel):
    project_id: UUID
    srs_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    task_type: TaskTypeEnum = TaskTypeEnum.feature
    priority: TaskPriorityEnum = TaskPriorityEnum.medium
    assigned_to_id: Optional[UUID] = None
    effort_hours: Optional[float] = None
    fr_references: Optional[list[str]] = None
    module_name: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    task_type: Optional[TaskTypeEnum] = None
    priority: Optional[TaskPriorityEnum] = None
    status: Optional[TaskStatusEnum] = None
    assigned_to_id: Optional[UUID] = None
    effort_hours: Optional[float] = None
    fr_references: Optional[list[str]] = None
    module_name: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatusEnum
    note: Optional[str] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    srs_id: Optional[UUID]
    title: str
    description: Optional[str]
    task_type: str
    priority: str
    status: str
    assigned_to_id: Optional[UUID]
    effort_hours: Optional[float]
    fr_references: Optional[list]
    linked_fr: Optional[str]
    module_name: Optional[str]
    order_index: int
    suggested_file: Optional[str]
    suggested_endpoint: Optional[str]
    suggested_table: Optional[str]
    spec_id: Optional[UUID] = None
    spec_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class KanbanBoard(BaseModel):
    backlog: list[TaskResponse]
    assigned: list[TaskResponse]
    in_progress: list[TaskResponse]
    in_review: list[TaskResponse]
    done: list[TaskResponse]
