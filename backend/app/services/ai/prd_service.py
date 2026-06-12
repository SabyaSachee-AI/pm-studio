"""AI PRD rewrite, enrichment, and quality validation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.services.ai.base import ai_call


class FeatureItemExtended(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    depends_on: Optional[str] = None
    estimated_effort: Optional[str] = None  # small | medium | large


class UserStoryExtended(BaseModel):
    id: str
    as_a: str
    i_want_to: str
    so_that: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class PRDContentExtended(BaseModel):
    executive_summary: str
    problem_statement: str
    target_users: list[str]
    features: list[FeatureItemExtended]
    user_stories: list[UserStoryExtended]
    non_functional_requirements: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class QualityCheckItem(BaseModel):
    item: str
    passed: bool
    note: str = ""


class QualityCheckResult(BaseModel):
    score: int
    checks: list[QualityCheckItem]


REWRITE_SYSTEM = (
    "You are an expert product manager. "
    "Rewrite a PRD based on PM instructions. "
    "Return strictly structured JSON matching the schema."
)

REWRITE_PROMPT = """
Rewrite this Product Requirements Document according to the PM's instructions.

Current PRD (JSON):
{prd_json}

PM instructions:
{instructions}

Preserve feature and user story IDs where possible. Update IDs only when adding/removing items.
Include non_functional_requirements and risks sections.
"""


def _priority_key(priority: str) -> str:
    return priority.lower().replace("_", "-").strip()


def enrich_prd_content(content: dict[str, Any]) -> dict[str, Any]:
    """Normalize PRD JSON with IDs, extended fields, and workflow metadata."""
    enriched = dict(content)
    meta = dict(enriched.get("_meta") or {})

    features_raw = enriched.get("features") or []
    features: list[dict[str, Any]] = []
    for index, feature in enumerate(features_raw, start=1):
        item = dict(feature)
        item.setdefault("id", f"F-{index:03d}")
        item.setdefault("acceptance_criteria", [])
        item.setdefault("depends_on", None)
        item.setdefault("estimated_effort", None)
        features.append(item)
    enriched["features"] = features

    stories_raw = enriched.get("user_stories") or []
    stories: list[dict[str, Any]] = []
    for index, story in enumerate(stories_raw, start=1):
        item = dict(story)
        item.setdefault("id", f"US-{index:03d}")
        item.setdefault("acceptance_criteria", item.get("acceptance_criteria") or [])
        stories.append(item)
    enriched["user_stories"] = stories

    enriched.setdefault("non_functional_requirements", [])
    enriched.setdefault("risks", [])
    enriched.setdefault("out_of_scope", enriched.get("out_of_scope") or [])
    enriched.setdefault("success_metrics", enriched.get("success_metrics") or [])
    enriched.setdefault("assumptions", enriched.get("assumptions") or [])
    enriched.setdefault("target_users", enriched.get("target_users") or [])

    meta.setdefault("rewrite_count", 0)
    meta.setdefault("version_history", [])
    meta.setdefault("client_approval_status", "pending")
    enriched["_meta"] = meta
    return enriched


def compute_prd_stats(content: dict[str, Any]) -> dict[str, Any]:
    """Compute sidebar statistics from PRD content."""
    features = content.get("features") or []
    stories = content.get("user_stories") or []
    must_have = sum(1 for f in features if _priority_key(str(f.get("priority", ""))) == "must-have")
    should_have = sum(
        1 for f in features if _priority_key(str(f.get("priority", ""))) == "should-have"
    )
    nice_have = sum(
        1 for f in features if _priority_key(str(f.get("priority", ""))) == "nice-to-have"
    )
    criteria_count = sum(len(f.get("acceptance_criteria") or []) for f in features)
    criteria_count += sum(len(s.get("acceptance_criteria") or []) for s in stories)

    complexity = "Low"
    if len(features) >= 12 or criteria_count >= 40:
        complexity = "High"
    elif len(features) >= 7 or criteria_count >= 20:
        complexity = "Medium"

    meta = content.get("_meta") or {}
    return {
        "feature_count": len(features),
        "user_story_count": len(stories),
        "must_have": must_have,
        "should_have": should_have,
        "nice_to_have": nice_have,
        "acceptance_criteria_count": criteria_count,
        "complexity": complexity,
        "rewrite_count": meta.get("rewrite_count", 0),
        "quality_score": meta.get("quality_score"),
    }


def check_prd_quality(content: dict[str, Any]) -> QualityCheckResult:
    """Rule-based PRD completeness validation."""
    normalized = enrich_prd_content(content)
    checks: list[QualityCheckItem] = []

    summary = str(normalized.get("executive_summary", "")).strip()
    checks.append(
        QualityCheckItem(
            item="Executive summary present",
            passed=bool(summary),
            note="" if summary else "Add an executive summary",
        )
    )

    problem = str(normalized.get("problem_statement", "")).strip()
    checks.append(
        QualityCheckItem(
            item="Problem statement present",
            passed=bool(problem),
            note="" if problem else "Add a problem statement",
        )
    )

    features = normalized.get("features") or []
    features_with_criteria = all(
        len(f.get("acceptance_criteria") or []) > 0 for f in features
    ) if features else False
    checks.append(
        QualityCheckItem(
            item="Features have acceptance criteria",
            passed=features_with_criteria and len(features) > 0,
            note="" if features_with_criteria else "Each feature needs acceptance criteria",
        )
    )

    stories = normalized.get("user_stories") or []
    stories_complete = all(
        s.get("as_a") and s.get("i_want_to") and s.get("so_that") for s in stories
    ) if stories else False
    checks.append(
        QualityCheckItem(
            item="User stories complete",
            passed=stories_complete and len(stories) > 0,
            note="" if stories_complete else "Complete all user story fields",
        )
    )

    risks = normalized.get("risks") or []
    checks.append(
        QualityCheckItem(
            item="Risks identified",
            passed=len(risks) > 0,
            note="" if risks else "No risks identified (optional)",
        )
    )

    nfr = normalized.get("non_functional_requirements") or []
    checks.append(
        QualityCheckItem(
            item="Non-functional requirements listed",
            passed=len(nfr) > 0,
            note="" if nfr else "Consider adding NFRs",
        )
    )

    passed_count = sum(1 for c in checks if c.passed)
    score = int(round((passed_count / len(checks)) * 100)) if checks else 0
    return QualityCheckResult(score=score, checks=checks)


def append_version_history(
    content: dict[str, Any],
    version: int,
    trigger: str,
    note: str,
) -> dict[str, Any]:
    """Append a workflow version entry to PRD metadata."""
    updated = enrich_prd_content(content)
    meta = dict(updated.get("_meta") or {})
    history = list(meta.get("version_history") or [])
    history.append(
        {
            "version": version,
            "trigger": trigger,
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    meta["version_history"] = history
    if trigger == "rewrite":
        meta["rewrite_count"] = int(meta.get("rewrite_count", 0)) + 1
    updated["_meta"] = meta
    return updated


async def rewrite_prd_ai(
    existing_content: dict[str, Any],
    instructions: str,
) -> PRDContentExtended:
    """Rewrite a PRD using PM instructions."""
    normalized = enrich_prd_content(existing_content)
    clean = {k: v for k, v in normalized.items() if k != "_meta"}
    prompt = REWRITE_PROMPT.format(
        prd_json=str(clean)[:12000],
        instructions=instructions[:4000],
    )
    result = await ai_call(
        prompt=prompt,
        response_model=PRDContentExtended,
        system=REWRITE_SYSTEM,
        max_tokens=8000,
    )
    return result
