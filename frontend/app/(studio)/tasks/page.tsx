"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import {
  aiButtonClassName,
  aiButtonLabel,
  useAiJob,
} from "@/lib/hooks/useAiJob";
import { buildSpecPdf } from "@/lib/specPdfBuilder";
import {
  buildAllSpecsMarkdown,
  buildSpecMarkdown,
  downloadTextFile,
  slugFilename,
  type AllSpecsItem,
  type SpecMdTask,
} from "@/lib/specMarkdown";
import {
  api,
  type AiModelOption,
  type KanbanBoard,
  type KanbanTask,
  type ModelChoice,
  type Project,
  type SRS,
  type TaskSpec,
  type UserResponse,
} from "@/lib/api";
import { copyToClipboard } from "@/lib/copyToClipboard";

// ── Constants ─────────────────────────────────────────────────────────────────

const COLUMNS: { key: keyof KanbanBoard; label: string }[] = [
  { key: "backlog",      label: "Backlog" },
  { key: "assigned",    label: "Assigned" },
  { key: "in_progress", label: "In progress" },
  { key: "in_review",   label: "In review" },
  { key: "done",        label: "Done" },
];

const SYSTEM_TASK_MIN_ORDER = 99996;
const PROJECT_BIBLE_ORDER   = 99996;
const CODE_AUDIT_ORDER      = 99997;
const LOCAL_UI_TEST_ORDER   = 99998;
const DEPLOY_ORDER          = 99999;

const COL_STYLE: Record<string, { dot: string; head: string; border: string; bg: string }> = {
  backlog:     { dot: "bg-slate-400",   head: "text-slate-300",  border: "border-slate-700/50",  bg: "bg-slate-900/30" },
  assigned:    { dot: "bg-blue-400",    head: "text-blue-300",   border: "border-blue-800/40",   bg: "bg-blue-950/20" },
  in_progress: { dot: "bg-amber-400",   head: "text-amber-300",  border: "border-amber-800/40",  bg: "bg-amber-950/20" },
  in_review:   { dot: "bg-purple-400",  head: "text-purple-300", border: "border-purple-800/40", bg: "bg-purple-950/20" },
  done:        { dot: "bg-emerald-400", head: "text-emerald-300",border: "border-emerald-800/40",bg: "bg-emerald-950/20" },
};

const PRIORITY_LEFT: Record<string, string> = {
  critical: "border-l-red-500",
  high:     "border-l-orange-500",
  medium:   "border-l-blue-500",
  low:      "border-l-slate-600",
};

const PRIORITY_BADGE: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400",
  high:     "bg-orange-500/15 text-orange-400",
  medium:   "bg-blue-500/15 text-blue-400",
  low:      "bg-slate-500/15 text-slate-400",
};

const METHOD_STYLE: Record<string, string> = {
  GET:    "bg-blue-500/20 text-blue-300",
  POST:   "bg-green-500/20 text-green-300",
  PUT:    "bg-yellow-500/20 text-yellow-300",
  PATCH:  "bg-orange-500/20 text-orange-300",
  DELETE: "bg-red-500/20 text-red-300",
};

const SYS_STYLES: Record<number, { badge: string; bCls: string; card: string }> = {
  [PROJECT_BIBLE_ORDER]: { badge: "SETUP FIRST",    bCls: "bg-amber-500/20 text-amber-300",  card: "border-amber-500/50 bg-amber-950/20 border-l-2 border-l-amber-500" },
  [CODE_AUDIT_ORDER]:    { badge: "FINAL — STEP 1", bCls: "bg-purple-500/20 text-purple-300", card: "border-purple-500/50 bg-purple-950/20 border-l-2 border-l-purple-500" },
  [LOCAL_UI_TEST_ORDER]: { badge: "FINAL — STEP 2", bCls: "bg-teal-500/20 text-teal-300",    card: "border-teal-500/50 bg-teal-950/20 border-l-2 border-l-teal-500" },
  [DEPLOY_ORDER]:        { badge: "DEPLOY",          bCls: "bg-blue-500/20 text-blue-300",    card: "border-blue-500/50 bg-blue-950/20 border-l-2 border-l-blue-500" },
};

// ── Types ──────────────────────────────────────────────────────────────────────

interface SpecTable    { name?: string; relevant_columns?: Array<{ name?: string; type?: string }> }
interface SpecEndpoint { method?: string; path?: string; request_body?: string; response_schema?: string; status_code?: string }
interface TaskDraft    { title: string; description: string; priority: string; module_name: string }

