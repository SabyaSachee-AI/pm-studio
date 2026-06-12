"""add ai_tier column and new provider API keys support

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-10 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
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
