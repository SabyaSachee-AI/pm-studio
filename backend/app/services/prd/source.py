"""Resolve authoritative PRD content for downstream generation (SRS, architecture, tasks)."""

from __future__ import annotations

import copy
from typing import Any

from app.models.prd import PRD, PRDStatus


def strip_prd_body(content: dict[str, Any]) -> dict[str, Any]:
    """PRD payload without workflow metadata."""
    return {k: v for k, v in content.items() if k != "_meta"}


def is_prd_finalized(content: dict[str, Any] | None, prd_status: PRDStatus | str | None = None) -> bool:
    """True when the PRD workflow is locked for downstream use."""
    if not content:
        return False
    meta = content.get("_meta") or {}
    if meta.get("workflow_finalized") is True:
        return True
    status = prd_status.value if hasattr(prd_status, "value") else str(prd_status or "")
    return status in {PRDStatus.approved.value, "approved"}


def is_prd_locked(prd: PRD) -> bool:
    """Finalized PRDs cannot be edited, rewritten, or regenerated."""
    if prd.status == PRDStatus.approved:
        return True
    if not prd.content_json:
        return False
    meta = (prd.content_json or {}).get("_meta") or {}
    if meta.get("workflow_finalized") and prd.status in {
        PRDStatus.submitted,
        PRDStatus.approved,
    }:
        return True
    return False


def snapshot_prd_on_finalize(
    content: dict[str, Any],
    *,
    version: int,
    confirmed_by_name: str,
    confirmed_by_id: str,
    confirmed_at: str,
) -> dict[str, Any]:
    """Store immutable finalized PRD body for all future downstream steps."""
    enriched = copy.deepcopy(content)
    meta = dict(enriched.get("_meta") or {})
    meta["workflow_finalized"] = True
    meta["finalized_content_json"] = strip_prd_body(enriched)
    meta["finalized_version"] = version
    meta["finalized_at"] = confirmed_at
    meta["finalized_by_name"] = confirmed_by_name
    meta["finalized_by_id"] = confirmed_by_id
    meta["confirmed_at"] = confirmed_at
    meta["confirmed_by_name"] = confirmed_by_name
    meta["confirmed_by_id"] = confirmed_by_id
    enriched["_meta"] = meta
    return enriched


def resolve_prd_for_downstream(prd: PRD) -> tuple[dict[str, Any], dict[str, Any]]:
    """Content + source metadata for SRS, architecture, modules, specs, traceability.

    When finalized, always uses ``finalized_content_json`` (the confirmed version),
    not later draft edits to ``content_json``.
    """
    raw = prd.content_json or {}
    meta = dict(raw.get("_meta") or {})
    finalized = is_prd_finalized(raw, prd.status)
    snapshot = get_finalized_prd_body(raw)

    if finalized and snapshot:
        version = int(meta.get("finalized_version") or prd.version)
        source = {
            "type": "finalized_prd",
            "version": version,
            "finalized": True,
            "finalized_at": meta.get("finalized_at"),
            "finalized_by_name": meta.get("finalized_by_name"),
            "instruction": (
                f"Use only finalized PRD version {version} as the authoritative product scope. "
                "Ignore any pre-finalization drafts."
            ),
        }
        return copy.deepcopy(snapshot), source

    source = {
        "type": "current_prd",
        "version": prd.version,
        "finalized": False,
        "instruction": "PRD is not finalized — using current draft content.",
    }
    return strip_prd_body(raw), source


def get_finalized_prd_body(content: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the locked finalized PRD body if available."""
    if not content:
        return None
    meta = content.get("_meta") or {}
    snapshot = meta.get("finalized_content_json")
    if isinstance(snapshot, dict) and snapshot:
        return snapshot
    if meta.get("workflow_finalized"):
        return strip_prd_body(content)
    return None


def get_prd_export_content(prd: PRD) -> dict[str, Any] | None:
    """Full PRD payload for PDF, portal, and KB — uses finalized snapshot when locked."""
    raw = prd.content_json
    if not raw:
        return None
    snapshot = get_finalized_prd_body(raw)
    if snapshot and is_prd_finalized(raw, prd.status):
        meta = dict(raw.get("_meta") or {})
        return {**copy.deepcopy(snapshot), "_meta": meta}
    return raw


def prd_eligible_for_downstream(prd: PRD) -> bool:
    """True when PRD is finalized with a locked snapshot for SRS, architecture, tasks."""
    if not prd.content_json:
        return False
    if not is_prd_finalized(prd.content_json, prd.status):
        return False
    return get_finalized_prd_body(prd.content_json) is not None
