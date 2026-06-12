"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  Download,
  Pencil,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { ArchitectureDocView } from "@/components/features/architecture/ArchitectureDocView";
import { ArchitectureEditSheet } from "@/components/features/architecture/ArchitectureEditSheet";
import {
  ArchModelSelector,
  modelLabelFromProgress,
} from "@/components/ui/ArchModelSelector";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
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

  const generationStarted = useRef(false);

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
      showToast(`Generation complete (${elapsedSeconds}s)`);
    },
    onFailed: () => {
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

  useEffect(() => {
    if (!arch || generationStarted.current) return;
    const hasDocs = DOC_TABS.some((t) => arch[t.key]);
    if (hasDocs && !arch.can_resume) return;
    const taskId = taskFromUrl ?? arch.generation_task_id;
    if (!taskId) return;
    generationStarted.current = true;
    aiJob.startJob(taskId, "Generating architecture");
  }, [arch, taskFromUrl, aiJob.startJob]);

  const completedCount = useMemo(() => {
    if (!arch) return 0;
    return DOC_TABS.filter((t) => COMPLETE_STATUSES.has(String(arch[statusField(t.key)] ?? ""))).length;
  }, [arch]);

  const isGenerating = useMemo(() => {
    if (!arch) return false;
    return (
      DOC_TABS.some((t) =>
        GENERATING_STATUSES.has(String(arch[statusField(t.key)] ?? "")),
      ) || aiJob.isRunning
    );
  }, [arch, aiJob.isRunning]);

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
      aiJob.startJob(result.task_id, "Generating architecture");
      showToast("Resuming generation...");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Resume failed", "error");
    }
  }

  async function handleRegenerateDoc(docKey: DocKey) {
    try {
      const result = await api.regenerateArchitectureDoc(id, docKey, regenModel);
      aiJob.startJob(result.task_id, "Generating architecture");
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
        <div>
          <Link href="/architecture" className="text-sm text-gray-500 hover:text-gray-300">
            ← Architecture suite
          </Link>
          <h1 className="mt-1 text-2xl font-semibold text-white">
            {arch.display_name ?? `${project?.name ?? "Project"} architecture`}
          </h1>
          <p className="text-sm text-gray-500">
            v{arch.version} · {arch.status} · {completedCount}/6 documents
          </p>
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

        {pdfMessage ? (
          <p className="text-sm text-blue-300">{pdfMessage}</p>
        ) : null}

        {arch.last_error ? (
          <p className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">
            {arch.last_error}
          </p>
        ) : null}

        {isGenerating ? (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-medium text-white">Generating architecture suite</h2>
              <span className="text-sm text-gray-400">
                {completedCount} of 6 complete
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-800">
              <div
                className="h-full rounded-full bg-blue-600 transition-all duration-500"
                style={{ width: `${(completedCount / 6) * 100}%` }}
              />
            </div>
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
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {DOC_TABS.map((t) => {
                const kind = docStatusKind(String(arch[statusField(t.key)] ?? "pending"));
                const isLive = liveDoc === t.key && kind === "generating";
                return (
                  <li
                    key={t.key}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 ${
                      isLive
                        ? "border-blue-600/60 bg-blue-950/30"
                        : "border-gray-800 bg-gray-950/40"
                    }`}
                  >
                    <span
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusDotClass(kind, isLive)}`}
                    />
                    <span className="text-gray-200">{t.short}</span>
                    <span className="ml-auto text-xs text-gray-500">
                      {statusLabel(kind)}
                    </span>
                  </li>
                );
              })}
            </ul>
            <AiStatusBar
              {...aiJobStatusBarProps(aiJob)}
              operationName={aiJob.operationName || "Generating architecture"}
              processingMessage={liveMessage}
              onCancel={aiJob.cancel}
            />
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
              <Button
                variant="outline"
                size="sm"
                disabled={isGenerating}
                onClick={() => void handleRegenerateDoc(activeTab)}
              >
                <RefreshCw className="mr-1.5 h-4 w-4" />
                Regenerate
              </Button>
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
          ) : (
            <div className="animate-pulse space-y-3">
              <div className="h-4 w-full rounded bg-gray-800" />
              <div className="h-4 w-5/6 rounded bg-gray-800" />
              <div className="h-32 rounded bg-gray-800/70" />
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
