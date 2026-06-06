"""Decision registry API endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_screen_permission
from app.core.database import get_db
from app.models.decision import Decision
from app.models.user import User
from app.schemas.decision import DecisionCreate, DecisionResponse, DecisionUpdate

router = APIRouter(prefix="/decisions", tags=["Decisions"])


@router.get("", response_model=list[DecisionResponse])
async def list_decisions(
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("decisions", "view")),
) -> list[DecisionResponse]:
    """List decisions, optionally filtered by project."""
    query = select(Decision).where(Decision.deleted_at.is_(None))
    if project_id:
        query = query.where(Decision.project_id == project_id)
    query = query.order_by(Decision.decided_at.desc())
    result = await db.execute(query)
    return [DecisionResponse.model_validate(d) for d in result.scalars().all()]


@router.post("", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
async def create_decision(
    body: DecisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("decisions", "edit")),
) -> DecisionResponse:
    """Record a new project decision."""
    decision = Decision(
        project_id=body.project_id,
        title=body.title,
        decision=body.decision,
        reason=body.reason,
        alternatives=body.alternatives,
        decided_by_id=current_user.id,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(decision)
    await db.commit()
    await db.refresh(decision)
    return DecisionResponse.model_validate(decision)


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("decisions", "view")),
) -> DecisionResponse:
    """Return a single decision."""
    result = await db.execute(
        select(Decision).where(
            Decision.id == decision_id, Decision.deleted_at.is_(None)
        )
    )
    decision = result.scalar_one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return DecisionResponse.model_validate(decision)


@router.patch("/{decision_id}", response_model=DecisionResponse)
async def update_decision(
    decision_id: UUID,
    body: DecisionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("decisions", "edit")),
) -> DecisionResponse:
    """Update a decision record."""
    result = await db.execute(
        select(Decision).where(
            Decision.id == decision_id, Decision.deleted_at.is_(None)
        )
    )
    decision = result.scalar_one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(decision, key, value)
    await db.commit()
    await db.refresh(decision)
    return DecisionResponse.model_validate(decision)


@router.delete("/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_decision(
    decision_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("decisions", "edit")),
) -> None:
    """Soft-delete a decision."""
    result = await db.execute(
        select(Decision).where(
            Decision.id == decision_id, Decision.deleted_at.is_(None)
        )
    )
    decision = result.scalar_one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    decision.deleted_at = datetime.now(timezone.utc)
    await db.commit()
