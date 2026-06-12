"""AI prompt and post-processing for requirement gap categorization."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.requirement import GapCategory
from app.services.ai.base import ai_call

ANALYSIS_SYSTEM = (
    "You are an expert software business analyst. "
    "Categorize every gap as client-facing or technical. "
    "Return strictly structured JSON matching the schema."
)

ANALYSIS_PROMPT_TEMPLATE = """
Analyze the following software project requirements document.
Identify the project type, gaps, risks, technical questions, and missing non-functional requirements.

For EACH gap in the gaps array, set:
- client_input (boolean): true if the client must answer; false if PM Studio applies a technical standard
- question (string): a clear clarification question when applicable
- auto_answer (string|null): required when client_input is false — a concise standard technical decision

Categorization rules:

client_input = FALSE (technical — auto-answer with industry-standard defaults):
- Maximum recording duration / file size limits
- Error handling approach
- Browser compatibility
- Storage capacity handling
- Design / color scheme / branding (use accessible neutral defaults)
- Sorting order
- Language support (default English unless document specifies otherwise)
- Real-time vs after-stop display behavior
- Performance benchmarks
- Security implementation (HTTPS, auth, encryption at rest, OWASP-aligned practices)

client_input = TRUE (business — client must answer):
- What to build / project overview and scope
- Who are the users / personas
- What features are needed
- Timeline and milestones
- Budget constraints
- Whether search/filter is needed
- Whether edit-after-save is allowed
- Whether export feature is needed
- Whether confirmation dialogs are needed

When client_input is false, always provide a specific auto_answer (2-4 sentences) describing the standard approach.
When client_input is true, set auto_answer to null.

Document Text:
{text}
"""


class RequirementGapAnalysis(BaseModel):
    description: str
    category: GapCategory
    question: Optional[str] = None
    client_input: bool = True
    auto_answer: Optional[str] = None


class RequirementAnalysisResult(BaseModel):
    project_type: str
    gaps: list[RequirementGapAnalysis]
    business_risks: list[str]
    technical_questions: list[str] = Field(default_factory=list)
    missing_nfr: list[str]
    summary: str


def _default_auto_answer(gap: RequirementGapAnalysis) -> str:
    """Fallback technical standard when the model omits auto_answer."""
    combined = f"{gap.description} {gap.question or ''}".lower()

    rules: list[tuple[tuple[str, ...], str]] = [
        (
            ("recording", "duration", "length", "size limit", "file size"),
            "Sessions are capped at 60 minutes or 500 MB per recording, whichever comes first, "
            "with a clear warning shown before the limit is reached.",
        ),
        (
            ("error", "failure", "exception"),
            "Errors surface user-friendly messages, are logged server-side, and failed operations "
            "are retried once before showing a recovery action.",
        ),
        (
            ("browser", "compatibility", "device"),
            "Support the latest two versions of Chrome, Firefox, Safari, and Edge on desktop and mobile.",
        ),
        (
            ("storage", "capacity", "quota"),
            "Use scalable object storage with soft quotas per user; warn at 80% usage and block new uploads at 100%.",
        ),
        (
            ("design", "color", "branding", "ui", "theme"),
            "Apply an accessible neutral palette (WCAG AA contrast), system fonts, and consistent spacing "
            "from the studio design system unless branding assets are supplied later.",
        ),
        (
            ("sort", "order", "ordering"),
            "Default to newest-first ordering with optional user-selectable sort (date, name, relevance).",
        ),
        (
            ("language", "locale", "i18n", "translation"),
            "English is the default UI language; architecture supports adding locales without schema changes.",
        ),
        (
            ("real-time", "realtime", "live", "after-stop", "after stop"),
            "Show progressive feedback during processing; finalize and persist results when the action completes.",
        ),
        (
            ("performance", "latency", "benchmark", "response time"),
            "Target sub-2s page loads and sub-500ms API responses at p95 under normal load.",
        ),
        (
            ("security", "auth", "encrypt", "permission"),
            "Enforce HTTPS, HttpOnly session cookies, role-based access control, and encryption at rest for sensitive data.",
        ),
    ]

    for keywords, answer in rules:
        if any(word in combined for word in keywords):
            return answer

    return (
        "Apply PM Studio standard technical defaults: secure defaults, accessible UI, "
        "structured logging, and extensible architecture consistent with similar SaaS modules."
    )


def enrich_gap_analysis(result: RequirementAnalysisResult) -> RequirementAnalysisResult:
    """Ensure technical gaps always carry an auto_answer."""
    enriched_gaps: list[RequirementGapAnalysis] = []
    for gap in result.gaps:
        if not gap.client_input:
            auto_answer = (gap.auto_answer or "").strip() or _default_auto_answer(gap)
            enriched_gaps.append(gap.model_copy(update={"auto_answer": auto_answer}))
        else:
            enriched_gaps.append(gap.model_copy(update={"auto_answer": None}))
    return result.model_copy(update={"gaps": enriched_gaps})


async def analyze_requirements_ai(text: str) -> RequirementAnalysisResult:
    """Analyze extracted text with smart client vs technical gap categorization."""
    truncated_text = text[:10000]
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(text=truncated_text)
    result = await ai_call(
        prompt=prompt,
        response_model=RequirementAnalysisResult,
        system=ANALYSIS_SYSTEM,
        task_type="req_analyze",
        screen="requirements",
    )
    return enrich_gap_analysis(result)


SYNTHESIS_SYSTEM = (
    "You are an expert software business analyst. "
    "Synthesize a final requirement draft from the original document and client feedback. "
    "Return strictly structured JSON matching the schema."
)

SYNTHESIS_PROMPT_TEMPLATE = """
Create a Final Requirement Draft by merging the original requirement with client feedback answers.

