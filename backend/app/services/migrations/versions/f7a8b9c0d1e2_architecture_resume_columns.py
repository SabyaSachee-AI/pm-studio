"""architecture resume columns

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-06 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "architectures",
        sa.Column("can_resume", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "architectures",
        sa.Column("last_error", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "architectures",
        sa.Column("resume_from", sa.String(length=64), nullable=True),
    )
    op.alter_column("architectures", "can_resume", server_default=None)


def downgrade() -> None:
    op.drop_column("architectures", "resume_from")
    op.drop_column("architectures", "last_error")
    op.drop_column("architectures", "can_resume")
