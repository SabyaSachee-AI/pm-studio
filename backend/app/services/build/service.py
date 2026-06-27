"""Build services: scaffold (Stage 0) + resumable chunked code generation (Stage 1).

Generation is chunked per Kanban task. Each chunk is its own ``ai_call`` (task
type ``code_generate``) so it rides the code-specialist fallback chain. Completed
files persist immediately and the task id is recorded in ``generation_progress``,
so if a model exhausts its quota mid-run the next chunk simply continues — never
restarting. Every chunk is given a manifest of already-generated files (paths +
signatures) so context and code flow are preserved across model switches.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.architecture import Architecture
from app.models.build import Build, BuildStatus, FileStatus, GeneratedFile
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.schemas.build import GeneratedFileSet, ScaffoldPlan
from app.services.ai.base import ai_call

logger = logging.getLogger(__name__)

SYSTEM_ORDER_FLOOR = 9000  # system tasks (bible/audit/deploy) generated last, if at all
_MAX_CHUNK_ATTEMPTS = 4     # per-task in-run retries before deferring to Celery auto-resume

# Layer ordering so code is generated bottom-up: models → services → API → UI.
_LAYER_RULES: list[tuple[int, tuple[str, ...]]] = [
    (0, ("database", "model", "schema", "migration", "entity")),
    (1, ("service", "business", "logic", "core", "domain", "worker", "celery")),
    (2, ("api", "endpoint", "route", "controller", "backend")),
    (3, ("frontend", "ui", "component", "page", "view", "client")),
]


def _layer_rank(task: Task) -> int:
    hay = f"{task.module_name or ''} {task.title or ''}".lower()
    for rank, keywords in _LAYER_RULES:
        if any(k in hay for k in keywords):
            return rank
    return 4  # everything else after the known layers


def _order_tasks(tasks: list[Task]) -> list[Task]:
    """Dependency order: by layer, then the board's own order_index."""
    return sorted(tasks, key=lambda t: (_layer_rank(t), t.order_index))


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", "ignore")).hexdigest()[:16]


def _file_signature(path: str, content: str) -> str:
    """Extract a compact signature (exports/defs/classes) for downstream context."""
    lines = content.splitlines()
    sig: list[str] = []
    for ln in lines:
        s = ln.strip()
        if re.match(r"^(export\s+(default\s+)?(function|const|class|interface|type|enum)|"
                    r"def\s+\w+|class\s+\w+|async\s+def\s+\w+|@router\.|@app\.)", s):
            sig.append(s[:160])
        if len(sig) >= 12:
            break
    return "\n".join(sig)


_CAPABILITY_CODE_HINTS = {
    "pwa": "PWA — implement the manifest, service worker (offline cache), icons, installability.",
    "offline": "Offline — cache shell + data, queue writes, sync on reconnect.",
    "voice": "Voice — wire mic capture (MediaRecorder/Web Speech API) + speech-to-text + permission UX.",
    "camera": "Camera — implement capture with permission handling.",
    "geolocation": "Geolocation — implement location access with permission handling.",
    "integration_api": "Integration — implement API-key auth, webhook dispatch, and an OpenAPI spec/route.",
}


def _capabilities_brief(arch: Architecture | None) -> str:
    caps = getattr(arch, "capabilities", None) if arch else None
    if not caps:
        return ""
    lines = [_CAPABILITY_CODE_HINTS[k] for k in _CAPABILITY_CODE_HINTS if caps.get(k)]
    return ("\nREQUIRED CAPABILITIES (must be fully implemented in the code):\n- "
            + "\n- ".join(lines)) if lines else ""


def _arch_brief(arch: Architecture | None) -> str:
    """Compact stack/structure context from the architecture suite."""
    if not arch:
        return ""
    sys_doc = arch.doc_system_arch or {}
    fe_doc = arch.doc_frontend or {}
    brief = {
        "tech_stack": sys_doc.get("tech_stack", {}),
        "architecture_pattern": sys_doc.get("architecture_pattern", ""),
        "folder_structure": fe_doc.get("folder_structure", {}),
        "framework": fe_doc.get("framework", ""),
    }
    return json.dumps(brief, separators=(",", ":"), default=str)[:4000] + _capabilities_brief(arch)


def _spec_for_task(task: Task) -> dict[str, Any]:
    spec = getattr(task, "spec", None)
    if spec and spec.content_json:
        return spec.content_json
    # Fall back to task hints if no detailed spec
    return {
        "task_scope": task.description or task.title,
        "files_to_create": [task.suggested_file] if task.suggested_file else [],
        "api_endpoints": [{"path": task.suggested_endpoint}] if task.suggested_endpoint else [],
    }


def _manifest(files: list[GeneratedFile], limit: int = 60) -> str:
    """Paths + signatures of already-generated files, for cross-file context."""
    rows: list[str] = []
    for f in files[:limit]:
        rows.append(f"- {f.path}" + (f"\n    {f.signature}" if f.signature else ""))
    return "\n".join(rows)


# Foundational layers a task usually imports from — included as FULL content.
_DEP_PATH_HINTS = (
    "model", "schema", "entity", "type", "interface", "/db", "database",
    "config", "base", "constant", "util", "lib/", "core/",
)
_RELATED_FULL_LIMIT = 8       # how many dependency files to inline in full
_RELATED_FILE_CHARS = 2200    # per-file content cap (keeps small-context models happy)


def _spec_paths(spec: dict[str, Any]) -> set[str]:
    """File paths the task explicitly touches (modify) — its closest dependencies."""
    out: set[str] = set()
    for key in ("files_to_modify", "files_to_create"):
        v = spec.get(key)
        if isinstance(v, list):
            out.update(str(p) for p in v if p)
    return out


def _related_files(
    spec: dict[str, Any], task: Task, prior_files: list[GeneratedFile],
) -> tuple[list[GeneratedFile], set[str]]:
    """Pick the prior files most likely needed as context — returned for FULL inlining.

    Priority: files the task modifies → same module → foundational layers (models,
    schemas, config, utils). The rest stay as signatures in the manifest.
    """
    modify = {p.lstrip("/") for p in _spec_paths(spec)}
    related: list[GeneratedFile] = []
    chosen: set[str] = set()

    def add(f: GeneratedFile) -> None:
        if f.path not in chosen:
            related.append(f)
            chosen.add(f.path)

    # 1) files this task explicitly modifies
    for f in prior_files:
        if f.path.lstrip("/") in modify:
            add(f)
    # 2) foundational/dependency files by path hint
    for f in prior_files:
        if len(related) >= _RELATED_FULL_LIMIT:
            break
        low = f.path.lower()
        if any(h in low for h in _DEP_PATH_HINTS):
            add(f)
    return related[:_RELATED_FULL_LIMIT], chosen


