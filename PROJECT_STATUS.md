# PM Studio — Project Status

> **Last updated:** 2026-06-06  
> **Phase:** MVP complete — verified end-to-end on real test data

---

## Summary

PM Studio is a working AI-assisted planning platform for software studios. The full MVP loop runs from requirement upload through technical specs and knowledge base storage. Backend API, Celery workers, Next.js studio UI, and database schema are operational and **E2E-verified** on the Acme E-Commerce test project.

---

## Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| Docker Compose | ✅ | 5 services: postgres, redis, backend, celery-worker, frontend |
| FastAPI backend | ✅ | Port 8000 |
| Next.js frontend | ✅ | Next.js 16, port 3000 |
| Celery worker | ✅ | Redis broker; `--pool=solo` required on Windows |
| Alembic migrations | ✅ | Head: `d5e6f7a8b9c0`; path: `app/services/migrations` |
| GitHub CI | ✅ | Import check, pytest, frontend lint/build |
| Staging deploy | ✅ | `scripts/deploy-staging.sh` |

---

## Database Tables (17)

| Table | Purpose |
|-------|---------|
| `users` | 9 roles: studio_owner, studio_admin, project_manager, business_analyst, architect, developer (code_creator), qa_engineer, client, viewer |
| `clients` | Client organizations |
| `projects` | Projects linked to clients |
| `requirements` | Uploaded docs + AI analysis (JSONB) |
| `prds` | Product requirement documents (JSONB) |
| `srs_documents` | IEEE 830 SRS (JSONB) |
| `tasks` | Kanban work items |
| `task_specs` | AI technical specs per task (JSONB) |
| `task_status_logs` | Task status audit trail |
| `organizations` | Multi-tenant org support |
| `screen_permissions` | Role-to-screen access (seeded) |
| `document_versions` | PRD/SRS version history |
| `knowledge_base_items` | Saved PRDs, SRS, specs |
| `reusable_modules` | Reusable module patterns |
| `decisions` | Decision registry |
| `notifications` | In-app user notifications |
| `alembic_version` | Migration tracking |

All domain tables use **soft delete** (`deleted_at`).

---

## Backend API

### Auth
- `POST/GET /api/v1/auth/register`
- `POST /api/v1/auth/login`, `/refresh`, `/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/screens` — role-based nav permissions

### Clients & projects
- Full CRUD on `/api/v1/clients` and `/api/v1/projects`
- Screen permissions enforced

### Requirements
- `POST /api/v1/requirements/upload`
- `GET /api/v1/requirements/{id}`
- `POST /api/v1/requirements/{id}/feedback-upload`
- `GET /api/v1/requirements/{id}/cost-estimate`
- `GET /api/v1/documents/requirements/{id}/clarification-pdf`

### PRDs
- `POST /api/v1/prds/generate`
- `GET/PATCH /api/v1/prds/{id}` (edit saves new version)
- `PATCH /api/v1/prds/{id}/submit`, `/approve`
- `GET /api/v1/prds/{id}/versions`
- `GET /api/v1/documents/prd/{id}/export-pdf/sync`

### SRS
- `POST /api/v1/srs/generate` (requires approved PRD)
- `GET /api/v1/srs/{id}`
- `PATCH /api/v1/srs/{id}/submit`, `/approve`
- `GET /api/v1/documents/srs/{id}/export-pdf/sync`

### Tasks (Kanban)
- `GET/POST /api/v1/tasks`
- `GET/PATCH/DELETE /api/v1/tasks/{id}`
- `PATCH /api/v1/tasks/{id}/status`
- `GET /api/v1/tasks/kanban/{project_id}`
- `POST /api/v1/tasks/extract-modules` — AI module extraction → seeds tasks

### Technical specs
- `POST /api/v1/specs/generate`
- `GET /api/v1/specs/{id}`
- `GET /api/v1/specs/task/{task_id}`
- `PATCH /api/v1/specs/{id}/assign` (sends notification)

### Knowledge base
- `GET/POST /api/v1/knowledge/items`
- `POST /api/v1/knowledge/items/save-from-source`
- `GET/POST /api/v1/knowledge/modules`

### Decisions
- Full CRUD on `/api/v1/decisions`

### Notifications
- `GET /api/v1/notifications`
- `PATCH /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/read-all`

### Background jobs
- `GET /api/v1/jobs/{id}` — Celery status poll
- `GET /api/v1/jobs/{id}/stream` — SSE progress

### Health
- `GET /health`

---

## AI Pipeline (fully working)

| Step | Input | Schema | Celery task |
|------|-------|--------|-------------|
| Requirement analysis | PDF → PyMuPDF | `RequirementAnalysisSchema` | `requirements.process_upload` |
| PRD generation | Analyzed requirements | `PRDSchema` | `prd.generate` |
| SRS generation | Approved PRD | `SRSSchema` | `srs.generate` |
| Module extraction | Approved PRD + SRS | `ModuleListSchema` | `modules.extract` |
| Technical spec | Task + SRS context | `TaskSpecSchema` | `spec.generate` |

All calls go through `ai_call()` with Pydantic `response_model`. Includes **retry** and **OpenAI fallback** when `OPENAI_API_KEY` is set. Results stored as **JSONB** — never raw markdown.

---

## Frontend (studio UI)

