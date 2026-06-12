"""AI SRS rewrite, enrichment, quality validation, and IEEE 830 normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.services.ai.base import ai_call


class IntroductionSection(BaseModel):
    purpose: str = ""
    scope: str = ""
    definitions: list[str] = Field(default_factory=list)
    overview: str = ""


class OverallDescriptionSection(BaseModel):
    product_perspective: str = ""
    product_functions: list[str] = Field(default_factory=list)
    user_characteristics: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions_dependencies: list[str] = Field(default_factory=list)


class FunctionalRequirementExtended(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    inputs: str = ""
    processing: str = ""
    outputs: str = ""
    error_handling: str = ""
    linked_feature: Optional[str] = None
    test_criteria: list[str] = Field(default_factory=list)
    depends_on: Optional[str] = None
    complexity: Optional[str] = None


class NonFunctionalRequirementExtended(BaseModel):
    category: str
    id: str
    description: str
    metric: str = ""
    threshold: str = ""


class SystemInterfacesSection(BaseModel):
    user_interfaces: list[str] = Field(default_factory=list)
    hardware_interfaces: list[str] = Field(default_factory=list)
    software_interfaces: list[str] = Field(default_factory=list)
    communication_interfaces: list[str] = Field(default_factory=list)


class DataEntity(BaseModel):
    name: str
    fields: list[str] = Field(default_factory=list)
    relationships: str = ""


class DataRequirementsSection(BaseModel):
    data_entities: list[DataEntity] = Field(default_factory=list)
    data_storage: str = ""
    data_retention: str = ""


class SRSContentExtended(BaseModel):
    introduction: IntroductionSection
    overall_description: OverallDescriptionSection
    functional_requirements: list[FunctionalRequirementExtended]
    non_functional_requirements: list[NonFunctionalRequirementExtended]
    system_interfaces: SystemInterfacesSection = Field(default_factory=SystemInterfacesSection)
    data_requirements: DataRequirementsSection = Field(default_factory=DataRequirementsSection)
    security_requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class QualityCheckItem(BaseModel):
    item: str
    passed: bool
    note: str = ""


class QualityCheckResult(BaseModel):
    score: int
    checks: list[QualityCheckItem]
    traceability: dict[str, Any] = Field(default_factory=dict)


REWRITE_SYSTEM = (
    "You are an expert software architect writing IEEE 830 SRS documents. "
    "Rewrite the SRS based on PM instructions. Return strictly structured JSON."
)

REWRITE_PROMPT = """
Rewrite this IEEE 830 Software Requirements Specification per PM instructions.

Current SRS (JSON):
{srs_json}

PM instructions:
{instructions}

Preserve FR and NFR IDs where possible. Maintain PRD feature traceability via linked_feature.
"""


def _migrate_legacy_content(content: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy flat SRS schema to IEEE 830 nested structure."""
    if isinstance(content.get("introduction"), dict):
        return content

    intro_text = str(content.get("introduction", ""))
    scope_text = str(content.get("scope", ""))
    definitions = content.get("definitions") or []
    if isinstance(definitions, str):
        definitions = [definitions]

    frs_raw = content.get("functional_requirements") or []
    functional: list[dict[str, Any]] = []
    for index, fr in enumerate(frs_raw, start=1):
        if isinstance(fr, dict):
            item = dict(fr)
        else:
            # Legacy content may store FRs as plain strings
            item = {"title": str(fr), "description": str(fr)}
        item["id"] = item.get("id") or item.get("fr_number") or f"FR-{index:03d}"
        item.setdefault("inputs", "")
        item.setdefault("processing", "")
        item.setdefault("outputs", "")
        item.setdefault("error_handling", "")
        item.setdefault("linked_feature", None)
        item.setdefault("depends_on", None)
        item.setdefault("complexity", None)
        item.setdefault("test_criteria", item.get("test_criteria") or [])
        functional.append(item)

    nfrs_raw = content.get("non_functional_requirements") or content.get(
        "nonfunctional_requirements"
    ) or []
    non_functional: list[dict[str, Any]] = []
    for index, nfr in enumerate(nfrs_raw, start=1):
        if isinstance(nfr, dict):
            item = dict(nfr)
        else:
            # Legacy content may store NFRs as plain strings
            item = {"category": "General", "description": str(nfr)}
        item["id"] = item.get("id") or f"NFR-{index:03d}"
        non_functional.append(item)

    return {
        "introduction": {
            "purpose": intro_text,
            "scope": scope_text,
            "definitions": list(definitions),
            "overview": intro_text,
        },
        "overall_description": {
            "product_perspective": scope_text,
            "product_functions": [
                str(fr.get("title", "")) for fr in functional if fr.get("title")
            ],
            "user_characteristics": [],
            "constraints": list(content.get("constraints") or []),
            "assumptions_dependencies": list(content.get("assumptions") or []),
        },
        "functional_requirements": functional,
        "non_functional_requirements": non_functional,
        "system_interfaces": content.get("system_interfaces")
        or {
            "user_interfaces": [],
            "hardware_interfaces": [],
            "software_interfaces": [],
            "communication_interfaces": [],
        },
        "data_requirements": content.get("data_requirements")
        or {"data_entities": [], "data_storage": "", "data_retention": ""},
        "security_requirements": list(content.get("security_requirements") or []),
        "constraints": list(content.get("constraints") or []),
        "references": list(content.get("references") or []),
    }


