"""add ai_tier column and new provider API keys support

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-06-10 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ai_tier column — "free" | "low_cost" | "premium"
    # Back-fill from existing free_mode_enabled flag:
    #   free_mode_enabled=True  → ai_tier="free"
    #   free_mode_enabled=False → ai_tier="premium"
    op.add_column(
        "organizations",
        sa.Column(
            "ai_tier",
            sa.String(20),
            nullable=False,
            server_default="premium",
        ),
    )
    # Back-fill existing rows
    op.execute(
        "UPDATE organizations SET ai_tier = 'free' WHERE free_mode_enabled = TRUE"
    )
    op.execute(
        "UPDATE organizations SET ai_tier = 'premium' WHERE free_mode_enabled = FALSE"
    )


def downgrade() -> None:
    op.drop_column("organizations", "ai_tier")
