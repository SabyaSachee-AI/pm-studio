"""One-time fix: Cirtificate -> Certificate on Contabo (or any Postgres URL)."""

from __future__ import annotations

import os
import sys

import psycopg2

REMOTE = os.getenv(
    "REMOTE_DATABASE_URL",
    "postgresql://pmstudio:prod_secure_password_123@185.185.80.147:5435/pmstudio",
)

OLD, NEW = "Cirtificate", "Certificate"

TEXT_UPDATES = [
    ("projects", "name"),
    ("tasks", "title"),
    ("tasks", "description"),
    ("requirements", "original_filename"),
    ("requirements", "extracted_text"),
    ("requirements", "feedback_filename"),
    ("generated_files", "path"),
    ("generated_files", "content"),
    ("architectures", "display_name"),
]

JSON_UPDATES = [
    ("requirements", "analysis_result"),
    ("prds", "content_json"),
    ("srs_documents", "content_json"),
    ("architectures", "doc_system_arch"),
    ("architectures", "doc_database"),
    ("architectures", "doc_api"),
    ("architectures", "doc_frontend"),
    ("architectures", "doc_security"),
    ("architectures", "doc_uiux"),
    ("architectures", "suite_canon"),
    ("architectures", "generation_progress"),
    ("builds", "scaffold"),
    ("builds", "quality_report"),
    ("builds", "generation_progress"),
    ("knowledge_base_items", "content_json"),
]


def main() -> int:
    conn = psycopg2.connect(REMOTE)
    conn.autocommit = False
    cur = conn.cursor()
    total = 0

    for table, column in TEXT_UPDATES:
        cur.execute(
            f"""
            UPDATE {table}
            SET {column} = REPLACE({column}, %s, %s)
            WHERE {column} LIKE %s
            """,
            (OLD, NEW, f"%{OLD}%"),
        )
        if cur.rowcount:
            print(f"  {table}.{column}: {cur.rowcount}")
            total += cur.rowcount

    for table, column in JSON_UPDATES:
        cur.execute(
            f"""
            UPDATE {table}
            SET {column} = REPLACE({column}::text, %s, %s)::jsonb
            WHERE {column}::text LIKE %s
            """,
            (OLD, NEW, f"%{OLD}%"),
        )
        if cur.rowcount:
            print(f"  {table}.{column}: {cur.rowcount}")
            total += cur.rowcount

    conn.commit()
    conn.close()
    print(f"Done — {total} column update(s) on Contabo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
