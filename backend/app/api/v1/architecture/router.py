"""Architecture Suite API endpoints."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_screen_permission
from app.core.database import get_db
from app.models.architecture import (
    Architecture,
    ArchitectureStatus,
    DOC_FIELDS,
    DOC_STATUS_FIELDS,
    DocGenerationStatus,
)
from app.models.prd import PRD, PRDStatus
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.models.user import User
from app.schemas.architecture import ArchitectureListItem, ArchitectureResponse
from app.services.ai.architecture_service import (
    edit_architecture_doc_ai,
    polish_architecture_docs_for_pdf,
)
from app.services.ai.model_override import model_override_scope
from app.workers.architecture_tasks import (
    consolidate_architecture_task,
    generate_architecture_doc_task,
    generate_architecture_task,
    regenerate_architecture_doc_task,
)

router = APIRouter(prefix="/architecture", tags=["Architecture"])


class ArchitectureGenerateRequest(BaseModel):
    project_id: UUID
    srs_id: UUID


class ArchitectureUpdateDocRequest(BaseModel):
    doc_key: str
    content: dict[str, Any]


class ArchitectureAiEditRequest(BaseModel):
    instruction: str
    current_content: dict[str, Any]


class ArchitecturePolishExportRequest(BaseModel):
    mode: str  # "full" | "section"
    doc_key: str | None = None


def _prd_eligible(prd: PRD) -> bool:
    if not prd.content_json:
        return False
    if prd.status == PRDStatus.approved:
        return True
    meta = (prd.content_json or {}).get("_meta") or {}
    if meta.get("workflow_finalized") or meta.get("workflow_confirmed"):
        return True
    return prd.status == PRDStatus.submitted


def _srs_eligible(srs: SRS) -> bool:
    meta = (srs.content_json or {}).get("_meta") or {}
    if meta.get("workflow_finalized"):
        return True
    if srs.status == SRSStatus.approved:
        return True
    if meta.get("workflow_confirmed"):
        return True
    return srs.status == SRSStatus.submitted


def _arch_display_name(arch: Architecture, project: Project | None) -> str:
    if arch.display_name:
        return arch.display_name
    project_name = project.name if project else "Project"
    timestamp = arch.created_at.strftime("%d %b %Y, %I:%M %p")
    return f"{project_name} Architecture — v{arch.version} — {timestamp}"


def _srs_display_name(srs: SRS, project: Project | None) -> str:
    project_name = project.name if project else "Project"
    timestamp = srs.created_at.strftime("%d %b %Y, %I:%M %p")
    return f"{project_name} SRS — v{srs.version} — {timestamp}"


def _count_generated(arch: Architecture) -> int:
    count = 0
    for field in DOC_FIELDS:
        if getattr(arch, field):
            count += 1
    return count


def _to_list_item(
    arch: Architecture,
    srs: SRS | None = None,
    project: Project | None = None,
) -> ArchitectureListItem:
    return ArchitectureListItem(
        id=arch.id,
        project_id=arch.project_id,
        srs_id=arch.srs_id,
        status=arch.status.value,
        version=arch.version,
        display_name=_arch_display_name(arch, project),
        created_at=arch.created_at,
        source_srs_display_name=_srs_display_name(srs, project) if srs else None,
        docs_generated=_count_generated(arch),
        docs_total=6,
    )


def _to_response(arch: Architecture) -> ArchitectureResponse:
    return ArchitectureResponse(
        id=arch.id,
        project_id=arch.project_id,
        srs_id=arch.srs_id,
        status=arch.status.value,
        version=arch.version,
        display_name=arch.display_name,
        created_by_id=arch.created_by_id,
        confirmed_by_id=arch.confirmed_by_id,
        confirmed_at=arch.confirmed_at,
        generation_task_id=arch.generation_task_id,
        doc_task_ids=arch.doc_task_ids or {},
        generation_progress=arch.generation_progress,
        can_resume=arch.can_resume,
        last_error=arch.last_error,
        resume_from=arch.resume_from,
        suite_canon=arch.suite_canon,
        consistency_report=arch.consistency_report,
        created_at=arch.created_at,
        updated_at=arch.updated_at,
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
    )


async def _load_architecture(arch_id: UUID, db: AsyncSession) -> Architecture:
    result = await db.execute(
        select(Architecture)
        .options(
            selectinload(Architecture.srs),
            selectinload(Architecture.project),
            selectinload(Architecture.created_by),
        )
        .where(Architecture.id == arch_id, Architecture.deleted_at.is_(None))
    )
    arch = result.scalar_one_or_none()
    if arch is None:
        raise HTTPException(status_code=404, detail="Architecture not found")
    return arch


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_architecture(
    body: ArchitectureGenerateRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Queue generation of all 6 architecture documents from finalized SRS."""
    srs_result = await db.execute(
        select(SRS)
        .options(selectinload(SRS.project))
        .where(SRS.id == body.srs_id, SRS.deleted_at.is_(None))
    )
    srs = srs_result.scalar_one_or_none()
    if srs is None:
        raise HTTPException(status_code=404, detail="SRS not found")
    if not srs.content_json:
        raise HTTPException(status_code=400, detail="SRS has no content")
    if not _srs_eligible(srs):
        raise HTTPException(
            status_code=400,
            detail="SRS must be finalized or approved before architecture generation",
        )

    if not srs.prd_id:
        raise HTTPException(
            status_code=400,
            detail="SRS must be linked to a PRD before architecture generation",
        )
    prd_result = await db.execute(
        select(PRD).where(PRD.id == srs.prd_id, PRD.deleted_at.is_(None))
    )
    prd = prd_result.scalar_one_or_none()
    if prd is None or not _prd_eligible(prd):
        raise HTTPException(
            status_code=400,
            detail="An approved PRD is required before architecture generation",
        )

    arch = Architecture(
        project_id=body.project_id,
        srs_id=body.srs_id,
        status=ArchitectureStatus.draft,
        created_by_id=current_user.id,
    )
    db.add(arch)
    await db.commit()
    await db.refresh(arch)
    arch.display_name = _arch_display_name(arch, srs.project)
    await db.commit()
    await db.refresh(arch)

    task = generate_architecture_task.delay(
        str(arch.id),
        resume=False,
        model_provider=model_provider,
        model_id=model_id,
    )
    arch.generation_task_id = task.id
    await db.commit()

    return {
        "architecture_id": str(arch.id),
        "task_id": task.id,
        "status": "generating",
    }


