"""Code-generation build models.

A ``Build`` turns a finalized Architecture suite + Kanban task specs into a real
codebase. Generation is **chunked per task/file and resumable**: every file is
persisted the moment it is produced, and the suite progress is stored in
``generation_progress``. If a free-tier model exhausts its limit mid-run, the
next model in the fallback chain (handled inside ``ai_call``) picks up the next
pending chunk — never restarting completed work, never losing context (each
chunk is given a manifest of already-generated files).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class BuildStatus(enum.Enum):
    """Lifecycle of a code-generation build."""

    draft = "draft"            # created, nothing generated yet
    scaffolding = "scaffolding"
    scaffolded = "scaffolded"  # repo skeleton ready
    generating = "generating"  # per-task code generation in progress
    qa = "qa"                  # pushed; CI quality gate running
    ready = "ready"            # all gates green
    failed = "failed"


class FileStatus(enum.Enum):
    """Lifecycle of a single generated file."""

    pending = "pending"
    generated = "generated"
    edited = "edited"          # human or AI edited after generation
    qa_passed = "qa_passed"
    qa_failed = "qa_failed"


class BuildStage(enum.Enum):
    """Pipeline stage a run belongs to (for the QA report + history)."""

    scaffold = "scaffold"
    codegen = "codegen"
    static_qa = "static_qa"
    tests = "tests"
    deploy = "deploy"


class Build(TimeStampedModel):
    """A generated codebase for one project, derived from its architecture."""

    __tablename__ = "builds"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    architecture_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("architectures.id"), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    status: Mapped[BuildStatus] = mapped_column(
        Enum(
            BuildStatus,
            name="build_status",
            values_callable=lambda items: [i.value for i in items],
        ),
        nullable=False,
        default=BuildStatus.draft,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # GitHub linkage (populated at push time)
    repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_full_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(120), nullable=False, default="main")

    # Quality rollup across all gates (0-10), like the architecture consistency score
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Resumable chunk state: completed task ids, manifest summary, current chunk…
    generation_progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    generation_task_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    can_resume: Mapped[bool] = mapped_column(default=False, nullable=False)
    resume_from: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Scaffold metadata (stack, dependencies, scripts) for context + CI
    scaffold: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    files: Mapped[list["GeneratedFile"]] = relationship(
        back_populates="build",
        cascade="all, delete-orphan",
    )
    stage_runs: Mapped[list["BuildStageRun"]] = relationship(
        back_populates="build",
        cascade="all, delete-orphan",
    )


class GeneratedFile(TimeStampedModel):
    """One file in a build. Content is the editable source of truth; the Git repo
    is materialised from these rows at push time."""

    __tablename__ = "generated_files"

    build_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("builds.id"), nullable=False
    )
    # Which Kanban task produced this file (null for scaffold/shared files)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    status: Mapped[FileStatus] = mapped_column(
        Enum(
            FileStatus,
            name="generated_file_status",
            values_callable=lambda items: [i.value for i in items],
        ),
        nullable=False,
        default=FileStatus.generated,
    )
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Short signature/summary (exports, classes) used to give later chunks context
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    build: Mapped["Build"] = relationship(back_populates="files")


class BuildStageRun(TimeStampedModel):
    """A single pipeline-stage execution (scaffold, codegen, static_qa, …)."""

    __tablename__ = "build_stage_runs"

    build_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("builds.id"), nullable=False
    )
    stage: Mapped[BuildStage] = mapped_column(
        Enum(
            BuildStage,
            name="build_stage",
            values_callable=lambda items: [i.value for i in items],
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_run_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    build: Mapped["Build"] = relationship(back_populates="stage_runs")
