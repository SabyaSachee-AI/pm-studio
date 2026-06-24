"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type BuildSummary, type Project } from "@/lib/api";
import { Button } from "@/components/ui/button";

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-gray-800 text-gray-400",
  scaffolding: "bg-blue-950/50 text-blue-300",
  scaffolded: "bg-blue-950/50 text-blue-300",
  generating: "bg-amber-950/50 text-amber-300",
  qa: "bg-purple-950/50 text-purple-300",
  ready: "bg-emerald-950/50 text-emerald-300",
  failed: "bg-red-950/50 text-red-300",
};

export default function BuildIndexPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [builds, setBuilds] = useState<BuildSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      const fromUrl = typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("project") : null;
      setProjectId(fromUrl || p[0]?.id || "");
    });
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    api.listBuilds(projectId)
      .then(setBuilds)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load builds"))
      .finally(() => setLoading(false));
  }, [projectId]);

  async function handleCreate() {
    if (!projectId) return;
    setCreating(true);
    setError("");
    try {
      const build = await api.createBuild(projectId);
      router.push(`/build/${build.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create build — finalize the architecture first.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-gray-500">Code factory</p>
          <h1 className="text-2xl font-semibold text-white">Build</h1>
          <p className="text-sm text-gray-400">Generate the full codebase from the architecture + Kanban specs.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            title="Project"
            className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <Button disabled={!projectId || creating} onClick={() => void handleCreate()}>
            <i className="ti ti-plus mr-1.5" aria-hidden />
            {creating ? "Creating…" : "New build"}
          </Button>
        </div>
      </div>

      {error ? (
        <p className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</p>
      ) : null}

      {loading ? (
        <p className="text-sm text-gray-500">Loading builds…</p>
      ) : builds.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-700 p-10 text-center">
          <p className="text-gray-400">No builds yet for this project.</p>
          <p className="mt-1 text-xs text-gray-600">
            Click <strong className="text-gray-300">New build</strong> to scaffold a repo and generate code from your tasks.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {builds.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => router.push(`/build/${b.id}`)}
              className="flex w-full items-center justify-between gap-4 rounded-lg border border-gray-800 bg-gray-900/50 px-4 py-3 text-left hover:border-gray-600"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-gray-200">
                  {b.display_name || `Build v${b.version}`}
                </p>
                <p className="text-xs text-gray-500">
                  {b.file_count} files · {new Date(b.created_at).toLocaleString()}
                </p>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {b.quality_score != null ? (
                  <span className="text-xs text-gray-400">{b.quality_score.toFixed(1)}/10</span>
                ) : null}
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[b.status] ?? STATUS_STYLE.draft}`}>
                  {b.status}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
