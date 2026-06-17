# PM Studio — Deploy & fresh clone guide

Step-by-step instructions for running PM Studio on a **new folder**, **new machine**, or **VPS**.

**Repository:** https://github.com/SabyaSachee-AI/pm-studio

---

## How the app is structured

PM Studio needs **five running pieces** to work fully:

```mermaid
flowchart LR
  Browser["Browser :3000"] --> Frontend["Next.js frontend"]
  Frontend --> API["FastAPI :8000"]
  API --> PG["PostgreSQL :5432"]
  API --> Redis["Redis :6379"]
  Celery["Celery worker"] --> Redis
  Celery --> PG
  Celery --> AI["AI providers"]
```

| Service | Role | If it is missing |
|---------|------|------------------|
| PostgreSQL | Stores users, projects, PRDs, SRS, architecture, tasks | App cannot start |
| Redis | Celery job queue | AI jobs never run |
| FastAPI (backend) | REST API, auth, business logic | No API |
| Celery worker | PRD/SRS/architecture generation, PDF export | Jobs stay "pending" forever |
| Next.js (frontend) | Studio UI + client portal | No web UI |

**Recommended local setup:** Docker runs Postgres + Redis only; you run backend, Celery, and frontend on the host for fast hot reload.

---

## Part 0 — What git gives you vs what you must supply

### Included in the repository

- All application source code (backend + frontend)
- Alembic migrations (`backend/app/services/migrations/versions/`)
- `docker-compose.yml`, Dockerfiles, `.env.example`
- `package-lock.json` for reproducible `npm ci`

### Not included (you must create or migrate)

| Item | Why it matters |
|------|----------------|
| `.env` | Secrets are gitignored — copy from `.env.example` |
| `backend/venv/` | Python virtualenv — create with `python -m venv` |
| `frontend/node_modules/` | Install with `npm install` |
| PostgreSQL **data** | Your projects, PRDs, SRS, architecture live here |
| `backend/uploads/` | Uploaded requirement PDFs and export files |
| Login account | Fresh DB has **no seed user** — register on first visit |

