"""Celery tasks for SRS generation."""

import asyncio
import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.prd import PRD
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.services.ai.model_override import clear_model_override, set_model_override
from app.services.ai.srs_service import enrich_srs_content
from app.services.srs.service import generate_srs_ai

logger = logging.getLogger(__name__)


@celery_app.task(name="srs.generate")
def generate_srs_task(
    srs_id: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, str]:
    """Background task to generate SRS from approved PRD."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    srs: SRS | None = None
    try:
        srs = db.query(SRS).filter(SRS.id == UUID(srs_id)).first()
        if not srs:
            return {"error": "SRS not found"}

        prd = db.query(PRD).filter(PRD.id == srs.prd_id).first()
        project = db.query(Project).filter(Project.id == srs.project_id).first()

        if not prd or not prd.content_json:
            srs.status = SRSStatus.rejected
            db.commit()
            return {"error": "PRD has no content"}

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            srs_data = loop.run_until_complete(
                generate_srs_ai(
                    prd_content=prd.content_json,
                    project_name=project.name if project else "Unknown Project",
                )
            )
        finally:
            loop.close()

        srs.content_json = enrich_srs_content(srs_data.model_dump())
        srs.status = SRSStatus.draft
        db.commit()

        return {"srs_id": srs_id, "status": SRSStatus.draft.value}

    except Exception as exc:
        logger.exception("SRS generation failed", extra={"srs_id": srs_id})
        if srs is not None:
            srs.status = SRSStatus.rejected
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()
