"""User database model and role definitions."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.dialects.postgresql import TIMESTAMP as TIMESTAMPTZ
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimeStampedModel


class UserRole(enum.Enum):
    """Application roles for access control."""

    studio_owner = "studio_owner"
    studio_admin = "studio_admin"
    project_manager = "project_manager"
    business_analyst = "business_analyst"
    architect = "architect"
    developer = "code_creator"
    qa_engineer = "qa_engineer"
    client = "client"
    viewer = "viewer"


class User(TimeStampedModel):
    """User account model."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda roles: [role.value for role in roles],
        ),
        nullable=False,
        default=UserRole.viewer,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ(timezone=True), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
