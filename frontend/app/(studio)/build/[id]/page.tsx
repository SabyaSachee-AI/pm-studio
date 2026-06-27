"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  api,
  type BuildDetail,
  type GeneratedFile,
  type GeneratedFileListItem,
  type ModelChoice,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { ArchModelSelector } from "@/components/ui/ArchModelSelector";
import { CodeEditor } from "@/components/ui/CodeEditor";
import { useAiJob } from "@/lib/hooks/useAiJob";
import { downloadTextFile, slugFilename } from "@/lib/specMarkdown";

// Only states where AI/Celery is actively producing code.
// NOTE: `qa` is intentionally NOT here — during QA we're waiting on GitHub CI
// (an HTTP poll), not AI generation. Treating it as "generating" caused the
// stale "Generating code … QUEUED" bar and hid the action buttons.
const GENERATING = new Set(["scaffolding", "generating"]);

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-gray-800 text-gray-400",
  scaffolding: "bg-blue-950/50 text-blue-300",
  scaffolded: "bg-blue-950/50 text-blue-300",
  generating: "bg-amber-950/50 text-amber-300",
  qa: "bg-purple-950/50 text-purple-300",
  ready: "bg-emerald-950/50 text-emerald-300",
  failed: "bg-red-950/50 text-red-300",
};

const FILE_STATUS_DOT: Record<string, string> = {
  pending: "bg-gray-600",
  generated: "bg-blue-500",
  edited: "bg-amber-400",
  qa_passed: "bg-emerald-500",
  qa_failed: "bg-red-500",
};

// ── Pipeline stage stepper ──────────────────────────────────────────────────
type StageState = "done" | "active" | "blocked" | "failed" | "todo";
type Stage = { key: string; label: string; icon: string; state: StageState; hint?: string };
type QaState = { status?: string; conclusion?: string | null } | null;

function deriveStages(build: BuildDetail, qa: QaState): Stage[] {
  const files = build.file_count;
  const pushed = !!build.github_full_name;
  const s = build.status;
  const report = (build.quality_report ?? {}) as Record<string, unknown>;
  const uiSigned = !!(report?.ui_test as { signed_off?: boolean } | undefined)?.signed_off;
  const deployUrl = (report?.deploy as { url?: string } | undefined)?.url;

  const scaffold: StageState =
    s === "scaffolding" ? "active"
    : (files > 0 || ["scaffolded", "generating", "ready", "qa", "failed"].includes(s)) ? "done"
    : "todo";
  const generate: StageState = s === "generating" ? "active" : files > 0 ? "done" : "todo";
  const push: StageState = pushed ? "done" : "todo";

  let ci: StageState = "todo";
  if (pushed) {
    if (s === "ready") ci = "done";
    else if (s === "failed" || qa?.conclusion === "failure") ci = "failed";
    else if (qa?.status === "blocked") ci = "blocked";
    else if (s === "qa") ci = "active";
    else ci = "done";
  }

  const uitest: StageState = uiSigned ? "done" : "todo";
  const deploy: StageState = deployUrl ? "done" : "todo";

  return [
    { key: "scaffold", label: "Scaffold", icon: "ti-stack-2", state: scaffold },
    { key: "generate", label: "Generate code", icon: "ti-sparkles", state: generate, hint: files > 0 ? `${files} files` : undefined },
    { key: "push", label: "Push", icon: "ti-brand-github", state: push },
    { key: "ci", label: "CI / QA", icon: "ti-test-pipe", state: ci, hint: qa?.conclusion ?? (qa?.status === "blocked" ? "blocked" : undefined) ?? undefined },
    { key: "uitest", label: "UI test", icon: "ti-device-desktop-check", state: uitest, hint: uiSigned ? "signed off" : undefined },
    { key: "deploy", label: "Deploy", icon: "ti-rocket", state: deploy, hint: deployUrl ? "live" : undefined },
  ];
}

function stageDotCls(state: StageState): string {
  switch (state) {
    case "done": return "border border-emerald-700 bg-emerald-900/60 text-emerald-300";
    case "active": return "border border-amber-600 bg-amber-900/50 text-amber-300 animate-pulse";
    case "failed": return "border border-red-700 bg-red-900/50 text-red-300";
    case "blocked": return "border border-amber-700 bg-amber-900/40 text-amber-300";
    default: return "border border-gray-700 bg-gray-800 text-gray-500";
  }
}

function stageLabelCls(state: StageState): string {
  switch (state) {
    case "done": return "text-emerald-300";
    case "active": return "text-amber-300";
    case "failed": return "text-red-300";
    case "blocked": return "text-amber-300";
    default: return "text-gray-500";
  }
}

