"""PRD API endpoints."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles, require_screen_permission
from app.core.database import get_db
from app.models.document_version import DocumentType
from app.models.prd import PRD, PRDStatus
from app.models.user import User, UserRole
from app.schemas.prd import PRDResponse
from app.services.document.versioning import save_document_version
from app.workers.prd_tasks import generate_prd_task

router = APIRouter(prefix="/prds", tags=["PRDs"])


class PRDGenerateRequest(BaseModel):
    project_id: UUID
    requirement_id: UUID


class PRDUpdateRequest(BaseModel):
    content_json: dict[str, Any]
    change_note: str | None = None


def _to_prd_response(prd: PRD) -> PRDResponse:
    return PRDResponse(
        id=prd.id,
        project_id=prd.project_id,
        requirement_id=prd.requirement_id,
        version=prd.version,
        status=prd.status.value,
        content_json=prd.content_json,
        generated_by_id=prd.generated_by_id,
        approved_by_id=prd.approved_by_id,
        approved_at=prd.approved_at,
        created_at=prd.created_at,
        updated_at=prd.updated_at,
    )


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_prd(
    body: PRDGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> dict[str, str]:
    """Queue PRD generation from an analyzed requirement."""
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

    task = generate_prd_task.delay(str(prd.id))
    prd.generation_task_id = task.id
    await db.commit()

    return {
        "prd_id": str(prd.id),
        "task_id": task.id,
        "status": "generating",
    }


@router.get("/project/{project_id}", response_model=list[PRDResponse])
async def list_project_prds(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> list[PRDResponse]:
    """List all PRDs for a project ordered by version descending."""
    result = await db.execute(
        select(PRD)
        .where(PRD.project_id == project_id, PRD.deleted_at.is_(None))
        .order_by(PRD.version.desc())
    )
    return [_to_prd_response(prd) for prd in result.scalars().all()]


@router.get("/{prd_id}", response_model=PRDResponse)
async def get_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> PRDResponse:
    """Return a PRD by id."""
    result = await db.execute(
        select(PRD).where(PRD.id == prd_id, PRD.deleted_at.is_(None))
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=404, detail="PRD not found")
    return _to_prd_response(prd)


@router.patch("/{prd_id}", response_model=PRDResponse)
async def update_prd(
    prd_id: UUID,
    body: PRDUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> PRDResponse:
    """Edit PRD content and save as a new version."""
    result = await db.execute(
        select(PRD).where(PRD.id == prd_id, PRD.deleted_at.is_(None))
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=404, detail="PRD not found")
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

    prd.version += 1
    prd.content_json = body.content_json
    prd.status = PRDStatus.draft
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


@router.patch("/{prd_id}/submit", response_model=PRDResponse)
async def submit_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "edit")),
) -> PRDResponse:
    """Submit a PRD for client approval."""
    result = await db.execute(
        select(PRD).where(PRD.id == prd_id, PRD.deleted_at.is_(None))
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=404, detail="PRD not found")
    if not prd.content_json:
        raise HTTPException(status_code=400, detail="PRD has no content to submit")
    if prd.status not in {PRDStatus.draft, PRDStatus.rejected}:
        raise HTTPException(status_code=400, detail="PRD cannot be submitted in current status")

    prd.status = PRDStatus.submitted
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


@router.patch("/{prd_id}/approve", response_model=PRDResponse)
async def approve_prd(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.client, UserRole.studio_owner, UserRole.project_manager)
    ),
) -> PRDResponse:
    """Approve a submitted PRD (client or owner)."""
    result = await db.execute(
        select(PRD).where(PRD.id == prd_id, PRD.deleted_at.is_(None))
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=404, detail="PRD not found")
    if prd.status != PRDStatus.submitted:
        raise HTTPException(status_code=400, detail="PRD must be submitted before approval")

    prd.status = PRDStatus.approved
    prd.approved_by_id = current_user.id
    prd.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(prd)
    return _to_prd_response(prd)


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
