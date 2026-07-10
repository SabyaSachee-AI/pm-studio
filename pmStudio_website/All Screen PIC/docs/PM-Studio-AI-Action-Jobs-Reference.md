# PM Studio — AI Action Jobs Reference

Generated from PM Studio codebase audit.

## Pipeline overview

```
Upload PDF → Analyze → Synthesize feedback → PRD → SRS → Architecture (6 docs) → Kanban tasks → Per-task specs → Orchestration
```

Each step feeds the next. Weak output upstream propagates downstream.

---

## Master table — all 21 AI action jobs

| # | Screen | UI action button | Internal AI job (`task_type`) | What the job does | Why it is important | Ideal LLM specialty |
|---|--------|------------------|-------------------------------|-------------------|---------------------|------------------------|
| 1 | Requirements | Upload requirement PDF *(auto)* | `req_analyze` | Reads extracted PDF text; classifies gaps (client vs technical), risks, project type, auto-answers technical gaps | **Foundation of entire project** — wrong gaps → wrong PRD/SRS | Long-context document analysis + structured JSON extraction |
| 2 | Requirements | Regenerate analysis | `req_analyze` | Re-runs same analysis on existing PDF | Fixes bad first pass without re-upload | Long-context document analysis + structured JSON extraction |
| 3 | Requirements | Synthesize feedback | `req_synthesize` | Merges original requirement + client feedback doc into final draft (features, scope, decisions) | Locks scope before PRD; reduces client disputes | Cross-document synthesis + business requirements writing |
| 4 | Requirements | Rewrite analysis (PM instructions) | `req_synthesize` | Rewrites final draft per PM edit instructions | Iterates scope without new upload | Instruction-following rewrite + structured JSON |
| 5 | PRDs | Generate PRD | `prd_generate` | Builds full PRD: personas, features, user stories, acceptance criteria, metrics | **Commercial contract** with client; drives all downstream docs | Product/business narrative + nested structured JSON |
| 6 | PRDs | Regenerate PRD | `prd_generate` | Rebuilds PRD from requirement analysis | Recovery from weak generation | Product/business narrative + nested structured JSON |
| 7 | PRD detail | Rewrite PRD (PM comment) | `prd_rewrite` | Rewrites existing PRD sections per PM instructions | Refinement without full regen | Instruction-following rewrite + product writing |
| 8 | SRS | Generate SRS | `srs_generate` | IEEE-style SRS: FR-001…, NFRs, data entities, interfaces | **Legal/technical spec** — every later task links to FR numbers | Formal standards compliance (IEEE 830) + precise structured JSON |
| 9 | SRS | Regenerate SRS | `srs_generate` | Rebuilds SRS from PRD | Fixes missing FRs or weak NFRs | Formal standards compliance (IEEE 830) + precise structured JSON |
| 10 | SRS detail | Rewrite SRS (PM comment) | `srs_rewrite` | Rewrites SRS while preserving FR numbering | Surgical fixes; FR IDs must not break | Instruction-following rewrite + traceability preservation |
| 11 | Architecture | Generate Architecture Suite | `arch_generate` | Generates 6 docs: System, DB, API, Frontend, Security, UI/UX (large JSON + Mermaid) | **Build blueprint** for dev team; API paths, tables, auth model | Systems architecture reasoning + very long context + structured JSON |
| 12 | Architecture | Resume generation | `arch_generate` | Continues suite from first incomplete doc | Completes partial runs | Systems architecture reasoning + very long context + structured JSON |
| 13 | Architecture | Regenerate full suite | `arch_generate` | Clears all 6 docs and regenerates | Nuclear reset when suite is misaligned | Systems architecture reasoning + very long context + structured JSON |
| 14 | Architecture detail | Generate single doc (per tab) | `arch_generate` | One of 6 architecture documents | Targeted fix without burning quota on all 6 | Domain-specific architecture (DB/API/FE/security) |
| 15 | Architecture detail | Regenerate single doc | `arch_generate` | Replaces one doc | Refresh weak doc (e.g. API only) | Domain-specific architecture (DB/API/FE/security) |
| 16 | Architecture detail | Apply AI / AI-assist (with instructions) | `arch_generate` | Regenerates one doc incorporating PM instructions | Human-guided correction | Instruction-following + architecture reasoning |
| 17 | Tasks / Kanban | Generate tasks from SRS & Architecture | `module_extract` | Maps every FR to Kanban tasks with file paths, endpoints, tables from architecture | **FR → implementable work**; gaps here = missed features | Entity-to-structure mapping + software project planning |
| 18 | Tasks (fill gaps / replace modes) | Same button, different mode | `module_extract` | Only missing FRs, or wipe + regenerate tasks | Coverage repair without duplicating tasks | Entity-to-structure mapping + software project planning |
| 19 | Task detail panel | Generate technical spec | `spec_generate` | Full dev spec: files, steps, DB, API, security, Cursor prompt | **Direct input to Cursor/IDE** — most code-quality-critical job | Software engineering / coding-agent + zero-ambiguity spec writing |
| 20 | Task detail panel | Regenerate spec | `spec_generate` | Replaces failed or weak spec | Retry without new task | Software engineering / coding-agent + zero-ambiguity spec writing |
| 21 | Tasks (all done banner) | Generate project orchestration | `orchestration_generate` ⚠️ | Master build guide: file manifest, build order, Cursor workspace prompt | **Single paste-in prompt for whole project** | Cross-document aggregation + implementation sequencing |

