"""Authentication API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES
from app.core.config import get_settings
from app.core.database import get_db
from app.models.screen_permission import ScreenPermission
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.auth.service import (
    authenticate_user,
    create_access_token,
    create_token_pair,
    create_user,
    decode_token,
    get_user_by_email,
    get_user_by_id,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

settings = get_settings()

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def _cookie_secure() -> bool:
    """Use Secure cookies outside local development (HTTPS)."""
    return settings.environment != "development"


def _set_auth_cookies(response: JSONResponse, tokens: dict[str, str]) -> None:
    """Attach HttpOnly access and refresh token cookies to a response."""
    secure = _cookie_secure()
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=tokens["access_token"],
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=tokens["refresh_token"],
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


def _clear_auth_cookies(response: JSONResponse) -> None:
    """Remove auth cookies server-side."""
    secure = _cookie_secure()
    response.delete_cookie(key=ACCESS_COOKIE, path="/", secure=secure, samesite="lax")
    response.delete_cookie(key=REFRESH_COOKIE, path="/", secure=secure, samesite="lax")


async def _user_from_access_cookie(request: Request, db: AsyncSession) -> User:
    """Resolve the current user from the HttpOnly access token cookie."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(token)
    user = await get_user_by_id(db, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return user


class RefreshTokenRequest(BaseModel):
    """Request body for refreshing an access token (legacy; prefer cookie)."""

    refresh_token: str | None = None


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user account."""
    existing_user = await get_user_by_email(db, str(user_data.email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = await create_user(db, user_data)
    await db.commit()
    return UserResponse.model_validate(user)


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Authenticate a user and set HttpOnly auth cookies."""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await db.commit()
    tokens = create_token_pair(user)
    response = JSONResponse(content={"token_type": tokens["token_type"]})
    _set_auth_cookies(response, tokens)
    return response


@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Issue a new access token cookie from the HttpOnly refresh cookie."""
    refresh_value = request.cookies.get(REFRESH_COOKIE)
    if not refresh_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(
            refresh_value,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise credentials_exception from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user = await get_user_by_id(db, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    token_payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
    }
    access_token = create_access_token(token_payload)
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_value,
        "token_type": "bearer",
    }
    response = JSONResponse(content={"token_type": "bearer"})
    _set_auth_cookies(response, tokens)
    return response


class ScreenPermissionResponse(BaseModel):
    screen_key: str
    can_view: bool
    can_edit: bool


@router.get("/screens", response_model=list[ScreenPermissionResponse])
async def get_my_screens(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[ScreenPermissionResponse]:
    """Return screen permissions for the current user's role."""
    current_user = await _user_from_access_cookie(request, db)

    if current_user.role in ADMIN_ROLES:
        from app.models.screen_permission import ScreenKey

        return [
            ScreenPermissionResponse(screen_key=s.value, can_view=True, can_edit=True)
            for s in ScreenKey
        ]

    result = await db.execute(
        select(ScreenPermission).where(
            ScreenPermission.role == current_user.role,
            ScreenPermission.deleted_at.is_(None),
        )
    )
    return [
        ScreenPermissionResponse(
            screen_key=p.screen_key,
            can_view=p.can_view,
            can_edit=p.can_edit,
        )
        for p in result.scalars().all()
        if p.can_view
    ]


@router.get("/me", response_model=UserResponse)
async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Return the currently authenticated user."""
    current_user = await _user_from_access_cookie(request, db)
    return UserResponse.model_validate(current_user)


@router.post("/logout")
async def logout() -> JSONResponse:
    """Clear auth cookies server-side."""
    response = JSONResponse(content={"detail": "Successfully logged out"})
    _clear_auth_cookies(response)
    return response
