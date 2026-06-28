"use client";

import { useEffect, useState } from "react";
import { formatElapsed } from "@/components/ui/AiStatusBar";

type AutoCi = {
  phase?: string;
  message?: string;
  at?: string;
  heartbeat_at?: string;
  stale?: boolean;
  current_model?: string;
  model_attempt?: number;
  repair_cycle?: number;
  repair_cycle_max?: number;
  activity_step?: string;
  activity_detail?: string;
  batch_current?: number;
  batch_total?: number;
  files_fixed_so_far?: number;
  files_targeted?: number;
};

type RepairPlan = {
  fixed?: number;
  targeted?: string[];
};

const PHASE_LABEL: Record<string, string> = {
  watching: "Waiting for GitHub CI",
  repairing: "AI fixing CI failures",
  repushed: "Watching new CI run",
};

const STEP_LABEL: Record<string, string> = {
  read_logs: "Reading CI logs",
  parse_logs: "Parsing CI failures",
  dockerfiles: "Adding Dockerfiles",
  ai_fix: "AI fixing files",
  static_gate: "Running static checks",
  push: "Pushing to GitHub",
  waiting_ci: "Waiting for CI",
};

function repairCycleLabel(autoCi: AutoCi, repairAttempts?: number): string | null {
  if (autoCi.repair_cycle != null && autoCi.repair_cycle_max != null) {
    return `Repair ${autoCi.repair_cycle}/${autoCi.repair_cycle_max}`;
  }
  const m = autoCi.message?.match(/attempt\s+(\d+)\s*\/\s*(\d+)/i);
  if (m) return `Repair ${m[1]}/${m[2]}`;
  if (repairAttempts != null && repairAttempts >= 0) {
    return `Repair ${repairAttempts + 1}/5`;
  }
  return null;
}

export function AutoRepairStatusBar({
  autoCi,
  repairAttempts,
  repairPlan,
  fallbackModel,
}: {
  autoCi: AutoCi | undefined;
  repairAttempts?: number;
  repairPlan?: RepairPlan | null;
  fallbackModel?: string;
}) {
  const phase = autoCi?.phase || "";
  const active = ["watching", "repairing", "repushed"].includes(phase);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active || !autoCi?.at) {
      setElapsed(0);
      return;
    }
    const started = new Date(autoCi.at).getTime();
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [active, autoCi?.at]);

  if (!active) return null;

  const stepKey = autoCi?.activity_step || phase;
  const title = STEP_LABEL[stepKey] || PHASE_LABEL[phase] || "Auto-repair in progress";
  const detail =
    autoCi?.activity_detail
    || (phase === "watching" ? "Polling GitHub Actions…" : PHASE_LABEL[phase] || "");

  const repairCycle = repairCycleLabel(autoCi ?? {}, repairAttempts);
  const modelName =
    autoCi?.current_model || (phase === "repairing" ? fallbackModel : undefined) || "Auto (best available)";

  const targeted = autoCi?.files_targeted ?? repairPlan?.targeted?.length ?? 0;
  const fixedCount = autoCi?.files_fixed_so_far ?? repairPlan?.fixed ?? 0;
  const batchLabel =
    autoCi?.batch_current && autoCi?.batch_total
      ? `Batch ${autoCi.batch_current}/${autoCi.batch_total}`
      : null;

  const progressPct =
    autoCi?.batch_total && autoCi.batch_current
      ? Math.min(95, Math.round((autoCi.batch_current / autoCi.batch_total) * 100))
      : phase === "push"
        ? 90
        : phase === "waiting_ci" || phase === "repushed"
          ? 50
          : 70;

  return (
    <div
      className="rounded-xl border border-gray-700 bg-gray-900/80 p-4 text-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium text-gray-200">
          🔄 {title}
        </p>
        <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-400">
          Working — do not interrupt
        </span>
      </div>

      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          className="h-full rounded-full bg-blue-600 transition-all duration-500 animate-pulse"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      <p className="mt-2 text-sm text-blue-100">{detail}</p>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
        <span>⏱ {formatElapsed(elapsed)}</span>
        {phase === "repairing" || stepKey === "ai_fix" ? <span>🤖 {modelName}</span> : null}
        {repairCycle ? <span>↻ {repairCycle}</span> : null}
        {batchLabel ? <span>📦 {batchLabel}</span> : null}
        {targeted > 0 ? (
          <span>📄 {fixedCount}/{targeted} files</span>
        ) : null}
        {autoCi?.model_attempt != null && autoCi.model_attempt > 0 ? (
          <span>↻ Model #{autoCi.model_attempt}</span>
        ) : null}
      </div>

      <p className="mt-3 rounded bg-gray-800/70 px-2 py-1 text-xs text-gray-300">
        <span className="font-medium text-gray-400">Please wait:</span> do not click Push to GitHub, Fix with AI, or
        Sync from GitHub until this finishes.
      </p>
    </div>
  );
}

export function isAutoRepairActive(autoCi: AutoCi | undefined): boolean {
  const phase = autoCi?.phase || "";
  if (autoCi?.stale || phase === "stopped") return false;
  return ["watching", "repairing", "repushed"].includes(phase);
}