| Route | Features |
|-------|----------|
| `/login` | JWT auth, token storage |
| `/dashboard` | User info, protected layout |
| `/clients`, `/projects` | CRUD; projects link to Kanban |
| `/requirements` | List + detail: gaps, risks, cost, clarification PDF, feedback upload |
| `/prds`, `/prds/[id]` | List, generate, JSON edit, submit/approve, PDF, save to KB |
| `/srs`, `/srs/[id]` | List, generate, submit/approve, PDF, save to KB |
| `/tasks` | 5-column Kanban, drag-drop, extract modules, generate/assign specs |
| `/knowledge` | List saved PRD/SRS/spec items |
| `/decisions` | Record and list project decisions |
| `/admin/users` | User management |
| `/portal/prd/[id]` | Client PRD review + approve |

Sidebar filters nav by role via `GET /auth/screens`. Header shows unread notifications.

---

## Three Non-Negotiable Rules

1. **AI calls** — always through `ai_call()` with a Pydantic `response_model`
2. **Soft delete** — `deleted_at` on every model; never hard delete
3. **Heavy work** — always through Celery; API returns `task_id` immediately

---

## E2E Verification (2026-06-06)

Verified on test project **Acme E-Commerce** (`e891ce0a-7b5a-47fb-bafd-dd9bbf728ce6`) via `backend/test_e2e_flow.py`:

| Step | Result |
|------|--------|
| Requirement analyzed | `test_req.pdf` — analyzed |
| PRD approved | `04f26973-...` |
| SRS approved | `19a6bc78-...` — 12 FRs |
| Module extraction | 73 Kanban tasks created |
| Spec generation | `Build product catalog with search` — **ready** (~30s) |
| Knowledge base | 3 items saved (spec + PRD + SRS) |

**Test credentials:** `owner@pmstudio.com` / `password123`

---

## MVP Success Criteria

| Criterion | Status |
|-----------|--------|
| End-to-end flow (zero workarounds) | ✅ API + UI paths complete |
| Document quality + printable PDF | ✅ PRD, SRS, clarification PDFs |
| Spec usability in Cursor | ✅ `test_spec.py` + E2E passed |
| Speed (<5 min per stage, non-blocking) | ✅ Celery + SSE/`/jobs` polling |
| Knowledge Base (save 2+ items, reuse) | ✅ 3 items saved |

---

## What Is Not Yet Built (Phase 1+)

- Architecture Suite (6 documents)
- Detailed PERT cost estimator
- Git Manager, Test Manager, Deploy Manager, Monitor Hub
- Full Client Portal (magic links, separate auth flow)
- MCP Server (Cursor integration)
- PostgreSQL RLS, formal state machine
- Requirements traceability matrix
- VPS SSL/Nginx automation (script only; no Certbot/monitoring yet)

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

# 3. Celery (Windows requires solo pool)
celery -A app.core.celery_app worker --loglevel=info --pool=solo

# 4. Frontend
cd frontend
npm run dev
```

---

## Environment Variables

Copy `.env.example` to `.env` at the project root.

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async PostgreSQL URL |
| `SYNC_DATABASE_URL` | No | Auto-derived for Alembic |
| `REDIS_URL` | Yes | Redis for Celery |
| `JWT_SECRET` | Yes | Min 32 characters |
| `ANTHROPIC_API_KEY` | Yes* | Primary AI provider |
| `OPENAI_API_KEY` | No | Fallback AI provider |
| `ENVIRONMENT` | No | Default `development` |
| `ALLOWED_ORIGINS` | No | CORS origins |

Optional: `R2_*` for Cloudflare R2, `UPLOAD_DIR` for local storage.

---

## Known Limitations

1. **WeasyPrint on Windows** — PDF export needs GTK/Pango; use Docker backend image locally.
2. **Celery on Windows** — must use `--pool=solo`.
3. **Uvicorn `--reload` on Windows** — orphaned workers can hold port 8000; kill stale PIDs if routes 404 after code changes.
4. **SRS generation** — requires PRD status `approved`.
5. **Spec re-generation** — duplicate spec per task blocked; delete failed spec in DB to retry.

---

## Migration Chain (head)

```
fdfe482d01cb → c8c3d473f83f → f6ed1711e458 → 514c783416cf → 33a032d9a080
→ 7618b8bcd83b → c28834547b24 → a9f3e2b1c4d5 → 8f7cf3ad8389
→ c4d5e6f7a8b9 → d5e6f7a8b9c0
```

| Revision | Description |
|----------|-------------|
| `8f7cf3ad8389` | Tasks + task_specs + task_status_logs |
| `c4d5e6f7a8b9` | Knowledge base, decisions, notifications, screen perms |
| **`d5e6f7a8b9c0`** | Timestamp defaults on new tables (head) |

---

## Test Scripts

| Script | Purpose |
|--------|---------|
| `test_upload.py` | Requirement PDF upload |
| `test_prd.py` | PRD generation |
| `test_srs.py` | SRS generation |
| `test_spec.py` | Technical spec generation |
| `test_tasks.py` | Kanban task CRUD |
| `test_e2e_flow.py` | Full MVP pipeline |

---

## Git History (recent)

| Commit | Description |
|--------|-------------|
| `c2eb776` | Week 6 — project status, env config, Phase 1 backend + studio shell |
| `4488eff` | Week 5 — Kanban board + Technical Spec Engine |
