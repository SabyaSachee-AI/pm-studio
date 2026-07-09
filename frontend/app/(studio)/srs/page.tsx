"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { Button } from "@/components/ui/button";
import { FinalizedBadge, WorkflowStatusBadge } from "@/components/ui/FinalizedBadge";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import {
  aiButtonClassName,
  aiButtonLabel,
  useAiJob,
} from "@/lib/hooks/useAiJob";
import { api, type PRD, type Project, type SRS } from "@/lib/api";

function isFinalized(srs: SRS): boolean {
  return srs.status === "approved";
}

export default function SrsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [prds, setPrds] = useState<PRD[]>([]);
  const [srsList, setSrsList] = useState<SRS[]>([]);
  const [prdId, setPrdId] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const aiJob = useAiJob({
    onComplete: () => {
      if (projectId) void api.listSrs(projectId).then(setSrsList);
    },
  });

  const generateBtn = aiButtonLabel(
    "Generate SRS",
    aiJob.status,
    aiJob.operationName === "Generating SRS",
  );

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      if (p[0]) setProjectId(p[0].id);
    });
  }, []);

  useEffect(() => {
    if (!projectId) return;
    api.listPrds(projectId).then((p) => {
      // Show any PRD that is not a raw draft or rejected — backend maps status to workflow_status
      const eligible = p.filter(
        (x) => x.status !== "draft" && x.status !== "rejected",
      );
      setPrds(eligible);
      if (eligible[0]) setPrdId(eligible[0].id);
    });
    api.listSrs(projectId).then(setSrsList);
  }, [projectId]);

  async function handleGenerate() {
    if (!projectId || !prdId) return;
    try {
      const { task_id } = (await api.generateSrs(projectId, prdId)) as {
        task_id: string;
      };
      aiJob.startJob(task_id, "Generating SRS");
    } catch (err) {
      aiJob.reportError(
        err instanceof Error ? err.message : "Could not start SRS generation",
        "Generating SRS",
      );
    }
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.preventDefault();
    if (!confirm("Delete this SRS? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await api.deleteSrs(id);
      setSrsList((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Could not delete the SRS");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">SRS documents</h1>
        <ScreenModelSelector screen="srs" />
      </div>
      <div className="flex flex-wrap gap-2">
        <select
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <select
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={prdId}
          onChange={(e) => setPrdId(e.target.value)}
        >
          {prds.length === 0 && (
            <option value="" disabled>No confirmed PRD — confirm a PRD first</option>
          )}
          {prds.map((p) => {
            const projectName = projects.find((pr) => pr.id === p.project_id)?.name ?? "";
            const statusLabel =
              p.status === "approved" || p.status === "finalized"
                ? "Finalized"
                : p.status === "confirmed"
                  ? "Confirmed"
                  : "Ready";
            return (
              <option key={p.id} value={p.id}>
                {projectName ? `${projectName} — PRD v${p.version}` : `PRD v${p.version}`} ({statusLabel})
              </option>
            );
          })}
        </select>
        <Button
          onClick={() => void handleGenerate()}
          disabled={generateBtn.disabled || aiJob.isRunning}
          className={aiButtonClassName(generateBtn.variant)}
        >
          {generateBtn.label}
        </Button>
      </div>
      {aiJob.isVisible ? (
        <AiStatusBar
          {...aiJobStatusBarProps(aiJob)}
          onCancel={aiJob.cancel}
          onTryAgain={() => void handleGenerate()}
        />
      ) : null}
      <div className="rounded-xl border border-gray-800">
        {srsList.map((s) => {
          const finalized = isFinalized(s);
          return (
            <div
              key={s.id}
              className="flex items-center border-b border-gray-800 last:border-0 hover:bg-gray-900/50"
            >
              <Link href={`/srs/${s.id}`} className="flex flex-1 items-center gap-3 px-4 py-3">
                <span className="font-medium">
                  {projects.find((p) => p.id === s.project_id)?.name
                    ? `${projects.find((p) => p.id === s.project_id)!.name} — SRS v${s.version}`
                    : `SRS v${s.version}`}
                </span>
                <WorkflowStatusBadge status={s.status} />
                {finalized && (
                  <span title="Approved — cannot delete">
                    <i className="ti ti-lock text-xs text-emerald-600" aria-hidden />
                  </span>
                )}
              </Link>
              <button
                onClick={(e) => void handleDelete(e, s.id)}
                disabled={finalized || deletingId === s.id}
                title={finalized ? "Approved SRS documents cannot be deleted" : "Delete SRS"}
                className="mr-3 flex h-7 w-7 shrink-0 items-center justify-center rounded border border-red-900/40 bg-red-950/20 text-red-500 hover:border-red-700/60 hover:bg-red-950/40 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-30 transition-colors"
              >
                {deletingId === s.id
                  ? <i className="ti ti-loader-2 animate-spin text-sm" aria-hidden />
                  : <i className="ti ti-trash text-sm" aria-hidden />}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