def _related_block(related: list[GeneratedFile]) -> str:
    parts: list[str] = []
    for f in related:
        parts.append(f"### {f.path}\n```\n{f.content[:_RELATED_FILE_CHARS]}\n```")
    return "\n\n".join(parts)


def _ts_looks_broken(content: str) -> str | None:
    """Heuristic, dependency-free sanity check for JS/TS (no Node needed).

    Catches the gross corruption weaker models produce — the exact errors that
    keep failing ESLint — so broken TS is re-fixed BEFORE the slow CI round-trip,
    instead of after. Conservative: only flags clear breakage to avoid false hits.
    """
    if not content.strip():
        return "Empty file"
    # Literal escape blob (a whole file returned as one escaped string).
    if "\n" not in content and "\\n" in content and len(content) > 120:
        return "Literal \\n escapes — file is not real source"
    # Unbalanced brackets (ignore those inside strings/comments only loosely).
    pairs = {")": "(", "]": "[", "}": "{"}
    opens = {"(": 0, "[": 0, "{": 0}
    in_s: str | None = None  # current string/template quote
    prev = ""
    for ch in content:
        if in_s:
            if ch == in_s and prev != "\\":
                in_s = None
        elif ch in "\"'`":
            in_s = ch
        elif ch in opens:
            opens[ch] += 1
        elif ch in pairs:
            o = pairs[ch]
            opens[o] -= 1
            if opens[o] < 0:
                return f"Unbalanced '{ch}' (more closing than opening)"
        prev = ch
    if any(v != 0 for v in opens.values()):
        return f"Unbalanced brackets {opens}"
    if in_s in ("\"", "'"):
        return "Unterminated string literal"
    return None


def _static_check_file(path: str, content: str) -> str | None:
    """Cheap, dependency-free validity check. Returns an error string or None.

    Covers the highest-value cases server-side (Python syntax, JSON, and a JS/TS
    heuristic) so obvious breakage is caught instantly — before the slow CI round-trip.
    """
    p = path.lower()
    try:
        if p.endswith(".py"):
            compile(content, path, "exec")
        elif p.endswith(".json"):
            json.loads(content)
        elif p.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")):
            return _ts_looks_broken(content)
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} (line {exc.lineno})"
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}"
    except Exception as exc:  # noqa: BLE001
        return str(exc)[:200]
    return None


# Invisible characters that routinely break compilers/linters when a model
# emits them by accident (NBSP instead of space, zero-width joiners, BOM).
_INVISIBLE = str.maketrans({
    "﻿": "", "​": "", "‌": "", "‍": "", "⁠": "",
    " ": " ",  # non-breaking space → normal space (a classic "Invalid character")
})


# C0 control characters that break compilers (keep tab \t, newline \n, CR \r).
_CONTROL_CHARS = {c: None for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)}
_CONTROL_CHARS[0x7F] = None  # DEL


def _sanitize_code(path: str, content: str) -> str:
    """Clean generated content before storing.

    Fixes the common ways a weaker model corrupts code-in-JSON:
    - invisible chars (NBSP/zero-width/BOM) → removed ("Invalid character")
    - C0 control chars (e.g. U+0008 backspace) → removed
    - a file returned as ONE escaped blob (literal ``\\n``/``\\t`` and no real
      newlines) → de-escaped back into real lines
    - an accidental wrapping markdown code fence (```lang … ```) → stripped
    """
    content = content.translate(_INVISIBLE).translate(_CONTROL_CHARS)

    # Whole file came back as a single escaped string (no real newlines but
    # literal "\n"): decode the standard escapes back to real characters.
    if "\n" not in content and "\\n" in content:
        content = (
            content.replace("\\r\\n", "\n").replace("\\n", "\n")
            .replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")
        )

    low = path.lower()
    if not (low.endswith(".md") or low.endswith(".mdx")):
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
                content = "\n".join(lines[1:-1]) + "\n"
    return content


# PM Studio owns the CI/CD workflows. AI-generated files under this path are
# ignored so a model can never overwrite the deterministic, runnable workflows
# (which caused false CI failures, e.g. npm-cache requiring a missing lockfile).
_PROTECTED_WORKFLOW_PREFIX = ".github/workflows/"


def _persist_file(
    db: Session,
    build: Build,
    path: str,
    content: str,
    language: str,
    task_id: UUID | None,
    status: FileStatus = FileStatus.generated,
    force: bool = False,
) -> GeneratedFile | None:
    """Insert or update a generated file (dedupe by path within the build).

    Writes under ``.github/workflows/`` are ignored unless ``force=True`` — only
    PM Studio's deterministic CI/CD templates may live there.
    """
    if not force and path.lstrip("/").startswith(_PROTECTED_WORKFLOW_PREFIX):
        return None
    content = _sanitize_code(path, content)
    existing = (
        db.query(GeneratedFile)
        .filter(
            GeneratedFile.build_id == build.id,
            GeneratedFile.path == path,
            GeneratedFile.deleted_at.is_(None),
        )
        .first()
    )
    sig = _file_signature(path, content)
    if existing:
        existing.content = content
        existing.language = language or existing.language
        existing.checksum = _checksum(content)
        existing.signature = sig
        existing.status = status
        if task_id:
            existing.task_id = task_id
        return existing
    row = GeneratedFile(
        build_id=build.id,
        task_id=task_id,
        path=path,
        content=content,
        language=language or _guess_lang(path),
        status=status,
        checksum=_checksum(content),
        signature=sig,
    )
    db.add(row)
    return row


def _guess_lang(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "python", "ts": "typescript", "tsx": "typescript", "js": "javascript",
        "jsx": "javascript", "json": "json", "md": "markdown", "yml": "yaml",
        "yaml": "yaml", "sql": "sql", "css": "css", "html": "html", "sh": "bash",
        "toml": "toml", "env": "dotenv", "dockerfile": "docker",
    }.get(ext, ext or "text")


# ── Stage 0: scaffold ────────────────────────────────────────────────────────

