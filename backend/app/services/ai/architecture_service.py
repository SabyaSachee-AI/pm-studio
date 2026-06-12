"""AI generation for the 6-document architecture suite."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.architecture import ArchitectureDocSchema
from app.services.ai.base import ai_call
from app.services.ai.mermaid_sanitize import sanitize_mermaid

ARCH_DOC_KEYS: list[tuple[str, str]] = [
    ("doc_system_arch", "System architecture"),
    ("doc_database", "Database design"),
    ("doc_api", "API specification"),
    ("doc_frontend", "Frontend architecture"),
    ("doc_security", "Security and RBAC"),
    ("doc_uiux", "UI/UX design guidance"),
]

MERMAID_RULES = """
Mermaid diagram rules (required):
- Include 1-3 diagrams in the diagrams dict (keys: snake_case names).
- Use valid Mermaid v11 syntax only.
- subgraph titles: subgraph ID ["Title with space"] (space before bracket).
- Do NOT put port numbers inside node labels (use "PostgreSQL" not "PostgreSQL :5432").
- flowchart TD or LR; sequenceDiagram; erDiagram as appropriate.
- Keep diagram labels short and readable.
"""


def _srs_summary(srs_content: dict[str, Any]) -> str:
    frs = srs_content.get("functional_requirements", [])
    fr_lines = "\n".join(
        f"- {fr.get('fr_number', '')}: {fr.get('title', '')}"
        for fr in frs[:20]
        if isinstance(fr, dict)
    )
    nfrs = srs_content.get("nonfunctional_requirements", [])
    nfr_lines = "\n".join(
        f"- {nfr.get('category', '')}: {nfr.get('description', '')}"
        for nfr in nfrs[:8]
        if isinstance(nfr, dict)
    )
    return f"""
Introduction: {srs_content.get('introduction', '')}
Scope: {srs_content.get('scope', '')}
Functional requirements:
{fr_lines}
Non-functional requirements:
{nfr_lines}
"""


def _sanitize_doc_diagrams(doc: ArchitectureDocSchema) -> ArchitectureDocSchema:
    data = doc.model_dump()
    diagrams = data.get("diagrams") or {}
    data["diagrams"] = {
        name: sanitize_mermaid(src) for name, src in diagrams.items() if src
    }
    return ArchitectureDocSchema.model_validate(data)


async def generate_architecture_doc_ai(
    doc_key: str,
    doc_title: str,
    srs_content: dict[str, Any],
    project_name: str,
    project_description: str,
    prior_docs: dict[str, Any],
    instructions: str = "",
) -> ArchitectureDocSchema:
    """Generate one architecture suite document."""
    prior_summary = json.dumps(
        {k: v for k, v in prior_docs.items() if v},
        indent=2,
    )[:6000]

    extra = f"\nAdditional instructions:\n{instructions}" if instructions else ""

    prompts: dict[str, str] = {
        "doc_system_arch": f"""
Generate the System Architecture document for {project_name}.
Include: overview, architecture_pattern, tech_stack (layer/name/version/reason),
components (name/type/port/responsibility), data_flow steps,
diagrams (system_overview flowchart, component diagram).
{MERMAID_RULES}
""",
        "doc_database": f"""
Generate the Database Design document for {project_name}.
Include: overview, database engine, conventions object, tables with columns
(name/type/pk/nullable/default/purpose/linked_srs_entity), ER diagram in diagrams.
{MERMAID_RULES}
""",
        "doc_api": f"""
Generate the API Specification for {project_name}.
Include: overview, base_url, auth approach, endpoints array
(method, path or full_path, module, description, linked_fr, request_body, file).
Add diagrams for API overview and auth flow.
{MERMAID_RULES}
""",
        "doc_frontend": f"""
Generate the Frontend Architecture for {project_name}.
Include: overview, framework, styling, pages (path/description/file),
folder_structure tree object, diagrams for routes and component hierarchy.
{MERMAID_RULES}
""",
        "doc_security": f"""
Generate Security + RBAC document for {project_name}.
Include: overview, rbac.permission_matrix (resource/studio_owner/developer/client),
owasp_checklist (id/name/status/how), diagrams for auth and RBAC flow.
{MERMAID_RULES}
""",
        "doc_uiux": f"""
Generate UI/UX design guidance for {project_name}.
Include: overview, design_system.color_palette, ux_rules list,
diagrams for layout and user flows.
{MERMAID_RULES}
""",
    }

    prompt = f"""
You are a senior software architect producing the "{doc_title}" section.

Project: {project_name}
Description: {project_description or "N/A"}

SRS context:
{_srs_summary(srs_content)}

Previously generated architecture documents (stay consistent):
{prior_summary}

{prompts.get(doc_key, "Generate a complete architecture document.")}
{extra}

Return structured JSON. Field "overview" is required. Field "diagrams" must be a dict of
diagram_name -> mermaid source string.
"""

    system = (
        "You are an expert software architect. Produce implementation-ready technical "
        "architecture documents. Return strictly valid JSON matching the schema."
    )

    result = await ai_call(
        prompt=prompt,
        response_model=ArchitectureDocSchema,
        system=system,
        max_tokens=8000,
        task_type="arch_single_doc",
        screen="architecture",
    )
    return _sanitize_doc_diagrams(result)
