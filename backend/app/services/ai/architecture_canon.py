"""Shared architecture suite canon — enforces cross-document consistency."""

from __future__ import annotations

import json
from typing import Any

from app.models.architecture import DOC_FIELDS

DOC_GENERATION_ORDER = [
    "doc_system_arch",
    "doc_database",
    "doc_api",
    "doc_frontend",
    "doc_security",
    "doc_uiux",
]

CANON_RULES_TEXT = """
=== MANDATORY SUITE CANON (every document MUST follow exactly) ===
1. Architecture style: Modular monolith — FastAPI backend + Celery workers + PostgreSQL + Redis.
   NOT microservices for MVP. Internal feature modules are Python packages, not separate deployables.
2. API base URL: /api/v1 only. NEVER use /api/auth/* — auth lives at /api/v1/auth/*.
3. Auth: JWT stored in HttpOnly Secure SameSite cookies set by FastAPI. NO NextAuth, NO /api/auth/signin.
   Auth endpoints: POST /api/v1/auth/register, POST /api/v1/auth/login, POST /api/v1/auth/logout,
   GET /api/v1/auth/me, POST /api/v1/auth/refresh.
4. Frontend: Next.js 14 App Router calling FastAPI via fetch with credentials:include.
5. Entity naming: Use the EXACT entity names from the entity_glossary in the PROJECT SUITE CANON JSON below.
   Never invent synonyms for canonical entities (no renaming, no aliases) — same names in DB tables,
   API routes, and frontend pages.
6. SRS traceability: EVERY functional requirement (FR-xxx) MUST appear in at least one API endpoint linked_fr field.
7. MVP scope: Tag each API endpoint and DB table with mvp_scope "v1" or "v2". Auth + core domain entities = v1.
8. Security roles must EXACTLY match the roles list in the PROJECT SUITE CANON JSON below — same names
   in the RBAC matrix and API permission checks.
9. Do NOT repeat long SRS narrative in overview — reference FR IDs instead.
10. All frontend page api_calls MUST use exact full_path values from the API document.
"""

# Roles used when the SRS does not define user classes
GENERIC_ROLES = ["admin", "user", "guest"]


def _derive_entities_from_srs(srs_content: dict[str, Any]) -> dict[str, str]:
    """Extract canonical entity names from SRS data requirements (any project type)."""
    entities: dict[str, str] = {}
    data_req = srs_content.get("data_requirements") or {}
    raw = (
        data_req.get("entities")
        or data_req.get("data_entities")
        or data_req.get("logical_data_model")
        or []
    )
    if isinstance(raw, dict):
        raw = list(raw.items())
    if isinstance(raw, list):
        for e in raw:
            if isinstance(e, dict):
                name = str(e.get("name") or e.get("entity") or "").strip().lower()
                desc = str(e.get("description") or e.get("purpose") or "")[:140]
            elif isinstance(e, tuple) and len(e) == 2:
                name, desc = str(e[0]).strip().lower(), str(e[1])[:140]
            else:
                name, desc = str(e).strip().lower(), ""
            if name and len(name) < 60:
                entities[name] = desc or "Core domain entity"
    return entities


def _derive_roles_from_srs(srs_content: dict[str, Any]) -> list[str]:
    """Extract user roles from SRS user classes; fall back to generic roles."""
    overall = srs_content.get("overall_description") or {}
    raw = (
        overall.get("user_classes")
        or overall.get("user_characteristics")
        or srs_content.get("user_classes")
        or []
    )
    roles: list[str] = []
    if isinstance(raw, list):
        for u in raw:
            name = (
                str(u.get("name") or u.get("class") or u.get("role") or "").strip()
                if isinstance(u, dict)
                else str(u).strip()
            )
            name = name.lower().replace(" ", "_")[:40]
            if name and name not in roles:
                roles.append(name)
    if "admin" not in roles:
        roles.insert(0, "admin")
    return roles if len(roles) > 1 else GENERIC_ROLES


def _fr_id(fr: dict[str, Any]) -> str:
    return str(fr.get("fr_number") or fr.get("id") or fr.get("fr_id") or "")


def _fr_title(fr: dict[str, Any]) -> str:
    return str(fr.get("title") or fr.get("description") or fr.get("name") or "")[:200]


