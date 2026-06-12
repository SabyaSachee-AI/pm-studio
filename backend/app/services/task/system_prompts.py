"""Prompt assembly for pinned system tasks — pure data formatting, no AI calls."""

from typing import Any

PROJECT_BIBLE_ORDER = 99996
CODE_AUDIT_ORDER = 99997
LOCAL_UI_TEST_ORDER = 99998
DEPLOY_ORDER = 99999

SYSTEM_TASK_ORDERS = (
    PROJECT_BIBLE_ORDER,
    CODE_AUDIT_ORDER,
    LOCAL_UI_TEST_ORDER,
    DEPLOY_ORDER,
)


def _frs(srs_content: dict[str, Any]) -> list[dict[str, Any]]:
    frs = srs_content.get("functional_requirements") or []
    return [fr for fr in frs if isinstance(fr, dict) and fr.get("fr_number")]


def _nfrs(srs_content: dict[str, Any]) -> list[dict[str, Any]]:
    nfrs = (
        srs_content.get("non_functional_requirements")
        or srs_content.get("nonfunctional_requirements")
        or []
    )
    return [nfr for nfr in nfrs if isinstance(nfr, dict)]


def _endpoints(arch_content: dict[str, Any] | None) -> list[dict[str, Any]]:
    doc_api = (arch_content or {}).get("doc_api") or {}
    endpoints = doc_api.get("endpoints") or []
    return [ep for ep in endpoints if isinstance(ep, dict) and (ep.get("path") or ep.get("full_path"))]


def _tables(arch_content: dict[str, Any] | None) -> list[dict[str, Any]]:
    doc_database = (arch_content or {}).get("doc_database") or {}
    tables = doc_database.get("tables") or []
    return [t for t in tables if isinstance(t, dict) and t.get("name")]


def _frontend_pages(arch_content: dict[str, Any] | None) -> list[dict[str, Any]]:
    doc_frontend = (arch_content or {}).get("doc_frontend") or {}
    pages = doc_frontend.get("pages") or []
    return [p for p in pages if isinstance(p, dict)]


def _ep_line(ep: dict[str, Any]) -> tuple[str, str]:
    method = str(ep.get("method", "")).strip().upper() or "GET"
    path = str(ep.get("full_path") or ep.get("path") or "").strip()
    return method, path


