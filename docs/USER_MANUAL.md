# PM Studio — Complete User Manual

PM Studio turns an idea into a **running, deployed web application**, fully driven by AI.
You move through a fixed pipeline; each stage uses the output of the stage before it.

**The big picture (the whole journey):**

```
Client → Project → Requirement → PRD → SRS → Architecture → Kanban tasks
      → Traceability → BUILD (Scaffold → Generate → Polish → Tests → Push
      → CI/QA → Local UI test → Deploy) → Live app
```

Every stage below tells you: **◀ Previous step**, **▶ What you do now**, **⚙ What happens**, and **▶▶ Next step**.

---

## PART A — One‑time setup (do this once)

You only need to do Part A the first time (or when a token/key changes).

### A0. Sign in
- ◀ Previous: none.
- ▶ Do: open PM Studio in the browser and log in (you are the **Studio Owner**).
- ▶▶ Next: A1.

### A1. Choose your AI tier — *Admin → AI config*
- ◀ Previous: signed in.
- ▶ Do: open **AI config** (sidebar). Pick a cost tier:
  - **Free** — uses free models with a deep fallback chain.
  - **Low‑cost** — cheap paid models.
  - **Premium** — best quality (Claude etc.).
- ⚙ What happens: every AI action (PRD, SRS, code, …) uses this tier unless you override the model per action.
- 💡 Tip: each screen has an **Auto / model dropdown** — “Auto” lets PM Studio pick the best available model.
- ▶▶ Next: A2.

### A2. Connect GitHub — *Admin → AI config → GitHub*
The Build factory pushes your generated code to GitHub (where CI runs).
- ◀ Previous: AI tier chosen.
- ▶ Do:
  1. On GitHub: **Settings → Developer settings → Fine‑grained tokens → Generate new token**.
  2. Give it a **long expiry**, repository access to your account, and these permissions:
     - **Contents: Read and write**
     - **Workflows: Read and write**
     - **Actions: Read**  ← needed so PM Studio can see CI results
     - **Administration: Read and write** (to create repos)
  3. In PM Studio: paste the token + your GitHub **username/owner** → **Save**.
- ⚙ What happens: the token is encrypted and saved. PM Studio **immediately verifies** it and shows a checklist:
  - ✓ Authentication · ✓ Contents · ✓ Workflows · ✓ Actions: Read
- 💡 If any item is ✕, fix that permission on GitHub and Save again. (A wrong/expired token = 401; missing Actions = 403.)
- ▶▶ Next: A3 (only if you will deploy).

### A3. Connect your VPS — *Admin → AI config → VPS* (optional, for deploy)
- ◀ Previous: GitHub connected.
- ▶ Do: enter your server **host, user, SSH key, and target path**. Save (SSH key is encrypted).
- ⚙ What happens: PM Studio can later deploy a build to this server automatically.
- ▶▶ Next: Part B (start building).

---

## PART B — Build a project (repeat per project)

### B1. Create a Client — *Clients*
- ◀ Previous: setup done (Part A).
- ▶ Do: **Clients → New client**. Enter the client/company name.
- ⚙ What happens: a client record is created to group projects.
- ▶▶ Next: B2 (create a project under this client).

### B2. Create a Project — *Projects*
- ◀ Previous: a client exists.
- ▶ Do: **Projects → New project**. Pick the client, give the project a name + short description.
- ⚙ What happens: an empty project is created — the container for everything below.
- ▶▶ Next: B3 (add the requirement).

### B3. Add the Requirement — *Requirements*
- ◀ Previous: a project exists.
- ▶ Do: open **Requirements**, choose your project, and **upload the requirement PDF** (or paste text).
- ⚙ What happens: AI reads the document and extracts structured requirements (functional + non‑functional).
- 💡 This is the **source of truth**. Better input here = better everything downstream.
- ▶▶ Next: B4 (generate the PRD).

### B4. Generate the PRD (Product Requirements) — *PRDs*
- ◀ Previous: requirement uploaded.
- ▶ Do: open **PRDs**, select the project, click **Generate PRD**. Review; edit with AI if needed; **finalize**.
- ⚙ What happens: AI writes a product spec (features, users, scope) from the requirement.
- 💡 Finalizing “locks” the PRD so the next stage uses a stable version.
- ▶▶ Next: B5 (generate the SRS).

