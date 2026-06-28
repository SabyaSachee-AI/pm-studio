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
_COMPILE_PY = re.compile(r"\*\*\* Error compiling '([^']+\.py)'")
_SYNTAXERR_LINE = re.compile(r"^\s*SyntaxError:", re.I)

# pytest / tsc / docker
_PYTEST = re.compile(
    r"(?:FAILED|ERROR)\s+((?:tests/)?[\w./]+\.py(?:::[\w.\[\]()+]+)?)",
    re.I,
)
_TSC = re.compile(r"([\w./]+\.tsx?)\(\d+,\d+\):\s+error TS\d+", re.I)
_DOCKER_TARGET = re.compile(r"target\s+(\w+):\s+failed", re.I)
# Invalid/unknown docker images referenced by docker-compose.
_IMAGE_ERR = re.compile(
    r"(?:manifest for|pull access denied for|repository|image)\s+([\w][\w./-]*(?::[\w.\-]+)?)\s+(?:not found|does not exist)",
    re.I,
)

# Any repo-relative source path mentioned on an error line.
_PATH_ANY = re.compile(
    r"\.?/?((?:app|backend|frontend|src|api|lib|components|tests|services|cron|hooks|"
    r"utils|types|db|pages|server|modules|cron|middleware|config|schemas|models|workers|"
    r"routes|controllers|handlers|scripts|cron|public|styles|store|context|providers|"
    r"features|ui|hooks|cron|prisma|drizzle)/[\w./\[\]@()\-]+\.\w+)"
)
# Standalone ./file.tsx at start of line (Next.js build output)
_STANDALONE_FILE = re.compile(
    r"^\.?/([\w./\[\]@()\- ]+\.(?:tsx?|jsx?|py|ts|js))\s*$"
)

_ERR_HINT = (
    "error", "syntaxerror", "failed", "cannot find", "not found",
    "missing", "unexpected", "parsing error", "unmatched", "invalid",
    "module not found", "typeerror", "referenceerror",
)


def _norm(path: str) -> str:
    return path.strip().lstrip("./").lstrip("/")


def _last_eslint_file(recent: list[str]) -> str | None:
    for prev in reversed(recent):
        m = _ESLINT_FILE.match(prev.strip())
        if m and "/" in m.group(1):
            return _norm(m.group(1))
        m2 = _STANDALONE_FILE.match(prev.strip())
        if m2:
            return _norm(m2.group(1))
    return None


def parse_ci_failures(text: str) -> dict:
    """Return {"files": {path: [error,...]}, "infra": [str|dict,...]}."""
    files: dict[str, list[str]] = {}
    current_ts: str | None = None
    recent: list[str] = []
    last_py_file: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        recent.append(line)
        if len(recent) > 50:
            recent.pop(0)

        # ESLint file header (sets context for the indented errors that follow)
        m = _ESLINT_FILE.match(line.strip())
        if m and "/" in m.group(1):
            current_ts = _norm(m.group(1))
            files.setdefault(current_ts, [])
            continue
        m = _STANDALONE_FILE.match(line.strip())
        if m and m.group(1).endswith((".tsx", ".ts", ".jsx", ".js")):
            current_ts = _norm(m.group(1))
            files.setdefault(current_ts, [])
            continue

        m = _ESLINT_ERR.match(line)
        if m:
            ts = current_ts or _last_eslint_file(recent[:-1])
            if ts:
                if m.group(3) == "Error":
                    files.setdefault(ts, []).append(
                        f"{m.group(1)}:{m.group(2)} {m.group(4)}"
                    )
            continue

        # Don't reset ESLint context on blank lines — GitHub logs interleave jobs.
        if not line.strip():
            continue

        # Python file + line
        for pm in _PY_FILE.finditer(line):
            p = _norm(pm.group(1))
            last_py_file = p
            files.setdefault(p, []).append(f"line {pm.group(2)}")

        for cm in _COMPILE_PY.finditer(line):
            p = _norm(cm.group(1))
            last_py_file = p
            files.setdefault(p, [])

        if _SYNTAXERR_LINE.match(line) and last_py_file:
            files.setdefault(last_py_file, []).append("SyntaxError")

        for pm in _PYTEST.finditer(line):
            p = _norm(pm.group(1).split("::")[0])
            files.setdefault(p, []).append(pm.group(1))

        for tm in _TSC.finditer(line):
            files.setdefault(_norm(tm.group(1)), []).append("TypeScript error")

        # Generic path on an error-ish line
        low = line.lower()
        if any(k in low for k in _ERR_HINT):
            for pm in _PATH_ANY.finditer(line):
                files.setdefault(_norm(pm.group(1)), [])

    infra: list[str | dict] = []
    for dm in _DOCKER_TARGET.finditer(text):
        infra.append({"type": "dockerfile_missing", "service": dm.group(1)})

    low = text.lower()
    if "dockerfile" in low and any(
        k in low for k in ("not found", "no such file", "cannot find", "unable to prepare context")
    ):
        if not infra:
            infra.append("dockerfile_missing")

    # Invalid/unknown docker image (e.g. "manifest for foo/bar:1.3 not found",
    # "pull access denied for x", "repository x not found"). These name no source
    # file, so target the compose file directly to fix the bad image tag.
    bad_images: list[str] = []
    for im in _IMAGE_ERR.finditer(text):
        ref = im.group(1)
        if ref and ref not in bad_images:
            bad_images.append(ref)
    if bad_images:
        note = "fix invalid/unknown docker image(s): " + ", ".join(bad_images[:5])
        for cf in ("docker-compose.yml", "docker-compose.yaml"):
            files.setdefault(cf, []).append(note)

    # Drop obvious noise (node_modules, site-packages, the runner toolcache)
    files = {
        p: errs for p, errs in files.items()
        if not any(seg in p for seg in ("node_modules", "site-packages", "hostedtoolcache", ".git/"))
    }
    return {"files": files, "infra": infra}
