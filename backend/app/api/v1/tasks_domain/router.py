"""PM task management API (Kanban)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_screen_permission
from app.core.database import get_db
from app.models.task import Task
from app.models.task_spec import TaskSpec, TaskSpecStatus
from app.models.user import User
from app.models.requirement import Requirement
from app.models.prd import PRD, PRDStatus
from sqlalchemy.orm import selectinload
from app.schemas.module import ModuleExtractRequest
from app.schemas.task import (
    KanbanBoard,
    TaskCreate,
    TaskResponse,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.project import Project
from app.models.srs import SRS, SRSStatus
from app.workers.module_tasks import extract_modules_task
from app.workers.orchestration_tasks import generate_orchestration_task
from app.services.task.bible_builder import build_project_bible
from app.services.task.coverage import (
    compute_coverage,
    compute_full_coverage,
    covered_fr_ids,
    extract_fr_ids,
    normalize_fr_id,
)
from app.services.prd.source import get_finalized_prd_body, prd_eligible_for_downstream
from app.services.task.service import (
    create_task,
    delete_task,
    get_kanban_board,
    get_task_by_id,
    update_task,
    update_task_status,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _to_task_response(task: Task, spec: TaskSpec | None = None) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        srs_id=task.srs_id,
        title=task.title,
        description=task.description,
        task_type=task.task_type.value,
        priority=task.priority.value,
        status=task.status.value,
        assigned_to_id=task.assigned_to_id,
        effort_hours=task.effort_hours,
        fr_references=task.fr_references,
        linked_fr=task.linked_fr,
        module_name=task.module_name,
        order_index=task.order_index,
        suggested_file=task.suggested_file,
        suggested_endpoint=task.suggested_endpoint,
        suggested_table=task.suggested_table,
        spec_id=spec.id if spec else None,
        spec_status=spec.status.value if spec else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post("/extract-modules", status_code=status.HTTP_202_ACCEPTED)
async def extract_modules(
    body: ModuleExtractRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Extract modules from approved PRD + SRS and seed Kanban tasks (uses finalized architecture when available)."""
    srs_result = await db.execute(
        select(SRS).where(
            SRS.id == body.srs_id,
            SRS.project_id == body.project_id,
            SRS.deleted_at.is_(None),
        )
    )
    srs = srs_result.scalar_one_or_none()
    if srs is None:
        raise HTTPException(status_code=404, detail="SRS not found")
    meta = (srs.content_json or {}).get("_meta") or {}
    srs_eligible = (
        srs.status == SRSStatus.approved
        or meta.get("workflow_finalized")
        or meta.get("workflow_confirmed")
        or srs.status == SRSStatus.submitted
    )
    if not srs_eligible:
        raise HTTPException(status_code=400, detail="SRS must be approved or finalized")

    if not srs.prd_id:
        raise HTTPException(
            status_code=400,
            detail="SRS must be linked to an approved PRD before task generation",
        )
    prd_result = await db.execute(
        select(PRD).where(PRD.id == srs.prd_id, PRD.deleted_at.is_(None))
    )
    prd = prd_result.scalar_one_or_none()
    if prd is None or not prd_eligible_for_downstream(prd):
        raise HTTPException(
            status_code=400,
            detail="An approved or finalized PRD is required before task generation",
        )

    arch_result = await db.execute(
        select(Architecture).where(
            Architecture.project_id == body.project_id,
            Architecture.status == ArchitectureStatus.finalized,
            Architecture.deleted_at.is_(None),
        )
    )
    arch = arch_result.scalars().first()
    arch_warning = None if arch else "No finalized architecture suite found — generating from PRD + SRS only"

    celery_task = extract_modules_task.delay(
        str(body.project_id),
        str(body.srs_id),
        str(arch.id) if arch else None,
        body.replace_existing,
        body.fill_gaps_only,
    )
    response: dict = {
        "project_id": str(body.project_id),
        "srs_id": str(body.srs_id),
        "task_id": celery_task.id,
        "status": "extracting",
    }
    if arch_warning:
        response["warning"] = arch_warning
    return response


