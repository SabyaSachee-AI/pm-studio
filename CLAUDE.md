# PM Studio — Development Standards

## Stack
Backend  : FastAPI Python async + SQLAlchemy 2 + Pydantic v2
Frontend : Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui
Database : PostgreSQL 16 + Redis 7
AI       : Anthropic Claude via Instructor library (structured output only)
Queue    : Celery + Redis
Files    : Cloudflare R2

## 3 Rules — Never Violate
1. ALL AI calls must use app/services/ai/base.py ai_call() only
   Never call Claude directly. Always pass Pydantic response_model.
   Never store raw markdown — only structured JSON.

2. ALL models must have: deleted_at = Column(TIMESTAMPTZ, nullable=True)
   Always soft delete. Never hard delete.

3. ALL heavy operations must use Celery tasks (AI gen, PDF export)
   Route returns task_id immediately. Never block API response.

## Backend Structure
app/api/v1/{domain}/router.py   — routes only
app/services/{domain}/          — business logic
app/models/{domain}.py          — SQLAlchemy models
app/schemas/{domain}.py         — Pydantic schemas
app/workers/{domain}_tasks.py   — Celery tasks

## Frontend Structure
app/(studio)/{feature}/page.tsx — pages
components/features/{feature}/  — components
lib/api.ts                      — API client

## Standards
Python  : async/await everywhere, type hints required
TypeScript : strict mode, no any type
Text    : sentence case always
Errors  : proper HTTP status codes with {"detail": "message"}
Secrets : always from os.getenv() — never hardcode