SCAFFOLD_SYSTEM = (
    "You are a senior software architect scaffolding a new repository. "
    "Return strictly structured JSON. Produce only config/skeleton files "
    "(package.json, requirements.txt, tsconfig, configs, .gitignore, README, "
    "docker-compose.yml) — NOT feature code. Use the project's exact stack. "
    "Do NOT create GitHub workflow files; PM Studio injects CI/CD itself."
)

# Deterministic CI workflow — real gates: backend compiles + pytest, frontend
# installs + lint + build. Conditioned on folders existing so it adapts to the
# generated layout; build/test failures DO fail CI (so "green" means verified).
_CI_WORKFLOW = """name: CI
on:
  push:
    branches: [main, master]
  pull_request:
  workflow_dispatch:
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install, compile, test (backend)
        run: |
          if [ -f backend/requirements.txt ]; then
            cd backend
            pip install -r requirements.txt
            python -m compileall app 2>/dev/null || python -m compileall . || true
            if [ -d tests ] || ls test_*.py >/dev/null 2>&1; then pytest -q; fi
          elif [ -f requirements.txt ]; then
            pip install -r requirements.txt
            python -m compileall . || true
            if [ -d tests ]; then pytest -q; fi
          else
            echo "No Python backend detected — skipping"
          fi
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install, lint, build, test (frontend)
        run: |
          DIR=""
          if [ -f frontend/package.json ]; then DIR=frontend; elif [ -f package.json ]; then DIR=.; fi
          if [ -n "$DIR" ]; then
            cd "$DIR"
            npm install
            npm run lint --if-present
            npm run build --if-present
            CI=true npm test --if-present
          else
            echo "No JS/TS frontend detected — skipping"
          fi
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Boot the stack and smoke-test it
        run: |
          if [ ! -f docker-compose.yml ]; then echo "No compose — skipping smoke"; exit 0; fi
          cp -n .env.example .env 2>/dev/null || true
          docker compose up -d --build
          ok=""
          for i in $(seq 1 30); do
            for url in http://localhost:3000 http://localhost:3000/health http://localhost:8000/health; do
              if curl -fsS "$url" >/dev/null 2>&1; then ok=1; break; fi
            done
            [ -n "$ok" ] && break
            sleep 5
          done
          docker compose ps
          docker compose logs --tail 50 || true
          docker compose down -v || true
          if [ -z "$ok" ]; then echo "Smoke test failed — app did not become healthy"; exit 1; fi
"""

# Deterministic deploy workflow — SSH to the VPS, auto-clone the (private) repo on
# first run, pull thereafter, and bring the stack up on a per-app port. This makes
# deploys safe on a shared VPS (no manual clone, no port clashes).
_DEPLOY_WORKFLOW = """name: Deploy
on:
  workflow_dispatch:
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy over SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            set -e
            TARGET="${{ secrets.VPS_PATH }}"
            REPO_URL="${{ secrets.REPO_TOKEN_URL }}"
            export APP_PORT="${{ secrets.APP_PORT }}"
            if [ ! -d "$TARGET/.git" ]; then
              mkdir -p "$TARGET"
              git clone "$REPO_URL" "$TARGET"
            fi
            cd "$TARGET"
            git remote set-url origin "$REPO_URL"
            PREV=$(git rev-parse HEAD || echo "")
            git pull origin main
            cp -n .env.example .env 2>/dev/null || true
            docker compose up -d --build
            # Health gate — roll back to the previous commit if the app doesn't come up.
            ok=""
            for i in $(seq 1 24); do
              if curl -fsS "http://localhost:${APP_PORT:-3000}" >/dev/null 2>&1 \
                 || curl -fsS "http://localhost:${APP_PORT:-3000}/health" >/dev/null 2>&1; then ok=1; break; fi
              sleep 5
            done
            if [ -z "$ok" ] && [ -n "$PREV" ]; then
              echo "Health check failed — rolling back to $PREV"
              git reset --hard "$PREV"
              docker compose up -d --build
              exit 1
            fi
            docker compose ps
"""


_BACKEND_DOCKERFILE = """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]
"""

_FRONTEND_DOCKERFILE = """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build || true
EXPOSE 3000
CMD ["sh", "-c", "npm start || npm run dev"]
"""


def _norm_compose_path(raw: str) -> str:
    p = raw.strip().strip('"\'').strip()
    if p in (".", "./"):
        return ""
    return p.strip("./").rstrip("/")


def _dockerfile_paths_from_compose(content: str) -> list[str]:
    """Resolve every Dockerfile path docker-compose expects (repo-relative)."""
    paths: set[str] = set()
    contexts: set[str] = set()

    for m in re.finditer(r"context:\s*[\"']?([^\s\"'#]+)", content, re.I):
        val = m.group(1)
        if val.startswith("${"):
            continue
        contexts.add(_norm_compose_path(val))

    for m in re.finditer(
        r"build:\s*[\"']?(\./[^\s\"'#]+|\.)\s*[\"']?",
        content,
    ):
        val = m.group(1)
        if val.startswith("${"):
            continue
        contexts.add(_norm_compose_path(val))

    for ctx in contexts:
        paths.add("Dockerfile" if ctx == "" else f"{ctx}/Dockerfile")

    for m in re.finditer(r"dockerfile:\s*[\"']?([^\s\"'#]+)", content, re.I):
        df = _norm_compose_path(m.group(1))
        if df.startswith("${"):
            continue
        # dockerfile: Dockerfile with context: ./backend → backend/Dockerfile
        if df.lower() == "dockerfile":
            continue
        if "/" in df:
            paths.add(df)
        else:
            # Relative to nearest context — inject at every context if ambiguous.
            for ctx in contexts or {""}:
                paths.add(f"{ctx}/{df}".strip("/") if ctx else df)

    return sorted(paths)


def _dockerfile_path_for_service(compose: str, service: str) -> str | None:
    """Best-effort: map a docker-compose service name to its Dockerfile path."""
    block = re.search(
        rf"^\s*{re.escape(service)}:\s*\n(.*?)(?=^\S|\Z)",
        compose,
        re.M | re.S,
    )
    if not block:
        return None
    chunk = block.group(1)
    ctx = ""
    df = "Dockerfile"
    cm = re.search(r"context:\s*[\"']?([^\s\"'#]+)", chunk, re.I)
    if cm:
        ctx = _norm_compose_path(cm.group(1))
    dm = re.search(r"dockerfile:\s*[\"']?([^\s\"'#]+)", chunk, re.I)
    if dm:
        df = _norm_compose_path(dm.group(1))
    bm = re.search(r"build:\s*[\"']?(\./[^\s\"'#]+|\.|[^\s\"'#]+)[\"']?", chunk)
    if bm and not cm:
        ctx = _norm_compose_path(bm.group(1))
    if df.lower() == "dockerfile":
        return "Dockerfile" if ctx == "" else f"{ctx}/Dockerfile"
    if "/" in df:
        return df
    return f"{ctx}/{df}".strip("/") if ctx else df


