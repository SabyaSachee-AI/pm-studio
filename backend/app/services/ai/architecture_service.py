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
from app.services.ai.mermaid_sanitize import sanitize_doc_diagrams

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
(system_overview, deployment). Use valid Mermaid syntax.
""",
        "doc_database": f"""
Generate the Database Design document for {project_name}.

SRS context:
{srs_summary}

Include: overview, PostgreSQL conventions, tables linked to SRS data entities with columns/indexes,
relationships, migration_order, and Mermaid erDiagram in diagrams.erd.
""",
        "doc_api": f"""
Generate the API Specification for {project_name}.

SRS context:
{srs_summary}

Include: REST endpoints at /api/v1 linked to SRS FR ids, auth (JWT HttpOnly cookies),
request/response bodies, error codes, file paths, and Mermaid sequence diagrams
(auth_flow, request_flow).
""",
        "doc_frontend": f"""
Generate the Frontend Architecture for {project_name}.

SRS context:
{srs_summary}

Include: Next.js 14 App Router pages, components, api_calls, folder_structure,
and Mermaid diagrams (component_tree, routing).
""",
        "doc_security": f"""
Generate the Security + RBAC plan for {project_name}.

SRS context:
{srs_summary}

Include: JWT auth mechanism, RBAC roles/permission_matrix, api_security controls,
OWASP checklist, and Mermaid diagrams (auth_flow, rbac_flow).
""",
        "doc_uiux": f"""
Generate UI/UX Design Guidance for {project_name}.

SRS context:
{srs_summary}

Include: design_system (colors, typography), page sections/components, ux_rules,
and Mermaid diagrams (user_flow, page_layout).
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
    if prd_content:
        # Selective extraction — all features by title+priority, no char barrier.
        prd_brief = {
            "executive_summary": (prd_content.get("executive_summary") or "")[:600],
            "features": [
                {
                    "title": f.get("title", ""),
                    "description": (f.get("description") or "")[:120],
                    "priority": f.get("priority", ""),
                }
                for f in (prd_content.get("features") or [])
            ],
            "out_of_scope": prd_content.get("out_of_scope") or [],
            "success_metrics": prd_content.get("success_metrics") or [],
        }
        prompt += f"\n\nPRD CONTEXT:\n{json.dumps(prd_brief, separators=(',', ':'), default=str)}"
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
    )


async def generate_api_document_chunked(
    arch: Architecture,
    db: Session,
    srs_content: dict[str, Any],
    project_info: dict[str, Any],
    *,
    suite_canon: dict[str, Any] | None = None,
    cross_doc_context: str = "",
    task_type: str = "arch_generate",
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
    prd_content = prd.content_json if prd and prd.content_json else None
    project_info = {
        "name": project.name if project else "Unknown Project",
        "type": "Web App",
        "description": project.description if project else "",
    }
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
            )
        elif doc_field == "doc_api":
            result = await generate_api_document_chunked(
                arch,
                db,
                srs.content_json,
                project_info,
                suite_canon=suite_canon,
                cross_doc_context=cross_doc_context,
                task_type=task_type,
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
        task_ids = dict(arch.doc_task_ids or {})
        task_ids.pop(doc_field, None)
        arch.doc_task_ids = task_ids
        db.commit()

        arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
        if arch and all(
            getattr(arch, f"{f}_status") in COMPLETED_STATUSES for f, _, _ in DOCUMENT_ORDER
        ):
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
) -> dict[str, str]:
    """Generate documents one at a time, saving after each."""
    arch = db.query(Architecture).filter(Architecture.id == architecture_id).first()
    if not arch:
        return {"error": "Architecture not found"}

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
            result = await generate_single_document(doc_field, srs_content, project_info)
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
                result = await generate_single_document(doc_field, srs_content, project_info)
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
    fixed = apply_deterministic_fixes(docs, srs.content_json, canon)
    report = validate_suite(fixed, srs.content_json, canon)

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
        report = validate_suite(fixed, srs.content_json, canon)

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
