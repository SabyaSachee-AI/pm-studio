# PM Studio — Detailed User Guide

This guide explains **every major screen**, **workflow step**, and **action button** in PM Studio. Each section uses the same pattern:

| Symbol | Meaning |
|--------|---------|
| **◀ Previous** | What you should have done before this step |
| **▶ Do now** | What to click or do on this screen |
| **⚙ What happens** | What PM Studio does in the background |
| **▶▶ Next** | Where to go after this step |

---

## The full pipeline (one picture)

```
Sign in
  → Admin setup (AI tier, GitHub, VPS)
  → Client → Project
  → Requirement (upload → gaps → feedback → finalize)
  → PRD (generate → review → quality → finalize)
  → SRS (generate → review → quality → finalize)
  → Architecture (6 docs → align → confirm → finalize)
  → Kanban (extract tasks → specs per task)
  → Traceability (fix gaps → coverage green)
  → Build (scaffold → generate → polish → tests → push → CI → UI test → deploy)
  → Live app on VPS
```

**Golden rule:** Each stage reads the **finalized** output of the stage before it. Skipping finalize causes weaker or blocked downstream steps.

---

## Sidebar — where everything lives

| Menu item | Purpose | Typical “next” after this screen |
|-----------|---------|----------------------------------|
| **Dashboard** | Overview stats, active AI jobs | Any screen with work in progress |
| **Clients** | Customer records | **Projects** |
| **Projects** | One product/initiative per client | **Requirements** |
| **Requirements** | Upload & analyze source document | **PRDs** |
| **PRDs** | Product requirements document | **SRS** |
| **SRS** | Technical requirements (FR-IDs, APIs) | **Architecture** |
| **Architecture** | 6 architecture documents + diagrams | **Kanban** |
| **Kanban** | Tasks + per-task dev specs | **Traceability** or **Build** |
| **Build** | Code factory (scaffold → deploy) | Iterate or new build |
| **Traceability** | Coverage matrix + gap fixes | **Build** |
| **Knowledge** | Saved snippets from PRD/SRS | Reference only |
| **Decisions** | Architecture decision log | Reference only |
| **Users** | Team accounts (admin) | — |
| **Permissions** | Screen access (admin) | — |
| **AI config** | Models, GitHub, VPS (admin) | Part A setup |

**Model selector:** Top-right on most AI screens — **Auto** uses the configured tier + fallback chain; or pick a specific provider/model for one action.

---

# PART A — One-time setup (Admin → AI config)

◀ **Previous:** Signed in as Studio Owner or Studio Admin  
▶▶ **Next:** Part B — create a client and project

---

## A1. AI tier & provider keys

**Screen:** Admin → AI config

| Button / control | What it does | Next step |
|------------------|--------------|-----------|
| **Free / Low cost / Premium** tier | Sets default model quality/cost for all AI | Add provider keys or use **Use all free** |
| **Use all free** | Enables free multi-provider chains | A2 GitHub |
| **Provider API keys** (per provider) | Save keys for OpenRouter, Gemini, etc. | Keys unlock models in the chain |
| **Per-screen model overrides** | Default model per screen (read-only display; users override on each page) | — |
| **Routing table** | Shows which models run for each task type | — |

⚙ Free tier walks a long fallback chain (Gemini → OpenRouter → …). Rate limits cause automatic model switching — jobs may take several minutes.

---

## A2. GitHub (Build code factory)

◀ **Previous:** AI tier chosen  
▶▶ **Next:** A3 VPS (if deploying) or Part B

| Field / button | What it does |
|----------------|--------------|
| **GitHub repo token** | PAT for pushing generated code & reading CI |
| **GitHub username / owner** | Account that owns created repos |
| **Save** | Encrypts token, runs permission checklist |
| **Verify** | Re-checks token against GitHub API |

**Required GitHub permissions:** Contents (R/W), Workflows (R/W), Actions (Read), Administration (R/W) for repo creation.

---

## A3. VPS deploy (Contabo) — optional

◀ **Previous:** GitHub connected  
▶▶ **Next:** Part B

| Field / button | What it does |
|----------------|--------------|
| **Host / IP** | Server IP (e.g. `185.185.80.147`) |
| **SSH user** | Login user (`sabya`, `root`, …) |
| **App path on VPS** | Folder where **generated app** is cloned (e.g. `/opt/apps/my-chatbot`) — use a **unique path per app** |
| **SSH private key** | Deploy key (encrypted in DB) |
| **Save** | Status becomes **● CONFIGURED** |