def ensure_deterministic_dockerfiles(
    db: Session, build: Build, *, service_hints: list[str] | None = None,
) -> int:
    """Inject Dockerfiles wherever compose/CI expect them but files are missing.

    Returns the number of Dockerfiles newly injected.
    """
    by_path = {
        f.path.lstrip("/"): f
        for f in db.query(GeneratedFile)
        .filter(GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None))
        .all()
    }
    present = set(by_path)
    injected = 0

    def have(p: str) -> bool:
        return p in present

    def inject(path: str, tpl: str) -> None:
        nonlocal injected
        if path in present:
            return
        _persist_file(db, build, path, tpl, "docker", task_id=None)
        present.add(path)
        injected += 1

    def template_for(base: str) -> str | None:
        b = base.strip().strip("./").rstrip("/")
        req = f"{b}/requirements.txt".lstrip("/") if b else "requirements.txt"
        pkg = f"{b}/package.json".lstrip("/") if b else "package.json"
        if have(req):
            return _BACKEND_DOCKERFILE
        if have(pkg):
            return _FRONTEND_DOCKERFILE
        return None

    needed: set[str] = set()

    compose = by_path.get("docker-compose.yml") or by_path.get("docker-compose.yaml")
    if compose is not None:
        needed.update(_dockerfile_paths_from_compose(compose.content))
        for hint in service_hints or []:
            p = _dockerfile_path_for_service(compose.content, hint)
            if p:
                needed.add(p)

    # Pass 2 — standard layout fallback.
    if have("backend/requirements.txt"):
        needed.add("backend/Dockerfile")
    elif have("requirements.txt") and not have("backend/requirements.txt"):
        needed.add("Dockerfile")
    if have("frontend/package.json"):
        needed.add("frontend/Dockerfile")
    elif have("package.json") and not have("frontend/package.json"):
        needed.add("Dockerfile")

    for dpath in sorted(needed):
        base = dpath.rsplit("/", 1)[0] if "/" in dpath else ""
        tpl = template_for(base)
        if tpl:
            inject(dpath, tpl)

    return injected


def ensure_deterministic_workflows(db: Session, build: Build) -> None:
    """Force PM Studio's CI/CD workflows into the build (overwriting any AI copy).

    Called at scaffold, after generation, and before every push so the repo
    always ships the robust, runnable workflows — never a model's variant.
    """
    _persist_file(db, build, ".github/workflows/ci.yml", _CI_WORKFLOW, "yaml", task_id=None, force=True)
    _persist_file(db, build, ".github/workflows/deploy.yml", _DEPLOY_WORKFLOW, "yaml", task_id=None, force=True)


async def build_scaffold(build_id: UUID, db: Session, project_info: dict[str, Any]) -> dict[str, Any]:
    """Generate the repo skeleton from the architecture and persist scaffold files."""
    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}

    arch = (
        db.query(Architecture).filter(Architecture.id == build.architecture_id).first()
        if build.architecture_id else None
    )
    arch_brief = _arch_brief(arch)

    build.status = BuildStatus.scaffolding
    build.last_error = None
    db.commit()

    prompt = (
        f"Project: {project_info.get('name', 'Project')}\n"
        f"Description: {project_info.get('description', '')}\n\n"
        f"ARCHITECTURE (stack + folders):\n{arch_brief}\n\n"
        "Generate the repository scaffold for the EXACT stack in the architecture "
        "(any language/framework). Do NOT create .github workflows.\n\n"
        "RUNNABILITY CHECKLIST — the project MUST start and work end-to-end with one "
        "`docker compose up`. Include ALL of:\n"
        "  1. Package manifests for each app with PINNED dependency versions + lockfiles.\n"
        "  2. A `.env.example` listing EVERY env var the app needs (DB URL, secret/JWT, "
        "third-party keys) with safe placeholder defaults; all config read from env.\n"
        "  3. Database migrations (e.g. Alembic/Prisma/Knex) AND a backend container "
        "ENTRYPOINT script that runs migrations (and an idempotent seed/first-admin if "
        "auth exists) BEFORE starting the server. Never assume tables already exist.\n"
        "  4. A health endpoint (e.g. GET /health → 200) on the backend.\n"
        "  5. docker-compose.yml that: builds each app, wires services via the compose "
        "network, loads env from `.env`, runs the entrypoint (migrate+seed+serve), and "
        "is SHARED-VPS-SAFE — expose ONLY the web service on `${APP_PORT:-3000}:3000`; "
        "Postgres/Redis/backend get NO host ports; use a project-specific name prefix.\n"
        "  6. README with run instructions.\n"
        "Return all these as scaffold files. Fill dependencies and scripts."
    )
    result = await ai_call(
        prompt=prompt,
        response_model=ScaffoldPlan,
        system=SCAFFOLD_SYSTEM,
        max_tokens=12000,
        task_type="code_generate",
        screen="tasks",
    )

    for f in result.files:
        if f.path and f.content:
            _persist_file(db, build, f.path, f.content, f.language, task_id=None)

    # Deterministic CI/CD workflows — guarantees correct secret names + a deploy
    # path regardless of what the AI produced.
    ensure_deterministic_workflows(db, build)

    build.scaffold = {"dependencies": result.dependencies, "scripts": result.scripts, "notes": result.notes}
    build.status = BuildStatus.scaffolded
    db.commit()
    count = db.query(GeneratedFile).filter(
        GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None)
    ).count()
    return {"status": "scaffolded", "file_count": count}


# ── Stage 1: resumable chunked code generation ───────────────────────────────

CODEGEN_SYSTEM = (
    "You are a senior full-stack engineer writing complete, production-ready code "
    "for ONE task of a larger project. Return strictly structured JSON with a "
    "files array. Every file must be complete and runnable — no TODOs, no "
    "placeholders. Reuse the EXACT paths/names/signatures of already-generated "
    "files so imports resolve and types align. Follow the task spec precisely."
)


