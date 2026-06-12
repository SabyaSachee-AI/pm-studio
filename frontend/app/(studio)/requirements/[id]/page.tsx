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
import { useParams, useRouter } from "next/navigation";
import {
  BorderStyle,
  Document,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";
import { saveAs } from "file-saver";
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
  { num: 1, label: "Analysis" },
  { num: 2, label: "Client Feedback" },
  { num: 3, label: "Review Draft" },
  { num: 4, label: "Confirm" },
  { num: 5, label: "Finalized" },
] as const;

const GAP_ORDER: Record<string, number> = {
  critical: 0,
  important: 1,
  minor: 2,
};

type GapRecord = Record<string, unknown>;
type DraftRecord = Record<string, unknown>;
type DraftHistoryEntry = {
  version: number;
  draft: DraftRecord;
  created_at: string;
  trigger: string;
};

function isClientInputGap(gap: GapRecord): boolean {
  return gap.client_input !== false;
}

function formatClientQuestion(gap: GapRecord): string {
  const category = String(gap.category ?? "").trim();
  const description = String(gap.description ?? "").trim();
  const question = String(gap.question ?? "").trim();
  const prefix = category ? `[${category.toUpperCase()}] ` : "";

  if (question && description) {
    return `${prefix}${description} — Q: ${question}`;
  }
  return `${prefix}${question || description}`.trim();
}

function countGapCategories(gaps: GapRecord[]): { client: number; auto: number } {
  let client = 0;
  let auto = 0;
  for (const gap of gaps) {
    if (isClientInputGap(gap)) {
      client += 1;
    } else {
      auto += 1;
    }
  }
  return { client, auto };
}

function sortGapsBySeverity(gaps: GapRecord[]): GapRecord[] {
  return [...gaps].sort((a, b) => {
    const aOrder = GAP_ORDER[String(a.category).toLowerCase()] ?? 99;
    const bOrder = GAP_ORDER[String(b.category).toLowerCase()] ?? 99;
    return aOrder - bOrder;
  });
}

function sanitizeFilenamePart(value: string): string {
  return value.replace(/[^\w\-]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
}

function severityBadgeClass(category: string): string {
  const normalized = category.toLowerCase();
  if (normalized === "critical") {
    return "border-red-700 bg-red-900/50 text-red-200";
  }
  if (normalized === "important") {
    return "border-amber-700 bg-amber-900/40 text-amber-200";
  }
  return "border-gray-600 bg-gray-800 text-gray-300";
}

async function buildClarificationDocx(
  analysis: Record<string, unknown>,
  projectName: string,
): Promise<void> {
  const gaps = (analysis.gaps as GapRecord[]) ?? [];
  const clientGaps = gaps.filter(isClientInputGap);
  const autoGaps = gaps.filter((gap) => !isClientInputGap(gap));

  const sectionAHeader = new Paragraph({
    children: [
      new TextRun({
        text: "SECTION A — Questions Requiring Your Input",
        bold: true,
        size: 24,
      }),
    ],
    spacing: { after: 200 },
  });

  const tableHeader = new TableRow({
    children: [
      new TableCell({
        children: [
          new Paragraph({
            children: [new TextRun({ text: "Clarification Question", bold: true })],
          }),
        ],
      }),
      new TableCell({
        children: [
          new Paragraph({
            children: [new TextRun({ text: "Client Response", bold: true })],
          }),
        ],
      }),
    ],
  });

  const clientRows = clientGaps.map((gap) => {
    const question = formatClientQuestion(gap);
    return new TableRow({
      children: [
        new TableCell({ children: [new Paragraph(question)] }),
        new TableCell({ children: [new Paragraph("")] }),
      ],
    });
  });

  const sectionATable =
    clientRows.length > 0
      ? new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [tableHeader, ...clientRows],
        })
      : new Paragraph("No client input questions identified.");

  const sectionBHeader = new Paragraph({
    children: [
      new TextRun({
        text: "SECTION B — Technical Standards Applied Automatically",
        bold: true,
        size: 24,
      }),
    ],
    spacing: { before: 400, after: 200 },
  });

  const autoItems = autoGaps.flatMap((gap) => {
    const question = formatClientQuestion(gap);
    const answer = String(gap.auto_answer ?? "").trim();
    return [
      new Paragraph({
        children: [
          new TextRun({ text: "Handled by system — ", bold: true }),
          new TextRun({ text: question }),
        ],
        spacing: { after: 80 },
      }),
      new Paragraph({
        children: [new TextRun({ text: answer || "Standard technical default applied." })],
        spacing: { after: 200 },
      }),
    ];
  });

  const sectionCDivider = new Paragraph({
    border: {
      bottom: {
        color: "999999",
        space: 1,
        style: BorderStyle.SINGLE,
        size: 6,
      },
    },
    spacing: { before: 400, after: 200 },
  });

  const sectionCHeader = new Paragraph({
    children: [
      new TextRun({
        text: "SECTION C — Additional Instructions / Comments",
        bold: true,
        size: 24,
      }),
    ],
    spacing: { after: 200 },
  });

  const commentLines = Array.from({ length: 10 }, () => new Paragraph(""));

  const commentsBox = new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: {
              top: { style: BorderStyle.SINGLE, size: 1, color: "999999" },
              bottom: { style: BorderStyle.SINGLE, size: 1, color: "999999" },
              left: { style: BorderStyle.SINGLE, size: 1, color: "999999" },
              right: { style: BorderStyle.SINGLE, size: 1, color: "999999" },
            },
            children: commentLines,
          }),
        ],
      }),
    ],
  });

  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({
            children: [
              new TextRun({
                text: "Clarification Document",
                bold: true,
                size: 32,
              }),
            ],
          }),
          new Paragraph({
            children: [new TextRun({ text: `Project: ${projectName}` })],
          }),
          new Paragraph(" "),
          sectionAHeader,
          sectionATable,
          sectionBHeader,
          ...(autoItems.length > 0
            ? autoItems
            : [new Paragraph("No technical standards were auto-applied.")]),
          sectionCDivider,
          sectionCHeader,
          commentsBox,
        ],
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  const dateStamp = new Date().toISOString().slice(0, 10);
  const fileName = `Clarification_${sanitizeFilenamePart(projectName)}_${dateStamp}.docx`;
  saveAs(blob, fileName);
}