⚙ Used only when you click **Deploy to VPS** on a build — not for running PM Studio itself.

---

# PART B — Project pipeline (repeat per project)

---

## B1. Clients

◀ **Previous:** Part A complete  
▶▶ **Next:** B2 Projects

| Button | What it does |
|--------|--------------|
| **New client** | Create client/company record |
| **Edit / delete** (list row) | Manage existing client |

---

## B2. Projects

◀ **Previous:** Client exists  
▶▶ **Next:** B3 Requirements

| Button | What it does |
|--------|--------------|
| **New project** | Name, description, link to client |
| **Open project** | Opens project context for downstream screens |

---

## B3. Requirements — 5-step workflow

**Screen:** Requirements → open a requirement  
**Steps shown:** Analysis → Client Feedback → Review Draft → Confirm → Finalized

### Step 1 — Analysis

◀ **Previous:** Requirement document uploaded (PDF/DOCX/TXT)  
▶▶ **Next:** Step 2 (client feedback) or Step 3 (if no client gaps)

| Button | What it does | Next |
|--------|--------------|------|
| **Upload** (initial, on list page) | AI extracts text and analyzes gaps | Gap list appears |
| **Version history ▼** | View past analysis versions | — |
| **Download Client Feedback Form (DOCX)** | Gap questions for the client | Client fills form |
| **Choose file** (upload feedback) | Upload completed feedback `.docx/.pdf/.txt` | Auto-starts **Synthesizing feedback** |
| **← Back to gap analysis** (from step 3) | Return to step 1 view | — |

⚙ Upload feedback triggers AI synthesis → consolidated draft.

### Step 2 — Client Feedback (processing)

| UI | What it means |
|----|----------------|
| **AiStatusBar** (Queued / In progress) | Background job running |
| **Cancel** | Dismiss bar (does not stop server job) |
| **Try again** | Retry failed synthesis |

### Step 3 — Review Draft

◀ **Previous:** Draft synthesized from original + feedback  
▶▶ **Next:** Step 4 Confirm **or** rewrite again

| Button | What it does |
|--------|--------------|
| **✅ Confirm & Finalize** | Opens confirm modal → locks requirement |
| **🔄 Analyze Again** (with PM comment) | Rewrites draft from your instructions |
| Textarea **Not satisfied?** | Instructions for rewrite |

### Step 4 — Confirm (modal)

| Button | What it does |
|--------|--------------|
| **Cancel** | Back to review |
| **✅ Yes, Confirm** | Finalizes requirement |

### Step 5 — Finalized

◀ **Previous:** Confirmed  
▶▶ **Next:** **PRDs**

| Button | What it does |
|--------|--------------|
| **🖨️ Print Final Requirement** | Print formal sheet |
| **→ Generate PRD** | Links to PRDs for this project |

---

## B4. PRD — 5-step workflow

**Screen:** PRDs → open PRD  
**Steps:** Generate → Add Feedback → Review Draft → Confirm → Finalized

### Step 1 — Generate

◀ **Previous:** Requirement finalized  
▶▶ **Next:** Step 2 review

| Button | What it does |
|--------|--------------|
| **🔵 Generate PRD** | Starts AI generation (auto on open if new) |
| **AiStatusBar** | Shows progress; **Try again** on failure |

### Step 2 — Review (+ optional quality check)

| Button | What it does | Next |
|--------|--------------|------|
| **Run quality check** / **📊 PRD Quality Check** | Scores PRD (e.g. 50/100) with checklist | Step 3 |
| **✅ Confirm & Finalize →** (after quality) | Move to confirm modal | Step 4 |
| **💬 Request changes** + **Rewrite PRD** | AI rewrites from your comment | Stay in review |
| **🔗 Client review link → Copy** | Portal URL for client feedback | Share externally |
| **✏️ Edit PRD** | Manual field edit mode | Save edit |
| **📜 Change Log ▼** | Version history | — |
| **Actions ▾** | Edit / Regenerate / Delete | — |

### Step 3 — After quality check

Same as step 2 with quality score visible; **Confirm & Finalize** when satisfied.

### Step 4 — Confirm (modal)

| Button | What it does |
|--------|--------------|
| **✅ Yes, Confirm PRD** | Locks PRD for SRS generation |

### Step 5 — Finalized

◀ **Previous:** PRD confirmed  
▶▶ **Next:** **SRS**

