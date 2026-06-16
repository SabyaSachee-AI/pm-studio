#!/usr/bin/env python3
"""Collect AI workflow logs from Celery/backend terminal captures for optimization review."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Patterns we care about for free-tier / fallback-chain analysis
PATTERNS = {
    "task_received": re.compile(r"Task (\S+)\[([0-9a-f-]+)\] received"),
    "task_succeeded": re.compile(
        r"Task (\S+)\[([0-9a-f-]+)\] succeeded in ([0-9.]+)s: (.+)"
    ),
    "task_failed": re.compile(r"Task (\S+)\[([0-9a-f-]+)\] FAILED"),
    "http_request": re.compile(
        r'HTTP Request: POST (https?://[^\s]+) "HTTP/1\.1 (\d+[^"]*)"'
    ),
    "rate_limit": re.compile(r"Rate limited on (\S+)", re.I),
    "timeout": re.compile(r"Timeout after ([0-9.]+)s: (\S+)", re.I),
    "max_tokens": re.compile(r"max_tokens length limit", re.I),
    "ai_usage": re.compile(r"AI usage"),
    "chunked": re.compile(r"chunked_\w+: (\d+) batch", re.I),
    "api_post": re.compile(
        r'"POST (/api/v1/[^"]+)" (\d+)'
    ),
    "warning": re.compile(r"WARNING.*"),
    "error": re.compile(r"ERROR.*"),
}


def scan_file(path: Path) -> list[dict]:
    events: list[dict] = []
    if not path.exists():
        return events
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        ts_match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        ts = ts_match.group(1) if ts_match else None
        for kind, pat in PATTERNS.items():
            m = pat.search(line)
            if m:
                events.append(
                    {
                        "source": path.name,
                        "line": i + 1,
                        "timestamp": ts,
                        "kind": kind,
                        "match": m.groups() if m.groups() else m.group(0),
                        "text": line.strip()[:500],
                    }
                )
                break
    return events


def summarize(events: list[dict]) -> dict:
    tasks: dict[str, dict] = {}
    providers: dict[str, int] = {}
    http_codes: dict[str, int] = {}
    issues: list[str] = []

    for e in events:
        kind = e["kind"]
        if kind == "task_received":
            name, tid = e["match"]
            tasks[tid] = {"name": name, "status": "running", "events": []}
        elif kind == "task_succeeded":
            name, tid, secs, result = e["match"]
            tasks[tid] = {
                "name": name,
                "status": "succeeded",
                "duration_s": float(secs),
                "result": result[:300],
            }
        elif kind == "task_failed":
            name, tid = e["match"]
            tasks[tid] = {"name": name, "status": "failed"}
        elif kind == "http_request":
            url, code = e["match"]
            host = url.split("/")[2] if "://" in url else url
            providers[host] = providers.get(host, 0) + 1
            http_codes[code.split()[0]] = http_codes.get(code.split()[0], 0) + 1
        elif kind == "rate_limit":
            issues.append(f"rate_limit:{e['match'][0]}")
        elif kind == "timeout":
            issues.append(f"timeout:{e['match'][1]} ({e['match'][0]}s)")
        elif kind == "max_tokens":
            issues.append("max_tokens_truncation")

    return {
        "task_count": len(tasks),
        "tasks": tasks,
        "provider_calls": providers,
        "http_status_counts": http_codes,
        "issue_flags": list(dict.fromkeys(issues)),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    # Cursor terminal folder (adjust if running outside Cursor)
    term_dirs = [
        Path(r"C:\Users\ssd\.cursor\projects\f-knowledgebase-ProjectPreparation-PMS-pm-studio\terminals"),
    ]
    sources: list[Path] = []
    for d in term_dirs:
        if d.is_dir():
            sources.extend(sorted(d.glob("*.txt")))

    all_events: list[dict] = []
    for p in sources:
        all_events.extend(scan_file(p))

    report = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "sources": [str(p) for p in sources],
        "event_count": len(all_events),
        "summary": summarize(all_events),
        "events": all_events[-500:],  # last 500 relevant lines
    }

    out_dir = root / "logs"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"workflow_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_file}")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
