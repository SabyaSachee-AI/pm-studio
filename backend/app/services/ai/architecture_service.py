"""AI generation for the 6-document Architecture Suite — one doc at a time."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, Type
from uuid import UUID

from anthropic import RateLimitError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.architecture import Architecture
from app.services.ai.architecture_progress import (
    clear_architecture_context,
    set_architecture_context,
)
from app.schemas.architecture import (
    ApiChunkSchema,
    ApiSchema,
    ApiShellSchema,
    DatabaseSchema,
    DiagramMermaidSchema,
    FrontendSchema,
    SecuritySchema,
    SystemArchSchema,
    UiUxSchema,
)
from app.models.architecture import DOC_FIELDS
from app.services.ai.architecture_canon import (
    build_cross_doc_context,
    build_suite_canon_from_srs,
    format_canon_prompt_block,
)
from app.services.ai.architecture_consistency import (
    apply_deterministic_fixes,
    collect_docs_from_architecture,
    persist_fixed_docs,
    validate_suite,
)
from app.services.ai.base import ai_call
from app.services.ai.mermaid_sanitize import sanitize_doc_diagrams, sanitize_mermaid
from app.services.prd.source import resolve_prd_for_downstream
from app.services.requirement.source import get_finalized_draft, is_requirement_finalized

logger = logging.getLogger(__name__)

DOCUMENT_ORDER: list[tuple[str, str, Type[BaseModel]]] = [
    ("doc_system_arch", "Generating system architecture...", SystemArchSchema),
    ("doc_database", "Generating database design...", DatabaseSchema),
    ("doc_api", "Generating API specification...", ApiSchema),
    ("doc_frontend", "Generating frontend architecture...", FrontendSchema),
    ("doc_security", "Generating security plan...", SecuritySchema),
    ("doc_uiux", "Generating UI/UX guidance...", UiUxSchema),
]

ARCH_DOC_KEYS: list[tuple[str, str]] = [
    (key, title.removeprefix("Generating ").removesuffix("...").strip().capitalize())
    for key, title, _ in DOCUMENT_ORDER
]

COMPLETED_STATUSES = frozenset({"completed", "generated"})

# Diagrams built on the frontend from structured doc data — not AI-regeneratable.
PROGRAMMATIC_DIAGRAMS: dict[str, frozenset[str]] = {
    "doc_system_arch": frozenset({"system_overview", "data_flow"}),
    "doc_database": frozenset({"erd"}),
    "doc_api": frozenset({"auth_flow", "request_flow"}),
    "doc_frontend": frozenset({"routing", "component_tree"}),
    "doc_security": frozenset({"auth_flow", "rbac"}),
}

# Expected AI-only diagram slots per document (shown even when missing).
AI_DIAGRAM_SLOTS: dict[str, list[str]] = {
    "doc_system_arch": ["deployment"],
    "doc_security": ["rbac_flow"],
    "doc_uiux": ["user_flow", "page_layout"],
}

DIAGRAM_TYPE_HINTS: dict[str, str] = {
    "deployment": "flowchart TD showing infrastructure deployment (servers, containers, cloud services, ports)",
    "data_flow": "flowchart LR showing data flow between system components",
    "request_flow": "sequenceDiagram showing a typical authenticated API request lifecycle",
    "rbac_flow": "flowchart LR showing RBAC authorization from JWT to role permissions",
    "user_flow": "flowchart TD showing primary user journeys through the application",
    "page_layout": "flowchart TD showing page layout sections and component hierarchy",
}


def is_diagram_regeneratable(
    doc_field: str,
    diagram_name: str,
    existing_doc: dict[str, Any] | None,
) -> bool:
    """Return True when a diagram may be (re)generated via targeted AI."""
    if diagram_name in PROGRAMMATIC_DIAGRAMS.get(doc_field, frozenset()):
        return False
    diagrams = (existing_doc or {}).get("diagrams") or {}
    if isinstance(diagrams, dict) and diagram_name in diagrams:
        return True
    return diagram_name in AI_DIAGRAM_SLOTS.get(doc_field, [])


async def run_single_architecture_diagram(
    architecture_id: UUID,
    doc_field: str,
    diagram_name: str,
    db: Session,
) -> dict[str, str]:
    """Generate or fix one AI diagram and patch doc.diagrams[name] only."""
    arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
    if not arch:
        return {"error": "Architecture not found", "doc_key": doc_field, "diagram_name": diagram_name}

    from app.models.prd import PRD  # noqa: PLC0415
    from app.models.project import Project  # noqa: PLC0415
    from app.models.srs import SRS  # noqa: PLC0415

    existing_doc = getattr(arch, doc_field, None)
    if not existing_doc or not isinstance(existing_doc, dict):
        return {"error": "Document has no content", "doc_key": doc_field, "diagram_name": diagram_name}

    if not is_diagram_regeneratable(doc_field, diagram_name, existing_doc):
        return {
            "error": "This diagram is built from document data; use document regenerate instead",
            "doc_key": doc_field,
            "diagram_name": diagram_name,
        }

    srs = db.query(SRS).filter(SRS.id == arch.srs_id).first()
    project = db.query(Project).filter(Project.id == arch.project_id).first()
    if not srs or not srs.content_json:
        return {"error": "SRS has no content", "doc_key": doc_field, "diagram_name": diagram_name}

    project_name = project.name if project else "Project"
    doc_context = {k: v for k, v in existing_doc.items() if k != "diagrams"}
    doc_context_json = json.dumps(doc_context, separators=(",", ":"), default=str)[:12000]
    broken = str((existing_doc.get("diagrams") or {}).get(diagram_name) or "")

    type_hint = DIAGRAM_TYPE_HINTS.get(
        diagram_name,
        f"Mermaid {diagram_name.replace('_', ' ')} diagram for this architecture document",
    )
    prompt = f"""Generate ONE Mermaid diagram named "{diagram_name}" for the architecture document "{doc_field}".

