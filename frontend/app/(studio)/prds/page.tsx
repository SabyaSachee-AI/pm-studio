"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { Button } from "@/components/ui/button";
import { FinalizedBadge, WorkflowStatusBadge } from "@/components/ui/FinalizedBadge";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import {
  aiButtonClassName,
  aiButtonLabel,
  useAiJob,
} from "@/lib/hooks/useAiJob";
import { api, type PRD, type Project, type Requirement } from "@/lib/api";
import { formatRequirementLabel } from "@/lib/requirementDisplay";

function isFinalized(prd: PRD): boolean {
  return prd.status === "approved";
}

function isPrdEligible(r: Requirement): boolean {
  return r.status === "finalized";
}

export default function PrdsPage() {
  const searchParams = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [prds, setPrds] = useState<PRD[]>([]);
  const [reqId, setReqId] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const aiJob = useAiJob({
    onComplete: () => {
      if (projectId) void api.listPrds(projectId).then(setPrds);
    },
  });

  const generateBtn = aiButtonLabel(
    "Generate PRD",
    aiJob.status,
    aiJob.operationName === "Generating PRD",
  );

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      const fromUrl = searchParams.get("project");
      const match = fromUrl ? p.find((x) => x.id === fromUrl) : undefined;
      if (match) setProjectId(match.id);
      else if (p[0]) setProjectId(p[0].id);
    });
  }, [searchParams]);

  useEffect(() => {
    if (!projectId) return;
    api.listRequirements(projectId).then((r) => {
      const eligible = r.filter(isPrdEligible);
      setRequirements(eligible);
      setReqId(eligible[0]?.id ?? "");
    });
    api.listPrds(projectId).then(setPrds);
  }, [projectId]);

  async function handleGenerate() {
    if (!projectId || !reqId) return;
    const { task_id } = (await api.generatePrd(projectId, reqId)) as {
      task_id: string;
    };
    aiJob.startJob(task_id, "Generating PRD");
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.preventDefault();
    if (!confirm("Delete this PRD? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await api.deletePrd(id);
      setPrds((prev) => prev.filter((p) => p.id !== id));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">PRDs</h1>
        <ScreenModelSelector screen="prds" />
      </div>
      <div className="flex flex-wrap gap-2">
        <select
          aria-label="Project"
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
          aria-label="Finalized requirement"
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={reqId}
          onChange={(e) => setReqId(e.target.value)}
          disabled={requirements.length === 0}
        >
          {requirements.length === 0 ? (
            <option value="">No finalized requirements</option>
          ) : (
            requirements.map((r) => (
              <option key={r.id} value={r.id}>
                {formatRequirementLabel(r)}
              </option>
            ))
          )}
        </select>
        <Button
          onClick={() => void handleGenerate()}
          disabled={
            generateBtn.disabled ||
            aiJob.isRunning ||
            !reqId ||
            requirements.length === 0
          }
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
      {requirements.length === 0 && projectId ? (
        <p className="text-sm text-amber-400/90">
          Finalize a requirement on the Requirements page before generating a PRD.
        </p>
      ) : null}
      <div className="rounded-xl border border-gray-800">
        {prds.map((p) => {
          const finalized = isFinalized(p);
          return (
            <div
              key={p.id}
              className="flex items-center border-b border-gray-800 last:border-0 hover:bg-gray-900/50"
            >
              <Link href={`/prds/${p.id}`} className="flex flex-1 items-center gap-3 px-4 py-3">
                <span className="font-medium">
                  {projects.find((pr) => pr.id === p.project_id)?.name
                    ? `${projects.find((pr) => pr.id === p.project_id)!.name} — PRD v${p.version}`
                    : `PRD v${p.version}`}
                </span>
                <WorkflowStatusBadge status={p.status} />
                {finalized && (
                  <span title="Approved — cannot delete">
                    <i className="ti ti-lock text-xs text-emerald-600" aria-hidden />
                  </span>
                )}
              </Link>
              <button
                onClick={(e) => void handleDelete(e, p.id)}
                disabled={finalized || deletingId === p.id}
                title={finalized ? "Approved PRDs cannot be deleted" : "Delete PRD"}
                className="mr-3 flex h-7 w-7 shrink-0 items-center justify-center rounded border border-red-900/40 bg-red-950/20 text-red-500 hover:border-red-700/60 hover:bg-red-950/40 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-30 transition-colors"
              >
                {deletingId === p.id
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
