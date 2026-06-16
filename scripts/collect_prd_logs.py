#!/usr/bin/env python3
"""Collect PRD generation session logs (DB, Celery, terminals)."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import redis
from celery.result import AsyncResult

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.celery_app import celery_app  # noqa: E402
from app.core.database import SyncSessionLocal  # noqa: E402
from app.models.prd import PRD  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.requirement import Requirement  # noqa: E402
from app.services.requirement.source import resolve_requirement_for_generation  # noqa: E402

TERMINALS = Path(
    r"C:\Users\ssd\.cursor\projects\f-knowledgebase-ProjectPreparation-PMS-pm-studio\terminals"
)
KNOWN_TASK_IDS = [
    "87ef0b4c-7c37-4e36-9fb3-f203b5951c0b",
    "6b81c0b7-70d2-45b3-90a2-e46bee49d25f",
    "8b31df23-1870-4d11-8aad-8e5fa62bcec9",
]


def scan_prd_lines() -> list[dict]:
    pat = re.compile(
        r"prd|PRD|8eed989f|87ef0b4c|6b81c0b7|8b31df23|prd\.generate|/prds/",
        re.I,
    )
    lines: list[dict] = []
    if not TERMINALS.is_dir():
        return lines
    for path in sorted(TERMINALS.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                lines.append(
                    {"file": path.name, "line": i, "text": line.strip()[:600]}
                )
    return lines[-300:]


def celery_task_snapshot(task_id: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    snap: dict = {"task_id": task_id, "state": result.state}
    if isinstance(result.info, dict):
        snap["meta"] = result.info
    elif result.info:
        snap["info"] = str(result.info)[:500]
    if result.ready():
        snap["result"] = result.result
    try:
        client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
        raw = client.get(f"celery-task-meta-{task_id}")
        if raw:
            snap["redis_meta"] = json.loads(raw)
    except Exception as exc:
        snap["redis_error"] = str(exc)
    return snap


def collect(prd_id: str | None = None) -> dict:
    report: dict = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scope": "prd_generation_session",
    }

    with SyncSessionLocal() as db:
        query = db.query(PRD).filter(PRD.deleted_at.is_(None))
        if prd_id:
            prd = query.filter(PRD.id == UUID(prd_id)).first()
            prds = [prd] if prd else []
        else:
            prds = query.order_by(PRD.updated_at.desc()).limit(5).all()

        report["prds"] = []
        all_task_ids: list[str] = list(KNOWN_TASK_IDS)

        for prd in prds:
            if prd is None:
                continue
            project = db.query(Project).filter(Project.id == prd.project_id).first()
            req = (
                db.query(Requirement).filter(Requirement.id == prd.requirement_id).first()
                if prd.requirement_id
                else None
            )
            req_source = None
            if req:
                _, analysis = resolve_requirement_for_generation(req)
                req_source = analysis.get("_generation_source")

            content = prd.content_json or {}
            meta = content.get("_meta") or {}
            features = content.get("features") or []
            stories = content.get("user_stories") or []

            if prd.generation_task_id and prd.generation_task_id not in all_task_ids:
                all_task_ids.append(prd.generation_task_id)

            report["prds"].append(
                {
                    "id": str(prd.id),
                    "project": project.name if project else None,
                    "project_id": str(prd.project_id),
                    "requirement_id": str(prd.requirement_id) if prd.requirement_id else None,
                    "requirement_file": req.original_filename if req else None,
                    "version": prd.version,
                    "status": prd.status.value if hasattr(prd.status, "value") else str(prd.status),
                    "generation_task_id": prd.generation_task_id,
                    "created_at": prd.created_at.isoformat() if prd.created_at else None,
                    "updated_at": prd.updated_at.isoformat() if prd.updated_at else None,
                    "requirement_source": meta.get("requirement_source") or req_source,
                    "rewrite_count": meta.get("rewrite_count", 0),
                    "version_history_count": len(meta.get("version_history") or []),
                    "content_stats": {
                        "features": len(features),
                        "user_stories": len(stories),
                        "has_executive_summary": bool(content.get("executive_summary")),
                    },
                    "executive_summary_preview": (content.get("executive_summary") or "")[:500],
                    "feature_titles": [f.get("title") for f in features[:20]],
                }
            )

    report["celery_tasks"] = [celery_task_snapshot(tid) for tid in all_task_ids]
    report["terminal_prd_lines"] = scan_prd_lines()
    logs_dir = ROOT / "logs"
    report["prior_snapshots"] = sorted(p.name for p in logs_dir.glob("prd*.json"))
    return report


def main() -> None:
    prd_id = sys.argv[1] if len(sys.argv) > 1 else "8eed989f-00d1-40a2-8d21-c04c729a4ca3"
    report = collect(prd_id)
    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"prd_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_file}")
    if report["prds"]:
        p = report["prds"][0]
        print(
            json.dumps(
                {
                    "prd_id": p["id"],
                    "status": p["status"],
                    "requirement_source": p.get("requirement_source"),
                    "features": p["content_stats"]["features"],
                    "celery_tasks": len(report["celery_tasks"]),
                    "terminal_lines": len(report["terminal_prd_lines"]),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