function renderDraftSections(draft: DraftRecord): ReactNode {
  const features = (draft.confirmed_features as string[]) ?? [];
  const decisions = (draft.technical_decisions as string[]) ?? [];
  const outOfScope = (draft.out_of_scope as string[]) ?? [];
  const openQuestions = (draft.open_questions as string[]) ?? [];

  return (
    <div className="space-y-5 text-sm text-gray-300 print:text-black">
      <section>
        <h3 className="font-medium text-white print:text-black">📋 Project Overview</h3>
        <p className="mt-2 whitespace-pre-wrap">{String(draft.project_overview ?? "")}</p>
      </section>
      <section>
        <h3 className="font-medium text-white print:text-black">👥 Users &amp; Roles</h3>
        <p className="mt-2 whitespace-pre-wrap">{String(draft.users_and_roles ?? "")}</p>
      </section>
      <section>
        <h3 className="font-medium text-white print:text-black">✅ Confirmed Features</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {features.map((feature, index) => (
            <li key={index}>{feature}</li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="font-medium text-white print:text-black">⚙️ Technical Decisions</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {decisions.map((decision, index) => (
            <li key={index}>{decision}</li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="font-medium text-white print:text-black">❌ Out of Scope</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {outOfScope.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </section>
      {openQuestions.length > 0 ? (
        <section>
          <h3 className="font-medium text-white print:text-black">⚠️ Still Unclear</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {openQuestions.map((question, index) => (
              <li key={index}>{question}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <section>
        <h3 className="font-medium text-white print:text-black">
          📝 What Changed from Original
        </h3>
        <p className="mt-2 whitespace-pre-wrap">{String(draft.synthesis_notes ?? "")}</p>
      </section>
    </div>
  );
}

function StepProgressBar({
  currentStep,
  isFinalized,
}: {
  currentStep: number;
  isFinalized: boolean;
}) {
  const activeStep = isFinalized ? 5 : currentStep;

  return (
    <div className="no-print mb-6">
      <div className="hidden sm:flex flex-wrap items-center gap-1 text-sm">
        {STEPS.map((step, index) => {
          const isActive = step.num === activeStep;
          const isComplete = step.num < activeStep;
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
        Step {activeStep} of {STEPS.length}:{" "}
        {STEPS.find((s) => s.num === activeStep)?.label}
      </p>
    </div>
  );
}

export default function RequirementDetailPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [req, setReq] = useState<Requirement | null>(null);
  const [aiModel, setAiModel] = useState<ModelChoice | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [clientName, setClientName] = useState("Client");
  const [pmUser, setPmUser] = useState<UserResponse | null>(null);
  const [cost, setCost] = useState<Record<string, unknown> | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [manualStep, setManualStep] = useState<number | null>(null);
  const [viewingVersion, setViewingVersion] = useState<number | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [pmComment, setPmComment] = useState("");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
    visible: boolean;
  }>({ message: "", type: "success", visible: false });
  const autoSynthesizeAttempted = useRef(false);

  const commentStorageKey = `req-comment-${id}`;

  const showToast = useCallback(
    (message: string, type: "success" | "error" = "success") => {
      setToast({ message, type, visible: true });
    },
    [],
  );

  const aiJob = useAiJob({
    onComplete: ({ elapsedSeconds, tokenCount, operationName }) => {
      const tokenPart = tokenCount ? `, ${tokenCount.toLocaleString()} tokens` : "";
      if (operationName === "Synthesizing feedback") {
        showToast(`Feedback synthesis complete! (${elapsedSeconds}s${tokenPart})`);
      } else if (operationName === "Rewriting requirement analysis") {
        showToast(`Requirement analysis updated! (${elapsedSeconds}s${tokenPart})`);
      }
    },
    onFailed: ({ operationName }) => {
      showToast(`${operationName} failed. Please try again.`, "error");
    },
  });

  const refreshRequirement = useCallback(async (requirementId: string) => {
    const updated = await api.getRequirement(requirementId);
    setReq(updated);
    const estimate = await api.getCostEstimate(requirementId).catch(() => null);
    if (estimate) setCost(estimate);
    return updated;
  }, []);

  const runSynthesize = useCallback(
    async (requirementId: string) => {
      aiJob.startManual("Synthesizing feedback");
      setManualStep(2);

      try {
        const modelQS = aiModel
          ? `?model_provider=${encodeURIComponent(aiModel.provider)}&model_id=${encodeURIComponent(aiModel.model)}`
          : "";
        const response = await fetch(
          `${API_BASE}/requirements/${requirementId}/synthesize${modelQS}`,
          {
            method: "POST",
            credentials: "include",
          },
        );
        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as {
            detail?: string;
          } | null;
          throw new Error(body?.detail ?? "Synthesis failed");
        }
        await refreshRequirement(requirementId);
        setManualStep(3);
        setViewingVersion(null);
        aiJob.completeManual();
      } catch (err) {
        setManualStep(1);
        aiJob.failManual(
          err instanceof Error ? err.message : "Synthesis failed",
        );
      }
    },
    [aiJob, refreshRequirement, aiModel],
  );

  const runReanalyze = useCallback(
    async (requirementId: string, instructions: string) => {
      aiJob.startManual("Rewriting requirement analysis");
      setManualStep(2);

      try {
        const modelQS = aiModel
          ? `?model_provider=${encodeURIComponent(aiModel.provider)}&model_id=${encodeURIComponent(aiModel.model)}`
          : "";
        const response = await fetch(
          `${API_BASE}/requirements/${requirementId}/reanalyze${modelQS}`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ instructions }),
          },
        );
        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as {
            detail?: string;
          } | null;
          throw new Error(body?.detail ?? "Reanalysis failed");
        }
        await refreshRequirement(requirementId);
        setManualStep(3);
        setViewingVersion(null);
        setPmComment("");
        localStorage.removeItem(commentStorageKey);
        aiJob.completeManual();
      } catch (err) {
        setManualStep(3);
        aiJob.failManual(
          err instanceof Error ? err.message : "Reanalysis failed",
        );
      }
    },
    [aiJob, commentStorageKey, refreshRequirement, aiModel],
  );

  useEffect(() => {
    void refreshRequirement(id);
    api.me().then(setPmUser).catch(() => null);
    const saved = localStorage.getItem(commentStorageKey);
    if (saved) setPmComment(saved);
  }, [id, refreshRequirement, commentStorageKey]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      localStorage.setItem(commentStorageKey, pmComment);
    }, 30_000);
    return () => clearInterval(interval);
  }, [pmComment, commentStorageKey]);

  useEffect(() => {
    if (!req?.project_id) return;
    Promise.all([api.listProjects(), api.listClients()]).then(
      ([projects, clients]: [Project[], Client[]]) => {
        const match = projects.find((p) => p.id === req.project_id);
        if (match) {
          setProject(match);
          const client = clients.find((c) => c.id === match.client_id);
          if (client) {
            setClientName(client.company_name || client.name);
          }
        }
      },
    );
  }, [req?.project_id]);

  useEffect(() => {
    if (!req || aiJob.isRunning || autoSynthesizeAttempted.current) return;
    const ar = req.analysis_result as Record<string, unknown> | null;
    const finalized = req.status === "finalized" || ar?.finalized === true;
    if (ar?.feedback_uploaded && !ar?.final_draft_json && !finalized) {
      autoSynthesizeAttempted.current = true;
      void runSynthesize(req.id);
    }
  }, [req, aiJob.isRunning, runSynthesize]);

  const analysis = req?.analysis_result as Record<string, unknown> | null;
  const gaps = sortGapsBySeverity((analysis?.gaps as GapRecord[]) ?? []);
  const gapCounts = useMemo(() => {
    let critical = 0;
    let important = 0;
    let minor = 0;
    for (const gap of gaps) {
      const cat = String(gap.category).toLowerCase();
      if (cat === "critical") critical += 1;
      else if (cat === "important") important += 1;
      else minor += 1;
    }
    return { critical, important, minor };
  }, [gaps]);

  const isFinalized =
    req?.status === "finalized" || analysis?.finalized === true;
  const hasDraft = Boolean(analysis?.final_draft_json);
  const draftHistory = (analysis?.draft_history as DraftHistoryEntry[]) ?? [];
  const reanalysisCount = Number(analysis?.reanalysis_count ?? 0);
  const refinedCost = analysis?.refined_cost_estimate as
    | Record<string, unknown>
    | undefined;
  const currentVersion =
    viewingVersion ??
    (draftHistory.length > 0 ? draftHistory[draftHistory.length - 1].version : 1);

  const activeDraft: DraftRecord | null = useMemo(() => {
    if (!analysis) return null;
    if (viewingVersion !== null) {
      const entry = draftHistory.find((h) => h.version === viewingVersion);
      return (entry?.draft as DraftRecord) ?? null;
    }
    return (analysis.final_draft_json as DraftRecord) ?? null;
  }, [analysis, draftHistory, viewingVersion]);

  const derivedStep = useMemo(() => {
    if (isFinalized) return 5;
    if (aiJob.isRunning) return 2;
    if (hasDraft) return 3;
    return 1;
  }, [aiJob.isRunning, hasDraft, isFinalized]);

  const currentStep = manualStep ?? derivedStep;

  if (!req) return <p className="text-gray-400">Loading...</p>;

  const { client: clientGapCount, auto: autoGapCount } = countGapCategories(gaps);
  const hasDocxContent = gaps.length > 0;
  const finalizedAt = String(analysis?.finalized_at ?? "");
  const finalizedBy = String(
    analysis?.finalized_by_name ?? pmUser?.full_name ?? "PM",
  );
  const finalizedDate = finalizedAt
    ? new Date(finalizedAt).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : new Date().toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });

  const originalText = String(
    analysis?.original_text_snapshot ?? analysis?.extracted_text ?? "",
  );
  const feedbackSummary =
    (activeDraft?.client_feedback_summary as Array<{
      question: string;
      answer: string;
    }>) ?? [];

  const uploadBtn = aiButtonLabel(
    "Choose file",
    aiJob.status,
    aiJob.operationName === "Synthesizing feedback",
  );
  const reanalyzeBtn = aiButtonLabel(
    "🔄 Analyze Again",
    aiJob.status,
    aiJob.operationName === "Rewriting requirement analysis",
  );

  return (
    <>
      <style>{`
        @page {
          size: A4 landscape;
          margin: 1.5cm;
        }
        @media print {
          aside,
          header,
          nav,
          .no-print {
            display: none !important;
          }
          main {
            padding: 0 !important;
            overflow: visible !important;
          }
          body {
            background: #fff !important;
            color: #000 !important;
          }
          .print-document {
            color: #000 !important;
            background: #fff !important;
          }
          .print-only {
            display: block !important;
          }
        }
        .print-only {
          display: none;
        }
        @keyframes progress-pulse {
          0% { opacity: 0.6; }
          50% { opacity: 1; }
          100% { opacity: 0.6; }
        }
        .progress-animate {
          animation: progress-pulse 1.5s ease-in-out infinite;
        }
      `}</style>

      <Toast
        message={toast.message}
        type={toast.type}
        visible={toast.visible}
        onDismiss={() => setToast((t) => ({ ...t, visible: false }))}
      />

      {showConfirmModal ? (
        <div className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 p-6 shadow-xl">
            <h2 className="text-lg font-semibold">Confirm finalization</h2>
            <p className="mt-3 text-sm text-gray-400">
              You are about to finalize this requirement. This will lock the
              document for PRD generation. Are you sure?
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={() => setShowConfirmModal(false)}>
                Cancel
              </Button>
              <Button
                className="border-green-700 bg-green-800 text-green-100 hover:bg-green-700"
                disabled={finalizing}
                onClick={async () => {
                  setFinalizing(true);
                  try {
                    const response = await fetch(
                      `${API_BASE}/requirements/${req.id}`,
                      {
                        method: "PATCH",
                        credentials: "include",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ status: "finalized" }),
                      },
                    );
                    if (!response.ok) {
                      const body = (await response.json().catch(() => null)) as {
                        detail?: string;
                      } | null;
                      throw new Error(body?.detail ?? "Finalization failed");
                    }
                    await refreshRequirement(req.id);
                    setShowConfirmModal(false);
                    setManualStep(5);
                    showToast("Requirement finalized");
                  } catch (err) {
                    showToast(
                      err instanceof Error ? err.message : "Finalization failed",
                      "error",
                    );
                  } finally {
                    setFinalizing(false);
                  }
                }}
              >
                {finalizing ? "Finalizing..." : "Yes, Finalize"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex gap-6 print-document">
        {draftHistory.length > 0 ? (
          <aside
            className={`no-print shrink-0 transition-all ${
              historyOpen ? "w-56" : "w-10"
            }`}
          >
            <button
              type="button"
              onClick={() => setHistoryOpen((open) => !open)}
              className="mb-2 rounded border border-gray-700 px-2 py-1 text-xs text-gray-400 hover:bg-gray-900"
              title="Version history"
            >
              {historyOpen ? "◀ History" : "▶"}
            </button>
            {historyOpen ? (
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
                <h3 className="text-xs font-medium uppercase text-gray-500">
                  Version History
                </h3>
                <ul className="mt-2 space-y-1">
                  {[...draftHistory].reverse().map((entry) => (
                    <li key={entry.version}>
                      <button
                        type="button"
                        onClick={() => {
                          setViewingVersion(entry.version);
                          setManualStep(3);
                        }}
                        className={`w-full rounded px-2 py-1 text-left text-xs hover:bg-gray-800 ${
                          currentVersion === entry.version
                            ? "bg-gray-800 text-blue-300"
                            : "text-gray-400"
                        }`}
                      >
                        Version {entry.version}
                        <span className="block text-[10px] text-gray-600">
                          {new Date(entry.created_at).toLocaleString()}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </aside>
        ) : null}

        <div className="min-w-0 flex-1 space-y-6">
          <StepProgressBar currentStep={currentStep} isFinalized={isFinalized} />

          <div className="flex flex-wrap items-center justify-between gap-3 no-print">
            <h1 className="text-2xl font-semibold">Requirements Analysis</h1>
            <div className="flex flex-wrap items-center gap-3">
              <ScreenModelSelector screen="requirements" />
              <ModelSelect value={aiModel} onChange={setAiModel} />
              <GeneratedDocActions
                showEdit={false}
                onDelete={async () => {
                  await api.deleteRequirement(id);
                  router.push("/requirements");
                }}
                onRegenerate={async () => {
                  const result = await api.regenerateRequirement(id, aiModel);
                  router.push(`/requirements/${id}?task=${result.task_id}`);
                }}
              />
              <p className="text-sm text-gray-500">{req.original_filename}</p>
            </div>
          </div>

          {/* ── STEP 5: FINALIZED ── */}
          {currentStep === 5 || isFinalized ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-full border border-green-700 bg-green-900/40 px-3 py-1 text-sm font-medium uppercase text-green-300">
                  Finalized
                </span>
                <span className="text-sm text-gray-400">
                  {finalizedDate} · {finalizedBy}
                </span>
              </div>

              {(cost || refinedCost) && (
                <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 no-print">
                  <h2 className="font-medium">Cost estimate</h2>
                  {cost ? (
                    <p className="mt-2 text-sm text-gray-300">
                      Initial estimate: ${String(cost.min_budget_usd)} – $
                      {String(cost.max_budget_usd)} {String(cost.currency)}
                    </p>
                  ) : null}
                  {refinedCost ? (
                    <p className="mt-1 text-sm text-green-300">
                      Refined estimate after feedback: $
                      {String(refinedCost.min_budget_usd)} – $
                      {String(refinedCost.max_budget_usd)}{" "}
                      {String(refinedCost.currency)}
                    </p>
                  ) : null}
                </div>
              )}

              <div className="flex flex-wrap gap-3 no-print">
                <Button variant="outline" onClick={() => window.print()}>
                  🖨️ Print Final Requirement
                </Button>
                <Link href={`/prds?project=${req.project_id}`}>
                  <Button>→ Generate PRD</Button>
                </Link>
              </div>

              {activeDraft ? (
                <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 no-print">
                  <h2 className="font-medium">Final consolidated requirement</h2>
                  <div className="mt-4">{renderDraftSections(activeDraft)}</div>
                </div>
              ) : null}
            </div>
          ) : null}

          {/* ── STEP 2: ANALYZING FEEDBACK ── */}
          {currentStep === 2 && !isFinalized ? (
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 no-print">
              <p className="text-lg font-medium">
                {aiJob.operationName || "Processing requirement..."}
              </p>
              <AiStatusBar
                {...aiJobStatusBarProps(aiJob)}
                onCancel={aiJob.cancel}
                onTryAgain={() => {
                  if (aiJob.operationName === "Rewriting requirement analysis") {
                    void runReanalyze(req.id, pmComment.trim());
                  } else {
                    void runSynthesize(req.id);
                  }
                }}
              />
            </div>
          ) : null}

          {/* ── STEP 3: REVIEW DRAFT ── */}
          {currentStep === 3 && !isFinalized && activeDraft ? (
            <div className="space-y-6 no-print">
              {currentStep > 1 ? (
                <button
                  type="button"
                  onClick={() => setManualStep(1)}
                  className="text-sm text-gray-400 hover:text-gray-200"
                >
                  ← Back to gap analysis
                </button>
              ) : null}

              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-lg font-semibold">Final Requirement Draft</h2>
                    <p className="text-sm text-gray-400">
                      Based on: Original doc + Feedback
                    </p>
                  </div>
                  <div className="text-right text-sm text-gray-500">
                    <p>Version {currentVersion}</p>
                    {reanalysisCount > 0 ? (
                      <p className="text-xs">Reanalyzed {reanalysisCount} times</p>
                    ) : null}
                  </div>
                </div>
                <div className="mt-6 border-t border-gray-800 pt-6">
                  {renderDraftSections(activeDraft)}
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-green-800 bg-green-900/20 p-4">
                  <h3 className="font-medium text-green-200">
                    ✅ This requirement is correct
                  </h3>
                  <Button
                    className="mt-3 border-green-700 bg-green-800 text-green-100 hover:bg-green-700"
                    onClick={() => {
                      setManualStep(4);
                      setShowConfirmModal(true);
                    }}
                  >
                    Confirm &amp; Finalize
                  </Button>
                </div>

                <div className="rounded-xl border border-amber-800 bg-amber-900/20 p-4">
                  <h3 className="font-medium text-amber-200">
                    💬 Not satisfied? Add instructions
                  </h3>
                  <textarea
                    value={pmComment}
                    onChange={(e) => setPmComment(e.target.value)}
                    placeholder="Describe what needs to change. PM Studio will rewrite the requirement based on your instructions..."
                    rows={4}
                    className="mt-3 w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder:text-gray-600"
                  />
                  <Button
                    className={aiButtonClassName(
                      reanalyzeBtn.variant,
                      "mt-3 border-amber-700 bg-amber-800 text-amber-100 hover:bg-amber-700",
                    )}
                    disabled={reanalyzeBtn.disabled || !pmComment.trim()}
                    onClick={() => void runReanalyze(req.id, pmComment.trim())}
                  >
                    {reanalyzeBtn.label}
                  </Button>
                  {aiJob.operationName === "Rewriting requirement analysis" ? (
                    <AiStatusBar
                      {...aiJobStatusBarProps(aiJob)}
                      onCancel={aiJob.cancel}
                      onTryAgain={() =>
                        void runReanalyze(req.id, pmComment.trim())
                      }
                    />
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          {/* ── STEP 1: GAP ANALYSIS ── */}
          {(currentStep === 1 || (currentStep === 4 && !isFinalized)) &&
          !isFinalized ? (
            <div className="space-y-6">
              {analysis ? (
                <>
                  <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 print:border-gray-300 print:bg-white">
                    <h2 className="font-medium">Summary</h2>
                    <p className="mt-2 text-sm text-gray-300 print:text-black">
                      {String(analysis.summary)}
                    </p>
                  </div>

                  {cost && (
                    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 print:border-gray-300 print:bg-white">
                      <h2 className="font-medium">Preliminary cost estimate</h2>
                      <p className="mt-2 text-sm text-gray-300 print:text-black">
                        ${String(cost.min_budget_usd)} – ${String(cost.max_budget_usd)}{" "}
                        {String(cost.currency)}
                      </p>
                      <p className="text-xs text-gray-500 print:text-gray-700">
                        {String(cost.note)}
                      </p>
                    </div>
                  )}

                  <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 print:border-gray-300 print:bg-white">
                    <h2 className="font-medium">Gaps</h2>
                    <p className="mt-2 text-sm text-gray-400 print:text-gray-700">
                      {clientGapCount} question{clientGapCount === 1 ? "" : "s"} require
                      client input. {autoGapCount} technical decision
                      {autoGapCount === 1 ? "" : "s"} handled automatically.
                    </p>
                    <ul className="mt-3 space-y-2">
                      {gaps.map((gap, i) => {
                        const needsClientInput = isClientInputGap(gap);
                        return (
                          <li
                            key={i}
                            className={`rounded-md border p-3 text-sm print:text-black ${
                              needsClientInput
                                ? "border-gray-800 bg-gray-950 print:border-gray-300 print:bg-white"
                                : "border-gray-700 bg-gray-800/80 print:border-gray-300 print:bg-gray-100"
                            }`}
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <span
                                className={`rounded border px-2 py-0.5 text-xs uppercase ${severityBadgeClass(
                                  String(gap.category),
                                )} print:border-gray-400 print:bg-gray-200 print:text-black`}
                              >
                                {String(gap.category)}
                              </span>
                              {!needsClientInput ? (
                                <span className="rounded border border-gray-600 bg-gray-700 px-2 py-0.5 text-xs text-gray-200 print:border-gray-400 print:bg-gray-300 print:text-black">
                                  Auto — technical standard
                                </span>
                              ) : null}
                            </div>
                            <p className="mt-2">{String(gap.description)}</p>
                            {gap.question ? (
                              <p
                                className={`mt-1 ${
                                  needsClientInput
                                    ? "text-gray-400 print:text-gray-700"
                                    : "text-gray-300 print:text-gray-800"
                                }`}
                              >
                                Q: {String(gap.question)}
                              </p>
                            ) : null}
                            {!needsClientInput && gap.auto_answer ? (
                              <p className="mt-2 text-xs text-gray-300 print:text-gray-800">
                                <span className="font-medium">Auto answer:</span>{" "}
                                {String(gap.auto_answer)}
                              </p>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  <div className="no-print space-y-4 rounded-xl border border-gray-800 bg-gray-900 p-4">
                    <Button
                      className="border-green-700 bg-green-800 text-green-100 hover:bg-green-700"
                      disabled={downloading || !hasDocxContent}
                      onClick={async () => {
                        setDownloadError(null);
                        setDownloading(true);
                        try {
                          await buildClarificationDocx(
                            analysis,
                            project?.name ?? "Project",
                          );
                        } catch (err) {
                          setDownloadError(
                            err instanceof Error
                              ? err.message
                              : "DOCX download failed",
                          );
                        } finally {
                          setDownloading(false);
                        }
                      }}
                    >
                      {downloading
                        ? "Generating..."
                        : "Download Client Feedback Form (DOCX)"}
                    </Button>
                    {downloadError ? (
                      <p className="text-sm text-red-400" role="alert">
                        {downloadError}
                      </p>
                    ) : null}
                    <p className="text-sm text-gray-400">
                      Fill this form with your client, then upload it below to
                      continue.
                    </p>

                    <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center">
                      <p className="text-sm font-medium">
                        Upload completed feedback document
                      </p>
                      <p className="mt-1 text-xs text-gray-500">
                        Accepts .docx, .pdf, .txt
                      </p>
                      <label
                        className={`mt-4 inline-flex items-center rounded-md border px-4 py-2 text-sm ${
                          uploadBtn.disabled
                            ? "cursor-not-allowed border-gray-600 bg-gray-700 text-gray-300 opacity-80"
                            : "cursor-pointer border-gray-700 hover:bg-gray-800"
                        }`}
                      >
                        {uploadBtn.label}
                        <input
                          type="file"
                          accept=".docx,.pdf,.txt"
                          className="hidden"
                          disabled={uploadBtn.disabled}
                          onChange={async (e) => {
                            const file = e.target.files?.[0];
                            if (!file) return;
                            try {
                              const formData = new FormData();
                              formData.append("file", file);
                              const uploadResponse = await fetch(
                                `${API_BASE}/requirements/${id}/feedback-document`,
                                {
                                  method: "POST",
                                  credentials: "include",
                                  body: formData,
                                },
                              );
                              if (!uploadResponse.ok) {
                                const body = (await uploadResponse
                                  .json()
                                  .catch(() => null)) as { detail?: string } | null;
                                throw new Error(
                                  body?.detail ?? "Feedback upload failed",
                                );
                              }
                              await refreshRequirement(id);
                              await runSynthesize(id);
                            } catch (err) {
                              aiJob.failManual(
                                err instanceof Error
                                  ? err.message
                                  : "Feedback upload failed",
                              );
                            } finally {
                              e.target.value = "";
                            }
                          }}
                        />
                      </label>
                      {aiJob.operationName === "Synthesizing feedback" ? (
                        <AiStatusBar
                          {...aiJobStatusBarProps(aiJob)}
                          onCancel={aiJob.cancel}
                          onTryAgain={() => void runSynthesize(id)}
                        />
                      ) : null}
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-gray-400">Analysis not yet available.</p>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {/* ── PRINT DOCUMENT (5 sections) ── */}
      <div className="print-only mt-8 font-serif text-black">
        <div className="text-center">
          <h1 className="text-xl font-bold tracking-wide">
            FINAL CLIENT REQUIREMENT
          </h1>
        </div>
        <table className="mt-6 w-full text-sm">
          <tbody>
            <tr>
              <td className="w-24 font-semibold">Project</td>
              <td>{project?.name ?? "—"}</td>
            </tr>
            <tr>
              <td className="font-semibold">Client</td>
              <td>{clientName}</td>
            </tr>
            <tr>
              <td className="font-semibold">Date</td>
              <td>{finalizedDate}</td>
            </tr>
            <tr>
              <td className="font-semibold">Prepared</td>
              <td>{finalizedBy}</td>
            </tr>
            <tr>
              <td className="font-semibold">Status</td>
              <td>FINALIZED</td>
            </tr>
          </tbody>
        </table>
        <hr className="my-4 border-black" />

        <h2 className="text-sm font-bold uppercase">
          Section 1 — Original Requirement
        </h2>
        <pre className="mt-2 whitespace-pre-wrap text-xs font-sans">
          {originalText || "Original document text not available."}
        </pre>
        <hr className="my-4 border-black" />

        <h2 className="text-sm font-bold uppercase">
          Section 2 — Gap Analysis Summary
        </h2>
        <p className="mt-2 text-xs">
          Gaps identified: {gapCounts.critical} critical, {gapCounts.important}{" "}
          important, {gapCounts.minor} minor
        </p>
        <ul className="mt-2 list-disc pl-5 text-xs">
          {gaps.map((gap, i) => (
            <li key={i}>
              <strong>{String(gap.category).toUpperCase()}:</strong>{" "}
              {String(gap.description)}
              {gap.question ? ` — Q: ${String(gap.question)}` : ""}
            </li>
          ))}
        </ul>
        <hr className="my-4 border-black" />

        <h2 className="text-sm font-bold uppercase">
          Section 3 — Client Feedback Summary
        </h2>
        {feedbackSummary.length > 0 ? (
          <ul className="mt-2 list-none space-y-2 text-xs">
            {feedbackSummary.map((item, i) => (
              <li key={i}>
                <strong>Q:</strong> {item.question}
                <br />
                <strong>A:</strong> {item.answer}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-xs text-gray-600">
            Client feedback captured in uploaded document.
          </p>
        )}
        <hr className="my-4 border-black" />

        <h2 className="text-sm font-bold uppercase">
          Section 4 — Final Consolidated Requirement
        </h2>
        {activeDraft ? (
          <div className="mt-2 text-xs">
            <p>
              <strong>Project Overview</strong>
              <br />
              {String(activeDraft.project_overview)}
            </p>
            <p className="mt-2">
              <strong>Users &amp; Roles</strong>
              <br />
              {String(activeDraft.users_and_roles)}
            </p>
            <p className="mt-2 font-semibold">Confirmed Features</p>
            <ol className="list-decimal pl-5">
              {((activeDraft.confirmed_features as string[]) ?? []).map(
                (feature, i) => (
                  <li key={i}>{feature}</li>
                ),
              )}
            </ol>
            <p className="mt-2 font-semibold">Technical Decisions</p>
            <ul className="list-disc pl-5">
              {((activeDraft.technical_decisions as string[]) ?? []).map(
                (decision, i) => (
                  <li key={i}>{decision}</li>
                ),
              )}
            </ul>
            <p className="mt-2 font-semibold">Out of Scope</p>
            <ul className="list-disc pl-5">
              {((activeDraft.out_of_scope as string[]) ?? []).map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <hr className="my-4 border-black" />

        <h2 className="text-sm font-bold uppercase">Section 5 — Confirmation</h2>
        <table className="mt-2 text-xs">
          <tbody>
            <tr>
              <td className="w-28 font-semibold">Finalized by</td>
              <td>{finalizedBy}</td>
            </tr>
            <tr>
              <td className="font-semibold">Date</td>
              <td>{finalizedDate}</td>
            </tr>
            <tr>
              <td className="font-semibold">Signature</td>
              <td>___________________</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