def build_code_audit_prompt(
    project_name: str,
    srs_content: dict[str, Any],
    arch_content: dict[str, Any] | None,
    task_titles: list[str],
) -> str:
    """Assemble the final code audit prompt from SRS, architecture, and task data."""
    fr_lines: list[str] = []
    for fr in _frs(srs_content):
        fr_lines.append(
            f"{fr['fr_number']}: {fr.get('title', '')} → expected at: backend/app/api/v1/..."
        )
    fr_block = "\n".join(fr_lines) if fr_lines else "(no functional requirements found in SRS)"

    ep_lines: list[str] = []
    for ep in _endpoints(arch_content):
        method, path = _ep_line(ep)
        file_hint = str(ep.get("file", "")).strip() or "backend/app/api/v1/.../router.py"
        suffix = " → must be soft delete only" if method == "DELETE" else f" → {file_hint}"
        ep_lines.append(f"  {method} {path}{suffix}")
    ep_block = "\n".join(ep_lines) if ep_lines else "  (no endpoints defined in architecture)"

    table_lines: list[str] = []
    for table in _tables(arch_content):
        cols = [
            f"{c['name']} {c.get('type', '')}".strip()
            for c in (table.get("columns") or [])
            if isinstance(c, dict) and c.get("name")
        ]
        if "deleted_at" not in {c.split(" ")[0] for c in cols}:
            cols.append("deleted_at TIMESTAMPTZ")
        table_lines.append(f"  Table: {table['name']} → columns: {', '.join(cols)}")
    table_block = "\n".join(table_lines) if table_lines else "  (no tables defined in architecture)"

    task_lines = "\n".join(f"  - {t}" for t in task_titles) if task_titles else "  (no tasks recorded)"

    return f"""You are performing a final code audit of {project_name}.
Complete every step in order. Do not skip any step.

Project tasks implemented so far:
{task_lines}

════════════════════════════════════════
STEP 1 — FUNCTIONAL REQUIREMENT COVERAGE
════════════════════════════════════════
Verify that every SRS functional requirement below has a corresponding
implementation in the codebase. For each FR, find the backend route,
service function, and frontend page that implements it.
If any FR has no implementation, create it now before proceeding.

{fr_block}

════════════════════════════════════════
STEP 2 — API ENDPOINT COMPLETENESS
════════════════════════════════════════
Verify every endpoint listed below exists in the codebase,
has correct request/response schemas, and returns proper HTTP status codes.

{ep_block}

════════════════════════════════════════
STEP 3 — DATABASE COMPLETENESS
════════════════════════════════════════
Verify every table and column listed below exists in:
  a) SQLAlchemy model (backend/app/models/)
  b) Alembic migration (backend/app/services/migrations/versions/)

{table_block}

If any table or column is missing from migrations, generate the
Alembic migration now: alembic revision --autogenerate -m "add missing [table]"

════════════════════════════════════════
STEP 4 — GAP AND DEFECT DETECTION
════════════════════════════════════════
Search the entire codebase for these patterns and fix every instance found:

  a) TODO or FIXME or HACK comments → implement or remove
  b) raise NotImplementedError → implement the function
  c) Hardcoded secrets, API keys, passwords, or connection strings
     Fix: move to os.getenv() and add to .env.example
  d) Missing deleted_at filter in any SQLAlchemy query
     Every query must include: .where(Model.deleted_at.is_(None))
  e) Any endpoint that performs AI generation without using Celery
     Fix: move to Celery task, return task_id from endpoint
  f) Direct AI provider calls outside of ai_call()
     Fix: route through backend/app/services/ai/base.py
  g) Any `any` TypeScript type in frontend code
     Fix: add proper interface or type
  h) Missing error handling at API boundaries (no try/except on external calls)

════════════════════════════════════════
STEP 5 — AUTOMATED TEST WRITING
════════════════════════════════════════
For every API endpoint that does not have a test, write a pytest test.
Place tests in: backend/tests/test_{{domain}}.py
Follow the pattern of existing test files.

Each test must cover:
  - Happy path (correct input → correct response + status code)
  - Auth failure (no token → 401)
  - Not found (invalid ID → 404)
  - Soft delete verification (deleted record not returned in list)

Run all tests after writing: cd backend && pytest -v
Fix any failing test before proceeding to the next step.

════════════════════════════════════════
STEP 6 — CODE QUALITY PASS
════════════════════════════════════════
Run these commands and fix all reported issues:

  cd backend
  ruff check . --fix
  mypy app/ --ignore-missing-imports

  cd frontend
  npx tsc --noEmit
  npx eslint . --fix

All commands must exit with zero errors before this task is complete.
"""


