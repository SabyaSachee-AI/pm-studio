"""Shared FastAPI dependencies."""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.screen_permission import ScreenPermission
from app.models.user import User, UserRole
from app.services.auth.service import decode_token, get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ADMIN_ROLES = {UserRole.studio_owner, UserRole.studio_admin}


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the authenticated user from a valid access token."""
    payload = decode_token(token)
    user = await get_user_by_id(db, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return user


async def _check_screen_permission(
    db: AsyncSession,
    user: User,
    screen_key: str,
    action: str,
) -> None:
    """Raise 403 when the user's role lacks the required screen permission."""
    if user.role in ADMIN_ROLES:
        return

    result = await db.execute(
        select(ScreenPermission).where(
            ScreenPermission.role == user.role,
            ScreenPermission.screen_key == screen_key,
            ScreenPermission.deleted_at.is_(None),
        )
    )
    permission = result.scalar_one_or_none()
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No permission for screen: {screen_key}",
        )

    allowed = permission.can_edit if action == "edit" else permission.can_view
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permission for {screen_key}",
        )


def require_screen_permission(screen_key: str, action: str = "view") -> Callable:
    """Dependency factory enforcing role-based screen access."""

    async def _dependency(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        await _check_screen_permission(db, current_user, screen_key, action)
        return current_user

    return _dependency


def require_roles(*roles: UserRole) -> Callable:
    """Dependency factory restricting access to specific roles."""

    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles and current_user.role not in ADMIN_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action",
            )
        return current_user

    return _dependency