Project: {project_name}

DOCUMENT CONTENT (use as source of truth):
{doc_context_json}

Diagram purpose: {type_hint}
"""
    if broken.strip():
        prompt += (
            f"\nPREVIOUS ATTEMPT (invalid Mermaid — fix syntax, preserve intent):\n"
            f"{broken[:4000]}\n"
        )
    prompt += MERMAID_RULES
    prompt += '\n\nReturn ONLY valid Mermaid source in the "mermaid" field. No markdown fences.'

    status_msg = f"Regenerating {diagram_name.replace('_', ' ')} diagram..."
    arch.generation_progress = {
        "current_doc": doc_field,
        "phase": "diagram",
        "diagram_name": diagram_name,
        "message": status_msg,
    }
    arch.last_error = None
    db.commit()

    set_architecture_context(architecture_id, doc_field)
    await update_job_status(architecture_id, "processing", message=status_msg)

    try:
        result = await ai_call(
            prompt=prompt,
            response_model=DiagramMermaidSchema,
            system=(
                "You are a senior software architect. Output strictly valid Mermaid syntax. "
                "Return structured JSON with a single mermaid field."
            ),
            max_tokens=4000,
            task_type="arch_generate",
            screen="architecture",
        )
        mermaid = sanitize_mermaid(result.mermaid)
        if not mermaid:
            raise ValueError("AI returned empty diagram")

        updated_doc = dict(existing_doc)
        diagrams = dict(updated_doc.get("diagrams") or {})
        diagrams[diagram_name] = mermaid
        updated_doc["diagrams"] = diagrams
        setattr(arch, doc_field, updated_doc)
        arch.generation_progress = None
        arch.generation_task_id = None
        db.commit()
        await update_job_status(architecture_id, "completed", message=f"{diagram_name} diagram ready")
        return {
            "status": "completed",
            "doc_key": doc_field,
            "diagram_name": diagram_name,
        }
    except Exception as exc:
        logger.exception(
            "Architecture diagram regeneration failed",
            extra={"doc": doc_field, "diagram": diagram_name, "arch_id": str(architecture_id)},
        )
        arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
        if arch is not None:
            # A single diagram failing is non-critical — never poison the
            # suite-level last_error / generation_task_id (the docs are fine).
            arch.generation_progress = None
            arch.generation_task_id = None
            db.commit()
        return {
            "error": str(exc)[:500],
            "doc_key": doc_field,
            "diagram_name": diagram_name,
            "status": "failed",
        }
    finally:
        clear_architecture_context()


def _srs_summary(srs_content: dict[str, Any]) -> str:
    # All arch models in HEAVY_FREE_TAIL have ≥128K context — no truncation needed.
    # Compact JSON (no indent) keeps tokens low without losing any FR/NFR coverage.
    return json.dumps(
        {
            "functional_requirements": srs_content.get("functional_requirements", []),
            "non_functional_requirements": srs_content.get("non_functional_requirements", []),
            "data_requirements": srs_content.get("data_requirements", {}),
            "system_interfaces": srs_content.get("system_interfaces", {}),
            "security_requirements": srs_content.get("security_requirements", []),
            "introduction": srs_content.get("introduction", {}),
            "overall_description": srs_content.get("overall_description", {}),
        },
        separators=(",", ":"),
        default=str,
    )


def _requirements_brief(requirements: list[Any]) -> str:
    """Compact JSON summary of finalized requirements for architecture context."""
    rows: list[dict[str, Any]] = []
    for req in requirements:
        analysis = req.analysis_result or {}
        if not is_requirement_finalized(analysis):
            continue
        draft = get_finalized_draft(analysis)
        if not draft:
            continue
        rows.append(
            {
                "file": req.original_filename,
                "project_overview": (draft.get("project_overview") or "")[:500],
                "confirmed_features": (draft.get("confirmed_features") or [])[:20],
                "technical_decisions": (draft.get("technical_decisions") or [])[:20],
                "out_of_scope": (draft.get("out_of_scope") or [])[:10],
                "users_and_roles": (draft.get("users_and_roles") or "")[:300],
            }
        )
    if not rows:
        return ""
    return json.dumps(rows, separators=(",", ":"), default=str)


def _prd_brief_block(prd_content: dict[str, Any] | None) -> str:
    """Compact PRD context block appended to architecture prompts."""
    if not prd_content:
        return ""
    prd_brief = {
        "executive_summary": (prd_content.get("executive_summary") or "")[:1000],
        "features": [
            {
                "title": f.get("title", ""),
                "description": (f.get("description") or "")[:300],
                "priority": f.get("priority", ""),
            }
            for f in (prd_content.get("features") or [])
        ],
        "out_of_scope": prd_content.get("out_of_scope") or [],
        "success_metrics": prd_content.get("success_metrics") or [],
    }
    return f"\n\nPRD CONTEXT:\n{json.dumps(prd_brief, separators=(',', ':'), default=str)}"


_AVAILABILITY_DOWNTIME = {
    "99": "~14.4 min/day, 7.3 hr/month",
    "99.9": "~1.44 min/day, 43.8 min/month",
    "99.99": "~8.6 s/day, 4.4 min/month",
    "99.999": "~0.86 s/day, 26 s/month",
}


def _nfr_brief_block(nfr_profile: dict[str, Any] | None) -> str:
    """Compact non-functional constraints block — drives right-sized design."""
    if not nfr_profile:
        return ""
    p = nfr_profile
    avail = str(p.get("availability") or "").replace("%", "")
    budget = _AVAILABILITY_DOWNTIME.get(avail, "")
    fields = {
        "expected_scale": p.get("scale"),
        "availability_target": (f"{avail}% ({budget})" if budget else (p.get("availability") or None)),
        "latency_target": p.get("latency"),
        "rto": p.get("rto"),
        "rpo": p.get("rpo"),
        "compliance": p.get("compliance"),
        "budget_tier": p.get("budget"),
        "time_to_market": p.get("time_to_market"),
        "deploy_target": p.get("deploy_target"),
    }
    fields = {k: v for k, v in fields.items() if v}
    if not fields:
        return ""
    return (
        "\n\nNON-FUNCTIONAL CONSTRAINTS (the design MUST meet these and be RIGHT-SIZED "
        "to them — do NOT over-engineer beyond the stated scale/budget, and do NOT "
        "under-provision below the availability/RTO/RPO targets):\n"
        + json.dumps(fields, separators=(",", ":"), default=str)
    )


_RELIABILITY_INSTRUCTION = (
    "\n\nAlso populate a 'reliability' object for this system document, sized to the "
    "constraints above: {availability_target, downtime_budget, rto, rpo, "
    "backup_and_dr, failure_modes:[{component,failure,mitigation}], redundancy, "
    "scaling_strategy, capacity_assumptions, performance_targets}."
)

_CAPABILITY_LINES = {
    "pwa": "Installable PWA — web app manifest, service worker, app icons, 'add to home screen', mobile-first responsive layout.",
    "offline": "Offline support — cache the app shell + key data; work without network and sync on reconnect.",
    "voice": "Voice input — microphone capture (MediaRecorder / Web Speech API) + speech-to-text; handle mic permissions and errors.",
    "camera": "Camera — photo/video capture with permission handling.",
    "geolocation": "Geolocation — location access with permission handling.",
    "integration_api": "Public integration API — API-key auth, webhooks for key events, and a published OpenAPI/Swagger spec so other systems can connect.",
}


def _capabilities_block(capabilities: dict[str, Any] | None) -> str:
    """Optional capability requirements injected into architecture prompts."""
    if not capabilities:
        return ""
    lines = [_CAPABILITY_LINES[k] for k in _CAPABILITY_LINES if capabilities.get(k)]
    if not lines:
        return ""
    return (
        "\n\nREQUIRED CAPABILITIES (design and implement these explicitly across the "
        "relevant documents — frontend, API, security):\n- " + "\n- ".join(lines)
    )


MERMAID_RULES = """
MERMAID DIAGRAM RULES — follow exactly or the diagram will fail to render:
- flowchart: start with "flowchart TD" or "flowchart LR". Node IDs must be alphanumeric (A, API, DB1). Labels with spaces/colons must use quotes: A["Label with spaces"]. Arrows: A --> B or A --> B["label"]. subgraph must end with "end".
- erDiagram: start with "erDiagram" (no direction keyword). Entity names UPPERCASE. Relations: ENTITY1 ||--o{ ENTITY2 : "label". Attributes on next lines after entity name block.
- sequenceDiagram: participant aliases must be quoted if they contain spaces: participant A as "API Server". Arrows: A ->> B: message. Never use "->", always "->>".
- NEVER use: classDef, class, style, linkStyle, %% comments, note left/right (sequence-only). Do NOT wrap in ```mermaid blocks.
"""


def _doc_prompt(
    doc_field: str,
    srs_summary: str,
    project_name: str,
    project_type: str,
) -> str:
    prompts = {
        "doc_system_arch": f"""
Generate the System Architecture document for {project_name} ({project_type}).

SRS context:
{srs_summary}

Include: overview, architecture_pattern, tech_stack (Next.js 14, FastAPI, PostgreSQL, Redis, Celery),
components with ports, data_flow steps, infrastructure, and Mermaid flowcharts in diagrams
(system_overview, deployment).
{MERMAID_RULES}
""",
        "doc_database": f"""
Generate the Database Design document for {project_name}.

SRS context:
{srs_summary}

Include: overview, PostgreSQL conventions, tables linked to SRS data entities with columns/indexes,
relationships, migration_order, and Mermaid erDiagram in diagrams.erd.
{MERMAID_RULES}
""",
        "doc_api": f"""
Generate the API Specification for {project_name}.

SRS context:
{srs_summary}

Include: REST endpoints at /api/v1 linked to SRS FR ids, auth (JWT HttpOnly cookies),
request/response bodies, error codes, file paths, and Mermaid sequence diagrams
(auth_flow, request_flow).
{MERMAID_RULES}
""",
        "doc_frontend": f"""
Generate the Frontend Architecture for {project_name}.

SRS context:
{srs_summary}

Include: Next.js 14 App Router pages, components, api_calls, folder_structure,
and Mermaid diagrams (component_tree, routing).
{MERMAID_RULES}
""",
        "doc_security": f"""
Generate the Security + RBAC plan for {project_name}.

SRS context:
{srs_summary}

Include: JWT auth mechanism, RBAC roles/permission_matrix, api_security controls,
OWASP checklist, and Mermaid diagrams (auth_flow, rbac_flow).
{MERMAID_RULES}
""",
        "doc_uiux": f"""
Generate UI/UX Design Guidance for {project_name}.

SRS context:
{srs_summary}

Include: design_system (colors, typography), page sections/components, ux_rules,
and Mermaid diagrams (user_flow, page_layout).
{MERMAID_RULES}
""",
    }
    return prompts.get(doc_field, f"Generate architecture document {doc_field}.")


async def generate_single_document(
    doc_field: str,
    srs_content: dict[str, Any],
    project_info: dict[str, Any],
    prd_content: dict[str, Any] | None = None,
    *,
    task_type: str = "arch_generate",
    suite_canon: dict[str, Any] | None = None,
    cross_doc_context: str = "",
    instructions: str = "",
    existing_doc: dict[str, Any] | None = None,
    requirements_context: str = "",
    nfr_profile: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate one architecture document via AI."""
    schema = next(s for f, _, s in DOCUMENT_ORDER if f == doc_field)
    srs_summary = _srs_summary(srs_content)
    prompt = _doc_prompt(
        doc_field,
        srs_summary,
        project_info.get("name", "Project"),
        project_info.get("type", "Web App"),
    )
    if suite_canon:
        prompt += f"\n\n{format_canon_prompt_block(suite_canon)}"
    if cross_doc_context:
        prompt += f"\n\nPRIOR DOCUMENTS:\n{cross_doc_context}"
    prompt += _prd_brief_block(prd_content)
    # Non-functional constraints drive right-sized, reliability-aware design.
    nfr_block = _nfr_brief_block(nfr_profile)
    if nfr_block:
        prompt += nfr_block
        if doc_field == "doc_system_arch":
            prompt += _RELIABILITY_INSTRUCTION
    prompt += _capabilities_block(capabilities)
    if requirements_context:
        prompt += f"\n\nORIGINAL REQUIREMENTS (source of truth — features/decisions confirmed by client):\n{requirements_context}"
    if existing_doc:
        prompt += f"\n\nEXISTING DOCUMENT (revise):\n{json.dumps(existing_doc)[:8000]}"
    if instructions.strip():
        prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{instructions.strip()}"
    system = (
        "You are a senior software architect. Return strictly structured JSON. "
        "Mermaid diagram strings must use valid syntax."
    )
    result = await ai_call(
        prompt=prompt,
        response_model=schema,
        system=system,
        max_tokens=16000,  # router clamps per provider (Gemini 24K, Groq 8K, etc.)
        task_type=task_type,
        screen="architecture",
    )
    doc = sanitize_doc_diagrams(result.model_dump())
    return doc


def _is_doc_cancel_requested(arch: Architecture, doc_field: str) -> bool:
    flags = arch.doc_cancel_flags or {}
    return bool(flags.get(doc_field))


def _clear_doc_cancel_flag(db: Session, arch: Architecture, doc_field: str) -> None:
    flags = dict(arch.doc_cancel_flags or {})
    flags.pop(doc_field, None)
    arch.doc_cancel_flags = flags or None
    db.flush()


async def generate_single_doc_with_instructions(
    doc_field: str,
    srs_content: dict[str, Any],
    project_info: dict[str, Any],
    *,
    existing_doc: dict[str, Any] | None = None,
    instructions: str = "",
    prd_content: dict[str, Any] | None = None,
    suite_canon: dict[str, Any] | None = None,
    cross_doc_context: str = "",
    task_type: str = "arch_generate",
    requirements_context: str = "",
    nfr_profile: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await generate_single_document(
        doc_field,
        srs_content,
        project_info,
        prd_content,
        task_type=task_type,
        suite_canon=suite_canon,
        cross_doc_context=cross_doc_context,
        instructions=instructions,
        existing_doc=existing_doc,
        requirements_context=requirements_context,
        nfr_profile=nfr_profile,
        capabilities=capabilities,
    )


async def generate_api_document_chunked(
    arch: Architecture,
    db: Session,
    srs_content: dict[str, Any],
    project_info: dict[str, Any],
    *,
    prd_content: dict[str, Any] | None = None,
    suite_canon: dict[str, Any] | None = None,
    cross_doc_context: str = "",
    task_type: str = "arch_generate",
    requirements_context: str = "",
    nfr_profile: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate API doc in chunks — shell first, then endpoint groups by FR batch."""
    srs_summary = _srs_summary(srs_content)
    project_name = project_info.get("name", "Project")
    project_type = project_info.get("type", "Web App")

    progress = dict(arch.generation_progress or {})
    chunk_state: dict[str, Any] = dict(progress.get("api_chunk_state") or {})

    def _fr_groups() -> list[list[dict[str, Any]]]:
        frs = [
            fr
            for fr in srs_content.get("functional_requirements", [])
            if isinstance(fr, dict)
        ]
        if not frs:
            return [[]]
        chunk_size = 5
        return [frs[i : i + chunk_size] for i in range(0, len(frs), chunk_size)]

    if not chunk_state.get("fr_groups"):
        chunk_state["fr_groups"] = _fr_groups()
        chunk_state["total_chunks"] = len(chunk_state["fr_groups"])
        chunk_state["completed_chunks"] = []
        chunk_state["endpoints"] = []

    fr_groups: list[list[dict[str, Any]]] = chunk_state["fr_groups"]
    completed_chunks: set[int] = set(chunk_state.get("completed_chunks") or [])
    merged_endpoints: list[dict[str, Any]] = list(chunk_state.get("endpoints") or [])
    shell_data: dict[str, Any] = dict(chunk_state.get("shell") or {})

    def persist_chunk_state(*, message: str) -> None:
        chunk_state["completed_chunks"] = sorted(completed_chunks)
        chunk_state["endpoints"] = merged_endpoints
        if shell_data:
            chunk_state["shell"] = shell_data
            chunk_state["shell_completed"] = True
        progress.update(
            {
                "current_doc": "doc_api",
                "phase": "generating",
                "message": message,
                "api_chunk_state": chunk_state,
            }
        )
        arch.generation_progress = progress
        db.commit()
        db.refresh(arch)

    base_prompt = _doc_prompt("doc_api", srs_summary, project_name, project_type)
    if suite_canon:
        base_prompt += f"\n\n{format_canon_prompt_block(suite_canon)}"
    if cross_doc_context:
        base_prompt += f"\n\nPRIOR DOCUMENTS:\n{cross_doc_context}"
    base_prompt += _prd_brief_block(prd_content)
    base_prompt += _nfr_brief_block(nfr_profile)
    base_prompt += _capabilities_block(capabilities)
    if requirements_context:
        base_prompt += f"\n\nORIGINAL REQUIREMENTS (source of truth):\n{requirements_context}"

    system = (
        "You are a senior software architect. Return strictly structured JSON. "
        "Mermaid diagram strings must use valid syntax."
    )

    if not chunk_state.get("shell_completed"):
        await update_job_status(
            arch.id,
            "processing",
            message="Generating API document shell…",
        )
        shell_result = await ai_call(
            prompt=base_prompt
            + "\n\nGenerate ONLY the API document shell: overview, base_url, auth, "
            "versioning, response_format, global_headers, and diagrams. "
            "Leave endpoints empty — they will be generated in separate calls.",
            response_model=ApiShellSchema,
            system=system,
            max_tokens=8000,
            task_type=task_type,
            screen="architecture",
        )
        shell_data = sanitize_doc_diagrams(shell_result.model_dump())
        persist_chunk_state(message="API shell complete — generating endpoint chunks…")

    total = len(fr_groups)
    for idx, fr_group in enumerate(fr_groups):
        if idx in completed_chunks:
            continue

        fr_labels = ", ".join(
            str(fr.get("fr_number", "")) for fr in fr_group if fr.get("fr_number")
        ) or f"group {idx + 1}"
        await update_job_status(
            arch.id,
            "processing",
            message=f"Generating API endpoints chunk {idx + 1}/{total} ({fr_labels})…",
        )

        fr_block = json.dumps(fr_group, indent=2, default=str)[:6000]
        chunk_prompt = (
            f"{base_prompt}\n\n"
            f"Generate REST endpoints ONLY for these functional requirements:\n{fr_block}\n\n"
            "Return endpoints linked to the FR ids above. Use /api/v1 paths, JWT auth, "
            "request/response bodies, error codes, and file paths. "
            "Do not repeat endpoints from other FR groups."
        )
        if merged_endpoints:
            existing_ids = [
                ep.get("id") or ep.get("path", "")
                for ep in merged_endpoints[:20]
                if isinstance(ep, dict)
            ]
            chunk_prompt += (
                f"\n\nAlready generated endpoint ids/paths (do not duplicate):\n"
                f"{json.dumps(existing_ids)}"
            )

        chunk_result = await ai_call(
            prompt=chunk_prompt,
            response_model=ApiChunkSchema,
            system=system,
            max_tokens=8000,
            task_type=task_type,
            screen="architecture",
        )
        for ep in chunk_result.endpoints:
            merged_endpoints.append(ep.model_dump())
        completed_chunks.add(idx)
        persist_chunk_state(
            message=f"Completed API chunk {idx + 1}/{total}",
        )

    result = {**shell_data, "endpoints": merged_endpoints}
    return sanitize_doc_diagrams(result)


def _rate_limit_wait_seconds(exc: RateLimitError) -> int:
    retry_after = 60
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is not None:
            try:
                retry_after = max(1, int(raw))
            except (TypeError, ValueError):
                pass
    return retry_after


async def update_job_status(
    architecture_id: UUID,
    status: str,
    message: str = "",
) -> None:
    """Update Celery task meta for optional SSE consumers."""
    try:
        from celery import current_task

        task = current_task
        if task and getattr(task, "request", None) and task.request.id:
            task.update_state(
                state="PROGRESS",
                meta={
                    "architecture_id": str(architecture_id),
                    "status": status,
                    "message": message,
                },
            )
    except Exception:
        pass


async def run_single_architecture_doc(
    architecture_id: UUID,
    doc_field: str,
    db: Session,
    *,
    instructions: str = "",
    task_type: str = "arch_generate",
) -> dict[str, str]:
    """Generate or regenerate one architecture document and persist the result."""
    arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
    if not arch:
        return {"error": "Architecture not found", "doc_key": doc_field}

    from app.models.prd import PRD  # noqa: PLC0415
    from app.models.project import Project  # noqa: PLC0415
    from app.models.srs import SRS  # noqa: PLC0415

    srs = db.query(SRS).filter(SRS.id == arch.srs_id).first()
    project = db.query(Project).filter(Project.id == arch.project_id).first()
    if not srs or not srs.content_json:
        return {"error": "SRS has no content", "doc_key": doc_field}

    prd = db.query(PRD).filter(PRD.id == srs.prd_id).first() if srs.prd_id else None
    prd_content = None
    if prd and prd.content_json:
        prd_content, _ = resolve_prd_for_downstream(prd)
    project_info = {
        "name": project.name if project else "Unknown Project",
        "type": "Web App",
        "description": project.description if project else "",
    }

    from app.models.requirement import Requirement  # noqa: PLC0415
    reqs = (
        db.query(Requirement)
        .filter(
            Requirement.project_id == arch.project_id,
            Requirement.deleted_at.is_(None),
        )
        .all()
    )
    requirements_context = _requirements_brief(reqs)
    nfr_profile = getattr(arch, "nfr_profile", None)
    capabilities = getattr(arch, "capabilities", None)

    suite_canon = getattr(arch, "suite_canon", None) or build_suite_canon_from_srs(
        srs.content_json,
        project_info["name"],
        project_info.get("description", ""),
    )
    cross_doc_context = build_cross_doc_context(arch, doc_field)

    status_field = f"{doc_field}_status"
    status_msg = next(
        (msg for field, msg, _ in DOCUMENT_ORDER if field == doc_field),
        f"Generating {doc_field}...",
    )

    if _is_doc_cancel_requested(arch, doc_field):
        setattr(arch, status_field, "pending")
        arch.generation_progress = None
        _clear_doc_cancel_flag(db, arch, doc_field)
        db.commit()
        return {"status": "cancelled", "doc_key": doc_field}

    setattr(arch, status_field, "processing")
    prev_progress = arch.generation_progress or {}
    new_progress: dict[str, Any] = {
        "current_doc": doc_field,
        "phase": "generating",
        "message": status_msg,
    }
    # Keep partially generated API chunks so a retry resumes mid-doc
    if (
        doc_field == "doc_api"
        and prev_progress.get("current_doc") == "doc_api"
        and prev_progress.get("api_chunk_state")
    ):
        new_progress["api_chunk_state"] = prev_progress["api_chunk_state"]
    arch.generation_progress = new_progress
    arch.last_error = None
    db.commit()
    db.refresh(arch)

    set_architecture_context(architecture_id, doc_field)
    await update_job_status(architecture_id, "processing", message=status_msg)

    try:
        existing_doc = getattr(arch, doc_field, None)
        if instructions.strip():
            result = await generate_single_doc_with_instructions(
                doc_field,
                srs.content_json,
                project_info,
                existing_doc=existing_doc,
                instructions=instructions,
                prd_content=prd_content,
                suite_canon=suite_canon,
                cross_doc_context=cross_doc_context,
                requirements_context=requirements_context,
                nfr_profile=nfr_profile,
                capabilities=capabilities,
            )
        elif doc_field == "doc_api":
            result = await generate_api_document_chunked(
                arch,
                db,
                srs.content_json,
                project_info,
                prd_content=prd_content,
                suite_canon=suite_canon,
                cross_doc_context=cross_doc_context,
                task_type=task_type,
                requirements_context=requirements_context,
                nfr_profile=nfr_profile,
                capabilities=capabilities,
            )
        else:
            result = await generate_single_document(
                doc_field,
                srs.content_json,
                project_info,
                prd_content,
                task_type=task_type,
                suite_canon=suite_canon,
                cross_doc_context=cross_doc_context,
                requirements_context=requirements_context,
                nfr_profile=nfr_profile,
                capabilities=capabilities,
            )

        arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
        if arch is None:
            return {"error": "Architecture not found", "doc_key": doc_field}

        if _is_doc_cancel_requested(arch, doc_field):
            setattr(arch, status_field, "pending")
            arch.generation_progress = None
            _clear_doc_cancel_flag(db, arch, doc_field)
            db.commit()
            return {"status": "cancelled", "doc_key": doc_field}

        setattr(arch, doc_field, result)
        setattr(arch, status_field, "completed")
        arch.suite_canon = suite_canon
        arch.generation_progress = None
        arch.last_error = None
        arch.generation_task_id = None
        task_ids = dict(arch.doc_task_ids or {})
        task_ids.pop(doc_field, None)
        arch.doc_task_ids = task_ids
        db.commit()

        arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
        if arch and all(
            getattr(arch, f"{f}_status") in COMPLETED_STATUSES for f, _, _ in DOCUMENT_ORDER
        ):
            arch.can_resume = False
            arch.resume_from = None
            db.commit()
            await consolidate_architecture_suite(architecture_id, db)

        return {"status": "completed", "doc_key": doc_field}

    except Exception as exc:
        logger.exception(
            "Architecture doc generation failed",
            extra={"doc": doc_field, "arch_id": str(architecture_id)},
        )
        arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
        if arch is not None:
            setattr(arch, status_field, "failed")
            arch.can_resume = True
            arch.last_error = str(exc)[:500]
            arch.resume_from = doc_field
            failed_progress: dict[str, Any] = {
                "current_doc": doc_field,
                "phase": "failed",
                "message": str(exc)[:200],
            }
            # Keep completed API chunks so resume continues from the failed chunk
            chunk_state = (arch.generation_progress or {}).get("api_chunk_state")
            if doc_field == "doc_api" and chunk_state:
                failed_progress["api_chunk_state"] = chunk_state
            arch.generation_progress = failed_progress
            task_ids = dict(arch.doc_task_ids or {})
            task_ids.pop(doc_field, None)
            arch.doc_task_ids = task_ids
            db.commit()
        return {"error": str(exc)[:500], "doc_key": doc_field, "status": "failed"}
    finally:
        clear_architecture_context()


async def generate_full_architecture(
    architecture_id: UUID,
    srs_content: dict[str, Any],
    project_info: dict[str, Any],
    db: Session,
    resume: bool = False,
    prd_content: dict[str, Any] | None = None,
    requirements_context: str = "",
    nfr_profile: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Generate documents one at a time, saving after each."""
    arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
    if not arch:
        return {"error": "Architecture not found"}
    if nfr_profile is None:
        nfr_profile = getattr(arch, "nfr_profile", None)
    capabilities = getattr(arch, "capabilities", None)

    arch.can_resume = False
    arch.last_error = None
    arch.resume_from = None
    db.commit()

    completed_count = 0

    for doc_field, status_msg, _schema in DOCUMENT_ORDER:
        status_field = f"{doc_field}_status"
        current_status = getattr(arch, status_field, "pending")

        if resume and current_status in COMPLETED_STATUSES:
            completed_count += 1
            continue

        setattr(arch, status_field, "processing")
        db.commit()
        db.refresh(arch)

        await update_job_status(architecture_id, "processing", message=status_msg)

        try:
            result = await generate_single_document(
                doc_field, srs_content, project_info, prd_content,
                requirements_context=requirements_context,
                nfr_profile=nfr_profile,
                capabilities=capabilities,
            )
            setattr(arch, doc_field, result)
            setattr(arch, status_field, "completed")
            arch.resume_from = None
            db.commit()
            db.refresh(arch)
            completed_count += 1

        except RateLimitError as exc:
            wait_seconds = _rate_limit_wait_seconds(exc)
            setattr(arch, status_field, "rate_limited")
            arch.last_error = f"Rate limit hit on {doc_field}"
            arch.can_resume = True
            arch.resume_from = doc_field
            db.commit()
            db.refresh(arch)

            await update_job_status(
                architecture_id,
                "rate_limited",
                message=f"Rate limit reached. Waiting {wait_seconds}s...",
            )
            await asyncio.sleep(wait_seconds)

            try:
                result = await generate_single_document(
                    doc_field, srs_content, project_info, prd_content,
                    requirements_context=requirements_context,
                    nfr_profile=nfr_profile,
                )
                setattr(arch, doc_field, result)
                setattr(arch, status_field, "completed")
                arch.can_resume = False
                arch.last_error = None
                arch.resume_from = None
                db.commit()
                db.refresh(arch)
                completed_count += 1
            except Exception as retry_error:
                logger.exception(
                    "Architecture doc retry failed",
                    extra={"doc": doc_field, "arch_id": str(architecture_id)},
                )
                setattr(arch, status_field, "failed")
                arch.can_resume = True
                arch.last_error = str(retry_error)[:500]
                arch.resume_from = doc_field
                db.commit()
                break

        except Exception as exc:
            logger.exception(
                "Architecture doc generation failed",
                extra={"doc": doc_field, "arch_id": str(architecture_id)},
            )
            setattr(arch, status_field, "failed")
            arch.can_resume = True
            arch.last_error = str(exc)[:500]
            arch.resume_from = doc_field
            db.commit()
            break

    arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
    if arch is None:
        return {"error": "Architecture not found"}

    all_done = all(
        getattr(arch, f"{f}_status") in COMPLETED_STATUSES for f, _, _ in DOCUMENT_ORDER
    )
    if all_done:
        arch.can_resume = False
        arch.last_error = None
        arch.resume_from = None
        db.commit()
        consolidate_report = await consolidate_architecture_suite(architecture_id, db)
        return {
            "architecture_id": str(architecture_id),
            "status": "completed",
            "docs_completed": "6",
            "consistency_overall": str(consolidate_report.get("overall", "")),
        }

    first_missing = next(
        (
            f
            for f, _, _ in DOCUMENT_ORDER
            if getattr(arch, f"{f}_status") not in COMPLETED_STATUSES
        ),
        None,
    )
    arch.can_resume = True
    if first_missing and not arch.resume_from:
        arch.resume_from = first_missing
    if not arch.last_error and first_missing:
        arch.last_error = f"Incomplete suite — {first_missing.replace('doc_', '')} not generated"
    db.commit()

    return {
        "architecture_id": str(architecture_id),
        "status": "partial",
        "docs_completed": str(completed_count),
        "can_resume": "true",
        "resume_from": arch.resume_from or (first_missing or ""),
        "error": arch.last_error or "",
    }


def build_architecture_context_for_task(
    architecture: Any,
    fr_references: list[str],
) -> str:
    """Extract architecture context for task spec generation."""
    if architecture is None:
        return ""

    doc_api = architecture.doc_api or {}
    doc_db = architecture.doc_database or {}
    doc_fe = architecture.doc_frontend or {}
    doc_sec = architecture.doc_security or {}

    endpoints = doc_api.get("endpoints", [])
    linked_eps = [
        ep
        for ep in endpoints
        if ep.get("linked_fr") in fr_references
        or any(fr in str(ep.get("description", "")) for fr in fr_references)
    ]
    if not linked_eps and endpoints:
        linked_eps = endpoints[:3]

    tables = doc_db.get("tables", [])
    pages = doc_fe.get("pages", [])

    files_to_modify: list[str] = []
    for ep in linked_eps:
        if ep.get("file"):
            files_to_modify.append(ep["file"])
    for page in pages[:5]:
        if page.get("file"):
            files_to_modify.append(page["file"])

    security_lines = [
        f"- {item.get('control', '')}: {item.get('implementation', '')}"
        for item in (doc_sec.get("api_security") or [])[:5]
    ]

    ep_lines = []
    for ep in linked_eps[:3]:
        ep_lines.append(
            f"- {ep.get('method', 'GET')} {ep.get('full_path', ep.get('path', ''))}\n"
            f"  Auth: {'required' if ep.get('auth_required', True) else 'none'}\n"
            f"  Request: {json.dumps(ep.get('request_body', {}))}\n"
            f"  Response: {json.dumps(ep.get('response_200', {}))}"
        )

    table_lines = []
    for tbl in tables[:4]:
        cols = ", ".join(c.get("name", "") for c in (tbl.get("columns") or [])[:8])
        table_lines.append(f"- Table: {tbl.get('name', '')}\n  Columns: {cols}")

    return f"""
Architecture context for this task:

FILES TO MODIFY:
{chr(10).join(f'- {f}' for f in dict.fromkeys(files_to_modify)) or '- See SRS FR implementation'}

DATABASE:
{chr(10).join(table_lines) or '- Derive from SRS data entities'}

API ENDPOINTS:
{chr(10).join(ep_lines) or '- Define REST endpoint per FR'}

SECURITY:
{chr(10).join(security_lines) or '- Validate inputs with Pydantic; enforce RBAC'}
- Always use soft delete (set deleted_at, never hard DELETE)
"""


async def consolidate_architecture_suite(
    architecture_id: UUID,
    db: Session,
    *,
    ai_repair: bool = False,
) -> dict[str, Any]:
    """Apply deterministic cross-doc alignment and persist consistency scores."""
    arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
    if not arch:
        return {"error": "Architecture not found"}

    from app.models.project import Project  # noqa: PLC0415
    from app.models.srs import SRS  # noqa: PLC0415

    srs = db.query(SRS).filter(SRS.id == arch.srs_id).first()
    if not srs or not srs.content_json:
        return {"error": "SRS has no content"}

    project = db.query(Project).filter(Project.id == arch.project_id).first()
    project_name = project.name if project else "Project"
    canon = getattr(arch, "suite_canon", None) or build_suite_canon_from_srs(
        srs.content_json,
        project_name,
        project.description if project else "",
    )

    docs = collect_docs_from_architecture(arch)
    nfr_profile = getattr(arch, "nfr_profile", None)
    fixed = apply_deterministic_fixes(docs, srs.content_json, canon)
    report = validate_suite(fixed, srs.content_json, canon, nfr_profile=nfr_profile)

    if ai_repair and report.get("overall", 0) < 9.5:
        repair_fields = []
        scores = report.get("scores") or {}
        if scores.get("srs_traceability", 10) < 10:
            repair_fields.append("doc_api")
        if scores.get("api_frontend_alignment", 10) < 10:
            repair_fields.append("doc_frontend")
        if scores.get("security_api_alignment", 10) < 10:
            repair_fields.append("doc_security")
        project_info = {
            "name": project_name,
            "type": "Web App",
            "description": project.description if project else "",
        }
        for field in repair_fields:
            persist_fixed_docs(arch, fixed)
            db.commit()
            db.refresh(arch)
            cross_doc = build_cross_doc_context(arch, field)
            for other_field in DOC_FIELDS:
                if fixed.get(other_field):
                    setattr(arch, other_field, fixed[other_field])
            repair_instructions = (
                "CRITICAL: Fix all alignment issues. Match suite canon exactly. "
                f"Current issues: {report.get('issues', [])}"
            )
            regenerated = await generate_single_doc_with_instructions(
                field,
                srs.content_json,
                project_info,
                existing_doc=fixed.get(field),
                instructions=repair_instructions,
                suite_canon=canon,
                cross_doc_context=cross_doc,
            )
            fixed[field] = regenerated
        fixed = apply_deterministic_fixes(fixed, srs.content_json, canon)
        report = validate_suite(fixed, srs.content_json, canon, nfr_profile=nfr_profile)

    persist_fixed_docs(arch, fixed)
    arch.suite_canon = canon
    arch.consistency_report = report
    db.commit()
    logger.info(
        "Architecture suite consolidated",
        extra={"arch_id": str(architecture_id), "overall": report.get("overall")},
    )
    return report


def find_finalized_architecture_for_project(architectures: list[Any]) -> Optional[Any]:
    finalized = [
        a for a in architectures
        if getattr(a, "status", None) and a.status.value == "finalized"
    ]
    if not finalized:
        confirmed = [
            a for a in architectures
            if getattr(a, "status", None) and a.status.value == "confirmed"
        ]
        if confirmed:
            return sorted(confirmed, key=lambda x: x.created_at, reverse=True)[0]
        return None
    return sorted(finalized, key=lambda x: x.created_at, reverse=True)[0]


DOC_SCHEMA_MAP: dict[str, Type[BaseModel]] = {
    key: schema for key, _, schema in DOCUMENT_ORDER
}

AI_EDIT_SYSTEM = (
    "You are an expert software architect editing a single architecture suite document. "
    "Apply the PM instructions precisely. Preserve IDs, traceability links, and valid Mermaid "
    "diagram syntax. Return strictly structured JSON matching the schema."
)

AI_EDIT_PROMPT = """
Edit this architecture document section according to PM instructions.

Document key: {doc_key}

Current document JSON:
{doc_json}

PM instructions:
{instructions}
"""


async def edit_architecture_doc_ai(
    doc_key: str,
    current_content: dict[str, Any],
    instruction: str,
) -> dict[str, Any]:
    """Apply free-text PM instructions to one architecture doc via ai_call()."""
    schema_cls = DOC_SCHEMA_MAP.get(doc_key)
    if schema_cls is None:
        raise ValueError(f"Invalid document key: {doc_key}")

    prompt = AI_EDIT_PROMPT.format(
        doc_key=doc_key,
        doc_json=json.dumps(current_content, indent=2, default=str)[:14000],
        instructions=instruction.strip(),
    )
    result = await ai_call(
        prompt=prompt,
        response_model=schema_cls,
        system=AI_EDIT_SYSTEM,
        max_tokens=8000,
        task_type="arch_single_doc",
    )
    dumped = result.model_dump()
    sanitized = sanitize_doc_diagrams(dumped)
    return sanitized if sanitized is not None else dumped


async def edit_architecture_suite_ai(
    architecture_id: UUID,
    instruction: str,
    db: Session,
) -> dict[str, Any]:
    """Apply one free-text PM instruction across all 6 architecture documents.

    Each generated doc is edited via ai_call(), persisted, then the whole suite is
    re-aligned to canon and re-scored so the consistency report stays accurate.
    """
    arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
    if not arch:
        return {"error": "Architecture not found"}

    edited_keys: list[str] = []
    for doc_key in DOC_FIELDS:
        content = getattr(arch, doc_key, None)
        if not content:
            continue
        try:
            corrected = await edit_architecture_doc_ai(doc_key, content, instruction)
        except Exception:  # noqa: BLE001 — one doc failing must not abort the suite
            logger.exception("Suite edit failed for %s", doc_key)
            continue
        setattr(arch, doc_key, corrected)
        edited_keys.append(doc_key)

    db.commit()
    db.refresh(arch)

    # Re-align + re-score so the consistency report reflects the edits
    report = await consolidate_architecture_suite(architecture_id, db, ai_repair=False)
    report["edited_docs"] = edited_keys
    return report


PDF_POLISH_SYSTEM = (
    "You write concise formal technical architecture prose for PDF reports. "
    "Be precise and short — only what implementers need. No marketing language."
)

PDF_POLISH_PROMPT = """
Polish this architecture document section for a formal PDF export.

Document key: {doc_key}

Current JSON:
{doc_json}

Return a concise overview (2–4 sentences) that accurately summarizes this section.
Preserve all technical facts, component names, and stack choices.
Do not invent features not present in the source.
"""


class PdfPolishedOverview(BaseModel):
    overview: str


async def polish_architecture_doc_for_pdf(
    doc_key: str,
    doc_content: dict[str, Any],
) -> dict[str, Any]:
    """Rewrite overview into concise formal PDF prose via ai_call()."""
    prompt = PDF_POLISH_PROMPT.format(
        doc_key=doc_key,
        doc_json=json.dumps(doc_content, indent=2, default=str)[:12000],
    )
    result = await ai_call(
        prompt=prompt,
        response_model=PdfPolishedOverview,
        system=PDF_POLISH_SYSTEM,
        max_tokens=1200,
        task_type="arch_single_doc",
    )
    polished = dict(doc_content)
    polished["overview"] = result.overview.strip()
    return polished


async def polish_architecture_docs_for_pdf(
    documents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Polish multiple architecture docs for PDF export (parallel)."""
    if not documents:
        return {}

    async def _one(key: str, content: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        polished = await polish_architecture_doc_for_pdf(key, content)
        return key, polished

    pairs = await asyncio.gather(
        *(_one(key, content) for key, content in documents.items())
    )
    return dict(pairs)
