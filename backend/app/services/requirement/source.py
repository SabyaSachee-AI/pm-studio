"""Resolve which requirement content downstream generators (PRD, SRS) must use."""

from __future__ import annotations

from typing import Any

from app.models.requirement import Requirement


def is_requirement_finalized(analysis: dict[str, Any] | None) -> bool:
    """True when the requirement workflow is locked for PRD generation."""
    return bool((analysis or {}).get("finalized"))


def get_finalized_draft(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Return the authoritative finalized draft payload (latest version).

    Prefers ``final_draft_json``. Falls back to the highest-version entry in
    ``draft_history`` when the top-level field is missing.
    """
    draft = analysis.get("final_draft_json")
    if isinstance(draft, dict) and draft:
        return draft

    history = analysis.get("draft_history") or []
    if not history:
        return None

    latest = max(history, key=lambda entry: int(entry.get("version") or 0))
    historical = latest.get("draft")
    if isinstance(historical, dict) and historical:
        return historical
    return None


def finalized_draft_version(analysis: dict[str, Any], draft: dict[str, Any] | None = None) -> int:
    """Resolve the finalized draft version number for display and metadata."""
    history = analysis.get("draft_history") or []
    versions = [int(entry.get("version", 0)) for entry in history if entry.get("version") is not None]
    if versions:
        return max(versions)
    if draft or analysis.get("final_draft_json"):
        return 1
    return 0


def final_draft_to_requirement_text(draft: dict[str, Any], *, version: int | None = None) -> str:
    """Serialize a finalized requirement draft into plain text for AI generation."""
    header = "# Final requirement document (authoritative — overrides original upload)"
    if version and version > 0:
        header = f"# Final requirement document — version {version} (authoritative — overrides original upload)"

    lines: list[str] = [header, ""]

    overview = draft.get("project_overview")
    if overview:
        lines.extend(["## Project overview", str(overview), ""])

    users = draft.get("users_and_roles")
    if users:
        lines.extend(["## Users and roles", str(users), ""])

    features = draft.get("confirmed_features") or []
    if features:
        lines.append("## Confirmed features")
        lines.extend(f"- {item}" for item in features)
        lines.append("")

    decisions = draft.get("technical_decisions") or []
    if decisions:
        lines.append("## Technical decisions")
        lines.extend(f"- {item}" for item in decisions)
        lines.append("")

    out_of_scope = draft.get("out_of_scope") or []
    if out_of_scope:
        lines.append("## Out of scope")
        lines.extend(f"- {item}" for item in out_of_scope)
        lines.append("")

    open_questions = draft.get("open_questions") or []
    if open_questions:
        lines.append("## Open questions")
        lines.extend(f"- {item}" for item in open_questions)
        lines.append("")

    feedback = draft.get("client_feedback_summary") or []
    if feedback:
        lines.append("## Client feedback incorporated")
        for item in feedback:
            if isinstance(item, dict):
                q = item.get("question", "")
                a = item.get("answer", "")
                lines.append(f"Q: {q}")
                lines.append(f"A: {a}")
                lines.append("")

    notes = draft.get("synthesis_notes")
    if notes:
        lines.extend(["## Synthesis notes", str(notes), ""])

    return "\n".join(lines).strip()


def mandatory_constraints_for_prd(analysis: dict[str, Any]) -> str:
    """Build non-negotiable requirements block for PRD generation prompts."""
    draft = get_finalized_draft(analysis)
    if not draft:
        return ""

    lines = [
        "## Mandatory requirements (must appear explicitly in PRD features, stories, or NFRs)",
        "",
        "Do NOT substitute generic descriptions. Preserve exact thresholds, architecture terms, "
        "and delivery mechanisms from the finalized requirement draft below.",
        "",
    ]

    for item in draft.get("technical_decisions") or []:
        lines.append(f"- {item}")

    for item in draft.get("confirmed_features") or []:
        lines.append(f"- {item}")

    for item in draft.get("out_of_scope") or []:
        lines.append(f"- OUT OF SCOPE: {item}")

    return "\n".join(lines).strip()


def resolve_requirement_for_generation(
    requirement: Requirement,
) -> tuple[str, dict[str, Any]]:
    """Return requirement text and enriched analysis metadata for PRD/SRS generation.

    When finalized, ALWAYS uses the latest finalized draft (``final_draft_json`` or
    newest ``draft_history`` entry). Never falls back to the original PDF
    ``extracted_text`` for finalized requirements.
    """
    analysis: dict[str, Any] = dict(requirement.analysis_result or {})

    if is_requirement_finalized(analysis):
        draft = get_finalized_draft(analysis)
        if not draft:
            analysis["_generation_source"] = {
                "type": "missing_final_draft",
                "finalized": True,
                "error": "Requirement is finalized but has no final draft content.",
            }
            return "", analysis

        version = finalized_draft_version(analysis, draft)
        analysis["_generation_source"] = {
            "type": "final_draft_json",
            "version": version,
            "finalized": True,
            "instruction": (
                f"Generate strictly from Final Requirement Draft version {version}. "
                "Do not use or infer requirements from the original uploaded PDF."
            ),
        }
        return final_draft_to_requirement_text(draft, version=version), analysis

    analysis["_generation_source"] = {
        "type": "extracted_text",
        "finalized": False,
        "instruction": "Requirement not finalized — using original extracted upload text.",
    }
    return requirement.extracted_text or "", analysis
