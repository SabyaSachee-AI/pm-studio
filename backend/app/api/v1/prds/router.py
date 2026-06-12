"""PRD API endpoints."""

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
from app.models.requirement import Requirement
from app.models.user import User, UserRole
from app.schemas.prd import PRDResponse
from app.services.ai.model_override import model_override_scope
from app.services.ai.prd_service import (
    append_version_history,
    check_prd_quality,
    compute_prd_stats,
    enrich_prd_content,
    rewrite_prd_ai,
)
from app.services.document.versioning import save_document_version
from app.workers.prd_tasks import generate_prd_task

router = APIRouter(prefix="/prds", tags=["PRDs"])


class PRDGenerateRequest(BaseModel):
    project_id: UUID
    requirement_id: UUID


class PRDUpdateRequest(BaseModel):
    content_json: dict[str, Any]
    change_note: str | None = None


class PRDRewriteRequest(BaseModel):
    instructions: str


def _requirement_finalized(req: Requirement) -> bool:
    analysis = req.analysis_result or {}
    return bool(analysis.get("finalized"))


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


def _prepare_content(content: dict[str, Any] | None) -> dict[str, Any] | None:
    if not content:
        return None
    return enrich_prd_content(content)


class PRDEnrichedResponse(PRDResponse):
    generation_task_id: Optional[str] = None
    workflow_status: str
    source_requirement_name: Optional[str] = None
    stats: Optional[dict[str, Any]] = None


def _to_prd_response(
    prd: PRD,
    requirement: Requirement | None = None,
) -> PRDEnrichedResponse:
    content = _prepare_content(prd.content_json)
    stats = compute_prd_stats(content) if content else None
    source_name = None
    if requirement:
        analysis = requirement.analysis_result or {}
        source_name = analysis.get("display_name") or requirement.original_filename

    return PRDEnrichedResponse(
        id=prd.id,
        project_id=prd.project_id,
        requirement_id=prd.requirement_id,
        version=prd.version,
        status=_prd_workflow_status(prd),
        content_json=content,
        generated_by_id=prd.generated_by_id,
        approved_by_id=prd.approved_by_id,
        approved_at=prd.approved_at,
        created_at=prd.created_at,
        updated_at=prd.updated_at,
        generation_task_id=prd.generation_task_id,
        workflow_status=_prd_workflow_status(prd),
        source_requirement_name=source_name,
        stats=stats,
    )


