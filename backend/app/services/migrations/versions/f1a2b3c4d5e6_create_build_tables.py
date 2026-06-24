"""create build / generated_files / build_stage_runs tables

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
Create Date: 2026-06-18 02:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "builds",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("architecture_id", sa.UUID(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "scaffolding", "scaffolded", "generating", "qa", "ready", "failed",
                name="build_status",
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=True),
        sa.Column("repo_url", sa.String(length=500), nullable=True),
        sa.Column("github_full_name", sa.String(length=300), nullable=True),
        sa.Column("default_branch", sa.String(length=120), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generation_progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generation_task_id", sa.String(length=120), nullable=True),
        sa.Column("can_resume", sa.Boolean(), nullable=False),
        sa.Column("resume_from", sa.String(length=200), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("scaffold", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["architecture_id"], ["architectures.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_builds_project_id", "builds", ["project_id"])

    op.create_table(
        "generated_files",
        sa.Column("build_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "generated", "edited", "qa_passed", "qa_failed",
                name="generated_file_status",
            ),
            nullable=False,
        ),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["build_id"], ["builds.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_files_build_id", "generated_files", ["build_id"])

    op.create_table(
        "build_stage_runs",
        sa.Column("build_id", sa.UUID(), nullable=False),
        sa.Column(
            "stage",
            sa.Enum(
                "scaffold", "codegen", "static_qa", "tests", "deploy",
                name="build_stage",
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("github_run_url", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["build_id"], ["builds.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_build_stage_runs_build_id", "build_stage_runs", ["build_id"])


def downgrade() -> None:
    op.drop_index("ix_build_stage_runs_build_id", table_name="build_stage_runs")
    op.drop_table("build_stage_runs")
    op.drop_index("ix_generated_files_build_id", table_name="generated_files")
    op.drop_table("generated_files")
    op.drop_index("ix_builds_project_id", table_name="builds")
    op.drop_table("builds")
    sa.Enum(name="build_stage").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="generated_file_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="build_status").drop(op.get_bind(), checkfirst=True)