def build_local_ui_test_prompt(
    project_name: str,
    prd_content: dict[str, Any],
    srs_content: dict[str, Any],
    arch_content: dict[str, Any] | None,
) -> str:
    """Assemble the manual local UI test checklist from PRD, SRS, and architecture data."""
    pages = _frontend_pages(arch_content)
    routes_by_name: dict[str, str] = {}
    for page in pages:
        description = str(page.get("description", "")).lower()
        route = str(page.get("path", "")).strip()
        if route:
            routes_by_name[description] = route

    feature_blocks: list[str] = []
    features = prd_content.get("features") or []
    for feature in features:
        if not isinstance(feature, dict) or not feature.get("title"):
            continue
        title = str(feature["title"]).strip()
        route = next(
            (r for desc, r in routes_by_name.items() if title.lower() in desc),
            "(find the route in the frontend navigation)",
        )
        feature_blocks.append(
            f"""Feature: {title}
  □ Navigate to: {route}
  □ Perform the primary action
  □ Verify correct data appears in the UI
  □ Verify correct data is stored in the database:
    SELECT * FROM [table] ORDER BY created_at DESC LIMIT 3;
  □ Verify the action appears correctly after page refresh
  □ Test the error case: what happens with invalid input?"""
        )
    feature_block = (
        "\n\n".join(feature_blocks)
        if feature_blocks
        else "(no PRD features found — test every page reachable from the navigation)"
    )

    ep_lines: list[str] = []
    for ep in _endpoints(arch_content):
        method, path = _ep_line(ep)
        ep_lines.append(f"  □ {method} {path} → expect correct status code, response matches schema")
    if ep_lines:
        ep_lines.append("  □ Check response time < 500ms for non-AI endpoints")
        ep_lines.append("  □ Check AI endpoints return task_id immediately (< 200ms)")
    ep_block = "\n".join(ep_lines) if ep_lines else "  (no endpoints defined in architecture)"

    nfr_lines: list[str] = []
    for nfr in _nfrs(srs_content):
        category = str(nfr.get("category", "")).strip()
        metric = str(nfr.get("metric", "")).strip()
        threshold = str(nfr.get("threshold", "")).strip()
        target = " ".join(p for p in (metric, threshold) if p) or "meets SRS target"
        nfr_lines.append(f"  □ {category}: {target}")
    nfr_block = "\n".join(nfr_lines) if nfr_lines else "  □ (no NFR targets found in SRS)"

    return f"""You are preparing {project_name} for local testing.
Follow every step. Do not mark this task done until all steps pass.

════════════════════════════════════════
STEP 1 — START THE APPLICATION
════════════════════════════════════════
Run these commands in separate terminals:

Terminal 1 — Infrastructure:
  docker-compose up -d postgres redis
  # Wait 10 seconds for containers to be healthy

Terminal 2 — Backend:
  cd backend
  alembic upgrade head
  uvicorn app.main:app --reload --port 8000

Terminal 3 — Celery worker:
  cd backend
  celery -A app.core.celery_app worker --loglevel=info --pool=solo

Terminal 4 — Frontend:
  cd frontend
  npm run dev

Open browser: http://localhost:3000
Confirm no console errors on page load.
Confirm backend health: http://localhost:8000/health → returns {{"status": "ok"}}

════════════════════════════════════════
STEP 2 — AUTHENTICATION FLOW TEST
════════════════════════════════════════
Test every auth step in the browser:

  □ Register new user → check DB: SELECT * FROM users ORDER BY created_at DESC LIMIT 1
  □ Login → verify JWT cookie is set (DevTools → Application → Cookies)
  □ Refresh page → user stays logged in (cookie-based auth persists)
  □ Logout → cookie is cleared, redirect to login page
  □ Access protected page without login → redirect to login
  □ Wrong password → shows error message, no token set

════════════════════════════════════════
STEP 3 — FEATURE-BY-FEATURE TEST
════════════════════════════════════════
Test every user-facing feature listed in the PRD.
For each feature, verify the complete user journey end to end:

{feature_block}

════════════════════════════════════════
STEP 4 — API RESPONSE VERIFICATION
════════════════════════════════════════
Open browser DevTools → Network tab.
Perform each action below and verify the API response:

{ep_block}

════════════════════════════════════════
STEP 5 — EDGE CASE AND ERROR TEST
════════════════════════════════════════
  □ Submit empty forms → validation errors shown correctly
  □ Submit with maximum length input → accepted or rejected gracefully
  □ Delete a record → soft deleted (deleted_at set), not shown in list
  □ Concurrent requests — open two browser tabs, perform same action
  □ Network offline — disconnect network, verify graceful error message
  □ Token expiry — wait for token to expire or clear cookie manually,
    verify redirect to login

════════════════════════════════════════
STEP 6 — PERFORMANCE CHECK
════════════════════════════════════════
Verify NFRs from SRS are met:
{nfr_block}

Check in DevTools → Lighthouse → run audit.
Performance score must be above 70 before proceeding to deployment.

════════════════════════════════════════
SIGN-OFF
════════════════════════════════════════
When all steps above pass, mark this task done in PM Studio.
Then proceed to: "Git push and deploy"
"""


