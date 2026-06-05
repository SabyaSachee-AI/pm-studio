"""Shared FastAPI dependencies."""

from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.auth.service import decode_token, get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the authenticated user from a valid access token."""
    payload = decode_token(token)
    user = await get_user_by_id(db, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