| Button | What it does |
|--------|--------------|
| **💾 Save to KB** | Save to Knowledge base |
| **Export** (PDF/DOCX via actions) | Download document |
| **→ Generate SRS** (link) | Go to SRS |

**Actions ▾ menu (any time before delete):**
- **✏️ Edit** — manual edit page
- **🔄 Regenerate** — new AI generation
- **🗑 Delete** — remove PRD

---

## B5. SRS — same 5-step pattern as PRD

◀ **Previous:** PRD finalized  
▶▶ **Next:** **Architecture**

Buttons mirror PRD:

| Button | Notes |
|--------|-------|
| **🔵 Generate SRS** | From finalized PRD |
| **Quality check** | SRS completeness score |
| **Request changes / Rewrite** | AI revision |
| **Client review link → Copy** | Portal `/portal/srs/{id}` |
| **✏️ Edit SRS** | Manual edit |
| **Confirm & Finalize** | Locks for architecture & tasks |
| **💾 Save to KB** | Knowledge base |

⚙ Confirming SRS enables automatic task generation downstream.

---

## B6. Architecture — 5-step workflow

**Screen:** Architecture → open suite  
**Steps:** Generate → Review → Align → Confirm → Finalized  
**Documents (6):** System, Database, API, Frontend, Security, UI/UX

### Before generating (optional panels)

| Panel | Save button | Purpose |
|-------|-------------|---------|
| **Non-functional profile** | Save | Scale, availability, compliance, deploy target |
| **Capabilities** | Save | PWA, offline, voice, camera, public API |

Set these **before** Generate or Reassess.

### Header buttons

◀ **Previous:** SRS finalized  
▶▶ **Next:** Kanban or Traceability

| Button | When available | What it does |
|--------|----------------|--------------|
| **Download full architecture** | ≥1 doc complete | PDF export of suite |
| **Resume generation** | `can_resume` | Continue interrupted full generation |
| **Align suite canon** | ≥2 docs, idle | Sync terminology across docs |
| **Reassess suite (AI)** | All 6 docs complete | AI consistency pass |
| **Edit suite with AI** | All 6 complete | Bulk AI edit with instructions |
| **Confirm architecture** | Status `draft` | PM sign-off |
| **Finalize** | Status `confirmed` | **Required** before Build/Kanban |
| **Generate first missing** | Missing docs | Generate next empty doc |
| **Generate →** (per doc card) | Doc empty | Generate one document |
| **Reassess with AI** (per doc) | Doc exists | Re-run one doc |
| **Edit** | Doc exists | Open edit sheet |
| **Regenerate diagram** | Has diagram | Redraw architecture diagram |
| **Delete** | Doc exists | Clear that section |

### Per-document tab actions

| Button | What it does |
|--------|--------------|
| **Generate** | AI writes this document |
| **Save** (edit sheet) | Save manual edits |
| **Cancel** | Close editor |

---

## B7. Kanban (Tasks)

**Screen:** Kanban (`/tasks`) — pick project at top

◀ **Previous:** Architecture finalized  
▶▶ **Next:** Traceability (recommended) or Build

### Board overview bar

| Button | What it does | Next |
|--------|--------------|------|
| **Generate tasks** | First-time extract from PRD+SRS+Architecture | Board populates |
| **Regenerate tasks** | Re-extract (destructive — confirm) | New task set |
| **Reset board** | Clear all tasks | Empty board |
| **Traceability matrix** | Link to Traceability for this project | Gap fixes |

### Per-task panel (click a card)

| Button | What it does |
|--------|--------------|
| **Generate spec** | AI writes technical spec for this task |
| **Regenerate spec** | Replace spec content |
| **Copy summary** | Copy spec text to clipboard |
| **Download spec PDF** | Export single spec |
| **Move column** (drag) | backlog → assigned → in progress → in review → done |

### Bulk spec actions

| Button | What it does |
|--------|--------------|
| **Generate all specs** | Server job — one spec per task, resumable |
| **Download all specs (MD/PDF)** | Export every spec |

⚙ Tasks with **spec ready** are what the Build factory uses for code generation.

---

## B8. Traceability

**Screen:** Traceability — pick project

◀ **Previous:** Kanban tasks (and specs) exist  
▶▶ **Next:** **Build → New build**

### Top actions

| Button | What it does |
|--------|--------------|
| **Refresh** | Reload matrix |
| **Export matrix** | Download traceability data |
| **Resolve all gaps** | Runs full auto-fix pipeline in order |

