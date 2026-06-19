"""create architectures table

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-06 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "architectures",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("srs_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "confirmed", "finalized", name="architecture_status"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("confirmed_by_id", sa.UUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation_task_id", sa.String(length=255), nullable=True),
        sa.Column("doc_system_arch", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("doc_database", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("doc_api", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("doc_frontend", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("doc_security", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("doc_uiux", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("doc_system_arch_status", sa.String(length=32), nullable=False),
        sa.Column("doc_database_status", sa.String(length=32), nullable=False),
        sa.Column("doc_api_status", sa.String(length=32), nullable=False),
        sa.Column("doc_frontend_status", sa.String(length=32), nullable=False),
        sa.Column("doc_security_status", sa.String(length=32), nullable=False),
        sa.Column("doc_uiux_status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["confirmed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["srs_id"], ["srs_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    screen_permissions = sa.table(
        "screen_permissions",
        sa.column("role", sa.String),
        sa.column("screen_key", sa.String),
        sa.column("can_view", sa.Boolean),
        sa.column("can_edit", sa.Boolean),
        sa.column("id", sa.UUID),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    rows = []
    for role, view, edit in [
        ("studio_owner", True, True),
        ("architect", True, True),
        ("code_creator", True, False),
        ("client", False, False),
    ]:
        rows.append(
            {
                "role": role,
                "screen_key": "architecture",
                "can_view": view,
                "can_edit": edit,
            }
        )
    op.bulk_insert(screen_permissions, rows)


def downgrade() -> None:
    op.execute(
        "DELETE FROM screen_permissions WHERE screen_key = 'architecture'"
    )
    op.drop_table("architectures")
    op.execute("DROP TYPE IF EXISTS architecture_status")