@router.get("", response_model=list[ArchitectureListItem])
async def list_architectures(
    project_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[ArchitectureListItem]:
    query = (
        select(Architecture)
        .options(selectinload(Architecture.srs), selectinload(Architecture.project))
        .where(Architecture.deleted_at.is_(None))
        .order_by(Architecture.created_at.desc())
    )
    if project_id is not None:
        query = query.where(Architecture.project_id == project_id)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [_to_list_item(a, a.srs, a.project) for a in rows]


@router.get("/{arch_id}", response_model=ArchitectureResponse)
async def get_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> ArchitectureResponse:
    arch = await _load_architecture(arch_id, db)
    return _to_response(arch)


@router.patch("/{arch_id}/confirm", response_model=ArchitectureResponse)
async def confirm_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    arch = await _load_architecture(arch_id, db)
    if not any(getattr(arch, f) for f in DOC_FIELDS):
        raise HTTPException(status_code=400, detail="No architecture documents generated yet")
    arch.status = ArchitectureStatus.confirmed
    arch.confirmed_by_id = current_user.id
    arch.confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.delete("/{arch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> None:
    """Soft-delete an architecture suite."""
    arch = await _load_architecture(arch_id, db)
    arch.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/{arch_id}/consolidate", status_code=status.HTTP_202_ACCEPTED)
async def consolidate_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Align all 6 docs to suite canon (deterministic fixes + consistency scoring)."""
    arch = await _load_architecture(arch_id, db)
    incomplete = any(
        getattr(arch, f"{f}_status") not in {"completed", "generated", "saved"}
        for f in DOC_FIELDS
    )
    if incomplete:
        raise HTTPException(
            status_code=400,
            detail="All 6 documents must be generated before consolidating",
        )

    task = consolidate_architecture_task.delay(str(arch.id))
    arch.generation_task_id = task.id
    arch.generation_progress = {
        "phase": "consolidating",
        "message": "Aligning suite to shared canon…",
    }
    await db.commit()

    return {
        "architecture_id": str(arch.id),
        "task_id": task.id,
        "status": "consolidating",
    }


@router.post("/{arch_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_architecture(
    arch_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Clear all architecture documents and re-generate the full suite."""
    arch = await _load_architecture(arch_id, db)
    for field in DOC_FIELDS:
        setattr(arch, field, None)
    for status_field in DOC_STATUS_FIELDS:
        setattr(arch, status_field, DocGenerationStatus.pending.value)
    arch.status = ArchitectureStatus.draft
    arch.confirmed_by_id = None
    arch.confirmed_at = None
    arch.can_resume = False
    arch.last_error = None
    arch.resume_from = None
    arch.doc_cancel_flags = {}
    await db.commit()

    task = generate_architecture_task.delay(
        str(arch.id), resume=False,
        model_provider=model_provider, model_id=model_id,
    )
    arch.generation_task_id = task.id
    await db.commit()

    return {
        "architecture_id": str(arch.id),
        "task_id": task.id,
        "status": "regenerating",
    }


@router.patch("/{arch_id}/finalize", response_model=ArchitectureResponse)
async def finalize_architecture(
    arch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    arch = await _load_architecture(arch_id, db)
    if arch.status != ArchitectureStatus.confirmed:
        raise HTTPException(status_code=400, detail="Architecture must be confirmed first")
    arch.status = ArchitectureStatus.finalized
    arch.confirmed_by_id = current_user.id
    arch.confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.post("/{arch_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_architecture(
    arch_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Resume architecture generation from the first incomplete document."""
    arch = await _load_architecture(arch_id, db)
    incomplete = any(
        getattr(arch, f"{f}_status") not in {"completed", "generated"}
        for f in DOC_FIELDS
    )
    if not incomplete:
        raise HTTPException(status_code=400, detail="All documents already generated")

    task = generate_architecture_task.delay(
        str(arch.id), resume=True,
        model_provider=model_provider, model_id=model_id,
    )
    arch.generation_task_id = task.id
    arch.can_resume = False
    await db.commit()

    return {
        "architecture_id": str(arch.id),
        "task_id": task.id,
        "status": "resuming",
    }


@router.post("/{arch_id}/polish-export")
async def polish_architecture_export(
    arch_id: UUID,
    body: ArchitecturePolishExportRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """AI-polish architecture docs into concise formal prose before PDF export."""
    arch = await _load_architecture(arch_id, db)
    mode = body.mode.lower().strip()
    if mode not in {"full", "section"}:
        raise HTTPException(status_code=400, detail="mode must be full or section")
    if mode == "section":
        if not body.doc_key or body.doc_key not in DOC_FIELDS:
            raise HTTPException(status_code=400, detail="doc_key required for section export")
        keys = [body.doc_key]
    else:
        keys = list(DOC_FIELDS)

    documents: dict[str, dict[str, Any]] = {}
    for key in keys:
        content = getattr(arch, key)
        if content:
            documents[key] = content

    if not documents:
        raise HTTPException(status_code=400, detail="No generated documents to export")

    with model_override_scope(model_provider, model_id):
        polished = await polish_architecture_docs_for_pdf(documents)
    return {"documents": polished}


@router.patch("/{arch_id}/doc/{doc_key}/ai-edit")
async def ai_edit_architecture_doc(
    arch_id: UUID,
    doc_key: str,
    body: ArchitectureAiEditRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, Any]:
    """Apply PM free-text instructions to one architecture doc via AI."""
    if doc_key not in DOC_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid document key")
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction is required")

    await _load_architecture(arch_id, db)

    with model_override_scope(model_provider, model_id):
        corrected = await edit_architecture_doc_ai(
            doc_key,
            body.current_content,
            body.instruction,
        )
    return {"corrected_content": corrected}


@router.delete("/{arch_id}/doc/{doc_key}", response_model=ArchitectureResponse)
async def delete_architecture_doc(
    arch_id: UUID,
    doc_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    """Clear one architecture document (soft content reset, status pending)."""
    if doc_key not in DOC_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid document key")
    arch = await _load_architecture(arch_id, db)
    setattr(arch, doc_key, None)
    status_key = f"{doc_key}_status"
    if hasattr(arch, status_key):
        setattr(arch, status_key, DocGenerationStatus.pending.value)
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.patch("/{arch_id}/doc", response_model=ArchitectureResponse)
async def update_architecture_doc(
    arch_id: UUID,
    body: ArchitectureUpdateDocRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> ArchitectureResponse:
    if body.doc_key not in DOC_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid document key")
    arch = await _load_architecture(arch_id, db)
    setattr(arch, body.doc_key, body.content)
    status_key = f"{body.doc_key}_status"
    if hasattr(arch, status_key):
        setattr(arch, status_key, "generated")
    await db.commit()
    await db.refresh(arch)
    return _to_response(arch)


@router.post("/{arch_id}/generate-doc/{doc_key}", status_code=status.HTTP_202_ACCEPTED)
async def generate_architecture_doc(
    arch_id: UUID,
    doc_key: str,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Generate a single pending architecture document."""
    if doc_key not in DOC_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid document key")
    arch = await _load_architecture(arch_id, db)
    task = generate_architecture_doc_task.delay(
        str(arch.id),
        doc_key,
        model_provider=model_provider,
        model_id=model_id,
    )
    task_ids = dict(arch.doc_task_ids or {})
    task_ids[doc_key] = task.id
    arch.doc_task_ids = task_ids
    setattr(arch, f"{doc_key}_status", DocGenerationStatus.generating.value)
    arch.generation_task_id = task.id
    await db.commit()
    return {
        "architecture_id": str(arch.id),
        "task_id": task.id,
        "status": "generating",
    }


@router.post("/{arch_id}/cancel-doc/{doc_key}", status_code=status.HTTP_202_ACCEPTED)
async def cancel_architecture_doc(
    arch_id: UUID,
    doc_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Request cancellation of an in-flight single-document generation."""
    if doc_key not in DOC_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid document key")
    arch = await _load_architecture(arch_id, db)
    flags = dict(arch.doc_cancel_flags or {})
    flags[doc_key] = True
    arch.doc_cancel_flags = flags
    await db.commit()
    return {
        "architecture_id": str(arch.id),
        "doc_key": doc_key,
        "status": "cancelling",
    }


@router.post("/{arch_id}/regenerate-doc/{doc_key}", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_architecture_doc(
    arch_id: UUID,
    doc_key: str,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("architecture", "edit")),
) -> dict[str, str]:
    """Regenerate a single architecture document."""
    if doc_key not in DOC_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid document key")
    arch = await _load_architecture(arch_id, db)
    task = regenerate_architecture_doc_task.delay(
        str(arch.id),
        doc_key,
        "",
        model_provider=model_provider,
        model_id=model_id,
    )
    task_ids = dict(arch.doc_task_ids or {})
    task_ids[doc_key] = task.id
    arch.doc_task_ids = task_ids
    setattr(arch, f"{doc_key}_status", DocGenerationStatus.generating.value)
    arch.generation_task_id = task.id
    await db.commit()
    return {
        "architecture_id": str(arch.id),
        "task_id": task.id,
        "status": "generating",
    }
