"""Parse GitHub Actions CI logs into structured failures.

Returns the set of source files CI complained about (with their error lines) plus
infrastructure gaps (e.g. a missing Dockerfile). This lets the repair step fix the
*right* files completely, instead of guessing from a path-less distilled log.
"""

from __future__ import annotations

import re

# ESLint / Next.js prints a bare file header line, then indented "line:col Error: …":
#   ./app/(public)/page.tsx
#   75:6  Error: Parsing error: ...
_ESLINT_FILE = re.compile(r"^\.?/([\w./\[\]@()\- ]+\.(?:tsx?|jsx?|mjs|cjs))\s*$")
_ESLINT_ERR = re.compile(r"^\s*(\d+):(\d+)\s+(Error|Warning):\s+(.*)$")

# Python tracebacks / compileall: File "./path/x.py", line N
_PY_FILE = re.compile(r'File "\.?/?([^"]+\.py)", line (\d+)')

# Any repo-relative source path mentioned on an error line.
_PATH_ANY = re.compile(
    r"\.?/?((?:app|backend|frontend|src|api|lib|components|tests|services|cron|hooks|utils|types|db|pages|server)"
    r"/[\w./\[\]@()\-]+\.\w+)"
)

_ERR_HINT = ("error", "syntaxerror", "failed", "cannot find", "not found",
             "missing", "unexpected", "parsing error", "unmatched", "invalid")


def _norm(path: str) -> str:
    return path.strip().lstrip("./").lstrip("/")


def parse_ci_failures(text: str) -> dict:
    """Return {"files": {path: [error,...]}, "infra": [str,...]}."""
    files: dict[str, list[str]] = {}
    current_ts: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        # ESLint file header (sets context for the indented errors that follow)
        m = _ESLINT_FILE.match(line.strip())
        if m and "/" in m.group(1):
            current_ts = _norm(m.group(1))
            files.setdefault(current_ts, [])
            continue
        m = _ESLINT_ERR.match(line)
        if m and current_ts:
            if m.group(3) == "Error":
                files[current_ts].append(f"{m.group(1)}:{m.group(2)} {m.group(4)}")
            continue
        if not line.strip():
            current_ts = None  # blank line ends an ESLint file block

        # Python file + line
        for pm in _PY_FILE.finditer(line):
            files.setdefault(_norm(pm.group(1)), []).append(f"line {pm.group(2)}")

        # Generic path on an error-ish line
        low = line.lower()
        if any(k in low for k in _ERR_HINT):
            for pm in _PATH_ANY.finditer(line):
                files.setdefault(_norm(pm.group(1)), [])

    infra: list[str] = []
    low = text.lower()
    if "dockerfile" in low and any(k in low for k in ("not found", "no such file", "cannot find", "unable to prepare context")):
        infra.append("dockerfile_missing")

    # Drop obvious noise (node_modules, site-packages, the runner toolcache)
    files = {
        p: errs for p, errs in files.items()
        if not any(seg in p for seg in ("node_modules", "site-packages", "hostedtoolcache", ".git/"))
    }
    return {"files": files, "infra": infra}