def enrich_srs_content(content: dict[str, Any]) -> dict[str, Any]:
    """Normalize SRS JSON with IDs, metadata, and IEEE 830 structure."""
    migrated = _migrate_legacy_content(content)
    enriched = dict(migrated)
    meta = dict(enriched.get("_meta") or {})
    meta.setdefault("rewrite_count", 0)
    meta.setdefault("version_history", [])
    meta.setdefault("client_approval_status", "pending")
    enriched["_meta"] = meta
    return enriched


def compute_traceability(
    prd_content: dict[str, Any] | None,
    srs_content: dict[str, Any],
) -> dict[str, Any]:
    """Build PRD feature → SRS FR traceability matrix."""
    prd_stripped = {k: v for k, v in (prd_content or {}).items() if k != "_meta"}
    features = prd_stripped.get("features") or []
    feature_ids = [
        str(f.get("id") or f"F-{i + 1:03d}")
        for i, f in enumerate(features)
    ]
    frs = srs_content.get("functional_requirements") or []
    matrix: dict[str, list[str]] = {fid: [] for fid in feature_ids}
    for fr in frs:
        linked = fr.get("linked_feature")
        fr_id = str(fr.get("id") or fr.get("fr_number") or "")
        if linked and linked in matrix and fr_id:
            matrix[linked].append(fr_id)

    uncovered = [fid for fid, links in matrix.items() if not links]
    covered_count = len(feature_ids) - len(uncovered)
    total = len(feature_ids) or 1
    return {
        "matrix": matrix,
        "uncovered_features": uncovered,
        "features_covered": covered_count,
        "features_total": len(feature_ids),
        "all_covered": len(uncovered) == 0 and len(feature_ids) > 0,
        "coverage_ratio": f"{covered_count}/{len(feature_ids)}",
    }


