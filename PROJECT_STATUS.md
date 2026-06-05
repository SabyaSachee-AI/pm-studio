# PM Studio — project status

> Last updated: 2026-06-05  
> Purpose: onboarding doc for AI assistants and developers. Read this first to understand what exists and what to build next.

---

## 1. What is PM Studio?

**PM Studio** is an AI-assisted project management application (monorepo under `PMS/pm-studio`).

It is in **early bootstrap phase**: scaffolding, dependencies, and dev standards are in place, but core backend infrastructure and all product features are **not yet built**.

Development standards live in [`.cursorrules`](./.cursorrules). Follow them strictly.

---

## 2. Tech stack (planned / partially wired)

| Layer | Technology | Status |
|-------|------------|--------|
| Backend API | FastAPI (async) + Pydantic v2 | Minimal — health endpoint only |
| ORM | SQLAlchemy 2 (async) | Dependencies installed, **not configured** |
| Database | PostgreSQL 16 | Docker service ready |
| Cache / queue broker | Redis 7 | Docker service ready |
| Background jobs | Celery | Dependencies installed, **not configured** |
| AI | Anthropic Claude via Instructor | `ai_call()` helper exists |
| File storage | Cloudflare R2 (boto3) | Dependencies installed, **not configured** |
| PDF export | WeasyPrint + PyMuPDF | Dependencies installed, **not used** |
| Frontend | Next.js 16 + React 19 + TypeScript | Default template scaffold |
| UI | Tailwind 4 + shadcn/ui (base-nova) | Partial — `button` component only |
| Auth | JWT (python-jose) | Env vars set, **not implemented** |

---

## 3. Repository layout

```
pm-studio/
├── .cursorrules          # Dev standards (read before coding)
├── .env                  # Local secrets (gitignored)
├── .env.example          # Empty — needs to be populated
├── docker-compose.yml    # postgres + redis
├── PROJECT_STATUS.md     # This file
│
├── backend/
│   ├── requirements.txt  # Full dependency lock (pip freeze style)
│   ├── venv/             # Local Python venv (gitignored)
│   └── app/
│       ├── main.py                 # FastAPI app + /health
│       ├── __init__.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── v1/
│       │       └── __init__.py     # No routers yet
│       └── services/
│           └── ai/
│               └── base.py         # ai_call() — only AI entry point
│
└── frontend/
    ├── package.json
    ├── components.json             # shadcn config
    ├── app/
    │   ├── layout.tsx              # Default Next.js layout
    │   ├── page.tsx                # Default starter page (not PM Studio UI)
    │   └── globals.css
    ├── components/ui/button.tsx    # Only shadcn component added
    └── lib/utils.ts
```

### Expected structure (not yet created)

Per `.cursorrules`, these directories/files should be added as features are built:

```
backend/app/
├── api/v1/{domain}/router.py
├── services/{domain}/
├── models/{domain}.py
├── schemas/{domain}.py
└── workers/{domain}_tasks.py

frontend/
├── app/(studio)/{feature}/page.tsx
├── components/features/{feature}/
└── lib/api.ts
```

---

## 4. What is done

### Infrastructure & config

- [x] Monorepo folder structure (`backend/`, `frontend/`)
- [x] `docker-compose.yml` — PostgreSQL 16 + Redis 7 with healthcheck
- [x] `.env` — `DATABASE_URL`, `REDIS_URL`, `JWT_*`, `ANTHROPIC_API_KEY`, `ENVIRONMENT`
- [x] `.gitignore` — `.env`, `venv/`, `node_modules/`, `.next/`, etc.
- [x] Python venv created; all backend deps installed (`requirements.txt`)
- [x] Frontend deps installed (`npm install` assumed; `node_modules/` present)

### Backend

- [x] FastAPI app in `app/main.py`
  - Title: `"PM Studio"`, version `"1.0.0"`
  - CORS allows `http://localhost:3000`
  - `GET /health` → `{"status": "ok", "service": "pm-studio"}`
- [x] AI service stub in `app/services/ai/base.py`
  - `ai_call(prompt, response_model, system="", context="")` using Instructor + Anthropic
  - Model: `claude-sonnet-4-5-20250514`
  - **Rule:** all AI calls must go through this function only

### Frontend

- [x] Next.js 16 app scaffolded (`create-next-app` defaults)
- [x] Tailwind 4 + TypeScript strict mode
- [x] shadcn/ui initialized (`components.json`, `button` component)
- [x] `AGENTS.md` — note that Next.js 16 has breaking changes vs older versions

### Git

- [ ] **No commits yet** — entire repo is untracked (`git status` shows all files as `??`)

### Recent fix (2026-06-05)

- [x] Fixed corrupted `__init__.py` files that contained null bytes (`\x00`), which blocked `uvicorn app.main:app` with:
  ```
  SyntaxError: source code string cannot contain null bytes
  ```
  Affected files (now clean):
  - `backend/app/__init__.py`
  - `backend/app/api/__init__.py`
  - `backend/app/api/v1/__init__.py`

---

## 5. What is NOT done

Everything below is **missing** and must be built:

| Area | Missing pieces |
|------|----------------|
| Database | SQLAlchemy async engine/session, base model, Alembic setup, migrations |
| Models | No `app/models/` — no tables, no `deleted_at` soft-delete pattern |
| Schemas | No `app/schemas/` |
| API routes | No `app/api/v1/{domain}/router.py`; routers not mounted in `main.py` |
| Auth | No user model, login/register, JWT middleware |
| Celery | No worker app, no `app/workers/`, no task definitions |
| R2 / files | No upload/download service |
| PDF | No export pipeline |
| Tests | No test files (pytest + pytest-asyncio installed) |
| Frontend product UI | Still default Next.js starter page |
| Frontend API client | No `lib/api.ts` |
| Frontend routes | No `app/(studio)/` feature pages |
| `.env.example` | Empty — should document required env vars (no real secrets) |

