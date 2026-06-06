"""Preliminary cost estimation from requirement analysis."""

from app.schemas.requirement import GapCategory, RequirementAnalysisSchema


COMPLEXITY_MULTIPLIER = {
    GapCategory.CRITICAL: 1.5,
    GapCategory.IMPORTANT: 1.2,
    GapCategory.MINOR: 1.0,
}

BASE_FEATURE_COST = 8_000


def estimate_cost(analysis: RequirementAnalysisSchema) -> dict[str, int | float | str]:
    """Estimate a min/max budget range from analysis gaps and scope."""
    gap_count = len(analysis.gaps)
    critical_count = sum(1 for gap in analysis.gaps if gap.category == GapCategory.CRITICAL)
    complexity = 1.0 + (critical_count * 0.15) + (gap_count * 0.05)
    feature_units = max(3, gap_count + len(analysis.technical_questions))
    min_budget = int(feature_units * BASE_FEATURE_COST * 0.8 * complexity)
    max_budget = int(feature_units * BASE_FEATURE_COST * 1.4 * complexity)
    return {
        "feature_units": feature_units,
        "complexity_multiplier": round(complexity, 2),
        "min_budget_usd": min_budget,
        "max_budget_usd": max_budget,
        "currency": "USD",
        "note": "Preliminary estimate based on gap count and complexity. Not a formal quote.",
    }