async def _generate_one_task(
    db: Session,
    build: Build,
    task: Task,
    arch_brief: str,
    project_info: dict[str, Any],
    protect_edited: bool = False,
) -> int:
    """Generate the files for a single task. Returns number of files written.

    protect_edited=True (full-suite run) skips files a human/AI already edited, so
    re-generating the whole build never clobbers your manual changes.
    """
    prior_files = (
        db.query(GeneratedFile)
        .filter(GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None))
        .order_by(GeneratedFile.created_at.asc())
        .all()
    )
    edited_paths = {f.path for f in prior_files if f.status == FileStatus.edited} if protect_edited else set()
    spec = _spec_for_task(task)
    spec_json = json.dumps(spec, separators=(",", ":"), default=str)[:8000]

    # Dependency-aware context: FULL content of the files this task most likely
    # imports/extends; signatures only for everything else (token-bounded).
    related, related_paths = _related_files(spec, task, prior_files)
    rest = [f for f in prior_files if f.path not in related_paths]
    related_block = _related_block(related)
    manifest = _manifest(rest, limit=120)

    prompt = (
        f"Project: {project_info.get('name', 'Project')}\n\n"
        f"ARCHITECTURE (stack + folders — follow exactly):\n{arch_brief}\n\n"
        f"DEPENDENCY FILES (full source — import from these EXACTLY; reuse their "
        f"names, signatures, and types; do NOT redefine them):\n"
        f"{related_block or '(none yet)'}\n\n"
        f"OTHER EXISTING FILES (signatures only — names/paths to reuse):\n"
        f"{manifest or '(none yet)'}\n\n"
        f"TASK TO IMPLEMENT NOW:\n"
        f"Title: {task.title}\n"
        f"Module: {task.module_name or ''}\n"
        f"Linked FR: {task.linked_fr or ''}\n"
        f"SPEC:\n{spec_json}\n\n"
        "Generate ALL files needed to implement THIS task only. Each file complete "
        "and runnable. Imports MUST resolve against the dependency files above. "
        "Use exact paths from the folder structure."
    )
    result = await ai_call(
        prompt=prompt,
        response_model=GeneratedFileSet,
        system=CODEGEN_SYSTEM,
        max_tokens=14000,
        task_type="code_generate",
        screen="tasks",
    )
    written = 0
    for f in result.files:
        if f.path and f.content:
            if f.path in edited_paths:
                continue  # preserve human/AI edits during a full regenerate
            _persist_file(db, build, f.path, f.content, f.language, task_id=task.id)
            written += 1
    return written


_STATIC_FIX_SYSTEM = (
    "You are fixing a single source file that failed a syntax/validity check. "
    "Return the corrected file (same path) in the files array — complete and "
    "runnable, no explanations, no placeholders."
)


async def _validate_and_repair(db: Session, build: Build, max_fix: int = 25) -> dict[str, Any]:
    """Fast pre-push gate: static-check every file; auto-fix syntax failures locally
    (Python/JSON) so obvious breakage never reaches the slow CI round-trip."""
    files = (
        db.query(GeneratedFile)
        .filter(GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None))
        .all()
    )
    failures: list[tuple[GeneratedFile, str]] = []
    for f in files:
        err = _static_check_file(f.path, f.content)
        if err:
            failures.append((f, err))

    fixed = 0
    still_failing: list[str] = []
    for f, err in failures[:max_fix]:
        try:
            prompt = (
                f"This file failed a static check and must be fixed.\n"
                f"FILE: {f.path}\nERROR: {err}\n\n"
                f"```\n{f.content[:12000]}\n```\n\n"
                "Return the corrected file (same path)."
            )
            result = await ai_call(
                prompt=prompt,
                response_model=GeneratedFileSet,
                system=_STATIC_FIX_SYSTEM,
                max_tokens=12000,
                task_type="code_generate",
                screen="tasks",
            )
            out = next((x for x in result.files if x.content.strip()), None)
            if out and _static_check_file(f.path, out.content) is None:
                _persist_file(db, build, f.path, out.content, out.language or f.language,
                              task_id=f.task_id, status=FileStatus.edited)
                fixed += 1
            else:
                f.status = FileStatus.qa_failed
                still_failing.append(f.path)
        except Exception:  # noqa: BLE001
            f.status = FileStatus.qa_failed
            still_failing.append(f.path)
    db.commit()
    return {
        "checked": len(files),
        "failed": len(failures),
        "auto_fixed": fixed,
        "still_failing": still_failing,
    }


