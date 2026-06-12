"""AI module + task extraction from approved PRD, SRS, and optional Architecture."""

from typing import Any

from app.schemas.module import ModuleListSchema
from app.services.ai.base import ai_call


def _arch_context(arch_content: dict[str, Any]) -> str:
    lines: list[str] = []

    frontend = arch_content.get("doc_frontend") or {}
    folder = frontend.get("folder_structure", {})
    if folder:
        lines.append("## Frontend folder structure (MUST use for suggested_file)")
        lines.append(_flatten_folder(folder, ""))

    api_doc = arch_content.get("doc_api") or {}
    endpoints = api_doc.get("endpoints", [])
    if endpoints:
        lines.append("## API endpoints (use for suggested_endpoint)")
        for ep in endpoints[:30]:
            method = ep.get("method", "")
            path = ep.get("path", "") or ep.get("full_path", "")
            linked = ep.get("linked_fr", "")
            file_ = ep.get("file", "")
            lines.append(f"  {method} {path}  [linked_fr: {linked}]  [file: {file_}]")

    db_doc = arch_content.get("doc_database") or {}
    tables = db_doc.get("tables", [])
    if tables:
        lines.append("## Database tables (use for suggested_table)")
        for t in tables[:20]:
            lines.append(f"  {t.get('name', '')} — {t.get('purpose', '')}")

    sys_doc = arch_content.get("doc_system_arch") or {}
    components = sys_doc.get("components", [])
    if components:
        lines.append("## System components")
        for c in components[:10]:
            lines.append(f"  {c.get('name', '')} ({c.get('type', '')}) — {c.get('responsibility', '')}")

    return "\n".join(lines)


def _flatten_folder(node: Any, prefix: str, depth: int = 0) -> str:
    if depth > 4:
        return ""
    if isinstance(node, dict):
        parts = []
        for k, v in node.items():
            parts.append(f"{'  ' * depth}{prefix}{k}/")
            parts.append(_flatten_folder(v, "", depth + 1))
        return "\n".join(parts)
    if isinstance(node, list):
        return "\n".join(f"{'  ' * depth}{item}" for item in node if isinstance(item, str))
    return ""


async def generate_modules_ai(
    project_name: str,
    prd_content: dict,
    srs_content: dict,
    arch_content: dict[str, Any] | None = None,
    target_frs: list[str] | None = None,
) -> ModuleListSchema:
    """Extract modules and implementation tasks from PRD + SRS + Architecture context.

    target_frs: if set, only generate tasks covering these specific FRs (fill-gaps mode).
    """
    features = prd_content.get("features", [])
    features_text = "\n".join(
        f"- {f.get('title', '')}: {f.get('description', '')} [{f.get('priority', '')}]"
        for f in features[:12]
    )
    frs = srs_content.get("functional_requirements", [])

    if target_frs:
        frs = [fr for fr in frs if fr.get("fr_number") in target_frs]

    frs_text = "\n".join(
        f"{fr.get('fr_number', '')}: {fr.get('title', '')} — {fr.get('description', '')}"
        for fr in frs[:30]
    )

    if arch_content:
        ctx = _arch_context(arch_content)
        arch_section = f"""
Architecture context (use this to align tasks to the real file/folder design):
{ctx}

CRITICAL task distribution rules:
1. Module names MUST reflect the Architecture layer they belong to:
   Use names like "Backend — Auth", "Backend — Projects API", "Frontend — Dashboard",
   "Database — Schema", "Infrastructure — Celery Workers", "Frontend — Components".
2. Each task's suggested_file MUST be a real path from the folder structure above.
3. Each task's suggested_endpoint MUST match an endpoint from the API list above.
4. Each task's suggested_table MUST match a table from the database list above.
5. Order tasks within each module in the sequence a developer would implement them
   (models first → schemas → service → router → frontend → tests).
6. Every FR must map to at least one task via linked_fr.
"""
    else:
        arch_section = """
No architecture document is available yet.
Group tasks by logical layer: "Backend — [Feature]", "Frontend — [Feature]", "Database — [Feature]".
Order tasks: model → schema → service → API endpoint → frontend page → tests.
Set linked_fr to the primary FR number. Leave suggested_file/endpoint/table as null.
"""

    fill_note = ""
    if target_frs:
        fill_note = f"""
IMPORTANT — Fill-gaps mode: ONLY generate tasks for these specific FRs that currently have no coverage:
{", ".join(target_frs)}
Do not generate tasks for any other FRs.
"""

    prompt = f"""
You are a senior technical project manager breaking a software project into modules and tasks.
Each task must map directly to the file/folder structure in the architecture design.

Project: {project_name}

PRD Features:
{features_text or "No features listed"}

SRS Functional Requirements to cover:
{frs_text or "No FRs listed"}
{arch_section}{fill_note}
Rules:
- Maximum 6 tasks per module. Keep module count reasonable (one module per architectural concern).
- Priorities: critical (auth, core data models), high (main features), medium (secondary), low (polish).
- Each task title must be specific: "Create Task SQLAlchemy model and Alembic migration" NOT "Setup database".
- Description must say WHO does WHAT: "Implement the POST /api/v1/tasks endpoint in app/api/v1/tasks/router.py".
- effort_hours: realistic estimate in hours (1-16).
- Every task must have linked_fr set to the primary FR it implements.
"""

    system = """You are an expert software project planner with deep knowledge of layered architecture.
Return strictly structured JSON matching the schema.
Module names reflect architectural layers, not feature names.
Tasks are ordered in implementation sequence within each module.
Every task is independently implementable and maps to a specific file."""

    return await ai_call(
        prompt=prompt,
        response_model=ModuleListSchema,
        system=system,
        max_tokens=12000,
    )
