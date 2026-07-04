"""Code-generation Build API."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_screen_permission
from app.core.celery_app import celery_app
from app.core.database import get_db
from app.models.architecture import Architecture, ArchitectureStatus
from app.models.build import Build, BuildStatus, GeneratedFile
from app.models.user import User
from app.models.task import Task
from app.models.task_spec import TaskSpec
from app.schemas.build import (
    BuildCreateRequest,
    BuildDetailResponse,
    BuildResponse,
    FileAiEditRequest,
    FileUpdateRequest,
    GeneratedFileListItem,
    GeneratedFileResponse,
    UiChecklistItem,
    UiChecklistResponse,
    UiTestSaveRequest,
)
from app.services.ai.model_override import model_override_scope
from app.services.build.service import ai_edit_file as svc_ai_edit_file
from app.workers.build_tasks import (
    deploy_build_task,
    generate_build_task,
    generate_task_code_task,
    generate_tests_task,
    polish_build_task,
    push_build_to_github_task,
    repair_build_task,
    scaffold_build_task,
)

router = APIRouter(prefix="/builds", tags=["Build"])


def _revoke_prev_task(build: Build) -> None:
    """Drop this build's previous queued task (if any) so stale/duplicate tasks
    never pile up. Only affects tasks not yet started — running work is untouched."""
    if build.generation_task_id:
        try:
            celery_app.control.revoke(build.generation_task_id)
        except Exception:  # noqa: BLE001
            pass


async def _load_build(build_id: UUID, db: AsyncSession) -> Build:
    result = await db.execute(
        select(Build).where(Build.id == build_id, Build.deleted_at.is_(None))
    )
    build = result.scalar_one_or_none()
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")
    return build


async def _file_count(build_id: UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(GeneratedFile.id)).where(
            GeneratedFile.build_id == build_id, GeneratedFile.deleted_at.is_(None)
        )
    )
    return int(result.scalar_one() or 0)


def _to_response(build: Build, file_count: int) -> BuildResponse:
    return BuildResponse(
        id=build.id,
        project_id=build.project_id,
        architecture_id=build.architecture_id,
        status=build.status.value,
        version=build.version,
        display_name=build.display_name,
        repo_url=build.repo_url,
        github_full_name=build.github_full_name,
        default_branch=build.default_branch,
        quality_score=build.quality_score,
        quality_report=build.quality_report,
        generation_progress=build.generation_progress,
        generation_task_id=build.generation_task_id,
        can_resume=build.can_resume,
        last_error=build.last_error,
        file_count=file_count,
        created_at=build.created_at,
        updated_at=build.updated_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BuildResponse)
async def create_build(
    body: BuildCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> BuildResponse:
    """Create a build for a project (defaults to its finalized architecture)."""
    arch_id = body.architecture_id
    if arch_id is None:
        result = await db.execute(
            select(Architecture)
            .where(
                Architecture.project_id == body.project_id,
                Architecture.deleted_at.is_(None),
            )
            .order_by(Architecture.created_at.desc())
        )
        arch = result.scalars().first()
        if arch is None:
            raise HTTPException(status_code=400, detail="No architecture found for this project")
        if arch.status != ArchitectureStatus.finalized:
            raise HTTPException(
                status_code=400,
                detail="Finalize the architecture suite before generating code",
            )
        arch_id = arch.id

    build = Build(
        project_id=body.project_id,
        architecture_id=arch_id,
        status=BuildStatus.draft,
        created_by_id=current_user.id,
    )
    db.add(build)
    await db.commit()
    await db.refresh(build)
    return _to_response(build, 0)


@router.get("", response_model=list[BuildResponse])
async def list_builds(
    project_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[BuildResponse]:
    query = (
        select(Build)
        .where(Build.deleted_at.is_(None))
        .order_by(Build.created_at.desc())
    )
    if project_id is not None:
        query = query.where(Build.project_id == project_id)
    rows = (await db.execute(query)).scalars().all()
    out: list[BuildResponse] = []
    for b in rows:
        out.append(_to_response(b, await _file_count(b.id, db)))
    return out


@router.get("/{build_id}", response_model=BuildDetailResponse)
async def get_build(
    build_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> BuildDetailResponse:
    build = await _load_build(build_id, db)
    from app.core.database import SyncSessionLocal  # noqa: PLC0415
    from app.services.build.auto_ci_progress import reconcile_auto_ci  # noqa: PLC0415

    sync_db = SyncSessionLocal()
    try:
        sync_build = sync_db.query(Build).filter(
            Build.id == build_id, Build.deleted_at.is_(None),
        ).first()
        if sync_build:
            reconcile_auto_ci(sync_db, sync_build)
    finally:
        sync_db.close()
    await db.refresh(build)
    files = (
        await db.execute(
            select(GeneratedFile)
            .where(GeneratedFile.build_id == build_id, GeneratedFile.deleted_at.is_(None))
            .order_by(GeneratedFile.path.asc())
        )
    ).scalars().all()
    base = _to_response(build, len(files))
    return BuildDetailResponse(
        **base.model_dump(),
        files=[GeneratedFileListItem.model_validate(f) for f in files],
    )


@router.get("/{build_id}/file/{file_id}", response_model=GeneratedFileResponse)
async def get_build_file(
    build_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> GeneratedFileResponse:
    result = await db.execute(
        select(GeneratedFile).where(
            GeneratedFile.id == file_id,
            GeneratedFile.build_id == build_id,
            GeneratedFile.deleted_at.is_(None),
        )
    )
    f = result.scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="File not found")
    return GeneratedFileResponse.model_validate(f)


@router.post("/{build_id}/scaffold", status_code=status.HTTP_202_ACCEPTED)
async def scaffold_build(
    build_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    build = await _load_build(build_id, db)
    task = scaffold_build_task.delay(str(build.id), model_provider=model_provider, model_id=model_id)
    build.status = BuildStatus.scaffolding
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    build.last_error = None
    build.generation_progress = {
        "phase": "scaffolding",
        "message": "Queued — starting scaffold…",
    }
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "scaffolding"}


@router.post("/{build_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_build(
    build_id: UUID,
    resume: bool = False,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    build = await _load_build(build_id, db)
    task = generate_build_task.delay(
        str(build.id), resume=resume, model_provider=model_provider, model_id=model_id
    )
    build.status = BuildStatus.generating
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    build.last_error = None
    gp = dict(build.generation_progress or {}) if resume else {}
    gp.update({"phase": "generating", "message": "Queued — starting code generation…"})
    build.generation_progress = gp
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "generating"}


@router.post("/{build_id}/generate-task/{task_id}", status_code=status.HTTP_202_ACCEPTED)
async def generate_task_code(
    build_id: UUID,
    task_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    build = await _load_build(build_id, db)
    task = generate_task_code_task.delay(
        str(build.id), str(task_id), model_provider=model_provider, model_id=model_id
    )
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "generating"}


@router.patch("/{build_id}/file/{file_id}", response_model=GeneratedFileResponse)
async def update_build_file(
    build_id: UUID,
    file_id: UUID,
    body: FileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> GeneratedFileResponse:
    result = await db.execute(
        select(GeneratedFile).where(
            GeneratedFile.id == file_id,
            GeneratedFile.build_id == build_id,
            GeneratedFile.deleted_at.is_(None),
        )
    )
    f = result.scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="File not found")
    f.content = body.content
    from app.models.build import FileStatus  # noqa: PLC0415
    f.status = FileStatus.edited
    await db.commit()
    await db.refresh(f)
    return GeneratedFileResponse.model_validate(f)


@router.post("/{build_id}/file/{file_id}/ai-edit", response_model=GeneratedFileResponse)
async def ai_edit_build_file(
    build_id: UUID,
    file_id: UUID,
    body: FileAiEditRequest,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> GeneratedFileResponse:
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction is required")
    # ai_edit_file uses a sync Session; run it against a fresh sync session.
    from app.core.database import SyncSessionLocal  # noqa: PLC0415
    sync_db = SyncSessionLocal()
    try:
        with model_override_scope(model_provider, model_id):
            result = await svc_ai_edit_file(build_id, file_id, body.instruction, sync_db)
    finally:
        sync_db.close()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    # Re-read via async session for the response
    row = (await db.execute(
        select(GeneratedFile).where(GeneratedFile.id == file_id)
    )).scalar_one()
    return GeneratedFileResponse.model_validate(row)


@router.post("/{build_id}/push", status_code=status.HTTP_202_ACCEPTED)
async def push_build(
    build_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Push the generated codebase to GitHub in one commit (triggers CI)."""
    build = await _load_build(build_id, db)
    if await _file_count(build.id, db) == 0:
        raise HTTPException(status_code=400, detail="No files to push — generate code first")
    task = push_build_to_github_task.delay(str(build.id))
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "pushing"}