### B5. Generate the SRS (Software Requirements) — *SRS*
- ◀ Previous: PRD finalized.
- ▶ Do: open **SRS**, **Generate**, review/edit, finalize.
- ⚙ What happens: AI turns the PRD into technical requirements (FR‑IDs, endpoints, data, NFRs).
- ▶▶ Next: B6 (architecture).

### B6. Generate the Architecture suite — *Architecture*
- ◀ Previous: SRS finalized.
- ▶ Do: open **Architecture**, **Generate full architecture** (6 documents + diagrams). Review each doc.
  - You can **edit a single doc**, run **Reassess with AI**, and check **consistency badges**.
  - Optional panels: **Non‑functional profile** (reliability/constraints) and **Capabilities** (PWA, voice, camera, public API) — off by default; turn on only if your project needs them.
- ⚙ What happens: AI designs the system (stack, components, data model, APIs, diagrams).
- ▶ Do (important): when satisfied, **Finalize** the architecture — required before building.
- ▶▶ Next: B7 (Kanban tasks).

### B7. Generate Kanban tasks + specs — *Kanban*
- ◀ Previous: architecture finalized.
- ▶ Do: open **Kanban**, generate tasks. Each task gets a **spec** (acceptance criteria, files).
- ⚙ What happens: AI breaks the whole project (functional + non‑functional + every architecture entity) into buildable tasks.
- ▶▶ Next: B8 (check for gaps).

### B8. Check coverage / fill gaps — *Traceability*
- ◀ Previous: tasks generated.
- ▶ Do: open **Traceability**. Look at the **completeness meters** (FR / endpoints / tables / NFRs). If anything is uncovered, click **Solve gaps with AI**.
- ⚙ What happens: AI adds the missing tasks so the build will be complete.
- 💡 Goal: high coverage on all meters before you build.
- ▶▶ Next: B9 (open the Build screen).

---

## PART C — The Build screen (the code factory)

Open **Build** in the sidebar and create/select a build. The top shows a **stage stepper**:

```
① Scaffold → ② Generate code → ③ Push → ④ CI/QA → ⑤ UI test → ⑥ Deploy
```
Each step lights up by real status: 🟢 done · 🟡 active/blocked · 🔴 failed · ⚪ to‑do.
The action buttons are numbered in the same order. Below is each one.

### C1. Scaffold the repo — button **1 Scaffold**
- ◀ Previous: traceability looks complete (Part B done).
- ▶ Do: click **Scaffold**.
- ⚙ What happens: AI creates the project skeleton (folders, package files, configs, `.env.example`, `docker-compose.yml`). PM Studio injects its **own CI/CD workflows** (you don’t manage those).
- ▶▶ Next: C2.

### C2. Generate the code — button **2 Generate code**
- ◀ Previous: scaffolded.
- ▶ Do: click **Generate code**. (Pick a model in the **Auto** dropdown first if you want.)
- ⚙ What happens: AI writes every file, task by task, in dependency order. It is **resumable** — if interrupted, click **Resume**. A static check auto‑fixes obvious syntax breakage.
- 💡 Click any file in the left tree to view/edit it in the **Monaco editor** (syntax highlighting, bracket colors). “Apply AI” edits a single file with an instruction.
- ▶▶ Next: C3 (optional) or C5 (push).

### C3. Polish the code (optional) — button **3 Polish (AI)**
- ◀ Previous: code generated.
- ▶ Do: click **Polish (AI)**. Choose **critical** (auth/models/API/security) or **all** files.
- ⚙ What happens: AI improves quality — error handling, validation, security, cleanup.
- ▶▶ Next: C4 (optional) or C5.

### C4. Generate tests (optional) — button **4 Generate tests**
- ◀ Previous: code generated (and maybe polished).
- ▶ Do: click **Generate tests**.
- ⚙ What happens: AI writes automated tests from your acceptance criteria. These run in CI after you push.
- 💡 Do this **before** Push so CI verifies them.
- ▶▶ Next: C5.

### C5. Push to GitHub — button **5 Push to GitHub**
- ◀ Previous: code (and optionally polish/tests) ready.
- ▶ Do: click **Push to GitHub**.
- ⚙ What happens: all files are pushed in one commit to a private repo. PM Studio **forces its own `ci.yml`/`deploy.yml`** (so CI is always runnable) and **removes any stray workflow files**. The push automatically **triggers CI**.
- ▶▶ Next: C6 (CI runs automatically).

