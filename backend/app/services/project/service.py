"""Project business logic and database operations."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from app.schemas.project import ProjectCreate, ProjectUpdate


async def get_projects(db: AsyncSession) -> list[Project]:
    """Return all non-deleted projects ordered by newest first."""
    result = await db.execute(
        select(Project)
        .where(Project.deleted_at.is_(None))
        .order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


async def get_projects_by_client(db: AsyncSession, client_id: UUID) -> list[Project]:
    """Return non-deleted projects for a specific client."""
    result = await db.execute(
        select(Project)
        .where(
            Project.client_id == client_id,
            Project.deleted_at.is_(None),
        )
        .order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


async def get_project_by_id(db: AsyncSession, project_id: UUID) -> Project | None:
    """Return a non-deleted project by id, or None."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_project(
    db: AsyncSession,
    data: ProjectCreate,
    created_by_id: UUID,
) -> Project:
    """Create and persist a new project."""
    project = Project(
        name=data.name,
        description=data.description,
        status=ProjectStatus(data.status.value),
        client_id=data.client_id,
        created_by_id=created_by_id,
        start_date=data.start_date,
        end_date=data.end_date,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def update_project(
    db: AsyncSession,
    project: Project,
    data: ProjectUpdate,
) -> Project:
    """Update only fields provided in the PATCH payload."""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value is not None:
            value = ProjectStatus(value.value)
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project: Project) -> None:
    """Soft-delete a project by setting deleted_at."""
    project.deleted_at = datetime.now(timezone.utc)
    await db.commit()
