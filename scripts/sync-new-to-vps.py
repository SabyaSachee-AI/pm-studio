#!/usr/bin/env python3
"""Copy only new PM Studio rows from local Postgres to VPS (no duplicates).

Compares primary keys (UUID) on each table. Rows that already exist on the
remote database are skipped. Inserts use ON CONFLICT (id) DO NOTHING.

Typical flow (from your Windows machine):

  1. Open SSH tunnel to VPS Postgres (keep this terminal open):
       ssh -L 5435:127.0.0.1:5435 sabya@185.185.80.147 -N

  2. Dry-run first:
       python scripts/sync-new-to-vps.py --dry-run

  3. Apply:
       python scripts/sync-new-to-vps.py

  4. Optional — copy uploaded requirement files:
       python scripts/sync-new-to-vps.py --with-uploads

Environment overrides:
  LOCAL_DATABASE_URL   default postgresql://pmstudio:devpassword123@localhost:5432/pmstudio
  REMOTE_DATABASE_URL  default postgresql://pmstudio:prod_secure_password_123@localhost:5435/pmstudio

Requires: pip install psycopg2-binary
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from typing import Any

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import Json, execute_values
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

# Insert order respects foreign keys. Self-referencing tables use multi-pass logic.
SYNC_TABLES: list[str] = [
    "organizations",
    "users",
    "clients",
    "projects",
    "requirements",
    "prds",
    "srs_documents",
    "architectures",
    "tasks",
    "task_specs",
    "task_status_logs",
    "knowledge_base_items",
    "reusable_modules",
    "decisions",
    "notifications",
    "document_versions",
    "screen_permissions",
    "builds",
    "build_stage_runs",
    "generated_files",
]

SELF_REF_PARENT_COL: dict[str, str] = {
    "requirements": "parent_requirement_id",
}

DEFAULT_LOCAL = "postgresql://pmstudio:devpassword123@localhost:5432/pmstudio"
DEFAULT_REMOTE = "postgresql://pmstudio:prod_secure_password_123@localhost:5435/pmstudio"


def connect(url: str):
    return psycopg2.connect(url)


def table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
        return cur.fetchone()[0] is not None


def get_columns(conn, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def load_remote_ids(conn, table: str) -> set[Any]:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT id FROM {}").format(sql.Identifier(table)))
        return {row[0] for row in cur.fetchall()}


def fetch_local_rows(
    conn,
    table: str,
    columns: list[str],
    since: datetime | None,
    project_ids: list[str] | None,
) -> list[tuple[Any, ...]]:
    col_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    query = sql.SQL("SELECT {} FROM {}").format(col_sql, sql.Identifier(table))
    clauses: list[sql.Composable] = []
    params: list[Any] = []

    if since is not None:
        clauses.append(sql.SQL("created_at >= %s"))
        params.append(since)

    if project_ids and table == "projects":
        clauses.append(sql.SQL("id = ANY(%s::uuid[])"))
        params.append(project_ids)
    elif project_ids and table in {
        "requirements",
        "prds",
        "srs_documents",
        "architectures",
        "tasks",
        "knowledge_base_items",
        "decisions",
        "builds",
    }:
        clauses.append(sql.SQL("project_id = ANY(%s::uuid[])"))
        params.append(project_ids)
    elif project_ids and table == "generated_files":
        clauses.append(
            sql.SQL(
                "build_id IN (SELECT id FROM builds WHERE project_id = ANY(%s::uuid[]))"
            )
        )
        params.append(project_ids)
    elif project_ids and table == "build_stage_runs":
        clauses.append(
            sql.SQL(
                "build_id IN (SELECT id FROM builds WHERE project_id = ANY(%s::uuid[]))"
            )
        )
        params.append(project_ids)
    elif project_ids and table in {"task_specs", "task_status_logs"}:
        clauses.append(
            sql.SQL("task_id IN (SELECT id FROM tasks WHERE project_id = ANY(%s::uuid[]))")
        )
        params.append(project_ids)

    if clauses:
        query = sql.SQL("{} WHERE {}").format(
            query, sql.SQL(" AND ").join(clauses)
        )

    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def get_json_columns(conn, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
              AND udt_name IN ('json', 'jsonb')
            """,
            (table,),
        )
        return {row[0] for row in cur.fetchall()}


def adapt_rows_for_insert(
    columns: list[str],
    rows: list[tuple[Any, ...]],
    json_columns: set[str],
) -> list[tuple[Any, ...]]:
    if not json_columns:
        return rows
    json_indices = [columns.index(name) for name in columns if name in json_columns]
    adapted: list[tuple[Any, ...]] = []
    for row in rows:
        values = list(row)
        for idx in json_indices:
            value = values[idx]
            if value is not None and isinstance(value, (dict, list)):
                values[idx] = Json(value)
        adapted.append(tuple(values))
    return adapted


def insert_rows(
    conn,
    table: str,
    columns: list[str],
    rows: list[tuple[Any, ...]],
    dry_run: bool,
) -> int:
    if not rows:
        return 0
    if dry_run:
        return len(rows)

    json_columns = get_json_columns(conn, table)
    payload = adapt_rows_for_insert(columns, rows, json_columns)

    col_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT (id) DO NOTHING").format(
        sql.Identifier(table),
        col_sql,
    )
    with conn.cursor() as cur:
        execute_values(cur, insert_sql.as_string(conn), payload, page_size=200)
    conn.commit()
    return len(rows)