@router.get("/project-bible/{project_id}")
async def get_project_bible(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Assemble the .cursorrules project bible from Architecture + SRS + Project data."""
    arch_result = await db.execute(
        select(Architecture)
        .where(
            Architecture.project_id == project_id,
            Architecture.status == ArchitectureStatus.finalized,
            Architecture.deleted_at.is_(None),
        )
        .order_by(Architecture.created_at.desc())
    )
    arch = arch_result.scalars().first()
    if arch is None:
        raise HTTPException(
            status_code=404,
            detail="No finalized architecture found for this project",
        )

    srs_result = await db.execute(
        select(SRS)
        .where(SRS.project_id == project_id, SRS.deleted_at.is_(None))
        .order_by(SRS.created_at.desc())
    )
    srs_candidates = srs_result.scalars().all()
    srs = None
    for candidate in srs_candidates:
        meta = (candidate.content_json or {}).get("_meta") or {}
        if (
            candidate.status == SRSStatus.approved
            or meta.get("workflow_finalized")
            or meta.get("workflow_confirmed")
        ):
            srs = candidate
            break
    if srs is None:
        raise HTTPException(
            status_code=400,
            detail="No approved SRS found for this project",
        )

    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    content = build_project_bible(project, srs, arch)
    return {"content": content, "project_name": project.name}


@router.get("/coverage/{project_id}")
async def get_task_coverage(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "view")),
) -> dict:
    """Return FR coverage report: which FRs have tasks vs which are missing."""
    # Get approved SRS for this project
    srs_result = await db.execute(
        select(SRS).where(
            SRS.project_id == project_id,
            SRS.deleted_at.is_(None),
        ).order_by(SRS.created_at.desc())
    )
    srs = srs_result.scalars().first()
    if not srs or not srs.content_json:
        return {"total": 0, "covered": 0, "missing": [], "has_tasks": False}

    all_frs = extract_fr_ids(srs.content_json)

    tasks_result = await db.execute(
        select(Task).where(Task.project_id == project_id, Task.deleted_at.is_(None))
    )
    tasks = tasks_result.scalars().all()

    covered = covered_fr_ids(tasks)
    missing = [f for f in all_frs if f not in covered]

    # Spec coverage
    task_ids = [t.id for t in tasks]
    spec_count = 0
    if task_ids:
        specs_result = await db.execute(
            select(TaskSpec).where(
                TaskSpec.task_id.in_(task_ids),
                TaskSpec.status == TaskSpecStatus.ready,
                TaskSpec.deleted_at.is_(None),
            )
        )
        spec_count = len(specs_result.scalars().all())

    done_count = sum(1 for t in tasks if str(t.status.value if hasattr(t.status, "value") else t.status) == "done")

    return {
        "total_frs": len(all_frs),
        "covered_frs": len([f for f in all_frs if f in covered]),
        "missing_frs": missing,
        "total_tasks": len(tasks),
        "tasks_with_spec": spec_count,
        "tasks_done": done_count,
        "has_tasks": len(tasks) > 0,
        "all_done": done_count == len(tasks) and len(tasks) > 0,
        "coverage_pct": round(len([f for f in all_frs if f in covered]) / max(len(all_frs), 1) * 100),
    }


@router.delete("/clear/{project_id}", status_code=status.HTTP_200_OK)
async def clear_project_tasks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict:
    """Soft-delete ALL tasks (and their specs) for a project."""
    from datetime import datetime, timezone as tz
    tasks_result = await db.execute(
        select(Task).where(Task.project_id == project_id, Task.deleted_at.is_(None))
    )
    tasks = tasks_result.scalars().all()
    if not tasks:
        return {"deleted_tasks": 0, "deleted_specs": 0}

    task_ids = [t.id for t in tasks]
    specs_result = await db.execute(
        select(TaskSpec).where(TaskSpec.task_id.in_(task_ids), TaskSpec.deleted_at.is_(None))
    )
    specs = specs_result.scalars().all()

    now = datetime.now(tz.utc)
    for spec in specs:
        spec.deleted_at = now
    for task in tasks:
        task.deleted_at = now
    await db.commit()

    return {"deleted_tasks": len(tasks), "deleted_specs": len(specs)}


@router.post("/orchestration/{project_id}", status_code=status.HTTP_202_ACCEPTED)
async def generate_orchestration(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict:
    """Generate the master project orchestration spec (Celery background task)."""
    celery_task = generate_orchestration_task.delay(str(project_id), str(current_user.id))
    return {
        "project_id": str(project_id),
        "task_id": celery_task.id,
        "status": "generating",
    }


@router.get("/kanban/{project_id}", response_model=KanbanBoard)
async def get_kanban(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "view")),
) -> KanbanBoard:
    """Return tasks grouped by status for a Kanban board."""
    board = await get_kanban_board(db, project_id)
    all_tasks: list[Task] = [t for col in board.values() for t in col]
    all_task_ids = [t.id for t in all_tasks]

    specs_by_task: dict = {}
    if all_task_ids:
        spec_result = await db.execute(
            select(TaskSpec).where(
                TaskSpec.task_id.in_(all_task_ids),
                TaskSpec.deleted_at.is_(None),
            )
        )
        for s in spec_result.scalars().all():
            specs_by_task[s.task_id] = s

    def _tr(t: Task) -> TaskResponse:
        return _to_task_response(t, specs_by_task.get(t.id))

    return KanbanBoard(
        backlog=[_tr(t) for t in board["backlog"]],
        assigned=[_tr(t) for t in board["assigned"]],
        in_progress=[_tr(t) for t in board["in_progress"]],
        in_review=[_tr(t) for t in board["in_review"]],
        done=[_tr(t) for t in board["done"]],
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task_endpoint(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> TaskResponse:
    """Create a new task."""
    task = await create_task(db, body)
    return _to_task_response(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_endpoint(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "view")),
) -> TaskResponse:
    """Return a task by id."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_task_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task_endpoint(
    task_id: UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> TaskResponse:
    """Partially update a task."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await update_task(db, task, body)
    return _to_task_response(updated)


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status_endpoint(
    task_id: UUID,
    body: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> TaskResponse:
    """Update task status and record the change in the audit log."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await update_task_status(
        db,
        task,
        body.status.value,
        current_user.id,
        body.note,
    )
    return _to_task_response(updated)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> None:
    """Soft-delete a task."""
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await delete_task(db, task)


