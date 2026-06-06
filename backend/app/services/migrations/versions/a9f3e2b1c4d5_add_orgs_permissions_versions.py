"""add organizations screen_permissions document_versions

Revision ID: a9f3e2b1c4d5
Revises: c28834547b24
Create Date: 2026-06-06 12:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a9f3e2b1c4d5"
down_revision: Union[str, Sequence[str], None] = "c28834547b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCREENS = ["dashboard", "clients", "projects", "requirements", "prds", "srs", "admin_users"]

DEFAULT_PERMISSIONS: dict[str, dict[str, tuple[bool, bool]]] = {
    "studio_owner": {s: (True, True) for s in SCREENS},
    "studio_admin": {
        **{s: (True, True) for s in SCREENS if s != "admin_users"},
        "admin_users": (True, True),
    },
    "project_manager": {
        "dashboard": (True, False),
        "clients": (True, True),
        "projects": (True, True),
        "requirements": (True, True),
        "prds": (True, True),
        "srs": (True, True),
        "admin_users": (False, False),
    },
    "business_analyst": {
        "dashboard": (True, False),
        "clients": (True, False),
        "projects": (True, False),
        "requirements": (True, True),
        "prds": (True, True),
        "srs": (True, False),
        "admin_users": (False, False),
    },
    "architect": {
        "dashboard": (True, False),
        "clients": (True, False),
        "projects": (True, False),
        "requirements": (True, False),
        "prds": (True, False),
        "srs": (True, True),
        "admin_users": (False, False),
    },
    "code_creator": {
        "dashboard": (True, False),
        "clients": (False, False),
        "projects": (True, False),
        "requirements": (True, False),
        "prds": (True, False),
        "srs": (True, False),
        "admin_users": (False, False),
    },
    "qa_engineer": {
        "dashboard": (True, False),
        "clients": (False, False),
        "projects": (True, False),
        "requirements": (True, False),
        "prds": (True, False),
        "srs": (True, False),
        "admin_users": (False, False),
    },
    "client": {
        "dashboard": (True, False),
        "clients": (False, False),
        "projects": (True, False),
        "requirements": (True, False),
        "prds": (True, False),
        "srs": (True, False),
        "admin_users": (False, False),
    },
    "viewer": {
        "dashboard": (True, False),
        "clients": (False, False),
        "projects": (True, False),
        "requirements": (False, False),
        "prds": (False, False),
        "srs": (False, False),
        "admin_users": (False, False),
    },
}


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])

    op.add_column("clients", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_clients_organization_id",
        "clients",
        "organizations",
        ["organization_id"],
        ["id"],
    )

    op.create_table(
        "screen_permissions",
        sa.Column("role", postgresql.ENUM(name="user_role", create_type=False), nullable=False),
        sa.Column("screen_key", sa.String(length=50), nullable=False),
        sa.Column("can_view", sa.Boolean(), nullable=False),
        sa.Column("can_edit", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role", "screen_key", name="uq_screen_permissions_role_screen"),
    )
    op.create_index("ix_screen_permissions_screen_key", "screen_permissions", ["screen_key"])

    screen_permissions = sa.table(
        "screen_permissions",
        sa.column("id", sa.UUID()),
        sa.column("role", sa.String()),
        sa.column("screen_key", sa.String()),
        sa.column("can_view", sa.Boolean()),
        sa.column("can_edit", sa.Boolean()),
    )
    rows = []
    for role, screens in DEFAULT_PERMISSIONS.items():
        for screen, (can_view, can_edit) in screens.items():
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "role": role,
                    "screen_key": screen,
                    "can_view": can_view,
                    "can_edit": can_edit,
                }
            )
    op.bulk_insert(screen_permissions, rows)

    op.create_table(
        "document_versions",
        sa.Column(
            "document_type",
            sa.Enum("prd", "srs", name="document_type"),
            nullable=False,
        ),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("change_note", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])

    op.add_column("requirements", sa.Column("parent_requirement_id", sa.UUID(), nullable=True))
    op.add_column("requirements", sa.Column("feedback_filename", sa.String(length=500), nullable=True))
    op.add_column("requirements", sa.Column("feedback_storage_path", sa.String(length=1000), nullable=True))
    op.add_column(
        "requirements",
        sa.Column("cost_estimate_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_requirements_parent_requirement_id",
        "requirements",
        "requirements",
        ["parent_requirement_id"],
        ["id"],
    )

    default_org_id = str(uuid.uuid4())
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
    )
    op.bulk_insert(
        organizations,
        [{"id": default_org_id, "name": "PM Studio", "slug": "pm-studio"}],
    )


def downgrade() -> None:
    op.drop_constraint("fk_requirements_parent_requirement_id", "requirements", type_="foreignkey")
    op.drop_column("requirements", "cost_estimate_json")
    op.drop_column("requirements", "feedback_storage_path")
    op.drop_column("requirements", "feedback_filename")
    op.drop_column("requirements", "parent_requirement_id")
    op.drop_table("document_versions")
    op.execute("DROP TYPE IF EXISTS document_type")
    op.drop_table("screen_permissions")
    op.drop_constraint("fk_clients_organization_id", "clients", type_="foreignkey")
    op.drop_column("clients", "organization_id")
    op.drop_index("ix_organizations_name", table_name="organizations")
    op.drop_table("organizations")