### Gap resolution center (work top → bottom)

| Step | Button | What it fixes |
|------|--------|---------------|
| 1 | **Answer with AI** / manual answers | Requirement open questions |
| 2 | **Add missing to SRS** | PRD features not in SRS |
| 3 | **Solve gaps with AI** | Missing FR → new Kanban tasks |
| 4 | **Link orphaned tasks** | Tasks without requirement link |
| 5 | **Reconcile with architecture** | Tasks vs architecture entities |
| 6 | **Generate architecture** (if missing) | Incomplete arch docs |
| 7 | **Generate all specs** | Tasks without dev specs |

**Goal:** All gates green → safe to **Build**.

---

# PART C — Build (code factory)

**Screen:** Build → select project → **New build** or open existing

◀ **Previous:** Traceability mostly green; architecture finalized; tasks + specs exist  
▶▶ **Next:** Live app on VPS (or iterate)

### Build list page

| Button | What it does |
|--------|--------------|
| **New build** | Creates build record linked to project architecture |
| **Open build** | Enter workspace |

### Stage stepper (top of build workspace)

```
Scaffold → Generate code → Push → CI/QA → UI test → Deploy
```

Colors: 🟢 done · 🟡 active · 🔴 failed · ⚪ todo

---

## C1. Scaffold — button `1 Scaffold`

◀ **Previous:** New build created (`draft`)  
▶▶ **Next:** C2 Generate code

| Button | What it does |
|--------|--------------|
| **1 Scaffold** | AI creates repo skeleton: `package.json`, `docker-compose.yml`, `.env.example`, README, etc. |
| **Auto / model dropdown** | Optional model override |

⚙ PM Studio injects its own `ci.yml` and `deploy.yml` — you never edit those manually.

**Status bar:** Shows *Scaffolding repository* — may take several minutes on free models.

---

## C2. Generate code — button `2 Generate code`

◀ **Previous:** Status `scaffolded` (files in tree)  
▶▶ **Next:** C3 Polish and/or C5 Push

| Button | What it does |
|--------|--------------|
| **2 Generate code** | AI writes all task files in dependency order |
| **Resume** | Continue after interrupt (same build, keeps finished tasks) |

### File editor (click file in left tree)

| Button | What it does |
|--------|--------------|
| **Save** | Save manual edit to DB |
| **Download** | Download this file |
| **Regenerate task** | Re-run AI for this task only |
| **Apply AI** (+ instruction box) | Targeted AI edit on current file |

---

## C3. Polish (optional) — button `3 Polish (AI)`

◀ **Previous:** Code generated  
▶▶ **Next:** C4 or C5

| Button | What it does |
|--------|--------------|
| **3 Polish (AI)** | Confirm dialog: **OK** = all files, **Cancel** = critical files only (auth, models, API, security) |

---

## C4. Generate tests (optional) — button `4 Generate tests`

◀ **Previous:** Code ready  
▶▶ **Next:** C5 Push (run before push so CI includes tests)

| Button | What it does |
|--------|--------------|
| **4 Generate tests** | AI writes tests from acceptance criteria |

---

## C5. Push to GitHub — button `5 Push to GitHub`

◀ **Previous:** Code (and optional polish/tests)  
▶▶ **Next:** C6 CI (automatic)

| Button | What it does |
|--------|--------------|
| **5 Push to GitHub** | One commit to private repo; triggers CI |

⚙ Creates repo if needed; forces PM Studio workflows; removes stray workflow files.

---

## C6. CI / QA — mostly automatic

◀ **Previous:** Pushed  
▶▶ **Next:** C7 Local UI test (when green)

| UI / button | What it does |
|-------------|--------------|
| **CI/QA stage** (stepper) | Polls GitHub Actions |
| **Auto-repair bar** | On failure: AI reads logs, fixes, re-pushes (bounded retries) |
| **Fix with AI & re-push** | Manual repair trigger |
| **Open Actions on GitHub** | View CI logs |
| **View run logs** | Direct link to failed run |
| **Mark ready & continue** | Skip CI gate (token issues or manual override) |
| **6 Run CI / QA** | Re-check CI status manually |

**Outcomes:** passed → green · failed → fix & re-push · token error → fix Admin GitHub token

---

## C7. Local UI test — button `7 Local UI test`

◀ **Previous:** CI passed (or marked ready)  
▶▶ **Next:** C8 Deploy

