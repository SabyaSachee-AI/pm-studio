"""Organization database model."""

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class Organization(TimeStampedModel):
    """Top-level studio organization."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    free_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    screen_model_overrides: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default="{}"
    )
    ai_provider_configs: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default="{}"
    )
    ai_tier: Mapped[str] = mapped_column(String(20), default="premium", nullable=False)

    clients: Mapped[list["Client"]] = relationship("Client", back_populates="organization")

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name={self.name}>"
