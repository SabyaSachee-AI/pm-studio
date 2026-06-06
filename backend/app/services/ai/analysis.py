"""AI requirement analysis — canonical entry point."""

from app.schemas.requirement import RequirementAnalysisSchema
from app.services.requirement.service import analyze_requirements_ai

__all__ = ["RequirementAnalysisSchema", "analyze_requirements_ai"]
