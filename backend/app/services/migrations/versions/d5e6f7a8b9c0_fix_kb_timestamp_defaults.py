"""fix timestamp defaults on kb tables

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "knowledge_base_items",
    "reusable_modules",
    "decisions",
    "notifications",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN created_at SET DEFAULT NOW()"
        )
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN updated_at SET DEFAULT NOW()"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN created_at DROP DEFAULT"
        )
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN updated_at DROP DEFAULT"
        )
