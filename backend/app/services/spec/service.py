"""Technical task specification AI generation."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.schemas.spec import SpecCoreSchema, SpecPromptSchema, TaskSpecSchema
from app.services.ai.base import ai_call

SPEC_PHASE_CORE = "core"
SPEC_PHASE_SUMMARY = "summary"
SPEC_GENERATION_PROGRESS_KEY = "_generation_progress"

_CODING_RULES = """
CODING RULES (always follow):
- All AI calls via backend/app/services/ai/base.py → ai_call() only
- Soft delete: set deleted_at, never DELETE from database
- Heavy operations: Celery task, API returns task_id immediately
- TypeScript strict mode — no any types
- Python: async/await, full type hints
- Errors: {"detail": "message"} + correct HTTP status code
- Secrets: os.getenv() only, never hardcode
"""


def parse_spec_resume_state(
    content_json: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Return partial spec fields and completed phase names from a prior run."""
    if not content_json:
        return {}, []
    progress = content_json.get(SPEC_GENERATION_PROGRESS_KEY) or {}
    partial = dict(progress.get("partial") or {})
    completed = list(progress.get("completed_phases") or [])
    return partial, completed


def build_spec_progress_payload(
    partial: dict[str, Any],
    completed_phases: list[str],
    *,
    current_phase: str = "",
) -> dict[str, Any]:
    """Wrap partial spec output for persistence while status is generating."""
    return {
        SPEC_GENERATION_PROGRESS_KEY: {
            "partial": partial,
            "completed_phases": completed_phases,
            "current_phase": current_phase,
        }
    }


def strip_spec_progress(content: dict[str, Any]) -> dict[str, Any]:
    """Remove internal generation metadata before marking spec ready."""
    cleaned = dict(content)
    cleaned.pop(SPEC_GENERATION_PROGRESS_KEY, None)
    return cleaned


def _format_endpoint(ep: dict[str, Any]) -> str:
    method = str(ep.get("method", "")).upper()
    path = ep.get("full_path") or ep.get("path") or ""
    lines = [f"{method} {path} — {ep.get('description', '')}"]
    if ep.get("file"):
        lines.append(f"  file: {ep['file']}")
    if ep.get("request_body"):
        lines.append(f"  request body: {ep['request_body']}")
    if ep.get("response_200"):
        lines.append(f"  response 200: {ep['response_200']}")
    if ep.get("response_errors"):
        lines.append(f"  error responses: {ep['response_errors']}")
    return "\n".join(lines)


def _format_table(table: dict[str, Any]) -> str:
    cols = ", ".join(
        f"{c.get('name')} {c.get('type', '')}{' PK' if c.get('pk') else ''}"
        for c in (table.get("columns") or [])
        if isinstance(c, dict) and c.get("name")
    )
    return f"Table {table.get('name')}: {cols or '(columns unspecified)'}"


def build_arch_spec_context(
    task_suggested_file: str | None,
    task_suggested_endpoint: str | None,
    task_suggested_table: str | None,
    fr_references: list[str],
    linked_fr: str,
    arch_content: dict[str, Any] | None,
) -> str:
    """Extract architecture details relevant to one task as prompt text."""
    if not arch_content:
        return ""
    sections: list[str] = []
    fr_set = set(fr_references) | ({linked_fr} if linked_fr else set())

    sys_doc = arch_content.get("doc_system_arch") or {}
    tech_stack = sys_doc.get("tech_stack") or {}
    if tech_stack:
        stack_lines = []
        for layer, item in tech_stack.items():
            if isinstance(item, dict):
                stack_lines.append(
                    f"  {layer}: {item.get('name', '')} {item.get('version', '')}".rstrip()
                )
            else:
                stack_lines.append(f"  {layer}: {item}")
        sections.append("Tech stack (exact versions, no substitutions):\n" + "\n".join(stack_lines))

    api_doc = arch_content.get("doc_api") or {}
    endpoints = [ep for ep in (api_doc.get("endpoints") or []) if isinstance(ep, dict)]
    relevant_eps = [
        ep
        for ep in endpoints
        if (
            task_suggested_endpoint
            and task_suggested_endpoint in (ep.get("path", "") + ep.get("full_path", ""))
        )
        or (ep.get("linked_fr") and ep.get("linked_fr") in fr_set)
    ]
    if not relevant_eps and endpoints:
        relevant_eps = endpoints[:20]
    if relevant_eps:
        sections.append(
            "API endpoints (exact contract — use these paths):\n"
            + "\n".join(_format_endpoint(ep) for ep in relevant_eps[:20])
        )

    db_doc = arch_content.get("doc_database") or {}
    tables = [t for t in (db_doc.get("tables") or []) if isinstance(t, dict)]
    relevant_tables = [
        t for t in tables if task_suggested_table and t.get("name") == task_suggested_table
    ]
    if not relevant_tables and task_suggested_table:
        sections.append(
            f"Database table: {task_suggested_table} (definition not found in architecture)"
        )
    elif relevant_tables:
        sections.append(
            "Database tables (exact names and columns — never invent new ones):\n"
            + "\n".join(_format_table(t) for t in relevant_tables)
        )
    elif tables:
        sections.append(
            "All database tables in architecture:\n"
            + "\n".join(_format_table(t) for t in tables)
        )

    fe_doc = arch_content.get("doc_frontend") or {}
    pages = [p for p in (fe_doc.get("pages") or []) if isinstance(p, dict)]
    if pages:
        page_lines = [
            f"  {p.get('path', '')} → {p.get('file', '')} — {p.get('description', '')}"
            for p in pages
        ]
        sections.append("Frontend routes and pages:\n" + "\n".join(page_lines))

    if task_suggested_file:
        sections.append(f"Primary file for this task: {task_suggested_file}")

    sec_doc = arch_content.get("doc_security") or {}
    auth = sec_doc.get("auth_mechanism") or {}
    if auth:
        sections.append(f"Auth mechanism: {auth}")

    return "\n\n".join(sections)


