"""Requirement upload and status API endpoints."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_screen_permission
from app.core.database import get_db
from app.models.requirement import Requirement, RequirementStatus
from app.models.user import User
from app.schemas.requirement import RequirementAnalysisSchema, RequirementResponse
from app.services.ai.model_override import model_override_scope
from app.services.ai.requirement_analysis import (
    FinalRequirementDraft,
    estimate_refined_cost,
    extract_document_text,
    rewrite_requirement_draft,
    synthesize_requirement_draft,
)
from app.services.requirement.cost import estimate_cost
from app.services.ai.job_progress import sync_progress_scope
from app.services.storage.service import get_local_path, save_upload
from app.workers.requirement_tasks import process_requirement_task

router = APIRouter(prefix="/requirements", tags=["Requirements"])


def _status_value(req: Requirement) -> str:
    if req.analysis_result and req.analysis_result.get("finalized"):
        return "finalized"
    return req.status.value


def _format_display_name(
    filename: str,
    when: datetime,
    *,
    finalized: bool = False,
) -> str:
    """Build a human-readable label: filename — date (and time for uploads)."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if finalized:
        stamp = when.astimezone(timezone.utc).strftime("%d %b %Y")
        return f"{filename} — finalized {stamp}"
    stamp = when.astimezone(timezone.utc).strftime("%d %b %Y, %I:%M %p")
    return f"{filename} — uploaded {stamp}"


def _finalized_timestamp(req: Requirement) -> datetime:
    """Resolve when a requirement was finalized."""
    analysis = req.analysis_result or {}
    raw = analysis.get("finalized_at")
    if isinstance(raw, str) and raw.strip():
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    if req.updated_at:
        return req.updated_at
    return req.created_at


def _get_display_name(req: Requirement) -> str:
    """Return stored display_name or derive from filename and lifecycle timestamps."""
    analysis = req.analysis_result or {}
    if analysis.get("finalized"):
        stored = analysis.get("display_name")
        if isinstance(stored, str) and "finalized" in stored:
            return stored
        return _format_display_name(
            req.original_filename,
            _finalized_timestamp(req),
            finalized=True,
        )
    if isinstance(analysis.get("display_name"), str):
        return analysis["display_name"]
    return _format_display_name(req.original_filename, req.created_at)


def _merge_analysis_metadata(
    existing: dict[str, Any] | None,
    updated: dict[str, Any],
) -> dict[str, Any]:
    """Preserve display_name when analysis_result is updated."""
    if existing and existing.get("display_name") and not updated.get("display_name"):
        updated["display_name"] = existing["display_name"]
    return updated


class RequirementEnrichedResponse(RequirementResponse):
    display_name: str
    uploaded_by_name: Optional[str] = None


def _to_response(req: Requirement) -> RequirementEnrichedResponse:
    uploaded_by_name = req.uploaded_by.full_name if req.uploaded_by else None
    return RequirementEnrichedResponse(
        id=req.id,
        project_id=req.project_id,
        original_filename=req.original_filename,
        status=_status_value(req),
        analysis_result=req.analysis_result,
        cost_estimate=req.cost_estimate_json,
        error_message=req.error_message,
        created_at=req.created_at,
        updated_at=req.updated_at,
        display_name=_get_display_name(req),
        uploaded_by_name=uploaded_by_name,
    )


class RequirementStatusPatch(BaseModel):
    status: str


class ReanalyzeBody(BaseModel):
    instructions: str


def _append_draft_version(
    analysis: dict[str, Any],
    draft: dict[str, Any],
    trigger: str,
) -> dict[str, Any]:
    """Store a new draft version in analysis_result metadata."""
    updated = dict(analysis)
    history = list(updated.get("draft_history", []))
    version = len(history) + 1
    history.append(
        {
            "version": version,
            "draft": draft,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger,
        }
    )
    updated["final_draft_json"] = draft
    updated["draft_history"] = history
    if trigger == "reanalyze":
        updated["reanalysis_count"] = updated.get("reanalysis_count", 0) + 1
    return updated


async def _load_requirement(
    requirement_id: UUID,
    db: AsyncSession,
) -> Requirement:
    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