**Important:** Cloning the repo copies the **code**, not your ChatBOT_CustomData project or any other studio data. Use [Part 2](#part-2--migrate-data-to-another-machine) to move data.

---

## Part 1 — Fresh clone (local development)

Use this when you clone into a new folder on your PC or laptop.

### Step 1.1 — Install prerequisites

| Tool | Version | How to verify |
|------|---------|---------------|
| Git | Any recent | `git --version` |
| Docker Desktop | Latest | `docker compose version` |
| Python | 3.12+ | `python --version` |
| Node.js | 20+ | `node --version` |

**Why:** Docker provides Postgres 16 and Redis 7 without installing them natively. Python runs the API and Celery. Node runs the Next.js dev server.

---

### Step 1.2 — Clone the repository

**Windows (PowerShell):**

```powershell
cd F:\knowledgebase\ProjectPreparation\PMS
git clone https://github.com/SabyaSachee-AI/pm-studio.git pm-studio-new
cd pm-studio-new
```

**Linux / macOS:**

```bash
git clone https://github.com/SabyaSachee-AI/pm-studio.git
cd pm-studio
```

**What this does:** Downloads the exact code that is on GitHub `main`.

**Verify:**

```bash
git log -1 --oneline
```

You should see a recent commit (e.g. `c401cf2` or newer).

---

### Step 1.3 — Create `.env` from the template

**Windows:**

```powershell
copy .env.example .env
notepad .env
```

**Linux / macOS:**

```bash
cp .env.example .env
nano .env
```

**What this does:** The app reads configuration from `.env` at the **project root** (not inside `backend/`). See `backend/app/core/config.py`.

**Minimum values to set:**

| Variable | Example | Explanation |
|----------|---------|-------------|
| `JWT_SECRET` | 64 random characters | Signs login tokens; must be ≥ 32 chars |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Primary Claude provider (optional if others set) |
| `OPENROUTER_API_KEY` | `sk-or-...` | Free-tier routing (optional) |
| `GEMINI_API_KEY` | `AI...` | Google Gemini (optional) |

Leave `DATABASE_URL` and `REDIS_URL` as `localhost` for local hybrid setup.

**Optional:** Add more keys from `.env.example`. You can also configure providers later in **Studio → Admin → AI config** (stored in the database).

---

### Step 1.4 — Start PostgreSQL and Redis (Docker)

From the **project root**:

```bash
docker compose up -d postgres redis
```

**What this does:**

- Starts Postgres on port `5432` with database `pmstudio`, user `pmstudio`, password `devpassword123` (see `docker-compose.yml`)
- Starts Redis on port `6379`
- Creates a Docker volume `pg_data` so data survives container restarts

**Verify (wait 10–20 seconds on first run):**

```bash
docker compose ps
```

Both `postgres` and `redis` should show `healthy`.

**Test Postgres:**

```bash
docker compose exec postgres psql -U pmstudio -d pmstudio -c "SELECT 1;"
```

Expected: a row with `1`.

---

### Step 1.5 — Backend: virtualenv, dependencies, migrations

Open **Terminal A**. All commands from `backend/`:

```powershell
cd backend
python -m venv venv
```

**Activate the virtualenv:**

| OS | Command |
|----|---------|
| Windows PowerShell | `.\venv\Scripts\Activate.ps1` |
| Windows CMD | `venv\Scripts\activate.bat` |
| Linux / macOS | `source venv/bin/activate` |

**Install Python packages:**

```bash
pip install -r requirements.txt
```

**What this does:** Installs FastAPI, SQLAlchemy, Celery, Anthropic/Instructor, WeasyPrint (PDF), PyMuPDF, etc.

**Run database migrations:**

```bash
alembic upgrade head
```

**What this does:** Creates all tables (users, projects, requirements, PRDs, SRS, architecture, tasks, …) in empty Postgres. Safe to run multiple times — only applies pending migrations.

**Expected output:** Lines like `Running upgrade ... -> ..., <revision>`

**Start the API:**

```bash
uvicorn app.main:app --reload --port 8000
```

**Verify:** Open http://localhost:8000/health — should return JSON with status OK.

**API docs:** http://localhost:8000/docs

---

### Step 1.6 — Celery worker (required for AI)

Open **Terminal B**. Same `backend/` folder, venv activated:

**Windows (required flag):**

```bash
celery -A app.core.celery_app worker --loglevel=info --pool=solo
```

**Linux / macOS:**

```bash
celery -A app.core.celery_app worker --loglevel=info
```

**What this does:** Listens on Redis for background jobs:

- Requirement analysis, PRD/SRS generation
- Architecture suite (6 documents)
- Module extraction, spec generation
- PDF export

**Verify:** Log line `celery@<hostname> ready.` and task list including `prd.generate`, `srs.generate`, `architecture.generate`, etc.

**If Celery is not running:** UI shows "Generating…" forever and jobs stay pending.

---

### Step 1.7 — Frontend dev server

Open **Terminal C**:

```bash
cd frontend
npm install
npm run dev
```

**What this does:** Installs Next.js 16 + React 19 + Mermaid, etc., then starts dev server with hot reload.

**Verify:** http://localhost:3000 loads the login page.

**API URL:** Defaults to `http://localhost:8000/api/v1` (see `frontend/lib/api.ts`). Override with `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

### Step 1.8 — First login and smoke test

1. Open http://localhost:3000
2. **Register** a new user (fresh database has no default account)
3. Create a client → project → upload a requirement PDF
4. Confirm Celery logs show `requirements.process_upload` when analysis runs
5. Walk the pipeline: requirement → PRD → SRS → architecture

**Success criteria:**

| Check | Pass? |
|-------|-------|
| `/health` returns OK | |
| Login works | |
| Requirement upload triggers Celery task | |
| PRD generation completes (not stuck pending) | |

---

### Step 1.9 — Stop local development

1. `Ctrl+C` in frontend terminal
2. `Ctrl+C` in Celery terminal
3. `Ctrl+C` in backend terminal
4. From project root:

```bash
docker compose down
```

To **wipe database** (start completely fresh next time):

```bash
docker compose down -v
```

Then run `alembic upgrade head` again on next start.

---

## Part 2 — Migrate data to another machine

Use this to move your **existing studio work** (projects, PRDs, AI config in DB) to a new PC or VPS.

### Step 2.1 — Export database on the source machine

Ensure Postgres is running:

```bash
docker compose up -d postgres
```

Create a compressed backup:

```bash
docker compose exec postgres pg_dump -U pmstudio -Fc pmstudio > pmstudio_backup.dump
```

**What this does:** Dumps the entire `pmstudio` database (all tables and data) into one file.

**Verify:** File exists and size > 0 bytes:

```bash
ls -lh pmstudio_backup.dump
```

---

### Step 2.2 — Copy files to the target machine

Transfer via SCP, USB, or cloud storage:

| File / folder | Required? |
|---------------|-----------|
| `pmstudio_backup.dump` | Yes, for data |
| `.env` | Recommended (secrets; do not commit to git) |
| `backend/uploads/` | Optional (original PDFs, exports) |

**Security:** Treat `.env` and the dump as confidential.

---

### Step 2.3 — Restore on the target machine

1. Complete [Part 1](#part-1--fresh-clone-local-development) through **Step 1.4** (clone, `.env`, Docker postgres/redis)
2. **Before** using the app, restore:

```bash
docker compose exec -T postgres pg_restore -U pmstudio -d pmstudio --clean --if-exists < pmstudio_backup.dump
```

**What this does:** Replaces target DB content with your backup. `--clean` drops existing objects first.

3. Copy `backend/uploads/` into the new clone if you exported it
4. Start backend + Celery + frontend as in Part 1

**Verify:** Log in with your **existing** credentials; projects and PRDs should appear.

---

### Step 2.4 — What migrates automatically vs manually

| Data | In DB dump? | In uploads folder? |
|------|-------------|------------------|
| Users, orgs | Yes | — |
| Projects, clients | Yes | — |
| Requirements metadata | Yes | PDF file in `uploads/` |
| PRD / SRS / architecture JSON | Yes | — |
| Admin AI config (providers, routing) | Yes | — |
| Exported PDF files | — | Yes (`uploads/exports/`) |

---

## Part 3 — VPS production (full Docker stack)

For Ubuntu 22.04+ (or similar) with Docker and Docker Compose v2.

### Step 3.1 — Prepare the server

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl
# Install Docker: https://docs.docker.com/engine/install/ubuntu/
sudo usermod -aG docker $USER
# Log out and back in for group to apply
```

**Firewall (UFW example):**

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**Do not** open ports `5432` or `6379` to the public internet.

---

### Step 3.2 — Clone and configure production `.env`

```bash
cd /opt
sudo git clone https://github.com/SabyaSachee-AI/pm-studio.git
sudo chown -R $USER:$USER pm-studio
cd pm-studio
cp .env.example .env
nano .env
```

**Critical change for Docker:** use **service names** as hosts, not `localhost`:

```env
DATABASE_URL=postgresql+asyncpg://pmstudio:YOUR_STRONG_PASSWORD@postgres:5432/pmstudio
SYNC_DATABASE_URL=postgresql://pmstudio:YOUR_STRONG_PASSWORD@postgres:5432/pmstudio
REDIS_URL=redis://redis:6379/0

JWT_SECRET=replace-with-64-plus-random-characters-generated-securely
ENVIRONMENT=production
ALLOWED_ORIGINS=https://studio.yourdomain.com

ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
GEMINI_API_KEY=...
```

**Also edit `docker-compose.yml`:**

```yaml
environment:
  POSTGRES_PASSWORD: YOUR_STRONG_PASSWORD
```

Password in `.env` URLs must match `POSTGRES_PASSWORD`.

---

### Step 3.3 — Bind services to localhost only

Edit `docker-compose.yml` ports so nginx handles public traffic:

```yaml
backend:
  ports:
    - "127.0.0.1:8000:8000"

frontend:
  ports:
    - "127.0.0.1:3000:3000"

postgres:
  ports: []   # remove public 5432 exposure

redis:
  ports: []   # remove public 6379 exposure
```

**Why:** Only nginx on 443 should be reachable from the internet.

---

### Step 3.4 — Set frontend API URL and build

Edit `docker-compose.yml` **before** build:

```yaml
frontend:
  environment:
    NEXT_PUBLIC_API_URL: https://studio.yourdomain.com/api/v1
```

**Why:** Next.js bakes this at **build time**. Wrong URL = browser calls wrong host.

**Build and start all services:**

```bash
docker compose up -d --build
```

**First-time migrations:**

```bash
docker compose exec backend alembic upgrade head
```

**Verify:**

```bash
curl -s http://127.0.0.1:8000/health
docker compose ps
docker compose logs celery-worker --tail 20
```

---

### Step 3.5 — nginx reverse proxy + HTTPS

Install nginx and Certbot:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/pm-studio`:

```nginx
server {
    listen 80;
    server_name studio.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name studio.yourdomain.com;

    # Certbot will add ssl_certificate lines:
    # ssl_certificate /etc/letsencrypt/live/studio.yourdomain.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/studio.yourdomain.com/privkey.pem;

    client_max_body_size 50M;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and obtain certificate:

```bash
sudo ln -s /etc/nginx/sites-available/pm-studio /etc/nginx/sites-enabled/
sudo nginx -t
sudo certbot --nginx -d studio.yourdomain.com
sudo systemctl reload nginx
```

**Verify:** https://studio.yourdomain.com loads; register user; run a small AI job.

---

### Step 3.6 — Production deploy after `git pull`

```bash
cd /opt/pm-studio
git pull origin main
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

**Always restart Celery** after backend code changes (included in `docker compose up`).

---

## Part 4 — VPS hybrid (Docker DB + native processes)

Use when you want Docker only for Postgres/Redis but run Python/Node directly (similar to local dev).

### Step 4.1 — Infrastructure only

```bash
docker compose up -d postgres redis
```

Use `localhost` in `.env` (same as Part 1).

### Step 4.2 — Backend as a systemd service

Example `/etc/systemd/system/pm-studio-api.service`:

```ini
[Unit]
Description=PM Studio FastAPI
After=docker.service
Requires=docker.service

[Service]
User=www-data
WorkingDirectory=/opt/pm-studio/backend
EnvironmentFile=/opt/pm-studio/.env
ExecStart=/opt/pm-studio/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### Step 4.3 — Celery as a systemd service

`/etc/systemd/system/pm-studio-celery.service`:

```ini
[Unit]
Description=PM Studio Celery Worker
After=pm-studio-api.service

[Service]
User=www-data
WorkingDirectory=/opt/pm-studio/backend
EnvironmentFile=/opt/pm-studio/.env
ExecStart=/opt/pm-studio/backend/venv/bin/celery -A app.core.celery_app worker --loglevel=info --concurrency=2
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pm-studio-api pm-studio-celery
```

### Step 4.4 — Frontend production build

```bash
cd /opt/pm-studio/frontend
echo "NEXT_PUBLIC_API_URL=https://studio.yourdomain.com/api/v1" > .env.local
npm ci
npm run build
npm run start
```

Or use a systemd unit with `ExecStart=/usr/bin/npm run start` on port 3000.

Point nginx at `127.0.0.1:3000` and `127.0.0.1:8000` as in Part 3.5.

---

## Part 5 — Environment variables (full reference)

File location: **project root** `.env` (loaded by `backend/app/core/config.py`).

### Required

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async Postgres URL for FastAPI (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Celery broker (`redis://...`) |
| `JWT_SECRET` | Auth token signing (min 32 characters) |

### Auto-derived if omitted

| Variable | Behavior |
|----------|----------|
| `SYNC_DATABASE_URL` | Derived from `DATABASE_URL` by replacing `+asyncpg` |

### AI providers (at least one recommended)

Set in `.env` and/or **Admin → AI config** in the UI (DB overrides).

| Variable | Provider |
|----------|----------|
| `ANTHROPIC_API_KEY` | Claude (primary structured output) |
| `OPENAI_API_KEY` | OpenAI fallback |
| `OPENROUTER_API_KEY` | OpenRouter free-tier routing |
| `GROQ_API_KEY` | Groq |
| `GEMINI_API_KEY` | Google Gemini |
| `TOGETHER_API_KEY` | Together AI |
| `CEREBRAS_API_KEY` | Cerebras |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `SAMBANOVA_API_KEY` | SambaNova |
| `NVIDIA_API_KEY` | NVIDIA NIM |
| `HUGGINGFACE_API_KEY` | Hugging Face inference |
| `AIMLAPI_API_KEY` | AIML API |
| `SILICONFLOW_API_KEY` | SiliconFlow |
| `ALIBABA_API_KEY` | Alibaba DashScope |
| `GITHUB_API_KEY` | GitHub Models |

### Application

| Variable | Default | Production notes |
|----------|---------|----------------|
| `ENVIRONMENT` | `development` | Set `production` on VPS |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated HTTPS URLs |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Optional tuning |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Optional tuning |

### File storage

| Variable | Purpose |
|----------|---------|
| `UPLOAD_DIR` | Local uploads path (default `uploads`) |
| `R2_*` | Cloudflare R2 — optional; omit to use local disk |

### Frontend only

| Variable | When |
|----------|------|
| `NEXT_PUBLIC_API_URL` | Build time — Docker or `frontend/.env.local` |

### Hostname cheat sheet

| Setup | `DATABASE_URL` host | `REDIS_URL` host |
|-------|---------------------|------------------|
| Local hybrid (Docker infra) | `localhost` | `localhost` |
| Full Docker Compose | `postgres` | `redis` |

---

## Part 6 — Day-to-day operations

### After pulling new code

```bash
git pull origin main
cd backend && alembic upgrade head
# Restart API + Celery (or docker compose up -d --build)
```

### Backup database

```bash
docker compose exec postgres pg_dump -U pmstudio -Fc pmstudio > backup_$(date +%Y%m%d).dump
```

### View logs

```bash
# Docker
docker compose logs -f backend celery-worker

# systemd
sudo journalctl -u pm-studio-api -f
sudo journalctl -u pm-studio-celery -f
```

### Useful URLs (local)

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Studio UI |
| http://localhost:8000/docs | Swagger API |
| http://localhost:8000/health | Health check |

---

## Part 7 — Troubleshooting

### Backend won't start

| Symptom | Cause | Fix |
|---------|-------|-----|
| `JWT_SECRET` validation error | Secret too short | Use 32+ characters |
| Connection refused to Postgres | Docker not running | `docker compose up -d postgres` |
| `password authentication failed` | `.env` password ≠ `docker-compose.yml` | Align both |

### AI jobs stuck on "Generating…"

| Cause | Fix |
|-------|-----|
| Celery not running | Start worker (Part 1.6) |
| Redis down | `docker compose up -d redis` |
| No AI API keys | Set keys in `.env` or Admin → AI config |
| Stale Celery code | Restart worker after `git pull` |

### CORS errors in browser

Add your frontend URL to `ALLOWED_ORIGINS` in `.env` and restart backend:

```env
ALLOWED_ORIGINS=https://studio.yourdomain.com,http://localhost:3000
```

### Frontend calls wrong API

Set `NEXT_PUBLIC_API_URL` and **rebuild** frontend (`npm run build` or `docker compose build frontend`).

### Empty project list after clone

Expected on fresh DB. Restore backup (Part 2) or create new project.

### Windows Celery freezes

Always use `--pool=solo`.

### PDF export fails

Requires Celery + WeasyPrint system libraries. Docker backend image includes these; on bare Windows, prefer Docker for PDF jobs or install WeasyPrint dependencies.

### `alembic upgrade head` fails

- Run from `backend/` directory with venv active
- Ensure Postgres is healthy
- Check `DATABASE_URL` / `SYNC_DATABASE_URL` match running Postgres

---

## Quick decision guide

| Goal | Follow |
|------|--------|
| New dev machine, empty data | [Part 1](#part-1--fresh-clone-local-development) |
| Move existing projects to new PC | [Part 2](#part-2--migrate-data-to-another-machine) + Part 1 |
| Public VPS with HTTPS | [Part 3](#part-3--vps-production-full-docker-stack) |
| VPS with manual process control | [Part 4](#part-4--vps-hybrid-docker-db--native-processes) |

---

## Related docs

- [README.md](./README.md) — short local quick start
- [PROJECT_STATUS.md](./PROJECT_STATUS.md) — feature map and API overview
- [.env.example](./.env.example) — all environment variables
- [.cursorrules](./.cursorrules) — development standards
