"""Celery tasks for architecture suite generation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.services.ai.architecture_service import (
    ARCH_DOC_KEYS,
    generate_architecture_doc_ai,
)

logger = logging.getLogger(__name__)


def _doc_field(key: str) -> str:
    return key


def _status_field(key: str) -> str:
    return f"{key}_status"


def _prior_docs(arch: Architecture) -> dict[str, Any]:
    return {
        key: getattr(arch, key) for key, _ in ARCH_DOC_KEYS
    }


def _srs_eligible(srs: SRS) -> bool:
    meta = (srs.content_json or {}).get("_meta") or {}
    return (
        srs.status == SRSStatus.approved
        or meta.get("workflow_finalized")
        or meta.get("workflow_confirmed")
        or srs.status == SRSStatus.submitted
    )


@celery_app.task(bind=True, name="architecture.generate")
def generate_architecture_task(
    self,
    architecture_id: str,
    resume: bool = False,
) -> dict[str, Any]:
    """Generate all 6 architecture documents sequentially."""
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

        project_name = project.name if project else "Project"
        project_description = project.description if project else ""

        start_idx = 0
        if resume and arch.resume_from:
            for i, (key, _) in enumerate(ARCH_DOC_KEYS):
                if key == arch.resume_from:
                    start_idx = i
                    break

        completed = 0
        for idx, (doc_key, doc_title) in enumerate(ARCH_DOC_KEYS):
            if idx < start_idx:
                status = getattr(arch, _status_field(doc_key))
                if status == "completed":
                    completed += 1
                continue

            cancel_flags = arch.doc_cancel_flags or {}
            if cancel_flags.get(doc_key):
                setattr(arch, _status_field(doc_key), "cancelled")
                db.commit()
                continue

            setattr(arch, _status_field(doc_key), "generating")
            arch.generation_progress = {
                "current_doc": doc_key,
                "current_index": idx + 1,
                "total": len(ARCH_DOC_KEYS),
                "completed": completed,
            }
            arch.generation_task_id = self.request.id
            db.commit()

            self.update_state(
                state="PROGRESS",
                meta=arch.generation_progress,
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                doc = loop.run_until_complete(
                    generate_architecture_doc_ai(
                        doc_key=doc_key,
                        doc_title=doc_title,
                        srs_content=srs.content_json,
                        project_name=project_name,
                        project_description=project_description or "",
                        prior_docs=_prior_docs(arch),
                    )
                )
            finally:
                loop.close()

            setattr(arch, _doc_field(doc_key), doc.model_dump())
            setattr(arch, _status_field(doc_key), "completed")
            arch.resume_from = doc_key
            arch.can_resume = idx < len(ARCH_DOC_KEYS) - 1
            completed += 1
            arch.generation_progress = {
                "current_doc": doc_key,
                "current_index": idx + 1,
                "total": len(ARCH_DOC_KEYS),
                "completed": completed,
            }
            arch.last_error = None
            db.commit()

        arch.can_resume = False
        arch.resume_from = None
        arch.generation_task_id = None
        arch.generation_progress = {"completed": len(ARCH_DOC_KEYS), "total": len(ARCH_DOC_KEYS)}
        arch.status = ArchitectureStatus.draft
        db.commit()

        return {
            "architecture_id": architecture_id,
            "status": "completed",
            "docs_completed": completed,
        }
    except Exception as exc:
        logger.exception("Architecture generation failed", extra={"architecture_id": architecture_id})
        if arch is not None:
            arch.last_error = str(exc)[:500]
            arch.can_resume = True
            if arch.generation_progress:
                doc_key = arch.generation_progress.get("current_doc")
                if doc_key:
                    setattr(arch, _status_field(doc_key), "failed")
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()


@celery_app.task(bind=True, name="architecture.generate_doc")
def generate_architecture_doc_task(
    self,
    architecture_id: str,
    doc_key: str,
) -> dict[str, Any]:
    """Generate a single architecture document."""
    return _run_single_doc(architecture_id, doc_key, "")


@celery_app.task(bind=True, name="architecture.regenerate_doc")
def regenerate_architecture_doc_task(
    self,
    architecture_id: str,
    doc_key: str,
    instructions: str = "",
) -> dict[str, Any]:
    """Regenerate one document with optional instructions."""
    return _run_single_doc(architecture_id, doc_key, instructions)


def _run_single_doc(
    architecture_id: str,
    doc_key: str,
    instructions: str,
) -> dict[str, Any]:
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

        valid_keys = {k for k, _ in ARCH_DOC_KEYS}
        if doc_key not in valid_keys:
            return {"error": f"Invalid doc_key: {doc_key}"}

        doc_title = next((t for k, t in ARCH_DOC_KEYS if k == doc_key), doc_key)
        srs = db.query(SRS).filter(SRS.id == arch.srs_id).first()
        project = db.query(Project).filter(Project.id == arch.project_id).first()

        setattr(arch, _status_field(doc_key), "generating")
        task_ids = arch.doc_task_ids or {}
        db.commit()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            doc = loop.run_until_complete(
                generate_architecture_doc_ai(
                    doc_key=doc_key,
                    doc_title=doc_title,
                    srs_content=(srs.content_json if srs else {}) or {},
                    project_name=project.name if project else "Project",
                    project_description=(project.description if project else "") or "",
                    prior_docs=_prior_docs(arch),
                    instructions=instructions,
                )
            )
        finally:
            loop.close()

        setattr(arch, _doc_field(doc_key), doc.model_dump())
        setattr(arch, _status_field(doc_key), "completed")
        arch.last_error = None
        db.commit()

        return {"architecture_id": architecture_id, "doc_key": doc_key, "status": "completed"}
    except Exception as exc:
        logger.exception("Architecture doc generation failed")
        if arch is not None:
            setattr(arch, _status_field(doc_key), "failed")
            arch.last_error = str(exc)[:500]
            db.commit()
        return {"error": str(exc)[:500]}
    finally:
        db.close()
