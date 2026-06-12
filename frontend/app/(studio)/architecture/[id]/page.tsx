"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArchitectureDocView } from "@/components/features/architecture/ArchitectureDocView";
import type { ArchDocKey } from "@/components/features/architecture/ArchitecturePrintDocument";
import { AiStatusBar } from "@/components/ui/AiStatusBar";
import { Button } from "@/components/ui/button";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import { Toast } from "@/components/ui/Toast";
import { api, type Architecture, type Project } from "@/lib/api";
import { exportArchitecturePdf } from "@/lib/architecturePdfExport";
import { useAiJob } from "@/lib/hooks/useAiJob";

const DOC_TABS = [
  { key: "doc_system_arch", label: "System", title: "System architecture" },
  { key: "doc_database", label: "Database", title: "Database design" },
  { key: "doc_api", label: "API", title: "API specification" },
  { key: "doc_frontend", label: "Frontend", title: "Frontend architecture" },
  { key: "doc_security", label: "Security", title: "Security and RBAC" },
  { key: "doc_uiux", label: "UI/UX", title: "UI/UX design guidance" },
] as const;

type DocKey = (typeof DOC_TABS)[number]["key"];

const DOC_STATUS_LABEL: Record<string, string> = {
  pending: "Queued",
  generating: "Generating",
  completed: "Complete",
  generated: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

function statusField(key: DocKey): keyof Architecture {
  return `${key}_status` as keyof Architecture;
}

export default function ArchitectureDetailPage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const taskFromUrl = searchParams.get("task");

  const [arch, setArch] = useState<Architecture | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [activeTab, setActiveTab] = useState<DocKey>("doc_system_arch");
  const [pdfExporting, setPdfExporting] = useState(false);
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
    if (hasDocs) return;
    const taskId = taskFromUrl ?? arch.generation_task_id;
    if (!taskId) return;
    generationStarted.current = true;
    aiJob.startJob(taskId, "Generating architecture");
  }, [arch, taskFromUrl, aiJob.startJob]);

  const isGenerating = useMemo(() => {
    if (!arch) return false;
    return (
      DOC_TABS.some((t) => arch[statusField(t.key)] === "generating") ||
      aiJob.isRunning
    );
  }, [arch, aiJob.isRunning]);

  useEffect(() => {
    if (!isGenerating) return;
    const interval = window.setInterval(() => {
      void refresh();
    }, 3000);
    return () => clearInterval(interval);
  }, [isGenerating, refresh]);

  async function handleResume() {
    try {
      const result = await api.resumeArchitecture(id);
      aiJob.startJob(result.task_id, "Generating architecture");
      showToast("Resuming generation...");
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Resume failed", "error");
    }
  }

  async function handleRegenerateDoc(docKey: DocKey) {
    try {
      const result = await api.regenerateArchitectureDoc(id, docKey);
      aiJob.startJob(result.task_id, "Generating architecture");
      showToast(`Regenerating ${docKey}...`);
      await refresh();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Regenerate failed", "error");
    }
  }

  async function handleExportPdf(mode: "full" | "section") {
    if (!arch) return;
    setPdfExporting(true);
    setPdfMessage("Preparing PDF...");
    try {
      await exportArchitecturePdf({
        arch,
        projectName: project?.name ?? "Project",
        mode,
        sectionKey: mode === "section" ? (activeTab as ArchDocKey) : undefined,
        onProgress: setPdfMessage,
      });
      showToast("PDF downloaded");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "PDF export failed", "error");
    } finally {
      setPdfExporting(false);
      setPdfMessage("");
    }
  }

  if (!arch) {
    return <p className="text-gray-400">Loading architecture...</p>;
  }

  const activeTabMeta = DOC_TABS.find((t) => t.key === activeTab);

  return (
    <>
      <Toast
        message={toast.message}
        type={toast.type}
        visible={toast.visible}
        onDismiss={() => setToast((t) => ({ ...t, visible: false }))}
      />

      <div className="space-y-6 print-document">
        <div>
          <Link href="/architecture" className="text-sm text-gray-500 hover:text-gray-300">
            ← Architecture
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">
            {arch.display_name ?? `${project?.name ?? "Project"} architecture`}
          </h1>
          <p className="text-sm text-gray-500">
            v{arch.version} · {arch.status}
          </p>
        </div>

        <div className="no-print flex flex-wrap items-center gap-2">
          <ScreenModelSelector screen="architecture" />
          <Button
            variant="outline"
            disabled={pdfExporting}
            onClick={() => void handleExportPdf("full")}
          >
            {pdfExporting ? pdfMessage || "Exporting..." : "Export full PDF"}
          </Button>
          <Button
            variant="outline"
            disabled={pdfExporting}
            onClick={() => void handleExportPdf("section")}
          >
            Export section PDF
          </Button>
          <Button variant="outline" onClick={() => window.print()}>
            Print
          </Button>
          {arch.can_resume ? (
            <Button onClick={() => void handleResume()}>Resume generation</Button>
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

        {arch.last_error ? (
          <p className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">
            {arch.last_error}
          </p>
        ) : null}

        {isGenerating ? (
          <div className="no-print rounded-xl border border-gray-800 bg-gray-900 p-4">
            <h2 className="font-medium">Generating documents</h2>
            <ul className="mt-3 space-y-1 text-sm">
              {DOC_TABS.map((t) => {
                const st = String(arch[statusField(t.key)] ?? "pending");
                return (
                  <li key={t.key}>
                    {DOC_STATUS_LABEL[st] ?? st} — {t.title}
                  </li>
                );
              })}
            </ul>
            <AiStatusBar
              isVisible={aiJob.isVisible}
              status={aiJob.status}
              operationName={aiJob.operationName || "Generating architecture"}
              elapsedSeconds={aiJob.elapsedSeconds}
              tokenCount={aiJob.tokenCount}
              errorMessage={aiJob.errorMessage}
              processingMessage={aiJob.processingMessage}
              onCancel={aiJob.cancel}
            />
          </div>
        ) : null}

        <div className="no-print flex flex-wrap gap-2 border-b border-gray-800 pb-2">
          {DOC_TABS.map((t) => {
            const st = String(arch[statusField(t.key)] ?? "pending");
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setActiveTab(t.key)}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  activeTab === t.key
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {t.label}
                <span className="ml-1 text-xs text-gray-500">
                  ({DOC_STATUS_LABEL[st] ?? st})
                </span>
              </button>
            );
          })}
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
          <div className="no-print mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-medium">{activeTabMeta?.title}</h2>
            <Button
              variant="outline"
              size="sm"
              disabled={isGenerating}
              onClick={() => void handleRegenerateDoc(activeTab)}
            >
              Regenerate section
            </Button>
          </div>
          <ArchitectureDocView
            docKey={activeTab}
            doc={(arch[activeTab] as Record<string, unknown>) ?? null}
          />
        </div>

        <div className="hidden print:block">
          {DOC_TABS.map((t, i) => (
            <section key={t.key} className={i > 0 ? "print-section mt-8" : ""}>
              <h2 className="text-lg font-bold">
                {i + 1}. {t.title}
              </h2>
              <ArchitectureDocView
                docKey={t.key}
                doc={(arch[t.key] as Record<string, unknown>) ?? null}
              />
            </section>
          ))}
        </div>
      </div>
    </>
  );
}
