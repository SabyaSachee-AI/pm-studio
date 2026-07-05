"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, type AiChainStatus, type AiChainModelStatus } from "@/lib/api";

const TASK_LABELS: Record<string, string> = {
  code_generate: "Code generation",
  code_polish: "Code polish",
  spec_generate: "Task specs",
  arch_generate: "Architecture",
  srs_generate: "SRS",
  prd_generate: "PRD",
  req_analyze: "Requirement analysis",
};

const STATUS_STYLE: Record<
  AiChainModelStatus,
  { label: string; dot: string; text: string }
> = {
  ready: { label: "Ready", dot: "bg-emerald-500", text: "text-emerald-400" },
  cooling: { label: "Cooling (limit hit)", dot: "bg-amber-500", text: "text-amber-400" },
  no_key: { label: "No key — skipped", dot: "bg-red-500", text: "text-red-400" },
  unsupported: { label: "Unsupported", dot: "bg-zinc-500", text: "text-zinc-400" },
};

const REFRESH_MS = 5000;

export function AiChainStatusPanel() {
  const [taskType, setTaskType] = useState("code_generate");
  const [data, setData] = useState<AiChainStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (tt: string) => {
    try {
      setLoading(true);
      const res = await api.getAiChainStatus(tt);
      setData(res);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load chain status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(taskType);
    timer.current = setInterval(() => void load(taskType), REFRESH_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [taskType, load]);

  const usable = data?.usable_now ?? 0;
  const total = data?.total ?? 0;
  const cooling = data?.models.filter((m) => m.status === "cooling").length ?? 0;
  const noKey = data?.models.filter((m) => m.status === "no_key").length ?? 0;

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">Live model chain status</h2>
          <p className="text-sm text-zinc-500">
            Which fallback models are usable right now — refreshes every 5s.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm"
          >
            {(data?.task_types ?? Object.keys(TASK_LABELS)).map((tt) => (
              <option key={tt} value={tt}>
                {TASK_LABELS[tt] ?? tt}
              </option>
            ))}
          </select>
          <span
            className={`h-2 w-2 rounded-full ${loading ? "bg-emerald-500 animate-pulse" : "bg-zinc-600"}`}
            title={loading ? "Refreshing…" : "Idle"}
          />
        </div>
      </div>

      {error ? (
        <p className="rounded-md border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-400">
          {error}
        </p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-4 text-sm">
            <span className="text-emerald-400">
              <b>{usable}</b>/{total} usable now
            </span>
            {cooling > 0 && <span className="text-amber-400">{cooling} cooling</span>}
            {noKey > 0 && <span className="text-red-400">{noKey} no key</span>}
            {usable <= 2 && total > 0 && (
              <span className="text-amber-400">
                ⚠ Chain is shallow — add more provider keys so it does not stall when quotas run out.
              </span>
            )}
          </div>

          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900/60 text-left text-xs uppercase text-zinc-500">
                <tr>
                  <th className="px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Provider</th>
                  <th className="px-3 py-2 font-medium">Model</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data?.models.map((m) => {
                  const s = STATUS_STYLE[m.status];
                  return (
                    <tr key={m.index} className="border-t border-zinc-800/70">
                      <td className="px-3 py-2 text-zinc-500">{m.index}</td>
                      <td className="px-3 py-2">{m.provider}</td>
                      <td className="px-3 py-2 font-mono text-xs text-zinc-400">{m.model}</td>
                      <td className={`px-3 py-2 ${s.text}`}>
                        <span className="inline-flex items-center gap-1.5">
                          <span className={`h-2 w-2 rounded-full ${s.dot}`} />
                          {s.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {!data?.models.length && (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-zinc-500">
                      {loading ? "Loading…" : "No models in this chain."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
