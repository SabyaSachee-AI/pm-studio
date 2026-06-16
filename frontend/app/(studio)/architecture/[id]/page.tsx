"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Download,
  Pencil,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { ArchitectureDocView } from "@/components/features/architecture/ArchitectureDocView";
import { ArchitectureEditSheet } from "@/components/features/architecture/ArchitectureEditSheet";
import {
  ArchModelSelector,
  modelLabelFromProgress,
} from "@/components/ui/ArchModelSelector";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import {
  FinalizedBadge,
  WorkflowStatusBadge,
  finalizedBadgeClassName,
} from "@/components/ui/FinalizedBadge";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import { Button } from "@/components/ui/button";
import { Toast } from "@/components/ui/Toast";
import { exportArchitecturePdf } from "@/lib/architecturePdfExport";
import { api, type Architecture, type ModelChoice, type Project } from "@/lib/api";
import { useAiJob } from "@/lib/hooks/useAiJob";

const DOC_TABS = [
  { key: "doc_system_arch", label: "System architecture", short: "System" },
  { key: "doc_database", label: "Database design", short: "Database" },
  { key: "doc_api", label: "API specification", short: "API" },
  { key: "doc_frontend", label: "Frontend architecture", short: "Frontend" },
  { key: "doc_security", label: "Security + RBAC", short: "Security" },
  { key: "doc_uiux", label: "UI/UX design guidance", short: "UI/UX" },
] as const;

type DocKey = (typeof DOC_TABS)[number]["key"];

const COMPLETE_STATUSES = new Set(["completed", "generated", "saved"]);
const GENERATING_STATUSES = new Set(["generating", "processing", "rate_limited"]);

function statusField(key: DocKey): keyof Architecture {
  return `${key}_status` as keyof Architecture;
}

function docStatusKind(raw: string | null | undefined): "pending" | "generating" | "complete" | "failed" {
  const st = (raw ?? "pending").toLowerCase();
  if (COMPLETE_STATUSES.has(st)) return "complete";
  if (GENERATING_STATUSES.has(st)) return "generating";
  if (st === "failed" || st === "cancelled") return "failed";
  return "pending";
}

function statusDotClass(kind: ReturnType<typeof docStatusKind>, activeGenerating: boolean): string {
  if (kind === "complete") return "bg-green-500";
  if (kind === "failed") return "bg-red-500";
  if (kind === "generating") {
    return activeGenerating
      ? "bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.9)] animate-pulse"
      : "bg-blue-500";
  }
  return "bg-gray-500";
}

function statusLabel(kind: ReturnType<typeof docStatusKind>): string {
  if (kind === "complete") return "Complete";
  if (kind === "generating") return "Generating";
  if (kind === "failed") return "Failed";
  return "Pending";
}

function hasDocContent(arch: Architecture, key: DocKey): boolean {
  const doc = arch[key] as Record<string, unknown> | null | undefined;
  return Boolean(doc && typeof doc === "object" && Object.keys(doc).length > 0);
}

function isDocComplete(status: string, hasContent: boolean): boolean {
  if (COMPLETE_STATUSES.has(status.toLowerCase())) return true;
  return hasContent;
}

interface DocStatusRow {
  key: DocKey;
  label: string;
  title: string;
  status: string;
  hasContent: boolean;
}

const STEPS = [
  { num: 1, label: "Generate" },
  { num: 2, label: "Review" },
  { num: 3, label: "Align" },
  { num: 4, label: "Confirm" },
  { num: 5, label: "Finalized" },
] as const;

