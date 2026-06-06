"""Requirement upload and status API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_screen_permission
from app.core.database import get_db
from app.models.requirement import Requirement, RequirementStatus
from app.models.user import User
from app.schemas.requirement import RequirementAnalysisSchema, RequirementResponse
from app.services.requirement.cost import estimate_cost
from app.services.storage.service import save_upload
from app.workers.requirement_tasks import process_requirement_task

router = APIRouter(prefix="/requirements", tags=["Requirements"])


def _to_response(req: Requirement) -> RequirementResponse:
    return RequirementResponse(
        id=req.id,
        project_id=req.project_id,
        original_filename=req.original_filename,
        status=req.status.value,
        analysis_result=req.analysis_result,
        cost_estimate=req.cost_estimate_json,
        error_message=req.error_message,
        created_at=req.created_at,
    )


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_requirement(
    project_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> dict[str, str]:
    """Upload a requirements document and queue background processing."""
    file_bytes = await file.read()
    original_filename = file.filename or "unknown.pdf"
    storage_path = save_upload(file_bytes, original_filename)

    req = Requirement(
        project_id=project_id,
        original_filename=original_filename,
        storage_path=storage_path,
        file_size_bytes=len(file_bytes),
        status=RequirementStatus.uploaded,
        uploaded_by_id=current_user.id,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    task = process_requirement_task.delay(str(req.id))
    req.celery_task_id = task.id
    await db.commit()

    return {
        "requirement_id": str(req.id),
        "task_id": task.id,
        "status": RequirementStatus.uploaded.value,
    }


@router.post("/{requirement_id}/feedback-upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_feedback(
    requirement_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> dict[str, str]:
    """Upload client feedback and re-queue merged analysis."""
    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    file_bytes = await file.read()
    feedback_filename = file.filename or "feedback.pdf"
    feedback_path = save_upload(file_bytes, feedback_filename)

    req = Requirement(
        project_id=parent.project_id,
        parent_requirement_id=parent.id,
        original_filename=parent.original_filename,
        storage_path=parent.storage_path,
        feedback_filename=feedback_filename,
        feedback_storage_path=feedback_path,
        file_size_bytes=len(file_bytes),
        status=RequirementStatus.uploaded,
        uploaded_by_id=current_user.id,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    task = process_requirement_task.delay(str(req.id))
    req.celery_task_id = task.id
    await db.commit()

    return {
        "requirement_id": str(req.id),
        "parent_requirement_id": str(parent.id),
        "task_id": task.id,
        "status": "merging",
    }


@router.get("/{requirement_id}", response_model=RequirementResponse)
async def get_requirement(
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "view")),
) -> RequirementResponse:
    """Return a requirement record by id."""
    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return _to_response(req)


@router.get("/project/{project_id}", response_model=list[RequirementResponse])
async def list_project_requirements(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "view")),
) -> list[RequirementResponse]:
    """List all requirements for a project."""
    result = await db.execute(
        select(Requirement)
        .where(
            Requirement.project_id == project_id,
            Requirement.deleted_at.is_(None),
        )
        .order_by(Requirement.created_at.desc())
    )
    return [_to_response(req) for req in result.scalars().all()]


@router.get("/{requirement_id}/cost-estimate")
async def get_cost_estimate(
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "view")),
) -> dict:
    """Return preliminary cost estimate for an analyzed requirement."""
    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if req.cost_estimate_json:
        return req.cost_estimate_json
    if not req.analysis_result:
        raise HTTPException(status_code=400, detail="Requirement not yet analyzed")
    analysis = RequirementAnalysisSchema.model_validate(req.analysis_result)
    return estimate_cost(analysis)
