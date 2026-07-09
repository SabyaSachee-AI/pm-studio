"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type ActiveJob, type DashboardStats, type UserResponse } from "@/lib/api";

// ─── helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1)   return "just now";
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function pct(used: number, limit: number): number {
  if (!limit) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

// ─── sub-components ───────────────────────────────────────────────────────────

function StatCard({
  icon, label, value, sub, accent,
}: {
  icon: string; label: string; value: string | number; sub?: string; accent: string;
}) {
  return (
    <div className={`relative overflow-hidden rounded-xl border bg-gray-900/60 p-5 ${accent}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-gray-500">{label}</p>
          <p className="mt-1.5 text-3xl font-bold tabular-nums text-white">{value}</p>
          {sub && <p className="mt-0.5 text-[11px] text-gray-500">{sub}</p>}
        </div>
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${accent.replace("border-", "bg-").split(" ")[0]}/20`}>
          <i className={`ti ${icon} text-xl ${accent.split(" ").find(c => c.startsWith("text-")) ?? "text-gray-400"}`} aria-hidden />
        </div>
      </div>
    </div>
  );
}

function SectionHeading({ icon, label }: { icon: string; label: string }) {
  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-gray-600 mb-3">
      <i className={`ti ${icon} text-sm`} aria-hidden />
      <span>{label}</span>
    </div>
  );
}

function MiniBar({ color, pct: p, label, value }: { color: string; pct: number; label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-xs text-gray-400 truncate">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-gray-800 overflow-hidden">
        <div className={`h-2 rounded-full transition-all duration-700 ${color}`} style={{ width: `${p}%` }} />
      </div>
      <span className="w-8 text-right text-xs text-gray-500">{value}</span>
    </div>
  );
}

const TASK_STATUS_CFG: Record<string, { label: string; color: string; dot: string }> = {
  backlog:     { label: "Backlog",     color: "bg-gray-600",    dot: "bg-gray-500" },
  assigned:    { label: "Assigned",    color: "bg-indigo-500",  dot: "bg-indigo-400" },
  in_progress: { label: "In progress", color: "bg-amber-500",   dot: "bg-amber-400" },
  in_review:   { label: "In review",  color: "bg-purple-500",  dot: "bg-purple-400" },
  done:        { label: "Done",        color: "bg-teal-500",    dot: "bg-teal-400" },
};

const STATUS_CFG: Record<string, { label: string; dot: string }> = {
  active:    { label: "Active",    dot: "bg-emerald-400" },
  on_hold:   { label: "On hold",  dot: "bg-amber-400" },
  completed: { label: "Completed",dot: "bg-teal-400" },
  archived:  { label: "Archived", dot: "bg-gray-500" },
};

const PIPELINE_STEPS = [
  { key: "has_requirement", label: "Requirements", icon: "ti-file-upload",      color: "text-violet-400" },
  { key: "has_prd",         label: "PRD",          icon: "ti-book",             color: "text-blue-400" },
  { key: "has_srs",         label: "SRS",          icon: "ti-file-text",        color: "text-cyan-400" },
  { key: "has_architecture",label: "Architecture", icon: "ti-sitemap",          color: "text-indigo-400" },
  { key: "has_tasks",       label: "Tasks",        icon: "ti-columns",          color: "text-amber-400" },
  { key: "has_specs",       label: "Dev specs",    icon: "ti-code",             color: "text-emerald-400" },
];

const PROVIDER_COLOR: Record<string, string> = {
  purple:  "bg-purple-500",  orange:  "bg-orange-500",  blue:   "bg-blue-500",
  cyan:    "bg-cyan-500",    pink:    "bg-pink-500",     green:  "bg-emerald-500",
  indigo:  "bg-indigo-500",  red:     "bg-red-500",      teal:   "bg-teal-500",
  yellow:  "bg-yellow-500",  violet:  "bg-violet-500",   gray:   "bg-gray-500",
};