function StepProgressBar({
  currentStep,
  maxReached,
}: {
  currentStep: number;
  maxReached: number;
}) {
  return (
    <div className="no-print mb-6">
      <div className="hidden sm:flex flex-wrap items-center gap-1 text-sm">
        {STEPS.map((step, index) => {
          const isActive = step.num === currentStep;
          const isComplete = step.num < currentStep || step.num <= maxReached;
          return (
            <div key={step.num} className="flex items-center gap-1">
              <span
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  step.label === "Finalized" && (isComplete || isActive)
                    ? finalizedBadgeClassName
                    : isActive
                      ? "border-blue-500 bg-blue-900/50 text-blue-200"
                      : isComplete
                        ? "border-green-700 bg-green-900/30 text-green-300"
                        : "border-gray-700 bg-gray-900 text-gray-500"
                }`}
              >
                {isComplete && !isActive ? "✓ " : ""}
                Step {step.num}: {step.label}
              </span>
              {index < STEPS.length - 1 ? (
                <span className="text-gray-600">→</span>
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="sm:hidden text-sm text-gray-400">
        Step {currentStep} of {STEPS.length}:{" "}
        {STEPS.find((s) => s.num === currentStep)?.label}
      </p>
    </div>
  );
}

const CONSISTENCY_LABELS: Record<string, string> = {
  product_vision: "Vision",
  srs_traceability: "SRS trace",
  api_database_alignment: "API↔DB",
  api_frontend_alignment: "API↔FE",
  system_stack_alignment: "System",
  security_api_alignment: "Security",
  mvp_scope: "MVP scope",
  dev_ready: "Dev ready",
};

// Which doc tab a consistency score maps to (for click-to-edit). dev_ready spans
// the whole suite so it has no single target.
const CONSISTENCY_TARGET_DOC: Record<string, DocKey | null> = {
  product_vision: "doc_system_arch",
  srs_traceability: "doc_api",
  api_database_alignment: "doc_database",
  api_frontend_alignment: "doc_frontend",
  system_stack_alignment: "doc_system_arch",
  security_api_alignment: "doc_security",
  mvp_scope: "doc_api",
  dev_ready: null,
};

function ArchitectureSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-4 w-32 rounded bg-gray-800" />
      <div className="h-8 w-2/3 rounded bg-gray-800" />
      <div className="h-4 w-48 rounded bg-gray-800" />
      <div className="flex gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-9 w-24 rounded-md bg-gray-800" />
        ))}
      </div>
      <div className="h-64 rounded-xl bg-gray-800/80" />
    </div>
  );
}

export default function ArchitectureDetailPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const taskFromUrl = searchParams.get("task");

  const [arch, setArch] = useState<Architecture | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [activeTab, setActiveTab] = useState<DocKey>("doc_system_arch");
  const [regenModel, setRegenModel] = useState<ModelChoice | null>(null);
  const [downloadModel, setDownloadModel] = useState<ModelChoice | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfMessage, setPdfMessage] = useState("");
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
    visible: boolean;
  }>({ message: "", type: "success", visible: false });

  const generationStarted = useRef<Set<string>>(new Set());

  const clearTaskFromUrl = useCallback(() => {
    if (!taskFromUrl) return;
    router.replace(`/architecture/${id}`, { scroll: false });
  }, [id, router, taskFromUrl]);

  const showToast = useCallback(
    (message: string, type: "success" | "error" = "success") => {
      setToast({ message, type, visible: true });
    },
    [],
  );

  const refresh = useCallback(async () => {
    const updated = await api.getArchitecture(id);
    setArch(updated);
    return updated;
  }, [id]);

  const aiJob = useAiJob({
    onComplete: ({ elapsedSeconds }) => {
      void refresh();
      clearTaskFromUrl();
      showToast(`Generation complete (${elapsedSeconds}s)`);
    },
    onFailed: () => {
      clearTaskFromUrl();
      showToast("Generation failed.", "error");
    },
  });

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!arch?.project_id) return;
    api.listProjects().then((projects) => {
      setProject(projects.find((p) => p.id === arch.project_id) ?? null);
    });
  }, [arch?.project_id]);

  const completedCount = useMemo(() => {
    if (!arch) return 0;
    return DOC_TABS.filter((t) => {
      const st = String(arch[statusField(t.key)] ?? "pending");
      return isDocComplete(st, hasDocContent(arch, t.key));
    }).length;
  }, [arch]);

  const docStatuses = useMemo((): DocStatusRow[] => {
    if (!arch) return [];
    return DOC_TABS.map((t) => ({
      key: t.key,
      label: t.short,
      title: t.label,
      status: String(arch[statusField(t.key)] ?? "pending"),
      hasContent: hasDocContent(arch, t.key),
    }));
  }, [arch]);

  const missingDocs = useMemo(
    () =>
      docStatuses.filter(
        (d) =>
          !isDocComplete(d.status, d.hasContent) &&
          d.status !== "failed" &&
          !GENERATING_STATUSES.has(d.status),
      ),
    [docStatuses],
  );

  const hasFailure = docStatuses.some((d) => d.status === "failed");
  const hasRateLimit = docStatuses.some((d) => d.status === "rate_limited");

  const isGenerating = useMemo(() => {
    if (!arch) return false;
    return (
      DOC_TABS.some((t) =>
        GENERATING_STATUSES.has(String(arch[statusField(t.key)] ?? "")),
      ) || aiJob.isRunning
    );
  }, [arch, aiJob.isRunning]);

  const showDocTray =
    completedCount > 0 ||
    isGenerating ||
    missingDocs.length > 0 ||
    hasFailure ||
    hasRateLimit ||
    Boolean(arch?.can_resume);

  const progressPct = Math.round((completedCount / 6) * 100);

  const isFinalized = arch?.status === "finalized";
  const isConfirmed = arch?.status === "confirmed";
  const allDocsComplete = completedCount === 6 && missingDocs.length === 0;

  const workflowStep = useMemo(() => {
    if (isFinalized) return 5;
    if (isConfirmed) return 4;
    if (allDocsComplete && arch?.consistency_report) return 4;
    if (allDocsComplete) return 3;
    if (completedCount > 0 && !isGenerating) return 2;
    return 1;
  }, [allDocsComplete, arch?.consistency_report, completedCount, isConfirmed, isFinalized, isGenerating]);

  const maxWorkflowStep = isFinalized
    ? 5
    : isConfirmed
      ? 4
      : allDocsComplete
        ? 3
        : completedCount > 0
          ? 2
          : 1;

  useEffect(() => {
    if (!arch) return;

    const docGenerating = DOC_TABS.some((t) =>
      GENERATING_STATUSES.has(String(arch[statusField(t.key)] ?? "")),
    );
    if (!docGenerating && !aiJob.isRunning) return;

    const candidates: string[] = [];
    for (const t of DOC_TABS) {
      const tid = arch.doc_task_ids?.[t.key];
      if (tid) candidates.push(tid);
    }
    if (arch.generation_task_id) candidates.push(arch.generation_task_id);
    if (taskFromUrl && !candidates.includes(taskFromUrl)) {
      candidates.push(taskFromUrl);
    }

    for (const taskId of candidates) {
      if (generationStarted.current.has(taskId)) continue;
      generationStarted.current.add(taskId);
      const docLabel =
        DOC_TABS.find((t) => arch.doc_task_ids?.[t.key] === taskId)?.short ??
        "document";
      aiJob.startJob(
        taskId,
        docGenerating && candidates[0] === taskId
          ? `Regenerating ${docLabel}`
          : "Generating architecture",
      );
      break;
    }
  }, [arch, taskFromUrl, aiJob.isRunning, aiJob.startJob]);

  const progress = arch?.generation_progress as Record<string, unknown> | null | undefined;
  const liveDoc =
    (aiJob.taskMeta?.current_doc as DocKey | undefined) ??
    (progress?.current_doc as DocKey | undefined);
  const liveModel =
    modelLabelFromProgress(
      (aiJob.taskMeta?.current_model as string | undefined) ??
        (progress?.current_model as string | undefined),
    );
  const liveMessage =
    (aiJob.taskMeta?.message as string | undefined) ??
    (progress?.message as string | undefined) ??
    aiJob.processingMessage;
  const isRateLimitSwitch =
    aiJob.taskMeta?.phase === "rate_limited" ||
    progress?.phase === "rate_limited" ||
    (liveMessage?.includes("Rate limit") ?? false);

  useEffect(() => {
    if (!isGenerating) return;
    const interval = window.setInterval(() => {
      void refresh();
    }, 2000);
    return () => clearInterval(interval);
  }, [isGenerating, refresh]);

  useEffect(() => {
    if (liveDoc && DOC_TABS.some((t) => t.key === liveDoc)) {
      setActiveTab(liveDoc);
    }
  }, [liveDoc]);

  async function handleResume() {
    try {
      const result = await api.resumeArchitecture(id, regenModel);
      generationStarted.current.add(result.task_id);
      aiJob.startJob(result.task_id, "Generating architecture");
      showToast("Resuming generation...");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Resume failed", "error");
    }
  }

  async function handleGenerateDoc(docKey: DocKey) {
    try {
      clearTaskFromUrl();
      const result = await api.generateArchitectureDoc(id, docKey, regenModel);
      generationStarted.current.add(result.task_id);
      const label = DOC_TABS.find((t) => t.key === docKey)?.short ?? docKey;
      aiJob.startJob(result.task_id, `Generating ${label}`);
      showToast(`Generating ${DOC_TABS.find((t) => t.key === docKey)?.short ?? docKey}…`);
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Generate failed", "error");
    }
  }

  async function handleGenerateAllMissing() {
    if (missingDocs.length === 0) return;
    for (const doc of missingDocs) {
      await handleGenerateDoc(doc.key);
      break; // one at a time — user can queue rest from tray
    }
  }

  async function handleCancelDoc(docKey: DocKey) {
    try {
      await api.cancelArchitectureDoc(id, docKey);
      showToast("Cancellation requested");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Cancel failed", "error");
    }
  }

  async function handleConsolidate() {
    try {
      const result = await api.consolidateArchitecture(id);
      generationStarted.current.add(result.task_id);
      aiJob.startJob(result.task_id, "Aligning suite");
      showToast("Aligning suite canon…");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Consolidate failed", "error");
    }
  }

  async function handleReassess() {
    try {
      const result = await api.reassessArchitecture(id, regenModel);
      generationStarted.current.add(result.task_id);
      aiJob.startJob(result.task_id, "Reassessing suite");
      showToast("Reassessing suite with AI…");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Reassess failed", "error");
    }
  }

  async function handleEditSuite() {
    const instruction = window.prompt(
      "Describe the change to apply across ALL 6 architecture documents:",
      "",
    );
    if (!instruction?.trim()) return;
    try {
      const result = await api.editArchitectureSuite(id, instruction.trim(), regenModel);
      generationStarted.current.add(result.task_id);
      aiJob.startJob(result.task_id, "Editing suite with AI");
      showToast("Applying AI edits across the suite…");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Suite edit failed", "error");
    }
  }

  async function handleRegenerateDoc(docKey: DocKey) {
    try {
      clearTaskFromUrl();
      const result = await api.regenerateArchitectureDoc(id, docKey, regenModel);
      generationStarted.current.add(result.task_id);
      const label = DOC_TABS.find((t) => t.key === docKey)?.short ?? docKey;
      aiJob.startJob(result.task_id, `Regenerating ${label}`);
      showToast(`Regenerating ${docKey}...`);
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Regenerate failed", "error");
    }
  }

  async function handleDeleteDoc(docKey: DocKey) {
    if (!window.confirm("Delete this document section? Content will be cleared.")) return;
    try {
      const updated = await api.deleteArchitectureDoc(id, docKey);
      setArch(updated);
      showToast("Document cleared");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Delete failed", "error");
    }
  }

  async function buildArchForPdf(
    mode: "full" | "section",
    sectionKey?: DocKey,
  ): Promise<Architecture> {
    if (!arch) throw new Error("Architecture not loaded");
    if (!downloadModel) {
      return arch;
    }
    try {
      setPdfMessage("Enhancing report text with AI…");
      const { documents } = await api.polishArchitectureForExport(
        id,
        { mode, doc_key: sectionKey },
        downloadModel,
      );
      const merged = { ...arch } as Architecture;
      for (const [key, doc] of Object.entries(documents)) {
        (merged as unknown as Record<string, unknown>)[key] = doc;
      }
      return merged;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "AI enhance failed";
      showToast(`${msg}. Exporting with saved content.`, "error");
      return arch;
    }
  }

  async function handleDownloadSection(docKey: DocKey, title: string) {
    if (!arch) return;
    setPdfBusy(true);
    setPdfMessage(`Preparing ${title} PDF…`);
    try {
      const polishedArch = await buildArchForPdf("section", docKey);
      setPdfMessage("Rendering diagrams…");
      await exportArchitecturePdf({
        arch: polishedArch,
        projectName: project?.name ?? "Project",
        mode: "section",
        sectionKey: docKey,
        onProgress: setPdfMessage,
      });
      showToast("PDF downloaded");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "PDF export failed", "error");
    } finally {
      setPdfBusy(false);
      setPdfMessage("");
    }
  }

  async function handleDownloadFullReport() {
    if (!arch) return;
    setPdfBusy(true);
    setPdfMessage("Preparing full architecture report…");
    try {
      const polishedArch = await buildArchForPdf("full");
      setPdfMessage("Rendering diagrams…");
      await exportArchitecturePdf({
        arch: polishedArch,
        projectName: project?.name ?? "Project",
        mode: "full",
        onProgress: setPdfMessage,
      });
      showToast("Full report downloaded");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "PDF export failed", "error");
    } finally {
      setPdfBusy(false);
      setPdfMessage("");
    }
  }

  const docConsistencyIssues = useMemo(() => {
    const issues = (arch?.consistency_report?.issues ?? []) as string[];
    const keywordMap: Record<string, string[]> = {
      doc_database: ["database", "entity", "table", "db"],
      doc_frontend: ["frontend", "api_calls", "page"],
      doc_api: ["api", "endpoint", "fr coverage"],
      doc_security: ["security", "rbac", "auth", "permission"],
      doc_system_arch: ["system", "component", "microservice", "deployment"],
      doc_uiux: ["ui", "ux", "design", "style"],
    };
    const keywords = keywordMap[activeTab] ?? [];
    if (!keywords.length) return issues;
    return issues.filter((issue) =>
      keywords.some((kw) => issue.toLowerCase().includes(kw.toLowerCase())),
    );
  }, [arch?.consistency_report?.issues, activeTab]);

  if (!arch) {
    return (
      <div className="space-y-4">
        <ArchitectureSkeleton />
      </div>
    );
  }

  const activeTabMeta = DOC_TABS.find((t) => t.key === activeTab);
  const activeDoc = (arch[activeTab] as Record<string, unknown>) ?? null;
  const activeStatus = docStatusKind(String(arch[statusField(activeTab)] ?? "pending"));

  return (
    <>
      <Toast
        message={toast.message}
        type={toast.type}
        visible={toast.visible}
        onDismiss={() => setToast((t) => ({ ...t, visible: false }))}
      />

      <div className="space-y-6">
        <StepProgressBar currentStep={workflowStep} maxReached={maxWorkflowStep} />

        <div>
          <Link href="/architecture" className="text-sm text-gray-500 hover:text-gray-300">
            ← Architecture suite
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold text-white">
              {arch.display_name ?? `${project?.name ?? "Project"} architecture`}
            </h1>
            <ScreenModelSelector screen="architecture" />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <p className="text-sm text-gray-500">
              v{arch.version} · {completedCount}/6 documents
            </p>
            <WorkflowStatusBadge status={arch.status} />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <ArchModelSelector
            value={downloadModel}
            onChange={setDownloadModel}
            compact
          />
          <Button
            variant="outline"
            disabled={pdfBusy || completedCount === 0}
            onClick={() => void handleDownloadFullReport()}
          >
            <Download className="mr-2 h-4 w-4" />
            Download full architecture
          </Button>
          {arch.can_resume ? (
            <>
              <ArchModelSelector value={regenModel} onChange={setRegenModel} compact />
              <Button onClick={() => void handleResume()}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Resume generation
              </Button>
            </>
          ) : null}
          {completedCount >= 2 && !isGenerating ? (
            <Button variant="outline" onClick={() => void handleConsolidate()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Align suite canon
            </Button>
          ) : null}
          {allDocsComplete && !isGenerating ? (
            <Button variant="outline" onClick={() => void handleReassess()}>
              <Sparkles className="mr-2 h-4 w-4" />
              Reassess suite (AI)
            </Button>
          ) : null}
          {allDocsComplete && !isGenerating ? (
            <Button variant="outline" onClick={() => void handleEditSuite()}>
              <Pencil className="mr-2 h-4 w-4" />
              Edit suite with AI
            </Button>
          ) : null}
          {arch.status === "draft" && !isGenerating ? (
            <Button
              onClick={async () => {
                const updated = await api.confirmArchitecture(id);
                setArch(updated);
                showToast("Architecture confirmed");
              }}
            >
              Confirm architecture
            </Button>
          ) : null}
          {arch.status === "confirmed" ? (
            <Button
              onClick={async () => {
                const updated = await api.finalizeArchitecture(id);
                setArch(updated);
                showToast("Architecture finalized");
              }}
            >
              Finalize
            </Button>
          ) : null}
        </div>

        {arch.status === "finalized" ? (
          <div className="rounded-xl border border-green-800 bg-green-950/40 p-4">
            <FinalizedBadge label="Architecture finalized" />
          </div>
        ) : null}

        {pdfMessage ? (
          <p className="text-sm text-blue-300">{pdfMessage}</p>
        ) : null}

        {arch.last_error ? (
          <p className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">
            {arch.last_error}
          </p>
        ) : null}

        {arch.consistency_report && (arch.consistency_report.overall != null || arch.consistency_report.issues?.length) ? (
          <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-medium text-gray-200">Consistency report</h2>
                {allDocsComplete && !isGenerating ? (
                  <button
                    type="button"
                    onClick={() => void handleReassess()}
                    className="flex items-center gap-1 rounded border border-blue-900/50 bg-blue-950/20 px-2 py-0.5 text-xs text-blue-300 hover:bg-blue-950/40"
                  >
                    <Sparkles className="h-3 w-3" />
                    Reassess with AI
                  </button>
                ) : null}
              </div>
              {arch.consistency_report.overall != null ? (
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-400">
                    Overall:{" "}
                    <span className={`font-semibold ${arch.consistency_report.overall >= 8 ? "text-green-400" : arch.consistency_report.overall >= 6 ? "text-amber-400" : "text-red-400"}`}>
                      {arch.consistency_report.overall.toFixed(1)} / 10
                    </span>
                    <span className="ml-2 text-xs text-gray-500">({Math.round(arch.consistency_report.overall * 10)}%)</span>
                  </span>
                  {arch.consistency_report.fr_coverage ? (
                    <span className="text-xs text-gray-500">FR coverage: {arch.consistency_report.fr_coverage}</span>
                  ) : null}
                  {arch.consistency_report.endpoint_count != null ? (
                    <span className="text-xs text-gray-500">{arch.consistency_report.endpoint_count} endpoints</span>
                  ) : null}
                </div>
              ) : null}
            </div>
            {arch.consistency_report.scores ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(arch.consistency_report.scores).map(([key, score]) => {
                  const s = Number(score);
                  const color = s >= 8 ? "text-green-400 border-green-900/50 bg-green-950/20" : s >= 6 ? "text-amber-400 border-amber-900/50 bg-amber-950/20" : "text-red-400 border-red-900/50 bg-red-950/20";
                  const targetDoc = CONSISTENCY_TARGET_DOC[key];
                  const label = `${CONSISTENCY_LABELS[key] ?? key}: ${s.toFixed(0)}/10`;
                  if (!targetDoc) {
                    return (
                      <span
                        key={key}
                        title={`${label} — suite-wide`}
                        className={`rounded border px-2 py-0.5 text-xs ${color}`}
                      >
                        {label}
                      </span>
                    );
                  }
                  return (
                    <button
                      key={key}
                      type="button"
                      title={`${label} — click to edit ${DOC_TABS.find((t) => t.key === targetDoc)?.label ?? targetDoc}`}
                      onClick={() => {
                        setActiveTab(targetDoc);
                        setEditOpen(true);
                      }}
                      className={`rounded border px-2 py-0.5 text-xs transition-colors hover:brightness-125 ${color}`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            ) : null}
            {arch.consistency_report.issues?.length ? (
              <ul className="mt-3 list-inside list-disc text-xs text-amber-300/90">
                {arch.consistency_report.issues.slice(0, 5).map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {missingDocs.length > 0 && !isGenerating ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-800/50 bg-amber-950/30 px-4 py-3">
            <p className="text-sm text-amber-200">
              {missingDocs.length} document{missingDocs.length > 1 ? "s" : ""} missing:{" "}
              {missingDocs.map((d) => d.label).join(", ")}
            </p>
            <Button
              size="sm"
              variant="outline"
              className="border-amber-700/60 text-amber-200 hover:bg-amber-950/50"
              onClick={() => void handleGenerateAllMissing()}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              Generate first missing
            </Button>
          </div>
        ) : null}

        {showDocTray ? (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-medium text-white">
                {isGenerating ? "Generating architecture suite" : "Document generation status"}
              </h2>
              <span className="text-sm text-gray-400">
                {completedCount} of 6 complete · {progressPct}%
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-800">
              <div
                className="h-full rounded-full bg-blue-600 transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            {isGenerating ? (
              <div className="mt-4 space-y-2 text-sm">
                <p className="text-gray-300">
                  <span className="text-gray-500">Model:</span> {liveModel}
                </p>
                <p
                  className={
                    isRateLimitSwitch
                      ? "animate-pulse text-amber-300"
                      : "text-gray-400"
                  }
                >
                  {liveMessage}
                </p>
              </div>
            ) : null}
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {docStatuses.map((d) => {
                const kind = docStatusKind(d.status);
                const isLive = liveDoc === d.key && kind === "generating";
                const canGenerate =
                  !isGenerating &&
                  (kind === "pending" || (kind === "failed" && !d.hasContent));
                const canRegenerate =
                  !isGenerating &&
                  (kind === "complete" || d.hasContent) &&
                  kind !== "generating" &&
                  kind !== "pending";
                const canCancel = kind === "generating";
                return (
                  <li
                    key={d.key}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 ${
                      isLive
                        ? "border-blue-600/60 bg-blue-950/30"
                        : "border-gray-800 bg-gray-950/40"
                    }`}
                  >
                    <span
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusDotClass(kind, isLive)}`}
                    />
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left text-gray-200 hover:text-white"
                      onClick={() => setActiveTab(d.key)}
                    >
                      {d.label}
                    </button>
                    <span className="text-xs text-gray-500">{statusLabel(kind)}</span>
                    {canGenerate ? (
                      <button
                        type="button"
                        title={`Generate ${d.title}`}
                        disabled={isGenerating}
                        onClick={() => void handleGenerateDoc(d.key)}
                        className="shrink-0 rounded px-2 py-0.5 text-[11px] font-medium text-blue-300 hover:bg-blue-950/50"
                      >
                        Generate →
                      </button>
                    ) : null}
                    {canRegenerate ? (
                      <button
                        type="button"
                        title={`Regenerate ${d.title}`}
                        disabled={isGenerating}
                        onClick={() => void handleRegenerateDoc(d.key)}
                        className="shrink-0 rounded px-2 py-0.5 text-[11px] text-gray-400 hover:bg-gray-800 hover:text-gray-200"
                      >
                        ↺
                      </button>
                    ) : null}
                    {canCancel ? (
                      <button
                        type="button"
                        title="Cancel generation"
                        onClick={() => void handleCancelDoc(d.key)}
                        className="shrink-0 rounded p-0.5 text-red-400 hover:bg-red-950/40"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            {(isGenerating || aiJob.isVisible) ? (
              <AiStatusBar
                {...aiJobStatusBarProps(aiJob)}
                operationName={aiJob.operationName || "Generating architecture"}
                processingMessage={liveMessage}
                onCancel={aiJob.cancel}
              />
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-1 border-b border-gray-800 pb-2">
          {DOC_TABS.map((t) => {
            const kind = docStatusKind(String(arch[statusField(t.key)] ?? "pending"));
            const isLive = liveDoc === t.key && isGenerating;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setActiveTab(t.key)}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                  activeTab === t.key
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:bg-gray-900 hover:text-white"
                } ${isLive ? "ring-1 ring-blue-500/50" : ""}`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${statusDotClass(kind, isLive)}`}
                />
                {t.short}
              </button>
            );
          })}
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-medium text-white">{activeTabMeta?.label}</h2>
              <p className="text-xs text-gray-500">{statusLabel(activeStatus)}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!activeDoc}
                onClick={() => setEditOpen(true)}
              >
                <Pencil className="mr-1.5 h-4 w-4" />
                Edit
              </Button>
              <ArchModelSelector
                value={regenModel}
                onChange={setRegenModel}
                compact
              />
              {!activeDoc && activeStatus !== "generating" ? (
                <Button
                  size="sm"
                  disabled={isGenerating}
                  onClick={() => void handleGenerateDoc(activeTab)}
                >
                  <Sparkles className="mr-1.5 h-4 w-4" />
                  Generate
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isGenerating || activeStatus === "generating"}
                  onClick={() => void handleRegenerateDoc(activeTab)}
                >
                  <RefreshCw className="mr-1.5 h-4 w-4" />
                  Regenerate
                </Button>
              )}
              {activeStatus === "generating" ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleCancelDoc(activeTab)}
                  className="border-red-900/60 text-red-300 hover:bg-red-950/40"
                >
                  <X className="mr-1.5 h-4 w-4" />
                  Cancel
                </Button>
              ) : null}
              <ArchModelSelector
                value={downloadModel}
                onChange={setDownloadModel}
                compact
              />
              <Button
                variant="outline"
                size="sm"
                disabled={!activeDoc || pdfBusy}
                onClick={() =>
                  void handleDownloadSection(activeTab, activeTabMeta?.label ?? "Section")
                }
              >
                <Download className="mr-1.5 h-4 w-4" />
                Download section
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!activeDoc || isGenerating}
                onClick={() => void handleDeleteDoc(activeTab)}
                className="border-red-900/60 text-red-300 hover:bg-red-950/40"
              >
                <Trash2 className="mr-1.5 h-4 w-4" />
                Delete
              </Button>
            </div>
          </div>

          {activeDoc ? (
            <ArchitectureDocView docKey={activeTab} doc={activeDoc} />
          ) : activeStatus === "generating" ? (
            <div className="space-y-3 py-8 text-center">
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
              <p className="text-sm text-gray-400">Generating {activeTabMeta?.label}…</p>
              <p className="text-xs text-gray-500">{liveMessage}</p>
            </div>
          ) : (
            <div className="py-12 text-center">
              <p className="text-sm text-gray-500">No content yet for this document.</p>
              <Button
                className="mt-4"
                disabled={isGenerating}
                onClick={() => void handleGenerateDoc(activeTab)}
              >
                <Sparkles className="mr-2 h-4 w-4" />
                Generate {activeTabMeta?.short}
              </Button>
            </div>
          )}
        </div>
      </div>

      {activeDoc ? (
        <ArchitectureEditSheet
          open={editOpen}
          docKey={activeTab}
          title={activeTabMeta?.label ?? "Document"}
          architectureId={id}
          initialContent={activeDoc}
          consistencyIssues={docConsistencyIssues}
          onClose={() => setEditOpen(false)}
          onSaved={(content) => {
            setArch((prev) =>
              prev ? ({ ...prev, [activeTab]: content } as Architecture) : prev,
            );
            void refresh();
          }}
        />
      ) : null}
    </>
  );
}
