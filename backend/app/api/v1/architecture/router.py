"""Architecture suite API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_screen_permission
from app.core.celery_app import celery_app
from app.core.database import get_db
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.srs import SRS, SRSStatus
from app.models.user import User
from app.schemas.architecture import (
    ArchitectureDocGenerateRequest,
    ArchitectureDocRegenerateRequest,
    ArchitectureDocSaveRequest,
    ArchitectureGenerateRequest,
    ArchitectureListItem,
    ArchitectureResponse,
)
from app.services.ai.architecture_service import ARCH_DOC_KEYS
from app.workers.architecture_tasks import (
    generate_architecture_doc_task,
    generate_architecture_task,
    regenerate_architecture_doc_task,
)

router = APIRouter(prefix="/architecture", tags=["Architecture"])

VALID_DOC_KEYS = {key for key, _ in ARCH_DOC_KEYS}


def _to_response(arch: Architecture) -> ArchitectureResponse:
    return ArchitectureResponse(
        id=arch.id,
        project_id=arch.project_id,
        srs_id=arch.srs_id,
        status=arch.status.value if isinstance(arch.status, ArchitectureStatus) else str(arch.status),
        version=arch.version,
        display_name=arch.display_name,
        created_by_id=arch.created_by_id,
        confirmed_by_id=arch.confirmed_by_id,
        confirmed_at=arch.confirmed_at,
        generation_task_id=arch.generation_task_id,
        doc_task_ids=arch.doc_task_ids,
        generation_progress=arch.generation_progress,
        doc_cancel_flags=arch.doc_cancel_flags,
        can_resume=bool(arch.can_resume),
        last_error=arch.last_error,
        resume_from=arch.resume_from,
        suite_canon=arch.suite_canon,
        consistency_report=arch.consistency_report,
        doc_system_arch=arch.doc_system_arch,
        doc_database=arch.doc_database,
        doc_api=arch.doc_api,
        doc_frontend=arch.doc_frontend,
        doc_security=arch.doc_security,
        doc_uiux=arch.doc_uiux,
        doc_system_arch_status=arch.doc_system_arch_status,
        doc_database_status=arch.doc_database_status,
        doc_api_status=arch.doc_api_status,
        doc_frontend_status=arch.doc_frontend_status,
        doc_security_status=arch.doc_security_status,
        doc_uiux_status=arch.doc_uiux_status,
        created_at=arch.created_at,
        updated_at=arch.updated_at,
    )


def _to_list_item(arch: Architecture) -> ArchitectureListItem:
    return ArchitectureListItem(
        id=arch.id,
        project_id=arch.project_id,
        srs_id=arch.srs_id,
        status=arch.status.value if isinstance(arch.status, ArchitectureStatus) else str(arch.status),
        version=arch.version,
        display_name=arch.display_name,
        created_at=arch.created_at,
        updated_at=arch.updated_at,
        doc_system_arch_status=arch.doc_system_arch_status,
        doc_database_status=arch.doc_database_status,
        doc_api_status=arch.doc_api_status,
        doc_frontend_status=arch.doc_frontend_status,
        doc_security_status=arch.doc_security_status,
        doc_uiux_status=arch.doc_uiux_status,
    )


async def _get_arch_or_404(db: AsyncSession, arch_id: UUID) -> Architecture:
    result = await db.execute(
        select(Architecture).where(Architecture.id == arch_id, Architecture.deleted_at.is_(None))
    )
    arch = result.scalar_one_or_none()
    if arch is None:
        raise HTTPException(status_code=404, detail="Architecture not found")
    return arch


def _srs_eligible(srs: SRS) -> bool:
    meta = (srs.content_json or {}).get("_meta") or {}
    return (
        srs.status == SRSStatus.approved
        or meta.get("workflow_finalized")
        or meta.get("workflow_confirmed")
        or srs.status == SRSStatus.submitted
    )


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_architecture(
    body: ArchitectureGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Create architecture suite and queue 6-document generation."""
    srs_result = await db.execute(
        select(SRS).where(SRS.id == body.srs_id, SRS.deleted_at.is_(None))
    )
    srs = srs_result.scalar_one_or_none()
    if srs is None:
        raise HTTPException(status_code=404, detail="SRS not found")
    if not _srs_eligible(srs):
        raise HTTPException(status_code=400, detail="SRS must be approved or finalized")

    arch = Architecture(
        project_id=body.project_id,
        srs_id=body.srs_id,
        status=ArchitectureStatus.draft,
        version=1,
        display_name=f"Architecture v1",
        created_by_id=current_user.id,
        can_resume=False,
    )
    for key, _ in ARCH_DOC_KEYS:
        setattr(arch, f"{key}_status", "pending")

    db.add(arch)
    await db.commit()
    await db.refresh(arch)

    task = generate_architecture_task.delay(str(arch.id), resume=False)
    arch.generation_task_id = task.id
    await db.commit()

    return {
        "architecture_id": str(arch.id),
        "task_id": task.id,
        "status": "generating",
    }


@router.get("/project/{project_id}", response_model=list[ArchitectureListItem])
async def list_project_architectures(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "view")),
) -> list[ArchitectureListItem]:
    result = await db.execute(
        select(Architecture)
        .where(Architecture.project_id == project_id, Architecture.deleted_at.is_(None))
        .order_by(Architecture.created_at.desc())
    )
    return [_to_list_item(a) for a in result.scalars().all()]


