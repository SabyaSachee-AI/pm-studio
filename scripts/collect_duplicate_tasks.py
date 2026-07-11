#!/usr/bin/env python3
"""Collect Kanban duplicate-task report + recent module-extract Celery logs."""

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

    project_id = os.getenv("PROJECT_ID")
    db_url = os.getenv(
        "SYNC_DATABASE_URL",
        "postgresql://pmstudio:devpassword123@127.0.0.1:5432/pmstudio",
    )

    report: dict = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "db_url_host": db_url.split("@")[-1] if "@" in db_url else db_url,
    }

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL")
        report["total_tasks"] = cur.fetchone()[0]

        dup_sql = """
            SELECT p.name, t.project_id::text, t.title, COUNT(*) AS copies,
                   array_agg(t.id::text ORDER BY t.created_at) AS task_ids,
                   MIN(t.created_at)::text AS first_created,
                   MAX(t.created_at)::text AS last_created
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            WHERE t.deleted_at IS NULL AND t.order_index < 99996
        """
        params: list = []
        if project_id:
            dup_sql += " AND t.project_id = %s::uuid"
            params.append(project_id)
        dup_sql += """
            GROUP BY p.name, t.project_id, t.title
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, t.title
            LIMIT 50
        """
        cur.execute(dup_sql, params)
        rows = cur.fetchall()
        report["duplicate_titles"] = [
            {
                "project": r[0],
                "project_id": r[1],
                "title": r[2],
                "copies": r[3],
                "task_ids": r[4],
                "first_created": r[5],
                "last_created": r[6],
            }
            for r in rows
        ]

        summary_sql = """
            SELECT p.name, t.project_id::text, COUNT(*) AS total,
                   COUNT(DISTINCT t.title) AS unique_titles
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            WHERE t.deleted_at IS NULL AND t.order_index < 99996
        """
        if project_id:
            summary_sql += " AND t.project_id = %s::uuid"
        summary_sql += " GROUP BY p.name, t.project_id ORDER BY total DESC"
        cur.execute(summary_sql, params)
        report["project_summaries"] = [
            {"project": r[0], "project_id": r[1], "total": r[2], "unique_titles": r[3]}
            for r in cur.fetchall()
        ]

        conn.close()
        report["interpretation"] = (
            "Likely double-click on Generate tasks — two extract jobs appended the same titles."
            if report["duplicate_titles"]
            else "No duplicate titles found among regular (non-system) tasks."
        )
    except Exception as exc:
        report["error"] = str(exc)
        report["interpretation"] = "Could not reach database — start postgres or set SYNC_DATABASE_URL."

    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"duplicate_tasks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_file}")
    print(json.dumps({"duplicate_count": len(report.get("duplicate_titles", [])), "interpretation": report.get("interpretation")}, indent=2))


if __name__ == "__main__":
    main()
