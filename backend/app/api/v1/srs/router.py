"""SRS API endpoints."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_roles, require_screen_permission
from app.core.database import get_db
from app.models.document_version import DocumentType
from app.models.prd import PRD, PRDStatus
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.models.user import User, UserRole
from app.schemas.srs import SRSResponse
from app.services.ai.model_override import model_override_scope
from app.services.ai.srs_service import (
    append_version_history,
    check_srs_quality,
    compute_srs_stats,
    enrich_srs_content,
    rewrite_srs_ai,
)
from app.services.prd.source import get_finalized_prd_body, is_prd_finalized, prd_eligible_for_downstream, strip_prd_body
from app.services.document.versioning import save_document_version
from app.workers.srs_tasks import generate_srs_task

router = APIRouter(prefix="/srs", tags=["SRS"])


class SRSGenerateRequest(BaseModel):
    project_id: UUID
    prd_id: UUID


class SRSUpdateRequest(BaseModel):
    content_json: dict[str, Any]
    change_note: str | None = None


class SRSRewriteRequest(BaseModel):
    instructions: str


def _prd_workflow_status(prd: PRD) -> str:
    meta = (prd.content_json or {}).get("_meta") or {}
    if meta.get("workflow_finalized"):
        return "finalized"
    if meta.get("workflow_confirmed"):
        return "confirmed"
    if prd.status == PRDStatus.approved:
        return "finalized"
    if prd.status == PRDStatus.submitted:
        return "confirmed"
    return prd.status.value


def _is_prd_eligible_for_srs(prd: PRD) -> bool:
    return prd_eligible_for_downstream(prd)


def _prd_body_for_reference(prd: PRD | None) -> dict[str, Any] | None:
    if not prd or not prd.content_json:
        return None
    return get_finalized_prd_body(prd.content_json) or strip_prd_body(prd.content_json)


def _prd_display_name(prd: PRD, project_name: str) -> str:
    timestamp = prd.created_at.strftime("%d %b %Y, %I:%M %p")
    return f"{project_name} PRD — v{prd.version} — {timestamp}"


def _srs_workflow_status(srs: SRS) -> str:
    meta = (srs.content_json or {}).get("_meta") or {}
    if meta.get("workflow_finalized"):
        return "finalized"
    if meta.get("workflow_confirmed"):
        return "confirmed"
    if srs.status == SRSStatus.approved:
        return "finalized"
    if srs.status == SRSStatus.submitted:
        return "confirmed"
    if srs.status == SRSStatus.rejected:
        return "draft"
    return srs.status.value


def _prepare_content(content: dict[str, Any] | None) -> dict[str, Any] | None:
    if not content:
        return None
    return enrich_srs_content(content)


class SRSEnrichedResponse(SRSResponse):
    generation_task_id: Optional[str] = None
    workflow_status: str
    source_prd_display_name: Optional[str] = None
    stats: Optional[dict[str, Any]] = None


def _to_srs_response(
    srs: SRS,
    prd: PRD | None = None,
    project: Project | None = None,
) -> SRSEnrichedResponse:
    content = _prepare_content(srs.content_json)
    prd_content = _prd_body_for_reference(prd)
    stats = compute_srs_stats(content, prd_content) if content else None

    if srs.status == SRSStatus.approved and stats is not None:
        stats = {**stats, "client_approval_status": "approved"}
    elif content:
        meta = content.get("_meta") or {}
        if stats is not None and meta.get("client_approval_status"):
            stats = {**stats, "client_approval_status": meta["client_approval_status"]}

    project_name = project.name if project else "Project"
    source_name = _prd_display_name(prd, project_name) if prd else None

    return SRSEnrichedResponse(
        id=srs.id,
        project_id=srs.project_id,
        prd_id=srs.prd_id,
        version=srs.version,
        status=_srs_workflow_status(srs),
        content_json=content,
        generated_by_id=srs.generated_by_id,
        approved_by_id=srs.approved_by_id,
        approved_at=srs.approved_at,
        created_at=srs.created_at,
        updated_at=srs.updated_at,
        generation_task_id=srs.generation_task_id,
        workflow_status=_srs_workflow_status(srs),
        source_prd_display_name=source_name,
        stats=stats,
    )


async def _load_srs(srs_id: UUID, db: AsyncSession) -> SRS:
    result = await db.execute(
        select(SRS)
        .options(
            selectinload(SRS.prd),
            selectinload(SRS.project),
            selectinload(SRS.generated_by),
        )
        .where(SRS.id == srs_id, SRS.deleted_at.is_(None))
    )
    srs = result.scalar_one_or_none()
    if srs is None:
        raise HTTPException(status_code=404, detail="SRS not found")
    return srs


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_srs(
    body: SRSGenerateRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> dict[str, str]:
    """Queue SRS generation from a finalized PRD."""
    prd_result = await db.execute(
        select(PRD)
        .options(selectinload(PRD.project))
        .where(PRD.id == body.prd_id, PRD.deleted_at.is_(None))
    )
    prd = prd_result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=404, detail="PRD not found")
    if not prd.content_json:
        raise HTTPException(status_code=400, detail="PRD has no content")
    if not _is_prd_eligible_for_srs(prd):
        raise HTTPException(
            status_code=400,
            detail="PRD must be finalized or confirmed before SRS generation",
        )

    srs = SRS(
        project_id=body.project_id,
        prd_id=body.prd_id,
        status=SRSStatus.draft,
        content_json=None,
        generated_by_id=current_user.id,
    )
    db.add(srs)
    await db.commit()
    await db.refresh(srs)

    task = generate_srs_task.delay(
        str(srs.id),
        model_provider=model_provider,
        model_id=model_id,
    )
    srs.generation_task_id = task.id
    await db.commit()

    return {
        "srs_id": str(srs.id),
        "task_id": task.id,
        "status": "generating",
    }


@router.get("/project/{project_id}", response_model=list[SRSEnrichedResponse])
async def list_project_srs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "view")),
) -> list[SRSEnrichedResponse]:
    """List SRS documents for a project, newest first."""
    result = await db.execute(
        select(SRS)
        .options(selectinload(SRS.prd), selectinload(SRS.project))
        .where(SRS.project_id == project_id, SRS.deleted_at.is_(None))
        .order_by(SRS.created_at.desc())
    )
    return [
        _to_srs_response(srs, srs.prd, srs.project) for srs in result.scalars().all()
    ]


@router.get("/{srs_id}", response_model=SRSEnrichedResponse)
async def get_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "view")),
) -> SRSEnrichedResponse:
    """Return an SRS document by id."""
    srs = await _load_srs(srs_id, db)
    if srs.content_json:
        enriched = enrich_srs_content(srs.content_json)
        meta = dict(enriched.get("_meta") or {})
        if not meta.get("generated_at"):
            meta["generated_at"] = srs.created_at.isoformat()
        enriched["_meta"] = meta
        srs.content_json = enriched
    return _to_srs_response(srs, srs.prd, srs.project)


@router.patch("/{srs_id}", response_model=SRSEnrichedResponse)
async def update_srs(
    srs_id: UUID,
    body: SRSUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> SRSEnrichedResponse:
    """Edit SRS content and save as a new version."""
    srs = await _load_srs(srs_id, db)
    if srs.status == SRSStatus.approved:
        raise HTTPException(status_code=400, detail="Cannot edit an approved SRS")

    await save_document_version(
        db,
        document_type=DocumentType.srs,
        document_id=srs.id,
        version=srs.version,
        content_json=srs.content_json or {},
        created_by_id=current_user.id,
        change_note=body.change_note,
    )

    new_version = srs.version + 1
    updated_content = append_version_history(
        body.content_json,
        version=new_version,
        trigger="edit",
        note=body.change_note or f"Edited by {current_user.full_name}",
    )
    meta = dict(updated_content.get("_meta") or {})
    meta["last_edited_at"] = datetime.now(timezone.utc).isoformat()
    meta["last_edited_by"] = current_user.full_name
    updated_content["_meta"] = meta

    srs.version = new_version
    srs.content_json = enrich_srs_content(updated_content)
    if meta.get("workflow_finalized") or meta.get("workflow_confirmed"):
        srs.status = SRSStatus.submitted
    else:
        srs.status = SRSStatus.draft
    await db.commit()
    await db.refresh(srs)
    return _to_srs_response(srs, srs.prd, srs.project)


@router.post("/{srs_id}/rewrite", response_model=SRSEnrichedResponse)
async def rewrite_srs(
    srs_id: UUID,
    body: SRSRewriteRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> SRSEnrichedResponse:
    """Rewrite SRS content based on PM instructions."""
    srs = await _load_srs(srs_id, db)
    if not srs.content_json:
        raise HTTPException(status_code=400, detail="SRS has no content to rewrite")
    instructions = body.instructions.strip()
    if not instructions:
        raise HTTPException(status_code=400, detail="Instructions are required")

    await save_document_version(
        db,
        document_type=DocumentType.srs,
        document_id=srs.id,
        version=srs.version,
        content_json=srs.content_json,
        created_by_id=current_user.id,
        change_note=f"Rewrite: {instructions[:200]}",
    )

    with model_override_scope(model_provider, model_id):
        rewritten = await rewrite_srs_ai(srs.content_json, instructions)
    new_version = srs.version + 1
    content = enrich_srs_content(rewritten.model_dump())
    content = append_version_history(
        content,
        version=new_version,
        trigger="rewrite",
        note=instructions[:500],
    )
    meta = dict(content.get("_meta") or {})
    meta["last_rewrite_instructions"] = instructions
    content["_meta"] = meta

    srs.version = new_version
    srs.content_json = content
    srs.status = SRSStatus.draft
    await db.commit()
    await db.refresh(srs)
    return _to_srs_response(srs, srs.prd, srs.project)


@router.post("/{srs_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_srs(
    srs_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> dict[str, str]:
    """Re-queue full SRS generation."""
    srs = await _load_srs(srs_id, db)
    srs.content_json = None
    srs.status = SRSStatus.draft
    srs.version = 1
    await db.commit()

    task = generate_srs_task.delay(
        str(srs.id),
        model_provider=model_provider,
        model_id=model_id,
    )
    srs.generation_task_id = task.id
    await db.commit()

    return {
        "srs_id": str(srs.id),
        "task_id": task.id,
        "status": "regenerating",
    }


@router.post("/{srs_id}/quality-check")
async def quality_check_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "view")),
) -> dict[str, Any]:
    """Validate SRS completeness and traceability."""
    srs = await _load_srs(srs_id, db)
    if not srs.content_json:
        raise HTTPException(status_code=400, detail="SRS has no content")

    prd_content = _prd_body_for_reference(srs.prd)
    result = check_srs_quality(srs.content_json, prd_content)
    content = enrich_srs_content(srs.content_json)
    meta = dict(content.get("_meta") or {})
    meta["quality_score"] = result.score
    meta["quality_checks"] = [c.model_dump() for c in result.checks]
    meta["traceability"] = result.traceability
    meta["quality_checked_at"] = datetime.now(timezone.utc).isoformat()
    content["_meta"] = meta
    srs.content_json = content
    await db.commit()

    return {
        "score": result.score,
        "checks": [c.model_dump() for c in result.checks],
        "traceability": result.traceability,
        "stats": compute_srs_stats(content, prd_content),
    }


@router.patch("/{srs_id}/confirm", response_model=SRSEnrichedResponse)
async def confirm_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> SRSEnrichedResponse:
    """Confirm and finalize SRS for development and client portal."""
    srs = await _load_srs(srs_id, db)
    if not srs.content_json:
        raise HTTPException(status_code=400, detail="SRS has no content to confirm")

    content = enrich_srs_content(srs.content_json)
    meta = dict(content.get("_meta") or {})
    meta["workflow_confirmed"] = True
    meta["workflow_finalized"] = True
    meta["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    meta["confirmed_by_name"] = current_user.full_name
    meta["confirmed_by_id"] = str(current_user.id)
    meta["client_approval_status"] = "pending"
    meta["portal_sent_at"] = datetime.now(timezone.utc).isoformat()
    content["_meta"] = meta
    srs.content_json = content
    srs.status = SRSStatus.submitted
    await db.commit()
    await db.refresh(srs)
    return _to_srs_response(srs, srs.prd, srs.project)


@router.patch("/{srs_id}/submit", response_model=SRSEnrichedResponse)
async def submit_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> SRSEnrichedResponse:
    """Submit an SRS for client/architect approval."""
    srs = await _load_srs(srs_id, db)
    if not srs.content_json:
        raise HTTPException(status_code=400, detail="SRS has no content to submit")
    if srs.status not in {SRSStatus.draft, SRSStatus.rejected, SRSStatus.submitted}:
        raise HTTPException(status_code=400, detail="SRS cannot be submitted in current status")

    content = enrich_srs_content(srs.content_json)
    meta = dict(content.get("_meta") or {})
    meta["client_approval_status"] = "pending"
    content["_meta"] = meta
    srs.content_json = content
    srs.status = SRSStatus.submitted
    await db.commit()
    await db.refresh(srs)
    return _to_srs_response(srs, srs.prd, srs.project)


@router.patch("/{srs_id}/approve", response_model=SRSEnrichedResponse)
async def approve_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.architect, UserRole.studio_owner)
    ),
) -> SRSEnrichedResponse:
    """Approve a submitted SRS (architect, owner, or client)."""
    srs = await _load_srs(srs_id, db)
    if srs.status != SRSStatus.submitted:
        raise HTTPException(status_code=400, detail="SRS must be submitted before approval")

    if srs.content_json:
        content = enrich_srs_content(srs.content_json)
        meta = dict(content.get("_meta") or {})
        meta["client_approval_status"] = "approved"
        meta["client_approved_at"] = datetime.now(timezone.utc).isoformat()
        content["_meta"] = meta
        srs.content_json = content

    srs.status = SRSStatus.approved
    srs.approved_by_id = current_user.id
    srs.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(srs)
    return _to_srs_response(srs, srs.prd, srs.project)


@router.delete("/{srs_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> None:
    """Soft-delete an SRS document."""
    srs = await _load_srs(srs_id, db)
    srs.deleted_at = datetime.now(timezone.utc)
    await db.commit()
