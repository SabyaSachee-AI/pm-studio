"""Append-only gap fillers: add SRS FRs for uncovered PRD features, and link
orphaned Kanban tasks to functional requirements.

Both are strictly additive — existing FRs and tasks are never modified or removed,
only new FRs are appended (with a changelog) and orphaned tasks get a linked_fr set.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.models.prd import PRD
from app.models.srs import SRS
from app.models.task import Task
from app.services.ai.base import ai_call
from app.services.ai.model_override import clear_model_override, set_model_override
from app.services.prd.source import get_finalized_prd_body
from app.services.task.coverage import normalize_fr_id
from app.services.task.system_prompts import SYSTEM_TASK_ORDERS

logger = logging.getLogger(__name__)


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _next_fr_num(frs: list[dict]) -> int:
    mx = 0
    for f in frs:
        norm = normalize_fr_id(f.get("fr_number") or f.get("id") or "")
        tail = norm.split("-")[-1] if "-" in norm else ""
        if tail.isdigit():
            mx = max(mx, int(tail))
    return mx + 1


def _changelog(content: dict, msg: str) -> None:
    log = list(content.get("_changelog") or [])
    log.append({"at": datetime.now(timezone.utc).isoformat(), "change": msg})
    content["_changelog"] = log


# ── Stage 2: SRS FR gap-fill ────────────────────────────────────────────────

class _GapFR(BaseModel):
    feature_id: str = ""
    title: str
    description: str = ""
    priority: str = "should"
    test_criteria: list[str] = []


class _GapFRSet(BaseModel):
    requirements: list[_GapFR] = []


@celery_app.task(bind=True, name="gap.fill_srs")
def fill_srs_gaps_task(
    self, project_id: str, model_provider: str | None = None, model_id: str | None = None,
) -> dict[str, Any]:
    """For every PRD feature with no SRS functional requirement, generate FR(s)
    and append them to the SRS (never touches existing FRs)."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    try:
        srs = (
            db.query(SRS).filter(SRS.project_id == UUID(project_id), SRS.deleted_at.is_(None))
            .order_by(SRS.created_at.desc()).first()
        )
        if not srs or not srs.content_json:
            return {"error": "No SRS found — generate the SRS first."}
        prd = (
            db.query(PRD).filter(PRD.project_id == UUID(project_id), PRD.deleted_at.is_(None))
            .order_by(PRD.created_at.desc()).first()
        )
        prd_body = (get_finalized_prd_body(prd.content_json) if prd else None) or (prd.content_json if prd else {}) or {}
        features = prd_body.get("features") or []

        content = dict(srs.content_json)
        frs = list(content.get("functional_requirements") or [])
        covered = {str(f.get("linked_feature") or "") for f in frs if f.get("linked_feature")}
        uncovered = [
            f for f in features
            if (f.get("id") or f.get("feature_id")) and (f.get("id") or f.get("feature_id")) not in covered
        ]
        if not uncovered:
            return {"status": "ok", "added": 0, "message": "Every PRD feature already has SRS requirements."}

        feat_block = "\n".join(
            f"- [{f.get('id') or f.get('feature_id')}] {f.get('title','')}: {f.get('description','')}"
            for f in uncovered
        )
        existing_block = "\n".join(f"- {f.get('fr_number')}: {f.get('title')}" for f in frs[:60])
        prompt = (
            f"EXISTING SRS functional requirements (do NOT repeat these):\n{existing_block or '(none)'}\n\n"
            f"PRD FEATURES WITH NO REQUIREMENT YET (write requirements for each):\n{feat_block}\n\n"
            "For EACH feature above, write one or more concrete functional requirements. "
            "Each: a short title, a clear description, priority (must/should/nice), and 2-4 test_criteria. "
            "Set feature_id to the bracketed id it belongs to. Do not invent features not listed."
        )
        result = _run(ai_call(
            prompt=prompt, response_model=_GapFRSet,
            system="You are a senior business analyst writing precise SRS functional requirements.",
            max_tokens=8000, task_type="srs_generate", screen="srs",
        ))

        n = _next_fr_num(frs)
        added = 0
        for r in result.requirements:
            if not r.title.strip():
                continue
            frs.append({
                "fr_number": f"FR-{n:03d}",
                "title": r.title.strip(),
                "description": r.description.strip(),
                "priority": (r.priority or "should").strip(),
                "test_criteria": r.test_criteria or [],
                "linked_feature": r.feature_id or None,
            })
            n += 1
            added += 1

        if added:
            content["functional_requirements"] = frs
            _changelog(content, f"Added {added} functional requirement(s) via gap-fill for uncovered PRD features")
            srs.content_json = content
            db.commit()
        return {"status": "ok", "added": added,
                "message": f"Added {added} functional requirement(s) to the SRS. Now run 'Solve gaps' to create their tasks."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("fill_srs_gaps failed")
        return {"error": str(exc)[:400]}
    finally:
        db.close()
        clear_model_override()


# ── Stage 3: link orphaned tasks ────────────────────────────────────────────

class _OrphanMap(BaseModel):
    task_index: int
    fr_number: str = ""       # an existing FR-number, or "NEW"
    new_fr_title: str = ""    # used only when fr_number == "NEW"


class _OrphanSet(BaseModel):
    mappings: list[_OrphanMap] = []


@celery_app.task(bind=True, name="gap.link_orphans")
def link_orphaned_tasks_task(
    self, project_id: str, model_provider: str | None = None, model_id: str | None = None,
) -> dict[str, Any]:
    """Link each orphaned task to the best-matching FR. If a task is genuinely new
    scope, append a new FR to the SRS and link to it. Never deletes anything."""
    set_model_override(model_provider, model_id)
    db = SyncSessionLocal()
    try:
        srs = (
            db.query(SRS).filter(SRS.project_id == UUID(project_id), SRS.deleted_at.is_(None))
            .order_by(SRS.created_at.desc()).first()
        )
        if not srs or not srs.content_json:
            return {"error": "No SRS found."}
        content = dict(srs.content_json)
        frs = list(content.get("functional_requirements") or [])
        fr_ids = {normalize_fr_id(f.get("fr_number") or f.get("id") or "") for f in frs}

        tasks = (
            db.query(Task)
            .filter(Task.project_id == UUID(project_id), Task.deleted_at.is_(None),
                    Task.order_index.notin_(list(SYSTEM_TASK_ORDERS)))
            .order_by(Task.order_index.asc()).all()
        )

        def _linked(t: Task) -> bool:
            if t.linked_fr and normalize_fr_id(t.linked_fr) in fr_ids:
                return True
            return any(normalize_fr_id(r) in fr_ids for r in (t.fr_references or []))

        orphans = [t for t in tasks if not _linked(t)]
        if not orphans:
            return {"status": "ok", "linked": 0, "message": "No orphaned tasks — every task is linked to a requirement."}

        fr_block = "\n".join(f"- {f.get('fr_number')}: {f.get('title')}" for f in frs[:80])
        task_block = "\n".join(
            f"{i}: {t.title} — {(t.description or '')[:120]}" for i, t in enumerate(orphans)
        )
        prompt = (
            f"FUNCTIONAL REQUIREMENTS:\n{fr_block or '(none)'}\n\n"
            f"UNLINKED TASKS (index: title — description):\n{task_block}\n\n"
            "For each task, pick the FR-number it best implements. If a task is genuinely new "
            "scope not covered by any FR, set fr_number to 'NEW' and give a short new_fr_title. "
            "Return one mapping per task index."
        )
        result = _run(ai_call(
            prompt=prompt, response_model=_OrphanSet,
            system="You map implementation tasks to the requirements they fulfil.",
            max_tokens=4000, task_type="module_extract", screen="tasks",
        ))

        n = _next_fr_num(frs)
        linked = new_frs = 0
        for m in result.mappings:
            if m.task_index < 0 or m.task_index >= len(orphans):
                continue
            t = orphans[m.task_index]
            fr = (m.fr_number or "").strip()
            if fr.upper() == "NEW" and m.new_fr_title.strip():
                newid = f"FR-{n:03d}"
                frs.append({
                    "fr_number": newid, "title": m.new_fr_title.strip(),
                    "description": t.description or t.title, "priority": "should",
                    "test_criteria": [], "linked_feature": None,
                })
                fr_ids.add(newid)
                t.linked_fr = newid
                n += 1
                new_frs += 1
                linked += 1
            elif normalize_fr_id(fr) in fr_ids:
                t.linked_fr = normalize_fr_id(fr)
                linked += 1

        if new_frs:
            content["functional_requirements"] = frs
            _changelog(content, f"Added {new_frs} functional requirement(s) for new-scope orphaned tasks")
            srs.content_json = content
        if linked:
            db.commit()
        return {"status": "ok", "linked": linked, "new_frs": new_frs,
                "message": f"Linked {linked} task(s) to requirements ({new_frs} new FR(s) added)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("link_orphaned_tasks failed")
        return {"error": str(exc)[:400]}
    finally:
        db.close()
        clear_model_override()
