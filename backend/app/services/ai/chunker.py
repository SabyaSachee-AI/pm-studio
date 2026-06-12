"""Chunk-and-merge layer for large-input AI generation tasks.

Splits oversized inputs into paragraph-aligned chunks that fit ANY model
in the fallback chain — including 8K-context free models (Cerebras, small
Groq models, NVIDIA NIM).  Each chunk is processed by ai_call(), which
walks the full 15-model fallback chain as normal.  Partial results are
then merged into one final validated Pydantic object.

CLAUDE.md rule preserved: all AI calls go through ai_call().
Nothing in the router, providers, or workers is changed.

Token budget per chunk (worst case — 8K context model):
  System prompt      ~1 000 tok
  Rolling context    ~  300 tok
  Chunk content      ~2 500 tok   ← ANALYSIS_CHUNK_CHARS / 4
  Output budget      ~4 000 tok
  ─────────────────────────────
  Total              ~7 800 tok   ← fits inside 8K with margin
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.schemas.module import ExtractedModule, ExtractedTaskItem, ModuleListSchema
from app.schemas.prd import FeatureItem, PRDSchema, UserStory
from app.schemas.requirement import RequirementAnalysisSchema, RequirementGap
from app.schemas.srs import FunctionalRequirement, NonFunctionalRequirement, SRSSchema
from app.services.ai.base import ai_call


class _PrdNarrative(BaseModel):
    executive_summary: str
    problem_statement: str

logger = logging.getLogger(__name__)

# ── Token budget constants ─────────────────────────────────────────────────────
# 1 token ≈ 4 chars (English prose).  All limits are conservative.

ANALYSIS_CHUNK_CHARS   = 10_000   # ~2 500 tok input  — small output (analysis schema)
GENERATION_CHUNK_CHARS =  8_000   # ~2 000 tok input  — larger output (PRD/SRS/modules)
FR_BATCH_SIZE          = 8        # FRs per SRS chunk
MODULE_FR_BATCH_SIZE   = 8        # FRs per module-extract chunk
FEATURE_BATCH_SIZE     = 8        # PRD features per SRS-generation batch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _estimate_chars(obj: Any) -> int:
    """Rough char count of a string or JSON-serialisable object."""
    if isinstance(obj, str):
        return len(obj)
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return 0


def _split_by_paragraphs(text: str, max_chars: int) -> list[str]:
    """Split text at blank-line boundaries; never mid-sentence."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_len + len(para) + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks or [text]


