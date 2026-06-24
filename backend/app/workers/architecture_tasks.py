"""Celery tasks for architecture suite generation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.architecture import Architecture
from app.models.prd import PRD
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.srs import SRS
from app.services.ai.architecture_service import (
    ARCH_DOC_KEYS,
    _requirements_brief,
    consolidate_architecture_suite,
    edit_architecture_suite_ai,
    generate_full_architecture,
    run_single_architecture_diagram,
    run_single_architecture_doc,
)
from app.services.ai.model_override import clear_model_override, set_model_override
from app.services.prd.source import resolve_prd_for_downstream

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="architecture.generate")
def generate_architecture_task(
    self,
    architecture_id: str,
    resume: bool = False,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Generate all 6 architecture documents sequentially."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    arch: Architecture | None = None
    try:
        arch = (
            db.query(Architecture)
            .filter(Architecture.id == UUID(architecture_id), Architecture.deleted_at.is_(None))
            .first()
        )
        if not arch:
            return {"error": "Architecture not found"}

        srs = db.query(SRS).filter(SRS.id == arch.srs_id).first()
        project = db.query(Project).filter(Project.id == arch.project_id).first()
        if not srs or not srs.content_json:
            arch.last_error = "SRS not found or empty"
            db.commit()
            return {"error": arch.last_error}

        arch.generation_task_id = self.request.id
        db.commit()

        # Fetch PRD (finalized snapshot) and requirements for richer context
        prd = db.query(PRD).filter(PRD.id == srs.prd_id).first() if srs.prd_id else None
        prd_content = None
        if prd and prd.content_json:
            prd_content, _ = resolve_prd_for_downstream(prd)

        reqs = (
            db.query(Requirement)
            .filter(
                Requirement.project_id == arch.project_id,
                Requirement.deleted_at.is_(None),
            )
            .all()
        )
        requirements_context = _requirements_brief(reqs)

        project_info = {
            "name": project.name if project else "Project",
            "type": "Web App",
            "description": (project.description if project else "") or "",
        }
        return _run_async(
            generate_full_architecture(
                UUID(architecture_id),
                srs.content_json,
                project_info,
                db,
                resume=resume,
                prd_content=prd_content,
                requirements_context=requirements_context,
            )
        )
    except Exception as exc:
        logger.exception("Architecture generation failed", extra={"architecture_id": architecture_id})
        if arch is not None:
            arch.last_error = str(exc)[:500]
            arch.can_resume = True
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


@celery_app.task(bind=True, name="architecture.generate_doc")
def generate_architecture_doc_task(
    self,
    architecture_id: str,
    doc_key: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Generate a single architecture document."""
    return _run_single_doc(
        architecture_id,
        doc_key,
        "",
        model_provider=model_provider,
        model_id=model_id,
    )


@celery_app.task(bind=True, name="architecture.consolidate")
def consolidate_architecture_task(
    self,
    architecture_id: str,
) -> dict[str, Any]:
    """Align all docs to suite canon and persist consistency scores."""
    db = SyncSessionLocal()
    arch: Architecture | None = None
    try:
        arch = (
            db.query(Architecture)
            .filter(Architecture.id == UUID(architecture_id), Architecture.deleted_at.is_(None))
            .first()
        )
        if not arch:
            return {"error": "Architecture not found"}

        result = _run_async(consolidate_architecture_suite(UUID(architecture_id), db))
        arch.generation_progress = {
            "phase": "consolidated",
            "message": "Suite aligned to shared canon",
        }
        db.commit()
        return result
    except Exception as exc:
        logger.exception("Architecture consolidation failed")
        if arch is not None:
            arch.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()


@celery_app.task(bind=True, name="architecture.reassess")
def reassess_architecture_task(
    self,
    architecture_id: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """AI-reassess the whole suite: align to canon, AI-repair weak docs, re-score."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    arch: Architecture | None = None
    try:
        arch = (
            db.query(Architecture)
            .filter(Architecture.id == UUID(architecture_id), Architecture.deleted_at.is_(None))
            .first()
        )
        if not arch:
            return {"error": "Architecture not found"}

        result = _run_async(
            consolidate_architecture_suite(UUID(architecture_id), db, ai_repair=True)
        )
        arch.generation_progress = {
            "phase": "reassessed",
            "message": "Suite reassessed with AI",
        }
        db.commit()
        return result
    except Exception as exc:
        logger.exception("Architecture reassess failed")
        if arch is not None:
            arch.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


@celery_app.task(bind=True, name="architecture.edit_suite")
def edit_architecture_suite_task(
    self,
    architecture_id: str,
    instruction: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Apply one PM instruction across all 6 docs, then re-align and re-score."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    arch: Architecture | None = None
    try:
        arch = (
            db.query(Architecture)
            .filter(Architecture.id == UUID(architecture_id), Architecture.deleted_at.is_(None))
            .first()
        )
        if not arch:
            return {"error": "Architecture not found"}

        result = _run_async(
            edit_architecture_suite_ai(UUID(architecture_id), instruction, db)
        )
        arch.generation_progress = {
            "phase": "suite_edited",
            "message": "Suite updated with AI edits",
        }
        db.commit()
        return result
    except Exception as exc:
        logger.exception("Architecture suite edit failed")
        if arch is not None:
            arch.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()


@celery_app.task(bind=True, name="architecture.regenerate_doc")
def regenerate_architecture_doc_task(
    self,
    architecture_id: str,
    doc_key: str,
    instructions: str = "",
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Regenerate one document with optional instructions."""
    return _run_single_doc(
        architecture_id,
        doc_key,
        instructions,
        model_provider=model_provider,
        model_id=model_id,
    )


@celery_app.task(bind=True, name="architecture.regenerate_diagram")
def regenerate_architecture_diagram_task(
    self,
    architecture_id: str,
    doc_key: str,
    diagram_name: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Regenerate a single AI diagram within one architecture document."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    try:
        valid_keys = {k for k, _ in ARCH_DOC_KEYS}
        if doc_key not in valid_keys:
            return {"error": f"Invalid doc_key: {doc_key}", "diagram_name": diagram_name}

        return _run_async(
            run_single_architecture_diagram(
                UUID(architecture_id),
                doc_key,
                diagram_name,
                db,
            )
        )
    except Exception as exc:
        logger.exception("Architecture diagram regeneration failed")
        return {"error": str(exc)[:500], "diagram_name": diagram_name}
    finally:
        db.close()
        clear_model_override()


def _run_single_doc(
    architecture_id: str,
    doc_key: str,
    instructions: str,
    model_provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    try:
        valid_keys = {k for k, _ in ARCH_DOC_KEYS}
        if doc_key not in valid_keys:
            return {"error": f"Invalid doc_key: {doc_key}"}

        return _run_async(
            run_single_architecture_doc(
                UUID(architecture_id),
                doc_key,
                db,
                instructions=instructions,
            )
        )
    except Exception as exc:
        logger.exception("Architecture doc generation failed")
        return {"error": str(exc)[:500]}
    finally:
        db.close()
        clear_model_override()
