"""AI SRS generation — canonical entry point."""

from app.schemas.srs import SRSSchema
from app.services.srs.service import generate_srs_ai

__all__ = ["SRSSchema", "generate_srs_ai"]
