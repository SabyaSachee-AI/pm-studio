"""tasks_arch_fields

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("linked_fr", sa.String(length=50), nullable=True))
    op.add_column("tasks", sa.Column("suggested_file", sa.String(length=500), nullable=True))
    op.add_column("tasks", sa.Column("suggested_endpoint", sa.String(length=500), nullable=True))
    op.add_column("tasks", sa.Column("suggested_table", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "suggested_table")
    op.drop_column("tasks", "suggested_endpoint")
    op.drop_column("tasks", "suggested_file")
    op.drop_column("tasks", "linked_fr")
