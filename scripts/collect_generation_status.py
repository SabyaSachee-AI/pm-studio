#!/usr/bin/env python3
"""Snapshot current build/generation state from DB + Redis queues."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.chdir(ROOT / "backend")


def main() -> None:
    import psycopg2
    from celery.result import AsyncResult

    from app.core.celery_app import celery_app

    db_url = os.getenv(
        "SYNC_DATABASE_URL",
        "postgresql://pmstudio:devpassword123@127.0.0.1:5432/pmstudio",
    )
    build_id = os.getenv("BUILD_ID", "cb78187a-6e3e-4b5a-b4a2-ad8d67191db5")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.id, p.name, b.status, b.generation_task_id, b.generation_progress,
               b.github_full_name, b.repo_url, b.quality_score, b.last_error,
               (SELECT count(*) FROM generated_files gf WHERE gf.build_id=b.id AND gf.deleted_at IS NULL)
        FROM builds b
        JOIN projects p ON p.id = b.project_id
        WHERE b.id = %s::uuid
        """,
        (build_id,),
    )
    row = cur.fetchone()
    if not row:
        print(f"Build {build_id} not found")
        sys.exit(1)

    task_id = row[3]
    job = None
    if task_id:
        r = AsyncResult(task_id, app=celery_app)
        job = {"task_id": task_id, "status": r.status, "ready": r.ready()}
        if r.ready():
            job["result"] = str(r.result)[:500]

    try:
        import redis

        rds = redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
        queues = {"celery": rds.llen("celery"), "build": rds.llen("build")}
    except Exception as exc:
        queues = {"error": str(exc)}

    report = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "build_id": str(row[0]),
        "project": row[1],
        "build_status": row[2],
        "generation_progress": row[4],
        "github_repo": row[5],
        "repo_url": row[6],
        "quality_score": float(row[7]) if row[7] is not None else None,
        "last_error": row[8],
        "generated_file_count": row[9],
        "celery_job": job,
        "redis_queue_depth": queues,
        "interpretation": _interpret(row[2], row[4], queues),
    }

    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"generation_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_file}")
    print(json.dumps(report["interpretation"], indent=2))


def _interpret(status: str, progress: dict | None, queues: dict) -> dict:
    progress = progress or {}
    phase = progress.get("phase", "unknown")
    active = (queues.get("celery") or 0) + (queues.get("build") or 0) > 0
    if active:
        what = "Celery worker is processing queued tasks"
    elif status == "generating":
        what = f"Code build in progress — task {progress.get('current_index', '?')}/{progress.get('total_tasks', '?')}: {progress.get('current_task', '')}"
    elif status == "qa":
        what = "Code generation finished; waiting on GitHub QA / CI (not AI generation)"
    elif phase == "completed":
        what = "Code generation completed; check build status for next stage"
    else:
        what = f"Build status={status}, phase={phase}"
    return {
        "what_is_happening": what,
        "celery_queues_empty": not active,
        "codegen_complete": phase == "completed" or status in ("qa", "ready", "failed"),
    }


if __name__ == "__main__":
    main()