def _linked_fr_text(linked_fr: str, fr_references: list[str], srs_content: dict) -> str:
    fr_numbers = set(fr_references)
    if linked_fr:
        fr_numbers.add(linked_fr)
    if not fr_numbers:
        return "No specific FR linked"
    all_frs = srs_content.get("functional_requirements") or []
    lines: list[str] = []
    for fr in all_frs:
        if isinstance(fr, dict) and fr.get("fr_number") in fr_numbers:
            criteria = "; ".join(fr.get("test_criteria") or [])
            lines.append(
                f"{fr['fr_number']}: {fr.get('title', '')}\n"
                f"  {fr.get('description', '')}"
                + (f"\n  acceptance criteria: {criteria}" if criteria else "")
            )
    return "\n".join(lines) if lines else "No matching FR details in SRS"


def _linked_prd_feature(task_title: str, module_name: str, prd_content: dict | None) -> str:
    if not prd_content:
        return ""
    features = prd_content.get("features") or []
    title_lower = task_title.lower()
    module_lower = (module_name or "").lower()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        ft = str(feature.get("title", "")).lower()
        if ft and (ft in title_lower or title_lower in ft or ft in module_lower):
            return f"{feature.get('title', '')}: {feature.get('description', '')}"
    if features and isinstance(features[0], dict):
        f0 = features[0]
        return f"{f0.get('title', '')}: {f0.get('description', '')}"
    return ""


def _build_task_context(
    *,
    task_title: str,
    task_description: str,
    module_name: str,
    fr_references: list[str],
    linked_fr: str,
    suggested_file: str | None,
    suggested_endpoint: str | None,
    suggested_table: str | None,
    srs_content: dict,
    prd_content: dict | None,
    arch_content: dict | None,
    project_name: str,
) -> dict[str, str]:
    frs_text = _linked_fr_text(linked_fr, fr_references, srs_content)
    prd_feature = _linked_prd_feature(task_title, module_name, prd_content)

    prd_features_text = ""
    if prd_content:
        features = prd_content.get("features") or []
        related = [
            f"- {f.get('title', '')}: {f.get('description', '')} [{f.get('priority', '')}]"
            for f in features
            if isinstance(f, dict)
        ]
        if related:
            prd_features_text = "\nPRD features (product context):\n" + "\n".join(related)

    arch_context = build_arch_spec_context(
        task_suggested_file=suggested_file,
        task_suggested_endpoint=suggested_endpoint,
        task_suggested_table=suggested_table,
        fr_references=fr_references,
        linked_fr=linked_fr,
        arch_content=arch_content,
    )
    arch_section = (
        f"\nArchitecture context (authoritative — follow exactly, never rename tables or paths):\n"
        f"{arch_context}\n"
        if arch_context
        else "\nNo architecture document available — use standard project folder structure.\n"
    )

    hints = []
    if suggested_file:
        hints.append(f"primary file: {suggested_file}")
    if suggested_endpoint:
        hints.append(f"endpoint: {suggested_endpoint}")
    if suggested_table:
        hints.append(f"table: {suggested_table}")
    hints_text = f"Task placement hints: {', '.join(hints)}\n" if hints else ""

    return {
        "project_name": project_name,
        "module_name": module_name or "General",
        "task_title": task_title,
        "task_description": task_description or "No description provided",
        "linked_fr": linked_fr or "none",
        "hints_text": hints_text,
        "frs_text": frs_text,
        "prd_features_text": prd_features_text,
        "arch_section": arch_section,
        "prd_feature": prd_feature,
    }


def _core_prompt(ctx: dict[str, str]) -> str:
    return f"""
You are a senior software architect writing a technical specification for a developer.

PROJECT: {ctx["project_name"]}
MODULE: {ctx["module_name"]}
TASK: {ctx["task_title"]}
DESCRIPTION: {ctx["task_description"]}
LINKED FR: {ctx["linked_fr"]}
{ctx["hints_text"]}
SRS FUNCTIONAL REQUIREMENTS for this task:
{ctx["frs_text"]}
{ctx["prd_features_text"]}
{ctx["arch_section"]}
Generate the structured fields for this task spec (phase 1 — do NOT write the implementation summary yet).

Populate every field with concrete, implementation-ready detail from the architecture and SRS:
- task_scope: 3-6 sentences on what to build and why
- linked_fr: primary FR number(s)
- linked_prd_feature: PRD feature title and description
- files_to_create / files_to_modify: exact paths
- database.tables: each table with relevant_columns from architecture
- api_endpoints: method, path, request_body, response_schema, status_code
- frontend_route / frontend_component: exact paths from architecture
- acceptance_criteria: testable pass/fail criteria from SRS
- technical_notes: non-obvious constraints and pitfalls

Never invent table names, column names, or API paths not in the architecture context.
Never use the word "Cursor" anywhere.
"""


