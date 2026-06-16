"""Single source of truth for FR → task coverage.

All gap analysis (the /coverage endpoint, the /traceability matrix, and the
"Solve gaps" worker) must use these helpers so they always agree. The key is
canonical FR-ID normalization: the AI may emit "FR-6", "6", "fr-006" or
"FR-006" for the same requirement — we collapse them to one form before
comparing, so coverage matching is robust to format drift.
"""

from __future__ import annotations

import re
from typing import Any


def normalize_fr_id(raw: Any) -> str:
    """Collapse any FR-id spelling to a canonical form.

    Examples:
        "FR-6"      -> "FR-006"
        "6"         -> "FR-006"
        "fr006"     -> "FR-006"
        "FR-006: x" -> "FR-006"
        "NFR-2"     -> "NFR-002"
        ""          -> ""
    Non-numeric ids fall back to an uppercased, trimmed token.
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    # Capture an optional alpha prefix (FR / NFR / etc.) + the first number group
    m = re.match(r"\s*([A-Za-z]+)?[\s\-_]*0*(\d+)", s)
    if m:
        prefix = (m.group(1) or "FR").upper()
        num = int(m.group(2))
        return f"{prefix}-{num:03d}"
    # No digits — return a clean uppercase token (e.g. "AUTH")
    return re.sub(r"\s+", " ", s).strip().upper()


def extract_fr_ids(srs_content: dict[str, Any] | None) -> list[str]:
    """Ordered, de-duplicated, normalized FR ids declared in the SRS."""
    out: list[str] = []
    seen: set[str] = set()
    for fr in (srs_content or {}).get("functional_requirements", []) or []:
        if not isinstance(fr, dict):
            continue
        raw = fr.get("fr_number") or fr.get("id") or fr.get("fr_id") or ""
        fid = normalize_fr_id(raw)
        if fid and fid not in seen:
            seen.add(fid)
            out.append(fid)
    return out


def covered_fr_ids(tasks: list[Any]) -> set[str]:
    """Normalized set of FR ids that have at least one task covering them."""
    covered: set[str] = set()
    for t in tasks:
        linked = getattr(t, "linked_fr", None)
        if linked:
            covered.add(normalize_fr_id(linked))
        for ref in (getattr(t, "fr_references", None) or []):
            if ref:
                covered.add(normalize_fr_id(ref))
    return covered


def compute_coverage(
    srs_content: dict[str, Any] | None,
    tasks: list[Any],
) -> dict[str, Any]:
    """Authoritative FR coverage summary shared by all gap views."""
    all_frs = extract_fr_ids(srs_content)
    covered = covered_fr_ids(tasks)
    missing = [f for f in all_frs if f not in covered]
    covered_count = len(all_frs) - len(missing)
    return {
        "total_frs": len(all_frs),
        "covered_frs": covered_count,
        "missing_frs": missing,
        "coverage_pct": round(covered_count / max(len(all_frs), 1) * 100),
    }
