"use client";

import { Button } from "@/components/ui/button";
import type { AiJobStatus } from "@/lib/hooks/useAiJob";
import type { TaskStatus } from "@/lib/api";

export type AiStatusBarProps = {
  isVisible: boolean;
  status: AiJobStatus;
  operationName: string;
  elapsedSeconds: number;
  tokenCount?: number;
  errorMessage?: string;
  processingMessage?: string;
  currentModel?: string;
  phase?: string;
  attempt?: number;
  /** Short instruction telling the user what to do once this finishes. */
  nextStep?: string;
  onCancel?: () => void;
  onTryAgain?: () => void;
};

export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function progressWidth(status: AiJobStatus): string {
  if (status === "completed" || status === "failed") return "100%";
  if (status === "pending") return "25%";
  return "70%";
}

function progressClass(status: AiJobStatus): string {
  if (status === "completed") return "bg-green-600";
  if (status === "failed") return "bg-red-600";
  if (status === "pending") return "bg-gray-600";
  return "bg-blue-600 animate-pulse";
}

function statusLabel(status: AiJobStatus): string {
  switch (status) {
    case "pending":
      return "Queued";
    case "processing":
      return "In progress";
    case "completed":
      return "Success";
    case "failed":
      return "Failed";
    default:
      return "";
  }
}

function phaseLabel(phase: string | undefined): string | null {
  if (!phase) return null;
  if (phase === "rate_limited") return "Rate limited — switching model";
  if (phase === "starting") return "Starting";
  return phase.replace(/_/g, " ");
}

export function AiStatusBar({
  isVisible,
  status,
  operationName,
  elapsedSeconds,
  tokenCount,
  errorMessage,
  processingMessage,
  currentModel,
  phase,
  attempt,
  nextStep,
  onCancel,
  onTryAgain,
}: AiStatusBarProps) {
  if (!isVisible || status === "idle") return null;

  const headerIcon =
    status === "pending"
      ? "⏳"
      : status === "processing"
        ? "🔄"
        : status === "completed"
          ? "✅"
          : "❌";

  const headerText =
    status === "completed"
      ? `${operationName} complete`
      : status === "failed"
        ? `${operationName} failed`
        : operationName;

  const phaseText = phaseLabel(phase);

  return (
    <div className="mt-3 rounded-xl border border-gray-700 bg-gray-900/80 p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium text-gray-200">
          {headerIcon} {headerText}
        </p>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            status === "completed"
              ? "bg-green-500/15 text-green-400"
              : status === "failed"
                ? "bg-red-500/15 text-red-400"
                : status === "pending"
                  ? "bg-gray-500/15 text-gray-400"
                  : "bg-blue-500/15 text-blue-400"
          }`}
        >
          {statusLabel(status)}
        </span>
      </div>

      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${progressClass(status)}`}
          style={{ width: progressWidth(status) }}
        />
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
        <span>⏱ {formatElapsed(elapsedSeconds)}</span>
        <span>🤖 {currentModel || "Auto (best available)"}</span>
        {attempt != null && attempt > 0 ? <span>↻ Model #{attempt}</span> : null}
        {(tokenCount ?? 0) > 0 ? (
          <span>🔤 {tokenCount!.toLocaleString()} tokens</span>
        ) : null}
      </div>

      {/* Clear "it's alive" reassurance so the user knows work is happening */}
      {status === "processing" || status === "pending" ? (
        <p className="mt-2 text-xs text-blue-300">
          🔄 Working… {formatElapsed(elapsedSeconds)} elapsed — this runs in the background; large projects can take several minutes.
        </p>
      ) : null}

      {phaseText && (status === "pending" || status === "processing") ? (
        <p className="mt-2 text-xs text-amber-400/90">{phaseText}</p>
      ) : null}

      {processingMessage && (status === "pending" || status === "processing") ? (
        <p className="mt-1 text-xs text-gray-400">{processingMessage}</p>
      ) : null}

      {status === "completed" ? (
        <p className="mt-2 text-xs text-green-400/90">
          Finished in {formatElapsed(elapsedSeconds)}
          {(tokenCount ?? 0) > 0 ? ` · ${tokenCount!.toLocaleString()} tokens` : ""}
        </p>
      ) : null}

      {status === "failed" && errorMessage ? (
        <p className="mt-2 text-xs text-red-300">{errorMessage}</p>
      ) : null}

      {/* What to do next — so the user always knows the following step/button */}
      {nextStep && status !== "failed" ? (
        <p className="mt-2 rounded bg-gray-800/70 px-2 py-1 text-xs text-gray-300">
          <span className="font-medium text-gray-400">{status === "completed" ? "Next step:" : "After this:"}</span> {nextStep}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {status === "processing" && onCancel ? (
          <Button variant="outline" size="xs" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
        {status === "failed" && onTryAgain ? (
          <Button variant="outline" size="xs" onClick={onTryAgain}>
            Try again
          </Button>
        ) : null}
        {status === "failed" && onCancel ? (
          <Button variant="outline" size="xs" onClick={onCancel}>
            Dismiss
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** Shared props for AiStatusBar from useAiJob state + Celery meta. */
export function aiJobStatusBarProps(aiJob: {
  isVisible: boolean;
  status: AiJobStatus;
  operationName: string;
  elapsedSeconds: number;
  tokenCount?: number;
  errorMessage?: string;
  processingMessage: string;
  taskMeta: TaskStatus["meta"] | null | undefined;
}): Omit<AiStatusBarProps, "onCancel" | "onTryAgain"> {
  const meta = aiJob.taskMeta;
  const metaMessage = typeof meta?.message === "string" ? meta.message : undefined;
  const metaModel = typeof meta?.current_model === "string" ? meta.current_model : undefined;
  const metaPhase = typeof meta?.phase === "string" ? meta.phase : undefined;
  return {
    isVisible: aiJob.isVisible,
    status: aiJob.status,
    operationName: aiJob.operationName,
    elapsedSeconds: aiJob.elapsedSeconds,
    tokenCount: aiJob.tokenCount,
    errorMessage: aiJob.errorMessage,
    processingMessage: metaMessage || aiJob.processingMessage,
    currentModel: metaModel,
    phase: metaPhase,
    attempt: typeof meta?.attempt === "number" ? meta.attempt : undefined,
  };
}