def _resolve_feedback(req: Requirement) -> tuple[str, str]:
    """Return feedback filename and storage path from requirement or latest child."""
    if req.feedback_storage_path and req.feedback_filename:
        return req.feedback_filename, req.feedback_storage_path
    raise HTTPException(
        status_code=400,
        detail="No feedback document uploaded. Upload client feedback first.",
    )


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_requirement(
    project_id: UUID = Form(...),
    file: UploadFile = File(...),
    model_provider: str | None = None,
    model_id: str | None = None,
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

    display_name = _format_display_name(original_filename, req.created_at)
    req.analysis_result = {"display_name": display_name}
    await db.commit()

    task = process_requirement_task.delay(
        str(req.id), model_provider=model_provider, model_id=model_id
    )
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
    model_provider: str | None = None,
    model_id: str | None = None,
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

    task = process_requirement_task.delay(
        str(req.id), model_provider=model_provider, model_id=model_id
    )
    req.celery_task_id = task.id
    await db.commit()

    return {
        "requirement_id": str(req.id),
        "parent_requirement_id": str(parent.id),
        "task_id": task.id,
        "status": "merging",
    }


@router.patch("/{requirement_id}", response_model=RequirementEnrichedResponse)
async def patch_requirement(
    requirement_id: UUID,
    body: RequirementStatusPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> RequirementEnrichedResponse:
    """Update requirement status (supports finalization via analysis flag)."""
    result = await db.execute(
        select(Requirement)
        .options(selectinload(Requirement.uploaded_by))
        .where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    if body.status == "finalized":
        if not req.analysis_result:
            raise HTTPException(
                status_code=400,
                detail="Requirement must be analyzed before finalization",
            )
        now = datetime.now(timezone.utc)
        updated_analysis = dict(req.analysis_result)
        updated_analysis["finalized"] = True
        updated_analysis["finalized_at"] = now.isoformat()
        updated_analysis["finalized_by_name"] = current_user.full_name
        updated_analysis["display_name"] = _format_display_name(
            req.original_filename,
            now,
            finalized=True,
        )
        req.analysis_result = updated_analysis
    else:
        try:
            req.status = RequirementStatus(body.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid status") from exc

    await db.commit()
    await db.refresh(req)
    return _to_response(req)


@router.get("/{requirement_id}", response_model=RequirementEnrichedResponse)
async def get_requirement(
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "view")),
) -> RequirementEnrichedResponse:
    """Return a requirement record by id."""
    result = await db.execute(
        select(Requirement)
        .options(selectinload(Requirement.uploaded_by))
        .where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return _to_response(req)


@router.get("/project/{project_id}", response_model=list[RequirementEnrichedResponse])
async def list_project_requirements(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "view")),
) -> list[RequirementEnrichedResponse]:
    """List top-level requirements for a project, newest first."""
    result = await db.execute(
        select(Requirement)
        .options(selectinload(Requirement.uploaded_by))
        .where(
            Requirement.project_id == project_id,
            Requirement.parent_requirement_id.is_(None),
            Requirement.deleted_at.is_(None),
        )
        .order_by(Requirement.created_at.desc())
    )
    return [_to_response(req) for req in result.scalars().all()]


@router.delete("/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_requirement(
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> None:
    """Soft-delete a requirement document."""
    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    req.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/{requirement_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_requirement(
    requirement_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> dict[str, str]:
    """Re-run PDF extraction and AI analysis on an existing requirement."""
    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    req.status = RequirementStatus.uploaded
    req.analysis_result = None
    req.cost_estimate_json = None
    req.error_message = None
    req.extracted_text = None
    await db.commit()

    task = process_requirement_task.delay(
        str(req.id), model_provider=model_provider, model_id=model_id
    )
    return {
        "requirement_id": str(req.id),
        "task_id": task.id,
        "status": "regenerating",
    }


@router.post("/{requirement_id}/feedback-document", status_code=status.HTTP_200_OK)
async def upload_feedback_document(
    requirement_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> dict[str, str]:
    """Upload client feedback document onto the parent requirement."""
    req = await _load_requirement(requirement_id, db)
    if not req.analysis_result:
        raise HTTPException(status_code=400, detail="Requirement must be analyzed first")

    file_bytes = await file.read()
    feedback_filename = file.filename or "feedback.docx"
    extension = feedback_filename.rsplit(".", 1)[-1].lower()
    if extension not in {"docx", "pdf", "txt"}:
        raise HTTPException(
            status_code=400,
            detail="Feedback document must be .docx, .pdf, or .txt",
        )

    feedback_path = save_upload(file_bytes, feedback_filename)
    req.feedback_filename = feedback_filename
    req.feedback_storage_path = feedback_path

    updated_analysis = dict(req.analysis_result)
    updated_analysis["feedback_uploaded"] = True
    req.analysis_result = updated_analysis

    await db.commit()
    return {"status": "uploaded", "feedback_filename": feedback_filename}


@router.post("/{requirement_id}/synthesize")
async def synthesize_requirement(
    requirement_id: UUID,
    progress_id: str | None = None,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> dict[str, Any]:
    """Synthesize a final requirement draft from original text and client feedback."""
    req = await _load_requirement(requirement_id, db)
    if not req.extracted_text:
        raise HTTPException(status_code=400, detail="Original requirement text not available")
    if not req.analysis_result:
        raise HTTPException(status_code=400, detail="Requirement must be analyzed first")

    feedback_filename, feedback_path = _resolve_feedback(req)
    local_path = get_local_path(feedback_path)
    feedback_text = extract_document_text(local_path, feedback_filename)

    analysis_summary = str(req.analysis_result.get("summary", ""))
    with sync_progress_scope(progress_id), model_override_scope(model_provider, model_id):
        draft = await synthesize_requirement_draft(
            original_text=req.extracted_text,
            feedback_text=feedback_text,
            analysis_summary=analysis_summary,
        )
    draft_dict = draft.model_dump()

    updated_analysis = _append_draft_version(
        req.analysis_result,
        draft_dict,
        trigger="synthesize",
    )
    refined_cost = estimate_refined_cost(draft, req.cost_estimate_json)
    updated_analysis["refined_cost_estimate"] = refined_cost
    updated_analysis["feedback_text_snapshot"] = feedback_text[:20000]
    updated_analysis["original_text_snapshot"] = req.extracted_text[:20000]
    req.analysis_result = updated_analysis

    await db.commit()
    await db.refresh(req)

    history = updated_analysis.get("draft_history", [])
    version = history[-1]["version"] if history else 1
    return {
        "final_draft_json": draft_dict,
        "version": version,
        "reanalysis_count": updated_analysis.get("reanalysis_count", 0),
        "refined_cost_estimate": refined_cost,
        "original_text": req.extracted_text,
        "feedback_text": feedback_text,
    }


@router.post("/{requirement_id}/reanalyze")
async def reanalyze_requirement(
    requirement_id: UUID,
    body: ReanalyzeBody,
    progress_id: str | None = None,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "edit")),
) -> dict[str, Any]:
    """Rewrite the final draft based on PM revision instructions."""
    req = await _load_requirement(requirement_id, db)
    if not req.analysis_result or not req.analysis_result.get("final_draft_json"):
        raise HTTPException(status_code=400, detail="No final draft to reanalyze")

    instructions = body.instructions.strip()
    if not instructions:
        raise HTTPException(status_code=400, detail="Instructions are required")

    existing = FinalRequirementDraft.model_validate(req.analysis_result["final_draft_json"])
    with sync_progress_scope(progress_id), model_override_scope(model_provider, model_id):
        draft = await rewrite_requirement_draft(existing, instructions)
    draft_dict = draft.model_dump()

    updated_analysis = _append_draft_version(
        req.analysis_result,
        draft_dict,
        trigger="reanalyze",
    )
    refined_cost = estimate_refined_cost(draft, req.cost_estimate_json)
    updated_analysis["refined_cost_estimate"] = refined_cost
    updated_analysis["last_pm_instructions"] = instructions
    req.analysis_result = updated_analysis

    await db.commit()
    await db.refresh(req)

    history = updated_analysis.get("draft_history", [])
    version = history[-1]["version"] if history else 1
    return {
        "final_draft_json": draft_dict,
        "version": version,
        "reanalysis_count": updated_analysis.get("reanalysis_count", 0),
        "refined_cost_estimate": refined_cost,
    }


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
