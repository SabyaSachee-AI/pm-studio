"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Project } from "@/lib/api";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { useAiJob } from "@/lib/hooks/useAiJob";

// ─── types ────────────────────────────────────────────────────────────────────

interface Gap { category: string; description: string; question?: string; auto_answer?: string }

interface PRDFeature {
  id: string; title: string; description: string; priority: string; complexity?: string;
}

interface SRSFR {
  id: string;         // normalised = fr_number, e.g. "FR-001"
  fr_number: string;
  title: string; description: string; priority: string;
  inputs?: string; processing?: string; outputs?: string;
  linked_feature?: string | null;
}

interface TaskSpecPayload { id: string; status: string; content_json?: Record<string, unknown> | null }

interface KanbanTask {
  id: string; title: string; description?: string | null;
  status: string; task_type: string; priority: string;
  linked_fr?: string | null; fr_references: string[];
  module_name?: string | null;
  suggested_file?: string | null; suggested_endpoint?: string | null; suggested_table?: string | null;
  spec?: TaskSpecPayload | null;
}

interface ArchDocInfo { status: string; has_content: boolean }

interface TraceabilityData {
  project_id: string; project_name: string;
  requirement: { id: string; original_filename: string; status: string; gaps: Gap[] } | null;
  prd: { id: string; status: string; version: number; features: PRDFeature[] } | null;
  srs: { id: string; status: string; version: number; functional_requirements: SRSFR[] } | null;
  architecture: {
    id: string; status: string; version: number;
    docs: Record<string, ArchDocInfo>;
  } | null;
  tasks: KanbanTask[];
  coverage: { total_frs: number; covered_frs: number; missing_frs: string[]; coverage_pct: number };
  full_coverage?: {
    fr: { total_frs: number; covered_frs: number; coverage_pct: number };
    endpoints: Meter;
    tables: Meter;
    nfrs: Meter;
  };
  plan_drift?: { count: number; items: { task_id: string; title: string; reason: string }[] };
}

interface Meter { total: number; covered: number; missing: string[]; pct: number }

// ─── helpers ──────────────────────────────────────────────────────────────────

const PRIORITY_COLOR: Record<string, string> = {
  critical: "border-red-900/40 bg-red-950/20 text-red-400",
  high:     "border-orange-900/40 bg-orange-950/20 text-orange-400",
  medium:   "border-yellow-900/40 bg-yellow-950/20 text-yellow-400",
  low:      "border-gray-700/40 bg-gray-800/20 text-gray-500",
  must:     "border-red-900/40 bg-red-950/20 text-red-400",
};

const TASK_STATUS_COLOR: Record<string, string> = {
  backlog:     "border-gray-700 bg-gray-800 text-gray-400",
  assigned:    "border-indigo-800/40 bg-indigo-950/20 text-indigo-400",
  in_progress: "border-amber-800/40 bg-amber-950/20 text-amber-400",
  in_review:   "border-purple-800/40 bg-purple-950/20 text-purple-400",
  done:        "border-teal-800/40 bg-teal-950/20 text-teal-400",
};

const ARCH_DOCS = [
  { key: "system_arch", label: "System arch",  icon: "ti-sitemap" },
  { key: "database",    label: "Database",      icon: "ti-database" },
  { key: "api",         label: "API spec",      icon: "ti-api" },
  { key: "frontend",    label: "Frontend",      icon: "ti-device-desktop" },
  { key: "security",    label: "Security",      icon: "ti-shield-lock" },
  { key: "uiux",        label: "UI/UX",         icon: "ti-color-swatch" },
];

function pct(n: number, d: number) { return d > 0 ? Math.round((n / d) * 100) : 0; }

// One row in the Gap resolution center: shows a layer's status + the fix action.
function GapRow({ ok, icon, label, status, hint, action }: {
  ok: boolean; icon: string; label: string; status: string; hint: string; action?: ReactNode;
}) {
  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 ${
      ok ? "border-emerald-900/30 bg-emerald-950/10" : "border-amber-900/30 bg-amber-950/10"
    }`}>
      <div className="flex min-w-0 items-start gap-2.5">
        <i className={`ti ${ok ? "ti-circle-check text-emerald-400" : `${icon} text-amber-400`} mt-0.5 text-base shrink-0`} aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-200">
            {label} <span className={ok ? "text-emerald-400" : "text-amber-400"}>· {status}</span>
          </p>
          <p className="text-[11px] text-gray-500">{hint}</p>
        </div>
      </div>
      <div className="shrink-0">{ok ? <span className="text-xs font-medium text-emerald-500">✓ Done</span> : action}</div>
    </div>
  );
}

const FIX_BTN = "flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-40 transition-colors";
const LINK_BTN = "flex items-center gap-1.5 rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800 transition-colors";

function CoverageBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="mt-2 h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
      <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${value}%` }} />
    </div>
  );
}

// ─── page ─────────────────────────────────────────────────────────────────────

