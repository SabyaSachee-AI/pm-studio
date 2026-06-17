# PM Studio

AI-assisted planning platform for software studios — requirements, PRDs, SRS, architecture, Kanban specs, and knowledge base.

---

## Run locally with Docker (quick start)

Use Docker for **PostgreSQL** and **Redis**, and run the app on your machine for the fastest dev experience.

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Latest | Database and Redis |
| Python | 3.12+ | Backend API and Celery |
| Node.js | 20+ | Frontend dev server |

### First-time setup (once per machine)

1. **Clone the repo** and open a terminal in the project root (`pm-studio`).

2. **Create environment file:**

   ```powershell
   copy .env.example .env
   ```

   Edit `.env` and set at minimum:

   - `JWT_SECRET` — any random string, at least 32 characters
   - At least one AI provider key (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, etc.) — see `.env.example`

3. **Install backend dependencies:**

   ```powershell
   cd backend
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   cd ..
   ```

4. **Install frontend dependencies:**

   ```powershell
   cd frontend
   npm install
   cd ..
   ```

---

### Start the project

Open **four terminals** from the project root.

**Terminal 1 — Docker (database + Redis)**

```powershell
docker compose up -d postgres redis
```

Wait until both services are healthy (about 10–20 seconds on first run).

**Terminal 2 — Backend API**

```powershell
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Terminal 3 — Celery worker** (required for AI jobs and PDF export)

```powershell
cd backend
.\venv\Scripts\Activate.ps1
celery -A app.core.celery_app worker --loglevel=info --pool=solo
```

> On Windows, `--pool=solo` is required. On macOS/Linux you can omit it.

**Terminal 4 — Frontend**

```powershell
cd frontend
npm run dev
```

---

### Open the app

When all four terminals are running:

1. Open your browser and go to **[http://localhost:3000](http://localhost:3000)**
2. **Register** the first user at the login screen (fresh databases have no seed account).

   If you migrated an existing database dump, use your previous credentials.

**Other useful URLs**

| Service | URL |
|---------|-----|
| Frontend (studio UI) | [http://localhost:3000](http://localhost:3000) |
| Backend API docs | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Health check | [http://localhost:8000/health](http://localhost:8000/health) |

---

### Stop and close the project

Do these steps when you are done for the day:

1. **Stop the frontend** — in Terminal 4, press `Ctrl+C`
2. **Stop Celery** — in Terminal 3, press `Ctrl+C`
3. **Stop the backend** — in Terminal 2, press `Ctrl+C`
4. **Stop Docker services** — in Terminal 1 (or any terminal at project root):

   ```powershell
   docker compose down
   ```

   This stops PostgreSQL and Redis and frees ports `5432` and `6379`.

**Optional — remove database data**

To wipe the local database volume and start fresh next time:

```powershell
docker compose down -v
```

You will need to run `alembic upgrade head` again on the next start.

---

### Troubleshooting

| Problem | Fix |
|---------|-----|
| Port 5432 or 6379 already in use | Stop other Postgres/Redis instances, or change ports in `docker-compose.yml` |
| Backend cannot connect to DB | Ensure `docker compose up -d postgres redis` is running and `.env` uses `localhost` for `DATABASE_URL` and `REDIS_URL` |
| AI jobs stay pending | Confirm the Celery worker terminal is running with `--pool=solo` on Windows |
| `npm run dev` fails | Run `npm install` in `frontend/` |

---

## Full Docker stack (optional)

To run backend, Celery, and frontend inside Docker as well:

1. In `.env`, point services at Docker hostnames:

   ```
   DATABASE_URL=postgresql+asyncpg://pmstudio:devpassword123@postgres:5432/pmstudio
   SYNC_DATABASE_URL=postgresql://pmstudio:devpassword123@postgres:5432/pmstudio
   REDIS_URL=redis://redis:6379/0
   ```

2. Build and start all services:

   ```powershell
   docker compose up -d --build
   ```

3. Run migrations inside the backend container (first time only):

   ```powershell
   docker compose exec backend alembic upgrade head
   ```

4. Open **[http://localhost:3000](http://localhost:3000)**

5. Stop everything:

   ```powershell
   docker compose down
   ```

> For day-to-day development, the hybrid setup above (Docker for infra only) is recommended — it supports hot reload on backend and frontend.

---

## Stack

- **Backend:** FastAPI, SQLAlchemy 2, Pydantic v2, Celery, Alembic
- **Frontend:** Next.js 16 App Router, TypeScript, Tailwind, shadcn/ui
- **Data:** PostgreSQL 16, Redis 7
- **AI:** Anthropic Claude (structured output via Instructor)

## Project docs

- [DEPLOY.md](./DEPLOY.md) — fresh clone, VPS deploy, database migration, production env
- [PROJECT_STATUS.md](./PROJECT_STATUS.md) — feature status, API map, E2E verification
- [.cursorrules](./.cursorrules) — development standards for contributors

## License

Private / internal — see repository owner for terms.
