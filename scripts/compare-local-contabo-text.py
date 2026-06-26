"""Compare local vs Contabo text fields for spelling / content mismatches."""

from __future__ import annotations

import os

import psycopg2

LOCAL = os.getenv(
    "LOCAL_DATABASE_URL",
    "postgresql://pmstudio:devpassword123@127.0.0.1:5432/pmstudio",
)
REMOTE = os.getenv(
    "REMOTE_DATABASE_URL",
    "postgresql://pmstudio:prod_secure_password_123@185.185.80.147:5435/pmstudio",
)

TEXT_COLS = [
    ("projects", "id", ["name", "description"]),
    ("tasks", "id", ["title", "description"]),
    ("requirements", "id", ["original_filename", "extracted_text", "feedback_filename"]),
    ("architectures", "id", ["display_name"]),
    ("prds", "id", []),
    ("srs_documents", "id", []),
]

JSON_COLS = [
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


def fetch_map(conn, table: str, pk: str, cols: list[str]) -> dict[str, dict]:
    if not cols:
        return {}
    col_list = ", ".join([pk, *cols])
    with conn.cursor() as cur:
        cur.execute(f"SELECT {col_list} FROM {table}")
        rows = cur.fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        rid = str(row[0])
        out[rid] = {cols[i]: row[i + 1] for i in range(len(cols))}
    return out


def main() -> None:
    local = psycopg2.connect(LOCAL)
    remote = psycopg2.connect(REMOTE)

    print("=== Text column diffs (local vs Contabo) ===")
    for table, pk, cols in TEXT_COLS:
        if not cols:
            continue
        lm = fetch_map(local, table, pk, cols)
        rm = fetch_map(remote, table, pk, cols)
        for rid, lvals in lm.items():
            if rid not in rm:
                continue
            for col, lval in lvals.items():
                rval = rm[rid].get(col)
                if lval != rval and (lval is not None or rval is not None):
                    print(f"{table}.{col} id={rid}")
                    print(f"  local : {str(lval)[:120]}")
                    print(f"  remote: {str(rval)[:120]}")

    print("\n=== JSON column diffs (by serialized text) ===")
    for table, pk, cols in JSON_COLS:
        lm = fetch_map(local, table, pk, cols)
        rm = fetch_map(remote, table, pk, cols)
        for rid, lvals in lm.items():
            if rid not in rm:
                continue
            for col, lval in lvals.items():
                rval = rm[rid].get(col)
                ls = None if lval is None else str(lval)
                rs = None if rval is None else str(rval)
                if ls != rs:
                    has_cirt = (rs and "Cirtificate" in rs) or (ls and "Cirtificate" in ls)
                    flag = " [Cirtificate]" if has_cirt else ""
                    print(f"{table}.{col} id={rid}{flag}")

    print("\n=== Cirtificate scan on Contabo ===")
    with remote.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM projects WHERE name ILIKE '%cirtificate%'"
        )
        print("projects:", cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*) FROM architectures
            WHERE display_name ILIKE '%cirtificate%'
               OR doc_system_arch::text ILIKE '%cirtificate%'
               OR suite_canon::text ILIKE '%cirtificate%'
            """
        )
        print("architectures:", cur.fetchone()[0])

    local.close()
    remote.close()


if __name__ == "__main__":
    main()