def sync_table(
    local_conn,
    remote_conn,
    table: str,
    since: datetime | None,
    project_ids: list[str] | None,
    dry_run: bool,
) -> int:
    if not table_exists(local_conn, table):
        print(f"  skip {table}: not on local")
        return 0
    if not table_exists(remote_conn, table):
        print(f"  skip {table}: not on remote (run alembic upgrade head on VPS first)")
        return 0

    columns = get_columns(local_conn, table)
    if "id" not in columns:
        print(f"  skip {table}: no id column")
        return 0

    remote_ids = load_remote_ids(remote_conn, table)
    local_rows = fetch_local_rows(local_conn, table, columns, since, project_ids)
    id_idx = columns.index("id")
    missing = [row for row in local_rows if row[id_idx] not in remote_ids]

    if not missing:
        print(f"  {table}: 0 new")
        return 0

    parent_col = SELF_REF_PARENT_COL.get(table)
    if parent_col and parent_col in columns:
        parent_idx = columns.index(parent_col)
        inserted = 0
        pending = list(missing)
        for attempt in range(20):
            ready: list[tuple[Any, ...]] = []
            still_pending: list[tuple[Any, ...]] = []
            for row in pending:
                parent_id = row[parent_idx]
                if parent_id is None or parent_id in remote_ids:
                    ready.append(row)
                else:
                    still_pending.append(row)
            count = insert_rows(remote_conn, table, columns, ready, dry_run)
            inserted += count
            for row in ready:
                remote_ids.add(row[id_idx])
            pending = still_pending
            if not pending:
                break
            if not ready:
                print(
                    f"  WARN {table}: {len(pending)} rows blocked by missing parent "
                    f"({parent_col}); sync parents first or use full project scope"
                )
                break
        print(f"  {table}: {inserted} new" + (" (dry-run)" if dry_run else ""))
        return inserted

    count = insert_rows(remote_conn, table, columns, missing, dry_run)
    print(f"  {table}: {count} new" + (" (dry-run)" if dry_run else ""))
    return count


def sync_uploads(project_ids: list[str] | None, dry_run: bool) -> None:
    """Copy backend/uploads files that exist locally but not on VPS."""
    local_root = os.path.join(os.path.dirname(__file__), "..", "backend", "uploads")
    local_root = os.path.abspath(local_root)
    if not os.path.isdir(local_root):
        print("  uploads: local folder not found, skipping")
        return

    remote = "sabya@185.185.80.147:/opt/apps/pm-studio/backend/uploads/"
    rsync_cmd = [
        "rsync",
        "-avz",
        "--ignore-existing",
        f"{local_root}/",
        remote,
    ]
    if dry_run:
        rsync_cmd.insert(1, "--dry-run")
    print("  uploads:", " ".join(rsync_cmd))
    if not dry_run:
        try:
            subprocess.run(rsync_cmd, check=True)
        except FileNotFoundError:
            print(
                "  uploads: rsync not found on Windows — use WinSCP or:\n"
                "    scp -r backend/uploads/* sabya@185.185.80.147:/opt/apps/pm-studio/backend/uploads/"
            )
        except subprocess.CalledProcessError as exc:
            print(f"  uploads: failed ({exc.returncode})")


def parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"invalid date: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-url",
        default=os.getenv("LOCAL_DATABASE_URL", DEFAULT_LOCAL),
        help="Local Postgres URL (default: local Docker on 5432)",
    )
    parser.add_argument(
        "--remote-url",
        default=os.getenv("REMOTE_DATABASE_URL", DEFAULT_REMOTE),
        help="VPS Postgres URL (default: localhost:5435 via SSH tunnel)",
    )
    parser.add_argument(
        "--since",
        type=parse_since,
        default=None,
        help="Only consider local rows with created_at >= this (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--project-id",
        action="append",
        dest="project_ids",
        metavar="UUID",
        help="Limit sync to one or more projects (repeatable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts only; no writes")
    parser.add_argument(
        "--with-uploads",
        action="store_true",
        help="Also rsync backend/uploads (new files only)",
    )
    args = parser.parse_args()

    print("PM Studio — incremental sync (new rows only)")
    print(f"  local : {args.local_url.split('@')[-1]}")
    print(f"  remote: {args.remote_url.split('@')[-1]}")
    if args.since:
        print(f"  since : {args.since.isoformat()}")
    if args.project_ids:
        print(f"  projects: {', '.join(args.project_ids)}")
    if args.dry_run:
        print("  mode  : DRY RUN")
    print()

    try:
        local_conn = connect(args.local_url)
        remote_conn = connect(args.remote_url)
    except psycopg2.Error as exc:
        print(f"ERROR: cannot connect — {exc}", file=sys.stderr)
        print(
            "\nTip: open SSH tunnel first:\n"
            "  ssh -L 5435:127.0.0.1:5435 sabya@185.185.80.147 -N",
            file=sys.stderr,
        )
        return 1

    total = 0
    try:
        for table in SYNC_TABLES:
            total += sync_table(
                local_conn,
                remote_conn,
                table,
                args.since,
                args.project_ids,
                args.dry_run,
            )
    finally:
        local_conn.close()
        remote_conn.close()

    print()
    print(f"Done — {total} row(s) {'would be ' if args.dry_run else ''}inserted.")

    if args.with_uploads:
        print()
        print("Upload files:")
        sync_uploads(args.project_ids, args.dry_run)

    if not args.dry_run and total > 0:
        print(
            "\nNote: existing rows updated locally are NOT pushed (new IDs only). "
            "Re-run with --dry-run anytime to preview."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
