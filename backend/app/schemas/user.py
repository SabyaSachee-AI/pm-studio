from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserBase(BaseModel):
    """Shared user fields for create and update operations."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.viewer
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(min_length=8, max_length=100)

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        """Strip leading and trailing whitespace from full_name."""
        if isinstance(value, str):
            return value.strip()
        return value


class UserUpdate(BaseModel):
    """Schema for partial user updates (PATCH)."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=100)


class UserResponse(BaseModel):
    """User data returned to API clients (no password fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    avatar_url: Optional[str] = None


class UserInDB(UserResponse):
    """Internal user representation including hashed password."""

    hashed_password: str