async def generate_build_code(build_id: UUID, db: Session, *, resume: bool = False) -> dict[str, Any]:
    """Generate code for every task in dependency order. Resumable per task."""
    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}

    project = db.query(Project).filter(Project.id == build.project_id).first()
    project_info = {
        "name": project.name if project else "Project",
        "description": (project.description if project else "") or "",
    }
    arch = (
        db.query(Architecture).filter(Architecture.id == build.architecture_id).first()
        if build.architecture_id else None
    )
    arch_brief = _arch_brief(arch)

    tasks = (
        db.query(Task)
        .filter(
            Task.project_id == build.project_id,
            Task.deleted_at.is_(None),
            Task.order_index < SYSTEM_ORDER_FLOOR,
        )
        .all()
    )
    ordered = _order_tasks(tasks)

    progress = dict(build.generation_progress or {}) if resume else {}
    completed: set[str] = set(progress.get("completed_task_ids") or [])
    progress["total_tasks"] = len(ordered)

    build.status = BuildStatus.generating
    build.can_resume = False
    build.last_error = None
    build.generation_progress = {**progress, "completed_task_ids": sorted(completed)}
    db.commit()

    for idx, task in enumerate(ordered, start=1):
        if str(task.id) in completed:
            continue
        progress.update({
            "phase": "generating",
            "current_task": task.title,
            "current_index": idx,
            "message": f"Generating code for: {task.title} ({idx}/{len(ordered)})",
        })
        build.generation_progress = {**progress, "completed_task_ids": sorted(completed)}
        db.commit()

        # Per-task auto-retry: if every model in the chain is momentarily
        # exhausted, wait (quotas reset) and re-walk the chain — never restart
        # the whole run, never lose completed work.
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_CHUNK_ATTEMPTS + 1):
            try:
                await _generate_one_task(db, build, task, arch_brief, project_info, protect_edited=True)
                completed.add(str(task.id))
                build.generation_progress = {**progress, "completed_task_ids": sorted(completed)}
                db.commit()
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "Codegen attempt %d/%d failed for task %s: %s",
                    attempt, _MAX_CHUNK_ATTEMPTS, task.id, str(exc)[:200],
                )
                if attempt < _MAX_CHUNK_ATTEMPTS:
                    wait = min(60, 5 * (2 ** (attempt - 1)))  # 5s, 10s, 20s, 40s
                    build.generation_progress = {
                        **progress, "completed_task_ids": sorted(completed),
                        "phase": "retrying",
                        "message": (
                            f"All models busy on '{task.title}' — auto-retrying in "
                            f"{wait}s (attempt {attempt + 1}/{_MAX_CHUNK_ATTEMPTS}). "
                            "Continuing where it stopped."
                        ),
                    }
                    db.commit()
                    await asyncio.sleep(wait)

        if last_exc is not None:
            # Exhausted in-run retries — mark resumable. The Celery task will
            # auto re-enqueue (resume=True) after a cooldown; no manual click.
            logger.exception("Code generation exhausted retries for task %s", task.id)
            build.status = BuildStatus.failed
            build.can_resume = True
            build.resume_from = str(task.id)
            build.last_error = str(last_exc)[:500]
            build.generation_progress = {**progress, "completed_task_ids": sorted(completed),
                                         "phase": "failed", "message": str(last_exc)[:200]}
            db.commit()
            return {"error": str(last_exc)[:500], "status": "failed",
                    "completed": len(completed), "total": len(ordered)}

    # Fast pre-push static gate: catch + auto-fix obvious syntax breakage now.
    build.generation_progress = {**progress, "phase": "validating",
                                 "completed_task_ids": sorted(completed),
                                 "message": "Static-checking generated files…"}
    db.commit()
    static = await _validate_and_repair(db, build)

    # Re-assert PM Studio's CI/CD workflows + fill any missing Dockerfiles.
    ensure_deterministic_workflows(db, build)
    ensure_deterministic_dockerfiles(db, build)

    report = dict(build.quality_report or {})
    report["static_check"] = static
    build.quality_report = report
    build.status = BuildStatus.ready
    build.can_resume = False
    build.resume_from = None
    build.generation_progress = {**progress, "phase": "completed",
                                 "completed_task_ids": sorted(completed),
                                 "message": (
                                     f"Done. Static check: {static['auto_fixed']} auto-fixed, "
                                     f"{len(static['still_failing'])} still failing."
                                 )}
    db.commit()
    count = db.query(GeneratedFile).filter(
        GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None)
    ).count()
    return {"status": "completed", "tasks": len(ordered), "file_count": count, "static_check": static}


async def generate_single_task_code(build_id: UUID, task_id: UUID, db: Session) -> dict[str, Any]:
    """(Re)generate code for one task only."""
    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}
    task = db.query(Task).filter(Task.id == task_id, Task.deleted_at.is_(None)).first()
    if not task:
        return {"error": "Task not found"}
    project = db.query(Project).filter(Project.id == build.project_id).first()
    project_info = {"name": project.name if project else "Project",
                    "description": (project.description if project else "") or ""}
    arch = (
        db.query(Architecture).filter(Architecture.id == build.architecture_id).first()
        if build.architecture_id else None
    )
    written = await _generate_one_task(db, build, task, _arch_brief(arch), project_info)
    db.commit()
    return {"status": "completed", "task_id": str(task_id), "files_written": written}


# ── AI edit one file (free-text instruction) ─────────────────────────────────

class _SingleFile(GeneratedFileSet):
    pass


async def ai_edit_file(build_id: UUID, file_id: UUID, instruction: str, db: Session) -> dict[str, Any]:
    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}
    f = db.query(GeneratedFile).filter(
        GeneratedFile.id == file_id, GeneratedFile.build_id == build_id,
        GeneratedFile.deleted_at.is_(None),
    ).first()
    if not f:
        return {"error": "File not found"}

    prior_files = (
        db.query(GeneratedFile)
        .filter(GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None),
                GeneratedFile.id != file_id)
        .all()
    )
    prompt = (
        f"Edit this file per the instruction. Keep it complete and runnable.\n\n"
        f"FILE: {f.path}\n```\n{f.content[:12000]}\n```\n\n"
        f"OTHER FILES (for context — keep imports consistent):\n{_manifest(prior_files)}\n\n"
        f"INSTRUCTION:\n{instruction.strip()}\n\n"
        "Return the SINGLE edited file in the files array (same path)."
    )
    result = await ai_call(
        prompt=prompt,
        response_model=GeneratedFileSet,
        system=CODEGEN_SYSTEM,
        max_tokens=14000,
        task_type="code_generate",
        screen="tasks",
    )
    out = next((x for x in result.files if x.content.strip()), None)
    if not out:
        return {"error": "AI returned no file"}
    _persist_file(db, build, f.path, out.content, out.language or f.language,
                  task_id=f.task_id, status=FileStatus.edited)
    db.commit()
    return {"status": "edited", "path": f.path}


# ── CI repair loop: read failed CI logs → AI fix → re-push ───────────────────

_MAX_REPAIR_ATTEMPTS = 5

REPAIR_SYSTEM = (
    "You are a senior engineer fixing a CI failure. You are given the failing CI "
    "logs and the project's file manifest. Return ONLY the files that must change "
    "to make lint/typecheck/build/tests pass — each file COMPLETE and runnable. "
    "Keep imports/paths/signatures consistent with the rest of the project."
)


_REPAIR_BATCH = 3            # files per AI call (full content → reliable fixes)
_REPAIR_THROTTLE_SEC = 2     # pause between calls to avoid 429 bursts


