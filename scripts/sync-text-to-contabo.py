"""Push text + JSON column values from local Postgres to Contabo for matching IDs."""

from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2.extras import Json

LOCAL = os.getenv(
    "LOCAL_DATABASE_URL",
    "postgresql://pmstudio:devpassword123@127.0.0.1:5432/pmstudio",
)
REMOTE = os.getenv(
    "REMOTE_DATABASE_URL",
    "postgresql://pmstudio:prod_secure_password_123@185.185.80.147:5435/pmstudio",
)

TEXT_COLS: list[tuple[str, str, list[str]]] = [
    ("projects", "id", ["name", "description"]),
    ("tasks", "id", ["title", "description"]),
    ("requirements", "id", ["original_filename", "extracted_text", "feedback_filename"]),
    ("architectures", "id", ["display_name"]),
]

JSON_COLS: list[tuple[str, str, list[str]]] = [
    ("requirements", "id", ["analysis_result"]),
    ("prds", "id", ["content_json"]),
    ("srs_documents", "id", ["content_json"]),
    (
        "architectures",
        "id",
        [
            "doc_system_arch",
            "doc_database",
            "doc_api",
            "doc_frontend",
            "doc_security",
            "doc_uiux",
            "suite_canon",
            "generation_progress",
        ],
    ),
    ("builds", "id", ["scaffold", "quality_report", "generation_progress"]),
    ("knowledge_base_items", "id", ["content_json", "tags"]),
]


def table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
        return cur.fetchone()[0] is not None


def column_exists(conn, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            """,
            (table, column),
        )
        return cur.fetchone() is not None


def sync_columns(
    local_conn,
    remote_conn,
    table: str,
    pk: str,
    columns: list[str],
    json_mode: bool,
    dry_run: bool,
    project_id: str | None,
) -> int:
    if not table_exists(local_conn, table) or not table_exists(remote_conn, table):
        return 0

    valid_cols = [
        c
        for c in columns
        if column_exists(local_conn, table, c) and column_exists(remote_conn, table, c)
    ]
    if not valid_cols:
        return 0

    where = ""
    params: list[object] = []
    if project_id and table == "projects":
        where = f" WHERE {pk} = %s::uuid"
        params = [project_id]
    elif project_id and table in {
        "requirements",
        "prds",
        "srs_documents",
        "architectures",
        "tasks",
        "knowledge_base_items",
        "builds",
    }:
        where = " WHERE project_id = %s::uuid"
        params = [project_id]
    elif project_id and table == "generated_files":
        where = " WHERE build_id IN (SELECT id FROM builds WHERE project_id = %s::uuid)"
        params = [project_id]

    col_sql = ", ".join([pk, *valid_cols])
    with local_conn.cursor() as cur:
        cur.execute(f"SELECT {col_sql} FROM {table}{where}", params)
        local_rows = cur.fetchall()

    updates = 0
    with remote_conn.cursor() as cur:
        for row in local_rows:
            rid = row[0]
            for i, col in enumerate(valid_cols):
                value = row[i + 1]
                if json_mode:
                    cur.execute(
                        f"SELECT {col}::text FROM {table} WHERE {pk} = %s",
                        (rid,),
                    )
                    remote_val = cur.fetchone()
                    remote_text = None if remote_val is None else remote_val[0]
                    local_text = None if value is None else str(value)
                    if local_text == remote_text:
                        continue
                    if dry_run:
                        updates += 1
                        continue
                    cur.execute(
                        f"UPDATE {table} SET {col} = %s WHERE {pk} = %s",
                        (Json(value) if value is not None else None, rid),
                    )
                else:
                    cur.execute(
                        f"SELECT {col} FROM {table} WHERE {pk} = %s",
                        (rid,),
                    )
                    remote_val = cur.fetchone()
                    remote_value = None if remote_val is None else remote_val[0]
                    if value == remote_value:
                        continue
                    if dry_run:
                        updates += 1
                        continue
                    cur.execute(
                        f"UPDATE {table} SET {col} = %s WHERE {pk} = %s",
                        (value, rid),
                    )
                updates += cur.rowcount if not dry_run else 0
    return updates


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    project_id = None
    include_generated = "--include-generated-files" in sys.argv
    for arg in sys.argv[1:]:
        if arg.startswith("--project-id="):
            project_id = arg.split("=", 1)[1]

    if include_generated:
        TEXT_COLS.append(("generated_files", "id", ["path", "content"]))

    local_conn = psycopg2.connect(LOCAL)
    remote_conn = psycopg2.connect(REMOTE)
    remote_conn.autocommit = False

    print("Sync local text/JSON -> Contabo (matching IDs)")
    if project_id:
        print(f"  project filter: {project_id}")
    if dry_run:
        print("  mode: DRY RUN")

    total = 0
    for table, pk, cols in TEXT_COLS:
        n = sync_columns(local_conn, remote_conn, table, pk, cols, False, dry_run, project_id)
        if n:
            print(f"  {table} text: {n} update(s)")
        total += n

    for table, pk, cols in JSON_COLS:
        n = sync_columns(local_conn, remote_conn, table, pk, cols, True, dry_run, project_id)
        if n:
            print(f"  {table} json: {n} update(s)")
        total += n

    if dry_run:
        remote_conn.rollback()
        print(f"\nWould apply {total} column update(s).")
    else:
        remote_conn.commit()
        print(f"\nApplied {total} column update(s) on Contabo.")

    local_conn.close()
    remote_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