@router.get("/{build_id}/qa")
async def get_build_qa(
    build_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    """Poll the latest GitHub Actions (CI) run and update the quality report."""
    build = await _load_build(build_id, db)
    if not build.github_full_name:
        raise HTTPException(status_code=400, detail="Build not pushed to GitHub yet")
    from app.core.database import SyncSessionLocal  # noqa: PLC0415
    from app.services.build.auto_ci_progress import reconcile_auto_ci  # noqa: PLC0415
    from app.services.build.github import get_qa_status  # noqa: PLC0415
    sync_db = SyncSessionLocal()
    try:
        sync_build = sync_db.query(Build).filter(
            Build.id == build_id, Build.deleted_at.is_(None),
        ).first()
        if sync_build:
            reconcile_auto_ci(sync_db, sync_build)
        return await get_qa_status(build_id, sync_db)
    finally:
        sync_db.close()


@router.post("/{build_id}/sync-from-github")
async def sync_from_github(
    build_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict:
    """Pull the repo's latest commit back into PM Studio (GitHub wins).

    Use after editing code locally and `git push`-ing — mirrors the repo into the
    build's files: overwrites changed files, adds new ones, removes deleted ones.
    """
    build = await _load_build(build_id, db)
    if not build.github_full_name:
        raise HTTPException(status_code=400, detail="Build not pushed to GitHub yet")
    from app.core.database import SyncSessionLocal  # noqa: PLC0415
    from app.services.build.github import pull_build_from_github  # noqa: PLC0415
    sync_db = SyncSessionLocal()
    try:
        result = await pull_build_from_github(build_id, sync_db)
    finally:
        sync_db.close()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{build_id}/mark-ready", response_model=BuildResponse)
async def mark_build_ready(
    build_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> BuildResponse:
    """Manual override: force the build to `ready`.

    Escape hatch for when CI passed (or was verified locally) but PM Studio
    cannot read the run — e.g. the GitHub token lacks Actions: Read. A build
    must never get permanently stuck on `qa`.
    """
    build = await _load_build(build_id, db)
    report = dict(build.quality_report or {})
    report["manual_override"] = {
        "status": "ready",
        "by": str(current_user.id),
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": "Marked ready manually (CI verified or skipped)",
    }
    build.quality_report = report
    build.status = BuildStatus.ready
    await db.commit()
    await db.refresh(build)
    return _to_response(build, await _file_count(build.id, db))


@router.post("/{build_id}/polish", status_code=status.HTTP_202_ACCEPTED)
async def polish_build_endpoint(
    build_id: UUID,
    scope: str = Query("critical", pattern="^(critical|all)$"),
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Quality polish pass. scope=critical|all. Uses the chosen model, else the
    code_polish fallback chain for the configured tier."""
    build = await _load_build(build_id, db)
    if await _file_count(build.id, db) == 0:
        raise HTTPException(status_code=400, detail="Generate code before polishing")
    task = polish_build_task.delay(str(build.id), scope, model_provider, model_id)
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "polishing"}


@router.post("/{build_id}/generate-tests", status_code=status.HTTP_202_ACCEPTED)
async def generate_tests(
    build_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Generate automated tests from acceptance criteria (CI then runs them)."""
    build = await _load_build(build_id, db)
    if await _file_count(build.id, db) == 0:
        raise HTTPException(status_code=400, detail="Generate code before tests")
    task = generate_tests_task.delay(str(build.id), model_provider=model_provider, model_id=model_id)
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "generating_tests"}


@router.post("/{build_id}/repair", status_code=status.HTTP_202_ACCEPTED)
async def repair_build(
    build_id: UUID,
    model_provider: str | None = None,
    model_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """AI-repair the build from its failed CI logs, then re-push (triggers CI)."""
    build = await _load_build(build_id, db)
    if not build.github_full_name:
        raise HTTPException(status_code=400, detail="Build not pushed to GitHub yet")
    task = repair_build_task.delay(str(build.id), model_provider=model_provider, model_id=model_id)
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "repairing"}


@router.get("/{build_id}/ui-checklist", response_model=UiChecklistResponse)
async def get_ui_checklist(
    build_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> UiChecklistResponse:
    """Build the human UI-test checklist from each task's acceptance criteria."""
    build = await _load_build(build_id, db)
    rows = (await db.execute(
        select(Task)
        .options(selectinload(Task.spec))
        .where(Task.project_id == build.project_id, Task.deleted_at.is_(None))
        .order_by(Task.order_index.asc())
    )).scalars().all()

    items: list[UiChecklistItem] = []
    for t in rows:
        spec: TaskSpec | None = t.spec
        criteria = []
        if spec and spec.content_json:
            raw = spec.content_json.get("acceptance_criteria")
            if isinstance(raw, list):
                criteria = [str(c) for c in raw if str(c).strip()]
        for i, crit in enumerate(criteria):
            items.append(UiChecklistItem(key=f"{t.id}:{i}", task_title=t.title, criterion=crit))

    repo = build.repo_url
    name = (build.github_full_name or "").split("/")[-1] or "project"
    clone = f"git clone {repo} && cd {name}" if repo else "Push to GitHub first to get a clone URL"
    return UiChecklistResponse(
        repo_url=repo,
        clone_cmd=clone,
        run_cmd="docker compose up --build",
        items=items,
    )


@router.post("/{build_id}/ui-test", response_model=BuildResponse)
async def save_ui_test(
    build_id: UUID,
    body: UiTestSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> BuildResponse:
    """Persist the human UI-test results + sign-off into the quality report."""
    build = await _load_build(build_id, db)
    report = dict(build.quality_report or {})
    passed = sum(1 for r in body.results if r.status == "pass")
    failed = sum(1 for r in body.results if r.status == "fail")
    total = len(body.results)
    report["ui_test"] = {
        "results": [r.model_dump() for r in body.results],
        "passed": passed,
        "failed": failed,
        "total": total,
        "signed_off": body.signed_off,
        "signed_by": str(current_user.id),
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }
    build.quality_report = report
    await db.commit()
    await db.refresh(build)
    return _to_response(build, await _file_count(build.id, db))


@router.post("/{build_id}/deploy", status_code=status.HTTP_202_ACCEPTED)
async def deploy_build_endpoint(
    build_id: UUID,
    port: int | None = Query(None, ge=1, le=65535),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> dict[str, str]:
    """Deploy the build to the VPS via its GitHub Actions deploy workflow.

    `port` = the unique host port for THIS app on the shared VPS (default 3000).
    """
    build = await _load_build(build_id, db)
    if not build.github_full_name:
        raise HTTPException(status_code=400, detail="Push the build to GitHub first")
    task = deploy_build_task.delay(str(build.id), port=port)
    _revoke_prev_task(build)
    build.generation_task_id = task.id
    await db.commit()
    return {"build_id": str(build.id), "task_id": task.id, "status": "deploying"}


@router.delete("/{build_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_build(
    build_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("tasks", "edit")),
) -> None:
    build = await _load_build(build_id, db)
    build.deleted_at = datetime.now(timezone.utc)
    await db.commit()