// ─── page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [user,  setUser]  = useState<UserResponse | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [jobs,  setJobs]  = useState<ActiveJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tick,  setTick]  = useState(0);          // clock refresh
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const [u, s, j] = await Promise.all([
        api.me(),
        api.getDashboardStats(),
        api.getActiveJobs().catch(() => ({ jobs: [], count: 0 })),
      ]);
      setUser(u);
      setStats(s);
      setJobs(j.jobs);
      setError(null);
    } catch {
      setError("Could not load dashboard stats — retrying…");
    }
  }, []);

  // initial load + 30-second auto-refresh
  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 30_000);
    return () => clearInterval(id);
  }, [load]);

  // clock tick every second
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1_000);
    return () => clearInterval(id);
  }, []);

  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dateStr = now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric", year: "numeric" });

  if (!stats) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="space-y-2 text-center">
          <i className="ti ti-loader-2 animate-spin text-3xl text-indigo-400" aria-hidden />
          <p className="text-sm text-gray-500">{error ?? "Loading dashboard…"}</p>
        </div>
      </div>
    );
  }

  const { projects, clients, users, pipeline, tasks, ai, recent_projects } = stats;

  const totalTokens   = ai.total_tokens;
  const specCovPct    = tasks.total > 0 ? Math.round((tasks.specs_ready / tasks.total) * 100) : 0;
  const donePct       = tasks.total > 0 ? Math.round(((tasks.by_status.done ?? 0) / tasks.total) * 100) : 0;

  // Active AI providers (with at least 1 request today)
  const activeProviders = Object.entries(ai.by_provider)
    .filter(([, v]) => v.requests > 0)
    .sort((a, b) => b[1].requests - a[1].requests);

  // All providers sorted by tier then requests
  const allProviders = Object.entries(ai.by_provider).sort(
    (a, b) => (b[1].requests - a[1].requests)
  );

  return (
    <div className="space-y-6 pb-10">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-end justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-600">PM Studio</p>
          <h1 className="text-2xl font-bold text-white">Control centre</h1>
          {user && <p className="mt-0.5 text-sm text-gray-500">Welcome back, {user.full_name}</p>}
        </div>
        <div className="text-right">
          <p className="font-mono text-lg font-semibold text-white tabular-nums">{timeStr}</p>
          <p className="text-xs text-gray-600">{dateStr}</p>
          <p className="mt-0.5 text-[10px] text-gray-700">auto-refresh 30s</p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-800/40 bg-amber-950/20 px-4 py-2.5 text-sm text-amber-400">
          <i className="ti ti-alert-triangle" aria-hidden /> {error}
        </div>
      )}

      {/* ── Running AI jobs (live, across all projects) ───────────────── */}
      {jobs.length > 0 && (
        <section className="rounded-xl border border-blue-900/50 bg-blue-950/15 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-blue-300">
              <i className="ti ti-activity-heartbeat animate-pulse" aria-hidden />
              Running now — {jobs.length} job{jobs.length > 1 ? "s" : ""}
            </h2>
            <span className="text-[10px] text-gray-600">auto-refresh 30s</span>
          </div>
          <div className="space-y-2">
            {jobs.map((j) => {
              const pctDone = j.total_tasks
                ? Math.min(99, Math.round((j.done_tasks / j.total_tasks) * 100))
                : null;
              return (
                <Link
                  key={j.build_id}
                  href={`/build/${j.build_id}`}
                  className="block rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2.5 transition hover:border-blue-700"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium text-gray-200">
                      {j.project_name}
                      <span className="ml-1.5 text-xs text-gray-500">Build v{j.version}</span>
                    </p>
                    <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-400">
                      {j.phase ?? j.status}
                    </span>
                  </div>
                  {j.total_tasks ? (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-800">
                        <div
                          className="h-full rounded-full bg-blue-600 transition-all"
                          style={{ width: `${Math.max(3, pctDone ?? 0)}%` }}
                        />
                      </div>
                      <span className="text-[11px] tabular-nums text-gray-400">
                        {j.done_tasks}/{j.total_tasks}
                      </span>
                    </div>
                  ) : null}
                  {(j.message || j.current_task) && (
                    <p className="mt-1.5 truncate text-xs text-gray-500">
                      {j.message ?? j.current_task}
                    </p>
                  )}
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Top stat cards ───────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard icon="ti-folder-filled" label="Projects"
          value={projects.total}
          sub={`${projects.by_status.active ?? 0} active`}
          accent="border-indigo-800/40 text-indigo-400" />
        <StatCard icon="ti-building" label="Clients"
          value={clients.total}
          accent="border-blue-800/40 text-blue-400" />
        <StatCard icon="ti-users" label="Users"
          value={users.total}
          sub={`${users.by_role.studio_owner ?? 0} owner · ${users.by_role.studio_admin ?? 0} admin`}
          accent="border-violet-800/40 text-violet-400" />
        <StatCard icon="ti-columns" label="Total tasks"
          value={tasks.total}
          sub={`${donePct}% done · ${specCovPct}% spec coverage`}
          accent="border-teal-800/40 text-teal-400" />
      </div>

      {/* ── AI summary cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard icon="ti-bolt" label="AI calls today"
          value={fmt(ai.total_requests_today)}
          accent="border-amber-800/40 text-amber-400" />
        <StatCard icon="ti-arrow-right" label="Tokens in"
          value={fmt(ai.total_tokens_in)}
          accent="border-orange-800/40 text-orange-400" />
        <StatCard icon="ti-arrow-left" label="Tokens out"
          value={fmt(ai.total_tokens_out)}
          accent="border-emerald-800/40 text-emerald-400" />
        <StatCard icon="ti-infinity" label="Total tokens"
          value={fmt(totalTokens)}
          sub={activeProviders.length > 0 ? `${activeProviders.length} active provider${activeProviders.length > 1 ? "s" : ""}` : "no usage today"}
          accent="border-pink-800/40 text-pink-400" />
      </div>

      {/* ── Pipeline funnel ──────────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <SectionHeading icon="ti-git-branch" label="Project pipeline — stages reached" />
        <div className="flex items-end gap-2">
          {PIPELINE_STEPS.map((step, i) => {
            const count = pipeline[step.key] ?? 0;
            const maxCount = Math.max(projects.total, 1);
            const barH = Math.max(8, Math.round((count / maxCount) * 120));
            const isLast = i === PIPELINE_STEPS.length - 1;
            return (
              <div key={step.key} className="flex flex-1 flex-col items-center gap-2">
                <span className={`text-sm font-bold tabular-nums ${step.color}`}>{count}</span>
                <div className="w-full flex items-end justify-center" style={{ height: 128 }}>
                  <div
                    className={`w-full max-w-[48px] rounded-t-md transition-all duration-700 ${step.color.replace("text-", "bg-")}/30 border-t-2 ${step.color.replace("text-", "border-")}`}
                    style={{ height: barH }}
                  />
                </div>
                <i className={`ti ${step.icon} text-lg ${step.color}`} aria-hidden />
                <span className="text-center text-[10px] text-gray-600 leading-tight">{step.label}</span>
                {!isLast && (
                  <div className="absolute" />
                )}
              </div>
            );
          })}
        </div>
        {/* arrow connectors */}
        <div className="mt-2 flex items-center justify-between px-6">
          {PIPELINE_STEPS.slice(0, -1).map((s) => (
            <i key={s.key} className="ti ti-chevron-right text-gray-700 text-xs" aria-hidden />
          ))}
        </div>
      </div>

      {/* ── Mid row: project status + task breakdown ─────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">

        {/* Project status breakdown */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <SectionHeading icon="ti-chart-bar" label="Project status" />
          <div className="space-y-2.5">
            {Object.entries(projects.by_status).map(([status, count]) => {
              const cfg = STATUS_CFG[status] ?? { label: status, dot: "bg-gray-500" };
              const p = projects.total > 0 ? Math.round((count / projects.total) * 100) : 0;
              return (
                <div key={status} className="flex items-center gap-3">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${cfg.dot}`} />
                  <span className="w-20 shrink-0 text-xs text-gray-400">{cfg.label}</span>
                  <div className="flex-1 h-2 rounded-full bg-gray-800 overflow-hidden">
                    <div className={`h-2 rounded-full transition-all duration-700 ${cfg.dot}`} style={{ width: `${p}%` }} />
                  </div>
                  <span className="w-6 text-right text-xs text-gray-500">{count}</span>
                </div>
              );
            })}
          </div>

          <div className="mt-5 border-t border-gray-800 pt-4">
            <SectionHeading icon="ti-users" label="User roles" />
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(users.by_role)
                .filter(([, v]) => v > 0)
                .map(([role, count]) => (
                  <div key={role} className="rounded-lg border border-gray-800 bg-gray-800/40 px-3 py-2">
                    <p className="text-lg font-bold text-white tabular-nums">{count}</p>
                    <p className="text-[10px] text-gray-500 leading-tight truncate">{role.replace(/_/g, " ")}</p>
                  </div>
                ))}
            </div>
          </div>
        </div>

        {/* Task kanban distribution */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <SectionHeading icon="ti-columns" label="Task distribution" />
          {tasks.total === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-gray-600">
              <i className="ti ti-inbox text-3xl mb-2" aria-hidden />
              <p className="text-sm">No tasks generated yet</p>
            </div>
          ) : (
            <>
              {/* Stacked progress bar */}
              <div className="h-4 w-full rounded-full overflow-hidden flex mb-4">
                {Object.entries(TASK_STATUS_CFG).map(([key, cfg]) => {
                  const count = tasks.by_status[key] ?? 0;
                  const w = tasks.total > 0 ? (count / tasks.total) * 100 : 0;
                  return w > 0 ? (
                    <div key={key} className={`${cfg.color} h-full transition-all duration-700`} style={{ width: `${w}%` }} title={`${cfg.label}: ${count}`} />
                  ) : null;
                })}
              </div>
              <div className="space-y-2.5">
                {Object.entries(TASK_STATUS_CFG).map(([key, cfg]) => {
                  const count = tasks.by_status[key] ?? 0;
                  const p = tasks.total > 0 ? Math.round((count / tasks.total) * 100) : 0;
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${cfg.dot}`} />
                      <span className="w-24 shrink-0 text-xs text-gray-400">{cfg.label}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-gray-800 overflow-hidden">
                        <div className={`h-1.5 rounded-full transition-all duration-700 ${cfg.color}`} style={{ width: `${p}%` }} />
                      </div>
                      <span className="w-8 text-right text-xs text-gray-500">{count}</span>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 border-t border-gray-800 pt-4">
                <div className="rounded-lg border border-emerald-800/30 bg-emerald-950/20 px-4 py-3">
                  <p className="text-xl font-bold text-emerald-300 tabular-nums">{tasks.specs_ready}</p>
                  <p className="text-[10px] text-emerald-600">Specs ready</p>
                  <p className="text-[10px] text-gray-600">{specCovPct}% coverage</p>
                </div>
                <div className="rounded-lg border border-teal-800/30 bg-teal-950/20 px-4 py-3">
                  <p className="text-xl font-bold text-teal-300 tabular-nums">{tasks.by_status.done ?? 0}</p>
                  <p className="text-[10px] text-teal-600">Tasks done</p>
                  <p className="text-[10px] text-gray-600">{donePct}% complete</p>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── AI provider usage ────────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <div className="flex items-center justify-between mb-3">
          <SectionHeading icon="ti-robot" label="AI provider usage — today" />
          <span className="text-[10px] text-gray-700">Resets at midnight UTC</span>
        </div>
        {activeProviders.length === 0 ? (
          <div className="flex items-center gap-3 rounded-lg border border-dashed border-gray-800 bg-gray-800/20 px-4 py-5 text-sm text-gray-600">
            <i className="ti ti-moon text-lg" aria-hidden /> No AI usage recorded today
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {activeProviders.map(([key, p]) => {
              const barColor = PROVIDER_COLOR[p.color] ?? "bg-gray-500";
              const reqPct   = pct(p.requests, p.requests_limit);
              const tokPct   = pct(p.tokens_total, p.tokens_limit);
              return (
                <div key={key} className="rounded-lg border border-gray-800 bg-gray-800/40 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 rounded-full ${barColor}`} />
                      <span className="text-sm font-medium text-white">{p.label}</span>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[9px] uppercase tracking-wide ${
                      p.tier === "paid" ? "bg-amber-950/60 text-amber-400 border border-amber-800/40"
                                       : "bg-gray-800 text-gray-500 border border-gray-700/40"
                    }`}>{p.tier}</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="w-16 text-[10px] text-gray-600">Requests</span>
                      <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                        {p.requests_limit > 0 ? (
                          <div className={`h-1.5 rounded-full ${barColor} transition-all`} style={{ width: `${reqPct}%` }} />
                        ) : (
                          <div className={`h-1.5 rounded-full ${barColor} transition-all`} style={{ width: "30%" }} />
                        )}
                      </div>
                      <span className="w-12 text-right text-[10px] text-gray-500">
                        {p.requests}{p.requests_limit > 0 ? `/${fmt(p.requests_limit)}` : ""}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-16 text-[10px] text-gray-600">Tokens in</span>
                      <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                        <div className={`h-1.5 rounded-full ${barColor} opacity-60 transition-all`} style={{ width: "100%" }} />
                      </div>
                      <span className="w-12 text-right text-[10px] text-gray-500">{fmt(p.tokens_in)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-16 text-[10px] text-gray-600">Tokens out</span>
                      <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                        <div className={`h-1.5 rounded-full ${barColor} opacity-80 transition-all`} style={{ width: "100%" }} />
                      </div>
                      <span className="w-12 text-right text-[10px] text-gray-500">{fmt(p.tokens_out)}</span>
                    </div>
                  </div>
                  <div className="mt-3 border-t border-gray-700/40 pt-2 flex justify-between">
                    <span className="text-[10px] text-gray-600">Total tokens</span>
                    <span className="text-[10px] font-semibold text-white tabular-nums">{fmt(p.tokens_total)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Recent projects ──────────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <SectionHeading icon="ti-clock" label="Recent projects" />
        {recent_projects.length === 0 ? (
          <p className="text-sm text-gray-600">No projects yet — create one to get started.</p>
        ) : (
          <div className="divide-y divide-gray-800/60">
            {recent_projects.map((p) => {
              const cfg = STATUS_CFG[p.status] ?? { label: p.status, dot: "bg-gray-500" };
              return (
                <div key={p.id} className="flex items-center gap-3 py-2.5">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${cfg.dot}`} />
                  <span className="flex-1 text-sm text-white truncate">{p.name}</span>
                  <span className="text-xs text-gray-600">{cfg.label}</span>
                  <span className="w-16 text-right text-[11px] text-gray-700 tabular-nums">{timeAgo(p.updated_at)}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-t border-gray-800/60 pt-4 text-[10px] text-gray-700">
        <span>PM Studio — The Ultimate Web App Ecosystem</span>
        <span>Stats generated {stats.generated_at ? new Date(stats.generated_at).toLocaleTimeString() : "—"}</span>
      </div>
    </div>
  );
}
