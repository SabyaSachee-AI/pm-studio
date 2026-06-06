# PM Studio — Project Status

> **Last updated:** 2026-06-05  
> **Phase:** Week 6 — backend pipelines complete, studio shell in place

---

## Overview

PM Studio is an AI-assisted project management platform for software studios. The backend API, AI generation pipelines, and database schema are fully operational. The frontend provides authentication and a basic studio shell; feature UIs for PRD, SRS, Kanban, and specs are planned for Phase 1.

---

## Infrastructure

| Component | Status | Details |
|-----------|--------|---------|
| Docker Compose | ✅ | PostgreSQL 16 + Redis 7 |
| FastAPI backend | ✅ | Port 8000 |
| Next.js frontend | ✅ | Next.js 16, port 3000 |
| Celery worker | ✅ | Redis broker, `--pool=solo` on Windows |
| Alembic migrations | ✅ | `cd backend && alembic upgrade head` |

---

## Database Tables (13)

| Table | Purpose |
|-------|---------|
| `users` | 9 roles: studio_owner, studio_admin, project_manager, business_analyst, architect, developer, qa_engineer, client, viewer |
| `clients` | Client organizations |
| `projects` | Projects linked to clients |
| `requirements` | Uploaded requirement documents + AI analysis (JSONB) |
| `prds` | Product requirement documents (JSONB) |
| `srs_documents` | Software requirements specs, IEEE 830 (JSONB) |
| `tasks` | Kanban tasks per project |
| `task_specs` | AI-generated technical specs per task (JSONB) |
| `task_status_logs` | Task status change audit trail |
| `organizations` | Multi-tenant org support |
| `screen_permissions` | Role-to-screen access map (seeded) |
| `document_versions` | Version history for PRDs and SRS |
| `alembic_version` | Migration tracking |

All domain tables use **soft delete** (`deleted_at`).

---

## Backend API (fully working)

### Auth
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

### Clients
- `GET/POST /api/v1/clients`
- `GET/PATCH/DELETE /api/v1/clients/{id}`

### Projects
- `GET/POST /api/v1/projects`
- `GET/PATCH/DELETE /api/v1/projects/{id}`
- `GET /api/v1/projects/by-client/{client_id}`

### Requirements
- `POST /api/v1/requirements/upload`
- `GET /api/v1/requirements/{id}`

### PRDs
- `POST /api/v1/prds/generate`
- `GET /api/v1/prds/{id}`
- `PATCH /api/v1/prds/{id}/approve`
- `GET /api/v1/prds/project/{project_id}`

### SRS
- `POST /api/v1/srs/generate`
- `GET /api/v1/srs/{id}`
- `PATCH /api/v1/srs/{id}/approve`
- `GET /api/v1/srs/project/{project_id}`

### Tasks (Kanban)
- `GET/POST /api/v1/tasks`
- `GET/PATCH/DELETE /api/v1/tasks/{id}`
- `PATCH /api/v1/tasks/{id}/status`
- `GET /api/v1/tasks/kanban/{project_id}`

### Technical Specs
- `POST /api/v1/specs/generate`
- `GET /api/v1/specs/{id}`
- `GET /api/v1/specs/task/{task_id}`
- `PATCH /api/v1/specs/{id}/assign`

### Background jobs
- `GET /api/v1/tasks/{celery_task_id}` — Celery task polling

### Health
- `GET /health`

---

## AI Pipeline (fully working)

| Step | Input | Output schema | Storage |
|------|-------|---------------|---------|
| Requirement analysis | PDF upload → PyMuPDF text extraction | `RequirementAnalysisSchema` (gaps, risks, NFRs, questions) | `requirements.analysis_json` |
| PRD generation | Analyzed requirements | `PRDSchema` | `prds.content_json` |
| SRS generation | Approved PRD | `SRSSchema` (IEEE 830) | `srs_documents.content_json` |
| Technical spec | Kanban task + SRS context | `TaskSpecSchema` | `task_specs.content_json` |

All AI calls run through **Celery** background jobs. Results are stored as **JSONB** in PostgreSQL. Never raw markdown.

---

## Frontend

| Feature | Status |
|---------|--------|
| Next.js 16 app (port 3000) | ✅ |
| Login page with JWT auth | ✅ |
| Dashboard with user info | ✅ |
| Token storage in localStorage | ✅ |
| Protected routes | ✅ |

---

## Three Non-Negotiable Rules

1. **AI calls** — always through `ai_call()` with a Pydantic `response_model`
2. **Soft delete** — `deleted_at` on every model; never hard delete
3. **Heavy work** — always through Celery; API returns `task_id` immediately

---

## What Is Not Yet Built (Phase 1)

- Knowledge Base UI
- Decision Registry UI
- Print/PDF export
- Frontend for PRD / SRS / Tasks / Specs
- Role-based screen permissions enforcement
- Architecture Suite
- Git Manager
- Test Manager
- Deploy Manager
- Client Portal
- MCP Server

---

## How to Run

```powershell
# 1. Infrastructure (from project root)
docker compose up -d

# 2. Backend
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. Celery worker (Windows requires solo pool)
celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 4. Frontend
cd frontend
npm run dev
```

**Default login:** `owner@pmstudio.com` / `password123`

---

## Environment Variables

Copy `.env.example` to `.env` at the project root. Required variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `SYNC_DATABASE_URL` | No | Sync URL for Alembic (auto-derived from `DATABASE_URL`) |
| `REDIS_URL` | Yes | Redis connection URL |
| `JWT_SECRET` | Yes | Min 32 characters |
| `JWT_ALGORITHM` | No | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | Default `7` |
| `ANTHROPIC_API_KEY` | Yes* | Required for AI features |
| `ENVIRONMENT` | No | Default `development` |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins |

\* Optional at startup; AI endpoints fail at runtime if unset.

Optional: `R2_*` vars for Cloudflare R2 storage, `UPLOAD_DIR` for local file fallback.

---

## Known Limitations

1. **WeasyPrint on Windows** — PDF generation needs GTK/Pango; use Docker backend image locally.
2. **Celery on Windows** — must use `--pool=solo`.
3. **SRS generation** — requires PRD status `approved`.
4. **Route naming** — `GET /api/v1/tasks/{id}` serves PM tasks; Celery polling uses the same path pattern (register order matters).
5. **Uvicorn `--reload` on Windows** — orphaned workers can hold port 8000; kill stale PIDs if routes 404 after code changes.

---

## Migration Chain (head)

`fdfe482d01cb` → `c8c3d473f83f` → `f6ed1711e458` → `514c783416cf` → `33a032d9a080` → `7618b8bcd83b` → `c28834547b24` → `a9f3e2b1c4d5` → **`8f7cf3ad8389`** (tasks + specs tables)
