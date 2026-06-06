"""User administration API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_screen_permission
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.auth.service import get_user_by_email
from app.services.user.service import (
    admin_create_user,
    get_user,
    list_users,
    soft_delete_user,
    update_user,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserResponse])
async def list_users_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("admin_users", "view")),
) -> list[UserResponse]:
    """List all users (admin only)."""
    users = await list_users(db)
    return [UserResponse.model_validate(user) for user in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("admin_users", "edit")),
) -> UserResponse:
    """Create a user and assign a role (admin only)."""
    existing = await get_user_by_email(db, str(data.email))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await admin_create_user(db, data)
    await db.commit()
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_endpoint(
    user_id: UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("admin_users", "edit")),
) -> UserResponse:
    """Update a user's role or status (admin only)."""
    user = await get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updated = await update_user(db, user, data)
    await db.commit()
    return UserResponse.model_validate(updated)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("admin_users", "edit")),
) -> None:
    """Soft-delete a user (admin only)."""
    user = await get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await soft_delete_user(db, user)
    await db.commit()
