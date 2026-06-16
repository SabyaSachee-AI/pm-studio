"""Dashboard stats aggregation endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.architecture import Architecture
from app.models.client import Client
from app.models.organization import Organization
from app.models.prd import PRD
from app.models.project import Project, ProjectStatus
from app.models.requirement import Requirement
from app.models.srs import SRS
from app.models.task import Task, TaskStatus
from app.models.task_spec import TaskSpec, TaskSpecStatus
from app.models.user import User, UserRole
from app.services.ai.usage_tracker import PROVIDER_DAILY_LIMITS, get_daily_usage

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Aggregate PM Studio health metrics in a single request."""

    # ── Projects ──────────────────────────────────────────────────────────
    proj_rows = (
        await db.execute(
            select(Project.status, func.count().label("n"))
            .where(Project.deleted_at.is_(None))
            .group_by(Project.status)
        )
    ).all()
    project_by_status: dict[str, int] = {s.value: 0 for s in ProjectStatus}
    for row in proj_rows:
        project_by_status[row.status.value] = row.n
    total_projects = sum(project_by_status.values())

    # ── Clients ───────────────────────────────────────────────────────────
    total_clients = (
        await db.execute(
            select(func.count()).select_from(Client).where(Client.deleted_at.is_(None))
        )
    ).scalar_one()

    # ── Users ─────────────────────────────────────────────────────────────
    user_rows = (
        await db.execute(
            select(User.role, func.count().label("n"))
            .where(User.deleted_at.is_(None))
            .group_by(User.role)
        )
    ).all()
    users_by_role: dict[str, int] = {r.value: 0 for r in UserRole}
    for row in user_rows:
        role_val = row.role.value if hasattr(row.role, "value") else str(row.role)
        users_by_role[role_val] = row.n
    total_users = sum(users_by_role.values())

    # ── Pipeline (projects that have reached each stage) ──────────────────
    async def _distinct_projects(model: type, col: Any) -> int:
        result = await db.execute(
            select(func.count(func.distinct(col))).where(model.deleted_at.is_(None))
        )
        return result.scalar_one() or 0

    pipeline = {
        "has_requirement": await _distinct_projects(Requirement, Requirement.project_id),
        "has_prd":         await _distinct_projects(PRD,         PRD.project_id),
        "has_srs":         await _distinct_projects(SRS,         SRS.project_id),
        "has_architecture":await _distinct_projects(Architecture,Architecture.project_id),
    }

    # tasks & specs (cross-project totals)
    task_rows = (
        await db.execute(
            select(Task.status, func.count().label("n"))
            .where(Task.deleted_at.is_(None))
            .group_by(Task.status)
        )
    ).all()
    tasks_by_status: dict[str, int] = {s.value: 0 for s in TaskStatus}
    for row in task_rows:
        tasks_by_status[row.status] = row.n
    total_tasks = sum(tasks_by_status.values())

    # projects with at least one task / spec
    pipeline["has_tasks"] = (
        await db.execute(
            select(func.count(func.distinct(Task.project_id))).where(
                Task.deleted_at.is_(None)
            )
        )
    ).scalar_one() or 0

    spec_rows = (
        await db.execute(
            select(TaskSpec.status, func.count().label("n"))
            .where(TaskSpec.deleted_at.is_(None))
            .group_by(TaskSpec.status)
        )
    ).all()
    specs_by_status: dict[str, int] = {s.value: 0 for s in TaskSpecStatus}
    for row in spec_rows:
        specs_by_status[row.status] = row.n
    pipeline["has_specs"] = (
        await db.execute(
            select(func.count(func.distinct(TaskSpec.task_id))).where(
                TaskSpec.deleted_at.is_(None),
                TaskSpec.status == TaskSpecStatus.ready,
            )
        )
    ).scalar_one() or 0

    # ── Recent projects ───────────────────────────────────────────────────
    recent_result = await db.execute(
        select(Project)
        .where(Project.deleted_at.is_(None))
        .order_by(Project.updated_at.desc())
        .limit(6)
    )
    recent_projects = [
        {
            "id":         str(p.id),
            "name":       p.name,
            "status":     p.status.value,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in recent_result.scalars().all()
    ]

    # ── AI usage (today, from Redis) ──────────────────────────────────────
    org_result = await db.execute(select(Organization).limit(1))
    org = org_result.scalar_one_or_none()
    daily_usage: dict[str, Any] = {}
    if org:
        raw = await get_daily_usage(str(org.id))
        for provider, usage in raw.items():
            limits = PROVIDER_DAILY_LIMITS.get(provider, {})
            total_tokens = usage["tokens_in"] + usage["tokens_out"]
            daily_usage[provider] = {
                "label":            limits.get("label", provider),
                "tier":             limits.get("tier", "unknown"),
                "color":            limits.get("color", "gray"),
                "requests":         usage["requests"],
                "requests_limit":   limits.get("requests_per_day", 0),
                "tokens_in":        usage["tokens_in"],
                "tokens_out":       usage["tokens_out"],
                "tokens_total":     total_tokens,
                "tokens_limit":     limits.get("tokens_per_day", 0),
            }

    # total AI calls & tokens today (across all providers)
    total_ai_requests = sum(v["requests"] for v in daily_usage.values())
    total_tokens_in   = sum(v["tokens_in"] for v in daily_usage.values())
    total_tokens_out  = sum(v["tokens_out"] for v in daily_usage.values())

    return {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "projects": {
            "total":      total_projects,
            "by_status":  project_by_status,
        },
        "clients":  {"total": total_clients},
        "users": {
            "total":   total_users,
            "by_role": users_by_role,
        },
        "pipeline": pipeline,
        "tasks": {
            "total":        total_tasks,
            "by_status":    tasks_by_status,
            "specs_ready":  specs_by_status.get("ready", 0),
            "specs_total":  sum(specs_by_status.values()),
        },
        "ai": {
            "total_requests_today": total_ai_requests,
            "total_tokens_in":      total_tokens_in,
            "total_tokens_out":     total_tokens_out,
            "total_tokens":         total_tokens_in + total_tokens_out,
            "by_provider":          daily_usage,
        },
        "recent_projects": recent_projects,
    }