def build_deploy_prompt(project_name: str) -> str:
    """Assemble the git push and deploy checklist."""
    return f"""DEPLOYMENT PREPARATION — {project_name}
Complete every step in order. Do not push to GitHub until Step 1 passes.

════════════════════════════════════════
STEP 1 — PRE-PUSH SAFETY CHECKLIST
════════════════════════════════════════
Run every command below. All must succeed before any git command:

  cd backend && pytest -v
  # All tests must pass. Fix any failure before continuing.

  grep -r "sk-ant\\|sk-\\|password\\s*=\\s*['\\"]" backend/ --include="*.py"
  # Output must be empty. If any secrets found, move them to .env immediately.

  cat .gitignore | grep ".env"
  # Must show .env is ignored. If missing, add it now.

  cd backend && alembic heads
  # Must show exactly one head. If multiple heads, merge them.

  cd frontend && npm run build
  # Must complete with zero errors.

════════════════════════════════════════
STEP 2 — GIT COMMIT PLAN
════════════════════════════════════════
Commit in this order to keep git history clean and readable.
Use these exact commit message conventions.

Check what is uncommitted first:
  git status
  git diff --stat

Then commit in module order:

  # 1. Data layer first
  git add backend/app/models/ backend/app/schemas/
  git commit -m "feat: add domain models and Pydantic schemas"

  # 2. Database migrations
  git add backend/app/services/migrations/versions/
  git commit -m "feat: add Alembic database migrations"

  # 3. Business logic
  git add backend/app/services/
  git commit -m "feat: add service layer and business logic"

  # 4. Background workers
  git add backend/app/workers/
  git commit -m "feat: add Celery background task workers"

  # 5. API routes
  git add backend/app/api/
  git commit -m "feat: add FastAPI route handlers"

  # 6. Frontend pages
  git add "frontend/app/(studio)/"
  git commit -m "feat: add frontend application pages"

  # 7. Frontend components
  git add frontend/components/ frontend/lib/
  git commit -m "feat: add reusable UI components and API client"

  # 8. Tests
  git add backend/tests/
  git commit -m "test: add API endpoint test suite"

  # 9. Configuration and infrastructure
  git add docker-compose.yml docker/ .env.example
  git add .github/ nginx.conf
  git commit -m "chore: add Docker, CI/CD pipeline, and infrastructure config"

  # Final push
  git push origin main

════════════════════════════════════════
STEP 3 — CI/CD PIPELINE VERIFICATION
════════════════════════════════════════
After git push, verify .github/workflows/deploy.yml exists and contains:

  Trigger: on push to main branch
  Job 1 — Test:
    - Install Python dependencies
    - Run: cd backend && pytest -v
    - Fail the pipeline if any test fails

  Job 2 — Build (runs after Test passes):
    - Build Docker image for backend
    - Build Docker image for frontend
    - Push images to registry (GitHub Container Registry or Docker Hub)

  Job 3 — Deploy (runs after Build passes):
    - SSH into VPS
    - Pull latest Docker images
    - Run: docker-compose up -d --build
    - Run: docker-compose exec backend alembic upgrade head
    - Run health check: curl http://localhost:8000/health

If .github/workflows/deploy.yml does not exist, create it now
following the structure above. Use GitHub Actions syntax.

════════════════════════════════════════
STEP 4 — VPS DEPLOYMENT VERIFICATION
════════════════════════════════════════
After GitHub Actions pipeline completes:

  1. SSH into VPS:
     ssh [user]@[vps-ip]

  2. Verify containers are running:
     docker-compose ps
     # All services must show "Up" and "healthy"

  3. Verify database migrations applied:
     docker-compose exec backend alembic current
     # Must show the latest migration head

  4. Verify application is serving:
     curl http://localhost:8000/health
     curl http://localhost:3000
     # Both must return 200

  5. Check application logs for errors:
     docker-compose logs backend --tail=50
     docker-compose logs celery-worker --tail=50
     # No ERROR lines should appear on startup

  6. Test one critical API endpoint on the live VPS:
     curl -X POST http://[vps-ip]:8000/api/v1/auth/login \\
       -H "Content-Type: application/json" \\
       -d '{{"email":"test@example.com","password":"testpassword"}}'
     # Must return 200 with token cookie set

  7. Open the live URL in browser and complete the auth flow.
     Confirm the application works identically to local testing.

════════════════════════════════════════
DEPLOYMENT COMPLETE
════════════════════════════════════════
When all steps above pass, mark this task done in PM Studio.
Record the live URL in the project settings.
"""


def build_git_commit_block(
    task_title: str,
    task_type: str,
    module_name: str,
    suggested_file: str | None,
    is_last_in_module: bool,
) -> str:
    """Assemble the git commit block appended to regular feature task specs."""
    module_slug = (
        "".join(c if c.isalnum() or c in "-_" else "_" for c in module_name.lower().strip())
        or "module"
    )
    files_line = suggested_file or "[the files this task created or modified]"

    block = f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GIT COMMIT — After this task is working and tested locally:

Verify your work first:
  cd backend && pytest tests/test_{module_slug}.py -v
  # All tests must pass before committing

Stage and commit the files this task touched:
  git add {files_line}
  git add [any additional files created for this task]
  git commit -m "{task_type}: {task_title.lower()}"
"""
    if is_last_in_module:
        block += f"""
  # Module complete — commit everything in this module together
  git add backend/app/api/v1/{module_slug}/
  git add backend/app/services/{module_slug}/
  git add backend/app/models/{module_slug}.py
  git add backend/app/schemas/{module_slug}.py
  git add backend/app/workers/{module_slug}_tasks.py
  git add "frontend/app/(studio)/{module_slug}/"
  git add frontend/components/features/{module_slug}/
  git add backend/app/services/migrations/versions/*{module_slug}*
  git commit -m "feat: complete {module_name} module — [brief description]"
  git push origin main

After push, verify GitHub Actions pipeline passes before starting the next module.
"""
    block += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    return block