@router.get("/{arch_id}", response_model=ArchitectureResponse)
async def get_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "view")),
) -> ArchitectureResponse:
    arch = await _get_arch_or_404(db, arch_id)
    return _to_response(arch)


@router.patch("/{arch_id}/confirm", response_model=ArchitectureResponse)
async def confirm_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    arch = await _get_arch_or_404(db, arch_id)
    arch.status = ArchitectureStatus.confirmed
    arch.confirmed_by_id = current_user.id
    arch.confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.patch("/{arch_id}/finalize", response_model=ArchitectureResponse)
async def finalize_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    arch = await _get_arch_or_404(db, arch_id)
    arch.status = ArchitectureStatus.finalized
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.post("/{arch_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    arch = await _get_arch_or_404(db, arch_id)
    if not arch.can_resume:
        raise HTTPException(status_code=400, detail="Nothing to resume")
    task = generate_architecture_task.delay(str(arch.id), resume=True)
    arch.generation_task_id = task.id
    await db.commit()
    return {"architecture_id": str(arch.id), "task_id": task.id, "status": "generating"}


@router.post("/{arch_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    arch = await _get_arch_or_404(db, arch_id)
    for key, _ in ARCH_DOC_KEYS:
        setattr(arch, key, None)
        setattr(arch, f"{key}_status", "pending")
    arch.can_resume = False
    arch.last_error = None
    await db.commit()
    task = generate_architecture_task.delay(str(arch.id), resume=False)
    arch.generation_task_id = task.id
    await db.commit()
    return {"architecture_id": str(arch.id), "task_id": task.id, "status": "generating"}


@router.post("/{arch_id}/generate-doc", status_code=status.HTTP_202_ACCEPTED)
async def generate_single_doc(
    arch_id: UUID,
    body: ArchitectureDocGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    if body.doc_key not in VALID_DOC_KEYS:
        raise HTTPException(status_code=400, detail="Invalid doc_key")
    arch = await _get_arch_or_404(db, arch_id)
    task = generate_architecture_doc_task.delay(str(arch.id), body.doc_key)
    doc_task_ids = arch.doc_task_ids or {}
    doc_task_ids[body.doc_key] = task.id
    arch.doc_task_ids = doc_task_ids
    setattr(arch, f"{body.doc_key}_status", "generating")
    await db.commit()
    return {"task_id": task.id, "doc_key": body.doc_key, "status": "generating"}


@router.post("/{arch_id}/regenerate-doc", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_single_doc(
    arch_id: UUID,
    body: ArchitectureDocRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    if body.doc_key not in VALID_DOC_KEYS:
        raise HTTPException(status_code=400, detail="Invalid doc_key")
    arch = await _get_arch_or_404(db, arch_id)
    task = regenerate_architecture_doc_task.delay(
        str(arch.id), body.doc_key, body.instructions
    )
    doc_task_ids = arch.doc_task_ids or {}
    doc_task_ids[body.doc_key] = task.id
    arch.doc_task_ids = doc_task_ids
    setattr(arch, f"{body.doc_key}_status", "generating")
    await db.commit()
    return {"task_id": task.id, "doc_key": body.doc_key, "status": "generating"}


@router.post("/{arch_id}/cancel")
async def cancel_generation(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    arch = await _get_arch_or_404(db, arch_id)
    if arch.generation_task_id:
        celery_app.control.revoke(arch.generation_task_id, terminate=True)
    arch.generation_task_id = None
    await db.commit()
    return {"status": "cancelled"}


@router.post("/{arch_id}/cancel-doc/{doc_key}")
async def cancel_doc_generation(
    arch_id: UUID,
    doc_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    if doc_key not in VALID_DOC_KEYS:
        raise HTTPException(status_code=400, detail="Invalid doc_key")
    arch = await _get_arch_or_404(db, arch_id)
    flags = arch.doc_cancel_flags or {}
    flags[doc_key] = True
    arch.doc_cancel_flags = flags
    doc_task_ids = arch.doc_task_ids or {}
    task_id = doc_task_ids.get(doc_key)
    if task_id:
        celery_app.control.revoke(task_id, terminate=True)
    setattr(arch, f"{doc_key}_status", "cancelled")
    await db.commit()
    return {"status": "cancelled", "doc_key": doc_key}


@router.patch("/{arch_id}/doc/{doc_key}/save", response_model=ArchitectureResponse)
async def save_doc(
    arch_id: UUID,
    doc_key: str,
    body: ArchitectureDocSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    if doc_key not in VALID_DOC_KEYS:
        raise HTTPException(status_code=400, detail="Invalid doc_key")
    arch = await _get_arch_or_404(db, arch_id)
    setattr(arch, doc_key, body.content)
    setattr(arch, f"{doc_key}_status", "completed")
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.delete("/{arch_id}/doc/{doc_key}", response_model=ArchitectureResponse)
async def clear_doc(
    arch_id: UUID,
    doc_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    if doc_key not in VALID_DOC_KEYS:
        raise HTTPException(status_code=400, detail="Invalid doc_key")
    arch = await _get_arch_or_404(db, arch_id)
    setattr(arch, doc_key, None)
    setattr(arch, f"{doc_key}_status", "pending")
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.delete("/{arch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> None:
    arch = await _get_arch_or_404(db, arch_id)
    arch.soft_delete()
    await db.commit()