Original requirement text:
{original_text}

Client feedback document:
{feedback_text}

Gap analysis summary (for context):
{analysis_summary}

Produce a consolidated draft with:
- project_overview: concise overview of what will be built
- users_and_roles: who uses the system and their roles
- confirmed_features: list of agreed features (strings)
- technical_decisions: list of technical choices including auto-applied standards
- out_of_scope: explicitly excluded items
- open_questions: anything still unclear after feedback (empty if none)
- synthesis_notes: what changed from the original requirement
- client_feedback_summary: list of objects with "question" and "answer" for each client response found in the feedback document
"""

REANALYZE_SYSTEM = (
    "You are an expert software business analyst. "
    "Rewrite a requirement draft based on PM instructions. "
    "Return strictly structured JSON matching the schema."
)

REANALYZE_PROMPT_TEMPLATE = """
Rewrite this Final Requirement Draft according to the PM's instructions.

Current draft (JSON):
{draft_json}

PM instructions:
{instructions}

Update all sections as needed. Keep client_feedback_summary unless instructions say otherwise.
Increment synthesis_notes to describe what changed in this revision.
"""


class ClientFeedbackItem(BaseModel):
    question: str
    answer: str


class FinalRequirementDraft(BaseModel):
    project_overview: str
    users_and_roles: str
    confirmed_features: list[str]
    technical_decisions: list[str]
    out_of_scope: list[str]
    open_questions: list[str]
    synthesis_notes: str
    client_feedback_summary: list[ClientFeedbackItem] = Field(default_factory=list)


def _extract_docx_text(file_path: str) -> str:
    """Extract plain text from a DOCX file without external dependencies."""
    with zipfile.ZipFile(file_path) as archive:
        xml_content = archive.read("word/document.xml")
    root = ET.fromstring(xml_content)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.iterfind(".//w:p", namespace):
        texts = [node.text for node in paragraph.iterfind(".//w:t", namespace) if node.text]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def extract_document_text(file_path: str, filename: str) -> str:
    """Extract text from PDF, DOCX, or plain-text feedback documents."""
    extension = Path(filename).suffix.lower()
    if extension == ".txt":
        return Path(file_path).read_text(encoding="utf-8", errors="replace")
    if extension == ".docx":
        return _extract_docx_text(file_path)
    if extension == ".pdf":
        from app.services.requirement.service import extract_text_from_pdf

        return extract_text_from_pdf(file_path)
    return Path(file_path).read_text(encoding="utf-8", errors="replace")


def estimate_refined_cost(
    draft: FinalRequirementDraft,
    initial_cost: dict | None = None,
) -> dict[str, int | float | str]:
    """Estimate refined budget after feedback synthesis."""
    feature_units = max(3, len(draft.confirmed_features))
    open_questions = len(draft.open_questions)
    complexity = 1.0 + open_questions * 0.08
    base = 8_000
    min_budget = int(feature_units * base * 0.85 * complexity)
    max_budget = int(feature_units * base * 1.35 * complexity)
    note = "Refined estimate after client feedback and synthesis."
    if initial_cost:
        note = (
            f"Refined estimate after feedback. "
            f"Initial was ${initial_cost.get('min_budget_usd')}–"
            f"${initial_cost.get('max_budget_usd')}."
        )
    return {
        "feature_units": feature_units,
        "complexity_multiplier": round(complexity, 2),
        "min_budget_usd": min_budget,
        "max_budget_usd": max_budget,
        "currency": "USD",
        "note": note,
    }


async def synthesize_requirement_draft(
    original_text: str,
    feedback_text: str,
    analysis_summary: str = "",
) -> FinalRequirementDraft:
    """Merge original requirement and client feedback into a final draft."""
    prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        original_text=original_text[:8000],
        feedback_text=feedback_text[:8000],
        analysis_summary=analysis_summary[:2000] or "Not provided.",
    )
    return await ai_call(
        prompt=prompt,
        response_model=FinalRequirementDraft,
        system=SYNTHESIS_SYSTEM,
        task_type="req_synthesize",
        screen="requirements",
    )


async def rewrite_requirement_draft(
    existing_draft: FinalRequirementDraft,
    pm_instructions: str,
) -> FinalRequirementDraft:
    """Rewrite an existing draft based on PM revision instructions."""
    prompt = REANALYZE_PROMPT_TEMPLATE.format(
        draft_json=existing_draft.model_dump_json(),
        instructions=pm_instructions[:4000],
    )
    return await ai_call(
        prompt=prompt,
        response_model=FinalRequirementDraft,
        system=REANALYZE_SYSTEM,
        task_type="req_synthesize",
        screen="requirements",
    )