async def _load_prd(prd_id: UUID, db: AsyncSession) -> PRD:
    result = await db.execute(
        select(PRD)
        .options(
            selectinload(PRD.generated_by),
            selectinload(PRD.project),
        )
        .where(PRD.id == prd_id, PRD.deleted_at.is_(None))
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=404, detail="PRD not found")
    return prd


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_prd(
    body: PRDGenerateRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> dict[str, str]:
    """Queue PRD generation from a finalized requirement."""
    req_result = await db.execute(
        select(Requirement).where(
            Requirement.id == body.requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    requirement = req_result.scalar_one_or_none()
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if not _requirement_finalized(requirement):
        raise HTTPException(
            status_code=400,
            detail="Requirement must be finalized before PRD generation",
        )

    prd = PRD(
        project_id=body.project_id,
        requirement_id=body.requirement_id,
        status=PRDStatus.draft,
        content_json=None,
        generated_by_id=current_user.id,
    )
    db.add(prd)
    await db.commit()
    await db.refresh(prd)

    task = generate_prd_task.delay(
        str(prd.id),
        model_provider=model_provider,
        model_id=model_id,
    )
    prd.generation_task_id = task.id
    await db.commit()

    return {
        "prd_id": str(prd.id),
        "task_id": task.id,
        "status": "generating",
    }


@router.get("/project/{project_id}", response_model=list[PRDEnrichedResponse])
async def list_project_prds(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> list[PRDEnrichedResponse]:
    """List all PRDs for a project ordered by version descending."""
    result = await db.execute(
        select(PRD)
        .options(selectinload(PRD.project))
        .where(PRD.project_id == project_id, PRD.deleted_at.is_(None))
        .order_by(PRD.version.desc())
    )
    prds = result.scalars().all()
    req_ids = [p.requirement_id for p in prds if p.requirement_id]
    requirements: dict[UUID, Requirement] = {}
    if req_ids:
        req_result = await db.execute(
            select(Requirement).where(Requirement.id.in_(req_ids))
        )
        requirements = {r.id: r for r in req_result.scalars().all()}

    return [
        _to_prd_response(
            prd,
            requirements.get(prd.requirement_id) if prd.requirement_id else None,
        )
        for prd in prds
    ]


@router.get("/{prd_id}", response_model=PRDEnrichedResponse)
async def get_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> PRDEnrichedResponse:
    """Return a PRD by id."""
    prd = await _load_prd(prd_id, db)
    requirement = None
    if prd.requirement_id:
        req_result = await db.execute(
            select(Requirement).where(Requirement.id == prd.requirement_id)
        )
        requirement = req_result.scalar_one_or_none()
    if prd.content_json:
        enriched = enrich_prd_content(prd.content_json)
        meta = dict(enriched.get("_meta") or {})
        if not meta.get("generated_at"):
            meta["generated_at"] = prd.created_at.isoformat()
        enriched["_meta"] = meta
        prd.content_json = enriched
    return _to_prd_response(prd, requirement)


@router.patch("/{prd_id}", response_model=PRDEnrichedResponse)
async def update_prd(
    prd_id: UUID,
    body: PRDUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> PRDEnrichedResponse:
    """Edit PRD content and save as a new version."""
    prd = await _load_prd(prd_id, db)
    if prd.status == PRDStatus.approved:
        raise HTTPException(status_code=400, detail="Cannot edit an approved PRD")

    await save_document_version(
        db,
        document_type=DocumentType.prd,
        document_id=prd.id,
        version=prd.version,
        content_json=prd.content_json or {},
        created_by_id=current_user.id,
        change_note=body.change_note,
    )

    new_version = prd.version + 1
    updated_content = append_version_history(
        body.content_json,
        version=new_version,
        trigger="edit",
        note=body.change_note or f"Edited by {current_user.full_name}",
    )
    prd.version = new_version
    prd.content_json = enrich_prd_content(updated_content)
    prd.status = PRDStatus.draft
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


@router.post("/{prd_id}/rewrite", response_model=PRDEnrichedResponse)
async def rewrite_prd(
    prd_id: UUID,
    body: PRDRewriteRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> PRDEnrichedResponse:
    """Rewrite PRD content based on PM instructions."""
    prd = await _load_prd(prd_id, db)
    if not prd.content_json:
        raise HTTPException(status_code=400, detail="PRD has no content to rewrite")
    instructions = body.instructions.strip()
    if not instructions:
        raise HTTPException(status_code=400, detail="Instructions are required")

    await save_document_version(
        db,
        document_type=DocumentType.prd,
        document_id=prd.id,
        version=prd.version,
        content_json=prd.content_json,
        created_by_id=current_user.id,
        change_note=f"Rewrite: {instructions[:200]}",
    )

    with model_override_scope(model_provider, model_id):
        rewritten = await rewrite_prd_ai(prd.content_json, instructions)

    new_version = prd.version + 1
    content = enrich_prd_content(rewritten.model_dump())
    content = append_version_history(
        content,
        version=new_version,
        trigger="rewrite",
        note=instructions[:500],
    )
    meta = dict(content.get("_meta") or {})
    meta["last_rewrite_instructions"] = instructions
    content["_meta"] = meta

    prd.version = new_version
    prd.content_json = content
    prd.status = PRDStatus.draft
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


@router.post("/{prd_id}/quality-check")
async def quality_check_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> dict[str, Any]:
    """Validate PRD completeness."""
    prd = await _load_prd(prd_id, db)
    if not prd.content_json:
        raise HTTPException(status_code=400, detail="PRD has no content")

    result = check_prd_quality(prd.content_json)
    content = enrich_prd_content(prd.content_json)
    meta = dict(content.get("_meta") or {})
    meta["quality_score"] = result.score
    meta["quality_checks"] = [c.model_dump() for c in result.checks]
    meta["quality_checked_at"] = datetime.now(timezone.utc).isoformat()
    content["_meta"] = meta
    prd.content_json = content
    await db.commit()

    return {
        "score": result.score,
        "checks": [c.model_dump() for c in result.checks],
        "stats": compute_prd_stats(content),
    }


@router.patch("/{prd_id}/confirm", response_model=PRDEnrichedResponse)
async def confirm_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> PRDEnrichedResponse:
    """Confirm and finalize PRD for SRS generation and client portal."""
    prd = await _load_prd(prd_id, db)
    if not prd.content_json:
        raise HTTPException(status_code=400, detail="PRD has no content to confirm")

    content = enrich_prd_content(prd.content_json)
    meta = dict(content.get("_meta") or {})
    meta["workflow_confirmed"] = True
    meta["workflow_finalized"] = True
    meta["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    meta["confirmed_by_name"] = current_user.full_name
    meta["confirmed_by_id"] = str(current_user.id)
    meta["client_approval_status"] = "pending"
    content["_meta"] = meta
    prd.content_json = content
    prd.status = PRDStatus.submitted
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


@router.post("/{prd_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_prd(
    prd_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> dict[str, str]:
    """Re-queue full PRD generation."""
    prd = await _load_prd(prd_id, db)
    prd.content_json = None
    prd.status = PRDStatus.draft
    prd.version = 1
    await db.commit()

    task = generate_prd_task.delay(
        str(prd.id),
        model_provider=model_provider,
        model_id=model_id,
    )
    prd.generation_task_id = task.id
    await db.commit()

    return {
        "prd_id": str(prd.id),
        "task_id": task.id,
        "status": "regenerating",
    }


@router.patch("/{prd_id}/submit", response_model=PRDEnrichedResponse)
async def submit_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> PRDEnrichedResponse:
    """Submit a PRD for client approval."""
    prd = await _load_prd(prd_id, db)
    if not prd.content_json:
        raise HTTPException(status_code=400, detail="PRD has no content to submit")
    if prd.status not in {PRDStatus.draft, PRDStatus.rejected}:
        raise HTTPException(status_code=400, detail="PRD cannot be submitted in current status")

    prd.status = PRDStatus.submitted
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


@router.patch("/{prd_id}/approve", response_model=PRDEnrichedResponse)
async def approve_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.client, UserRole.studio_owner, UserRole.project_manager)
    ),
) -> PRDEnrichedResponse:
    """Approve a submitted PRD (client or owner)."""
    prd = await _load_prd(prd_id, db)
    if prd.status != PRDStatus.submitted:
        raise HTTPException(status_code=400, detail="PRD must be submitted before approval")

    prd.status = PRDStatus.approved
    prd.approved_by_id = current_user.id
    prd.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


@router.delete("/{prd_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> None:
    """Soft-delete a PRD."""
    prd = await _load_prd(prd_id, db)
    prd.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/{prd_id}/versions")
async def list_prd_versions(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> list[dict]:
    """List version history for a PRD."""
    from app.models.document_version import DocumentVersion

    result = await db.execute(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == prd_id,
            DocumentVersion.document_type == DocumentType.prd,
            DocumentVersion.deleted_at.is_(None),
        )
        .order_by(DocumentVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "version": v.version,
            "created_at": v.created_at.isoformat(),
            "change_note": v.change_note,
            "created_by_id": str(v.created_by_id),
        }
        for v in versions
    ]
