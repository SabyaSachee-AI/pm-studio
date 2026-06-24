"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { FinalizedBadge, finalizedBadgeClassName } from "@/components/ui/FinalizedBadge";
import { Button } from "@/components/ui/button";
import { GeneratedDocActions } from "@/components/ui/GeneratedDocActions";
import { ModelSelect } from "@/components/ui/ModelSelect";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import { Toast } from "@/components/ui/Toast";
import {
  api,
  type Client,
  type ModelChoice,
  type PRD,
  type Project,
  type SRS,
  type UserResponse,
} from "@/lib/api";
import { SrsFormalDocument } from "@/components/features/srs/SrsFormalDocument";
import {
  FORMAL_PRINT_STYLES,
  formatSrsDocumentDate,
  srsDocumentStatusLabel,
} from "@/lib/srsDocument";
import {
  aiButtonClassName,
  aiButtonLabel,
  useAiJob,
} from "@/lib/hooks/useAiJob";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const STEPS = [
  { num: 1, label: "Generate" },
  { num: 2, label: "Add Feedback" },
  { num: 3, label: "Review Draft" },
  { num: 4, label: "Confirm" },
  { num: 5, label: "Finalized" },
] as const;

type EnrichedSRS = SRS & {
  generation_task_id?: string;
  workflow_status?: string;
  source_prd_display_name?: string;
  stats?: Record<string, unknown>;
};

type SrsMeta = Record<string, unknown>;
type FrRecord = Record<string, unknown>;
type NfrRecord = Record<string, unknown>;
type QualityCheck = { item: string; passed: boolean; note?: string };
type VersionEntry = {
  version: number;
  trigger: string;
  note: string;
  created_at: string;
};

function getMeta(content: Record<string, unknown>): SrsMeta {
  return (content._meta as SrsMeta) ?? {};
}

function stripMeta(content: Record<string, unknown>): Record<string, unknown> {
  const { _meta: _, ...rest } = content;
  return rest;
}

function priorityBadge(priority: string): string {
  const p = priority.toLowerCase();
  if (p.includes("must")) return "border-red-700 bg-red-900/40 text-red-200";
  if (p.includes("should")) return "border-amber-700 bg-amber-900/40 text-amber-200";
  return "border-gray-600 bg-gray-800 text-gray-300";
}

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
              {index < STEPS.length - 1 ? <span className="text-gray-600">→</span> : null}
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