def build_suite_canon_from_srs(
    srs_content: dict[str, Any],
    project_name: str,
    project_description: str = "",
) -> dict[str, Any]:
    """Build the canonical contract all 6 docs must share."""
    frs = srs_content.get("functional_requirements") or []
    nfrs = srs_content.get("non_functional_requirements") or []
    fr_catalog = [
        {"id": _fr_id(fr), "title": _fr_title(fr)}
        for fr in frs
        if _fr_id(fr)
    ]
    return {
        "project_name": project_name,
        "project_description": (project_description or "")[:500],
        "architecture_pattern": "Modular monolith with Celery background workers",
        "api_base_url": "/api/v1",
        "auth_strategy": (
            "JWT in HttpOnly Secure SameSite cookies; FastAPI issues tokens; "
            "frontend uses fetch credentials:include — no NextAuth"
        ),
        "auth_endpoints": [
            "POST /api/v1/auth/register",
            "POST /api/v1/auth/login",
            "POST /api/v1/auth/logout",
            "GET /api/v1/auth/me",
            "POST /api/v1/auth/refresh",
        ],
        "entity_glossary": _derive_entities_from_srs(srs_content),
        "functional_requirements": fr_catalog,
        "required_fr_count": len(fr_catalog),
        "roles": _derive_roles_from_srs(srs_content),
        "tech_stack_mvp": {
            "frontend": "Next.js 14 App Router, TypeScript, Tailwind",
            "backend": "FastAPI, Python 3.12",
            "database": "PostgreSQL 16",
            "cache_queue": "Redis, Celery",
        },
        "nfr_summary": [
            str(n.get("title") or n.get("description") or n)[:120]
            for n in (nfrs[:8] if isinstance(nfrs, list) else [])
        ],
    }


def summarize_doc_for_context(doc_field: str, doc: dict[str, Any] | None) -> str:
    """Compact summary of a completed doc for subsequent generation."""
    if not doc:
        return ""
    if doc_field == "doc_system_arch":
        stack = doc.get("tech_stack") or {}
        layers = list(stack.keys())[:10] if isinstance(stack, dict) else []
        components = [c.get("name") for c in (doc.get("components") or [])[:10]]
        return (
            f"Pattern: {doc.get('architecture_pattern', '')}\n"
            f"Stack layers: {layers}\n"
            f"Components: {components}\n"
            f"Data flow steps: {(doc.get('data_flow') or [])[:5]}"
        )
    if doc_field == "doc_database":
        tables = doc.get("tables") or []
        return (
            f"Tables ({len(tables)}): "
            f"{[t.get('name') for t in tables[:20]]}\n"
            f"Migration order: {(doc.get('migration_order') or [])[:12]}"
        )
    if doc_field == "doc_api":
        eps = doc.get("endpoints") or []
        lines = [
            f"{e.get('method')} {e.get('full_path') or e.get('path')} -> {e.get('linked_fr')}"
            for e in eps[:40]
        ]
        return f"base_url: {doc.get('base_url')}\nauth: {str(doc.get('auth', ''))[:200]}\n" + "\n".join(lines)
    if doc_field == "doc_frontend":
        pages = doc.get("pages") or []
        return (
            f"framework: {doc.get('framework')}\n"
            f"auth: {str(doc.get('auth', ''))[:200]}\n"
            f"pages: {[(p.get('path'), p.get('file')) for p in pages[:15]]}"
        )
    if doc_field == "doc_security":
        roles = (doc.get("rbac") or {}).get("roles") or []
        role_names = [r.get("name") if isinstance(r, dict) else r for r in roles]
        return f"roles: {role_names}\nauth: {json.dumps(doc.get('auth_mechanism', {}), default=str)[:300]}"
    if doc_field == "doc_uiux":
        return (
            f"ux_rules: {(doc.get('ux_rules') or [])[:8]}\n"
            f"pages: {len(doc.get('pages') or [])}"
        )
    return json.dumps(doc, default=str)[:2000]


def build_cross_doc_context(arch: Any, target_doc_field: str) -> str:
    """Summaries of all docs generated before target_doc_field in suite order."""
    parts: list[str] = []
    for field in DOC_GENERATION_ORDER:
        if field == target_doc_field:
            break
        doc = getattr(arch, field, None)
        status = getattr(arch, f"{field}_status", "pending")
        if doc and status in ("completed", "generated", "saved"):
            parts.append(f"--- {field} ---\n{summarize_doc_for_context(field, doc)}")
    return "\n\n".join(parts)


def format_canon_prompt_block(suite_canon: dict[str, Any] | None, cross_doc: str = "") -> str:
    """Prompt prefix injected into every architecture doc generation."""
    blocks = [CANON_RULES_TEXT]
    if suite_canon:
        blocks.append(
            "=== PROJECT SUITE CANON (JSON) ===\n"
            + json.dumps(suite_canon, indent=2, default=str)[:8000]
        )
    if cross_doc.strip():
        blocks.append("=== COMPLETED SIBLING DOCUMENTS ===\n" + cross_doc[:10000])
    return "\n\n".join(blocks)
