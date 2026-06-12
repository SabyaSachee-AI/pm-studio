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
  type Requirement,
  type UserResponse,
} from "@/lib/api";
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
  { num: 6, label: "Edit" },
  { num: 7, label: "Save to KB" },
] as const;

type EnrichedPRD = PRD & {
  generation_task_id?: string;
  workflow_status?: string;
  source_requirement_name?: string;
  stats?: Record<string, unknown>;
};

type PrdMeta = Record<string, unknown>;
type FeatureRecord = Record<string, unknown>;
type StoryRecord = Record<string, unknown>;
type QualityCheck = { item: string; passed: boolean; note?: string };
type VersionEntry = {
  version: number;
  trigger: string;
  note: string;
  created_at: string;
};

function getMeta(content: Record<string, unknown>): PrdMeta {
  return (content._meta as PrdMeta) ?? {};
}

function stripMeta(content: Record<string, unknown>): Record<string, unknown> {
  const { _meta: _, ...rest } = content;
  return rest;
}

function priorityBadgeClass(priority: string): string {
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
                  isActive
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

function PrdContentView({
  content,
  editable,
  editContent,
  onEditContent,
}: {
  content: Record<string, unknown>;
  editable?: boolean;
  editContent?: Record<string, unknown>;
  onEditContent?: (next: Record<string, unknown>) => void;
}) {
  const data = editable && editContent ? editContent : content;
  const features = (data.features as FeatureRecord[]) ?? [];
  const stories = (data.user_stories as StoryRecord[]) ?? [];

  function updateField(key: string, value: unknown) {
    if (!onEditContent || !editContent) return;
    onEditContent({ ...editContent, [key]: value });
  }

  return (
    <div className="space-y-6 text-sm text-gray-300">
      <section>
        <h3 className="font-medium text-white">📋 Executive Summary</h3>
        {editable ? (
          <textarea
            className="mt-2 w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2"
            rows={4}
            value={String(data.executive_summary ?? "")}
            onChange={(e) => updateField("executive_summary", e.target.value)}
          />
        ) : (
          <p className="mt-2 whitespace-pre-wrap">{String(data.executive_summary ?? "")}</p>
        )}
      </section>

      <section>
        <h3 className="font-medium text-white">🎯 Problem Statement</h3>
        {editable ? (
          <textarea
            className="mt-2 w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2"
            rows={3}
            value={String(data.problem_statement ?? "")}
            onChange={(e) => updateField("problem_statement", e.target.value)}
          />
        ) : (
          <p className="mt-2 whitespace-pre-wrap">{String(data.problem_statement ?? "")}</p>
        )}
      </section>

      <section>
        <h3 className="font-medium text-white">👥 Target Users</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {((data.target_users as string[]) ?? []).map((user, i) => (
            <li key={i}>{user}</li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="font-medium text-white">✅ Features</h3>
        <div className="mt-3 space-y-3">
          {features.map((feature, i) => (
            <div
              key={String(feature.id ?? i)}
              className="rounded-lg border border-gray-800 bg-gray-950/60 p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-gray-800 px-2 py-0.5 text-xs font-mono">
                  {String(feature.id ?? `F-${i + 1}`)}
                </span>
                <strong>{String(feature.title ?? "")}</strong>
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs ${priorityBadgeClass(
                    String(feature.priority ?? ""),
                  )}`}
                >
                  {String(feature.priority ?? "")}
                </span>
                {feature.estimated_effort ? (
                  <span className="text-xs text-gray-500">
                    Effort: {String(feature.estimated_effort)}
                  </span>
                ) : null}
                {feature.depends_on ? (
                  <span className="text-xs text-gray-500">
                    Depends on: {String(feature.depends_on)}
                  </span>
                ) : null}
              </div>
              <p className="mt-2">{String(feature.description ?? "")}</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-gray-400">
                {((feature.acceptance_criteria as string[]) ?? []).map((c, j) => (
                  <li key={j}>{c}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="font-medium text-white">📖 User Stories</h3>
        <div className="mt-3 space-y-3">
          {stories.map((story, i) => (
            <div
              key={String(story.id ?? i)}
              className="rounded-lg border border-gray-800 p-3"
            >
              <p className="font-mono text-xs text-gray-500">
                {String(story.id ?? `US-${i + 1}`)}
              </p>
              <p className="mt-1">
                As a <strong>{String(story.as_a)}</strong>, I want to{" "}
                <strong>{String(story.i_want_to)}</strong>, so that{" "}
                <strong>{String(story.so_that)}</strong>
              </p>
            </div>
          ))}
        </div>
      </section>

      <SectionList title="⚙️ Non-Functional Requirements" items={data.non_functional_requirements} />
      <SectionList title="❌ Out of Scope" items={data.out_of_scope} />
      <SectionList title="📊 Success Metrics" items={data.success_metrics} />
      <SectionList title="⚠️ Risks" items={data.risks} />
      <SectionList title="Assumptions" items={data.assumptions} />
    </div>
  );
}

function SectionList({
  title,
  items,
}: {
  title: string;
  items: unknown;
}) {
  const list = (items as string[]) ?? [];
  if (list.length === 0) return null;
  return (
    <section>
      <h3 className="font-medium text-white">{title}</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {list.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export default function PrdDetailPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const taskFromUrl = searchParams.get("task");

  const [prd, setPrd] = useState<EnrichedPRD | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [clientName, setClientName] = useState("Client");
  const [pmUser, setPmUser] = useState<UserResponse | null>(null);
  const [manualStep, setManualStep] = useState<number | null>(null);
  const [aiModel, setAiModel] = useState<ModelChoice | null>(null);
  const [pmComment, setPmComment] = useState("");
  const [qualityResult, setQualityResult] = useState<{
    score: number;
    checks: QualityCheck[];
  } | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [changeLogOpen, setChangeLogOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState<Record<string, unknown> | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [showKbDialog, setShowKbDialog] = useState(false);
  const [kbTitle, setKbTitle] = useState("");
  const [kbProjectType, setKbProjectType] = useState("Web App");
  const [kbTags, setKbTags] = useState("");
  const [kbNotes, setKbNotes] = useState("");
  const [kbSaved, setKbSaved] = useState(false);
  const [kbItemId, setKbItemId] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
    visible: boolean;
  }>({ message: "", type: "success", visible: false });
  const [portalCopied, setPortalCopied] = useState(false);

  const generationStarted = useRef(false);
  const commentKey = `prd-comment-${id}`;

  const refreshPrd = useCallback(async () => {
    const updated = (await api.getPrd(id)) as EnrichedPRD;
    setPrd(updated);
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
      if (operationName === "Generating PRD") {
        void refreshPrd().then(() => setManualStep(2));
        showToastMsg(`PRD generated successfully! (${elapsedSeconds}s${tokenPart})`);
      } else if (operationName === "Rewriting PRD") {
        showToastMsg(`PRD rewrite complete. (${elapsedSeconds}s${tokenPart})`);
      } else if (operationName === "PRD quality check") {
        showToastMsg(`PRD quality check complete. (${elapsedSeconds}s)`);
      } else if (operationName === "Exporting PDF") {
        showToastMsg(`PDF ready for download. (${elapsedSeconds}s)`);
      }
    },
    onFailed: ({ operationName }) => {
      showToastMsg(`${operationName} failed. Please try again.`, "error");
    },
  });

  useEffect(() => {
    void refreshPrd().then((loaded) => {
      const loadedMeta = loaded.content_json
        ? getMeta(loaded.content_json as Record<string, unknown>)
        : {};
      if (
        loadedMeta.quality_score != null &&
        Array.isArray(loadedMeta.quality_checks)
      ) {
        setQualityResult({
          score: Number(loadedMeta.quality_score),
          checks: loadedMeta.quality_checks as QualityCheck[],
        });
      }
    });
    api.me().then(setPmUser).catch(() => null);
    const saved = localStorage.getItem(commentKey);
    if (saved) setPmComment(saved);
  }, [refreshPrd, commentKey]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      localStorage.setItem(commentKey, pmComment);
    }, 30_000);
    return () => clearInterval(interval);
  }, [pmComment, commentKey]);

  useEffect(() => {
    if (!prd?.project_id) return;
    Promise.all([api.listProjects(), api.listClients()]).then(
      ([projects, clients]: [Project[], Client[]]) => {
        const match = projects.find((p) => p.id === prd.project_id);
        if (match) {
          setProject(match);
          const client = clients.find((c) => c.id === match.client_id);
          if (client) setClientName(client.company_name || client.name);
        }
      },
    );
  }, [prd?.project_id]);

  useEffect(() => {
    if (!prd || prd.content_json || generationStarted.current) return;
    const taskId = taskFromUrl ?? prd.generation_task_id;
    if (!taskId) return;
    generationStarted.current = true;
    aiJob.startJob(taskId, "Generating PRD");
  }, [prd, taskFromUrl, aiJob.startJob]);

  useEffect(() => {
    if (searchParams.get("print") === "1") {
      window.setTimeout(() => window.print(), 500);
    }
  }, [searchParams]);

  const content = prd?.content_json as Record<string, unknown> | null;
  const meta = content ? getMeta(content) : {};
  const versionHistory = (meta.version_history as VersionEntry[]) ?? [];
  const rewriteCount = Number(meta.rewrite_count ?? 0);
  const isFinalized =
    meta.workflow_finalized === true ||
    prd?.workflow_status === "finalized" ||
    prd?.status === "approved";
  const isConfirmed = meta.workflow_confirmed === true || prd?.status === "submitted";

  const derivedStep = useMemo(() => {
    if (showKbDialog) return 7;
    if (editMode) return 6;
    if (isFinalized) return 5;
    if (showConfirmModal) return 4;
    if (qualityResult) return 3;
    if (aiJob.isRunning || !content) return 1;
    return 2;
  }, [
    aiJob.isRunning,
    content,
    editMode,
    isFinalized,
    qualityResult,
    showConfirmModal,
    showKbDialog,
  ]);

  const currentStep = manualStep ?? derivedStep;
  const maxReached = isFinalized ? 5 : qualityResult ? 3 : content ? 2 : 1;

  const stats = prd?.stats ?? {};
  const qualityScore =
    qualityResult?.score ?? (meta.quality_score as number | undefined) ?? null;

  async function runQualityCheck() {
    aiJob.startManual("PRD quality check");
    try {
      const response = await fetch(`${API_BASE}/prds/${id}/quality-check`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Quality check failed");
      const data = (await response.json()) as {
        score: number;
        checks: QualityCheck[];
      };
      setQualityResult(data);
      setManualStep(3);
      await refreshPrd();
      aiJob.completeManual();
    } catch (err) {
      aiJob.failManual(err instanceof Error ? err.message : "Quality check failed");
    }
  }

  async function runRewrite() {
    if (!pmComment.trim()) return;
    aiJob.startManual("Rewriting PRD");
    try {
      const modelQS = aiModel
        ? `?model_provider=${encodeURIComponent(aiModel.provider)}&model_id=${encodeURIComponent(aiModel.model)}`
        : "";
      const response = await fetch(`${API_BASE}/prds/${id}/rewrite${modelQS}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instructions: pmComment.trim() }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as {
          detail?: string;
        } | null;
        throw new Error(body?.detail ?? "Rewrite failed");
      }
      const updated = (await response.json()) as EnrichedPRD;
      setPrd(updated);
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
      window.open(api.getPrdPdfUrl(id), "_blank", "noopener,noreferrer");
      await new Promise((r) => window.setTimeout(r, 600));
      aiJob.completeManual();
    } catch (err) {
      aiJob.failManual(err instanceof Error ? err.message : "PDF export failed");
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      const response = await fetch(`${API_BASE}/prds/${id}/confirm`, {
        method: "PATCH",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Confirmation failed");
      const updated = (await response.json()) as EnrichedPRD;
      setPrd(updated);
      setShowConfirmModal(false);
      setManualStep(5);
      showToastMsg("PRD confirmed and finalized");
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
      const payload = { ...editContent, _meta: content?._meta };
      const updated = await api.updatePrd(
        id,
        payload,
        `Edited by ${pmUser?.full_name ?? "PM"}`,
      );
      setPrd(updated as EnrichedPRD);
      setEditMode(false);
      setManualStep(5);
      showToastMsg("PRD updated — new version saved");
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
      ];
      const item = await api.saveToKnowledge({
        source_type: "prd",
        source_id: id,
        title: kbTitle || `${project?.name ?? "Project"} PRD v${prd?.version}`,
        tags,
      });
      setKbSaved(true);
      setKbItemId(item.id);
      showToastMsg("Saved to Knowledge Base");
    } catch (err) {
      showToastMsg(err instanceof Error ? err.message : "KB save failed");
    }
  }

  function clientApprovalUi(): ReactNode {
    const status = String(
      meta.client_approval_status ??
        (prd?.status === "approved" ? "approved" : "pending"),
    );
    if (status === "approved") {
      const date = meta.client_approved_at
        ? new Date(String(meta.client_approved_at)).toLocaleDateString()
        : "";
      return (
        <p className="text-sm text-green-300">
          ✅ Approved by client{date ? ` on ${date}` : ""}
        </p>
      );
    }
    if (status === "changes_requested") {
      return (
        <p className="text-sm text-amber-300">
          ❌ Client requested changes: {String(meta.client_change_message ?? "")}
        </p>
      );
    }
    return <p className="text-sm text-gray-400">⏳ Awaiting client approval</p>;
  }

  if (!prd) {
    return <p className="text-gray-400">Loading PRD...</p>;
  }

  const portalUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/portal/prd/${id}`
      : `/portal/prd/${id}`;

  const confirmedBy = String(meta.confirmed_by_name ?? pmUser?.full_name ?? "PM");
  const confirmedDate = meta.confirmed_at
    ? new Date(String(meta.confirmed_at)).toLocaleDateString(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : new Date().toLocaleDateString();

  const displayContent = content ? stripMeta(content) : null;

  const generatingPrd =
    aiJob.operationName === "Generating PRD" && aiJob.isVisible;
  const rewriteBtn = aiButtonLabel(
    "🔄 Rewrite PRD",
    aiJob.status,
    aiJob.operationName === "Rewriting PRD",
  );
  const qualityBtn = aiButtonLabel(
    "Proceed to Quality Review →",
    aiJob.status,
    aiJob.operationName === "PRD quality check",
  );
  const exportBtn = aiButtonLabel(
    "📥 Export PDF",
    aiJob.status,
    aiJob.operationName === "Exporting PDF",
  );

  return (
    <>
      <style>{`
        @page { size: A4 landscape; margin: 1.5cm; }
        @media print {
          aside, header, nav, .no-print { display: none !important; }
          main { padding: 0 !important; overflow: visible !important; }
          body { background: #fff !important; color: #000 !important; }
          .print-document { color: #000 !important; background: #fff !important; }
          .print-only { display: block !important; }
        }
        .print-only { display: none; }
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
            <h2 className="text-lg font-semibold">Confirm PRD</h2>
            <div className="mt-4 space-y-2 text-sm text-gray-400">
              <p>PRD version: Version {prd.version} (rewritten {rewriteCount} times)</p>
              <p>
                Features: {String(stats.feature_count ?? "—")} | User stories:{" "}
                {String(stats.user_story_count ?? "—")}
              </p>
              {qualityScore != null ? <p>Quality score: {qualityScore}/100</p> : null}
              {prd.source_requirement_name ? (
                <p>Source requirement: {prd.source_requirement_name}</p>
              ) : null}
            </div>
            <p className="mt-4 text-sm text-gray-300">
              Confirming will lock this PRD for SRS generation. Client will be
              notified via portal. Are you sure?
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={() => setShowConfirmModal(false)}>
                Cancel
              </Button>
              <Button
                className="border-green-700 bg-green-800 text-green-100"
                disabled={confirming}
                onClick={() => void handleConfirm()}
              >
                {confirming ? "Confirming..." : "✅ Yes, Confirm PRD"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {showKbDialog ? (
        <div className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 p-6">
            <h2 className="text-lg font-semibold">💾 Save PRD to Knowledge Base</h2>
            {kbSaved ? (
              <div className="mt-4 space-y-3">
                <p className="text-green-300">Saved to Knowledge Base ✅</p>
                {kbItemId ? (
                  <Link href="/knowledge" className="text-sm text-blue-400 underline">
                    View in Knowledge Base →
                  </Link>
                ) : null}
                <Button onClick={() => { setShowKbDialog(false); setManualStep(5); }}>
                  Close
                </Button>
              </div>
            ) : (
              <div className="mt-4 space-y-3 text-sm">
                <label className="block">
                  Title
                  <input
                    className="mt-1 w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2"
                    value={kbTitle}
                    onChange={(e) => setKbTitle(e.target.value)}
                    placeholder={`${project?.name ?? "Project"} PRD v${prd.version}`}
                  />
                </label>
                <label className="block">
                  Project type
                  <select
                    className="mt-1 w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2"
                    value={kbProjectType}
                    onChange={(e) => setKbProjectType(e.target.value)}
                  >
                    {["Web App", "Mobile", "SaaS", "E-commerce", "MIS", "Other"].map(
                      (t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <label className="block">
                  Tags (comma separated)
                  <input
                    className="mt-1 w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2"
                    value={kbTags}
                    onChange={(e) => setKbTags(e.target.value)}
                  />
                </label>
                <label className="block">
                  Notes
                  <textarea
                    className="mt-1 w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2"
                    rows={2}
                    value={kbNotes}
                    onChange={(e) => setKbNotes(e.target.value)}
                  />
                </label>
                <p className="text-xs text-gray-500">
                  Saves: full PRD, feature list, user story templates, acceptance
                  criteria patterns
                </p>
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => { setShowKbDialog(false); setManualStep(5); }}
                  >
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
            <h3 className="text-xs font-medium uppercase text-gray-500">
              PRD Statistics
            </h3>
            <ul className="mt-3 space-y-1 text-xs text-gray-400">
              <li>Must-have: {String(stats.must_have ?? 0)}</li>
              <li>Should-have: {String(stats.should_have ?? 0)}</li>
              <li>Nice-to-have: {String(stats.nice_to_have ?? 0)}</li>
              <li>
                Acceptance criteria: {String(stats.acceptance_criteria_count ?? 0)}
              </li>
              <li>Complexity: {String(stats.complexity ?? "—")}</li>
              <li>Rewrites: {rewriteCount}</li>
            </ul>
          </div>
          {versionHistory.length > 0 ? (
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <button
                type="button"
                className="text-xs font-medium uppercase text-gray-500"
                onClick={() => setHistoryOpen((o) => !o)}
              >
                📜 Version History {historyOpen ? "▲" : "▼"}
              </button>
              {historyOpen ? (
                <ul className="mt-2 space-y-2 text-xs text-gray-400">
                  {[...versionHistory].reverse().map((entry) => (
                    <li key={entry.version}>
                      v{entry.version} — {entry.trigger}
                      <span className="block text-[10px] text-gray-600">
                        {new Date(entry.created_at).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </aside>

        <div className="min-w-0 flex-1 space-y-6">
          <StepProgressBar currentStep={currentStep} maxReached={maxReached} />

          <div className="flex flex-wrap items-center justify-between gap-3 no-print">
            <h1 className="text-2xl font-semibold">
              {project?.name ?? "Project"} PRD
            </h1>
            <div className="flex flex-wrap items-center gap-3">
              <ScreenModelSelector screen="prds" />
              <ModelSelect value={aiModel} onChange={setAiModel} />
              <GeneratedDocActions
                editHref={`/prds/${id}?step=6`}
                onDelete={async () => {
                  await api.deletePrd(id);
                  router.push("/prds");
                }}
                onRegenerate={async () => {
                  const result = await api.regeneratePrd(id, aiModel);
                  router.push(`/prds/${id}?task=${result.task_id}`);
                }}
              />
              <span className="text-sm text-gray-500">
                v{prd.version}
                {rewriteCount > 0 ? ` · Rewritten ${rewriteCount} times` : ""}
              </span>
            </div>
          </div>

          {/* STEP 1 — GENERATE */}
          {(currentStep === 1 || generatingPrd) && !isFinalized && !content ? (
            <div className="no-print space-y-4 rounded-xl border border-gray-800 bg-gray-900 p-6">
              <p className="text-lg font-medium">🔵 Generate PRD</p>
              {prd.source_requirement_name ? (
                <p className="text-sm text-gray-500">
                  Source requirement:{" "}
                  {prd.requirement_id ? (
                    <Link
                      href={`/requirements/${prd.requirement_id}`}
                      className="text-blue-400 underline"
                    >
                      {prd.source_requirement_name}
                    </Link>
                  ) : (
                    prd.source_requirement_name
                  )}
                </p>
              ) : null}
              <Button
                disabled
                className={aiButtonClassName(
                  aiJob.isRunning ? "loading" : "normal",
                  "border-blue-600 bg-blue-700 text-white",
                )}
              >
                {aiJob.isRunning ? "⏳ Generating..." : "🔵 Generate PRD"}
              </Button>
              <AiStatusBar
                {...aiJobStatusBarProps(aiJob)}
                onCancel={aiJob.cancel}
                onTryAgain={() => {
                  const taskId = taskFromUrl ?? prd.generation_task_id;
                  if (taskId) aiJob.startJob(taskId, "Generating PRD");
                }}
              />
            </div>
          ) : null}

          {/* STEP 2 / 3 — REVIEW */}
          {content &&
          displayContent &&
          (currentStep === 2 || currentStep === 3) &&
          !editMode &&
          !isFinalized ? (
            <div className="no-print space-y-6">
              {currentStep > 2 ? (
                <button
                  type="button"
                  className="text-sm text-gray-400 hover:text-gray-200"
                  onClick={() => { setManualStep(2); setQualityResult(null); }}
                >
                  ← Back to review
                </button>
              ) : null}

              {prd.source_requirement_name ? (
                <p className="text-sm text-gray-400">
                  📄 Source: {prd.source_requirement_name}
                  {meta.generated_at ? (
                    <span className="ml-2 text-gray-600">
                      · Generated {new Date(String(meta.generated_at)).toLocaleString()}
                    </span>
                  ) : null}
                </p>
              ) : null}

              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
                <PrdContentView content={displayContent} />
              </div>

              {currentStep === 3 && qualityResult ? (
                <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
                  <h3 className="font-medium">📊 PRD Quality Check</h3>
                  <ul className="mt-3 space-y-1 text-sm">
                    {qualityResult.checks.map((check, i) => (
                      <li key={i} className={check.passed ? "text-green-300" : "text-amber-300"}>
                        {check.passed ? "✅" : "⚠️"} {check.item}
                        {check.note ? ` — ${check.note}` : ""}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 font-medium">Score: {qualityResult.score}/100</p>
                  <p className="mt-2 text-xs text-gray-500">
                    {String(stats.feature_count ?? 0)} features ·{" "}
                    {String(stats.user_story_count ?? 0)} user stories · Must-have:{" "}
                    {String(stats.must_have ?? 0)} | Should-have:{" "}
                    {String(stats.should_have ?? 0)} | Nice-to-have:{" "}
                    {String(stats.nice_to_have ?? 0)}
                  </p>
                </div>
              ) : null}

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-green-800 bg-green-900/20 p-4">
                  <h3 className="font-medium text-green-200">✅ PRD looks correct</h3>
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
                      if (currentStep === 2) {
                        void runQualityCheck();
                      } else {
                        setManualStep(4);
                        setShowConfirmModal(true);
                      }
                    }}
                  >
                    {currentStep === 2 ? qualityBtn.label : "Confirm & Finalize →"}
                  </Button>
                  {aiJob.operationName === "PRD quality check" ? (
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
                    placeholder="Describe what needs to change. Example: Add offline mode. Remove admin panel."
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
                  {aiJob.operationName === "Rewriting PRD" ? (
                    <AiStatusBar
                      {...aiJobStatusBarProps(aiJob)}
                      onCancel={aiJob.cancel}
                      onTryAgain={() => void runRewrite()}
                    />
                  ) : null}
                </div>
              </div>

              {versionHistory.length > 0 ? (
                <div className="rounded-xl border border-gray-800 p-4">
                  <button
                    type="button"
                    className="text-sm text-gray-400"
                    onClick={() => setChangeLogOpen((o) => !o)}
                  >
                    📜 Change Log {changeLogOpen ? "▲" : "▼"}
                  </button>
                  {changeLogOpen ? (
                    <ul className="mt-2 space-y-2 text-xs text-gray-500">
                      {versionHistory.map((entry) => (
                        <li key={entry.version}>
                          v{entry.version} — {entry.trigger}: {entry.note}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {/* STEP 5 — FINALIZED */}
          {(currentStep === 5 || isFinalized) && content && displayContent && !editMode ? (
            <div className="no-print space-y-6">
              <div className="rounded-xl border border-green-800 bg-green-900/20 p-6">
                <h2 className="text-lg font-semibold text-green-200">✅ PRD FINALIZED</h2>
                <p className="mt-2 text-sm text-gray-300">
                  Version: {prd.version} | Date: {confirmedDate}
                </p>
                <p className="text-sm text-gray-400">
                  Confirmed by: {confirmedBy} | Features: {String(stats.feature_count ?? 0)}{" "}
                  | Stories: {String(stats.user_story_count ?? 0)}
                  {qualityScore != null ? ` | Quality: ${qualityScore}/100` : ""}
                </p>
                {clientApprovalUi()}
              </div>

              <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
                <p className="text-sm text-gray-400">Client review link:</p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="flex-1 truncate rounded bg-gray-950 px-2 py-1 text-xs">
                    {portalUrl}
                  </code>
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
                <Button variant="outline" onClick={() => window.print()}>
                  🖨️ Print PRD
                </Button>
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
                <Button variant="outline" onClick={() => void api.submitPrd(id).then(refreshPrd)}>
                  📤 Send to Client Portal
                </Button>
                <Link href={`/srs?project=${prd.project_id}&prd=${id}`}>
                  <Button>→ Generate SRS</Button>
                </Link>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditContent({ ...displayContent, _meta: content._meta });
                    setEditMode(true);
                    setManualStep(6);
                  }}
                >
                  ✏️ Edit PRD
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowKbDialog(true);
                    setManualStep(7);
                    setKbTitle(`${project?.name ?? "Project"} PRD v${prd.version}`);
                  }}
                >
                  💾 Save to KB
                </Button>
              </div>

              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
                <PrdContentView content={displayContent} />
              </div>
            </div>
          ) : null}

          {/* STEP 6 — EDIT */}
          {editMode && editContent ? (
            <div className="no-print space-y-4">
              <h2 className="text-lg font-medium">✏️ Edit PRD</h2>
              <p className="text-sm text-gray-500">
                Click sections to edit. Saving creates a new version.
              </p>
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
                <PrdContentView
                  content={stripMeta(editContent)}
                  editable
                  editContent={editContent}
                  onEditContent={setEditContent}
                />
              </div>
              <div className="flex gap-2">
                <Button disabled={savingEdit} onClick={() => void handleSaveEdit()}>
                  {savingEdit ? "Saving..." : "Save Changes"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditMode(false);
                    setManualStep(5);
                  }}
                >
                  Done Editing
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* PRINT DOCUMENT */}
      {displayContent ? (
        <div className="print-only mt-8 font-serif text-black">
          <div className="text-center">
            <h1 className="text-xl font-bold">PRODUCT REQUIREMENTS DOCUMENT</h1>
          </div>
          <table className="mt-6 w-full text-sm">
            <tbody>
              <tr><td className="w-24 font-semibold">Project</td><td>{project?.name}</td></tr>
              <tr><td className="font-semibold">Client</td><td>{clientName}</td></tr>
              <tr><td className="font-semibold">Version</td><td>v{prd.version}</td></tr>
              <tr><td className="font-semibold">Date</td><td>{confirmedDate}</td></tr>
              <tr><td className="font-semibold">Prepared</td><td>{confirmedBy}</td></tr>
              <tr><td className="font-semibold">Status</td><td>FINALIZED</td></tr>
            </tbody>
          </table>
          <hr className="my-4 border-black" />
          <h2 className="text-sm font-bold">1. EXECUTIVE SUMMARY</h2>
          <p className="mt-2 text-xs whitespace-pre-wrap">{String(displayContent.executive_summary)}</p>
          <h2 className="mt-4 text-sm font-bold">2. PROBLEM STATEMENT</h2>
          <p className="mt-2 text-xs whitespace-pre-wrap">{String(displayContent.problem_statement)}</p>
          <h2 className="mt-4 text-sm font-bold">3. TARGET USERS</h2>
          <ul className="mt-2 list-disc pl-5 text-xs">
            {((displayContent.target_users as string[]) ?? []).map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
          <h2 className="mt-4 text-sm font-bold">4. FEATURES</h2>
          {((displayContent.features as FeatureRecord[]) ?? []).map((f, i) => (
            <div key={i} className="mt-2 text-xs">
              <p>
                <strong>{String(f.id)}: {String(f.title)}</strong> [{String(f.priority).toUpperCase()}]
                {f.depends_on ? ` (Depends on: ${String(f.depends_on)})` : ""}
              </p>
              <p>Description: {String(f.description)}</p>
              <p>Acceptance criteria:</p>
              <ul className="list-none pl-3">
                {((f.acceptance_criteria as string[]) ?? []).map((c, j) => (
                  <li key={j}>✓ {c}</li>
                ))}
              </ul>
            </div>
          ))}
          <h2 className="mt-4 text-sm font-bold">5. USER STORIES</h2>
          {((displayContent.user_stories as StoryRecord[]) ?? []).map((s, i) => (
            <p key={i} className="mt-2 text-xs">
              {String(s.id)}: As a {String(s.as_a)}, I want to {String(s.i_want_to)} so that {String(s.so_that)}
            </p>
          ))}
          <h2 className="mt-4 text-sm font-bold">6–9. NFR / OUT OF SCOPE / METRICS / RISKS</h2>
          <SectionList title="" items={displayContent.non_functional_requirements} />
          <SectionList title="" items={displayContent.out_of_scope} />
          <SectionList title="" items={displayContent.success_metrics} />
          <SectionList title="" items={displayContent.risks} />
          <hr className="my-4 border-black" />
          <p className="text-xs">Confirmed by: {confirmedBy} | Date: {confirmedDate}</p>
          <p className="text-xs">Signature: ___________________</p>
          <p className="mt-2 text-xs">
            Client approval: {prd.status === "approved" ? "[x] Approved" : "[ ] Pending"}
          </p>
        </div>
      ) : null}
    </>
  );
}
