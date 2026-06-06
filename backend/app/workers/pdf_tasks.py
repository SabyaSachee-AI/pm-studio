"""Celery tasks for PDF export."""

import logging
import os
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import SyncSessionLocal
from app.models.prd import PRD
from app.models.project import Project
from app.services.pdf.service import build_prd_html, render_html_to_pdf

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="documents.export_prd_pdf")
def export_prd_pdf_task(prd_id: str) -> dict[str, str]:
    """Export a PRD to PDF and store it locally."""
    db = SyncSessionLocal()
    try:
        prd = db.query(PRD).filter(PRD.id == UUID(prd_id)).first()
        if not prd or not prd.content_json:
            return {"error": "PRD not found"}

        project = db.query(Project).filter(Project.id == prd.project_id).first()
        project_name = project.name if project else "Unknown project"

        html = build_prd_html(prd.content_json, project_name, prd.version)
        pdf_bytes = render_html_to_pdf(html)

        export_dir = os.path.join(settings.upload_dir, "exports")
        os.makedirs(export_dir, exist_ok=True)
        output_path = os.path.join(export_dir, f"prd-{prd_id}-v{prd.version}.pdf")
        with open(output_path, "wb") as output_file:
            output_file.write(pdf_bytes)

        return {"path": output_path, "prd_id": prd_id, "version": str(prd.version)}
    except Exception as exc:
        logger.error("PRD PDF export failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()
