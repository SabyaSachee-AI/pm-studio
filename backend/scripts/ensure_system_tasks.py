"""One-off script: create pinned system Kanban tasks for a project."""

import sys
from uuid import UUID

from app.core.database import SyncSessionLocal
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.prd import PRD
from app.models.project import Project
from app.models.srs import SRS
from app.models.task import Task
from app.workers.module_tasks import _build_arch_content, _ensure_system_tasks, SYSTEM_TASK_ORDERS


def main(project_id: str) -> None:
    db = SyncSessionLocal()
    try:
        pid = UUID(project_id)
        project = db.query(Project).filter(Project.id == pid, Project.deleted_at.is_(None)).first()
        if not project:
            print(f"ERROR: project {project_id} not found")
            sys.exit(1)

        srs = (
            db.query(SRS)
            .filter(SRS.project_id == pid, SRS.deleted_at.is_(None))
            .order_by(SRS.created_at.desc())
            .first()
        )
        if not srs:
            print("ERROR: no SRS found")
            sys.exit(1)

        prd = db.query(PRD).filter(PRD.id == srs.prd_id).first()
        prd_content = prd.content_json if prd and prd.content_json else {}

        arch = (
            db.query(Architecture)
            .filter(
                Architecture.project_id == pid,
                Architecture.status == ArchitectureStatus.finalized,
                Architecture.deleted_at.is_(None),
            )
            .order_by(Architecture.created_at.desc())
            .first()
        )
        arch_content = _build_arch_content(arch) if arch else None

        tasks = (
            db.query(Task)
            .filter(Task.project_id == pid, Task.deleted_at.is_(None))
            .all()
        )
        regular_titles = [t.title for t in tasks if t.order_index not in SYSTEM_TASK_ORDERS]

        created = _ensure_system_tasks(
            db,
            pid,
            srs.id,
            project.name,
            prd_content,
            srs.content_json or {},
            arch_content,
            regular_titles,
        )
        print(f"OK: created {len(created)} system task(s): {created}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/ensure_system_tasks.py <project_id>")
        sys.exit(1)
    main(sys.argv[1])