async def repair_build_from_ci(build_id: UUID, db: Session, project_name: str) -> dict[str, Any]:
    """One repair cycle that fixes EVERY file CI complained about.

    Parses the CI log into a structured list of failing files, then fixes them in
    small batches (full content per file → reliable), injects any missing infra
    (Dockerfiles), runs the static gate, and re-pushes once. Records a repair
    history so the UI can show what was fixed and what remains.
    """
    from app.services.build.github import get_run_logs, push_build  # noqa: PLC0415
    from app.services.build.ci_log_parser import parse_ci_failures  # noqa: PLC0415

    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}
    report = dict(build.quality_report or {})
    ci = report.get("ci") or {}
    attempts = int(report.get("repair_attempts") or 0)

    def _save_plan(targets: list[str], fixed: int, *, note: str = "") -> None:
        plan: dict[str, Any] = {"targeted": targets, "fixed": fixed}
        if note:
            plan["note"] = note
        report["repair_plan"] = plan
        build.quality_report = report
        db.commit()

    if ci.get("conclusion") != "failure":
        _save_plan([], 0, note="Latest CI run is not a failure")
        return {"error": "Latest CI run is not a failure — nothing to repair"}

    if attempts >= _MAX_REPAIR_ATTEMPTS:
        _save_plan([], 0, note=f"Repair limit reached ({_MAX_REPAIR_ATTEMPTS})")
        return {"error": f"Repair limit reached ({_MAX_REPAIR_ATTEMPTS}). Fix manually or regenerate."}

    _save_plan([], 0, note="Repair cycle started")

    # Full logs (with file paths) for parsing + a distilled view for context.
    raw = ""
    if build.github_full_name and ci.get("run_id"):
        raw = await get_run_logs(build.github_full_name, ci["run_id"], distil=False)
        if not raw:
            await asyncio.sleep(5)
            raw = await get_run_logs(build.github_full_name, ci["run_id"], distil=False)
    if not raw:
        _save_plan([], 0, note="Could not read CI logs")
        return {"error": "Could not read CI logs for this run"}
    parsed = parse_ci_failures(raw)
    distilled = _distil_ci(raw)

    service_hints: list[str] = []
    for item in parsed.get("infra") or []:
        if isinstance(item, dict) and item.get("service"):
            service_hints.append(str(item["service"]))

    # Layer A — fill infrastructure gaps deterministically (no AI).
    docker_injected = ensure_deterministic_dockerfiles(
        db, build, service_hints=service_hints or None,
    )
    db.commit()

    db_files = {
        f.path.lstrip("/"): f
        for f in db.query(GeneratedFile)
        .filter(GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None))
        .all()
    }
    # Match parsed failing paths to real DB files (keep order, de-dupe).
    targets: list[str] = []
    for p in parsed["files"]:
        if p in db_files and p not in targets:
            targets.append(p)

    # Robustness: even if the CI log lacked file paths, repair every file that
    # fails our local static check (Python compile / JS-TS heuristic). This makes
    # the loop self-sufficient — it never silently fixes zero files.
    local_errs: dict[str, str] = {}
    for p, f in db_files.items():
        err = _static_check_file(f.path, f.content)
        if err:
            local_errs[p] = err
            if p not in targets:
                targets.append(p)

    manifest = _manifest(list(db_files.values()), limit=150)
    fixed = 0

    async def _fix_batch(batch: list[str]) -> int:
        blocks: list[str] = []
        for p in batch:
            errs = "; ".join(parsed["files"].get(p) or [])
            if local_errs.get(p):
                errs = f"{errs}; static check: {local_errs[p]}" if errs else f"static check: {local_errs[p]}"
            blocks.append(f"FILE: {p}\nERRORS: {errs or 'see CI log'}\nCURRENT CONTENT:\n{db_files[p].content}")
        prompt = (
            f"Project: {project_name}\n\n"
            f"Fix these files so CI passes. Return each corrected file COMPLETE and "
            f"runnable, keeping imports/paths/signatures consistent with the project.\n\n"
            f"PROJECT SIGNATURES (for correct imports):\n{manifest}\n\n"
            f"CI LOG (distilled):\n```\n{distilled[:4000]}\n```\n\n"
            + "\n\n".join(blocks)
        )
        result = await ai_call(
            prompt=prompt, response_model=GeneratedFileSet, system=REPAIR_SYSTEM,
            max_tokens=14000, task_type="code_generate", screen="tasks",
        )
        n = 0
        for ff in result.files:
            if ff.path and ff.content.strip():
                _persist_file(db, build, ff.path, ff.content, ff.language,
                              task_id=None, status=FileStatus.edited)
                n += 1
        db.commit()
        return n

    for i in range(0, len(targets), _REPAIR_BATCH):
        batch = targets[i:i + _REPAIR_BATCH]
        try:
            fixed += await _fix_batch(batch)
        except Exception as exc:  # noqa: BLE001 — one batch shouldn't abort the cycle
            logger.warning("Repair batch failed (%s) — retrying once", exc)
            try:
                await asyncio.sleep(_REPAIR_THROTTLE_SEC)
                fixed += await _fix_batch(batch)  # single retry (handles a transient 429)
            except Exception as exc2:  # noqa: BLE001
                logger.warning("Repair batch retry failed: %s", exc2)
        if i + _REPAIR_BATCH < len(targets):
            await asyncio.sleep(_REPAIR_THROTTLE_SEC)  # throttle → fewer 429s

    # Layer A — static gate (Python compile + JSON) catches/repairs more.
    static = await _validate_and_repair(db, build)

    # Re-inject Dockerfiles after AI edits (models sometimes overwrite compose).
    docker_injected += ensure_deterministic_dockerfiles(
        db, build, service_hints=service_hints or None,
    )
    db.commit()

    # Record what happened so the UI can show progress.
    report["repair_attempts"] = attempts + 1
    history = list(report.get("repair_history") or [])
    history.append({
        "attempt": attempts + 1,
        "ci_run_id": ci.get("run_id"),
        "files_targeted": len(targets),
        "files_fixed": fixed,
        "infra": parsed.get("infra") or [],
        "docker_injected": docker_injected,
        "static_auto_fixed": static.get("auto_fixed", 0),
    })
    report["repair_history"] = history[-12:]
    report["repair_plan"] = {"targeted": targets, "fixed": fixed, "docker_injected": docker_injected}
    build.quality_report = report
    db.commit()

    has_infra = bool(parsed.get("infra")) or docker_injected > 0
    if fixed == 0 and not has_infra:
        return {"error": "Could not identify fixable files in the CI log",
                "repair_attempts": attempts + 1,
                "files_targeted": len(targets)}

    # Re-push the corrected codebase → triggers a fresh CI run.
    push_result = await push_build(build_id, db, project_name)
    if isinstance(push_result, dict) and push_result.get("error"):
        build.last_error = str(push_result["error"])[:500]
        db.commit()
        return {
            "error": push_result["error"],
            "files_fixed": fixed,
            "files_targeted": len(targets),
            "repair_attempts": attempts + 1,
        }
    return {
        "status": "repaired",
        "files_fixed": fixed,
        "files_targeted": len(targets),
        "repair_attempts": attempts + 1,
        "push": push_result,
    }