### C6. CI / QA — automatic (no button)
- ◀ Previous: pushed.
- ▶ Do: watch the **CI/QA** stage + the explainer banner. PM Studio polls GitHub Actions.
- ⚙ What happens: GitHub runs the workflow (`backend` compiles + tests, `frontend` installs + lint + build, `smoke` boots the stack and curls health).
- Possible outcomes (the banner tells you exactly which + what to do):
  - 🟢 **passed** → stage turns green → go to C7.
  - 🔴 **failed** → click **Fix with AI & re‑push** (AI reads the logs, fixes code, re‑pushes). Repeat until green.
  - 🟡 **blocked (token)** → fix the GitHub token (A2), or click **Mark ready** to continue.
- ▶▶ Next: C7.

### C7. Local UI test — button **6 Local UI test**
- ◀ Previous: CI green (or you marked it ready).
- ▶ Do: click **Local UI test**. A panel shows a **numbered guide** (each line has a **Copy** button):
  1. **Get the code** — `git clone <repo> && cd <name>`
  2. **Configure env** — `cp .env.example .env`
  3. **Run locally** — `docker compose up --build` (open the URL it prints)
  4. **Made fixes? Push** — `git add -A && git commit -m "..." && git push`
  5. **Pull back** — click **Sync from GitHub** (top) to bring your edits into PM Studio
- ⚙ What happens: you run the app yourself, tick each acceptance criterion **Pass/Fail**, and **Sign off**.
- 💡 Conflict rule: **GitHub wins** — Sync overwrites PM Studio’s copy with the repo.
- ▶▶ Next: C8.

### C8. Deploy to VPS — button **7 Deploy to VPS**
- ◀ Previous: app verified locally; VPS configured (A3).
- ▶ Do: click **Deploy to VPS**. Enter a **unique host port** for this app (not one already in use).
- ⚙ What happens: PM Studio sets the deploy secrets and triggers the deploy workflow — it SSHes to your server, clones/pulls the repo, brings the stack up on your port, **health‑checks**, and **rolls back** if it doesn’t come up. The live URL appears on the GitHub row.
- ▶▶ Next: 🎉 your app is live. Iterate by editing → Push → CI → Deploy again.

### Utility buttons (any time)
- **Sync from GitHub** — pull repo changes back into PM Studio (GitHub wins).
- **Download all** — download the whole codebase as one file.
- **Mark ready** — manual override if CI can’t be read.
- **🗑 Delete** — remove the build.

---

## PART D — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| CI banner: **token missing Actions: Read (403)** | Token lacks Actions read | A2 → add **Actions: Read**, Save, re‑verify |
| CI banner: **token invalid/expired (401)** | Token expired/revoked | A2 → create a new token, Save |
| CI fails: **“lock file not found” / npm ci** | An old build had a model‑made workflow | Just **Push again** — PM Studio now forces its own workflow and purges strays |
| Build buttons/CI stuck after deploy | Celery **workers** not rebuilt | On the server: `docker compose -f docker-compose.contabo.yml up -d --build` (rebuilds **all**, incl. workers) |
| “Generating code … QUEUED” won’t clear | Stale finished job | It auto‑clears on a finished build or after ~75s; refresh |
| Build tasks never run | No worker on the **build** queue | Ensure `celery-build-worker` is **Up** |

### Golden rules
1. **On the server, always use** `docker compose -f docker-compose.contabo.yml …`.
2. After pulling new code, rebuild **all** services (backend + both celery workers + frontend), then **Push again** — don’t just *re‑run* an old CI run (re‑running can’t change the workflow file).
3. Finalize each stage (PRD → SRS → Architecture) before moving on.
4. Keep your GitHub token valid (long expiry, correct permissions).

---

## Quick reference — the whole flow on one line

```
Setup: AI tier → GitHub token (Contents+Workflows+Actions) → VPS
Build: Client → Project → Requirement → PRD → SRS → Architecture(finalize)
       → Kanban → Traceability(solve gaps)
       → Scaffold → Generate → [Polish] → [Tests] → Push → CI green?
            yes → Local UI test → Deploy
            no  → Fix with AI & re‑push (repeat)
```
