"""User administration business logic."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth.service import hash_password


async def list_users(db: AsyncSession) -> list[User]:
    """Return all non-deleted users."""
    result = await db.execute(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Return a non-deleted user by id."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    """Apply partial updates to a user."""
    if data.email is not None:
        user.email = str(data.email)
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.password is not None:
        user.hashed_password = hash_password(data.password)
    await db.flush()
    await db.refresh(user)
    return user


async def soft_delete_user(db: AsyncSession, user: User) -> None:
    """Soft-delete a user account."""
    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    await db.flush()


async def admin_create_user(db: AsyncSession, data: UserCreate) -> User:
    """Create a user from the admin panel."""
    from app.services.auth.service import create_user

    return await create_user(db, data)
