"""AI PRD generation — canonical entry point."""

from app.schemas.prd import PRDSchema
from app.services.prd.service import generate_prd_ai

__all__ = ["PRDSchema", "generate_prd_ai"]
