"""Project bible (.cursorrules) assembly — pure data formatting, no AI calls."""

from typing import Any

from app.models.architecture import Architecture
from app.models.project import Project
from app.models.srs import SRS

_FOLDER_STRUCTURE = """backend/app/api/v1/{domain}/router.py     → HTTP routes only
backend/app/services/{domain}/            → business logic
backend/app/models/{domain}.py            → SQLAlchemy models
backend/app/schemas/{domain}.py           → Pydantic schemas
backend/app/workers/{domain}_tasks.py     → Celery background tasks
frontend/app/(studio)/{feature}/page.tsx  → pages
frontend/components/features/{feature}/   → components
frontend/lib/api.ts                       → API client"""

_CODING_RULES = """- All AI calls: backend/app/services/ai/base.py → ai_call() only
- Soft delete only: set deleted_at timestamp, never DELETE from database
- Heavy operations: Celery tasks — API returns task_id immediately
- TypeScript strict mode — zero `any` types
- Python: async/await everywhere, full type hints required
- Errors: return {"detail": "message"} with correct HTTP status code
- Secrets: always os.getenv() — never hardcode"""

_FIXED_SECURITY_RULES = [
    "JWT stored in HttpOnly Secure SameSite=strict cookies",
    "Token refresh via POST /api/v1/auth/refresh",
    "Never store tokens in localStorage or sessionStorage",
    "All protected routes require Authorization header check in FastAPI deps",
]


def _first_sentence(text: str, limit: int = 200) -> str:
    cleaned = " ".join(text.split())
    sentence = cleaned.split(". ")[0].rstrip(".")
    return sentence[:limit]


def _derive_project_type(srs_content: dict[str, Any]) -> str:
    overall = srs_content.get("overall_description")
    if isinstance(overall, str) and overall.strip():
        return _first_sentence(overall)
    if isinstance(overall, dict):
        for key in ("product_perspective", "summary", "overview"):
            value = overall.get(key)
            if isinstance(value, str) and value.strip():
                return _first_sentence(value)
    for key in ("scope", "introduction"):
        value = srs_content.get(key)
        if isinstance(value, str) and value.strip():
            return _first_sentence(value)
    return "Software application"


def _format_tech_stack(doc_system_arch: dict[str, Any]) -> str:
    tech_stack = doc_system_arch.get("tech_stack") or {}
    if not isinstance(tech_stack, dict) or not tech_stack:
        return "(tech stack not specified in architecture)"
    lines: list[str] = []
    for layer, item in tech_stack.items():
        label = str(layer).replace("_", " ").strip().title()
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            version = str(item.get("version", "")).strip()
            entry = f"{name} {version}".strip() or "(unspecified)"
        else:
            entry = str(item)
        lines.append(f"- {label}: {entry}")
    return "\n".join(lines)


def _format_tables(doc_database: dict[str, Any]) -> str:
    tables = doc_database.get("tables") or []
    if not isinstance(tables, list) or not tables:
        return "(no tables defined in architecture)"
    lines: list[str] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        name = str(table.get("name", "")).strip()
        if not name:
            continue
        columns = table.get("columns") or []
        col_parts: list[str] = []
        for col in columns:
            if isinstance(col, dict) and col.get("name"):
                col_parts.append(f"{col['name']} {col.get('type', '')}".strip())
        lines.append(f"- {name}: {', '.join(col_parts) if col_parts else '(columns unspecified)'}")
    return "\n".join(lines) if lines else "(no tables defined in architecture)"


def _format_endpoints(doc_api: dict[str, Any]) -> str:
    endpoints = doc_api.get("endpoints") or []
    if not isinstance(endpoints, list) or not endpoints:
        return "(no endpoints defined in architecture)"
    lines: list[str] = []
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        method = str(ep.get("method", "")).strip().upper()
        path = str(ep.get("full_path") or ep.get("path") or "").strip()
        description = str(ep.get("description", "")).strip()
        if not path:
            continue
        line = f"- {method} {path}".rstrip()
        if description:
            line += f" — {description}"
        lines.append(line)
    return "\n".join(lines) if lines else "(no endpoints defined in architecture)"


