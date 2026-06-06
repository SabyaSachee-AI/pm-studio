"""add knowledge base decisions notifications screens

Revision ID: c4d5e6f7a8b9
Revises: 8f7cf3ad8389
Create Date: 2026-06-05 14:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "8f7cf3ad8389"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SCREENS = ["tasks", "knowledge_base", "decisions"]

NEW_PERMISSIONS: dict[str, dict[str, tuple[bool, bool]]] = {
    "studio_owner": {s: (True, True) for s in NEW_SCREENS},
    "studio_admin": {s: (True, True) for s in NEW_SCREENS},
    "project_manager": {
        "tasks": (True, True),
        "knowledge_base": (True, True),
        "decisions": (True, True),
    },
    "business_analyst": {
        "tasks": (True, False),
        "knowledge_base": (True, True),
        "decisions": (True, True),
    },
    "architect": {
        "tasks": (True, True),
        "knowledge_base": (True, True),
        "decisions": (True, True),
    },
    "code_creator": {
        "tasks": (True, False),
        "knowledge_base": (True, False),
        "decisions": (True, False),
    },
    "qa_engineer": {
        "tasks": (True, False),
        "knowledge_base": (True, False),
        "decisions": (True, False),
    },
    "client": {
        "tasks": (False, False),
        "knowledge_base": (False, False),
        "decisions": (False, False),
    },
    "viewer": {
        "tasks": (True, False),
        "knowledge_base": (True, False),
        "decisions": (True, False),
    },
}


def upgrade() -> None:
    knowledge_item_type = sa.Enum(
        "document", "module", "spec", name="knowledge_item_type"
    )
    knowledge_source_type = sa.Enum(
        "prd", "srs", "spec", "manual", name="knowledge_source_type"
    )
    knowledge_item_type.create(op.get_bind(), checkfirst=True)
    knowledge_source_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "knowledge_base_items",
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column(
            "item_type",
            postgresql.ENUM(
                "document", "module", "spec", name="knowledge_item_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "prd", "srs", "spec", "manual", name="knowledge_source_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("saved_by_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["saved_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_base_items_project_id", "knowledge_base_items", ["project_id"])

    op.create_table(
        "reusable_modules",
        sa.Column("knowledge_base_item_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("saved_by_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["knowledge_base_item_id"], ["knowledge_base_items.id"]),
        sa.ForeignKeyConstraint(["saved_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reusable_modules_name", "reusable_modules", ["name"])

    op.create_table(
        "decisions",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("alternatives", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_project_id", "decisions", ["project_id"])

    op.create_table(
        "notifications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    screen_permissions = sa.table(
        "screen_permissions",
        sa.column("id", sa.UUID),
        sa.column("role", sa.String),
        sa.column("screen_key", sa.String),
        sa.column("can_view", sa.Boolean),
        sa.column("can_edit", sa.Boolean),
        sa.column("created_at", sa.TIMESTAMP(timezone=True)),
        sa.column("updated_at", sa.TIMESTAMP(timezone=True)),
        sa.column("deleted_at", sa.TIMESTAMP(timezone=True)),
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rows = []
    for role, screens in NEW_PERMISSIONS.items():
        for screen_key, (can_view, can_edit) in screens.items():
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "role": role,
                    "screen_key": screen_key,
                    "can_view": can_view,
                    "can_edit": can_edit,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            )
    op.bulk_insert(screen_permissions, rows)


def downgrade() -> None:
    for screen in NEW_SCREENS:
        op.execute(
            sa.text(
                "DELETE FROM screen_permissions WHERE screen_key = :screen"
            ).bindparams(screen=screen)
        )
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_decisions_project_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_reusable_modules_name", table_name="reusable_modules")
    op.drop_table("reusable_modules")
    op.drop_index("ix_knowledge_base_items_project_id", table_name="knowledge_base_items")
    op.drop_table("knowledge_base_items")
    sa.Enum(name="knowledge_source_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="knowledge_item_type").drop(op.get_bind(), checkfirst=True)
