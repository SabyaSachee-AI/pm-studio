"""Celery tasks for requirement document processing."""

import asyncio
import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.requirement import Requirement, RequirementStatus
from app.schemas.requirement import RequirementAnalysisSchema
from app.services.requirement.cost import estimate_cost
from app.services.requirement.service import analyze_requirements_ai, extract_text_from_pdf
from app.services.storage.service import get_local_path

logger = logging.getLogger(__name__)


def _merge_text(original: str, feedback: str) -> str:
    return (
        f"{original}\n\n--- CLIENT FEEDBACK ---\n\n{feedback}"
        if feedback
        else original
    )


@celery_app.task(name="requirements.process_upload")
def process_requirement_task(requirement_id: str) -> None:
    """Background task to extract text and run AI analysis."""
    db = SyncSessionLocal()
    req: Requirement | None = None
    try:
        req = (
            db.query(Requirement)
            .filter(Requirement.id == UUID(requirement_id))
            .first()
        )
        if not req:
            return

        req.status = RequirementStatus.extracting
        db.commit()

        local_path = get_local_path(req.storage_path)
        text = extract_text_from_pdf(local_path)

        if req.feedback_storage_path:
            feedback_path = get_local_path(req.feedback_storage_path)
            feedback_text = extract_text_from_pdf(feedback_path)
            text = _merge_text(text, feedback_text)

        req.extracted_text = text
        req.status = RequirementStatus.analyzing
        db.commit()

        analysis_result = asyncio.run(analyze_requirements_ai(text))
        req.analysis_result = analysis_result.model_dump()

        cost = estimate_cost(analysis_result)
        req.cost_estimate_json = cost
        req.status = RequirementStatus.analyzed
        db.commit()

    except Exception as exc:
        logger.error("Requirement processing failed: %s", exc)
        if req is not None:
            req.status = RequirementStatus.failed
            req.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()