class ResolveRequirementGapsBody(BaseModel):
    # Optional custom answers (one assumption line each). When omitted, the AI's
    # suggested auto_answers are used instead.
    answers: list[str] | None = None


@router.post("/resolve-requirement-gaps/{project_id}")
async def resolve_requirement_gaps(
    project_id: UUID,
    body: ResolveRequirementGapsBody | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict:
    """Resolve open requirement questions — safely, append-only.

    Adds answers to the SRS as `assumptions` (nothing existing is changed) and
    marks the questions resolved. Uses the user's custom `answers` when provided,
    otherwise the AI's suggested auto_answers.
    """
    from datetime import datetime, timezone as _tz  # noqa: PLC0415

    req = (await db.execute(
        select(Requirement)
        .where(Requirement.project_id == project_id, Requirement.deleted_at.is_(None))
        .order_by(Requirement.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    ar = dict((req.analysis_result if req else None) or {})
    unresolved = [g for g in (ar.get("gaps") or []) if not g.get("resolved")]
    if not unresolved:
        return {"applied": 0, "message": "No open requirement questions to resolve."}

    custom = [a.strip() for a in (body.answers if body and body.answers else []) if a and a.strip()]
    if custom:
        new_assumptions = custom
    else:
        new_assumptions = []
        for g in unresolved:
            q = (g.get("question") or g.get("description") or "").strip()
            a = (g.get("auto_answer") or "").strip()
            text = f"{q} → {a}" if q and a else (a or q)
            if text:
                new_assumptions.append(text)

    srs = (await db.execute(
        select(SRS)
        .where(SRS.project_id == project_id, SRS.deleted_at.is_(None))
        .order_by(SRS.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    applied_to: list[str] = []
    if srs is not None and srs.content_json is not None and new_assumptions:
        content = dict(srs.content_json)
        existing = list(content.get("assumptions") or [])
        seen = set(existing)
        for t in new_assumptions:
            if t not in seen:
                existing.append(t)
                seen.add(t)
        content["assumptions"] = existing
        log = list(content.get("_changelog") or [])
        log.append({
            "at": datetime.now(_tz.utc).isoformat(),
            "change": f"Added {len(new_assumptions)} assumption(s) from resolved requirement questions",
        })
        content["_changelog"] = log
        srs.content_json = content
        applied_to.append("SRS")

    for g in ar.get("gaps") or []:
        g["resolved"] = True
    if req is not None:
        req.analysis_result = ar

    await db.commit()
    return {
        "applied": len(new_assumptions),
        "docs": applied_to,
        "message": (
            f"Added {len(new_assumptions)} assumption(s) to the SRS and resolved "
            f"{len(unresolved)} question(s)."
            if applied_to else
            f"Resolved {len(unresolved)} question(s). (No SRS yet — assumptions will apply once an SRS exists.)"
        ),
    }


@router.get("/traceability/{project_id}")
async def get_project_traceability(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "view")),
) -> dict:
    """Return requirement ➔ PRD ➔ SRS ➔ task ➔ spec traceability tree."""
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch latest Requirement
    req_result = await db.execute(
        select(Requirement)
        .where(Requirement.project_id == project_id, Requirement.deleted_at.is_(None))
        .order_by(Requirement.created_at.desc())
        .limit(1)
    )
    requirement = req_result.scalar_one_or_none()

    # Fetch latest PRD
    prd_result = await db.execute(
        select(PRD)
        .where(PRD.project_id == project_id, PRD.deleted_at.is_(None))
        .order_by(PRD.created_at.desc())
        .limit(1)
    )
    prd = prd_result.scalar_one_or_none()

    # Fetch latest SRS
    srs_result = await db.execute(
        select(SRS)
        .where(SRS.project_id == project_id, SRS.deleted_at.is_(None))
        .order_by(SRS.created_at.desc())
        .limit(1)
    )
    srs = srs_result.scalar_one_or_none()

    # Fetch latest Architecture
    arch_result = await db.execute(
        select(Architecture)
        .where(Architecture.project_id == project_id, Architecture.deleted_at.is_(None))
        .order_by(Architecture.created_at.desc())
        .limit(1)
    )
    arch = arch_result.scalar_one_or_none()

    # Fetch all non-deleted tasks and their specs
    tasks_result = await db.execute(
        select(Task)
        .options(selectinload(Task.spec))
        .where(Task.project_id == project_id, Task.deleted_at.is_(None))
        .order_by(Task.order_index.asc())
    )
    tasks = tasks_result.scalars().all()

    requirement_data = None
    if requirement:
        requirement_data = {
            "id": str(requirement.id),
            "original_filename": requirement.original_filename,
            "status": requirement.status.value,
            # Hide gaps already resolved into the SRS (append-only auto-resolve).
            "gaps": [
                g for g in ((requirement.analysis_result or {}).get("gaps") or [])
                if not g.get("resolved")
            ],
        }

    prd_data = None
    if prd:
        prd_body = get_finalized_prd_body(prd.content_json) or (prd.content_json or {})
        raw_features = prd_body.get("features") or []
        normalized_features = []
        for feat in raw_features:
            feat_id = feat.get("id") or feat.get("feature_id") or ""
            normalized_features.append({
                "id":          feat_id,
                "title":       feat.get("title", ""),
                "description": feat.get("description", ""),
                "priority":    feat.get("priority", "medium"),
                "complexity":  feat.get("complexity"),
            })
        prd_data = {
            "id": str(prd.id),
            "status": prd.status.value,
            "version": prd.version,
            "features": normalized_features,
        }

    srs_data = None
    if srs:
        # Normalize each FR so that `id` is always the fr_number value.
        # Raw SRS JSON uses "fr_number" as the identifier; the frontend expects "id".
        raw_frs = (srs.content_json or {}).get("functional_requirements") or []
        normalized_frs = []
        for fr in raw_frs:
            fr_id = normalize_fr_id(fr.get("fr_number") or fr.get("id") or "")
            normalized_frs.append({
                "id":             fr_id,
                "fr_number":      fr_id,
                "title":          fr.get("title", ""),
                "description":    fr.get("description", ""),
                "priority":       fr.get("priority", "medium"),
                "inputs":         fr.get("inputs"),
                "processing":     fr.get("processing"),
                "outputs":        fr.get("outputs"),
                "linked_feature": fr.get("linked_feature"),
            })
        srs_data = {
            "id": str(srs.id),
            "status": srs.status.value,
            "version": srs.version,
            "functional_requirements": normalized_frs,
        }

    architecture_data = None
    if arch:
        architecture_data = {
            "id": str(arch.id),
            "status": arch.status.value,
            "version": arch.version,
            "docs": {
                "system_arch": {"status": arch.doc_system_arch_status or "pending", "has_content": arch.doc_system_arch is not None},
                "database": {"status": arch.doc_database_status or "pending", "has_content": arch.doc_database is not None},
                "api": {"status": arch.doc_api_status or "pending", "has_content": arch.doc_api is not None},
                "frontend": {"status": arch.doc_frontend_status or "pending", "has_content": arch.doc_frontend is not None},
                "security": {"status": arch.doc_security_status or "pending", "has_content": arch.doc_security is not None},
                "uiux": {"status": arch.doc_uiux_status or "pending", "has_content": arch.doc_uiux is not None},
            }
        }

    tasks_data = []
    for task in tasks:
        spec_data = None
        if task.spec:
            spec_data = {
                "id": str(task.spec.id),
                "status": task.spec.status.value,
                "content_json": task.spec.content_json,
            }
        tasks_data.append({
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "task_type": task.task_type.value,
            "priority": task.priority.value,
            "linked_fr": normalize_fr_id(task.linked_fr) if task.linked_fr else None,
            "fr_references": [normalize_fr_id(r) for r in (task.fr_references or [])],
            "module_name": task.module_name,
            "suggested_file": task.suggested_file,
            "suggested_endpoint": task.suggested_endpoint,
            "suggested_table": task.suggested_table,
            "spec": spec_data,
        })

    # Authoritative coverage — shared helper (normalized FR ids) so the
    # traceability matrix, the /coverage endpoint, and the gap-fill worker
    # always agree on which FRs are missing.
    coverage = compute_coverage(srs.content_json if srs else None, tasks)
    # Multi-dimensional completeness: FR + API endpoints + DB tables + NFRs.
    full_coverage = compute_full_coverage(srs.content_json if srs else None, arch, tasks)

    return {
        "project_id":   str(project_id),
        "project_name": project.name,
        "requirement":  requirement_data,
        "prd":          prd_data,
        "srs":          srs_data,
        "architecture": architecture_data,
        "tasks":        tasks_data,
        "coverage":     coverage,
        "full_coverage": full_coverage,
    }