def compute_srs_stats(
    content: dict[str, Any],
    prd_content: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute sidebar and list statistics."""
    frs = content.get("functional_requirements") or []
    nfrs = content.get("non_functional_requirements") or []
    must_have = sum(
        1 for fr in frs if "must" in str(fr.get("priority", "")).lower()
    )
    should_have = sum(
        1 for fr in frs if "should" in str(fr.get("priority", "")).lower()
    )
    nice_have = sum(
        1 for fr in frs if "nice" in str(fr.get("priority", "")).lower()
    )
    nfr_categories = {str(n.get("category", "")) for n in nfrs if n.get("category")}
    entities = (content.get("data_requirements") or {}).get("data_entities") or []
    trace = compute_traceability(prd_content, content)
    meta = content.get("_meta") or {}

    complexity = "Low"
    if len(frs) >= 15 or len(nfrs) >= 8:
        complexity = "High"
    elif len(frs) >= 8:
        complexity = "Medium"

    nfr_by_category: dict[str, int] = {}
    for nfr in nfrs:
        cat = str(nfr.get("category", "Other"))
        nfr_by_category[cat] = nfr_by_category.get(cat, 0) + 1

    return {
        "fr_count": len(frs),
        "nfr_count": len(nfrs),
        "must_have": must_have,
        "should_have": should_have,
        "nice_to_have": nice_have,
        "data_entity_count": len(entities),
        "nfr_categories_count": len(nfr_categories),
        "nfr_by_category": nfr_by_category,
        "uncovered_prd_features": len(trace.get("uncovered_features") or []),
        "traceability": trace,
        "complexity": complexity,
        "rewrite_count": meta.get("rewrite_count", 0),
        "quality_score": meta.get("quality_score"),
        "client_approval_status": meta.get("client_approval_status"),
    }


def check_srs_quality(
    content: dict[str, Any],
    prd_content: dict[str, Any] | None = None,
) -> QualityCheckResult:
    """IEEE 830 completeness and traceability validation."""
    normalized = enrich_srs_content(content)
    checks: list[QualityCheckItem] = []
    frs = normalized.get("functional_requirements") or []
    nfrs = normalized.get("non_functional_requirements") or []
    interfaces = normalized.get("system_interfaces") or {}
    data_req = normalized.get("data_requirements") or {}

    frs_with_tests = all(len(fr.get("test_criteria") or []) > 0 for fr in frs) if frs else False
    checks.append(
        QualityCheckItem(
            item="All FRs have test criteria",
            passed=frs_with_tests and len(frs) > 0,
            note="" if frs_with_tests else "Add test criteria to each FR",
        )
    )

    nfrs_measurable = all(
        n.get("metric") and n.get("threshold") for n in nfrs
    ) if nfrs else False
    checks.append(
        QualityCheckItem(
            item="NFRs have measurable thresholds",
            passed=nfrs_measurable,
            note="" if nfrs_measurable else "Add metric and threshold to NFRs",
        )
    )

    entities = data_req.get("data_entities") or []
    checks.append(
        QualityCheckItem(
            item="Data entities defined",
            passed=len(entities) > 0,
            note="" if entities else "Define at least one data entity",
        )
    )

    error_handling = all(fr.get("error_handling") for fr in frs) if frs else False
    checks.append(
        QualityCheckItem(
            item="Error handling specified",
            passed=error_handling,
            note="" if error_handling else "Specify error handling per FR",
        )
    )

    hw = interfaces.get("hardware_interfaces") or []
    checks.append(
        QualityCheckItem(
            item="Hardware interfaces documented",
            passed=len(hw) > 0,
            note="" if hw else "No hardware interfaces (OK for web apps)",
        )
    )

    security = normalized.get("security_requirements") or []
    checks.append(
        QualityCheckItem(
            item="Security requirements present",
            passed=len(security) > 0,
            note="" if security else "Add security requirements",
        )
    )

    trace = compute_traceability(prd_content, normalized)
    checks.append(
        QualityCheckItem(
            item="PRD feature traceability",
            passed=trace.get("all_covered", False) or not trace.get("features_total"),
            note=(
                "All PRD features have linked FRs"
                if trace.get("all_covered")
                else f"Uncovered: {', '.join(trace.get('uncovered_features') or [])}"
            ),
        )
    )

    passed_count = sum(1 for c in checks if c.passed)
    score = int(round((passed_count / len(checks)) * 100)) if checks else 0
    return QualityCheckResult(score=score, checks=checks, traceability=trace)


def append_version_history(
    content: dict[str, Any],
    version: int,
    trigger: str,
    note: str,
) -> dict[str, Any]:
    """Append workflow version entry to SRS metadata."""
    updated = enrich_srs_content(content)
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


async def rewrite_srs_ai(
    existing_content: dict[str, Any],
    instructions: str,
) -> SRSContentExtended:
    """Rewrite SRS using PM instructions."""
    normalized = enrich_srs_content(existing_content)
    clean = {k: v for k, v in normalized.items() if k != "_meta"}
    prompt = REWRITE_PROMPT.format(
        srs_json=str(clean)[:14000],
        instructions=instructions[:4000],
    )
    return await ai_call(
        prompt=prompt,
        response_model=SRSContentExtended,
        system=REWRITE_SYSTEM,
        max_tokens=12000,
    )
