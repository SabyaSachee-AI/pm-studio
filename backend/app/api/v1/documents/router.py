"""Document export API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_screen_permission
from app.core.database import get_db
from app.models.prd import PRD
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.user import User
from app.services.pdf.service import (
    build_clarification_html,
    build_prd_html,
    render_html_to_pdf,
)
from app.workers.pdf_tasks import export_prd_pdf_task

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/requirements/{requirement_id}/clarification-pdf")
async def download_clarification_pdf(
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("requirements", "view")),
) -> Response:
    """Generate and download a clarification questions PDF."""
    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None),
        )
    )
    req = result.scalar_one_or_none()
    if req is None or not req.analysis_result:
        raise HTTPException(status_code=404, detail="Requirement analysis not found")

    project_result = await db.execute(
        select(Project).where(Project.id == req.project_id)
    )
    project = project_result.scalar_one_or_none()
    project_name = project.name if project else "Unknown project"

    analysis = req.analysis_result
    html = build_clarification_html(
        project_name=project_name,
        filename=req.original_filename,
        gaps=analysis.get("gaps", []),
        questions=analysis.get("technical_questions", []),
    )
    pdf_bytes = render_html_to_pdf(html)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="clarification-{requirement_id}.pdf"'
            ),
        },
    )


@router.post("/prd/{prd_id}/export-pdf", status_code=status.HTTP_202_ACCEPTED)
async def export_prd_pdf(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> dict[str, str]:
    """Queue PRD PDF export as a background task."""
    result = await db.execute(
        select(PRD).where(PRD.id == prd_id, PRD.deleted_at.is_(None))
    )
    prd = result.scalar_one_or_none()
    if prd is None or not prd.content_json:
        raise HTTPException(status_code=404, detail="PRD content not found")

    task = export_prd_pdf_task.delay(str(prd_id))
    return {"prd_id": str(prd_id), "task_id": task.id, "status": "exporting"}


@router.get("/prd/{prd_id}/export-pdf/sync")
async def export_prd_pdf_sync(
    prd_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("prds", "view")),
) -> Response:
    """Synchronously export a PRD as PDF (for immediate download)."""
    result = await db.execute(
        select(PRD).where(PRD.id == prd_id, PRD.deleted_at.is_(None))
    )
    prd = result.scalar_one_or_none()
    if prd is None or not prd.content_json:
        raise HTTPException(status_code=404, detail="PRD content not found")

    project_result = await db.execute(
        select(Project).where(Project.id == prd.project_id)
    )
    project = project_result.scalar_one_or_none()
    project_name = project.name if project else "Unknown project"

    html = build_prd_html(prd.content_json, project_name, prd.version)
    pdf_bytes = render_html_to_pdf(html)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="prd-{prd_id}-v{prd.version}.pdf"'
        },
    )