/** Numbered step badge shown on the main pipeline action buttons. */
function StepNum({ n }: { n: number }) {
  return (
    <span className="mr-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-black/30 text-[10px] font-bold leading-none">
      {n}
    </span>
  );
}

/** A copyable command line for the local-run instructions. */
function CmdBlock({ cmd }: { cmd: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <code className="block flex-1 overflow-x-auto whitespace-pre rounded bg-gray-950 px-2 py-1 font-mono text-xs text-emerald-300">{cmd}</code>
      <button
        type="button"
        onClick={() => { void navigator.clipboard?.writeText(cmd); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
        className="shrink-0 rounded border border-gray-700 px-2 py-1 text-[10px] text-gray-400 hover:bg-gray-800"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export default function BuildWorkspacePage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();

  const [build, setBuild] = useState<BuildDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [file, setFile] = useState<GeneratedFile | null>(null);
  const [draft, setDraft] = useState("");
  const [aiInstruction, setAiInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [buildModel, setBuildModel] = useState<ModelChoice | null>(null);
  const [qa, setQa] = useState<{ status?: string; conclusion?: string | null; run_url?: string; message?: string; error?: string } | null>(null);
  const [showUiTest, setShowUiTest] = useState(false);
  const [uiChecklist, setUiChecklist] = useState<{ clone_cmd: string; run_cmd: string; items: { key: string; task_title: string; criterion: string }[] } | null>(null);
  const [uiResults, setUiResults] = useState<Record<string, { status: string; note: string }>>({});
  const [uiSaved, setUiSaved] = useState(false);
  const attached = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    const b = await api.getBuild(id);
    setBuild(b);
    return b;
  }, [id]);

  const aiJob = useAiJob({
    onComplete: () => { void refresh(); },
    onFailed: () => { void refresh(); },
  });

  useEffect(() => { void refresh(); }, [refresh]);

  // Re-attach to an in-flight generation task after reload
  useEffect(() => {
    if (!build?.generation_task_id) return;
    if (!GENERATING.has(build.status) && !aiJob.isRunning) return;
    const tid = build.generation_task_id;
    if (attached.current.has(tid)) return;
    attached.current.add(tid);
    aiJob.startJob(tid, "Generating code");
  }, [build, aiJob]);

  // Poll while generating
  useEffect(() => {
    if (!build || !GENERATING.has(build.status)) return;
    const t = setInterval(() => { void refresh(); }, 3000);
    return () => clearInterval(t);
  }, [build, refresh]);

  // Clear a generation bar stuck on QUEUED: happens when the page re-attaches to
  // a finished run that Celery has forgotten (reports PENDING forever). Never
  // clears an actively generating build.
  useEffect(() => {
    if (aiJob.status !== "pending") return;
    const terminal = build ? (build.status === "ready" || build.status === "failed") : false;
    if (terminal || aiJob.elapsedSeconds > 75) aiJob.reset();
  }, [aiJob.status, aiJob.elapsedSeconds, build?.status, aiJob.reset]);

  async function openFile(f: GeneratedFileListItem) {
    setSelectedId(f.id);
    setError("");
    try {
      const full = await api.getBuildFile(id, f.id);
      setFile(full);
      setDraft(full.content);
      setAiInstruction("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load file");
    }
  }

  const isGenerating = (build && GENERATING.has(build.status)) || aiJob.isRunning;

  async function handleScaffold() {
    try {
      const r = await api.scaffoldBuild(id, buildModel);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, "Scaffolding repository");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scaffold failed");
    }
  }

  async function handleGenerate(resume = false) {
    try {
      const r = await api.generateBuild(id, resume, buildModel);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, resume ? "Resuming code generation" : "Generating code");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    }
  }

  async function handleRegenerateTask() {
    if (!file?.task_id) return;
    try {
      const r = await api.generateTaskCode(id, file.task_id, buildModel);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, "Regenerating task code");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regenerate failed");
    }
  }

  async function handlePolish() {
    const scope = window.confirm(
      "Polish ALL code files? (OK = all · Cancel = critical files only: auth, models, API, security…)",
    ) ? "all" : "critical";
    setError("");
    try {
      const r = await api.polishBuild(id, scope, buildModel);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, `Polishing (${scope})`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Polish failed");
    }
  }

  async function handleGenerateTests() {
    setError("");
    try {
      const r = await api.generateBuildTests(id, buildModel);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, "Generating tests");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Test generation failed");
    }
  }

  async function handlePush() {
    setError("");
    try {
      const r = await api.pushBuild(id);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, "Pushing to GitHub");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Push failed — is GITHUB_REPO_TOKEN set?");
    }
  }

  async function handleRepair() {
    setError("");
    try {
      const r = await api.repairBuild(id, buildModel);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, "AI repairing from CI logs");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Repair failed");
    }
  }

  async function handleSyncFromGithub() {
    if (!window.confirm(
      "Sync from GitHub?\n\nThis pulls the repo's latest commit into PM Studio and OVERWRITES local copies (GitHub wins). Use this after you pushed local edits. Make sure your changes are pushed first.",
    )) return;
    setError("");
    setBusy(true);
    try {
      const r = await api.syncBuildFromGithub(id);
      const b = await refresh();
      // If the open file changed, reload it
      if (selectedId) {
        const stillThere = b.files.some((f) => f.id === selectedId);
        if (stillThere) { const full = await api.getBuildFile(id, selectedId); setFile(full); setDraft(full.content); }
        else { setFile(null); setSelectedId(null); setDraft(""); }
      }
      setError(`Synced from GitHub — ${r.updated} updated, ${r.added} added, ${r.removed} removed.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleMarkReady() {
    if (!window.confirm(
      "Mark this build as ready?\n\nUse this when CI passed (or you verified the app locally) but PM Studio can't read the CI status — e.g. the GitHub token is missing Actions: Read.",
    )) return;
    setError("");
    try {
      await api.markBuildReady(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not mark ready");
    }
  }

  async function handleDeploy() {
    setError("");
    const input = window.prompt(
      "Host port for THIS app on the VPS (must be unique — not 8090/8000/3000 used by PM Studio):",
      "3100",
    );
    if (input === null) return;
    const port = Number(input) || 3100;
    try {
      const r = await api.deployBuild(id, port);
      attached.current.add(r.task_id);
      aiJob.startJob(r.task_id, "Deploying to VPS");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deploy failed — set VPS config in Admin → AI config");
    }
  }

  const pollQa = useCallback(async () => {
    try {
      setQa(await api.getBuildQa(id));
      // Also refresh the build so autonomous-CI progress + status changes show live.
      await refresh();
    } catch { /* not pushed yet */ }
  }, [id, refresh]);

  // Poll CI status once pushed (status qa) until the run completes.
  // Stop polling if CI is unreadable (blocked) — no point hammering a 403.
  useEffect(() => {
    if (!build?.github_full_name) return;
    void pollQa();
    if (build.status !== "qa") return;
    if (qa?.status === "blocked" || qa?.status === "auth_failed" || qa?.status === "error") return;
    const t = setInterval(() => { void pollQa(); }, 6000);
    return () => clearInterval(t);
  }, [build?.github_full_name, build?.status, qa?.status, pollQa]);

  async function handleSave() {
    if (!file) return;
    setBusy(true);
    try {
      const updated = await api.updateBuildFile(id, file.id, draft);
      setFile(updated);
      setDraft(updated.content);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleAiEdit() {
    if (!file || !aiInstruction.trim()) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.aiEditBuildFile(id, file.id, aiInstruction.trim(), buildModel);
      setFile(updated);
      setDraft(updated.content);
      setAiInstruction("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI edit failed");
    } finally {
      setBusy(false);
    }
  }

  function downloadCurrent() {
    if (!file) return;
    const name = file.path.split("/").pop() || "file.txt";
    downloadTextFile(name, file.content, "text/plain");
  }

  async function downloadBundle() {
    if (!build) return;
    setBusy(true);
    try {
      const parts: string[] = [`# ${build.display_name || "Build"} — ${build.files.length} files\n`];
      for (const f of build.files) {
        const full = await api.getBuildFile(id, f.id);
        parts.push(`\n\n===== ${f.path} =====\n\n${full.content}`);
      }
      downloadTextFile(`${slugFilename(build.display_name || "build")}-code-bundle.txt`, parts.join(""), "text/plain");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bundle download failed");
    } finally {
      setBusy(false);
    }
  }

  async function openUiTest() {
    setShowUiTest((v) => !v);
    if (uiChecklist) return;
    try {
      const c = await api.getBuildUiChecklist(id);
      setUiChecklist(c);
      // seed from any saved results
      const saved = (build?.quality_report as Record<string, unknown> | null)?.ui_test as
        { results?: { key: string; status: string; note: string }[] } | undefined;
      const seed: Record<string, { status: string; note: string }> = {};
      for (const it of c.items) seed[it.key] = { status: "pending", note: "" };
      for (const r of saved?.results ?? []) seed[r.key] = { status: r.status, note: r.note };
      setUiResults(seed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load UI checklist");
    }
  }

  function setUiItem(key: string, patch: Partial<{ status: string; note: string }>) {
    setUiResults((prev) => {
      const base = prev[key] ?? { status: "pending", note: "" };
      return { ...prev, [key]: { ...base, ...patch } };
    });
    setUiSaved(false);
  }

  async function saveUiTest(signOff: boolean) {
    if (!uiChecklist) return;
    setBusy(true);
    try {
      const results = uiChecklist.items.map((it) => ({
        key: it.key,
        status: uiResults[it.key]?.status ?? "pending",
        note: uiResults[it.key]?.note ?? "",
      }));
      await api.saveBuildUiTest(id, results, signOff);
      setUiSaved(true);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save UI test");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this build and all generated files?")) return;
    await api.deleteBuild(id);
    router.push("/build");
  }

  if (!build) {
    return <div className="p-6 text-sm text-gray-500">Loading build…</div>;
  }

  const progress = build.generation_progress as Record<string, unknown> | null;
  const liveMessage = (progress?.message as string | undefined) ?? aiJob.processingMessage;

  return (
    <div className="flex h-[calc(100vh-1rem)] flex-col gap-3 p-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/build")} className="text-gray-500 hover:text-gray-300" title="Back">
            <i className="ti ti-arrow-left text-lg" aria-hidden />
          </button>
          <div>
            <h1 className="text-lg font-semibold text-white">{build.display_name || `Build v${build.version}`}</h1>
            <p className="text-xs text-gray-500">{build.file_count} files</p>
          </div>
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[build.status] ?? STATUS_STYLE.draft}`}>
            {build.status}
          </span>
          {build.quality_score != null ? (
            <span className="text-xs text-gray-400">{build.quality_score.toFixed(1)}/10</span>
          ) : null}
        </div>
        {/* Action buttons — ordered by the build pipeline sequence */}
        <div className="flex flex-wrap items-center gap-2">
          <ArchModelSelector value={buildModel} onChange={setBuildModel} compact />

          {/* 1 — Scaffold (only before any code exists) */}
          {build.status === "draft" ? (
            <Button size="sm" disabled={isGenerating} onClick={() => void handleScaffold()}>
              <StepNum n={1} /><i className="ti ti-stack-2 mr-1.5" aria-hidden /> Scaffold
            </Button>
          ) : null}

          {/* 2 — Generate code */}
          {(build.status === "scaffolded" || build.status === "ready" || build.status === "qa") && !isGenerating ? (
            <Button size="sm" onClick={() => void handleGenerate(false)}>
              <StepNum n={2} /><i className="ti ti-sparkles mr-1.5" aria-hidden /> Generate code
            </Button>
          ) : null}
          {build.can_resume && !isGenerating ? (
            <Button size="sm" variant="outline" onClick={() => void handleGenerate(true)}>
              <i className="ti ti-refresh mr-1.5" aria-hidden /> Resume
            </Button>
          ) : null}

          {/* 3 — Polish (AI) */}
          {build.file_count > 0 && !isGenerating ? (
            <Button size="sm" variant="outline" onClick={() => void handlePolish()}>
              <StepNum n={3} /><i className="ti ti-wand mr-1.5" aria-hidden /> Polish (AI)
            </Button>
          ) : null}

          {/* 4 — Generate tests */}
          {build.file_count > 0 && !isGenerating ? (
            <Button size="sm" variant="outline" onClick={() => void handleGenerateTests()}>
              <StepNum n={4} /><i className="ti ti-test-pipe mr-1.5" aria-hidden /> Generate tests
            </Button>
          ) : null}

          {/* 5 — Push to GitHub (triggers CI/QA automatically) */}
          {build.file_count > 0 && !isGenerating ? (
            <Button size="sm" variant="outline" onClick={() => void handlePush()}>
              <StepNum n={5} /><i className="ti ti-brand-github mr-1.5" aria-hidden /> Push to GitHub
            </Button>
          ) : null}

          {/* 6 — Local UI test (run locally + push/sync instructions inside) */}
          {build.file_count > 0 ? (
            <Button size="sm" variant="outline" onClick={() => void openUiTest()}>
              <StepNum n={6} /><i className="ti ti-device-desktop-check mr-1.5" aria-hidden /> Local UI test
            </Button>
          ) : null}

          {/* 7 — Deploy to VPS */}
          {build.github_full_name && !isGenerating ? (
            <Button size="sm" variant="outline" onClick={() => void handleDeploy()}>
              <StepNum n={7} /><i className="ti ti-rocket mr-1.5" aria-hidden /> Deploy to VPS
            </Button>
          ) : null}

          {/* divider — utility actions below (not part of the linear flow) */}
          <span className="mx-1 h-5 w-px bg-gray-700" aria-hidden />

          {build.github_full_name && !isGenerating ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void handleSyncFromGithub()}>
              <i className="ti ti-cloud-download mr-1.5" aria-hidden /> Sync from GitHub
            </Button>
          ) : null}
          <Button size="sm" variant="outline" disabled={busy || build.file_count === 0} onClick={() => void downloadBundle()}>
            <i className="ti ti-download mr-1.5" aria-hidden /> Download all
          </Button>
          <Button size="sm" variant="outline" onClick={() => void handleDelete()}
            className="border-red-900/60 text-red-300 hover:bg-red-950/40">
            <i className="ti ti-trash" aria-hidden />
          </Button>
        </div>
      </div>

      {/* Pipeline stage stepper — full flow at a glance */}
      <div className="flex items-center gap-1 overflow-x-auto rounded-lg border border-gray-800 bg-gray-900/40 px-3 py-2">
        {deriveStages(build, qa).map((st, i, arr) => (
          <Fragment key={st.key}>
            {i > 0 ? (
              <div className={`h-px w-5 shrink-0 sm:w-8 ${arr[i - 1].state === "done" ? "bg-emerald-700" : "bg-gray-700"}`} />
            ) : null}
            <div className="flex shrink-0 items-center gap-2" title={st.hint || st.label}>
              <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${stageDotCls(st.state)}`}>
                {st.state === "done" ? <i className="ti ti-check" aria-hidden />
                  : st.state === "failed" || st.state === "blocked" ? <i className="ti ti-alert-triangle" aria-hidden />
                  : <i className={`ti ${st.icon}`} aria-hidden />}
              </span>
              <div className="leading-tight">
                <p className={`text-xs font-medium ${stageLabelCls(st.state)}`}>{st.label}</p>
                {st.hint ? <p className="text-[10px] text-gray-500">{st.hint}</p> : null}
              </div>
            </div>
          </Fragment>
        ))}
      </div>

      {/* GitHub repo + live URL */}
      {build.repo_url ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-800 bg-gray-900/50 px-3 py-2 text-xs">
          <a href={build.repo_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">
            <i className="ti ti-brand-github mr-1" aria-hidden />{build.github_full_name}
          </a>
          {(() => {
            const dep = (build.quality_report as Record<string, unknown> | null)?.deploy as { url?: string } | undefined;
            return dep?.url ? (
              <a href={dep.url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">
                <i className="ti ti-rocket mr-1" aria-hidden />live: {dep.url}
              </a>
            ) : null;
          })()}
        </div>
      ) : null}

      {/* CI / QA explainer — always tells you WHY this stage is where it is */}
      {build.github_full_name && (build.status === "qa" || build.status === "failed" || qa?.conclusion === "failure") ? (
        (() => {
          const bad = qa?.status === "blocked" || qa?.status === "auth_failed" || qa?.status === "error"
            || qa?.conclusion === "failure" || build.status === "failed" || qa?.status === "no_runs"
            || (!!qa?.error && !qa?.conclusion);
          return (
            <div className={`rounded-lg border p-3 text-xs ${bad ? "border-amber-900/50 bg-amber-950/20" : "border-blue-900/40 bg-blue-950/20"}`}>
              <div className="flex items-start gap-2">
                <i className={`ti mt-0.5 ${bad ? "ti-alert-triangle text-amber-400" : "ti-loader-2 animate-spin text-blue-300"}`} aria-hidden />
                <div className="min-w-0 flex-1">
                  {(() => {
                    const auto = (build.quality_report as Record<string, unknown> | null)?.auto_ci as { phase?: string; message?: string } | undefined;
                    if (!auto) return null;
                    const active = ["watching", "repairing", "repushed"].includes(auto.phase || "");
                    if (active) {
                      return (
                        <p className="mb-1.5 flex items-center gap-1.5 rounded bg-blue-950/40 px-2 py-1 font-medium text-blue-200">
                          <i className="ti ti-robot animate-pulse" aria-hidden /> Auto-repair running — {auto.message}
                        </p>
                      );
                    }
                    if (auto.phase === "stopped") {
                      return (
                        <p className="mb-1.5 flex items-center gap-1.5 rounded bg-amber-950/40 px-2 py-1 font-medium text-amber-200">
                          <i className="ti ti-robot-off" aria-hidden /> Auto-repair stopped — {auto.message}
                        </p>
                      );
                    }
                    return null;
                  })()}
                  {(() => {
                    const plan = (build.quality_report as Record<string, unknown> | null)?.repair_plan as { targeted?: string[]; fixed?: number } | undefined;
                    if (!plan || !plan.targeted?.length) return null;
                    return (
                      <p className="mb-1.5 text-[11px] text-gray-500">
                        Last repair pass: fixed {plan.fixed ?? 0} of {plan.targeted.length} flagged file(s).
                      </p>
                    );
                  })()}
                  {!qa ? (
                    <p className="text-gray-300">Checking CI status on GitHub…</p>
                  ) : qa.status === "auth_failed" ? (
                    <>
                      <p className="font-medium text-amber-300">GitHub token is invalid or expired (401) — that&apos;s why this stage is stuck.</p>
                      <p className="mt-0.5 text-gray-400">
                        The token no longer authenticates with GitHub (expired, revoked, or wrong value). PM Studio
                        can&apos;t read CI — or push/deploy — until you set a valid token.
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <a href="/admin/ai-config" className="rounded border border-amber-700 px-2 py-1 text-amber-200 hover:bg-amber-950/40">Update token in Admin → AI config</a>
                        <a href={`${build.repo_url}/actions`} target="_blank" rel="noreferrer" className="rounded border border-gray-700 px-2 py-1 text-gray-300 hover:bg-gray-800">Open Actions on GitHub</a>
                        <button onClick={() => void handleMarkReady()} className="rounded border border-emerald-800 px-2 py-1 text-emerald-300 hover:bg-emerald-950/40">Mark ready &amp; continue</button>
                      </div>
                    </>
                  ) : qa.status === "blocked" ? (
                    <>
                      <p className="font-medium text-amber-300">CI status can&apos;t be read — that&apos;s why this stage is stuck.</p>
                      <p className="mt-0.5 text-gray-400">
                        Your GitHub token is missing <b>Actions: Read</b>, so PM Studio can&apos;t see whether CI passed.
                        Your code is already on GitHub — only the status check is blocked, not the build.
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <a href="/admin/ai-config" className="rounded border border-amber-700 px-2 py-1 text-amber-200 hover:bg-amber-950/40">Fix token (add Actions: Read)</a>
                        <a href={`${build.repo_url}/actions`} target="_blank" rel="noreferrer" className="rounded border border-gray-700 px-2 py-1 text-gray-300 hover:bg-gray-800">Open Actions on GitHub</a>
                        <button onClick={() => void handleMarkReady()} className="rounded border border-emerald-800 px-2 py-1 text-emerald-300 hover:bg-emerald-950/40">Mark ready &amp; continue</button>
                      </div>
                    </>
                  ) : qa.status === "no_runs" ? (
                    <>
                      <p className="font-medium text-gray-200">No CI run has started yet — that&apos;s why this stage is waiting.</p>
                      <p className="mt-0.5 text-gray-400">
                        It can take a minute after a push. If it never appears, the workflow file may be missing or
                        Actions may be disabled on the repo.
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <a href={`${build.repo_url}/actions`} target="_blank" rel="noreferrer" className="rounded border border-gray-700 px-2 py-1 text-gray-300 hover:bg-gray-800">Open Actions on GitHub</a>
                        <button onClick={() => void handleMarkReady()} className="rounded border border-emerald-800 px-2 py-1 text-emerald-300 hover:bg-emerald-950/40">Mark ready &amp; continue</button>
                      </div>
                    </>
                  ) : qa.conclusion === "failure" || build.status === "failed" ? (
                    <>
                      <p className="font-medium text-red-300">CI failed — that&apos;s why this stage is red.</p>
                      <p className="mt-0.5 text-gray-400">A test or build step failed on GitHub. Open the run logs, or let AI read the logs and fix + re-push.</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {qa.run_url ? <a href={qa.run_url} target="_blank" rel="noreferrer" className="rounded border border-gray-700 px-2 py-1 text-gray-300 hover:bg-gray-800">View run logs</a> : null}
                        {!isGenerating ? <button onClick={() => void handleRepair()} className="rounded border border-blue-800 px-2 py-1 text-blue-200 hover:bg-blue-950/40">Fix with AI &amp; re-push</button> : null}
                        <button onClick={() => void handleMarkReady()} className="rounded border border-emerald-800 px-2 py-1 text-emerald-300 hover:bg-emerald-950/40">Mark ready anyway</button>
                      </div>
                    </>
                  ) : qa.status === "error" || (qa.error && !qa.conclusion && qa.status !== "queued" && qa.status !== "in_progress") ? (
                    <>
                      <p className="font-medium text-amber-300">Couldn&apos;t read CI status — that&apos;s why this stage is stuck.</p>
                      <p className="mt-0.5 text-gray-400">GitHub returned an unexpected response. See the detail below, or check the run on GitHub.</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <a href={`${build.repo_url}/actions`} target="_blank" rel="noreferrer" className="rounded border border-gray-700 px-2 py-1 text-gray-300 hover:bg-gray-800">Open Actions on GitHub</a>
                        <button onClick={() => void handleMarkReady()} className="rounded border border-emerald-800 px-2 py-1 text-emerald-300 hover:bg-emerald-950/40">Mark ready &amp; continue</button>
                      </div>
                    </>
                  ) : (
                    <p className="text-gray-300">
                      CI is running on GitHub… this stage clears automatically when it finishes.
                      {qa.run_url ? <a href={qa.run_url} target="_blank" rel="noreferrer" className="ml-1 underline">view run</a> : null}
                    </p>
                  )}
                  {qa?.error ? <p className="mt-2 text-[11px] text-gray-500">Detail: {qa.error}</p> : null}
                </div>
              </div>
            </div>
          );
        })()
      ) : null}

      {isGenerating || aiJob.isVisible ? (() => {
        const barProps = aiJobStatusBarProps(aiJob);
        const selectedModel = buildModel ? `${buildModel.provider} / ${buildModel.model}` : "Auto (best free model)";
        const op = (aiJob.operationName || "").toLowerCase();
        const nextStep =
          op.includes("scaffold") ? "When done, click ‘2 Generate code’."
          : op.includes("test") ? "When done, click ‘5 Push to GitHub’ — CI will run these tests."
          : op.includes("polish") ? "When done, click ‘5 Push to GitHub’."
          : op.includes("generat") ? "When done, click ‘5 Push to GitHub’ (optionally ‘3 Polish’ / ‘4 Generate tests’ first)."
          : op.includes("push") ? "CI runs automatically after the push — PM Studio auto-repairs failures, just watch."
          : op.includes("deploy") ? "After deploy, open the live URL on the GitHub row."
          : op.includes("repair") ? "Re-pushes automatically when fixed — then CI runs again."
          : undefined;
        return (
          <AiStatusBar
            {...barProps}
            operationName={aiJob.operationName || "Generating code"}
            processingMessage={liveMessage}
            currentModel={barProps.currentModel || selectedModel}
            nextStep={nextStep}
            onCancel={aiJob.cancel}
          />
        );
      })() : null}

      {error ? <p className="rounded border border-red-800 bg-red-950/40 p-2 text-sm text-red-300">{error}</p> : null}

      {/* Stage 4 — local UI test (human-in-the-loop) */}
      {showUiTest && uiChecklist ? (
        <div className="max-h-[45vh] overflow-y-auto rounded-lg border border-gray-800 bg-gray-900/60 p-3 text-sm">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="font-medium text-gray-200">Local UI test</h3>
            <button onClick={() => setShowUiTest(false)} className="text-gray-500 hover:text-gray-300" title="Close">
              <i className="ti ti-x" aria-hidden />
            </button>
          </div>
          <p className="mb-2 text-xs text-gray-500">Run the app on your machine, verify each criterion, and (optionally) push fixes back.</p>
          <div className="mb-3 space-y-2 rounded-lg border border-gray-800 bg-gray-950/60 p-3">
            <div>
              <p className="mb-1 text-xs font-medium text-gray-300">1 · Get the code</p>
              <CmdBlock cmd={uiChecklist.clone_cmd} />
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-gray-300">2 · Configure environment</p>
              <CmdBlock cmd="cp .env.example .env   # then edit any secrets/keys" />
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-gray-300">3 · Run it locally</p>
              <CmdBlock cmd={uiChecklist.run_cmd} />
              <p className="mt-1 text-[11px] text-gray-500">Open the URL printed in the terminal (e.g. http://localhost:3000). No Docker? use each app&apos;s own commands (e.g. <span className="font-mono">npm install &amp;&amp; npm run dev</span>).</p>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-gray-300">4 · Made fixes? Push them to GitHub</p>
              <CmdBlock cmd={'git add -A\ngit commit -m "Local fixes during UI test"\ngit push'} />
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-gray-300">5 · Pull changes back into PM Studio</p>
              <p className="text-[11px] text-gray-500">Click <span className="font-medium text-gray-300">&ldquo;Sync from GitHub&rdquo;</span> at the top — it overwrites PM Studio&apos;s copies with the repo (GitHub wins).</p>
            </div>
          </div>
          {uiChecklist.items.length === 0 ? (
            <p className="text-xs text-gray-600">No acceptance criteria found — generate task specs to populate the checklist.</p>
          ) : (
            <ul className="space-y-1.5">
              {uiChecklist.items.map((it) => {
                const r = uiResults[it.key] ?? { status: "pending", note: "" };
                return (
                  <li key={it.key} className="rounded border border-gray-800 bg-gray-950 p-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-[10px] uppercase tracking-wide text-gray-600">{it.task_title}</p>
                        <p className="text-xs text-gray-300">{it.criterion}</p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <button onClick={() => setUiItem(it.key, { status: "pass" })}
                          className={`rounded px-2 py-0.5 text-xs ${r.status === "pass" ? "bg-emerald-700 text-white" : "bg-gray-800 text-gray-400 hover:text-emerald-300"}`}>Pass</button>
                        <button onClick={() => setUiItem(it.key, { status: "fail" })}
                          className={`rounded px-2 py-0.5 text-xs ${r.status === "fail" ? "bg-red-700 text-white" : "bg-gray-800 text-gray-400 hover:text-red-300"}`}>Fail</button>
                      </div>
                    </div>
                    {r.status === "fail" ? (
                      <input
                        className="mt-1.5 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-200"
                        placeholder="What went wrong? (sent to AI repair / regenerate)"
                        value={r.note}
                        onChange={(e) => setUiItem(it.key, { note: e.target.value })}
                      />
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
          {uiChecklist.items.length > 0 ? (
            <div className="mt-3 flex items-center gap-2">
              <Button size="sm" variant="outline" disabled={busy} onClick={() => void saveUiTest(false)}>Save progress</Button>
              <Button size="sm" disabled={busy} onClick={() => void saveUiTest(true)}>
                <i className="ti ti-circle-check mr-1" aria-hidden /> Sign off
              </Button>
              {uiSaved ? <span className="text-xs text-emerald-400">Saved</span> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Body: file tree + editor */}
      <div className="flex min-h-0 flex-1 gap-3">
        {/* File tree */}
        <div className="w-72 shrink-0 overflow-y-auto rounded-lg border border-gray-800 bg-gray-950 p-2">
          {build.files.length === 0 ? (
            <p className="p-3 text-xs text-gray-600">No files yet. Scaffold, then generate code.</p>
          ) : (
            <ul className="space-y-0.5">
              {build.files.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    onClick={() => void openFile(f)}
                    className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left font-mono text-xs ${
                      selectedId === f.id ? "bg-gray-800 text-white" : "text-gray-400 hover:bg-gray-900"
                    }`}
                    title={f.path}
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${FILE_STATUS_DOT[f.status] ?? "bg-gray-600"}`} />
                    <span className="truncate">{f.path}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Editor */}
        <div className="flex min-w-0 flex-1 flex-col rounded-lg border border-gray-800 bg-gray-950">
          {!file ? (
            <div className="flex flex-1 items-center justify-center text-sm text-gray-600">
              Select a file to view or edit.
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 px-3 py-2">
                <span className="font-mono text-xs text-gray-300">{file.path}</span>
                <div className="flex items-center gap-1.5">
                  {file.task_id ? (
                    <Button size="xs" variant="outline" disabled={isGenerating} onClick={() => void handleRegenerateTask()}>
                      <i className="ti ti-refresh mr-1" aria-hidden /> Regenerate task
                    </Button>
                  ) : null}
                  <Button size="xs" variant="outline" onClick={downloadCurrent}>
                    <i className="ti ti-download mr-1" aria-hidden /> Download
                  </Button>
                  <Button size="xs" disabled={busy || draft === file.content} onClick={() => void handleSave()}>
                    Save
                  </Button>
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <CodeEditor path={file.path} value={draft} onChange={setDraft} />
              </div>
              <div className="border-t border-gray-800 p-2">
                <div className="flex items-center gap-2">
                  <input
                    className="flex-1 rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-200"
                    placeholder="Ask AI to change this file — e.g. add input validation and error handling"
                    value={aiInstruction}
                    onChange={(e) => setAiInstruction(e.target.value)}
                    disabled={busy}
                  />
                  <Button size="sm" disabled={busy || !aiInstruction.trim()} onClick={() => void handleAiEdit()}>
                    <i className="ti ti-sparkles mr-1" aria-hidden /> Apply AI
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
