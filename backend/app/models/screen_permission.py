"""Screen-level role permissions."""

import enum

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimeStampedModel
from app.models.user import UserRole


class ScreenKey(str, enum.Enum):
    """Navigable application screens."""

    dashboard = "dashboard"
    clients = "clients"
    projects = "projects"
    requirements = "requirements"
    prds = "prds"
    srs = "srs"
    architecture = "architecture"
    tasks = "tasks"
    knowledge_base = "knowledge_base"
    decisions = "decisions"
    admin_users = "admin_users"


class ScreenPermission(TimeStampedModel):
    """Maps a role to view/edit access for a screen."""

    __tablename__ = "screen_permissions"
    __table_args__ = (
        UniqueConstraint("role", "screen_key", name="uq_screen_permissions_role_screen"),
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda roles: [role.value for role in roles],
            create_type=False,
        ),
        nullable=False,
    )
    screen_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    can_view: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<ScreenPermission role={self.role} screen={self.screen_key}>"