export default function TraceabilityPage() {
  const [projects,   setProjects]   = useState<Project[]>([]);
  const [projectId,  setProjectId]  = useState("");
  const [data,       setData]       = useState<TraceabilityData | null>(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");
  const [expanded,   setExpanded]   = useState<Record<string, boolean>>({});
  const [solveResult,setSolveResult]= useState<string | null>(null);

  // Shared AI job — same ambient loop, status bar, and completion chime as the
  // Kanban "Solve gaps with AI" button, so gap-solving behaves identically
  // everywhere and for every project.
  const solveJob = useAiJob({
    onComplete: async () => {
      if (!projectId) return;
      // Report the real outcome by re-checking coverage, not a blanket "done".
      try {
        const cov = await api.getTaskCoverage(projectId);
        const remaining = cov.missing_frs?.length ?? 0;
        setSolveResult(
          remaining === 0
            ? "✓ All functional requirements now have Kanban tasks."
            : `⚠ ${remaining} FR${remaining > 1 ? "s" : ""} still uncovered after AI run: ${cov.missing_frs.slice(0, 5).join(", ")}${remaining > 5 ? "…" : ""}. Try again or refine the SRS wording.`,
        );
      } catch {
        setSolveResult("✓ Gap solution finished — matrix refreshed.");
      }
      loadData(projectId);
    },
  });
  const solving = solveJob.isRunning;

  // Extra one-click fixes so every gap can be resolved from this page. These
  // reuse the exact same server flows as their own screens — no flow is changed.
  const specsMemKey = (pid: string) => `specs-all:${pid}`;
  const allSpecsJob = useAiJob({
    onComplete: () => {
      try { localStorage.removeItem(specsMemKey(projectId)); } catch { /* ignore */ }
      loadData(projectId);
    },
    onFailed: () => { try { localStorage.removeItem(specsMemKey(projectId)); } catch { /* ignore */ } },
  });
  const archJob = useAiJob({ onComplete: () => loadData(projectId) });
  const srsFillJob = useAiJob({ onComplete: () => { setSolveResult("✓ SRS updated — new requirements added. Now run 'Solve gaps' to create their tasks."); loadData(projectId); } });
  const orphanJob = useAiJob({ onComplete: () => { setSolveResult("✓ Orphaned tasks linked to requirements."); loadData(projectId); } });

  async function handleFillSrs() {
    if (!projectId || srsFillJob.isRunning) return;
    setError("");
    try {
      const { task_id } = await api.fillSrsGaps(projectId);
      srsFillJob.startJob(task_id, "Adding requirements to SRS");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start SRS gap-fill"); }
  }
  async function handleLinkOrphans() {
    if (!projectId || orphanJob.isRunning) return;
    setError("");
    try {
      const { task_id } = await api.linkOrphanedTasks(projectId);
      orphanJob.startJob(task_id, "Linking orphaned tasks");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start orphan linking"); }
  }
  const reconcileJob = useAiJob({ onComplete: () => { setSolveResult("✓ Tasks and architecture reconciled."); loadData(projectId); } });
  async function handleReconcilePlan() {
    if (!projectId || reconcileJob.isRunning) return;
    setError("");
    try {
      const { task_id } = await api.reconcilePlan(projectId);
      reconcileJob.startJob(task_id, "Reconciling tasks with architecture");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start reconcile"); }
  }

  async function handleGenerateAllSpecs() {
    if (!projectId || allSpecsJob.isRunning) return;
    setError("");
    try {
      const { task_id } = await api.generateAllSpecs(projectId, true, null);
      try { localStorage.setItem(specsMemKey(projectId), JSON.stringify({ task_id, at: Date.now() })); } catch { /* ignore */ }
      allSpecsJob.startJob(task_id, "Generating all specs");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start spec generation");
    }
  }

  const [reqResolving, setReqResolving] = useState(false);
  const [showManualReq, setShowManualReq] = useState(false);
  const [manualAnswers, setManualAnswers] = useState<Record<number, string>>({});

  async function handleResolveRequirementGaps(answers?: string[]) {
    if (!projectId || reqResolving) return;
    setError("");
    setReqResolving(true);
    try {
      const r = await api.resolveRequirementGaps(projectId, answers);
      setSolveResult(`✓ ${r.message}`);
      setShowManualReq(false);
      loadData(projectId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not resolve requirement questions");
    } finally {
      setReqResolving(false);
    }
  }

  function openManualReq() {
    // Pre-fill each answer with the AI's suggestion so the user can edit or keep it.
    const seed: Record<number, string> = {};
    (data?.requirement?.gaps ?? []).forEach((g, i) => { seed[i] = g.auto_answer ?? ""; });
    setManualAnswers(seed);
    setShowManualReq(true);
  }

  function applyManualAnswers() {
    const gaps = data?.requirement?.gaps ?? [];
    const lines = gaps.map((g, i) => {
      const ans = (manualAnswers[i] ?? g.auto_answer ?? "").trim();
      if (!ans) return "";
      const q = (g.question || g.description || "").trim();
      return q ? `${q} → ${ans}` : ans;
    }).filter(Boolean);
    void handleResolveRequirementGaps(lines);
  }

  async function handleCompleteArchitecture() {
    if (!projectId || archJob.isRunning) return;
    setError("");
    try {
      let taskId = "";
      if (data?.architecture?.id) {
        const r = await api.regenerateArchitecture(data.architecture.id);
        taskId = r.task_id;
      } else if (data?.srs?.id) {
        const r = await api.generateArchitecture(projectId, data.srs.id, null);
        taskId = r.task_id;
      } else {
        setError("Finalize an SRS first, then architecture can be generated.");
        return;
      }
      archJob.startJob(taskId, "Generating architecture");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start architecture generation");
    }
  }

  // ── data loading ────────────────────────────────────────────────────────────
  const loadData = useCallback((pid: string) => {
    if (!pid) return;
    setLoading(true);
    setError("");
    api.getTraceability(pid)
      .then((d) => {
        setData(d as unknown as TraceabilityData);
        // auto-expand all features
        const exp: Record<string, boolean> = {};
        (d as unknown as TraceabilityData).prd?.features.forEach((f) => { exp[f.id] = true; });
        setExpanded(exp);
      })
      .catch((e: Error) => setError(e.message || "Failed to load traceability"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      const fromUrl = typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("project") : null;
      const pid = fromUrl || p[0]?.id || "";
      setProjectId(pid);
    });
  }, []);

  useEffect(() => { if (projectId) loadData(projectId); }, [projectId, loadData]);

  // If a bulk-spec job started here or on Kanban is still running, re-show its bar.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    let raw: string | null = null;
    try { raw = localStorage.getItem(specsMemKey(projectId)); } catch { raw = null; }
    if (!raw) return;
    let stored: { task_id?: string; at?: number } = {};
    try { stored = JSON.parse(raw); } catch { stored = { task_id: raw }; }
    const tid = stored.task_id;
    if (!tid || (stored.at && Date.now() - stored.at > 60 * 60 * 1000)) {
      try { localStorage.removeItem(specsMemKey(projectId)); } catch { /* ignore */ }
      return;
    }
    (async () => {
      try {
        const s = (await api.getTaskStatus(tid)) as unknown as { status?: string };
        const st = String(s.status || "").toUpperCase();
        if (cancelled) return;
        if (["SUCCESS", "COMPLETED", "FAILURE", "FAILED"].includes(st)) {
          try { localStorage.removeItem(specsMemKey(projectId)); } catch { /* ignore */ }
          return;
        }
        if (!allSpecsJob.isRunning) allSpecsJob.startJob(tid, "Generating all specs");
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // ── solve gaps with AI (fill missing FRs only — never duplicates) ───────────
  const handleSolve = async () => {
    if (!projectId || !data?.srs?.id) return;
    if ((data.coverage.missing_frs?.length ?? 0) === 0) return;

    setSolveResult(null);
    setError("");
    solveJob.startManual("Solving gaps with AI");
    try {
      const res = await api.extractModules(projectId, data.srs.id, { fillGapsOnly: true });
      if (!res.task_id) throw new Error("No background task ID returned");
      // Hand off to the shared AI job — drives the ambient loop, status bar,
      // and completion chime, and re-loads the matrix on success.
      solveJob.startJob(res.task_id, "Solving gaps with AI");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to start gap solution";
      setError(msg);
      solveJob.failManual(msg);
    }
  };

  // ── derived mappings ────────────────────────────────────────────────────────
  const mappings = useMemo(() => {
    if (!data) return null;

    // FR → tasks lookup (by linked_fr OR fr_references)
    const tasksByFR: Record<string, KanbanTask[]> = { orphaned: [] };
    data.srs?.functional_requirements.forEach((fr) => { tasksByFR[fr.id] = []; });

    data.tasks.forEach((t) => {
      let linked = false;
      if (t.linked_fr && tasksByFR[t.linked_fr] !== undefined) {
        tasksByFR[t.linked_fr].push(t);
        linked = true;
      }
      (t.fr_references ?? []).forEach((ref) => {
        if (ref !== t.linked_fr && tasksByFR[ref] !== undefined) {
          tasksByFR[ref].push(t);
          linked = true;
        }
      });
      if (!linked) tasksByFR["orphaned"].push(t);
    });

    // Feature → FRs lookup
    const frsByFeature: Record<string, SRSFR[]> = { orphaned: [] };
    data.prd?.features.forEach((f) => { frsByFeature[f.id] = []; });
    data.srs?.functional_requirements.forEach((fr) => {
      const key = fr.linked_feature || "orphaned";
      if (!frsByFeature[key]) frsByFeature[key] = [];
      frsByFeature[key].push(fr);
    });

    return { tasksByFR, frsByFeature };
  }, [data]);

  const stats = useMemo(() => {
    if (!data) return null;
    const cov     = data.coverage;
    const tasks   = data.tasks;
    const specsRdy= tasks.filter((t) => t.spec?.status === "ready").length;
    const archDocs = ARCH_DOCS.filter((d) => {
      const info = data.architecture?.docs[d.key];
      return info?.has_content || info?.status === "completed" || info?.status === "generated";
    }).length;
    return {
      cov,
      totalFeatures:  data.prd?.features.length ?? 0,
      coveredFeatures: data.prd?.features.filter((f) =>
        data.srs?.functional_requirements.some((fr) => fr.linked_feature === f.id)
      ).length ?? 0,
      totalTasks:  tasks.length,
      specsRdy,
      archDocs,
    };
  }, [data]);

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6 pb-12">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-600">Analysis</p>
          <h1 className="text-2xl font-bold text-white">Traceability matrix</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            PRD → SRS → Architecture → Kanban tasks — gap analysis &amp; auto-fix
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-200"
            value={projectId}
            onChange={(e) => {
              setProjectId(e.target.value);
              const url = new URL(window.location.href);
              url.searchParams.set("project", e.target.value);
              window.history.pushState({}, "", url.toString());
            }}
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <a href={`/tasks?project=${projectId}`}
            className="flex items-center gap-1.5 rounded-lg border border-indigo-800/40 px-3 py-2 text-sm text-indigo-400 hover:bg-indigo-950/20 transition-colors">
            <i className="ti ti-columns text-sm" aria-hidden /> Kanban
          </a>
          <button onClick={() => loadData(projectId)}
            className="flex items-center gap-1.5 rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-400 hover:bg-gray-900 transition-colors">
            <i className="ti ti-refresh text-sm" aria-hidden /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red-900/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
          <i className="ti ti-alert-triangle" aria-hidden /> {error}
        </div>
      )}

      {loading && (
        <div className="flex h-48 items-center justify-center text-gray-500">
          <i className="ti ti-loader-2 animate-spin mr-2 text-xl" aria-hidden />
          Analysing traceability…
        </div>
      )}

      {!loading && data && stats && mappings && (
        <div className="space-y-6">

          {/* ── Coverage summary cards ────────────────────────────────── */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {/* PRD Feature coverage */}
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
              <p className="text-[10px] uppercase tracking-widest text-gray-600">PRD features</p>
              <div className="mt-1.5 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-white">{stats.coveredFeatures}/{stats.totalFeatures}</span>
                <span className="text-xs font-semibold text-emerald-400">{pct(stats.coveredFeatures, stats.totalFeatures)}%</span>
              </div>
              <p className="text-[10px] text-gray-600">mapped to SRS FRs</p>
              <CoverageBar value={pct(stats.coveredFeatures, stats.totalFeatures)} color="bg-emerald-500" />
            </div>

            {/* SRS FR → Task coverage (authoritative from backend) */}
            <div className={`rounded-xl border p-4 ${
              stats.cov.missing_frs.length > 0
                ? "border-amber-800/40 bg-amber-950/10"
                : "border-gray-800 bg-gray-900/50"
            }`}>
              <p className="text-[10px] uppercase tracking-widest text-gray-600">FR → task coverage</p>
              <div className="mt-1.5 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-white">{stats.cov.covered_frs}/{stats.cov.total_frs}</span>
                <span className={`text-xs font-semibold ${stats.cov.missing_frs.length > 0 ? "text-amber-400" : "text-blue-400"}`}>
                  {stats.cov.coverage_pct}%
                </span>
              </div>
              <p className="text-[10px] text-gray-600">
                {stats.cov.missing_frs.length > 0
                  ? `${stats.cov.missing_frs.length} FR${stats.cov.missing_frs.length > 1 ? "s" : ""} need tasks`
                  : "fully covered"}
              </p>
              <CoverageBar value={stats.cov.coverage_pct} color={stats.cov.missing_frs.length > 0 ? "bg-amber-500" : "bg-blue-500"} />
            </div>

            {/* Architecture suite */}
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
              <p className="text-[10px] uppercase tracking-widest text-gray-600">Architecture suite</p>
              <div className="mt-1.5 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-white">{stats.archDocs}/{ARCH_DOCS.length}</span>
                <span className="text-xs font-semibold text-pink-400">{pct(stats.archDocs, ARCH_DOCS.length)}%</span>
              </div>
              <p className="text-[10px] text-gray-600">documents ready</p>
              <CoverageBar value={pct(stats.archDocs, ARCH_DOCS.length)} color="bg-pink-500" />
            </div>

            {/* Spec coverage */}
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
              <p className="text-[10px] uppercase tracking-widest text-gray-600">Dev specs ready</p>
              <div className="mt-1.5 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-white">{stats.specsRdy}/{stats.totalTasks}</span>
                <span className="text-xs font-semibold text-purple-400">{pct(stats.specsRdy, stats.totalTasks)}%</span>
              </div>
              <p className="text-[10px] text-gray-600">tasks with spec</p>
              <CoverageBar value={pct(stats.specsRdy, stats.totalTasks)} color="bg-purple-500" />
            </div>

            {/* Gaps from requirement analysis */}
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
              <p className="text-[10px] uppercase tracking-widest text-gray-600">Req. gaps</p>
              <div className="mt-1.5 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-white">{data.requirement?.gaps.length ?? 0}</span>
                <span className="text-xs text-gray-600">items</span>
              </div>
              <p className="text-[10px] text-gray-600 truncate">{data.requirement?.original_filename ?? "No source"}</p>
              <div className="mt-2 h-1.5 w-full rounded-full bg-gray-800" />
            </div>
          </div>

          {/* ── Gap resolution center — find every gap & fix it here ──── */}
          {(() => {
            const frMissing = stats.cov.missing_frs.length;
            const specsMissing = Math.max(0, stats.totalTasks - stats.specsRdy);
            const archMissing = ARCH_DOCS.length - stats.archDocs;
            const orphaned = mappings.tasksByFR["orphaned"].length;
            const featuresNotInSrs = Math.max(0, stats.totalFeatures - stats.coveredFeatures);
            const reqGaps = data.requirement?.gaps.length ?? 0;
            const fc = data.full_coverage;
            const worst = fc ? Math.min(fc.endpoints.pct, fc.tables.pct, fc.nfrs.pct) : 100;
            const planDrift = data.plan_drift?.count ?? 0;
            const autoClear = frMissing === 0 && specsMissing === 0 && archMissing === 0;
            const allClear = autoClear && orphaned === 0 && featuresNotInSrs === 0 && reqGaps === 0 && planDrift === 0;
            return (
              <div className="rounded-xl border border-indigo-900/40 bg-indigo-950/10 p-5 space-y-3">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-indigo-300">
                    <i className="ti ti-wand text-base" aria-hidden /> Gap resolution center
                  </h3>
                  <p className="mt-1 text-xs text-gray-400">
                    This is your one place to <strong className="text-gray-300">find</strong> and <strong className="text-gray-300">fix</strong> every gap.
                    Work top to bottom — <span className="text-amber-400">amber</span> means action needed, <span className="text-emerald-400">green ✓</span> means that layer is complete.
                    Fixing here uses the same engine as each screen, so nothing else changes.
                  </p>
                </div>

                <div className="space-y-2">
                  {/* 1. FR → tasks (auto-fix) */}
                  <GapRow
                    ok={frMissing === 0}
                    icon="ti-list-check"
                    label="Requirements → tasks"
                    status={frMissing === 0 ? "every requirement has a task" : `${frMissing} requirement${frMissing > 1 ? "s" : ""} without a task`}
                    hint="Each SRS functional requirement needs at least one Kanban task. Fix adds only the missing ones — never duplicates."
                    action={
                      <button onClick={() => void handleSolve()} disabled={solving || !data.srs} className={FIX_BTN}>
                        <i className={`ti ${solving ? "ti-loader-2 animate-spin" : "ti-wand"}`} aria-hidden />
                        {solving ? "Solving…" : "Solve gaps with AI"}
                      </button>
                    }
                  />
                  {/* 2. Dev specs (auto-fix) */}
                  <GapRow
                    ok={stats.totalTasks > 0 && specsMissing === 0}
                    icon="ti-file-text"
                    label="Dev specs"
                    status={stats.totalTasks === 0 ? "no tasks yet" : specsMissing === 0 ? "every task has a spec" : `${specsMissing} task${specsMissing > 1 ? "s" : ""} without a spec`}
                    hint="Each task needs a technical spec before Build. Runs on the server, one by one — keeps going even if you leave."
                    action={
                      <button onClick={() => void handleGenerateAllSpecs()} disabled={allSpecsJob.isRunning || stats.totalTasks === 0} className={FIX_BTN}>
                        <i className={`ti ${allSpecsJob.isRunning ? "ti-loader-2 animate-spin" : "ti-list-check"}`} aria-hidden />
                        {allSpecsJob.isRunning ? "Generating…" : "Generate all specs"}
                      </button>
                    }
                  />
                  {/* 3. Architecture (auto-fix) */}
                  <GapRow
                    ok={archMissing === 0}
                    icon="ti-sitemap"
                    label="Architecture suite"
                    status={`${stats.archDocs}/${ARCH_DOCS.length} documents ready`}
                    hint="All 6 docs give tasks the right files, endpoints and tables. After generating, finalize it on the Architecture screen."
                    action={
                      <button onClick={() => void handleCompleteArchitecture()} disabled={archJob.isRunning} className={FIX_BTN}>
                        <i className={`ti ${archJob.isRunning ? "ti-loader-2 animate-spin" : "ti-sitemap"}`} aria-hidden />
                        {archJob.isRunning ? "Generating…" : "Generate architecture"}
                      </button>
                    }
                  />
                  {/* 4. Completeness meters — a derived signal that improves as the
                       other rows are resolved; only offer Solve gaps when it helps. */}
                  <GapRow
                    ok={worst >= 90}
                    icon="ti-checklist"
                    label="Completeness (endpoints · tables · NFRs)"
                    status={fc ? `endpoints ${fc.endpoints.pct}% · tables ${fc.tables.pct}% · NFR ${fc.nfrs.pct}%` : "no data"}
                    hint="How well tasks cover the architecture's endpoints, tables and non-functional needs. This improves automatically as you resolve the rows above (FR tasks, SRS, orphaned, reconcile)."
                    action={
                      frMissing > 0 ? (
                        <button onClick={() => void handleSolve()} disabled={solving || !data.srs} className={FIX_BTN}>
                          <i className={`ti ${solving ? "ti-loader-2 animate-spin" : "ti-wand"}`} aria-hidden /> Solve gaps
                        </button>
                      ) : (
                        <span className="text-[11px] text-gray-500">Improves as rows above are fixed</span>
                      )
                    }
                  />
                  {/* 5. Features not in SRS (manual — needs SRS) */}
                  <GapRow
                    ok={featuresNotInSrs === 0}
                    icon="ti-book"
                    label="PRD features → SRS"
                    status={featuresNotInSrs === 0 ? "all features are in the SRS" : `${featuresNotInSrs} feature${featuresNotInSrs > 1 ? "s" : ""} not in SRS`}
                    hint="These PRD features have no SRS requirement. Fix writes new requirements into the SRS for them (append-only) — then Solve gaps makes their tasks."
                    action={
                      <button onClick={() => void handleFillSrs()} disabled={srsFillJob.isRunning} className={FIX_BTN}>
                        <i className={`ti ${srsFillJob.isRunning ? "ti-loader-2 animate-spin" : "ti-wand"}`} aria-hidden />
                        {srsFillJob.isRunning ? "Adding…" : "Add requirements to SRS"}
                      </button>
                    }
                  />
                  {/* 6. Orphaned tasks (manual — review in Kanban) */}
                  <GapRow
                    ok={orphaned === 0}
                    icon="ti-unlink"
                    label="Orphaned tasks"
                    status={orphaned === 0 ? "all tasks link to a requirement" : `${orphaned} task${orphaned > 1 ? "s" : ""} not linked to any FR`}
                    hint="These tasks aren't tied to a requirement. Fix links each to the requirement it fulfils (and adds a requirement for genuinely new work) — tasks are never deleted."
                    action={
                      <button onClick={() => void handleLinkOrphans()} disabled={orphanJob.isRunning} className={FIX_BTN}>
                        <i className={`ti ${orphanJob.isRunning ? "ti-loader-2 animate-spin" : "ti-wand"}`} aria-hidden />
                        {orphanJob.isRunning ? "Linking…" : "Auto-link to requirements"}
                      </button>
                    }
                  />
                  {/* 6b. Plan consistency — tasks referencing non-architecture entities */}
                  <GapRow
                    ok={planDrift === 0}
                    icon="ti-git-compare"
                    label="Plan consistency (tasks ↔ architecture)"
                    status={planDrift === 0 ? "tasks match the architecture" : `${planDrift} task${planDrift > 1 ? "s" : ""} reference something not in the architecture`}
                    hint="A task's endpoint/table isn't in the architecture. Fix either renames the task to the real name, or adds the missing entity to the architecture — never deletes anything."
                    action={
                      <button onClick={() => void handleReconcilePlan()} disabled={reconcileJob.isRunning} className={FIX_BTN}>
                        <i className={`ti ${reconcileJob.isRunning ? "ti-loader-2 animate-spin" : "ti-wand"}`} aria-hidden />
                        {reconcileJob.isRunning ? "Reconciling…" : "Auto-reconcile"}
                      </button>
                    }
                  />
                  {planDrift > 0 && (data.plan_drift?.items?.length ?? 0) > 0 && (
                    <p className="pl-8 text-[11px] text-gray-600">
                      e.g. {data.plan_drift!.items.slice(0, 3).map((it) => `“${it.title}” (${it.reason})`).join("; ")}
                      {planDrift > 3 ? ` +${planDrift - 3} more` : ""}
                    </p>
                  )}

                  {/* 7. Requirement questions (manual — earlier stage) */}
                  <GapRow
                    ok={reqGaps === 0}
                    icon="ti-file-description"
                    label="Requirement questions"
                    status={reqGaps === 0 ? "no open questions" : `${reqGaps} open question${reqGaps > 1 ? "s" : ""}`}
                    hint="Open points the AI found in your document. Pick either: let AI answer, or type your own — both get added to the SRS as assumptions (nothing existing changes)."
                    action={
                      <div className="flex flex-wrap gap-2">
                        <button onClick={() => void handleResolveRequirementGaps()} disabled={reqResolving} className={FIX_BTN}>
                          <i className={`ti ${reqResolving ? "ti-loader-2 animate-spin" : "ti-wand"}`} aria-hidden />
                          {reqResolving ? "Resolving…" : "Auto-resolve (AI)"}
                        </button>
                        <button onClick={openManualReq} disabled={reqResolving} className={LINK_BTN}>
                          <i className="ti ti-edit" aria-hidden /> Answer manually
                        </button>
                      </div>
                    }
                  />

                  {/* Manual answer editor — pre-filled with the AI's suggestions */}
                  {showManualReq && (data.requirement?.gaps.length ?? 0) > 0 && (
                    <div className="rounded-lg border border-indigo-800/40 bg-gray-950/60 p-3 space-y-2">
                      <p className="text-xs text-gray-400">
                        Edit any answer (pre-filled with the AI's suggestion), then apply. Each becomes an SRS assumption. Leave one blank to skip it.
                      </p>
                      {data.requirement!.gaps.map((g, i) => (
                        <div key={i} className="space-y-1">
                          <p className="text-[11px] text-gray-300">
                            <span className="rounded bg-gray-800 px-1 text-[9px] uppercase text-gray-400">{g.category}</span>{" "}
                            {g.question || g.description}
                          </p>
                          <input
                            value={manualAnswers[i] ?? g.auto_answer ?? ""}
                            onChange={(e) => setManualAnswers((p) => ({ ...p, [i]: e.target.value }))}
                            placeholder="Your answer…"
                            className="w-full rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-200"
                          />
                        </div>
                      ))}
                      <div className="flex flex-wrap gap-2 pt-1">
                        <button onClick={applyManualAnswers} disabled={reqResolving} className={FIX_BTN}>
                          <i className={`ti ${reqResolving ? "ti-loader-2 animate-spin" : "ti-check"}`} aria-hidden />
                          {reqResolving ? "Applying…" : "Apply my answers to SRS"}
                        </button>
                        <button onClick={() => setShowManualReq(false)} disabled={reqResolving} className={LINK_BTN}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>

                {/* live progress for the fixes started here */}
                {allSpecsJob.isVisible && (
                  <AiStatusBar {...aiJobStatusBarProps(allSpecsJob)} operationName={allSpecsJob.operationName || "Generating all specs"} onCancel={allSpecsJob.cancel} />
                )}
                {archJob.isVisible && (
                  <AiStatusBar {...aiJobStatusBarProps(archJob)} operationName={archJob.operationName || "Generating architecture"} onCancel={archJob.cancel} />
                )}
                {srsFillJob.isVisible && (
                  <AiStatusBar {...aiJobStatusBarProps(srsFillJob)} operationName={srsFillJob.operationName || "Adding requirements to SRS"} onCancel={srsFillJob.cancel} />
                )}
                {orphanJob.isVisible && (
                  <AiStatusBar {...aiJobStatusBarProps(orphanJob)} operationName={orphanJob.operationName || "Linking orphaned tasks"} onCancel={orphanJob.cancel} />
                )}
                {reconcileJob.isVisible && (
                  <AiStatusBar {...aiJobStatusBarProps(reconcileJob)} operationName={reconcileJob.operationName || "Reconciling tasks with architecture"} onCancel={reconcileJob.cancel} />
                )}

                {allClear ? (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-700/50 bg-emerald-950/30 px-4 py-3">
                    <p className="text-sm font-medium text-emerald-300">
                      <i className="ti ti-circle-check mr-2" aria-hidden />
                      All gaps resolved — your project plan is complete and traceable. You can build now.
                    </p>
                    <a
                      href={`/build?project=${projectId}`}
                      className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-lg hover:bg-emerald-500 transition-colors"
                    >
                      <i className="ti ti-code" aria-hidden /> Go to Build <i className="ti ti-arrow-right" aria-hidden />
                    </a>
                  </div>
                ) : (
                  <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-4 py-2.5 text-xs text-gray-500">
                    <i className="ti ti-lock mr-2" aria-hidden />
                    Resolve the <span className="text-amber-400">amber</span> items above — the <strong className="text-gray-400">Go to Build</strong> button appears here once every gap is green.
                  </div>
                )}
              </div>
            );
          })()}

          {/* ── Gap analysis + solve panel ────────────────────────────── */}
          <div className={`rounded-xl border p-5 space-y-4 ${
            stats.cov.missing_frs.length > 0
              ? "border-amber-800/30 bg-amber-950/10"
              : "border-emerald-800/30 bg-emerald-950/10"
          }`}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-1 flex-1">
                <h3 className={`flex items-center gap-2 text-sm font-semibold uppercase tracking-wider ${
                  stats.cov.missing_frs.length > 0 ? "text-amber-400" : "text-emerald-400"
                }`}>
                  <i className={`ti ${stats.cov.missing_frs.length > 0 ? "ti-alert-triangle" : "ti-circle-check"} text-base`} aria-hidden />
                  {stats.cov.missing_frs.length > 0
                    ? `Gap detected — ${stats.cov.missing_frs.length} FR${stats.cov.missing_frs.length > 1 ? "s" : ""} without tasks`
                    : "Full coverage — all FRs have tasks"}
                </h3>

                {stats.cov.missing_frs.length > 0 ? (
                  <p className="text-sm text-gray-300">
                    The following functional requirements have no Kanban task. Click <strong className="text-amber-300">Solve gaps</strong> to generate
                    only the missing tasks — existing tasks will <em>never</em> be duplicated or removed.
                  </p>
                ) : (
                  <p className="text-sm text-gray-400">
                    Every SRS functional requirement maps to at least one Kanban task. No action needed.
                  </p>
                )}

                {/* Missing FR chips */}
                {stats.cov.missing_frs.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {stats.cov.missing_frs.map((frId) => {
                      const fr = data.srs?.functional_requirements.find((f) => f.id === frId);
                      return (
                        <span key={frId}
                          title={fr?.title ?? frId}
                          className="rounded border border-amber-800/40 bg-amber-950/30 px-2 py-0.5 font-mono text-[11px] text-amber-300">
                          {frId}
                          {fr ? ` — ${fr.title.slice(0, 30)}${fr.title.length > 30 ? "…" : ""}` : ""}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>

              {stats.cov.missing_frs.length > 0 && (
                <button
                  onClick={() => void handleSolve()}
                  disabled={solving || !data.srs}
                  className="shrink-0 flex items-center gap-2 rounded-lg bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-500 disabled:bg-amber-900/40 disabled:cursor-not-allowed transition-all shadow-lg"
                >
                  {solving
                    ? <><i className="ti ti-loader-2 animate-spin text-base" aria-hidden /> Solving…</>
                    : <><i className="ti ti-wand text-base" aria-hidden /> Solve gaps with AI</>}
                </button>
              )}
            </div>

            {/* Solve progress — shared AI status bar (ambient + chime) */}
            {solveJob.isVisible && (
              <AiStatusBar
                {...aiJobStatusBarProps(solveJob)}
                operationName={solveJob.operationName || "Solving gaps with AI"}
                processingMessage={
                  (solveJob.taskMeta?.message as string | undefined) ??
                  solveJob.processingMessage
                }
                onCancel={solveJob.cancel}
              />
            )}

            {/* Solve result */}
            {solveResult && !solving && (
              <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-4 py-2.5 text-sm text-emerald-300">
                <i className="ti ti-circle-check mr-2" aria-hidden />{solveResult}
              </div>
            )}

            {/* Architecture incomplete warning */}
            {stats.archDocs < ARCH_DOCS.length && (
              <div className="flex items-start gap-2.5 rounded-lg border border-amber-900/20 bg-amber-950/10 p-3 text-xs text-amber-400">
                <i className="ti ti-info-circle text-base mt-0.5 shrink-0" aria-hidden />
                <p>
                  Architecture suite is incomplete ({stats.archDocs}/{ARCH_DOCS.length} docs ready).
                  Generated tasks may lack suggested files, endpoints, and tables until the architecture is finalized.
                  <a href="/architecture" className="ml-1 underline hover:text-amber-300">Complete architecture →</a>
                </p>
              </div>
            )}
          </div>

          {/* ── Completeness coverage (multi-dimensional) ─────────────── */}
          {data.full_coverage ? (
            <div className="rounded-xl border border-gray-800 bg-gray-900/30 p-5">
              <h3 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-gray-500">
                <i className="ti ti-checklist" aria-hidden /> Completeness coverage
              </h3>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {([
                  ["FR → tasks", { total: data.full_coverage.fr.total_frs, covered: data.full_coverage.fr.covered_frs, pct: data.full_coverage.fr.coverage_pct, missing: [] as string[] }],
                  ["API endpoints", data.full_coverage.endpoints],
                  ["DB tables", data.full_coverage.tables],
                  ["Non-functional", data.full_coverage.nfrs],
                ] as [string, Meter][]).map(([label, m]) => {
                  const color = m.pct >= 90 ? "bg-emerald-500" : m.pct >= 60 ? "bg-amber-500" : "bg-red-500";
                  return (
                    <div key={label} className="rounded-lg border border-gray-800 bg-gray-950/50 p-3">
                      <div className="flex items-baseline justify-between">
                        <span className="text-[11px] uppercase tracking-wide text-gray-500">{label}</span>
                        <span className="text-sm font-semibold text-gray-200">{m.covered}/{m.total}</span>
                      </div>
                      <CoverageBar value={m.pct} color={color} />
                      {m.missing && m.missing.length > 0 ? (
                        <p className="mt-2 truncate text-[10px] text-gray-600" title={m.missing.join(", ")}>
                          Missing: {m.missing.slice(0, 3).join(", ")}{m.missing.length > 3 ? `  +${m.missing.length - 3}` : ""}
                        </p>
                      ) : (
                        <p className="mt-2 text-[10px] text-emerald-500/80">Fully covered</p>
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 text-[10px] text-gray-600">
                Heuristic completeness signal — endpoints/tables/NFRs matched to tasks. Run <strong>Solve gaps with AI</strong> or
                regenerate tasks (completeness pass) to close gaps.
              </p>
            </div>
          ) : null}

          {/* ── Architecture checklist ────────────────────────────────── */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/30 p-5">
            <h3 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-gray-500">
              <i className="ti ti-sitemap" aria-hidden /> Architecture suite
            </h3>
            <div className="grid gap-3 grid-cols-3 lg:grid-cols-6">
              {ARCH_DOCS.map((doc) => {
                const info = data.architecture?.docs[doc.key];
                const done = info?.has_content || info?.status === "completed" || info?.status === "generated";
                return (
                  <div key={doc.key} className={`rounded-lg border p-3 text-center ${
                    done ? "border-emerald-900/30 bg-emerald-950/15" : "border-gray-800 bg-gray-950/30"
                  }`}>
                    <i className={`ti ${doc.icon} text-lg ${done ? "text-emerald-400" : "text-gray-600"}`} aria-hidden />
                    <p className="mt-1.5 text-xs font-medium text-gray-300">{doc.label}</p>
                    <span className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${
                      done ? "bg-emerald-950 text-emerald-400 border border-emerald-900/40"
                           : "bg-gray-900 text-gray-600 border border-gray-800"
                    }`}>{done ? "Ready" : info?.status ?? "Pending"}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Traceability tree ─────────────────────────────────────── */}
          <div className="space-y-3">
            <div className="hidden lg:grid lg:grid-cols-12 gap-4 px-4 text-[10px] font-semibold uppercase tracking-widest text-gray-600">
              <div className="col-span-4">PRD feature</div>
              <div className="col-span-4">SRS functional requirement</div>
              <div className="col-span-4">Kanban task &amp; spec</div>
            </div>

            {(!data.prd || data.prd.features.length === 0) ? (
              <div className="rounded-xl border border-dashed border-gray-800 p-10 text-center text-sm text-gray-600">
                No PRD features found — generate and approve a PRD first.
              </div>
            ) : (
              data.prd.features.map((feature) => {
                const linkedFRs = mappings.frsByFeature[feature.id] ?? [];
                const isOpen = !!expanded[feature.id];
                const frsMissingTasks = linkedFRs.filter((fr) => (mappings.tasksByFR[fr.id] ?? []).length === 0);
                const hasGap = frsMissingTasks.length > 0;

                return (
                  <div key={feature.id}
                    className={`rounded-xl border overflow-hidden transition-all ${
                      hasGap ? "border-amber-800/30 bg-amber-950/5" : "border-gray-800 bg-gray-900/30"
                    }`}>

                    {/* Feature row header */}
                    <div
                      onClick={() => setExpanded((p) => ({ ...p, [feature.id]: !p[feature.id] }))}
                      className="grid grid-cols-12 gap-4 p-4 cursor-pointer hover:bg-gray-900/40 transition-colors select-none"
                    >
                      <div className="col-span-4 flex items-start gap-2.5">
                        <i className={`ti ${isOpen ? "ti-chevron-down" : "ti-chevron-right"} mt-0.5 text-gray-600 text-sm shrink-0`} aria-hidden />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono text-[11px] font-bold text-indigo-400">{feature.id}</span>
                            <span className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase ${
                              PRIORITY_COLOR[feature.priority?.toLowerCase()] ?? PRIORITY_COLOR.medium
                            }`}>{feature.priority}</span>
                            {hasGap && (
                              <span className="rounded border border-amber-800/40 bg-amber-950/30 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-amber-400">
                                {frsMissingTasks.length} gap{frsMissingTasks.length > 1 ? "s" : ""}
                              </span>
                            )}
                          </div>
                          <p className="mt-0.5 text-sm font-semibold text-white">{feature.title}</p>
                          <p className="mt-0.5 text-xs text-gray-500 line-clamp-1">{feature.description}</p>
                        </div>
                      </div>

                      <div className="col-span-4 flex items-center">
                        {linkedFRs.length > 0 ? (
                          <span className="flex items-center gap-1.5 rounded-full border border-emerald-900/30 bg-emerald-950/20 px-2.5 py-0.5 text-[11px] text-emerald-400">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                            {linkedFRs.length} FR{linkedFRs.length > 1 ? "s" : ""} mapped
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5 rounded-full border border-red-900/30 bg-red-950/20 px-2.5 py-0.5 text-[11px] text-red-400">
                            <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                            No FRs — not in SRS
                          </span>
                        )}
                      </div>

                      <div className="col-span-4 flex items-center text-xs text-gray-600">
                        {isOpen ? "Collapse" : "Expand to see FRs and tasks"}
                      </div>
                    </div>

                    {/* FR + task detail rows */}
                    {isOpen && (
                      <div className="border-t border-gray-800/60 bg-gray-950/30 px-4 py-3 space-y-3">
                        {linkedFRs.length === 0 ? (
                          <p className="py-3 text-center text-xs text-red-400">
                            This feature is not traced to any SRS functional requirement.
                          </p>
                        ) : (
                          linkedFRs.map((fr) => {
                            const frTasks = mappings.tasksByFR[fr.id] ?? [];
                            const frHasGap = frTasks.length === 0;
                            return (
                              <div key={fr.id}
                                className={`grid grid-cols-1 lg:grid-cols-12 gap-4 rounded-lg p-3 ${
                                  frHasGap ? "border border-amber-800/30 bg-amber-950/10" : "border border-gray-800/40 bg-gray-900/20"
                                }`}>

                                {/* FR info */}
                                <div className="lg:col-span-4 flex items-start gap-2.5 pl-4">
                                  <div className="h-2 w-2 shrink-0 rounded-full mt-1.5 bg-indigo-500/60" />
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="font-mono text-[11px] font-bold text-gray-400">{fr.id}</span>
                                      <span className={`rounded border px-1 py-0.5 text-[9px] uppercase ${
                                        PRIORITY_COLOR[fr.priority?.toLowerCase()] ?? PRIORITY_COLOR.medium
                                      }`}>{fr.priority}</span>
                                      {frHasGap && (
                                        <span className="rounded border border-amber-800/40 bg-amber-950/30 px-1 py-0.5 text-[9px] font-bold uppercase text-amber-400">
                                          No task
                                        </span>
                                      )}
                                    </div>
                                    <p className="mt-0.5 text-xs font-medium text-gray-200">{fr.title}</p>
                                    <p className="mt-0.5 text-[11px] text-gray-500 leading-relaxed line-clamp-2">{fr.description}</p>
                                    {fr.inputs && <p className="mt-1 text-[10px] text-gray-600"><strong>In:</strong> {fr.inputs}</p>}
                                    {fr.outputs && <p className="text-[10px] text-gray-600"><strong>Out:</strong> {fr.outputs}</p>}
                                  </div>
                                </div>

                                {/* Coverage status */}
                                <div className="lg:col-span-4 flex items-start pt-1">
                                  {frHasGap ? (
                                    <span className="flex items-center gap-1.5 rounded border border-amber-800/40 bg-amber-950/20 px-2 py-1 text-[11px] text-amber-400">
                                      <i className="ti ti-alert-triangle text-sm shrink-0" aria-hidden />
                                      Gap — no task covers this FR
                                    </span>
                                  ) : (
                                    <span className="flex items-center gap-1.5 rounded border border-blue-900/30 bg-blue-950/10 px-2 py-1 text-[11px] text-blue-400">
                                      <i className="ti ti-check text-sm shrink-0" aria-hidden />
                                      {frTasks.length} task{frTasks.length > 1 ? "s" : ""} covering this FR
                                    </span>
                                  )}
                                </div>

                                {/* Task cards */}
                                <div className="lg:col-span-4 space-y-2">
                                  {frHasGap ? (
                                    <div className="rounded border border-dashed border-amber-800/30 p-2.5 text-center text-xs text-amber-600">
                                      Will be created when you click "Solve gaps"
                                    </div>
                                  ) : (
                                    frTasks.map((task) => (
                                      <div key={task.id}
                                        className="rounded-lg border border-gray-800 bg-gray-900/50 p-2.5 text-xs">
                                        <div className="flex items-center justify-between gap-2">
                                          <span className="font-medium text-gray-200 truncate" title={task.title}>{task.title}</span>
                                          <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase ${
                                            TASK_STATUS_COLOR[task.status] ?? TASK_STATUS_COLOR.backlog
                                          }`}>{task.status}</span>
                                        </div>
                                        {(task.suggested_table || task.suggested_endpoint || task.suggested_file) && (
                                          <div className="mt-1.5 space-y-0.5 border-t border-gray-800/40 pt-1.5">
                                            {task.suggested_table    && <p className="flex items-center gap-1 text-[10px] text-pink-400"><i className="ti ti-database shrink-0" />{task.suggested_table}</p>}
                                            {task.suggested_endpoint && <p className="flex items-center gap-1 text-[10px] text-blue-400"><i className="ti ti-api shrink-0" />{task.suggested_endpoint}</p>}
                                            {task.suggested_file     && <p className="flex items-center gap-1 text-[10px] text-emerald-400"><i className="ti ti-file-code shrink-0" />{task.suggested_file}</p>}
                                          </div>
                                        )}
                                        <div className="mt-1.5 flex items-center justify-between border-t border-gray-800/30 pt-1">
                                          {task.spec
                                            ? <span className="flex items-center gap-1 text-[10px] text-purple-400"><i className="ti ti-check-double" aria-hidden />Spec ready</span>
                                            : <span className="flex items-center gap-1 text-[10px] text-gray-600"><i className="ti ti-clock" aria-hidden />No spec</span>}
                                          {task.module_name && <span className="text-[10px] text-gray-700 truncate">[{task.module_name}]</span>}
                                        </div>
                                      </div>
                                    ))
                                  )}
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* ── Orphaned tasks ────────────────────────────────────────── */}
          {mappings.tasksByFR["orphaned"].length > 0 && (
            <div className="rounded-xl border border-gray-800 bg-gray-900/30 p-5">
              <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-gray-500">
                <i className="ti ti-unlink" aria-hidden />
                Orphaned tasks — not linked to any SRS FR ({mappings.tasksByFR["orphaned"].length})
              </h3>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {mappings.tasksByFR["orphaned"].map((task) => (
                  <div key={task.id} className="rounded-lg border border-gray-800 bg-gray-900/60 p-3 text-xs">
                    <p className="font-medium text-gray-300">{task.title}</p>
                    <p className="mt-1 text-[10px] text-gray-600">{task.status} · {task.task_type}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Requirement gaps ──────────────────────────────────────── */}
          {(data.requirement?.gaps.length ?? 0) > 0 && (
            <div className="rounded-xl border border-gray-800 bg-gray-900/30 p-5">
              <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-gray-500">
                <i className="ti ti-file-description" aria-hidden />
                Requirement analysis gaps ({data.requirement!.gaps.length})
              </h3>
              <div className="max-h-60 overflow-y-auto space-y-2 pr-2">
                {data.requirement!.gaps.map((gap, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg border border-gray-800 bg-gray-950 p-3 text-xs">
                    <span className={`shrink-0 rounded border px-2 py-0.5 text-[9px] font-bold uppercase ${
                      gap.category.toLowerCase() === "critical" ? "border-red-900/40 bg-red-950 text-red-400"
                      : gap.category.toLowerCase() === "important" ? "border-amber-900/30 bg-amber-950 text-amber-400"
                      : "border-gray-700 bg-gray-800 text-gray-500"
                    }`}>{gap.category}</span>
                    <div className="space-y-0.5">
                      <p className="font-medium text-gray-200">{gap.description}</p>
                      {gap.question && <p className="text-gray-500"><strong className="text-indigo-400">Q:</strong> {gap.question}</p>}
                      {gap.auto_answer && <p className="text-gray-600"><strong className="text-emerald-500">Auto-answer:</strong> {gap.auto_answer}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
}
