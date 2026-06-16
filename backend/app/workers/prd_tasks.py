"""Celery tasks for PRD generation."""

import asyncio
import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.prd import PRD, PRDStatus
from app.models.project import Project
from app.models.requirement import Requirement
from app.services.ai.model_override import clear_model_override, set_model_override
from app.services.ai.prd_service import enrich_prd_content
from app.services.prd.service import generate_prd_ai
from app.services.requirement.source import resolve_requirement_for_generation

logger = logging.getLogger(__name__)


@celery_app.task(name="prd.generate")
def generate_prd_task(
    prd_id: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, str]:
    """Background task to generate PRD using Claude AI."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    prd: PRD | None = None
    try:
        prd = db.query(PRD).filter(PRD.id == UUID(prd_id)).first()
        if not prd:
            return {"error": "PRD not found"}

        project = db.query(Project).filter(Project.id == prd.project_id).first()
        requirement = db.query(Requirement).filter(
            Requirement.id == prd.requirement_id
        ).first()

        if not requirement or not requirement.analysis_result:
            prd.status = PRDStatus.rejected
            db.commit()
            return {"error": "Requirement not analyzed yet"}

        requirement_text, analysis_result = resolve_requirement_for_generation(
            requirement
        )
        source = analysis_result.get("_generation_source", {})
        if source.get("type") == "missing_final_draft":
            prd.status = PRDStatus.rejected
            db.commit()
            return {
                "error": source.get(
                    "error",
                    "Finalized requirement has no final draft content for PRD generation",
                )
            }
        if not requirement_text.strip():
            prd.status = PRDStatus.rejected
            db.commit()
            return {"error": "No requirement content available for PRD generation"}

        source = analysis_result.get("_generation_source", {})
        logger.info(
            "PRD generation source for requirement %s: %s v%s",
            requirement.id,
            source.get("type"),
            source.get("version"),
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            prd_data = loop.run_until_complete(
                generate_prd_ai(
                    requirement_text=requirement_text,
                    analysis_result=analysis_result,
                    project_name=project.name if project else "Unknown Project",
                )
            )
        finally:
            loop.close()

        prd.content_json = enrich_prd_content(prd_data.model_dump())
        if isinstance(prd.content_json, dict):
            meta = dict(prd.content_json.get("_meta") or {})
            meta["requirement_source"] = source
            prd.content_json["_meta"] = meta
        prd.status = PRDStatus.draft
        db.commit()

        return {"prd_id": prd_id, "status": PRDStatus.draft.value}

    except Exception as exc:
        logger.exception("PRD generation failed", extra={"prd_id": prd_id})
        if prd is not None:
            prd.status = PRDStatus.rejected
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()
