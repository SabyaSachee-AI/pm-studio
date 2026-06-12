"""architecture per-doc task tracking

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-06-06 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "architectures",
        sa.Column(
            "doc_task_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "architectures",
        sa.Column(
            "generation_progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "architectures",
        sa.Column(
            "doc_cancel_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("architectures", "doc_task_ids", server_default=None)
    op.alter_column("architectures", "doc_cancel_flags", server_default=None)


def downgrade() -> None:
    op.drop_column("architectures", "doc_cancel_flags")
    op.drop_column("architectures", "generation_progress")
    op.drop_column("architectures", "doc_task_ids")