interface HealthIssue {
  level: "critical" | "warn" | "info";
  icon:  string;
  message: string;
  action?: "regenerate" | "generate-specs";
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isSystem(t: KanbanTask) { return t.order_index >= SYSTEM_TASK_MIN_ORDER }
function strField(c: Record<string, unknown>, k: string): string { const v = c[k]; return typeof v === "string" ? v : "" }
function strList(c: Record<string, unknown>, k: string): string[] { const v = c[k]; if (!Array.isArray(v)) return []; return v.map(String) }

function specTables(c: Record<string, unknown>): SpecTable[] {
  const db = c.database;
  if (!db || typeof db !== "object") return [];
  const t = (db as { tables?: unknown }).tables;
  if (!Array.isArray(t)) return [];
  return t.filter((x): x is SpecTable => typeof x === "object" && x !== null);
}

function specEndpoints(c: Record<string, unknown>): SpecEndpoint[] {
  const eps = c.api_endpoints;
  if (!Array.isArray(eps)) return [];
  return eps.filter((e): e is SpecEndpoint => typeof e === "object" && e !== null);
}

// ── Smart coverage analysis ───────────────────────────────────────────────────

function analyzeHealth(
  allRegular: KanbanTask[],
  totalTasks: number,
  specReady: number,
  specGenerating: number,
  missingFrs?: string[] | null,
): HealthIssue[] {
  if (totalTasks === 0) return [];
  const issues: HealthIssue[] = [];

  // FR numbers referenced by existing tasks (used by the heuristic fallback
  // and the truncated-generation check below).
  const allFrRefs = allRegular.flatMap((t) => {
    const refs = [...(t.fr_references ?? [])];
    if (t.linked_fr) refs.unshift(t.linked_fr);
    return refs;
  }).filter(Boolean);
  const frNums = [...new Set(allFrRefs)]
    .map((fr) => parseInt(fr.replace(/\D/g, ""), 10))
    .filter((n) => n > 0)
    .sort((a, b) => a - b);

  // 1. FR gap detection — prefer the authoritative coverage (real SRS FR list,
  // normalized server-side). Fall back to the numeric-sequence heuristic only
  // when coverage data hasn't loaded yet.
  if (missingFrs != null) {
    if (missingFrs.length > 0) {
      const preview = missingFrs.slice(0, 5).join(", ");
      issues.push({
        level: "critical",
        icon: "ti-alert-circle",
        message: `${missingFrs.length} FR${missingFrs.length > 1 ? "s" : ""} have no task: ${preview}${missingFrs.length > 5 ? ` +${missingFrs.length - 5} more` : ""}.`,
        action: "regenerate",
      });
    }
  } else if (frNums.length > 0) {
    const maxFr  = frNums[frNums.length - 1];
    const frSet  = new Set(frNums);
    const gaps   = Array.from({ length: maxFr }, (_, i) => i + 1).filter((n) => !frSet.has(n));
    if (gaps.length > 0) {
      const preview = gaps.slice(0, 5).map((n) => `FR-${String(n).padStart(3, "0")}`).join(", ");
      issues.push({
        level: "critical",
        icon: "ti-alert-circle",
        message: `${gaps.length} FR${gaps.length > 1 ? "s" : ""} have no task: ${preview}${gaps.length > 5 ? ` +${gaps.length - 5} more` : ""}.`,
        action: "regenerate",
      });
    }
  }

  // 2. Tasks with no FR reference (orphaned / generic)
  const unlinked = allRegular.filter(
    (t) => !t.linked_fr && (!t.fr_references || t.fr_references.length === 0),
  ).length;
  if (unlinked > 0) {
    issues.push({
      level: "warn",
      icon: "ti-unlink",
      message: `${unlinked} task${unlinked > 1 ? "s" : ""} ${unlinked > 1 ? "have" : "has"} no FR reference — may be orphaned or over-generic.`,
    });
  }

  // 3. Thin modules — modules with only 1 task (likely incomplete)
  const modCounts = new Map<string, number>();
  allRegular.forEach((t) => { if (t.module_name) modCounts.set(t.module_name, (modCounts.get(t.module_name) ?? 0) + 1) });
  const thinMods = [...modCounts.entries()].filter(([, c]) => c <= 1);
  if (thinMods.length >= 3) {
    const names = thinMods.slice(0, 3).map(([m]) => m.split("—").pop()?.trim() ?? m).join(", ");
    issues.push({
      level: "warn",
      icon: "ti-packages",
      message: `${thinMods.length} modules have only 1 task each (${names}${thinMods.length > 3 ? "…" : ""}). Coverage may be incomplete.`,
      action: "regenerate",
    });
  }

  // 4. All tasks in backlog with zero specs started
  if (totalTasks >= 5 && specReady === 0 && specGenerating === 0) {
    issues.push({
      level: "info",
      icon: "ti-file-x",
      message: "No specs generated yet. Click any task to generate its developer spec.",
      action: "generate-specs",
    });
  }

  // 5. Large FR range but very few tasks (likely truncated generation)
  if (frNums.length > 0) {
    const maxFr = frNums[frNums.length - 1];
    if (maxFr > totalTasks * 2.5) {
      issues.push({
        level: "warn",
        icon: "ti-alert-triangle",
        message: `${totalTasks} tasks for ${maxFr} FRs — ratio looks low. Some FRs may not have been converted to tasks.`,
        action: "regenerate",
      });
    }
  }

  return issues;
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

type GenerateMode = "generate" | "regenerate" | "fill-gaps";

interface DashboardProps {
  projectId:       string;
  board:           KanbanBoard | null;
  totalTasks:      number;
  missingFrs:      string[] | null;
  extractJob:      ReturnType<typeof useAiJob>;
  extractBtnLabel: ReturnType<typeof aiButtonLabel>;
  clearLoading:    boolean;
  onGenerate:      (mode: GenerateMode) => void;
  onClear:         () => void;
}

function Dashboard({ projectId, board, totalTasks, missingFrs, extractJob, extractBtnLabel, clearLoading, onGenerate, onClear }: DashboardProps) {
  const allRegular = useMemo(
    () => COLUMNS.flatMap(({ key }) => (board?.[key] ?? []).filter((t) => !isSystem(t))),
    [board],
  );

  const specReady      = allRegular.filter((t) => t.spec_status === "ready").length;
  const specGenerating = allRegular.filter((t) => t.spec_status === "generating").length;
  const specPending    = totalTasks - specReady - specGenerating;
  const assigned       = allRegular.filter((t) => t.status !== "backlog").length;
  const inProgress     = board?.in_progress?.filter((t) => !isSystem(t)).length ?? 0;
  const inReview       = board?.in_review?.filter((t) => !isSystem(t)).length ?? 0;
  const done           = board?.done?.filter((t) => !isSystem(t)).length ?? 0;
  const specPct        = totalTasks > 0 ? Math.round((specReady / totalTasks) * 100) : 0;
  const donePct        = totalTasks > 0 ? Math.round((done / totalTasks) * 100) : 0;
  const isGenerated    = totalTasks > 0;

  const healthIssues = useMemo(
    () => analyzeHealth(allRegular, totalTasks, specReady, specGenerating, missingFrs),
    [allRegular, totalTasks, specReady, specGenerating, missingFrs],
  );

  const ISSUE_STYLE = {
    critical: { bar: "bg-red-500",    badge: "bg-red-950/60 border-red-800/40 text-red-300",   icon: "text-red-400" },
    warn:     { bar: "bg-amber-500",  badge: "bg-amber-950/60 border-amber-800/40 text-amber-300", icon: "text-amber-400" },
    info:     { bar: "bg-blue-500",   badge: "bg-blue-950/60 border-blue-800/40 text-blue-300",  icon: "text-blue-400" },
  };

  type StatChipProps = { icon: string; label: string; value: number | string; sub?: string; color: string };
  function StatChip({ icon, label, value, sub, color }: StatChipProps) {
    return (
      <div className={`flex items-center gap-2.5 rounded-lg border px-3 py-2.5 ${color}`}>
        <i className={`ti ${icon} text-lg shrink-0`} aria-hidden />
        <div>
          <div className="text-xl font-bold leading-none">{value}</div>
          <div className="mt-0.5 text-[10px] font-medium uppercase tracking-wide opacity-70">{label}</div>
          {sub && <div className="text-[10px] opacity-50">{sub}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-700/60 bg-gray-900/80 p-4">
      {/* Top row */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <i className="ti ti-layout-dashboard text-sm text-gray-400" aria-hidden />
          <span className="text-sm font-semibold text-gray-200">Project board overview</span>
          {isGenerated ? (
            <span className="rounded border border-emerald-800/30 bg-emerald-950/60 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
              ✓ tasks generated
            </span>
          ) : (
            <span className="animate-pulse rounded border border-amber-800/30 bg-amber-950/60 px-2 py-0.5 text-[10px] font-medium text-amber-400">
              ⚠ no tasks yet
            </span>
          )}
          {healthIssues.filter((i) => i.level === "critical").length > 0 && (
            <span className="animate-pulse rounded border border-red-800/40 bg-red-950/60 px-2 py-0.5 text-[10px] font-medium text-red-400">
              ⚠ {healthIssues.filter((i) => i.level === "critical").length} coverage issue{healthIssues.filter((i) => i.level === "critical").length > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onGenerate(isGenerated ? "regenerate" : "generate")}
            disabled={extractBtnLabel.disabled || extractJob.isRunning}
            className={`h-8 text-xs ${aiButtonClassName(extractBtnLabel.variant)}`}
          >
            {isGenerated ? (
              <><i className="ti ti-refresh mr-1.5 text-sm" aria-hidden />Regenerate tasks</>
            ) : (
              <><i className="ti ti-sparkles mr-1.5 text-sm" aria-hidden />{extractBtnLabel.label}</>
            )}
          </Button>
          {isGenerated && (
            <Button
              variant="outline"
              size="sm"
              onClick={onClear}
              disabled={clearLoading || extractJob.isRunning}
              className="h-8 text-xs border-red-800/60 text-red-400 hover:bg-red-950/40 hover:text-red-300"
            >
              <i className="ti ti-trash mr-1 text-sm" aria-hidden />
              Reset board
            </Button>
          )}
          {isGenerated && (
            <Link
              href={`/traceability?project=${projectId}`}
              className="inline-flex items-center justify-center rounded-md border border-indigo-800/40 bg-transparent px-3 py-1 text-xs font-semibold text-indigo-400 hover:bg-indigo-950/30 hover:text-indigo-300 transition-colors h-8"
            >
              <i className="ti ti-git-commit mr-1.5 text-sm" aria-hidden />
              Traceability matrix
            </Link>
          )}
        </div>
      </div>

      {/* Empty state */}
      {totalTasks === 0 ? (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-gray-700/60 bg-gray-800/30 px-4 py-5 text-sm text-gray-500">
          <i className="ti ti-info-circle text-lg text-gray-600" aria-hidden />
          Generate tasks from your approved PRD, finalized SRS, and architecture suite to start tracking development progress.
        </div>
      ) : (
        <>
          {/* Stat chips */}
          <div className="flex flex-wrap gap-2">
            <StatChip icon="ti-list-numbers" label="Total tasks" value={totalTasks}
              color="border-gray-700/60 bg-gray-800/40 text-gray-300" />
            <StatChip icon="ti-file-check" label="Specs ready" value={specReady}
              sub={`${specPct}% coverage`}
              color="border-emerald-800/40 bg-emerald-950/20 text-emerald-300" />
            {specGenerating > 0 && (
              <StatChip icon="ti-loader-2" label="Generating" value={specGenerating}
                color="border-blue-800/40 bg-blue-950/20 text-blue-300 animate-pulse" />
            )}
            {specPending > 0 && (
              <StatChip icon="ti-clock" label="Specs pending" value={specPending}
                color="border-gray-700/60 bg-gray-800/40 text-gray-400" />
            )}
            <StatChip icon="ti-user-check" label="Assigned" value={assigned}
              color="border-indigo-800/40 bg-indigo-950/20 text-indigo-300" />
            {inProgress > 0 && (
              <StatChip icon="ti-bolt" label="In progress" value={inProgress}
                color="border-amber-800/40 bg-amber-950/20 text-amber-300" />
            )}
            {inReview > 0 && (
              <StatChip icon="ti-eye" label="In review" value={inReview}
                color="border-purple-800/40 bg-purple-950/20 text-purple-300" />
            )}
            <StatChip icon="ti-circle-check" label="Done" value={done}
              sub={`${donePct}% of total`}
              color="border-teal-800/40 bg-teal-950/20 text-teal-300" />
          </div>

          {/* Progress bars */}
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-3">
              <span className="w-24 shrink-0 text-[10px] uppercase tracking-wide text-gray-600">Spec coverage</span>
              <div className="flex-1 h-1.5 rounded-full bg-gray-800 overflow-hidden">
                <div className="h-1.5 rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${specPct}%` }} />
              </div>
              <span className="w-8 text-right text-[10px] text-gray-500">{specPct}%</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-24 shrink-0 text-[10px] uppercase tracking-wide text-gray-600">Dev progress</span>
              <div className="flex-1 h-1.5 rounded-full bg-gray-800 overflow-hidden flex">
                <div className="h-1.5 bg-blue-500/70 transition-all duration-500"
                  style={{ width: `${totalTasks > 0 ? Math.round((assigned / totalTasks) * 100) : 0}%` }} />
                <div className="h-1.5 bg-amber-500/70 transition-all duration-500"
                  style={{ width: `${totalTasks > 0 ? Math.round((inProgress / totalTasks) * 100) : 0}%` }} />
                <div className="h-1.5 bg-purple-500/70 transition-all duration-500"
                  style={{ width: `${totalTasks > 0 ? Math.round((inReview / totalTasks) * 100) : 0}%` }} />
                <div className="h-1.5 bg-teal-500 transition-all duration-500" style={{ width: `${donePct}%` }} />
              </div>
              <span className="w-8 text-right text-[10px] text-gray-500">{donePct}%</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-24 shrink-0" />
              <div className="flex gap-3 text-[9px] text-gray-600 uppercase tracking-wide">
                <span className="flex items-center gap-1"><span className="inline-block h-1.5 w-3 rounded-sm bg-blue-500/70" />assigned</span>
                <span className="flex items-center gap-1"><span className="inline-block h-1.5 w-3 rounded-sm bg-amber-500/70" />in progress</span>
                <span className="flex items-center gap-1"><span className="inline-block h-1.5 w-3 rounded-sm bg-purple-500/70" />in review</span>
                <span className="flex items-center gap-1"><span className="inline-block h-1.5 w-3 rounded-sm bg-teal-500" />done</span>
              </div>
            </div>
          </div>

          {/* Health issues */}
          {healthIssues.length > 0 && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-gray-600">
                <i className="ti ti-heartbeat text-sm" aria-hidden />
                <span>Coverage analysis</span>
              </div>
              {healthIssues.map((issue, i) => {
                const s = ISSUE_STYLE[issue.level];
                return (
                  <div key={i} className={`flex items-start gap-3 overflow-hidden rounded-lg border pl-0 ${s.badge}`}>
                    <div className={`w-1 self-stretch shrink-0 ${s.bar} rounded-l-lg`} />
                    <div className="flex flex-1 items-center justify-between gap-3 px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <i className={`ti ${issue.icon} text-sm shrink-0 ${s.icon}`} aria-hidden />
                        <span className="text-xs leading-relaxed">{issue.message}</span>
                      </div>
                      {issue.action === "regenerate" && (
                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            onClick={() => onGenerate("fill-gaps")}
                            className="flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium bg-indigo-650 hover:bg-indigo-600 text-white border border-indigo-700/40 cursor-pointer transition-all"
                          >
                            <i className="ti ti-wand" aria-hidden /> Solve gaps with AI
                          </button>
                          <Link
                            href={`/traceability?project=${projectId}`}
                            className="rounded px-2.5 py-1 text-[11px] font-medium bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700/60"
                          >
                            Analyze Gaps
                          </Link>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Spec detail panel ─────────────────────────────────────────────────────────

function SecHeader({ icon, label, color }: { icon: string; label: string; color: string }) {
  return (
    <div className={`flex items-center gap-2 border-b pb-2 ${color}`}>
      <i className={`ti ${icon} text-sm`} aria-hidden />
      <span className="text-[11px] font-semibold uppercase tracking-widest">{label}</span>
    </div>
  );
}

function FilePill({ path, variant }: { path: string; variant: "create" | "modify" }) {
  return (
    <div className={`flex items-center gap-2 rounded px-2.5 py-1.5 font-mono text-xs ${
      variant === "create"
        ? "bg-emerald-950/40 text-emerald-400 border border-emerald-800/30"
        : "bg-amber-950/40 text-amber-400 border border-amber-800/30"
    }`}>
      <i className={`ti ${variant === "create" ? "ti-file-plus" : "ti-file-pencil"} text-xs`} aria-hidden />
      {path}
    </div>
  );
}

function SpecDetailPanel({
  content,
  summaryText,
  copiedKey,
  onCopySummary,
  onPrintPdf,
  onDownloadMd,
}: {
  content:       Record<string, unknown>;
  summaryText:   string;
  copiedKey:     string | null;
  onCopySummary: () => void;
  onPrintPdf:    () => void;
  onDownloadMd:  () => void;
}) {
  const tables      = specTables(content);
  const endpoints   = specEndpoints(content);
  const filesCreate = strList(content, "files_to_create");
  const filesModify = strList(content, "files_to_modify");
  const criteria    = strList(content, "acceptance_criteria");

  return (
    <div className="space-y-6">
      {/* Print / download spec */}
      <div className="flex justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          className="h-8 px-3 text-xs"
          onClick={onDownloadMd}
          title="Download this spec as a Markdown file"
        >
          <i className="ti ti-markdown mr-1.5 text-sm" aria-hidden />
          Download MD
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-8 px-3 text-xs"
          onClick={onPrintPdf}
          title="Download this spec as an A4 PDF"
        >
          <i className="ti ti-file-type-pdf mr-1.5 text-sm" aria-hidden />
          Print PDF
        </Button>
      </div>

      {/* Scope */}
      <div>
        <SecHeader icon="ti-target" label="What to build" color="border-purple-800/40 text-purple-400" />
        <p className="mt-3 text-sm leading-relaxed text-gray-300">{strField(content, "task_scope")}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {strField(content, "linked_fr") && (
            <span className="rounded bg-gray-800 px-2 py-0.5 font-mono text-xs text-gray-400">
              {strField(content, "linked_fr")}
            </span>
          )}
          {strField(content, "linked_prd_feature") && (
            <span className="rounded border border-indigo-800/30 bg-indigo-950/40 px-2 py-0.5 text-xs text-indigo-400">
              {strField(content, "linked_prd_feature")}
            </span>
          )}
        </div>
      </div>

      {/* Files */}
      {(filesCreate.length > 0 || filesModify.length > 0) && (
        <div>
          <SecHeader icon="ti-files" label="Files" color="border-emerald-800/40 text-emerald-400" />
          <div className="mt-3 space-y-1.5">
            {filesCreate.map((f) => <FilePill key={f} path={f} variant="create" />)}
            {filesModify.map((f) => <FilePill key={f} path={f} variant="modify" />)}
          </div>
        </div>
      )}

      {/* Database */}
      {tables.length > 0 && (
        <div>
          <SecHeader icon="ti-database" label="Database" color="border-blue-800/40 text-blue-400" />
          <div className="mt-3 space-y-2">
            {tables.map((table) => (
              <div key={table.name} className="rounded-lg border border-blue-900/40 bg-blue-950/20 px-3 py-2.5">
                <p className="font-mono text-sm font-semibold text-blue-300">{table.name}</p>
                <p className="mt-1 font-mono text-xs text-gray-500">
                  {(table.relevant_columns ?? []).map((c) => `${c.name ?? ""}: ${c.type ?? ""}`).join("  ·  ") || "—"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* API endpoints */}
      {endpoints.length > 0 && (
        <div>
          <SecHeader icon="ti-api" label="API endpoints" color="border-indigo-800/40 text-indigo-400" />
          <div className="mt-3 space-y-2">
            {endpoints.map((ep, i) => (
              <div key={i} className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className={`rounded px-2 py-0.5 font-mono text-xs font-bold ${
                    METHOD_STYLE[ep.method?.toUpperCase() ?? ""] ?? "bg-gray-700 text-gray-300"
                  }`}>
                    {ep.method?.toUpperCase()}
                  </span>
                  <span className="font-mono text-sm text-gray-200">{ep.path}</span>
                </div>
                {ep.request_body  && <p className="mt-1.5 text-xs text-gray-500">↑ {ep.request_body}</p>}
                {ep.response_schema && (
                  <p className="text-xs text-gray-500">↓ {ep.response_schema}{ep.status_code ? ` · ${ep.status_code}` : ""}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Frontend */}
      {(strField(content, "frontend_route") || strField(content, "frontend_component")) && (
        <div>
          <SecHeader icon="ti-layout" label="Frontend" color="border-teal-800/40 text-teal-400" />
          <div className="mt-3 space-y-1.5">
            {strField(content, "frontend_route") && (
              <div className="rounded border border-teal-900/40 bg-teal-950/20 px-3 py-2">
                <span className="text-[10px] uppercase tracking-wide text-gray-600">route  </span>
                <span className="font-mono text-sm text-teal-300">{strField(content, "frontend_route")}</span>
              </div>
            )}
            {strField(content, "frontend_component") && (
              <div className="rounded border border-teal-900/40 bg-teal-950/20 px-3 py-2">
                <span className="text-[10px] uppercase tracking-wide text-gray-600">component  </span>
                <span className="font-mono text-sm text-teal-300">{strField(content, "frontend_component")}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Acceptance criteria */}
      {criteria.length > 0 && (
        <div>
          <SecHeader icon="ti-circle-check" label="Acceptance criteria" color="border-emerald-800/40 text-emerald-400" />
          <ul className="mt-3 space-y-2">
            {criteria.map((c, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm leading-relaxed text-gray-300">
                <span className="mt-0.5 h-4 w-4 shrink-0 rounded border border-emerald-700/50 bg-emerald-950/30" />
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Technical notes */}
      {strField(content, "technical_notes") && (
        <div>
          <SecHeader icon="ti-alert-triangle" label="Technical notes" color="border-amber-800/40 text-amber-400" />
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-gray-400">
            {strField(content, "technical_notes")}
          </p>
        </div>
      )}

      {/* Implementation summary */}
      <div className="rounded-xl border border-indigo-800/50 bg-indigo-950/20">
        <div className="flex items-center justify-between border-b border-indigo-800/30 px-4 py-2.5">
          <div className="flex items-center gap-2 text-indigo-400">
            <i className="ti ti-clipboard-text text-base" aria-hidden />
            <span className="text-xs font-semibold uppercase tracking-widest">Implementation summary</span>
          </div>
          <Button size="sm" className="h-7 px-3 text-xs" onClick={onCopySummary} disabled={!summaryText}>
            {copiedKey === "summary" ? "✓ Copied" : "Copy"}
          </Button>
        </div>
        <pre className="max-h-96 overflow-auto p-4 font-mono text-xs leading-5 text-gray-300 whitespace-pre-wrap">
          {summaryText || "No summary yet."}
        </pre>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TasksPage() {
  const [projects,          setProjects]          = useState<Project[]>([]);
  const [projectId,         setProjectId]         = useState("");
  const [board,             setBoard]             = useState<KanbanBoard | null>(null);
  const [missingFrs,        setMissingFrs]        = useState<string[] | null>(null);
  const [allSpecsLoading,   setAllSpecsLoading]   = useState(false);
  const [srsList,           setSrsList]           = useState<SRS[]>([]);
  const [users,             setUsers]             = useState<UserResponse[]>([]);
  const [selectedTask,      setSelectedTask]      = useState<KanbanTask | null>(null);
  const [spec,              setSpec]              = useState<TaskSpec | null>(null);
  const [clearLoading,      setClearLoading]      = useState(false);
  const [specLoadingTaskId, setSpecLoadingTaskId] = useState<string | null>(null);
  const [dragTaskId,        setDragTaskId]        = useState<string | null>(null);
  const [bible,             setBible]             = useState<{ content: string; project_name: string } | null>(null);
  const [copiedKey,         setCopiedKey]         = useState<string | null>(null);
  const [models,            setModels]            = useState<AiModelOption[]>([]);
  const [specModel,         setSpecModel]         = useState<ModelChoice | null>(null);
  const [editingTask,       setEditingTask]       = useState(false);
  const [taskDraft,         setTaskDraft]         = useState<TaskDraft>({
    title: "", description: "", priority: "medium", module_name: "",
  });

  const copiedTimer    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSpecRef = useRef<{ specId: string } | null>(null);
  const panelRef       = useRef<HTMLDivElement>(null);

  const extractJob = useAiJob({ onComplete: () => { void loadBoard(projectId) } });

  const specJob = useAiJob({
    onComplete: async () => {
      const pending = pendingSpecRef.current;
      if (pending) {
        try { setSpec(await api.getSpec(pending.specId)) } catch { setSpec(null) }
        pendingSpecRef.current = null;
      }
      setSpecLoadingTaskId(null);
      await loadBoard(projectId);
    },
    onFailed: () => { pendingSpecRef.current = null; setSpecLoadingTaskId(null) },
  });

  // "Generate all specs" — one server-side job that generates every task's spec
  // serially; keeps running even if the tab closes. Individual buttons unchanged.
  const allSpecsJob = useAiJob({
    onComplete: async () => { await loadBoard(projectId); },
  });

  async function handleGenerateAllSpecs() {
    if (!projectId || allSpecsJob.isRunning) return;
    if (!window.confirm(
      "Generate specs for all tasks that don't have one yet?\n\nRuns on the server, one task at a time — it keeps going even if you close this tab. Individual specs are unaffected.",
    )) return;
    try {
      const { task_id } = await api.generateAllSpecs(projectId, true, specModel);
      allSpecsJob.startJob(task_id, "Generating all specs");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Could not start bulk spec generation");
    }
  }

  const extractBtn = aiButtonLabel("Generate tasks", extractJob.status, extractJob.operationName === "Extracting modules");

  const loadBoard = useCallback(async (pid: string) => {
    if (!pid) return;
    setBoard(await api.getKanban(pid));
    // Authoritative FR coverage (real SRS FR list, normalized server-side)
    try {
      const cov = await api.getTaskCoverage(pid);
      setMissingFrs(cov.missing_frs ?? []);
    } catch {
      setMissingFrs(null);
    }
  }, []);

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      const fromUrl = typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("project")
        : null;
      setProjectId(fromUrl || p[0]?.id || "");
    });
    api.listAiModels()
      .then((c) => setModels(c.models.filter((m) => m.available)))
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setBible(null); setSelectedTask(null); setSpec(null);
    loadBoard(projectId);
    api.listSrs(projectId).then(setSrsList);
    api.listUsers().then(setUsers).catch(() => setUsers([]));
  }, [projectId, loadBoard]);

  useEffect(() => () => { if (copiedTimer.current) clearTimeout(copiedTimer.current) }, []);

  // ── Computed ───────────────────────────────────────────────────────────────

  const seqMap = useMemo(() => {
    const all = COLUMNS.flatMap(({ key }) => (board?.[key] ?? []).filter((t) => !isSystem(t)));
    all.sort((a, b) => a.order_index - b.order_index);
    const m = new Map<string, number>();
    all.forEach((t, i) => m.set(t.id, i + 1));
    return m;
  }, [board]);

  const totalTasks = useMemo(
    () => COLUMNS.reduce((s, { key }) => s + (board?.[key]?.filter((t) => !isSystem(t)).length ?? 0), 0),
    [board],
  );

  const selectedIsSystem = selectedTask !== null && isSystem(selectedTask);
  const panelOpen        = selectedTask !== null && !selectedIsSystem;
  const isGenerating     =
    specLoadingTaskId === selectedTask?.id &&
    (specJob.isRunning || specJob.status === "pending" || specJob.status === "failed");
  const hasReadySpec = spec?.status === "ready" && !!spec.content_json;
  const summaryText  = typeof spec?.content_json?.cursor_prompt === "string"
    ? (spec.content_json.cursor_prompt as string) : "";
  const specContent  = (spec?.content_json ?? {}) as Record<string, unknown>;

  // ── Handlers ───────────────────────────────────────────────────────────────

  function showCopied(key: string) {
    setCopiedKey(key);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopiedKey(null), 2000);
  }

  async function copyText(key: string, text: string) {
    if (await copyToClipboard(text)) showCopied(key);
    else alert("Could not copy to clipboard.");
  }

  const projectName = projects.find((p) => p.id === projectId)?.name ?? "Project";

  function specMdTaskFor(task: KanbanTask): SpecMdTask {
    return {
      title:        task.title,
      seq:          seqMap.get(task.id) ?? null,
      priority:     task.priority,
      module_name:  task.module_name ?? null,
      linked_fr:    task.linked_fr ?? task.fr_references?.[0] ?? null,
      effort_hours: task.effort_hours ?? null,
    };
  }

  function handlePrintSpec() {
    if (!selectedTask || !hasReadySpec) return;
    try {
      buildSpecPdf({ task: specMdTaskFor(selectedTask), content: specContent, projectName });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Could not generate the spec PDF.");
    }
  }

  function handleDownloadSpecMd() {
    if (!selectedTask || !hasReadySpec) return;
    const md = buildSpecMarkdown(specMdTaskFor(selectedTask), specContent, 1);
    downloadTextFile(`${slugFilename(projectName)}-spec-${slugFilename(selectedTask.title)}.md`, md);
  }

  async function handleDownloadAllSpecsMd() {
    if (!board) return;
    setAllSpecsLoading(true);
    try {
      // All non-system tasks, ordered by serial
      const tasks = COLUMNS
        .flatMap(({ key }) => board[key] ?? [])
        .filter((t) => !isSystem(t))
        .sort((a, b) => (seqMap.get(a.id) ?? 9e9) - (seqMap.get(b.id) ?? 9e9));

      const items: AllSpecsItem[] = [];
      for (const t of tasks) {
        if (t.spec_status !== "ready") continue;
        try {
          const ts = await api.getSpecByTask(t.id);
          if (ts.content_json) {
            items.push({ task: specMdTaskFor(t), content: ts.content_json as Record<string, unknown> });
          }
        } catch { /* skip tasks whose spec can't be fetched */ }
      }

      if (items.length === 0) {
        alert("No generated specs to export yet. Generate task specs first.");
        return;
      }
      const md = buildAllSpecsMarkdown(projectName, items);
      downloadTextFile(`${slugFilename(projectName)}-all-specs.md`, md);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Could not export all specs.");
    } finally {
      setAllSpecsLoading(false);
    }
  }

  async function fetchBible(force = false): Promise<string | null> {
    if (bible && !force) return bible.content;
    try { const d = await api.getProjectBible(projectId); setBible(d); return d.content }
    catch (err) { alert(err instanceof Error ? err.message : "Could not build the project bible."); return null }
  }

  async function fetchSystemGuide(task: KanbanTask): Promise<string | null> {
    try {
      const ts = await api.getSpecByTask(task.id);
      const g  = ts.content_json?.cursor_prompt;
      if (typeof g === "string" && g) return g;
      alert("No guide content found."); return null;
    } catch { alert("Could not load the guide."); return null }
  }

  async function handleCopyBible()    { const c = await fetchBible(); if (c) await copyText("bible", c) }
  async function handleRefreshBible() { await fetchBible(true); showCopied("bible-refreshed") }
  async function handleCopySystemGuide(task: KanbanTask, key: string) {
    const g = await fetchSystemGuide(task); if (g) await copyText(key, g);
  }
  async function handleDownloadChecklist(task: KanbanTask) {
    const g = await fetchSystemGuide(task); if (!g) return;
    const b = new Blob([g], { type: "text/plain;charset=utf-8" });
    const u = URL.createObjectURL(b);
    const a = document.createElement("a");
    a.href = u; a.download = "local-ui-test-checklist.txt"; a.click();
    URL.revokeObjectURL(u);
  }

  async function handleGenerateTasks(mode: "generate" | "regenerate" | "fill-gaps" = "generate") {
    const ELIGIBLE = ["approved", "finalized", "confirmed"];
    const approved = srsList.find((s) =>
      ELIGIBLE.includes(s.status) ||
      ELIGIBLE.includes((s as SRS & { workflow_status?: string }).workflow_status ?? ""),
    );
    if (!approved) {
      alert(
        "No eligible SRS found. Finalize your PRD and SRS, and confirm a finalized architecture suite before generating tasks.",
      );
      return;
    }

    // regenerate → replace_existing=true  (wipes old tasks + specs, creates fresh set)
    // fill-gaps  → fill_gaps_only=true    (only adds tasks for FRs with no coverage)
    // generate   → both false             (first run)
    const opts = mode === "regenerate"
      ? { replaceExisting: true }
      : mode === "fill-gaps"
        ? { fillGapsOnly: true }
        : {};

    extractJob.startManual("Extracting modules");
    try {
      const { task_id } = await api.extractModules(projectId, approved.id, opts);
      extractJob.startJob(task_id, "Extracting modules");
    } catch (err) {
      extractJob.failManual(err instanceof Error ? err.message : "Failed to start task generation");
    }
  }

  async function handleClearAllTasks() {
    const name  = projects.find((p) => p.id === projectId)?.name ?? "this project";
    const count = COLUMNS.reduce((s, { key }) => s + (board?.[key]?.length ?? 0), 0);
    if (count === 0) { alert("No tasks to delete."); return }
    if (!confirm(`Delete all ${count} tasks for "${name}"?\n\nThis also removes all specs.`)) return;
    setClearLoading(true);
    try {
      const r = await api.clearProjectTasks(projectId);
      setSelectedTask(null); setSpec(null); setBible(null);
      await loadBoard(projectId);
      alert(`Deleted ${r.deleted_tasks} task(s) and ${r.deleted_specs} spec(s).`);
    } finally { setClearLoading(false) }
  }

  async function handleDrop(column: keyof KanbanBoard) {
    if (!dragTaskId) return;
    await api.updateTaskStatus(dragTaskId, column);
    setDragTaskId(null);
    await loadBoard(projectId);
  }

  async function openTask(task: KanbanTask) {
    setSelectedTask(task);
    setEditingTask(false);
    setTaskDraft({ title: task.title, description: task.description ?? "", priority: task.priority, module_name: task.module_name ?? "" });
    try { setSpec(await api.getSpecByTask(task.id)) } catch { setSpec(null) }
    setTimeout(() => panelRef.current?.scrollTo({ top: 0 }), 50);
  }

  async function handleGenerateSpec(task: KanbanTask) {
    setSpecLoadingTaskId(task.id);
    specJob.startManual("Generating spec");
    try {
      const { spec_id, task_id_celery } = await api.generateSpec(task.id, specModel);
      pendingSpecRef.current = { specId: spec_id };
      specJob.startJob(task_id_celery, "Generating spec");
    } catch (err) {
      setSpecLoadingTaskId(null);
      specJob.failManual(err instanceof Error ? err.message : "Failed to start spec generation");
    }
  }

  async function handleRegenerateSpec(task: KanbanTask) {
    setSpecLoadingTaskId(task.id);
    specJob.startManual("Generating spec");
    try {
      const { spec_id, task_id_celery } = await api.regenerateSpecByTask(task.id, specModel);
      pendingSpecRef.current = { specId: spec_id };
      specJob.startJob(task_id_celery, "Generating spec");
    } catch (err) {
      setSpecLoadingTaskId(null);
      specJob.failManual(err instanceof Error ? err.message : "Failed to regenerate spec");
    }
  }

  async function handleSaveTaskEdit() {
    if (!selectedTask) return;
    const updated = await api.updateTask(selectedTask.id, {
      title:       taskDraft.title,
      description: taskDraft.description || null,
      priority:    taskDraft.priority,
      module_name: taskDraft.module_name || null,
    });
    setSelectedTask({ ...selectedTask, ...updated });
    setEditingTask(false);
    await loadBoard(projectId);
  }

  async function handleDeleteTask(task: KanbanTask) {
    if (!confirm("Delete this task and its spec?")) return;
    await api.deleteTask(task.id);
    if (selectedTask?.id === task.id) { setSelectedTask(null); setSpec(null) }
    await loadBoard(projectId);
  }

  async function handleAssignSpec(userId: string) {
    if (!spec) return;
    setSpec(await api.assignSpec(spec.id, userId));
  }

  // ── Card renderers ─────────────────────────────────────────────────────────

  function renderCard(task: KanbanTask) {
    const isSelected = selectedTask?.id === task.id;
    const hasSpec    = task.spec_status === "ready";
    const left       = PRIORITY_LEFT[task.priority] ?? PRIORITY_LEFT.medium;
    const seq        = seqMap.get(task.id);

    return (
      <div
        key={task.id}
        draggable
        onDragStart={() => setDragTaskId(task.id)}
        onClick={() => void openTask(task)}
        className={`cursor-pointer rounded-md border border-l-2 px-3 py-3 transition-all select-none ${left} ${
          isSelected
            ? "border-blue-500/60 bg-gray-800/90 ring-1 ring-blue-500/30"
            : "border-gray-700/60 bg-gray-900/80 hover:border-gray-600/70 hover:bg-gray-900"
        }`}
      >
        <div className="flex items-start gap-1.5">
          {seq !== undefined && (
            <span className="mt-0.5 shrink-0 rounded bg-gray-800 px-1 py-0.5 font-mono text-[9px] text-gray-600">
              #{String(seq).padStart(3, "0")}
            </span>
          )}
          <p className="min-w-0 flex-1 text-[13px] font-medium leading-snug text-gray-100">{task.title}</p>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {task.module_name && (
            <span className="rounded border border-indigo-800/30 bg-indigo-950/60 px-1.5 py-0.5 text-[10px] text-indigo-400">
              {task.module_name.split("—").pop()?.trim() ?? task.module_name}
            </span>
          )}
          {(task.linked_fr ?? task.fr_references?.[0]) && (
            <span className="rounded bg-gray-800 px-1.5 py-0.5 font-mono text-[10px] text-gray-500">
              {task.linked_fr ?? task.fr_references?.[0]}
            </span>
          )}
          {task.effort_hours != null && <span className="text-[10px] text-gray-600">{task.effort_hours}h</span>}
          {hasSpec && (
            <span className="ml-auto rounded border border-emerald-800/30 bg-emerald-950/50 px-1.5 py-0.5 text-[10px] text-emerald-400">
              ✓ spec
            </span>
          )}
        </div>
      </div>
    );
  }

  function renderSystemCard(task: KanbanTask) {
    const st = SYS_STYLES[task.order_index];
    if (!st) return null;
    const isBible  = task.order_index === PROJECT_BIBLE_ORDER;
    const isAudit  = task.order_index === CODE_AUDIT_ORDER;
    const isUiTest = task.order_index === LOCAL_UI_TEST_ORDER;
    const isDeploy = task.order_index === DEPLOY_ORDER;

    return (
      <div key={task.id} className={`rounded-md border p-2.5 ${st.card}`}>
        <div className="flex items-start justify-between gap-2">
          <p className="text-[13px] font-medium text-gray-100">{isBible ? "Project bible" : task.title}</p>
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold tracking-widest ${st.bCls}`}>{st.badge}</span>
        </div>
        {task.module_name && <p className="mt-1 text-[10px] text-gray-500">{task.module_name}</p>}
        {isBible && (
          <div className="mt-2 space-y-1.5">
            <Button className="w-full h-7 text-xs" onClick={() => void handleCopyBible()}>
              {copiedKey === "bible" ? "✓ Copied" : "Copy project bible"}
            </Button>
            <Button variant="outline" size="sm" className="w-full h-7 text-xs" onClick={() => void handleRefreshBible()}>
              {copiedKey === "bible-refreshed" ? "Refreshed" : "↺ Refresh"}
            </Button>
          </div>
        )}
        {isAudit  && <div className="mt-2"><Button className="w-full h-7 text-xs" onClick={() => void handleCopySystemGuide(task, "audit")}>{copiedKey === "audit" ? "✓ Copied" : "Copy audit guide"}</Button></div>}
        {isUiTest && <div className="mt-2"><Button className="w-full h-7 text-xs" onClick={() => void handleDownloadChecklist(task)}>Download checklist</Button></div>}
        {isDeploy && <div className="mt-2"><Button className="w-full h-7 text-xs" onClick={() => void handleCopySystemGuide(task, "deploy")}>{copiedKey === "deploy" ? "✓ Copied" : "Copy deploy guide"}</Button></div>}
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-3">

      {/* Lean header */}
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold text-gray-100">Kanban board</h1>
        <ScreenModelSelector screen="tasks" />
        <select
          title="Select project"
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button
          type="button"
          onClick={() => void handleGenerateAllSpecs()}
          disabled={!projectId || allSpecsJob.isRunning || totalTasks === 0}
          title="Generate a spec for every task that doesn't have one — runs on the server, one task at a time (keeps going even if you close this tab)"
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-indigo-700 bg-indigo-900/40 px-3 py-1.5 text-sm text-indigo-200 hover:bg-indigo-900/60 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <i className={`ti ${allSpecsJob.isRunning ? "ti-loader-2 animate-spin" : "ti-list-check"}`} aria-hidden />
          {allSpecsJob.isRunning ? "Generating all specs…" : "Generate all specs"}
        </button>
      </div>

      {/* Dashboard */}
      <Dashboard
        projectId={projectId}
        board={board}
        totalTasks={totalTasks}
        missingFrs={missingFrs}
        extractJob={extractJob}
        extractBtnLabel={extractBtn}
        clearLoading={clearLoading}
        onGenerate={(mode) => void handleGenerateTasks(mode)}
        onClear={() => void handleClearAllTasks()}
      />

      {extractJob.isVisible && (
        <AiStatusBar
          {...aiJobStatusBarProps(extractJob)}
          onCancel={extractJob.cancel}
          onTryAgain={() => void handleGenerateTasks()}
        />
      )}

      {allSpecsJob.isVisible && (
        <AiStatusBar
          {...aiJobStatusBarProps(allSpecsJob)}
          operationName={allSpecsJob.operationName || "Generating all specs"}
          nextStep="Each task's spec is generated one by one — this continues on the server even if you close the tab."
          onCancel={allSpecsJob.cancel}
        />
      )}

      {/* ── 50/50 split: kanban + developer panel ── */}
      <div className="flex gap-2 items-start">

        {/* Kanban — takes left half (or full width when panel closed) */}
        <div className="flex-1 min-w-0 overflow-x-auto pb-2">
          <div className="flex gap-2.5" style={{ minWidth: "max-content" }}>
            {COLUMNS.map(({ key, label }) => {
              const cs       = COL_STYLE[key] ?? COL_STYLE.backlog;
              const colTasks = board?.[key] ?? [];
              const sysTasks = colTasks.filter(isSystem).sort((a, b) => a.order_index - b.order_index);
              const regTasks = colTasks.filter((t) => !isSystem(t));

              return (
                <div
                  key={key}
                  className={`w-48 shrink-0 rounded-xl border p-2.5 ${cs.border} ${cs.bg}`}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => void handleDrop(key)}
                >
                  <div className={`mb-2.5 flex items-center gap-2 ${cs.head}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${cs.dot}`} />
                    <span className="text-[11px] font-semibold uppercase tracking-widest">{label}</span>
                    <span className="ml-auto rounded bg-gray-800/60 px-1.5 py-0.5 text-[10px] text-gray-500">
                      {colTasks.length}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {regTasks.map((t) => renderCard(t))}
                    {sysTasks.length > 0 && regTasks.length > 0 && (
                      <div className="flex items-center gap-2 py-1">
                        <div className="h-px flex-1 bg-gray-700/50" />
                        <span className="text-[9px] uppercase tracking-widest text-gray-600">system</span>
                        <div className="h-px flex-1 bg-gray-700/50" />
                      </div>
                    )}
                    {sysTasks.map((t) => renderSystemCard(t))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Export all generated specs as one Markdown file (ordered by serial) */}
          {totalTasks > 0 && (
            <div className="mt-4 flex items-center gap-3 border-t border-gray-800 pt-3">
              <Button
                variant="outline"
                size="sm"
                className="h-8 px-3 text-xs"
                disabled={allSpecsLoading}
                onClick={() => void handleDownloadAllSpecsMd()}
                title="Download a single Markdown file with every generated spec, ordered by task serial"
              >
                <i className="ti ti-markdown mr-1.5 text-sm" aria-hidden />
                {allSpecsLoading ? "Collecting specs…" : "Print all specs (MD)"}
              </Button>
              <span className="text-[11px] text-gray-600">
                One Markdown summary of every generated spec, in task order.
              </span>
            </div>
          )}
        </div>

        {/* Developer panel — right half (50%) of the screen, sticky */}
        {panelOpen && selectedTask && (
          <div
            className="w-[560px] shrink-0 sticky top-2 z-10 flex flex-col rounded-xl border border-gray-700/60 bg-gray-950 shadow-2xl overflow-hidden"
            style={{ maxHeight: "calc(100vh - 24px)" }}
          >
            {/* Panel header */}
            <div className="border-b border-gray-800 bg-gray-900 px-5 pt-3 pb-3 flex-shrink-0">
              <div className="flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  {seqMap.get(selectedTask.id) !== undefined && (
                    <div className="mb-1 font-mono text-[10px] text-gray-600">
                      Task #{String(seqMap.get(selectedTask.id)).padStart(3, "0")}
                    </div>
                  )}
                  {editingTask ? (
                    <input
                      title="Task title"
                      className="w-full rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 focus:border-blue-500 focus:outline-none"
                      value={taskDraft.title}
                      onChange={(e) => setTaskDraft({ ...taskDraft, title: e.target.value })}
                    />
                  ) : (
                    <h3 className="text-base font-semibold leading-snug text-gray-100">{selectedTask.title}</h3>
                  )}
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${PRIORITY_BADGE[selectedTask.priority] ?? PRIORITY_BADGE.medium}`}>
                      {selectedTask.priority}
                    </span>
                    {selectedTask.module_name && (
                      <span className="rounded border border-indigo-800/30 bg-indigo-950/60 px-1.5 py-0.5 text-[10px] text-indigo-400">
                        {selectedTask.module_name}
                      </span>
                    )}
                    {(selectedTask.linked_fr ?? selectedTask.fr_references?.[0]) && (
                      <span className="rounded bg-gray-800 px-1.5 py-0.5 font-mono text-[10px] text-gray-500">
                        {selectedTask.linked_fr ?? selectedTask.fr_references?.[0]}
                      </span>
                    )}
                    {selectedTask.effort_hours != null && (
                      <span className="text-[10px] text-gray-600">{selectedTask.effort_hours}h</span>
                    )}
                  </div>
                </div>

                {/* Edit / Delete / Close — moved from card to panel */}
                <div className="flex items-center gap-0.5 flex-shrink-0">
                  {editingTask ? (
                    <>
                      <button
                        title="Save"
                        onClick={() => void handleSaveTaskEdit()}
                        className="rounded px-2.5 py-1 text-xs font-medium bg-blue-600 text-white hover:bg-blue-500"
                      >
                        Save
                      </button>
                      <button
                        title="Cancel"
                        onClick={() => setEditingTask(false)}
                        className="rounded p-1.5 text-gray-500 hover:text-gray-300 hover:bg-gray-800"
                      >
                        <i className="ti ti-x text-sm" aria-hidden />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        title="Edit task"
                        onClick={() => {
                          setEditingTask(true);
                          setTaskDraft({
                            title:       selectedTask.title,
                            description: selectedTask.description ?? "",
                            priority:    selectedTask.priority,
                            module_name: selectedTask.module_name ?? "",
                          });
                        }}
                        className="rounded p-1.5 text-gray-500 hover:text-blue-400 hover:bg-blue-950/30"
                      >
                        <i className="ti ti-edit text-sm" aria-hidden />
                      </button>
                      <button
                        title="Delete task"
                        onClick={() => void handleDeleteTask(selectedTask)}
                        className="rounded p-1.5 text-gray-600 hover:text-red-400 hover:bg-red-950/30"
                      >
                        <i className="ti ti-trash text-sm" aria-hidden />
                      </button>
                      <button
                        title="Close panel"
                        onClick={() => { setSelectedTask(null); setSpec(null) }}
                        className="rounded p-1.5 text-gray-600 hover:text-gray-300 hover:bg-gray-800"
                      >
                        <i className="ti ti-x text-sm" aria-hidden />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Scrollable body */}
            <div ref={panelRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-5">

              {/* Edit form */}
              {editingTask && (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-gray-500">Description</label>
                    <textarea
                      title="Task description"
                      className="h-24 w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                      value={taskDraft.description}
                      onChange={(e) => setTaskDraft({ ...taskDraft, description: e.target.value })}
                    />
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="mb-1 block text-[11px] uppercase tracking-wide text-gray-500">Priority</label>
                      <select
                        title="Priority"
                        className="w-full rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-200"
                        value={taskDraft.priority}
                        onChange={(e) => setTaskDraft({ ...taskDraft, priority: e.target.value })}
                      >
                        {["critical", "high", "medium", "low"].map((p) => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </select>
                    </div>
                    <div className="flex-1">
                      <label className="mb-1 block text-[11px] uppercase tracking-wide text-gray-500">Module</label>
                      <input
                        title="Module name"
                        className="w-full rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                        value={taskDraft.module_name}
                        onChange={(e) => setTaskDraft({ ...taskDraft, module_name: e.target.value })}
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Description (view mode) */}
              {!editingTask && selectedTask.description && (
                <p className="text-sm leading-relaxed text-gray-400">{selectedTask.description}</p>
              )}

              {/* Generate / Regenerate */}
              {!editingTask && (
                <div className="rounded-lg border border-gray-800 bg-gray-800/30 p-4 space-y-3">
                  <div>
                    <label className="mb-1.5 block text-[11px] uppercase tracking-wide text-gray-500">Model override</label>
                    <select
                      title="AI model for spec generation"
                      className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
                      value={specModel ? `${specModel.provider}::${specModel.model}` : ""}
                      onChange={(e) => {
                        const [provider, model] = e.target.value.split("::");
                        setSpecModel(provider && model ? { provider, model } : null);
                      }}
                    >
                      <option value="">Auto model</option>
                      {models.map((m) => (
                        <option key={`${m.provider}::${m.model}`} value={`${m.provider}::${m.model}`}>
                          {m.label} ({m.cost})
                        </option>
                      ))}
                    </select>
                  </div>
                  {hasReadySpec ? (
                    <Button
                      variant="outline"
                      className="w-full h-9 text-sm"
                      onClick={() => void handleRegenerateSpec(selectedTask)}
                      disabled={isGenerating}
                    >
                      <i className="ti ti-refresh mr-1.5" aria-hidden />
                      {isGenerating ? "Regenerating…" : "Regenerate spec"}
                    </Button>
                  ) : (
                    <Button
                      className={`w-full h-9 text-sm ${aiButtonClassName("normal")}`}
                      onClick={() => void handleGenerateSpec(selectedTask)}
                      disabled={isGenerating}
                    >
                      <i className="ti ti-sparkles mr-1.5" aria-hidden />
                      {isGenerating ? "Generating…" : "Generate spec"}
                    </Button>
                  )}
                  {specLoadingTaskId === selectedTask.id && specJob.isVisible && (
                    <AiStatusBar
                      {...aiJobStatusBarProps(specJob)}
                      onCancel={() => { specJob.cancel(); setSpecLoadingTaskId(null) }}
                      onTryAgain={() => void handleGenerateSpec(selectedTask)}
                    />
                  )}
                </div>
              )}

              {/* Spec content */}
              {!editingTask && hasReadySpec && (
                <>
                  <div className="h-px bg-gray-800" />
                  <SpecDetailPanel
                    content={specContent}
                    summaryText={summaryText}
                    copiedKey={copiedKey}
                    onCopySummary={() => void copyText("summary", summaryText)}
                    onPrintPdf={handlePrintSpec}
                    onDownloadMd={handleDownloadSpecMd}
                  />
                </>
              )}

              {/* Assign developer */}
              {!editingTask && hasReadySpec && users.filter((u) => u.role === "code_creator" || u.role === "developer").length > 0 && (
                <div>
                  <label className="mb-1.5 block text-[11px] uppercase tracking-wide text-gray-500">Assign to developer</label>
                  <select
                    title="Assign spec to developer"
                    className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
                    value={spec?.assigned_to_id ?? ""}
                    onChange={(e) => e.target.value && void handleAssignSpec(e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {users
                      .filter((u) => u.role === "code_creator" || u.role === "developer")
                      .map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                  </select>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
