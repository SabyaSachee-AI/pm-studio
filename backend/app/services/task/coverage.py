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


# ── Multi-dimensional coverage: architecture entities + NFRs ─────────────────

def _task_haystack(tasks: list[Any]) -> str:
    """One lowercased blob of all task text + suggested file/endpoint/table."""
    parts: list[str] = []
    for t in tasks:
        for attr in ("title", "description", "suggested_file", "suggested_endpoint",
                     "suggested_table", "module_name"):
            v = getattr(t, attr, None)
            if v:
                parts.append(str(v))
    return " ".join(parts).lower()


def _endpoint_key(ep: dict[str, Any]) -> str:
    """A matchable token for an endpoint — its path minus base/params."""
    path = str(ep.get("full_path") or ep.get("path") or "").lower()
    segs = [s for s in path.split("/") if s and not s.startswith("{") and s not in ("api", "v1")]
    return "/".join(segs[-2:]) if segs else path


def _meter(total: int, covered: int, missing: list[str]) -> dict[str, Any]:
    return {
        "total": total,
        "covered": covered,
        "missing": missing[:20],
        "pct": round(covered / max(total, 1) * 100) if total else 100,
    }


def _norm_ep(v: str) -> str:
    """Normalize an endpoint path for comparison (drop base/version/params)."""
    s = str(v or "").lower().strip()
    segs = [x for x in s.split("/") if x and not x.startswith("{") and x not in ("api", "v1", "")]
    return "/".join(segs[-2:]) if segs else s


def _norm_tbl(v: str) -> str:
    s = str(v or "").lower().strip().replace(" ", "_")
    return s[:-1] if s.endswith("s") else s


def compute_plan_drift(arch: Any, tasks: list[Any]) -> dict[str, Any]:
    """Tasks that reference an endpoint/table NOT present in the architecture.

    Low-noise: only flags a task when its *structured* suggested_endpoint /
    suggested_table has NO fuzzy match among the architecture's entities. Tasks
    with no suggested entity (cross-cutting work) are never flagged.
    """
    if not arch:
        return {"count": 0, "items": []}
    ep_set = {_norm_ep(_endpoint_key(ep)) for ep in ((getattr(arch, "doc_api", None) or {}).get("endpoints") or [])}
    ep_set |= {_norm_ep(ep.get("full_path") or ep.get("path") or "") for ep in ((getattr(arch, "doc_api", None) or {}).get("endpoints") or [])}
    tbl_set = {_norm_tbl(t.get("name") or "") for t in ((getattr(arch, "doc_database", None) or {}).get("tables") or [])}
    ep_set.discard("")
    tbl_set.discard("")
    # If the architecture declares no entities at all, we can't judge drift.
    if not ep_set and not tbl_set:
        return {"count": 0, "items": []}

    items: list[dict[str, Any]] = []
    for t in tasks:
        sug_ep = str(getattr(t, "suggested_endpoint", "") or "").strip()
        sug_tbl = str(getattr(t, "suggested_table", "") or "").strip()
        reasons: list[str] = []
        if sug_ep and ep_set:
            n = _norm_ep(sug_ep)
            if n and not any(n == e or n in e or e in n for e in ep_set):
                reasons.append(f"endpoint '{sug_ep}'")
        if sug_tbl and tbl_set:
            n = _norm_tbl(sug_tbl)
            if n and not any(n == tb or n in tb or tb in n for tb in tbl_set):
                reasons.append(f"table '{sug_tbl}'")
        if reasons:
            items.append({
                "task_id": str(getattr(t, "id", "")),
                "title": getattr(t, "title", ""),
                "suggested_endpoint": sug_ep or None,
                "suggested_table": sug_tbl or None,
                "reason": " and ".join(reasons),
            })
    return {"count": len(items), "items": items[:50]}


def compute_full_coverage(
    srs_content: dict[str, Any] | None,
    arch: Any,
    tasks: list[Any],
) -> dict[str, Any]:
    """FR + API-endpoint + DB-table + NFR coverage — multi-dimensional gap view.

    Coverage here is heuristic (token/keyword presence in task text) — meant as a
    completeness signal, not a strict proof. arch is the Architecture row (or None).
    """
    hay = _task_haystack(tasks)
    # Structured signals first: what tasks explicitly declare they build.
    sug_endpoints = " ".join(str(getattr(t, "suggested_endpoint", "") or "") for t in tasks).lower()
    sug_tables = {str(getattr(t, "suggested_table", "") or "").lower().strip() for t in tasks if getattr(t, "suggested_table", None)}
    out: dict[str, Any] = {"fr": compute_coverage(srs_content, tasks)}

    api_doc = (getattr(arch, "doc_api", None) or {}) if arch else {}
    endpoints = api_doc.get("endpoints") or []
    ep_missing: list[str] = []
    ep_cov = 0
    for ep in endpoints:
        key = _endpoint_key(ep)
        path = str(ep.get("full_path") or ep.get("path") or "").lower()
        label = f"{ep.get('method', '')} {ep.get('full_path') or ep.get('path', '')}".strip()
        # structured (suggested_endpoint) → then path/key text match
        covered = (path and path in sug_endpoints) or (key and (key in sug_endpoints or key in hay))
        if covered:
            ep_cov += 1
        else:
            ep_missing.append(label or key)
    out["endpoints"] = _meter(len(endpoints), ep_cov, ep_missing)

    db_doc = (getattr(arch, "doc_database", None) or {}) if arch else {}
    tables = db_doc.get("tables") or []
    tbl_missing: list[str] = []
    tbl_cov = 0
    for t in tables:
        name = str(t.get("name") or "").lower().strip()
        covered = name and (name in sug_tables or name in hay or name.rstrip("s") in hay)
        if covered:
            tbl_cov += 1
        elif name:
            tbl_missing.append(name)
    out["tables"] = _meter(len(tables), tbl_cov, tbl_missing)

    nfrs = (srs_content or {}).get("non_functional_requirements") \
        or (srs_content or {}).get("nonfunctional_requirements") or []
    nfr_missing: list[str] = []
    nfr_cov = 0
    for n in nfrs:
        cat = (n.get("category") if isinstance(n, dict) else str(n)) or ""
        cat_l = str(cat).lower()
        # a couple of synonyms per common NFR category
        keys = [cat_l] + {
            "security": ["auth", "encrypt", "owasp"],
            "performance": ["cache", "latency", "optimi"],
            "reliability": ["backup", "health", "retry", "failover"],
            "scalability": ["scale", "load balanc"],
            "usability": ["accessib", "ux"],
            "maintainability": ["logging", "observability", "test"],
        }.get(cat_l, [])
        if any(k and k in hay for k in keys):
            nfr_cov += 1
        else:
            nfr_missing.append(str(cat))
    out["nfrs"] = _meter(len(nfrs), nfr_cov, nfr_missing)

    return out