---

## 6. Development rules (from `.cursorrules`)

These three rules must never be violated:

1. **AI calls** — use `app/services/ai/base.py` → `ai_call()` only. Always pass a Pydantic `response_model`. Store structured JSON, never raw markdown.
2. **Soft delete** — every model must have `deleted_at = Column(TIMESTAMPTZ, nullable=True)`. Never hard-delete.
3. **Heavy work async** — AI generation, PDF export, etc. go through Celery. API returns `task_id` immediately; never block the response.

Additional standards:

- Python: `async/await` everywhere, type hints required
- TypeScript: strict mode, no `any`
- UI text: sentence case
- Errors: proper HTTP status + `{"detail": "message"}`
- Secrets: `os.getenv()` only — never hardcode

---

## 7. How to run locally

### Prerequisites

- Docker (for Postgres + Redis)
- Python 3.12
- Node.js (for frontend)

### 1. Start infrastructure

```powershell
cd F:\knowledgebase\ProjectPreparation\PMS\pm-studio
docker compose up -d
```

Services:

- Postgres: `localhost:5432` — db `pmstudio`, user `pmstudio`, password `devpassword123`
- Redis: `localhost:6379`

### 2. Backend

```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Verify: `GET http://localhost:8000/health`

> Load `.env` from project root. `main.py` does not yet call `python-dotenv` — consider adding `load_dotenv()` in a `config.py` or at app startup so env vars are available to SQLAlchemy, Celery, and AI services.

### 3. Frontend

```powershell
cd frontend
npm run dev
```

Runs at `http://localhost:3000` (CORS already allowed on backend).

---

## 8. Environment variables

Current `.env` (project root):

```env
DATABASE_URL=postgresql+asyncpg://pmstudio:devpassword123@localhost:5432/pmstudio
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=<set-a-32+-char-secret>
JWT_ALGORITHM=HS256
ANTHROPIC_API_KEY=<your-key>
ENVIRONMENT=development
```

**TODO:** populate `.env.example` with the same keys and placeholder values (no real secrets).

---

## 9. Recommended next steps (in order)

Use this as the build sequence for the next AI session or sprint.

### Phase A — Backend foundation

1. **`app/core/config.py`** — Pydantic settings loading from `.env` (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, etc.)
2. **`app/core/database.py`** — async SQLAlchemy engine, `AsyncSession`, dependency `get_db()`
3. **`app/models/base.py`** — declarative base with `id`, `created_at`, `updated_at`, `deleted_at` (soft delete)
4. **Alembic** — `alembic init`, wire to async engine, first migration
5. **Mount API** — create `app/api/v1/router.py` aggregator; include in `main.py` under `/api/v1`

### Phase B — Auth (first domain)

6. **`app/models/user.py`** + **`app/schemas/user.py`**
7. **`app/services/auth/`** — password hashing (passlib/bcrypt), JWT create/verify
8. **`app/api/v1/auth/router.py`** — register, login, me
9. **Auth dependency** — `get_current_user` for protected routes

### Phase C — Async infrastructure

10. **`app/core/celery_app.py`** — Celery instance bound to `REDIS_URL`
11. **`app/workers/`** — example task skeleton; pattern for AI/PDF jobs returning `task_id`
12. **Task status endpoint** — poll Celery result by `task_id`

### Phase D — Frontend foundation

13. **`frontend/lib/api.ts`** — typed fetch wrapper pointing to `http://localhost:8000/api/v1`
14. **Root layout** — rename metadata to "PM Studio", basic app shell
15. **`app/(studio)/`** — first feature page (e.g. dashboard or login)
16. **Auth flow** — login page + token storage + protected routes

### Phase E — First product feature

17. Pick the first PM domain (projects, requirements, specs, etc.) and implement end-to-end:
    - model + schema + service + router (backend)
    - Celery task if AI-heavy
    - studio page + feature components (frontend)

> **Note:** Specific PM product domains (entities, workflows, screens) are not defined in the repo yet. Confirm with the product owner before implementing Phase E.

---

## 10. Key files to read first

| File | Why |
|------|-----|
| [`.cursorrules`](./.cursorrules) | Non-negotiable dev standards |
| [`backend/app/main.py`](./backend/app/main.py) | Current FastAPI entry point |
| [`backend/app/services/ai/base.py`](./backend/app/services/ai/base.py) | AI integration pattern |
| [`docker-compose.yml`](./docker-compose.yml) | Local infra |
| [`frontend/components.json`](./frontend/components.json) | shadcn/ui setup |

---

## 11. Quick health checklist

Before starting new work, confirm:

- [ ] `docker compose ps` — postgres and redis healthy
- [ ] `uvicorn app.main:app --reload --port 8000` — starts without import errors
- [ ] `GET /health` returns 200
- [ ] `npm run dev` in `frontend/` — Next.js starts on port 3000
- [ ] No null bytes in `.py` files (see fix in section 4)

---

## 12. Open questions for product owner

1. What are the core PM domains? (e.g. projects, epics, user stories, sprint planning, AI spec generation)
2. What is the first user-facing feature to ship after auth?
3. Is multi-tenancy (organizations/workspaces) required from day one?
4. Cloudflare R2 bucket credentials — when to wire file uploads?

---

*End of status doc. Start from **Section 9 — Phase A** unless the product owner specifies otherwise.*