def _extract_roles(doc_security: dict[str, Any]) -> str:
    rbac = doc_security.get("rbac")
    roles_raw: Any = None
    if isinstance(rbac, dict):
        roles_raw = rbac.get("roles")
    names: list[str] = []
    if isinstance(roles_raw, list):
        for role in roles_raw:
            if isinstance(role, str):
                names.append(role)
            elif isinstance(role, dict):
                name = role.get("name") or role.get("role")
                if isinstance(name, str):
                    names.append(name)
    elif isinstance(roles_raw, dict):
        names = [str(k) for k in roles_raw.keys()]
    return ", ".join(names) if names else "(roles not specified in architecture)"


def _format_security(doc_security: dict[str, Any]) -> str:
    lines: list[str] = []
    overview = doc_security.get("overview")
    if isinstance(overview, str) and overview.strip():
        lines.append(f"- {' '.join(overview.split())}")
    rules = list(_FIXED_SECURITY_RULES)
    rules.insert(3, f"RBAC roles: {_extract_roles(doc_security)}")
    lines.extend(f"- {rule}" for rule in rules)
    api_security = doc_security.get("api_security") or []
    if isinstance(api_security, list):
        for item in api_security:
            if isinstance(item, dict):
                text = item.get("rule") or item.get("description") or item.get("name")
                if isinstance(text, str) and text.strip():
                    lines.append(f"- {' '.join(text.split())}")
            elif isinstance(item, str) and item.strip():
                lines.append(f"- {' '.join(item.split())}")
    return "\n".join(lines)


def _format_frs(srs_content: dict[str, Any]) -> str:
    frs = srs_content.get("functional_requirements") or []
    lines: list[str] = []
    for fr in frs:
        if isinstance(fr, dict) and fr.get("fr_number"):
            lines.append(f"- {fr['fr_number']}: {fr.get('title', '')}".rstrip(": "))
    return "\n".join(lines) if lines else "(no functional requirements found in SRS)"


def _format_nfrs(srs_content: dict[str, Any]) -> str:
    nfrs = (
        srs_content.get("non_functional_requirements")
        or srs_content.get("nonfunctional_requirements")
        or []
    )
    lines: list[str] = []
    for nfr in nfrs:
        if not isinstance(nfr, dict):
            continue
        category = str(nfr.get("category", "")).strip()
        description = " ".join(str(nfr.get("description", "")).split())
        metric = str(nfr.get("metric", "")).strip()
        threshold = str(nfr.get("threshold", "")).strip()
        line = f"- {category}: {description}".strip("-: ")
        target = " ".join(p for p in (metric, threshold) if p)
        if target:
            line += f" (target: {target})"
        lines.append(f"- {line.lstrip('- ')}")
    return "\n".join(lines) if lines else "(no non-functional requirements found in SRS)"


def build_project_bible(project: Project, srs: SRS, architecture: Architecture) -> str:
    """Assemble the .cursorrules content from project, SRS, and architecture data."""
    srs_content: dict[str, Any] = srs.content_json or {}
    doc_system_arch: dict[str, Any] = architecture.doc_system_arch or {}
    doc_database: dict[str, Any] = architecture.doc_database or {}
    doc_api: dict[str, Any] = architecture.doc_api or {}
    doc_security: dict[str, Any] = architecture.doc_security or {}

    description = " ".join((project.description or "").split()) or "No description provided"

    sections = [
        f"# {project.name} — AI Coding Assistant Rules",
        (
            "## Project Overview\n"
            f"{project.name} — {description}\n"
            f"Type: {_derive_project_type(srs_content)}"
        ),
        (
            "## Tech Stack (exact versions — use these, no substitutions)\n"
            f"{_format_tech_stack(doc_system_arch)}"
        ),
        (
            "## Folder Structure (exact paths — always use these)\n"
            f"{_FOLDER_STRUCTURE}"
        ),
        (
            "## Database Tables (exact names and columns — never invent new names)\n"
            f"{_format_tables(doc_database)}"
        ),
        (
            "## API Endpoints (exact paths — always use these)\n"
            f"{_format_endpoints(doc_api)}"
        ),
        (
            "## Security and Auth Rules\n"
            f"{_format_security(doc_security)}"
        ),
        (
            "## Coding Rules (never violate)\n"
            f"{_CODING_RULES}"
        ),
        (
            "## SRS Functional Requirements (implement all of these)\n"
            f"{_format_frs(srs_content)}"
        ),
        (
            "## Non-Functional Requirements\n"
            f"{_format_nfrs(srs_content)}"
        ),
    ]
    return "\n\n".join(sections) + "\n"