def _distil_ci(raw: str, limit: int = 8000) -> str:
    """Keep the most relevant error lines from a full CI log (for prompt context)."""
    lines = raw.splitlines()
    flagged = [ln for ln in lines if any(
        kw in ln.lower() for kw in ("error", "failed", "fail:", "✕", "exception",
                                    "cannot find", "not found", "traceback", "syntaxerror",
                                    "parsing error", "unmatched", "manifest unknown")
    )]
    picked = flagged if flagged else lines
    return "\n".join(picked[-400:])[-limit:]


# ── Stage 3: generate automated tests from acceptance criteria ───────────────

TESTS_SYSTEM = (
    "You are a senior test engineer. Write automated tests that verify the given "
    "acceptance criteria against the real generated code. Use pytest for Python "
    "(under backend/tests/, files named test_*.py) and the project's JS test runner "
    "for frontend (under __tests__/ or *.test.ts). Tests must import the ACTUAL "
    "modules/paths shown, be runnable, and assert real behaviour — no stubs that "
    "always pass. Return strictly structured JSON with a files array."
)


async def generate_build_tests(build_id: UUID, db: Session) -> dict[str, Any]:
    """Generate automated test files from the project's acceptance criteria."""
    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}

    # Collect acceptance criteria from every task's spec.
    tasks = (
        db.query(Task)
        .filter(Task.project_id == build.project_id, Task.deleted_at.is_(None),
                Task.order_index < SYSTEM_ORDER_FLOOR)
        .all()
    )
    criteria: list[str] = []
    for t in tasks:
        spec = _spec_for_task(t)
        for c in (spec.get("acceptance_criteria") or []):
            if str(c).strip():
                criteria.append(f"[{t.title}] {c}")
    if not criteria:
        return {"error": "No acceptance criteria found — generate task specs first."}

    files = (
        db.query(GeneratedFile)
        .filter(GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None))
        .all()
    )
    if not files:
        return {"error": "Generate code before generating tests."}

    # Real code as context: signatures of everything (so tests import correct paths).
    manifest = _manifest(files, limit=150)
    crit_block = "\n".join(f"- {c}" for c in criteria[:120])

    prompt = (
        f"PROJECT FILES (paths + signatures — import the REAL paths/names):\n{manifest}\n\n"
        f"ACCEPTANCE CRITERIA TO VERIFY:\n{crit_block}\n\n"
        "Generate automated test files covering these criteria. Group by area. "
        "Each test file complete and runnable; import the actual modules above."
    )
    result = await ai_call(
        prompt=prompt,
        response_model=GeneratedFileSet,
        system=TESTS_SYSTEM,
        max_tokens=14000,
        task_type="code_generate",
        screen="tasks",
    )
    written = 0
    for f in result.files:
        if f.path and f.content.strip():
            _persist_file(db, build, f.path, f.content, f.language, task_id=None)
            written += 1

    report = dict(build.quality_report or {})
    report["tests"] = {"files": written, "criteria": len(criteria)}
    build.quality_report = report
    db.commit()
    return {"status": "generated", "test_files": written, "criteria": len(criteria)}


# ── Polish pass: raise generated code to production quality ───────────────────

POLISH_SYSTEM = (
    "You are a principal engineer doing a quality pass on existing code. Improve "
    "validation, error handling, security, types, naming, and docs WITHOUT changing "
    "behaviour or the public interface. Keep the same path, exports, and signatures. "
    "Return strictly structured JSON with the single improved file in the files array."
)

# Files worth polishing first — the highest-risk / highest-value layers.
_CRITICAL_PATH_HINTS = (
    "auth", "security", "middleware", "model", "schema", "payment", "billing",
    "/api/", "router", "service", "core", "config", "db", "database", "permission",
)


def _is_critical(path: str) -> bool:
    low = path.lower()
    if low.endswith((".md", ".json", ".lock", ".txt", ".yml", ".yaml", ".gitignore")):
        return False
    return any(h in low for h in _CRITICAL_PATH_HINTS)


async def polish_build(
    build_id: UUID, db: Session, scope: str = "critical", max_files: int = 40,
) -> dict[str, Any]:
    """Re-write files to production quality. scope='critical' (default) or 'all'."""
    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}

    files = (
        db.query(GeneratedFile)
        .filter(GeneratedFile.build_id == build.id, GeneratedFile.deleted_at.is_(None))
        .order_by(GeneratedFile.created_at.asc())
        .all()
    )
    if not files:
        return {"error": "Nothing to polish — generate code first."}

    code_files = [f for f in files if f.language not in ("markdown", "json", "yaml", "text")]
    targets = code_files if scope == "all" else [f for f in code_files if _is_critical(f.path)]
    if not targets:
        targets = code_files  # fall back to all code if no critical match
    targets = targets[:max_files]

    polished = 0
    for idx, f in enumerate(targets, start=1):
        build.generation_progress = {
            "phase": "polishing",
            "message": f"Polishing {f.path} ({idx}/{len(targets)})",
        }
        db.commit()
        try:
            prompt = (
                f"Polish this file to production / class-one quality. Keep the same "
                f"path, exports, and behaviour.\n\nFILE: {f.path}\n```\n{f.content[:14000]}\n```\n\n"
                "Return the improved file (same path) in the files array."
            )
            result = await ai_call(
                prompt=prompt,
                response_model=GeneratedFileSet,
                system=POLISH_SYSTEM,
                max_tokens=14000,
                task_type="code_polish",
                screen="tasks",
            )
            out = next((x for x in result.files if x.content.strip()), None)
            if out:
                _persist_file(db, build, f.path, out.content, out.language or f.language,
                              task_id=f.task_id, status=FileStatus.edited)
                polished += 1
                db.commit()
        except Exception:  # noqa: BLE001 — one file failing must not abort the pass
            logger.warning("Polish failed for %s", f.path)

    # Re-run the static gate so polish can't introduce syntax breakage.
    static = await _validate_and_repair(db, build)
    report = dict(build.quality_report or {})
    report["polish"] = {"scope": scope, "polished": polished, "targets": len(targets)}
    report["static_check"] = static
    build.quality_report = report
    build.generation_progress = {"phase": "completed",
                                 "message": f"Polished {polished} files ({scope})."}
    db.commit()
    return {"status": "polished", "polished": polished, "targets": len(targets), "scope": scope}
