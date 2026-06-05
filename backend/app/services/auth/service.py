"""Authentication business logic: passwords, JWT tokens, and user persistence."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserResponse

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True when the plain password matches the stored hash."""
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    """Hash a plain-text password for storage."""
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(data: dict) -> str:
    """Create a signed JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    """Decode and validate an access token.

    Raises:
        HTTPException: When the token is invalid, expired, or a refresh token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise credentials_exception from exc

    if payload.get("type") == "refresh":
        raise credentials_exception

    return payload


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Return an active, non-deleted user matching the email, or None."""
    result = await db.execute(
        select(User).where(
            User.email == email,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Return a non-deleted user matching the id, or None."""
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
    """Create a new user with a hashed password."""
    user = User(
        email=str(user_data.email),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=user_data.is_active,
        hashed_password=hash_password(user_data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Authenticate credentials and update last login on success."""
    user = await get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(user)
    return user


def create_token_pair(user: User) -> dict[str, str]:
    """Build an access/refresh token pair for the given user."""
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
    }
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
    }
