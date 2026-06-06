"""Celery tasks for SRS generation."""

import asyncio
import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.prd import PRD
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.services.srs.service import generate_srs_ai

logger = logging.getLogger(__name__)


@celery_app.task(name="srs.generate")
def generate_srs_task(srs_id: str) -> dict[str, str]:
    """Background task to generate SRS from approved PRD."""
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

        srs_data = asyncio.run(
            generate_srs_ai(
                prd_content=prd.content_json,
                project_name=project.name if project else "Unknown Project",
            )
        )

        srs.content_json = srs_data.model_dump()
        srs.status = SRSStatus.draft
        db.commit()

        return {"srs_id": srs_id, "status": SRSStatus.draft.value}

    except Exception as exc:
        logger.error("SRS generation failed: %s", exc)
        if srs is not None:
            srs.status = SRSStatus.rejected
            db.commit()
        return {"error": str(exc)}
    finally:
        db.close()