| Button | What it does |
|--------|--------------|
| **7 Local UI test** | Opens checklist panel |
| **Copy** (on each command) | Copy clone/run/push commands |
| **Pass / Fail** per criterion | Record UI verification |
| **Save progress** | Save without signing off |
| **Sign off & mark ready** | Complete human UI gate |

**Important:** After editing on your machine → `git push` → **Sync from GitHub** in build header (GitHub wins).

---

## C8. Deploy to VPS — button `8 Deploy to VPS`

◀ **Previous:** UI test signed off; **Admin → VPS configured** (A3)  
▶▶ **Next:** 🎉 Live URL on build row

| Button | What it does |
|--------|--------------|
| **8 Deploy to VPS** | Prompts for **host port** (unique on shared VPS) |

⚙ Sets GitHub secrets (`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_PATH`, `APP_PORT`) and runs `deploy.yml` via SSH.

---

## Build — utility buttons (any time)

| Button | What it does |
|--------|--------------|
| **Sync from GitHub** | Pull repo → overwrite PM Studio files |
| **Download all** | Zip/bundle of generated codebase |
| **🗑 Delete** | Delete build and all generated files |
| **← Back** | Return to build list |

### AiStatusBar (during any build AI job)

| Control | What it does |
|---------|--------------|
| **Queued / In progress** | Job state (large jobs = minutes) |
| **Cancel** | Dismiss tracking (server may still run) |
| **After this:** hint | Tells you the next numbered button |

---

# PART D — Supporting screens

## Dashboard

◀ **Previous:** —  
**Shows:** Project counts, AI usage, active background jobs  
**Links:** Quick navigation to in-progress work  
▶▶ **Next:** Open the job’s screen (PRD, Build, etc.)

---

## Knowledge

◀ **Previous:** Saved from PRD/SRS **💾 Save to KB**  
**Shows:** Archived documents for reuse  
▶▶ **Next:** Reference when writing new projects

---

## Decisions

◀ **Previous:** —  
| Button | What it does |
|--------|--------------|
| **Log decision** form | Record ADR-style decisions (title, context, outcome) |

---

## Users & Permissions (admin)

| Screen | Purpose |
|--------|---------|
| **Users** | Create/edit team members, roles |
| **Permissions** | Which screens each role can view/edit |

---

# PART E — Shared UI patterns

## Workflow stepper (Requirements, PRD, SRS, Architecture)

- Click a **completed** step number to jump back and review.
- **Finalized** step = locked for downstream.

## `Actions ▾` menu (PRD, SRS, Architecture list)

| Item | Effect |
|------|--------|
| **Edit** | Manual edit mode |
| **Regenerate** | New AI run (may replace content) |
| **Delete** | Permanent delete with confirm |

## Model selector

| Choice | Behavior |
|--------|----------|
| **Auto** | Uses Admin tier + full fallback chain |
| **Specific model** | One-shot override for this action only |

## Client portal links (PRD / SRS)

- **Copy** shares read-only client review URL (`/portal/prd/...` or `/portal/srs/...`).
- Works on HTTP VPS after clipboard fix.

---

# Quick reference — button order on Build screen

| # | Button | Previous stage | Next stage |
|---|--------|----------------|------------|
| 1 | Scaffold | Build created | Generate code |
| 2 | Generate code | Scaffolded | Polish / Push |
| 3 | Polish (AI) | Code exists | Tests / Push |
| 4 | Generate tests | Code exists | Push |
| 5 | Push to GitHub | Code ready | CI (auto) |
| 6 | Run CI / QA | Pushed | UI test |
| 7 | Local UI test | CI green | Deploy |
| 8 | Deploy to VPS | UI signed off | Live app |

---

# Troubleshooting quick links

| Symptom | Go to |
|---------|-------|
| Copy button does nothing on HTTP | Hard refresh after deploy |
| Build stuck “Queued” long time | Wait (free models) or check `celery-build-worker` logs |
| CI 403 on Actions | Admin → GitHub token → add Actions: Read |
| Deploy fails | Admin → VPS config; unique port; SSH key on VPS |
| Tasks empty | Architecture must be **finalized**; then Kanban → Generate tasks |
| Gaps before build | Traceability → **Resolve all gaps** |

For VPS operations (PM Studio itself), see `deploy/contabo/VPS-OPS.md`.

---

*Generated from PM Studio codebase. Shorter overview: `docs/USER_MANUAL.md`.*
