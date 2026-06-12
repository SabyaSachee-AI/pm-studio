"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { TaskStatus } from "@/lib/api";

export type AiJobStatus = "idle" | "pending" | "processing" | "completed" | "failed";

const TERMINAL = new Set(["SUCCESS", "FAILURE", "COMPLETED", "FAILED"]);

const PROCESSING_MESSAGES: Record<string, string> = {
  "Analyzing requirement": "Reading and analyzing your document...",
  "Generating PRD": "Writing product requirements...",
  "Generating SRS": "Writing technical specifications...",
  "Generating architecture": "Building 6 architecture documents...",
  "Extracting modules": "Breaking SRS into Kanban tasks...",
  "Generating spec": "Writing technical task specification...",
};

const ROTATING_MESSAGES = [
  "AI is working carefully for best results...",
  "Almost there — final touches...",
];

function extractTokenCount(payload: Record<string, unknown>): number | undefined {
  if (typeof payload.token_count === "number") return payload.token_count;
  const usage = payload.usage;
  if (usage && typeof usage === "object") {
    const u = usage as Record<string, unknown>;
    if (typeof u.total_tokens === "number") return u.total_tokens;
    const input = typeof u.input_tokens === "number" ? u.input_tokens : 0;
    const output = typeof u.output_tokens === "number" ? u.output_tokens : 0;
    if (input > 0 || output > 0) return input + output;
  }
  const result = payload.result;
  if (result && typeof result === "object") {
    return extractTokenCount(result as Record<string, unknown>);
  }
  return undefined;
}

function mapCeleryStatus(raw: string): AiJobStatus {
  const status = raw.toUpperCase();
  if (status === "SUCCESS" || status === "COMPLETED") return "completed";
  if (status === "FAILURE" || status === "FAILED") return "failed";
  if (status === "PENDING" || status === "RETRY") return "pending";
  return "processing";
}

export function getProcessingMessage(operationName: string, rotateIndex: number): string {
  const primary =
    PROCESSING_MESSAGES[operationName] ?? `Working on ${operationName.toLowerCase()}...`;
  if (rotateIndex === 0) return primary;
  return ROTATING_MESSAGES[(rotateIndex - 1) % ROTATING_MESSAGES.length];
}

export type UseAiJobOptions = {
  onComplete?: (info: {
    elapsedSeconds: number;
    tokenCount?: number;
    operationName: string;
  }) => void;
  onFailed?: (info: {
    elapsedSeconds: number;
    errorMessage: string;
    operationName: string;
  }) => void;
};