---

## Buttons that look like AI but are NOT LLM jobs

| Screen | Button | What it actually does |
|--------|--------|------------------------|
| Requirements | Cost estimate | Local math from feature count — **no LLM** |
| PRD / SRS detail | Quality check | Rule-based checklist scoring — **no LLM** |
| PRD / SRS detail | Export PDF | Document export — **no LLM** |
| Architecture detail | Align suite | Deterministic cross-doc fixes — **no LLM** |
| Architecture / all docs | Save / Edit JSON | Manual edit — **no LLM** |
| Knowledge, Decisions, Clients, Projects | All actions | **No AI** in current codebase |

---

## LLM specialty types — quick reference

| Specialty type | Used for (job numbers) | What “good” looks like |
|----------------|------------------------|-------------------------|
| Long-context document analysis | #1, #2 | Reads full PDF; doesn’t miss sections |
| Structured JSON / schema adherence | All 21 jobs | Valid Pydantic output every time |
| Business / product narrative | #5, #6, #7 | Client-readable PRD, clear priorities |
| Formal spec / IEEE compliance | #8, #9, #10 | FR-001… numbering, measurable NFRs |
| Systems architecture reasoning | #11–#16 | Consistent auth, API, DB, monolith signals |
| Cross-document synthesis | #3, #4, #21 | Merges multiple sources without contradiction |
| Instruction-following rewrite | #4, #7, #10, #16 | Changes only what PM asked; preserves IDs |
| Entity-to-structure mapping | #17, #18 | Every FR → task + real file path |
| Software engineering / coding-agent | #19, #20 | Exact paths, functions, Cursor-ready prompts |
| Implementation sequencing | #21 | Correct build order across 50+ files |

---

## Free mode — configured primary models (live org)

| Screen | Primary model | Specialty fit |
|--------|---------------|---------------|
| Requirements | NVIDIA Nemotron 3 Super (FREE) | Long-context |
| PRD / SRS | OpenAI GPT-OSS 120B (FREE) | Structured JSON |
| Architecture | NVIDIA Nemotron Ultra 550B (FREE) | Largest reasoning / architecture |
| Tasks (specs) | Poolside Laguna M.1 (FREE) | Coding-agent |
| Tasks (extract) | Kimi K2.6 (FREE) | Structured extraction |

---

## Fallback behavior (free mode)

- Up to **14 models** per job, tried in order automatically.
- **Rate limit (429):** wait **1 second**, then next model.
- **Dead model / timeout (12 min on arch jobs) / API error:** skip immediately to next.
- **Providers:** OpenRouter (primary) → Groq → Together AI (if key configured).
- After all free models fail: **Anthropic Claude Sonnet** if key exists.
- **Per-screen model override** disables the entire fallback chain.

---

## Priority ranking for quality investment

| Priority | Jobs | Reason |
|----------|------|--------|
| 1 | #19–#20 Task spec | Coding-agent specialty — feeds Cursor directly |
| 2 | #8–#10 SRS | Formal spec + traceability specialty |
| 3 | #11–#16 Architecture | Systems architecture + long context |
| 4 | #17–#18 Module extract | Mapping specialty (FR coverage) |
| 5 | #5–#7 PRD | Product writing specialty |
| 6 | #1–#4 Requirements | Document analysis specialty |
| 7 | #21 Orchestration | Aggregation specialty *(broken in free mode today)* |

---

## Known gaps (codebase audit)

| Issue | Impact |
|-------|--------|
| `orchestration_generate` not in `FREE_ROUTING` | Job #21 fails unless Anthropic key exists |
| `arch_single_doc` routing exists but code always uses `arch_generate` | Same chain in practice — no practical difference |
| `quality_check` / `cost_estimate` in routing table | Defined but **never called** by UI |
| Per-screen model override | Disables 14-model fallback for that screen’s jobs |

---

**Total: 21 distinct AI action patterns** across 5 screens, driving the full PM Studio delivery pipeline from client PDF to developer-ready specs.
