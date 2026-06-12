"""Project orchestration spec generation — synthesises all task specs into a unified build guide."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.services.ai.base import ai_call


class FileManifestEntry(BaseModel):
    file_path: str
    purpose: str
    layer: str
    task_title: str
    task_serial: int
    spec_summary: str


class OrchestrationSchema(BaseModel):
    project_overview: str
    tech_stack_summary: str
    implementation_sequence: list[str]
    file_manifest: list[FileManifestEntry] = Field(default_factory=list)
    integration_points: list[str] = Field(default_factory=list)
    environment_setup: list[str] = Field(default_factory=list)
    known_risks: list[str] = Field(default_factory=list)
    cursor_workspace_prompt: str


async def generate_orchestration_ai(
    project_name: str,
    architecture_summary: dict[str, Any],
    task_specs: list[dict[str, Any]],
) -> OrchestrationSchema:
    """Generate a complete project orchestration spec from all task specs + architecture."""

    # Build concise task+spec summary
    task_lines: list[str] = []
    for ts in task_specs:
        task = ts.get("task", {})
        spec = ts.get("spec", {})
        serial = task.get("order_index", 0)
        title = task.get("title", "")
        module = task.get("module_name", "")
        suggested_file = task.get("suggested_file", "")
        files = spec.get("files_to_modify", [])
        scope = (spec.get("task_scope") or "")[:200]
        steps = spec.get("implementation_steps", [])[:3]
        task_lines.append(
            f"#{serial} [{module}] {title}\n"
            f"  File: {suggested_file or (files[0] if files else 'TBD')}\n"
            f"  Scope: {scope}\n"
            f"  Steps: {'; '.join(steps)}"
        )

    tasks_text = "\n\n".join(task_lines[:40])  # cap to avoid token overflow

    # Architecture summary
    sys_doc = architecture_summary.get("doc_system_arch") or {}
    db_doc = architecture_summary.get("doc_database") or {}
    fe_doc = architecture_summary.get("doc_frontend") or {}

    tech_stack = sys_doc.get("tech_stack", {})
    stack_lines = [f"{k}: {v.get('name','') if isinstance(v,dict) else v}" for k, v in tech_stack.items()]
    components = [c.get("name", "") for c in sys_doc.get("components", [])[:10]]
    tables = [t.get("name", "") for t in db_doc.get("tables", [])[:20]]
    pages = [p.get("path", "") for p in fe_doc.get("pages", [])[:15]]
    folder_structure = json.dumps(fe_doc.get("folder_structure", {}), indent=2)[:2000]

    prompt = f"""
You are a senior software architect creating a Master Project Orchestration Specification for the project "{project_name}".

This document is a complete build guide that a developer  can use to implement
the ENTIRE project from scratch in the correct sequence.

ARCHITECTURE OVERVIEW:
Tech Stack: {", ".join(stack_lines)}
System Components: {", ".join(components)}
Database Tables: {", ".join(tables)}
Frontend Pages: {", ".join(pages)}

Folder Structure:
{folder_structure}

ALL TASKS WITH SPECS ({len(task_specs)} tasks):
{tasks_text}

Generate a Master Orchestration Specification containing:

1. project_overview — 3-4 sentences describing what the complete system does and its architectural approach.

2. tech_stack_summary — concise paragraph naming every technology and its role.

3. implementation_sequence — ordered list of 15-25 steps covering the FULL build sequence, e.g.:
   "1. Set up PostgreSQL schema and run all Alembic migrations"
   "2. Implement User model and JWT auth middleware"
   "3. Build project CRUD API endpoints"
   ...follow the architecture layer order: infra → DB → backend models → backend APIs → frontend → tests

4. file_manifest — list of EVERY file that needs to be created or modified across the project.
   For each: file_path, purpose, layer (backend/frontend/database/infra/test), task_title, task_serial (#N), spec_summary (one sentence).
   Group files in layer order: database migrations → backend models → backend schemas →
   backend services → backend routers → frontend pages → frontend components → tests.

5. integration_points — list of critical connection points developers must verify:
   e.g. "JWT cookie set by POST /auth/login must be read by all protected endpoints"
   e.g. "Celery worker must be connected to the same Redis instance as the API"

6. environment_setup — ordered list of setup commands/steps before any coding:
   e.g. "1. Copy .env.example to .env and fill DB_URL, REDIS_URL, ANTHROPIC_API_KEY"
   e.g. "2. Run: docker-compose up -d postgres redis"

7. known_risks — list of integration risks / common failure points specific to this project.

8. cursor_workspace_prompt — a COMPLETE prompt (600-900 words) to paste into Cursor AI or Claude
   to implement the ENTIRE project. Structure it as:
   "I am building [project_name]. [tech_stack_summary]. The complete folder structure is [folder_structure].
   Please implement the following files in this exact sequence: [implementation_sequence].
   Here is the full file manifest: [file_manifest summary].
   Integration points to respect: [integration_points].
   Strict rules: Never hard-delete records (use deleted_at). All AI calls via ai_call() only.
   All heavy operations via Celery. JWT in HttpOnly cookies. Pydantic v2 schemas for all I/O."
   Make this prompt self-contained — a developer should be able to paste it into a fresh Cursor session
   and get the entire project implemented correctly.
"""

    system = """You are an expert software architect writing a master project build guide.
Be exhaustive about the file_manifest — every file matters.
The cursor_workspace_prompt must be complete enough for an AI to implement the full project.
Return strictly structured JSON."""

    return await ai_call(
        prompt=prompt,
        response_model=OrchestrationSchema,
        system=system,
        max_tokens=16000,
        task_type="orchestration_generate",
        screen="tasks",
    )