export function useAiJob(options: UseAiJobOptions = {}) {
  const [status, setStatus] = useState<AiJobStatus>("idle");
  const [operationName, setOperationName] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [tokenCount, setTokenCount] = useState<number | undefined>(undefined);
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined);
  const [messageRotateIndex, setMessageRotateIndex] = useState(0);
  const [taskMeta, setTaskMeta] = useState<TaskStatus["meta"] | null>(null);

  const timerRef = useRef<number | null>(null);
  const pollRef = useRef<number | null>(null);
  const hideRef = useRef<number | null>(null);
  const messageRotateRef = useRef<number | null>(null);
  const taskIdRef = useRef<string | null>(null);
  const isManualRef = useRef(false);
  const elapsedRef = useRef(0);
  const onCompleteRef = useRef(options.onComplete);
  const onFailedRef = useRef(options.onFailed);

  useEffect(() => {
    onCompleteRef.current = options.onComplete;
    onFailedRef.current = options.onFailed;
  }, [options.onComplete, options.onFailed]);

  const clearTimers = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (hideRef.current) {
      clearTimeout(hideRef.current);
      hideRef.current = null;
    }
    if (messageRotateRef.current) {
      clearInterval(messageRotateRef.current);
      messageRotateRef.current = null;
    }
  }, []);

  const startElapsedTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setElapsedSeconds(0);
    elapsedRef.current = 0;
    timerRef.current = window.setInterval(() => {
      elapsedRef.current += 1;
      setElapsedSeconds(elapsedRef.current);
    }, 1000);
  }, []);

  const scheduleHide = useCallback(() => {
    if (hideRef.current) clearTimeout(hideRef.current);
    hideRef.current = window.setTimeout(() => {
      setStatus("idle");
      setOperationName("");
      setErrorMessage(undefined);
      setMessageRotateIndex(0);
      setTaskMeta(null);
    }, 3000);
  }, []);

  const startMessageRotation = useCallback(() => {
    if (messageRotateRef.current) clearInterval(messageRotateRef.current);
    setMessageRotateIndex(0);
    messageRotateRef.current = window.setInterval(() => {
      setMessageRotateIndex((i) => i + 1);
    }, 8000);
  }, []);

  const completeJob = useCallback(
    (tokens?: number) => {
      clearTimers();
      taskIdRef.current = null;
      isManualRef.current = false;
      if (tokens !== undefined) setTokenCount(tokens);
      setStatus("completed");
      onCompleteRef.current?.({
        elapsedSeconds: elapsedRef.current,
        tokenCount: tokens,
        operationName,
      });
      scheduleHide();
    },
    [clearTimers, operationName, scheduleHide],
  );

  const failJob = useCallback(
    (error: string) => {
      clearTimers();
      taskIdRef.current = null;
      isManualRef.current = false;
      setErrorMessage(error);
      setStatus("failed");
      onFailedRef.current?.({
        elapsedSeconds: elapsedRef.current,
        errorMessage: error,
        operationName,
      });
    },
    [clearTimers, operationName],
  );

  const pollTask = useCallback(
    async (taskId: string) => {
      try {
        const data = (await api.getTaskStatus(taskId)) as unknown as Record<
          string,
          unknown
        >;
        const rawStatus = String(data.status ?? "PENDING");
        const mapped = mapCeleryStatus(rawStatus);
        const tokens = extractTokenCount(data);
        if (tokens !== undefined) setTokenCount(tokens);

        if (data.meta && typeof data.meta === "object") {
          setTaskMeta(data.meta);
        }

        if (mapped === "pending") setStatus("pending");
        else if (mapped === "processing" || rawStatus.toUpperCase() === "PROGRESS") {
          setStatus("processing");
        }
        else if (mapped === "completed") completeJob(tokens);
        else if (mapped === "failed") failJob(String(data.error ?? "Job failed"));

        if (TERMINAL.has(rawStatus.toUpperCase()) && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (err) {
        failJob(err instanceof Error ? err.message : "Failed to poll job status");
      }
    },
    [completeJob, failJob],
  );

  const startJob = useCallback(
    (taskId: string, opName: string) => {
      clearTimers();
      taskIdRef.current = taskId;
      isManualRef.current = false;
      setOperationName(opName);
      setTokenCount(undefined);
      setErrorMessage(undefined);
      setTaskMeta(null);
      setStatus("pending");
      startElapsedTimer();
      startMessageRotation();
      void pollTask(taskId);
      pollRef.current = window.setInterval(() => {
        void pollTask(taskId);
      }, 2000);
    },
    [clearTimers, pollTask, startElapsedTimer, startMessageRotation],
  );

  const reset = useCallback(() => {
    clearTimers();
    taskIdRef.current = null;
    isManualRef.current = false;
    setStatus("idle");
    setOperationName("");
    setElapsedSeconds(0);
    setTokenCount(undefined);
    setErrorMessage(undefined);
    setMessageRotateIndex(0);
    setTaskMeta(null);
  }, [clearTimers]);

  const cancel = useCallback(() => {
    reset();
  }, [reset]);

  const startManual = useCallback(
    (opName: string) => {
      clearTimers();
      isManualRef.current = true;
      taskIdRef.current = null;
      setOperationName(opName);
      setTokenCount(undefined);
      setErrorMessage(undefined);
      setStatus("processing");
      startElapsedTimer();
      startMessageRotation();
    },
    [clearTimers, startElapsedTimer, startMessageRotation],
  );

  const completeManual = useCallback(
    (tokens?: number) => {
      if (!isManualRef.current) return;
      completeJob(tokens);
    },
    [completeJob],
  );

  const failManual = useCallback(
    (error: string) => {
      if (!isManualRef.current) return;
      failJob(error);
    },
    [failJob],
  );

  useEffect(() => () => clearTimers(), [clearTimers]);

  const isRunning = status === "pending" || status === "processing";
  const processingMessage = getProcessingMessage(operationName, messageRotateIndex);

  return {
    status,
    operationName,
    elapsedSeconds,
    tokenCount,
    errorMessage,
    processingMessage,
    taskMeta,
    isRunning,
    isVisible: status !== "idle",
    startJob,
    startManual,
    completeManual,
    failManual,
    reset,
    cancel,
  };
}

export function aiButtonLabel(
  baseLabel: string,
  status: AiJobStatus,
  isThisJob: boolean,
): { label: string; disabled: boolean; variant: "normal" | "loading" | "completed" | "failed" } {
  if (!isThisJob || status === "idle") {
    return { label: baseLabel, disabled: false, variant: "normal" };
  }
  if (status === "pending" || status === "processing") {
    const verb = baseLabel.replace(/^[🔵✅❌⏳🔄\s]*/, "").trim();
    const loading = verb.endsWith("...") ? verb : `${verb.replace(/\.$/, "")}...`;
    return { label: `⏳ ${loading}`, disabled: true, variant: "loading" };
  }
  if (status === "completed") {
    return { label: "✅ Done!", disabled: true, variant: "completed" };
  }
  if (status === "failed") {
    return { label: "❌ Failed", disabled: false, variant: "failed" };
  }
  return { label: baseLabel, disabled: false, variant: "normal" };
}

export function aiButtonClassName(
  variant: "normal" | "loading" | "completed" | "failed",
  extraClass = "",
): string {
  if (variant === "loading") return `opacity-80 cursor-wait ${extraClass}`.trim();
  if (variant === "completed") return `border-green-700 bg-green-900/50 ${extraClass}`.trim();
  if (variant === "failed") return `border-red-700 ${extraClass}`.trim();
  return extraClass;
}