function SrsContentView({ content }: { content: Record<string, unknown> }) {
  const intro = (content.introduction as Record<string, unknown>) ?? {};
  const overall = (content.overall_description as Record<string, unknown>) ?? {};
  const frs = (content.functional_requirements as FrRecord[]) ?? [];
  const nfrs = (content.non_functional_requirements as NfrRecord[]) ?? [];
  const interfaces = (content.system_interfaces as Record<string, unknown>) ?? {};
  const dataReq = (content.data_requirements as Record<string, unknown>) ?? {};
  const entities = (dataReq.data_entities as Array<Record<string, unknown>>) ?? [];

  const nfrByCategory = nfrs.reduce<Record<string, NfrRecord[]>>((acc, nfr) => {
    const cat = String(nfr.category ?? "Other");
    acc[cat] = acc[cat] ?? [];
    acc[cat].push(nfr);
    return acc;
  }, {});

  return (
    <div className="space-y-6 text-sm text-gray-300">
      <section>
        <h3 className="font-medium text-white">1. Introduction</h3>
        <p className="mt-2">
          <span className="text-gray-500">Purpose:</span> {String(intro.purpose ?? "")}
        </p>
        <p className="mt-1">
          <span className="text-gray-500">Scope:</span> {String(intro.scope ?? "")}
        </p>
        <ul className="mt-2 list-disc pl-5">
          {((intro.definitions as string[]) ?? []).map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-white">2. Overall Description</h3>
        <p className="mt-2">{String(overall.product_perspective ?? "")}</p>
        <ul className="mt-2 list-disc pl-5">
          {((overall.product_functions as string[]) ?? []).map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
        <p className="mt-2 text-gray-500">User characteristics</p>
        <ul className="list-disc pl-5">
          {((overall.user_characteristics as string[]) ?? []).map((u, i) => (
            <li key={i}>{u}</li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-white">3. Functional Requirements</h3>
        <div className="mt-3 space-y-3">
          {frs.map((fr, i) => (
            <div
              key={String(fr.id ?? i)}
              className="rounded-lg border border-gray-800 bg-gray-950/60 p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{String(fr.id ?? `FR-${i + 1}`)}</span>
                <span className={`rounded-full border px-2 py-0.5 text-xs ${priorityBadge(String(fr.priority ?? ""))}`}>
                  {String(fr.priority ?? "")}
                </span>
                {fr.complexity ? (
                  <span className="text-xs text-gray-500">
                    Complexity: {String(fr.complexity)}
                  </span>
                ) : null}
                {fr.depends_on ? (
                  <span className="text-xs text-gray-500">
                    Depends on: {String(fr.depends_on)}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 font-medium">{String(fr.title ?? "")}</p>
              <p className="mt-1">{String(fr.description ?? "")}</p>
              <p className="mt-2 text-gray-400">Input: {String(fr.inputs ?? "—")}</p>
              <p className="text-gray-400">Processing: {String(fr.processing ?? "—")}</p>
              <p className="text-gray-400">Output: {String(fr.outputs ?? "—")}</p>
              <p className="text-gray-400">Error handling: {String(fr.error_handling ?? "—")}</p>
              {fr.linked_feature ? (
                <p className="mt-1 text-blue-400">Linked to: {String(fr.linked_feature)} (PRD)</p>
              ) : null}
              <ul className="mt-2 list-disc pl-5 text-gray-400">
                {((fr.test_criteria as string[]) ?? []).map((c, j) => (
                  <li key={j}>{c}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="font-medium text-white">4. Non-Functional Requirements</h3>
        {Object.entries(nfrByCategory).map(([category, items]) => (
          <div key={category} className="mt-3">
            <p className="text-gray-400">[{category}]</p>
            {items.map((nfr, i) => (
              <div key={i} className="mt-2 rounded border border-gray-800 p-3">
                <p className="font-mono text-xs">{String(nfr.id ?? "")}</p>
                <p>{String(nfr.description ?? "")}</p>
                <p className="text-gray-500">
                  Metric: {String(nfr.metric ?? "")} | Threshold: {String(nfr.threshold ?? "")}
                </p>
              </div>
            ))}
          </div>
        ))}
      </section>

      <section>
        <h3 className="font-medium text-white">5. System Interfaces</h3>
        <p className="mt-2">UI: {((interfaces.user_interfaces as string[]) ?? []).join(", ") || "—"}</p>
        <p>Hardware: {((interfaces.hardware_interfaces as string[]) ?? []).join(", ") || "—"}</p>
        <p>Software: {((interfaces.software_interfaces as string[]) ?? []).join(", ") || "—"}</p>
      </section>

      <section>
        <h3 className="font-medium text-white">6. Data Requirements</h3>
        {entities.map((entity, i) => (
          <div key={i} className="mt-2 rounded border border-gray-800 p-3">
            <p className="font-medium">Entity: {String(entity.name ?? "")}</p>
            <p className="text-gray-400">
              Fields: {((entity.fields as string[]) ?? []).join(", ")}
            </p>
            <p className="text-gray-400">{String(entity.relationships ?? "")}</p>
          </div>
        ))}
        <p className="mt-2 text-gray-400">Storage: {String(dataReq.data_storage ?? "—")}</p>
      </section>

      <section>
        <h3 className="font-medium text-white">7. Security Requirements</h3>
        <ul className="mt-2 list-disc pl-5">
          {((content.security_requirements as string[]) ?? []).map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-white">8. Constraints</h3>
        <ul className="mt-2 list-disc pl-5">
          {((content.constraints as string[]) ?? []).map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function TraceabilityMatrix({
  traceability,
}: {
  traceability: Record<string, unknown>;
}) {
  const matrix = (traceability.matrix as Record<string, string[]>) ?? {};
  const uncovered = (traceability.uncovered_features as string[]) ?? [];
  const entries = Object.entries(matrix);

  if (entries.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
      <h3 className="font-medium">Traceability Matrix</h3>
      {traceability.all_covered ? (
        <p className="mt-2 text-sm text-green-300">
          ✅ All PRD features have linked FRs
        </p>
      ) : (
        <p className="mt-2 text-sm text-amber-300">
          ⚠️ Uncovered features: {uncovered.join(", ") || "—"}
        </p>
      )}
      <table className="mt-3 w-full text-xs">
        <thead>
          <tr className="text-left text-gray-500">
            <th className="pb-2">PRD Feature</th>
            <th className="pb-2">SRS FRs</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([feature, frs]) => (
            <tr key={feature} className="border-t border-gray-800">
              <td className="py-2 font-mono">{feature}</td>
              <td className="py-2">{frs.length > 0 ? frs.join(", ") : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SrsDetailPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const taskFromUrl = searchParams.get("task");

  const [srs, setSrs] = useState<EnrichedSRS | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [clientName, setClientName] = useState("Client");
  const [pmUser, setPmUser] = useState<UserResponse | null>(null);
  const [prdFeatures, setPrdFeatures] = useState<string[]>([]);
  const [manualStep, setManualStep] = useState<number | null>(null);
  const [aiModel, setAiModel] = useState<ModelChoice | null>(null);
  const [pmComment, setPmComment] = useState("");
  const [qualityResult, setQualityResult] = useState<{
    score: number;
    checks: QualityCheck[];
    traceability?: Record<string, unknown>;
  } | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [changeLogOpen, setChangeLogOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState<Record<string, unknown> | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [showKbDialog, setShowKbDialog] = useState(false);
  const [kbTitle, setKbTitle] = useState("");
  const [kbProjectType, setKbProjectType] = useState("Web App");
  const [kbTags, setKbTags] = useState("");
  const [kbSaved, setKbSaved] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
    visible: boolean;
  }>({ message: "", type: "success", visible: false });
  const [portalCopied, setPortalCopied] = useState(false);

  const generationStarted = useRef(false);
  const commentKey = `srs-comment-${id}`;

  const refreshSrs = useCallback(async () => {
    const updated = (await api.getSrs(id)) as EnrichedSRS;
    setSrs(updated);
    return updated;
  }, [id]);

  const showToastMsg = useCallback(
    (msg: string, type: "success" | "error" = "success") => {
      setToast({ message: msg, type, visible: true });
    },
    [],
  );

  const aiJob = useAiJob({
    onComplete: ({ elapsedSeconds, tokenCount, operationName }) => {
      const tokenPart = tokenCount ? `, ${tokenCount.toLocaleString()} tokens` : "";
      if (operationName === "Generating SRS") {
        void refreshSrs().then(() => setManualStep(2));
        showToastMsg(`SRS generated successfully! (${elapsedSeconds}s${tokenPart})`);
      } else if (operationName === "Rewriting SRS") {
        showToastMsg(`SRS rewrite complete. (${elapsedSeconds}s${tokenPart})`);
      } else if (operationName === "SRS quality check") {
        showToastMsg(`SRS quality check complete. (${elapsedSeconds}s)`);
      } else if (operationName === "Exporting PDF") {
        showToastMsg(`PDF ready for download. (${elapsedSeconds}s)`);
      }
    },
    onFailed: ({ operationName }) => {
      showToastMsg(`${operationName} failed. Please try again.`, "error");
    },
  });

  useEffect(() => {
    void refreshSrs().then((loaded) => {
      const meta = loaded.content_json
        ? getMeta(loaded.content_json as Record<string, unknown>)
        : {};
      if (meta.quality_score != null && Array.isArray(meta.quality_checks)) {
        setQualityResult({
          score: Number(meta.quality_score),
          checks: meta.quality_checks as QualityCheck[],
          traceability: meta.traceability as Record<string, unknown> | undefined,
        });
      }
    });
    api.me().then(setPmUser).catch(() => null);
    const saved = localStorage.getItem(commentKey);
    if (saved) setPmComment(saved);
  }, [refreshSrs, commentKey]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      localStorage.setItem(commentKey, pmComment);
    }, 30_000);
    return () => clearInterval(interval);
  }, [pmComment, commentKey]);

  useEffect(() => {
    if (!srs?.project_id) return;
    Promise.all([api.listProjects(), api.listClients()]).then(
      ([projects, clients]: [Project[], Client[]]) => {
        const match = projects.find((p) => p.id === srs.project_id);
        if (match) {
          setProject(match);
          const client = clients.find((c) => c.id === match.client_id);
          if (client) setClientName(client.company_name || client.name);
        }
      },
    );
  }, [srs?.project_id]);

  useEffect(() => {
    if (!srs?.prd_id) return;
    api.getPrd(srs.prd_id).then((prd: PRD) => {
      const features = (prd.content_json?.features as Array<Record<string, unknown>>) ?? [];
      setPrdFeatures(
        features.map((f, i) => String(f.id ?? `F-${String(i + 1).padStart(3, "0")}`)),
      );
    });
  }, [srs?.prd_id]);

  useEffect(() => {
    if (!srs || srs.content_json || generationStarted.current) return;
    const taskId = taskFromUrl ?? srs.generation_task_id;
    if (!taskId) return;
    generationStarted.current = true;
    aiJob.startJob(taskId, "Generating SRS");
  }, [srs, taskFromUrl, aiJob.startJob]);

  useEffect(() => {
    if (searchParams.get("print") === "1") {
      window.setTimeout(() => window.print(), 500);
    }
  }, [searchParams]);

  const content = srs?.content_json as Record<string, unknown> | null;
  const meta = content ? getMeta(content) : {};
  const versionHistory = (meta.version_history as VersionEntry[]) ?? [];
  const rewriteCount = Number(meta.rewrite_count ?? 0);
  const isFinalized =
    meta.workflow_finalized === true ||
    srs?.workflow_status === "finalized" ||
    srs?.status === "approved";

  const derivedStep = useMemo(() => {
    if (isFinalized) return 5;
    if (showConfirmModal) return 4;
    if (qualityResult) return 3;
    if (aiJob.isRunning || !content) return 1;
    return 2;
  }, [aiJob.isRunning, content, isFinalized, qualityResult, showConfirmModal]);

  const currentStep = manualStep ?? derivedStep;
  const maxReached = isFinalized ? 5 : qualityResult ? 3 : content ? 2 : 1;
  const stats = srs?.stats ?? {};
  const qualityScore = qualityResult?.score ?? (meta.quality_score as number | undefined) ?? null;
  const traceability =
    qualityResult?.traceability ??
    (meta.traceability as Record<string, unknown> | undefined) ??
    (stats.traceability as Record<string, unknown> | undefined);

  async function runQualityCheck() {
    aiJob.startManual("SRS quality check");
    try {
      const response = await fetch(`${API_BASE}/srs/${id}/quality-check`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Quality check failed");
      const data = (await response.json()) as {
        score: number;
        checks: QualityCheck[];
        traceability: Record<string, unknown>;
      };
      setQualityResult(data);
      setManualStep(3);
      await refreshSrs();
      aiJob.completeManual();
    } catch (err) {
      aiJob.failManual(err instanceof Error ? err.message : "Quality check failed");
    }
  }

  async function runRewrite() {
    if (!pmComment.trim()) return;
    aiJob.startManual("Rewriting SRS");
    try {
      const modelQS = aiModel
        ? `?model_provider=${encodeURIComponent(aiModel.provider)}&model_id=${encodeURIComponent(aiModel.model)}`
        : "";
      const response = await fetch(`${API_BASE}/srs/${id}/rewrite${modelQS}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instructions: pmComment.trim() }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? "Rewrite failed");
      }
      const updated = (await response.json()) as EnrichedSRS;
      setSrs(updated);
      setQualityResult(null);
      setManualStep(2);
      setPmComment("");
      localStorage.removeItem(commentKey);
      aiJob.completeManual();
    } catch (err) {
      aiJob.failManual(err instanceof Error ? err.message : "Rewrite failed");
    }
  }

  async function handleExportPdf() {
    aiJob.startManual("Exporting PDF");
    try {
      window.open(api.getSrsPdfUrl(id), "_blank", "noopener,noreferrer");
      await new Promise((r) => window.setTimeout(r, 600));
      aiJob.completeManual();
    } catch (err) {
      aiJob.failManual(err instanceof Error ? err.message : "PDF export failed");
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      const response = await fetch(`${API_BASE}/srs/${id}/confirm`, {
        method: "PATCH",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Confirmation failed");
      const updated = (await response.json()) as EnrichedSRS;
      setSrs(updated);
      setShowConfirmModal(false);
      setManualStep(5);
      showToastMsg("SRS confirmed and finalized");
    } catch (err) {
      showToastMsg(err instanceof Error ? err.message : "Confirmation failed");
    } finally {
      setConfirming(false);
    }
  }

  async function handleSaveEdit() {
    if (!editContent) return;
    setSavingEdit(true);
    try {
      const response = await fetch(`${API_BASE}/srs/${id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content_json: { ...editContent, _meta: content?._meta },
          change_note: `Edited by ${pmUser?.full_name ?? "PM"}`,
        }),
      });
      if (!response.ok) throw new Error("Save failed");
      const updated = (await response.json()) as EnrichedSRS;
      setSrs(updated);
      setEditMode(false);
      setManualStep(5);
      showToastMsg("SRS updated");
    } catch (err) {
      showToastMsg(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleSaveKb() {
    try {
      const tags = [
        ...kbTags.split(",").map((t) => t.trim()).filter(Boolean),
        kbProjectType,
        "IEEE-830",
      ];
      await api.saveToKnowledge({
        source_type: "srs",
        source_id: id,
        title: kbTitle || `${project?.name ?? "Project"} SRS v${srs?.version}`,
        tags,
      });
      setKbSaved(true);
      showToastMsg("Saved to Knowledge Base");
    } catch (err) {
      showToastMsg(err instanceof Error ? err.message : "KB save failed");
    }
  }

  function updateFr(index: number, field: string, value: unknown) {
    if (!editContent) return;
    const frs = [...((editContent.functional_requirements as FrRecord[]) ?? [])];
    frs[index] = { ...frs[index], [field]: value };
    setEditContent({ ...editContent, functional_requirements: frs });
  }

  function clientApprovalUi(): ReactNode {
    const status = String(
      meta.client_approval_status ?? (srs?.status === "approved" ? "approved" : "pending"),
    );
    if (status === "approved") {
      const date = meta.client_approved_at
        ? new Date(String(meta.client_approved_at)).toLocaleDateString()
        : "";
      return (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <FinalizedBadge label="Approved" className="text-xs" />
          {date ? (
            <span className="text-sm text-gray-400">by client on {date}</span>
          ) : null}
        </div>
      );
    }
    if (status === "changes_requested") {
      return (
        <p className="text-sm text-amber-300">
          ❌ Changes requested: {String(meta.client_change_message ?? "")}
        </p>
      );
    }
    return <p className="text-sm text-gray-400">⏳ Awaiting client approval</p>;
  }

  if (!srs) return <p className="text-gray-400">Loading SRS...</p>;

  const portalUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/portal/srs/${id}`
      : `/portal/srs/${id}`;

  const confirmedBy = String(meta.confirmed_by_name ?? pmUser?.full_name ?? "PM");
  const confirmedDate = formatSrsDocumentDate(
    typeof meta.confirmed_at === "string" ? meta.confirmed_at : undefined,
  );
  const printStatusLabel = srsDocumentStatusLabel(srs?.status ?? "draft", meta);
  const clientApproved =
    srs?.status === "approved" || meta.client_approval_status === "approved";
  const clientApprovedDate =
    typeof meta.client_approved_at === "string"
      ? formatSrsDocumentDate(meta.client_approved_at)
      : undefined;

  const displayContent = content ? stripMeta(content) : null;
  const nfrByCategory = (stats.nfr_by_category as Record<string, number>) ?? {};

  const generatingSrs =
    aiJob.operationName === "Generating SRS" && aiJob.isVisible;
  const rewriteBtn = aiButtonLabel(
    "🔄 Rewrite SRS",
    aiJob.status,
    aiJob.operationName === "Rewriting SRS",
  );
  const qualityBtn = aiButtonLabel(
    "Proceed to Quality Review →",
    aiJob.status,
    aiJob.operationName === "SRS quality check",
  );
  const exportBtn = aiButtonLabel(
    "📥 Export PDF",
    aiJob.status,
    aiJob.operationName === "Exporting PDF",
  );

  return (
    <>
      <style>{`
        ${FORMAL_PRINT_STYLES}
        @keyframes progress-pulse {
          0% { opacity: 0.6; } 50% { opacity: 1; } 100% { opacity: 0.6; }
        }
        .progress-animate { animation: progress-pulse 1.5s ease-in-out infinite; }
      `}</style>

      <Toast
        message={toast.message}
        type={toast.type}
        visible={toast.visible}
        onDismiss={() => setToast((t) => ({ ...t, visible: false }))}
      />

      {showConfirmModal ? (
        <div className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-lg rounded-xl border border-gray-700 bg-gray-900 p-6">
            <h2 className="text-lg font-semibold">Confirm SRS</h2>
            <div className="mt-4 space-y-2 text-sm text-gray-400">
              <p>SRS version: v{srs.version}</p>
              <p>FR: {String(stats.fr_count ?? "—")} | NFR: {String(stats.nfr_count ?? "—")}</p>
              {qualityScore != null ? <p>Quality score: {qualityScore}/100</p> : null}
              {srs.source_prd_display_name ? (
                <p>Source PRD: {srs.source_prd_display_name}</p>
              ) : null}
              {traceability?.all_covered ? (
                <p>Traceability: All features covered</p>
              ) : (
                <p>Traceability: {String(traceability?.coverage_ratio ?? "—")} features covered</p>
              )}
            </div>
            <p className="mt-4 text-sm text-gray-300">
              Confirming SRS will lock it for development. Tasks will be auto-generated
              from FRs. Client will be notified. Are you sure?
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={() => setShowConfirmModal(false)}>Cancel</Button>
              <Button
                className="border-green-700 bg-green-800 text-green-100"
                disabled={confirming}
                onClick={() => void handleConfirm()}
              >
                {confirming ? "Confirming..." : "✅ Yes, Confirm SRS"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {showKbDialog ? (
        <div className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 p-6">
            <h2 className="text-lg font-semibold">💾 Save SRS to Knowledge Base</h2>
            {kbSaved ? (
              <div className="mt-4 space-y-3">
                <p className="text-green-300">Saved to Knowledge Base ✅</p>
                <Link href="/knowledge" className="text-sm text-blue-400 underline">
                  View in Knowledge Base →
                </Link>
                <Button onClick={() => { setShowKbDialog(false); setManualStep(5); }}>Close</Button>
              </div>
            ) : (
              <div className="mt-4 space-y-3 text-sm">
                <input
                  className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2"
                  value={kbTitle}
                  onChange={(e) => setKbTitle(e.target.value)}
                  placeholder={`${project?.name ?? "Project"} SRS v${srs.version}`}
                />
                <select
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2"
                  value={kbProjectType}
                  onChange={(e) => setKbProjectType(e.target.value)}
                >
                  {["Web App", "Mobile", "SaaS", "E-commerce", "MIS", "Other"].map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <input
                  className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2"
                  placeholder="Tags (comma separated)"
                  value={kbTags}
                  onChange={(e) => setKbTags(e.target.value)}
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => { setShowKbDialog(false); setManualStep(5); }}>
                    Cancel
                  </Button>
                  <Button onClick={() => void handleSaveKb()}>💾 Save to KB</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      <div className="flex gap-6 print-document">
        <aside className="no-print hidden w-52 shrink-0 space-y-4 lg:block">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <h3 className="text-xs font-medium uppercase text-gray-500">SRS Statistics</h3>
            <ul className="mt-3 space-y-1 text-xs text-gray-400">
              <li>Must-have FRs: {String(stats.must_have ?? 0)}</li>
              <li>Should-have: {String(stats.should_have ?? 0)}</li>
              <li>NFR categories: {String(stats.nfr_categories_count ?? 0)}/6</li>
              <li>Uncovered PRD features: {String(stats.uncovered_prd_features ?? 0)}</li>
              <li>Complexity: {String(stats.complexity ?? "—")}</li>
              <li>Rewrites: {rewriteCount}</li>
            </ul>
          </div>
        </aside>

        <div className="min-w-0 flex-1 space-y-6">
          <StepProgressBar currentStep={currentStep} maxReached={maxReached} />

          <div className="flex flex-wrap items-center justify-between gap-3 no-print">
            <h1 className="text-2xl font-semibold">{project?.name ?? "Project"} SRS</h1>
            {isFinalized ? <FinalizedBadge label="SRS finalized" /> : null}
            <div className="flex flex-wrap items-center gap-3">
              <ScreenModelSelector screen="srs" />
              <ModelSelect value={aiModel} onChange={setAiModel} />
              <GeneratedDocActions
                editHref={`/srs/${id}?step=6`}
                onDelete={async () => {
                  await api.deleteSrs(id);
                  router.push("/srs");
                }}
                onRegenerate={async () => {
                  const result = await api.regenerateSrs(id, aiModel);
                  router.push(`/srs/${id}?task=${result.task_id}`);
                }}
              />
              <span className="text-sm text-gray-500">
                v{srs.version} · IEEE 830
                {rewriteCount > 0 ? ` · Rewritten ${rewriteCount} times` : ""}
              </span>
            </div>
          </div>

          {(currentStep === 1 || generatingSrs) && !isFinalized && !content ? (
            <div className="no-print space-y-4 rounded-xl border border-gray-800 bg-gray-900 p-6">
              <p className="text-lg font-medium">🔵 Generate SRS</p>
              {srs.source_prd_display_name ? (
                <p className="text-sm text-gray-500">
                  Source PRD:{" "}
                  <Link href={`/prds/${srs.prd_id}`} className="text-blue-400 underline">
                    {srs.source_prd_display_name}
                  </Link>
                </p>
              ) : null}
              <Button
                disabled
                className={aiButtonClassName(
                  aiJob.isRunning ? "loading" : "normal",
                  "border-blue-600 bg-blue-700 text-white",
                )}
              >
                {aiJob.isRunning ? "⏳ Generating..." : "🔵 Generate SRS"}
              </Button>
              <AiStatusBar
                {...aiJobStatusBarProps(aiJob)}
                onCancel={aiJob.cancel}
                onTryAgain={() => {
                  const taskId = taskFromUrl ?? srs.generation_task_id;
                  if (taskId) aiJob.startJob(taskId, "Generating SRS");
                }}
              />
            </div>
          ) : null}

          {content && displayContent && (currentStep === 2 || currentStep === 3) && !editMode && !isFinalized ? (
            <div className="no-print space-y-6">
              {srs.source_prd_display_name ? (
                <p className="text-sm text-gray-400">Source PRD: {srs.source_prd_display_name}</p>
              ) : null}
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
                <SrsContentView content={displayContent} />
              </div>

              {currentStep === 3 && qualityResult ? (
                <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
                  <h3 className="font-medium">📊 SRS Quality Check (IEEE 830)</h3>
                  <ul className="mt-3 space-y-1 text-sm">
                    {qualityResult.checks.map((c, i) => (
                      <li key={i} className={c.passed ? "text-green-300" : "text-amber-300"}>
                        {c.passed ? "✅" : "⚠️"} {c.item}
                        {c.note ? ` — ${c.note}` : ""}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 font-medium">Score: {qualityResult.score}/100</p>
                  <p className="mt-2 text-xs text-gray-500">
                    FR count: {String(stats.fr_count ?? 0)} | NFR count:{" "}
                    {String(stats.nfr_count ?? 0)}
                    {Object.keys(nfrByCategory).length > 0
                      ? ` (${Object.entries(nfrByCategory).map(([k, v]) => `${k}: ${v}`).join(", ")})`
                      : ""}
                  </p>
                  <p className="text-xs text-gray-500">
                    Data entities: {String(stats.data_entity_count ?? 0)} | PRD traceability:{" "}
                    {String((traceability as Record<string, unknown>)?.coverage_ratio ?? "—")} features covered
                  </p>
                </div>
              ) : null}

              {traceability ? (
                <div>
                  <button
                    type="button"
                    className="text-sm text-gray-400"
                    onClick={() => setTraceOpen((o) => !o)}
                  >
                    Traceability Matrix {traceOpen ? "▲" : "▼"}
                  </button>
                  {traceOpen ? <TraceabilityMatrix traceability={traceability} /> : null}
                </div>
              ) : null}

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-green-800 bg-green-900/20 p-4">
                  <h3 className="font-medium text-green-200">✅ SRS looks correct</h3>
                  <Button
                    className={aiButtonClassName(
                      qualityBtn.variant,
                      "mt-3 border-green-700 bg-green-800 text-green-100",
                    )}
                    disabled={
                      qualityBtn.disabled ||
                      (currentStep === 2 && aiJob.isRunning)
                    }
                    onClick={() => {
                      if (currentStep === 2) void runQualityCheck();
                      else {
                        setManualStep(4);
                        setShowConfirmModal(true);
                      }
                    }}
                  >
                    {currentStep === 2 ? qualityBtn.label : "Confirm & Finalize →"}
                  </Button>
                  {aiJob.operationName === "SRS quality check" ? (
                    <AiStatusBar
                      {...aiJobStatusBarProps(aiJob)}
                      onCancel={aiJob.cancel}
                      onTryAgain={() => void runQualityCheck()}
                    />
                  ) : null}
                </div>
                <div className="rounded-xl border border-amber-800 bg-amber-900/20 p-4">
                  <h3 className="font-medium text-amber-200">💬 Request changes</h3>
                  <textarea
                    value={pmComment}
                    onChange={(e) => setPmComment(e.target.value)}
                    placeholder="Example: Add FR for voice command stop. NFR for offline performance."
                    rows={4}
                    className="mt-3 w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
                  />
                  <Button
                    className={aiButtonClassName(
                      rewriteBtn.variant,
                      "mt-3 border-amber-700 bg-amber-800 text-amber-100",
                    )}
                    disabled={rewriteBtn.disabled || !pmComment.trim()}
                    onClick={() => void runRewrite()}
                  >
                    {rewriteBtn.label}
                  </Button>
                  {aiJob.operationName === "Rewriting SRS" ? (
                    <AiStatusBar
                      {...aiJobStatusBarProps(aiJob)}
                      onCancel={aiJob.cancel}
                      onTryAgain={() => void runRewrite()}
                    />
                  ) : null}
                </div>
              </div>

              {/* Client review link — share before finalizing */}
              <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
                <p className="text-sm font-medium text-gray-300">🔗 Client review link</p>
                <p className="mt-1 text-xs text-gray-500">Share with client to collect feedback before you finalize</p>
                <div className="mt-2 flex items-center gap-2">
                  <a
                    href={portalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 truncate rounded bg-gray-950 px-2 py-1 text-xs text-blue-300 underline hover:text-blue-200"
                  >
                    {portalUrl}
                  </a>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void navigator.clipboard.writeText(portalUrl);
                      setPortalCopied(true);
                      window.setTimeout(() => setPortalCopied(false), 2000);
                    }}
                  >
                    {portalCopied ? "Copied!" : "Copy"}
                  </Button>
                </div>
              </div>

              {/* Edit SRS — manual edit before finalizing */}
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditContent({ ...displayContent, _meta: content._meta });
                    setEditMode(true);
                    setManualStep(null);
                  }}
                >
                  ✏️ Edit SRS
                </Button>
                <span className="text-xs text-gray-500">Make manual edits before finalizing</span>
              </div>

              {versionHistory.length > 0 ? (
                <div className="rounded-xl border border-gray-800 p-4">
                  <button type="button" className="text-sm text-gray-400" onClick={() => setChangeLogOpen((o) => !o)}>
                    📜 Change Log {changeLogOpen ? "▲" : "▼"}
                  </button>
                  {changeLogOpen ? (
                    <ul className="mt-2 space-y-1 text-xs text-gray-500">
                      {versionHistory.map((e) => (
                        <li key={e.version}>v{e.version}: {e.trigger} — {e.note}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {(currentStep === 5 || isFinalized) && content && displayContent && !editMode ? (
            <div className="no-print space-y-6">
              <div className="rounded-xl border border-green-800 bg-green-950/40 p-6">
                <div className="flex flex-wrap items-center gap-3">
                  <FinalizedBadge label="SRS finalized" className="text-sm" />
                </div>
                <p className="mt-1 text-sm text-gray-300">IEEE 830 Compliant</p>
                <p className="text-sm text-gray-400">
                  Version: {srs.version} | Date: {confirmedDate} | Confirmed by: {confirmedBy}
                </p>
                <p className="text-sm text-gray-400">
                  FR: {String(stats.fr_count ?? 0)} | NFR: {String(stats.nfr_count ?? 0)}
                  {qualityScore != null ? ` | Score: ${qualityScore}/100` : ""}
                </p>
                {srs.source_prd_display_name ? (
                  <p className="text-sm text-gray-500">Source PRD: {srs.source_prd_display_name}</p>
                ) : null}
                {clientApprovalUi()}
              </div>

              <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
                <p className="text-sm text-gray-400">Client review link:</p>
                <div className="mt-2 flex items-center gap-2">
                  <a
                    href={portalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 break-all rounded bg-gray-950 px-2 py-1 text-xs text-blue-300 underline hover:text-blue-200"
                  >
                    {portalUrl}
                  </a>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void navigator.clipboard.writeText(portalUrl);
                      setPortalCopied(true);
                      window.setTimeout(() => setPortalCopied(false), 2000);
                    }}
                  >
                    {portalCopied ? "Copied!" : "Copy"}
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => window.print()}>🖨️ Print SRS</Button>
                <div>
                  <Button
                    variant="outline"
                    className={aiButtonClassName(exportBtn.variant)}
                    disabled={exportBtn.disabled}
                    onClick={() => void handleExportPdf()}
                  >
                    {exportBtn.label}
                  </Button>
                  {aiJob.operationName === "Exporting PDF" ? (
                    <AiStatusBar
                      {...aiJobStatusBarProps(aiJob)}
                      onTryAgain={() => void handleExportPdf()}
                    />
                  ) : null}
                </div>
                <Button variant="outline" onClick={() => void api.submitSrs(id).then(refreshSrs)}>
                  📤 Send to Client Portal
                </Button>
                <Link href={`/tasks?project=${srs.project_id}&srs=${id}`}>
                  <Button>→ Extract Tasks &amp; Generate Kanban</Button>
                </Link>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditContent({ ...displayContent, _meta: content._meta });
                    setEditMode(true);
                    setManualStep(null);
                  }}
                >
                  ✏️ Edit SRS
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowKbDialog(true);
                    setKbTitle(`${project?.name ?? "Project"} SRS v${srs.version}`);
                  }}
                >
                  💾 Save to KB
                </Button>
              </div>

              {traceability ? <TraceabilityMatrix traceability={traceability} /> : null}
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
                <SrsContentView content={displayContent} />
              </div>
            </div>
          ) : null}

          {editMode && editContent ? (
            <div className="no-print space-y-4">
              <h2 className="text-lg font-medium">✏️ Edit SRS</h2>
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 space-y-4">
                {((editContent.functional_requirements as FrRecord[]) ?? []).map((fr, index) => (
                  <div key={index} className="rounded border border-gray-800 p-4 space-y-2">
                    <p className="font-mono text-xs">{String(fr.id ?? `FR-${index + 1}`)}</p>
                    <input
                      className="w-full rounded border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
                      value={String(fr.title ?? "")}
                      onChange={(e) => updateFr(index, "title", e.target.value)}
                      placeholder="Title"
                    />
                    <select
                      className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-sm"
                      value={String(fr.priority ?? "must-have")}
                      onChange={(e) => updateFr(index, "priority", e.target.value)}
                    >
                      <option value="must-have">must-have</option>
                      <option value="should-have">should-have</option>
                      <option value="nice-to-have">nice-to-have</option>
                    </select>
                    <textarea
                      className="w-full rounded border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
                      rows={2}
                      value={String(fr.description ?? "")}
                      onChange={(e) => updateFr(index, "description", e.target.value)}
                      placeholder="Description"
                    />
                    <textarea
                      className="w-full rounded border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
                      rows={2}
                      value={String(fr.inputs ?? "")}
                      onChange={(e) => updateFr(index, "inputs", e.target.value)}
                      placeholder="Inputs"
                    />
                    <textarea
                      className="w-full rounded border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
                      rows={2}
                      value={String(fr.processing ?? "")}
                      onChange={(e) => updateFr(index, "processing", e.target.value)}
                      placeholder="Processing"
                    />
                    <textarea
                      className="w-full rounded border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
                      rows={2}
                      value={String(fr.outputs ?? "")}
                      onChange={(e) => updateFr(index, "outputs", e.target.value)}
                      placeholder="Outputs"
                    />
                    <textarea
                      className="w-full rounded border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
                      rows={2}
                      value={String(fr.error_handling ?? "")}
                      onChange={(e) => updateFr(index, "error_handling", e.target.value)}
                      placeholder="Error handling"
                    />
                    <select
                      className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-sm"
                      value={String(fr.linked_feature ?? "")}
                      onChange={(e) => updateFr(index, "linked_feature", e.target.value || null)}
                    >
                      <option value="">Linked PRD feature</option>
                      {prdFeatures.map((fid) => (
                        <option key={fid} value={fid}>{fid}</option>
                      ))}
                    </select>
                    <select
                      className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-sm"
                      value={String(fr.complexity ?? "")}
                      onChange={(e) => updateFr(index, "complexity", e.target.value || null)}
                    >
                      <option value="">Complexity</option>
                      <option value="Simple">Simple</option>
                      <option value="Medium">Medium</option>
                      <option value="Complex">Complex</option>
                    </select>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Button disabled={savingEdit} onClick={() => void handleSaveEdit()}>
                  {savingEdit ? "Saving..." : "Save Changes"}
                </Button>
                <Button variant="outline" onClick={() => { setEditMode(false); setManualStep(5); }}>
                  Done Editing
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* PRINT DOCUMENT — A4 portrait (matches PRD) */}
      {displayContent && srs ? (
        <SrsFormalDocument
          variant="print"
          projectName={project?.name}
          clientName={clientName}
          version={srs.version}
          statusLabel={printStatusLabel}
          confirmedBy={confirmedBy}
          confirmedDate={confirmedDate}
          content={displayContent}
          sourcePrdName={srs.source_prd_display_name ?? undefined}
          frCount={Number(stats.fr_count ?? 0)}
          nfrCount={Number(stats.nfr_count ?? 0)}
          qualityScore={qualityScore}
          traceability={traceability}
          clientApproved={clientApproved}
          clientApprovedDate={clientApprovedDate}
        />
      ) : null}
    </>
  );
}
