"use client";

import { Button } from "@/components/ui/button";
import type { AiJobStatus } from "@/lib/hooks/useAiJob";

export type AiStatusBarProps = {
  isVisible: boolean;
  status: AiJobStatus;
  operationName: string;
  elapsedSeconds: number;
  tokenCount?: number;
  errorMessage?: string;
  processingMessage?: string;
  onCancel?: () => void;
  onTryAgain?: () => void;
};

function progressWidth(status: AiJobStatus): string {
  if (status === "completed" || status === "failed") return "100%";
  if (status === "pending") return "30%";
  return "65%";
}

function progressClass(status: AiJobStatus): string {
  if (status === "completed") return "bg-green-600";
  if (status === "failed") return "bg-red-600";
  if (status === "pending") return "bg-gray-600";
  return "bg-blue-600 animate-pulse";
}

export function AiStatusBar({
  isVisible,
  status,
  operationName,
  elapsedSeconds,
  tokenCount,
  errorMessage,
  processingMessage,
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
    status === "pending"
      ? `Queued: ${operationName}`
      : status === "completed"
        ? `${operationName} complete!`
        : status === "failed"
          ? `${operationName} failed`
          : operationName;

  return (
    <div className="mt-3 rounded-xl border border-gray-700 bg-gray-900/80 p-4 text-sm">
      <p className="font-medium text-gray-200">
        {headerIcon} {headerText}
      </p>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${progressClass(status)}`}
          style={{ width: progressWidth(status) }}
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 text-xs text-gray-400">
        <span>⏱ {elapsedSeconds}s</span>
        {(tokenCount ?? 0) > 0 ? (
          <span>🔤 {tokenCount!.toLocaleString()} tokens</span>
        ) : null}
      </div>
      {processingMessage && (status === "pending" || status === "processing") ? (
        <p className="mt-2 text-xs text-gray-400">{processingMessage}</p>
      ) : null}
      {status === "failed" && errorMessage ? (
        <p className="mt-2 text-xs text-red-300">{errorMessage}</p>
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
      </div>
    </div>
  );
}