def _batched(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _dedupe_str(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        low = item.strip().lower()
        if low and low not in seen:
            seen.add(low)
            out.append(item.strip())
    return out


def _compact_json(obj: Any, max_chars: int = 3_000) -> str:
    """Serialise to JSON and truncate to max_chars."""
    text = json.dumps(obj, ensure_ascii=False, indent=None)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…[truncated]"


# ── Merge helpers ──────────────────────────────────────────────────────────────

def _merge_analysis(parts: list[RequirementAnalysisSchema]) -> RequirementAnalysisSchema:
    """Combine partial analysis results from multiple chunks."""
    if not parts:
        raise RuntimeError("No analysis chunks returned")
    if len(parts) == 1:
        return parts[0]

    # project_type: pick the most specific (longest non-generic string)
    project_type = max(
        (p.project_type for p in parts if p.project_type),
        key=lambda s: len(s),
        default="Software Application",
    )

    # Lists — concat then dedupe by description/text
    all_gaps: list[RequirementGap] = []
    seen_gaps: set[str] = set()
    for p in parts:
        for g in p.gaps:
            key = g.description.lower().strip()[:80]
            if key not in seen_gaps:
                seen_gaps.add(key)
                all_gaps.append(g)

    all_risks = _dedupe_str([r for p in parts for r in p.business_risks])
    all_questions = _dedupe_str([q for p in parts for q in p.technical_questions])
    all_nfr = _dedupe_str([n for p in parts for n in p.missing_nfr])

    # Summary: take from last chunk (it has rolling context — most comprehensive)
    summary = parts[-1].summary or parts[0].summary

    return RequirementAnalysisSchema(
        project_type=project_type,
        gaps=all_gaps,
        business_risks=all_risks,
        technical_questions=all_questions,
        missing_nfr=all_nfr,
        summary=summary,
    )


def _merge_prd(parts: list[PRDSchema]) -> PRDSchema:
    """Combine partial PRD results from multiple requirement-text chunks."""
    if not parts:
        raise RuntimeError("No PRD chunks returned")
    if len(parts) == 1:
        return parts[0]

    # Narrative fields — take from chunk 1 (most complete context)
    base = parts[0]

    # Dedupe user stories by i_want_to
    seen_stories: set[str] = set()
    all_stories: list[UserStory] = []
    for p in parts:
        for s in p.user_stories:
            key = s.i_want_to.lower().strip()[:60]
            if key not in seen_stories:
                seen_stories.add(key)
                all_stories.append(s)

    # Dedupe features by title
    seen_feat: set[str] = set()
    all_features: list[FeatureItem] = []
    for p in parts:
        for f in p.features:
            key = f.title.lower().strip()[:60]
            if key not in seen_feat:
                seen_feat.add(key)
                all_features.append(f)

    return PRDSchema(
        executive_summary=base.executive_summary,
        problem_statement=base.problem_statement,
        target_users=_dedupe_str([u for p in parts for u in p.target_users]),
        features=all_features,
        user_stories=all_stories,
        out_of_scope=_dedupe_str([o for p in parts for o in p.out_of_scope]),
        success_metrics=_dedupe_str([m for p in parts for m in p.success_metrics]),
        assumptions=_dedupe_str([a for p in parts for a in p.assumptions]),
    )


def _merge_srs(parts: list[SRSSchema]) -> SRSSchema:
    """Combine partial SRS results; renumber FRs sequentially."""
    if not parts:
        raise RuntimeError("No SRS chunks returned")
    if len(parts) == 1:
        return parts[0]

    base = parts[0]

    # Combine FRs and renumber
    all_frs: list[FunctionalRequirement] = []
    for p in parts:
        all_frs.extend(p.functional_requirements)
    for idx, fr in enumerate(all_frs, start=1):
        fr.fr_number = f"FR-{idx:03d}"

    # NFRs — one per category (keep first seen)
    seen_nfr: set[str] = set()
    all_nfr: list[NonFunctionalRequirement] = []
    for p in parts:
        for n in p.nonfunctional_requirements:
            key = n.category.lower().strip()
            if key not in seen_nfr:
                seen_nfr.add(key)
                all_nfr.append(n)

    return SRSSchema(
        introduction=base.introduction,
        scope=base.scope,
        definitions=_dedupe_str([d for p in parts for d in p.definitions]),
        functional_requirements=all_frs,
        nonfunctional_requirements=all_nfr,
        assumptions=_dedupe_str([a for p in parts for a in p.assumptions]),
        constraints=_dedupe_str([c for p in parts for c in p.constraints]),
        references=_dedupe_str([r for p in parts for r in p.references]),
    )


def _merge_modules(parts: list[ModuleListSchema]) -> ModuleListSchema:
    """Combine partial module-extract results; merge same-named modules."""
    if not parts:
        raise RuntimeError("No module chunks returned")
    if len(parts) == 1:
        return parts[0]

    module_map: dict[str, list[ExtractedTaskItem]] = {}
    module_desc: dict[str, str] = {}

    for part in parts:
        for mod in part.modules:
            key = mod.name.strip()
            if key not in module_map:
                module_map[key] = []
                module_desc[key] = mod.description or ""
            # Dedupe tasks by title
            existing_titles = {t.title.lower()[:60] for t in module_map[key]}
            for task in mod.tasks:
                if task.title.lower()[:60] not in existing_titles:
                    existing_titles.add(task.title.lower()[:60])
                    module_map[key].append(task)

    merged_modules = [
        ExtractedModule(
            name=name,
            description=module_desc[name],
            tasks=tasks,
        )
        for name, tasks in module_map.items()
    ]
    return ModuleListSchema(modules=merged_modules)


# ── Public chunked entrypoints ─────────────────────────────────────────────────

async def chunked_analysis(
    text: str,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> RequirementAnalysisSchema:
    """Analyse a requirement document of any length.

    Splits by paragraph, processes each chunk, merges partial analyses.
    Single call if text is short enough.
    """
    chunks = _split_by_paragraphs(text, ANALYSIS_CHUNK_CHARS)
    logger.info("chunked_analysis: %d chunk(s) for %d chars", len(chunks), len(text))

    system = (
        "You are an expert software business analyst. "
        "Return strictly structured JSON matching the schema exactly."
    )
    parts: list[RequirementAnalysisSchema] = []
    rolling_project_type = ""
    rolling_counts: dict[str, int] = {
        "gaps": 0, "risks": 0, "questions": 0, "nfr": 0
    }

    for i, chunk in enumerate(chunks, start=1):
        rolling_header = ""
        if i > 1:
            rolling_header = (
                f"[CHUNK {i} of {len(chunks)}]\n"
                f"Running totals from earlier chunks — "
                f"project_type: \"{rolling_project_type}\", "
                f"gaps: {rolling_counts['gaps']}, "
                f"risks: {rolling_counts['risks']}, "
                f"questions: {rolling_counts['questions']}, "
                f"missing_nfr: {rolling_counts['nfr']}.\n"
                f"Extract NEW findings only. Do NOT repeat already-found items.\n\n"
            )
        else:
            rolling_header = f"[CHUNK {i} of {len(chunks)}]\n\n"

        prompt = (
            f"{rolling_header}"
            "Analyse the following portion of a software requirements document.\n"
            "Identify: project type, requirement gaps, business risks, "
            "technical questions, missing non-functional requirements.\n\n"
            f"Document Text:\n{chunk}"
        )

        result: RequirementAnalysisSchema = await ai_call(
            prompt=prompt,
            response_model=RequirementAnalysisSchema,
            system=system,
            task_type="req_analyze",
            screen="requirements",
            org_id=org_id,
            db=db,
        )
        parts.append(result)

        # Update rolling state
        if result.project_type:
            rolling_project_type = result.project_type
        rolling_counts["gaps"]      += len(result.gaps)
        rolling_counts["risks"]     += len(result.business_risks)
        rolling_counts["questions"] += len(result.technical_questions)
        rolling_counts["nfr"]       += len(result.missing_nfr)

    return _merge_analysis(parts)


async def chunked_prd(
    requirement_text: str,
    analysis_result: dict,
    project_name: str,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> PRDSchema:
    """Generate a PRD from requirement text of any length.

    Passes the FULL analysis_result to every chunk so context is preserved.
    Splits only the raw requirement text.
    """
    system = (
        "You are an expert product manager creating professional PRDs. "
        "Be specific, actionable, and comprehensive. "
        "Return strictly structured JSON matching the schema exactly."
    )

    # Build fixed context block (analysis result) — compact
    analysis_json = _compact_json(analysis_result, max_chars=2_000)
    gaps_summary = "\n".join(
        f"- [{g.get('category', '').upper()}] {g.get('description', '')}"
        for g in analysis_result.get("gaps", [])
    )
    risks_text = "\n".join(
        f"- {r}" for r in analysis_result.get("business_risks", [])
    )
    fixed_header = (
        f"Project: {project_name}\n"
        f"Project Type: {analysis_result.get('project_type', 'Software')}\n\n"
        f"Known Gaps:\n{gaps_summary}\n\n"
        f"Business Risks:\n{risks_text}\n\n"
        f"Analysis Summary: {analysis_result.get('summary', '')}\n\n"
    )

    chunks = _split_by_paragraphs(requirement_text, GENERATION_CHUNK_CHARS)
    logger.info(
        "chunked_prd: %d chunk(s) for requirement_text len=%d",
        len(chunks), len(requirement_text),
    )

    parts: list[PRDSchema] = []
    executive_summary_established = ""

    for i, chunk in enumerate(chunks, start=1):
        rolling_note = ""
        if i > 1 and executive_summary_established:
            rolling_note = (
                f"[CHUNK {i} of {len(chunks)}]\n"
                f"Executive summary already written: \"{executive_summary_established[:300]}\".\n"
                f"Generate ADDITIONAL features and user stories from this portion.\n"
                f"Use the same executive_summary, problem_statement, target_users "
                f"as established in chunk 1.\n\n"
            )
        else:
            rolling_note = f"[CHUNK {i} of {len(chunks)}]\n\n"

        prompt = (
            f"{rolling_note}"
            f"{fixed_header}"
            "Original Requirements (this portion):\n"
            f"{chunk}\n\n"
            "Generate a complete PRD with executive_summary, problem_statement, "
            "target_users, features, user_stories, out_of_scope, "
            "success_metrics, assumptions."
        )

        result: PRDSchema = await ai_call(
            prompt=prompt,
            response_model=PRDSchema,
            system=system,
            max_tokens=6000,
            task_type="prd_generate",
            screen="prds",
            org_id=org_id,
            db=db,
        )
        parts.append(result)
        if not executive_summary_established and result.executive_summary:
            executive_summary_established = result.executive_summary

    merged = _merge_prd(parts)

    if len(parts) > 1:
        # Synthesise executive_summary from the full merged feature list so it
        # covers the entire document, not just what chunk 1 saw.
        all_feature_lines = "\n".join(
            f"- [{f.title}] {f.description[:100]}" for f in merged.features
        )
        synthesis_prompt = (
            f"Project: {project_name}\n"
            f"Project type: {analysis_result.get('project_type', 'Software')}\n\n"
            f"All {len(merged.features)} confirmed features:\n{all_feature_lines}\n\n"
            f"Write a 3-4 sentence executive_summary that covers the full scope, "
            f"and a 2-3 sentence problem_statement grounded in the features above."
        )
        narrative: _PrdNarrative = await ai_call(
            prompt=synthesis_prompt,
            response_model=_PrdNarrative,
            system=(
                "You are an expert product manager. "
                "Return structured JSON with executive_summary and problem_statement only."
            ),
            max_tokens=800,
            task_type="prd_generate",
            screen="prds",
            org_id=org_id,
            db=db,
        )
        merged.executive_summary = narrative.executive_summary
        merged.problem_statement = narrative.problem_statement

    return merged


async def chunked_srs(
    prd_content: dict,
    project_name: str,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> SRSSchema:
    """Generate an SRS from PRD content.

    Splits the features list into batches so each call fits small models.
    NFRs are generated once (in the first chunk) to ensure consistency.
    """
    system = (
        "You are an expert software architect writing IEEE 830 compliant SRS documents. "
        "Be specific, measurable, and testable. "
        "Return strictly structured JSON matching the schema exactly."
    )

    features = prd_content.get("features", [])
    user_stories = prd_content.get("user_stories", [])
    executive_summary = prd_content.get("executive_summary", "")
    out_of_scope = prd_content.get("out_of_scope", [])

    # Fixed context — included in every chunk
    scope_text = "\n".join(f"- {item}" for item in out_of_scope)
    stories_text = "\n".join(
        f"- As a {s.get('as_a', '')}, I want to {s.get('i_want_to', '')}."
        for s in user_stories
    )

    feature_batches = _batched(features, FEATURE_BATCH_SIZE)
    logger.info(
        "chunked_srs: %d batch(es) for %d features",
        len(feature_batches), len(features),
    )

    parts: list[SRSSchema] = []
    fr_counter = 1       # global FR counter across batches
    defined_frs: list[str] = []  # rolling log of already-written FRs (prevents duplicates)

    for i, batch in enumerate(feature_batches, start=1):
        features_text = "\n".join(
            f"- [{f.get('priority', '').upper()}] {f.get('title', '')}: {f.get('description', '')}"
            for f in batch
        )
        next_fr = fr_counter

        nfr_instruction = (
            "Also generate 6 non-functional requirements (Performance, Security, "
            "Usability, Reliability, Scalability, Maintainability)."
            if i == 1
            else "Set nonfunctional_requirements to [] — NFRs already generated in previous batch."
        )

        # Rolling context — tells each batch what FRs already exist so it never
        # duplicates intent or writes contradicting requirements.
        prior_frs_block = ""
        if defined_frs:
            prior_frs_block = (
                f"ALREADY DEFINED FRs (do NOT duplicate these — reference by number if needed):\n"
                + "\n".join(f"  {line}" for line in defined_frs)
                + "\n\n"
            )

        prompt = (
            f"[FEATURE BATCH {i} of {len(feature_batches)}]\n"
            f"Start FR numbering from FR-{next_fr:03d}.\n\n"
            f"{prior_frs_block}"
            f"Project: {project_name}\n"
            f"Executive Summary: {executive_summary[:400]}\n\n"
            f"User Stories (context):\n{stories_text}\n\n"
            f"Out of Scope:\n{scope_text}\n\n"
            f"Features in THIS batch:\n{features_text}\n\n"
            f"Generate SRS with:\n"
            f"- Introduction and scope {'(write fully)' if i == 1 else '(copy from batch 1: use empty strings)'}\n"
            f"- Numbered functional requirements starting at FR-{next_fr:03d}\n"
            f"  Each FR: fr_number, title, description (≤80 words), priority, test_criteria (2 max)\n"
            f"- {nfr_instruction}\n"
            f"- Assumptions, constraints (only in batch 1, empty list otherwise)"
        )

        result: SRSSchema = await ai_call(
            prompt=prompt,
            response_model=SRSSchema,
            system=system,
            max_tokens=6000,
            task_type="srs_generate",
            screen="srs",
            org_id=org_id,
            db=db,
        )
        parts.append(result)

        # Update rolling log for next batch
        for fr in result.functional_requirements:
            defined_frs.append(f"{fr.fr_number}: {fr.title}")
        fr_counter += len(result.functional_requirements)

    return _merge_srs(parts)


async def chunked_modules(
    project_name: str,
    prd_content: dict,
    srs_content: dict,
    arch_content: dict[str, Any] | None = None,
    target_frs: list[str] | None = None,
    org_id: UUID | None = None,
    db: AsyncSession | None = None,
) -> ModuleListSchema:
    """Extract modules and tasks from SRS + Architecture.

    Splits the FR list into batches; each batch is processed independently.
    Arch context is compacted and included in every chunk.
    """
    system = (
        "You are an expert software project planner with deep knowledge of layered architecture. "
        "Return strictly structured JSON matching the schema. "
        "Module names reflect architectural layers, not feature names. "
        "Tasks are ordered in implementation sequence within each module. "
        "Every task is independently implementable and maps to a specific file."
    )

    features = prd_content.get("features", [])
    # Descriptions capped at 100 chars — features are context here, not generation input.
    # Full descriptions go to chunked_srs (where FRs are generated from them).
    features_text = "\n".join(
        f"- {f.get('title', '')}: {(f.get('description') or '')[:100]} [{f.get('priority', '')}]"
        for f in features
    )

    all_frs = srs_content.get("functional_requirements", [])
    if target_frs:
        all_frs = [fr for fr in all_frs if fr.get("fr_number") in target_frs]

    # Build compact arch context once
    arch_section = _build_compact_arch_context(arch_content)

    fill_note = (
        f"FILL-GAPS MODE: Only generate tasks for FRs: {', '.join(target_frs or [])}.\n"
        if target_frs else ""
    )

    fr_batches = _batched(all_frs, MODULE_FR_BATCH_SIZE)
    logger.info(
        "chunked_modules: %d batch(es) for %d FRs",
        len(fr_batches), len(all_frs),
    )

    parts: list[ModuleListSchema] = []
    established_modules: list[str] = []  # rolling list of module names — ensures consistency

    for i, batch in enumerate(fr_batches, start=1):
        frs_text = "\n".join(
            f"{fr.get('fr_number', '')}: {fr.get('title', '')} — {fr.get('description', '')}"
            for fr in batch
        )

        # Rolling module names — each batch reuses established names for the same
        # architectural layer so _merge_modules always finds them under one key.
        module_block = ""
        if established_modules:
            module_block = (
                "ESTABLISHED MODULE NAMES from prior batches "
                "(reuse EXACT names for the same architectural layer — never rename):\n"
                + "\n".join(f"  - {m}" for m in established_modules)
                + "\n\n"
            )

        prompt = (
            f"[FR BATCH {i} of {len(fr_batches)}]\n{fill_note}\n"
            f"{module_block}"
            f"Project: {project_name}\n\n"
            f"PRD Features (reference):\n{features_text or 'None'}\n\n"
            f"Functional Requirements to implement in this batch:\n{frs_text}\n\n"
            f"{arch_section}\n"
            "Rules:\n"
            "- Maximum 6 tasks per module.\n"
            "- Priorities: critical (auth, core data models), high (main features), "
            "medium (secondary), low (polish).\n"
            "- Each task title must be specific.\n"
            "- Description must say WHO does WHAT and IN WHICH FILE.\n"
            "- effort_hours: realistic estimate in hours (1–16).\n"
            "- Every task must have linked_fr set to the primary FR it implements.\n"
        )

        result: ModuleListSchema = await ai_call(
            prompt=prompt,
            response_model=ModuleListSchema,
            system=system,
            max_tokens=8000,
            task_type="module_extract",
            screen="tasks",
            org_id=org_id,
            db=db,
        )
        parts.append(result)

        # Collect module names for next batch
        for mod in result.modules:
            if mod.name not in established_modules:
                established_modules.append(mod.name)

    return _merge_modules(parts)


def _build_compact_arch_context(arch_content: dict[str, Any] | None) -> str:
    """Compact arch context that fits within 1 500 chars for small-model chunks."""
    if not arch_content:
        return (
            "No architecture document available.\n"
            "Group tasks by layer: 'Backend — [Feature]', 'Frontend — [Feature]', "
            "'Database — [Feature]'.\n"
            "Leave suggested_file/endpoint/table as null."
        )

    lines: list[str] = ["Architecture context:"]

    frontend = arch_content.get("doc_frontend") or {}
    folder = frontend.get("folder_structure", {})
    if folder:
        lines.append("Frontend folders (use for suggested_file):")
        lines.append(_flatten_folder_compact(folder))

    api_doc = arch_content.get("doc_api") or {}
    endpoints = api_doc.get("endpoints", [])
    if endpoints:
        lines.append("API endpoints (use for suggested_endpoint):")
        for ep in endpoints:  # 1 500-char cap below is the real ceiling
            lines.append(
                f"  {ep.get('method', '')} {ep.get('path', '') or ep.get('full_path', '')} "
                f"[{ep.get('linked_fr', '')}]"
            )

    db_doc = arch_content.get("doc_database") or {}
    tables = db_doc.get("tables", [])
    if tables:
        lines.append("DB tables (use for suggested_table):")
        for t in tables:  # 1 500-char cap below is the real ceiling
            lines.append(f"  {t.get('name', '')} — {t.get('purpose', '')}")

    result = "\n".join(lines)
    # Hard cap to stay within chunk budget
    if len(result) > 1_500:
        result = result[:1_497] + "…"
    return result


def _flatten_folder_compact(node: Any, depth: int = 0) -> str:
    if depth > 2:
        return ""
    if isinstance(node, dict):
        parts = []
        for k, v in node.items():  # 1 500-char cap in caller is the real ceiling
            parts.append(f"{'  ' * depth}{k}/")
            child = _flatten_folder_compact(v, depth + 1)
            if child:
                parts.append(child)
        return "\n".join(parts)
    if isinstance(node, list):
        return "\n".join(
            f"{'  ' * depth}{item}" for item in node if isinstance(item, str)
        )
    return ""
