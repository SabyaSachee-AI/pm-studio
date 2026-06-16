"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Layers } from "lucide-react";
import { ArchModelSelector } from "@/components/ui/ArchModelSelector";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { WorkflowStatusBadge, finalizedBadgeClassName } from "@/components/ui/FinalizedBadge";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import { Button } from "@/components/ui/button";
import { Toast } from "@/components/ui/Toast";
import {
  api,
  type ArchitectureListItem,
  type ModelChoice,
  type PRD,
  type Project,
  type SRS,
} from "@/lib/api";
import {
  aiButtonClassName,
  aiButtonLabel,
  useAiJob,
} from "@/lib/hooks/useAiJob";

const DOC_STATUS_KEYS = [
  "doc_system_arch_status",
  "doc_database_status",
  "doc_api_status",
  "doc_frontend_status",
  "doc_security_status",
  "doc_uiux_status",
] as const;

const DOCS_TOTAL = DOC_STATUS_KEYS.length;

const STEPS = [
  { num: 1, label: "Generate" },
  { num: 2, label: "Review" },
  { num: 3, label: "Align" },
  { num: 4, label: "Confirm" },
  { num: 5, label: "Finalized" },
] as const;

function ListStepBar() {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-1 text-sm">
      {STEPS.map((step, index) => (
        <div key={step.num} className="flex items-center gap-1">
          <span
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              step.num === 1
                ? "border-blue-500 bg-blue-900/50 text-blue-200"
                : step.label === "Finalized"
                  ? finalizedBadgeClassName
                  : "border-gray-700 bg-gray-900 text-gray-500"
            }`}
          >
            Step {step.num}: {step.label}
          </span>
          {index < STEPS.length - 1 ? (
            <span className="text-gray-600">→</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function countCompletedDocs(item: ArchitectureListItem): number {
  return item.docs_generated ?? DOC_STATUS_KEYS.filter(
    (k) => item[k] === "completed" || item[k] === "generated",
  ).length;
}

function isSrsEligible(srs: SRS): boolean {
  const s = srs.status.toLowerCase();
  return s === "approved" || s === "submitted" || s === "finalized";
}

function isPrdEligible(prd: PRD): boolean {
  const s = prd.status.toLowerCase();
  return (
    (s === "approved" || s === "submitted" || s === "finalized") &&
    !!prd.content_json
  );
}

function srsHasEligiblePrd(srs: SRS, prds: PRD[]): boolean {
  const linked = prds.find((p) => p.id === srs.prd_id);
  return linked ? isPrdEligible(linked) : false;
}

function prdDisplayLabel(
  srs: SRS,
  prd: PRD | undefined,
  projectName: string,
): string {
  if (srs.source_prd_display_name?.trim()) {
    return srs.source_prd_display_name;
  }
  if (!prd) return "No linked PRD found";
  const timestamp = new Date(prd.created_at).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
  return `${projectName} PRD — v${prd.version} — ${timestamp}`;
}

export default function ArchitectureListPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [srsList, setSrsList] = useState<SRS[]>([]);
  const [prdList, setPrdList] = useState<PRD[]>([]);
  const [architectures, setArchitectures] = useState<ArchitectureListItem[]>([]);
  const [selectedSrsId, setSelectedSrsId] = useState("");
  const [generateModel, setGenerateModel] = useState<ModelChoice | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
    visible: boolean;
  }>({ message: "", type: "success", visible: false });

  const showToast = useCallback(
    (message: string, type: "success" | "error" = "success") => {
      setToast({ message, type, visible: true });
    },
    [],
  );

  const loadData = useCallback(async (pid: string) => {
    if (!pid) return;
    const [srs, prds, arch] = await Promise.all([
      api.listSrs(pid),
      api.listPrds(pid),
      api.listArchitectures(pid),
    ]);
    setSrsList(srs);
    setPrdList(prds);
    setArchitectures(arch);
  }, []);

  const aiJob = useAiJob({
    onComplete: ({ elapsedSeconds }) => {
      showToast(`Architecture suite generated (${elapsedSeconds}s)`);
      void loadData(projectId);
    },
    onFailed: () => {
      showToast("Architecture generation failed.", "error");
    },
  });

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      const fromUrl =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("project")
          : null;
      setProjectId(fromUrl || p[0]?.id || "");
    });
  }, []);

  useEffect(() => {
    if (projectId) void loadData(projectId);
  }, [projectId, loadData]);

  const eligibleSrs = useMemo(() => srsList.filter(isSrsEligible), [srsList]);
  const eligiblePrds = useMemo(() => prdList.filter(isPrdEligible), [prdList]);

  const selectedSrs = useMemo(
    () => srsList.find((s) => s.id === selectedSrsId),
    [srsList, selectedSrsId],
  );

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === projectId),
    [projects, projectId],
  );

  const linkedPrd = useMemo(() => {
    if (!selectedSrs) return null;
    return prdList.find((p) => p.id === selectedSrs.prd_id) ?? null;
  }, [selectedSrs, prdList]);

  const linkedPrdLabel = useMemo(() => {
    if (!selectedSrs) return "";
    return prdDisplayLabel(selectedSrs, linkedPrd ?? undefined, selectedProject?.name ?? "Project");
  }, [selectedSrs, linkedPrd, selectedProject?.name]);

  const canGenerate = useMemo(() => {
    if (!selectedSrs) return false;
    return isSrsEligible(selectedSrs) && srsHasEligiblePrd(selectedSrs, prdList);
  }, [selectedSrs, prdList]);

  const generateDisabledReason = useMemo(() => {
    if (!selectedSrsId) return "Select a finalized SRS";
    if (!selectedSrs || !isSrsEligible(selectedSrs)) {
      return "Requires finalized SRS and PRD";
    }
    if (!srsHasEligiblePrd(selectedSrs, prdList)) {
      return "Requires finalized SRS and PRD";
    }
    return "";
  }, [selectedSrsId, selectedSrs, prdList]);

  async function handleDelete(id: string) {
    if (!confirm("Delete this architecture suite? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await api.deleteArchitecture(id);
      setArchitectures((prev) => prev.filter((a) => a.id !== id));
    } catch {
      showToast("Failed to delete architecture.", "error");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleGenerate() {
    if (!projectId || !selectedSrsId || !canGenerate) {
      showToast(generateDisabledReason || "Select an eligible SRS first.", "error");
      return;
    }
    try {
      const result = await api.generateArchitecture(
        projectId,
        selectedSrsId,
        generateModel,
      );
      aiJob.startJob(result.task_id, "Generating architecture");
      router.push(`/architecture/${result.architecture_id}?task=${result.task_id}`);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to start generation", "error");
    }
  }

  const generateBtn = aiButtonLabel(
    "Generate architecture suite",
    aiJob.status,
    aiJob.operationName === "Generating architecture",
  );

  return (
    <div className="space-y-6">
      <Toast
        message={toast.message}
        type={toast.type}
        visible={toast.visible}
        onDismiss={() => setToast((t) => ({ ...t, visible: false }))}
      />

        <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="h-7 w-7 text-blue-400" />
          <h1 className="text-2xl font-semibold text-white">Architecture suite</h1>
          <ScreenModelSelector screen="architecture" />
        </div>
        <select
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <ListStepBar />

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
        <h2 className="font-medium text-white">Step 1 — Generate from SRS</h2>
        <p className="mt-1 text-sm text-gray-400">
          Creates 6 technical documents: system, database, API, frontend, security, UI/UX
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            Source SRS
            <select
              className="mt-1 block min-w-64 rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
              value={selectedSrsId}
              onChange={(e) => setSelectedSrsId(e.target.value)}
            >
              <option value="">Select SRS...</option>
              {eligibleSrs.map((s) => {
                const projName = selectedProject?.name ?? projects.find((p) => p.id === s.project_id)?.name ?? "";
                return (
                  <option key={s.id} value={s.id}>
                    {projName ? `${projName} — SRS v${s.version}` : `SRS v${s.version}`} ({s.status})
                  </option>
                );
              })}
            </select>
          </label>
          {selectedSrs ? (
            <label className="text-sm">
              Source PRD
              <div className="mt-1 flex min-w-64 items-center gap-2 rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200">
                <span className="min-w-0 flex-1 truncate" title={linkedPrdLabel}>
                  {linkedPrd ? linkedPrdLabel : "No linked PRD found"}
                </span>
                {linkedPrd ? (
                  <>
                    <WorkflowStatusBadge status={linkedPrd.status} />
                    <Link
                      href={`/prds/${linkedPrd.id}`}
                      className="shrink-0 text-xs text-blue-400 hover:underline"
                    >
                      Open
                    </Link>
                  </>
                ) : null}
              </div>
            </label>
          ) : null}
          <ArchModelSelector value={generateModel} onChange={setGenerateModel} />
          <div>
            <span
              title={generateDisabledReason || undefined}
              className="inline-block"
            >
              <Button
                className={aiButtonClassName(
                  generateBtn.variant,
                  "border-blue-600 bg-blue-700 text-white",
                )}
                disabled={generateBtn.disabled || !canGenerate}
                onClick={() => void handleGenerate()}
              >
                {generateBtn.label}
              </Button>
            </span>
            {aiJob.isVisible ? (
              <AiStatusBar
                {...aiJobStatusBarProps(aiJob)}
                onCancel={aiJob.cancel}
                onTryAgain={() => void handleGenerate()}
              />
            ) : null}
          </div>
        </div>
        {eligibleSrs.length === 0 ? (
          <p className="mt-3 text-sm text-amber-400">
            No confirmed SRS found — confirm an SRS before generating architecture.
          </p>
        ) : null}
        {eligibleSrs.length > 0 && eligiblePrds.length === 0 ? (
          <p className="mt-3 text-sm text-amber-400">
            No confirmed PRD found — the SRS must be linked to a confirmed PRD.
          </p>
        ) : null}
        {selectedSrsId && !canGenerate && eligiblePrds.length > 0 ? (
          <p className="mt-3 text-sm text-amber-400" title={generateDisabledReason}>
            {generateDisabledReason}
          </p>
        ) : null}
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-medium text-white">Architecture documents</h2>
        {architectures.length === 0 ? (
          <p className="text-sm text-gray-500">No architecture suites yet.</p>
        ) : (
          architectures.map((a) => {
            const done = countCompletedDocs(a);
            return (
              <div
                key={a.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-800 bg-gray-900/60 p-4"
              >
                <div>
                  <p className="font-medium text-white">
                    {a.display_name
                      ?? (selectedProject?.name
                          ? `${selectedProject.name} — Architecture v${a.version}`
                          : `Architecture v${a.version}`)}
                  </p>
                  <p className="text-xs text-gray-500">
                    {done}/{DOCS_TOTAL} documents complete
                    {a.source_srs_display_name
                      ? ` · ${a.source_srs_display_name}`
                      : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <WorkflowStatusBadge status={a.status} />
                  {a.status === "finalized" && (
                    <span title="Finalized — cannot delete">
                      <i className="ti ti-lock text-xs text-emerald-600" aria-hidden />
                    </span>
                  )}
                  <Link href={`/architecture/${a.id}`}>
                    <Button variant="outline" size="sm">
                      Open
                    </Button>
                  </Link>
                  <button
                    onClick={() => void handleDelete(a.id)}
                    disabled={a.status === "finalized" || deletingId === a.id}
                    title={a.status === "finalized" ? "Finalized architecture cannot be deleted" : "Delete architecture"}
                    className="flex h-8 w-8 items-center justify-center rounded border border-red-900/40 bg-red-950/20 text-red-500 hover:border-red-700/60 hover:bg-red-950/40 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-30 transition-colors"
                  >
                    {deletingId === a.id
                      ? <i className="ti ti-loader-2 animate-spin text-sm" aria-hidden />
                      : <i className="ti ti-trash text-sm" aria-hidden />}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
