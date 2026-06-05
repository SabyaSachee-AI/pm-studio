"""Requirement upload and status API endpoints."""

import os
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.requirement import Requirement, RequirementStatus
from app.models.user import User
from app.schemas.requirement import RequirementResponse
from app.workers.requirement_tasks import process_requirement_task

router = APIRouter(prefix="/requirements", tags=["Requirements"])


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_requirement(
    project_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Upload a requirements document and queue background processing."""
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    original_filename = file.filename or "unknown.pdf"
    file_id = str(uuid.uuid4())
    file_ext = os.path.splitext(original_filename)[1] or ".pdf"
    storage_path = os.path.join(upload_dir, f"{file_id}{file_ext}")

    with open(storage_path, "wb") as output_file:
        output_file.write(await file.read())

    req = Requirement(
        project_id=project_id,
        original_filename=original_filename,
        storage_path=storage_path,
        file_size_bytes=os.path.getsize(storage_path),
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


@router.get("/{requirement_id}", response_model=RequirementResponse)
async def get_requirement(
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement not found",
        )

    return RequirementResponse(
        id=req.id,
        project_id=req.project_id,
        original_filename=req.original_filename,
        status=req.status.value,
        analysis_result=req.analysis_result,
        error_message=req.error_message,
        created_at=req.created_at,
    )
