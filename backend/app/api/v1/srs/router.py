"""SRS API endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles, require_screen_permission
from app.core.database import get_db
from app.models.prd import PRD, PRDStatus
from app.models.srs import SRS, SRSStatus
from app.models.user import User, UserRole
from app.schemas.srs import SRSResponse
from app.workers.srs_tasks import generate_srs_task

router = APIRouter(prefix="/srs", tags=["SRS"])


class SRSGenerateRequest(BaseModel):
    project_id: UUID
    prd_id: UUID


def _to_srs_response(srs: SRS) -> SRSResponse:
    return SRSResponse(
        id=srs.id,
        project_id=srs.project_id,
        prd_id=srs.prd_id,
        version=srs.version,
        status=srs.status.value,
        content_json=srs.content_json,
        generated_by_id=srs.generated_by_id,
        approved_by_id=srs.approved_by_id,
        approved_at=srs.approved_at,
        created_at=srs.created_at,
        updated_at=srs.updated_at,
    )


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_srs(
    body: SRSGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> dict[str, str]:
    """Queue SRS generation from an approved PRD."""
    prd_result = await db.execute(
        select(PRD).where(PRD.id == body.prd_id, PRD.deleted_at.is_(None))
    )
    prd = prd_result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=404, detail="PRD not found")
    if prd.status != PRDStatus.approved:
        raise HTTPException(status_code=400, detail="PRD must be approved before SRS generation")

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

    task = generate_srs_task.delay(str(srs.id))
    srs.generation_task_id = task.id
    await db.commit()

    return {
        "srs_id": str(srs.id),
        "task_id": task.id,
        "status": "generating",
    }


@router.get("/project/{project_id}", response_model=list[SRSResponse])
async def list_project_srs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "view")),
) -> list[SRSResponse]:
    """List all SRS documents for a project."""
    result = await db.execute(
        select(SRS)
        .where(SRS.project_id == project_id, SRS.deleted_at.is_(None))
        .order_by(SRS.version.desc())
    )
    return [_to_srs_response(srs) for srs in result.scalars().all()]


@router.get("/{srs_id}", response_model=SRSResponse)
async def get_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "view")),
) -> SRSResponse:
    """Return an SRS document by id."""
    result = await db.execute(
        select(SRS).where(SRS.id == srs_id, SRS.deleted_at.is_(None))
    )
    srs = result.scalar_one_or_none()
    if srs is None:
        raise HTTPException(status_code=404, detail="SRS not found")
    return _to_srs_response(srs)


@router.patch("/{srs_id}/submit", response_model=SRSResponse)
async def submit_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("srs", "edit")),
) -> SRSResponse:
    """Submit an SRS for architect approval."""
    result = await db.execute(
        select(SRS).where(SRS.id == srs_id, SRS.deleted_at.is_(None))
    )
    srs = result.scalar_one_or_none()
    if srs is None:
        raise HTTPException(status_code=404, detail="SRS not found")
    if not srs.content_json:
        raise HTTPException(status_code=400, detail="SRS has no content to submit")
    if srs.status not in {SRSStatus.draft, SRSStatus.rejected}:
        raise HTTPException(status_code=400, detail="SRS cannot be submitted in current status")

    srs.status = SRSStatus.submitted
    await db.commit()
    await db.refresh(srs)
    return _to_srs_response(srs)


@router.patch("/{srs_id}/approve", response_model=SRSResponse)
async def approve_srs(
    srs_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.architect, UserRole.studio_owner)
    ),
) -> SRSResponse:
    """Approve a submitted SRS (architect or owner)."""
    result = await db.execute(
        select(SRS).where(SRS.id == srs_id, SRS.deleted_at.is_(None))
    )
    srs = result.scalar_one_or_none()
    if srs is None:
        raise HTTPException(status_code=404, detail="SRS not found")
    if srs.status != SRSStatus.submitted:
        raise HTTPException(status_code=400, detail="SRS must be submitted before approval")

    srs.status = SRSStatus.approved
    srs.approved_by_id = current_user.id
    srs.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(srs)
    return _to_srs_response(srs)