def _summary_phase_instruction(ctx: dict[str, str], core: SpecCoreSchema) -> str:
    core_json = json.dumps(core.model_dump(), indent=2, default=str)
    return f"""
You are a senior software architect. Write the Implementation Summary only.

PROJECT: {ctx["project_name"]}
TASK: {ctx["task_title"]}
MODULE: {ctx["module_name"]}

Structured spec already finalized (use as source of truth — do not contradict):
{core_json}

Write the implementation summary as a dense, self-contained brief a developer pastes into an AI coding assistant.
Use this exact structure:

---
PROJECT: {ctx["project_name"]}
TASK: {ctx["task_title"]}
MODULE: {ctx["module_name"]}
SRS REQUIREMENT: [linked_fr — number: title: description]
PRD FEATURE: [linked_prd_feature]

WHAT TO BUILD:
[task_scope]

FILES TO CREATE:
[each path on its own line]

FILES TO MODIFY:
[each path on its own line]

DATABASE (use these exact names — do not rename):
[for each table: name, columns used, query pattern with deleted_at filter]

API ENDPOINTS TO IMPLEMENT:
[METHOD path, request body fields, response fields, HTTP status, auth required/public]

FRONTEND:
Page: [route]
Component: [path]
API calls: [api.xxx() from lib/api.ts]
State: [useState fields needed]

ACCEPTANCE CRITERIA (task is complete when all pass):
[numbered list]

TECHNICAL CONSTRAINTS:
[technical_notes]

{_CODING_RULES.strip()}
---

Never use the word "Cursor" in the output.
Return only the implementation summary as structured JSON (single text field).
"""


async def generate_spec_ai(
    task_title: str,
    task_description: str,
    module_name: str,
    fr_references: list[str],
    linked_fr: str,
    suggested_file: str | None,
    suggested_endpoint: str | None,
    suggested_table: str | None,
    srs_content: dict,
    prd_content: dict | None,
    arch_content: dict | None,
    project_name: str,
    *,
    resume_partial: dict[str, Any] | None = None,
    resume_completed_phases: list[str] | None = None,
    on_phase_complete: Callable[[str, dict[str, Any]], None] | None = None,
) -> TaskSpecSchema:
    """Generate a developer-ready spec in two phases with optional resume."""
    ctx = _build_task_context(
        task_title=task_title,
        task_description=task_description,
        module_name=module_name,
        fr_references=fr_references,
        linked_fr=linked_fr,
        suggested_file=suggested_file,
        suggested_endpoint=suggested_endpoint,
        suggested_table=suggested_table,
        srs_content=srs_content,
        prd_content=prd_content,
        arch_content=arch_content,
        project_name=project_name,
    )

    partial: dict[str, Any] = dict(resume_partial or {})
    completed = list(resume_completed_phases or [])

    core_system = (
        "You are an expert software architect writing precise technical specifications. "
        "Return strictly structured JSON matching the schema."
    )
    summary_system = (
        "You are an expert software architect writing a self-contained implementation summary. "
        "Return strictly structured JSON with one text field for the summary."
    )

    core_data: SpecCoreSchema | None = None
    if SPEC_PHASE_CORE in completed and partial.get("task_scope"):
        core_data = SpecCoreSchema.model_validate(partial)
    else:
        core_result = await ai_call(
            prompt=_core_prompt(ctx),
            response_model=SpecCoreSchema,
            system=core_system,
            max_tokens=8000,
            task_type="spec_generate",
            screen="tasks",
        )
        core_data = core_result
        partial.update(core_data.model_dump())
        completed.append(SPEC_PHASE_CORE)
        if on_phase_complete:
            on_phase_complete(SPEC_PHASE_CORE, dict(partial))

    cursor_prompt = str(partial.get("cursor_prompt") or "")
    if SPEC_PHASE_SUMMARY not in completed or not cursor_prompt.strip():
        partial_prefill = cursor_prompt.strip() if cursor_prompt.strip() else ""
        summary_result = await ai_call(
            prompt=_summary_phase_instruction(ctx, core_data),
            response_model=SpecPromptSchema,
            system=summary_system,
            max_tokens=8000,
            task_type="spec_generate",
            screen="tasks",
            assistant_prefill=partial_prefill,
        )
        partial["cursor_prompt"] = summary_result.cursor_prompt
        if SPEC_PHASE_SUMMARY not in completed:
            completed.append(SPEC_PHASE_SUMMARY)
        if on_phase_complete:
            on_phase_complete(SPEC_PHASE_SUMMARY, dict(partial))

    return TaskSpecSchema.model_validate(partial)
