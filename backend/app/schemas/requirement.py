from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GapCategory(str, Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    MINOR = "minor"


class RequirementGap(BaseModel):
    description: str
    category: GapCategory
    question: Optional[str] = None


class RequirementAnalysisSchema(BaseModel):
    project_type: str
    gaps: list[RequirementGap]
    business_risks: list[str]
    technical_questions: list[str]
    missing_nfr: list[str]
    summary: str


class RequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    original_filename: str
    status: str
    analysis_result: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime
