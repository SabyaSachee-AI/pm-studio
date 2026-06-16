"use client";

import { useEffect, useRef, useState } from "react";
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
import { api, type Project, type Requirement } from "@/lib/api";
import { formatRequirementLabel } from "@/lib/requirementDisplay";

export default function RequirementsPage() {
  const searchParams = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const aiJob = useAiJob({
    onComplete: () => {
      if (projectId) void api.listRequirements(projectId).then(setRequirements);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
  });

  const uploadBtn = aiButtonLabel(
    "Upload PDF",
    aiJob.status,
    aiJob.operationName === "Analyzing requirement",
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
    setListError(null);
    api
      .listRequirements(projectId)
      .then(setRequirements)
      .catch((err: Error) => {
        setRequirements([]);
        setListError(err.message || "Could not load requirements.");
      });
  }, [projectId]);

  async function handleUpload() {
    setUploadError(null);
    if (!file) {
      setUploadError("Choose a PDF file first.");
      return;
    }
    if (!projectId) {
      setUploadError("Select a project first.");
      return;
    }
    try {
      const { task_id } = await api.uploadRequirement(projectId, file);
      aiJob.startJob(task_id, "Analyzing requirement");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Upload failed. Please try again.";
      setUploadError(message);
    }
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.preventDefault();
    if (!confirm("Delete this requirement? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await api.deleteRequirement(id);
      setRequirements((prev) => prev.filter((r) => r.id !== id));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Requirements</h1>
        <ScreenModelSelector screen="requirements" />
      </div>
      <div className="flex gap-2">
        <select
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.length === 0 ? (
            <option value="">No projects</option>
          ) : (
            projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))
          )}
        </select>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={fileInputRef}
          id="requirement-file"
          type="file"
          accept=".pdf,application/pdf"
          className="sr-only"
          onChange={(e) => {
            setUploadError(null);
            setFile(e.target.files?.[0] ?? null);
          }}
        />
        <label
          htmlFor="requirement-file"
          className={`inline-flex cursor-pointer items-center rounded-md border px-4 py-2 text-sm ${
            uploadBtn.disabled || aiJob.isRunning
              ? "cursor-not-allowed border-gray-600 bg-gray-800 text-gray-400 opacity-60"
              : "border-gray-700 hover:bg-gray-800"
          }`}
        >
          {file ? file.name : "Choose PDF file"}
        </label>
        <Button
          type="button"
          onClick={() => void handleUpload()}
          disabled={uploadBtn.disabled || aiJob.isRunning || !file || !projectId}
          className={aiButtonClassName(uploadBtn.variant)}
        >
          {uploadBtn.label}
        </Button>
      </div>
      {uploadError ? (
        <p className="text-sm text-red-400" role="alert">
          {uploadError}
        </p>
      ) : null}
      {aiJob.isVisible ? (
        <AiStatusBar
          {...aiJobStatusBarProps(aiJob)}
          onCancel={aiJob.cancel}
          onTryAgain={() => void handleUpload()}
        />
      ) : null}
      {listError ? (
        <p className="text-sm text-red-400" role="alert">
          {listError}
        </p>
      ) : null}
      <div className="rounded-xl border border-gray-800">
        {requirements.length === 0 && !listError ? (
          <p className="px-4 py-6 text-sm text-gray-500">
            No requirements yet. Upload a PDF to get started.
          </p>
        ) : null}
        {requirements.map((r) => (
          <div
            key={r.id}
            className="flex items-center border-b border-gray-800 last:border-0 hover:bg-gray-900/50"
          >
            <Link
              href={`/requirements/${r.id}`}
              className="flex-1 px-4 py-3"
            >
              <p className="font-medium">{formatRequirementLabel(r)}</p>
              <div className="mt-1">
                <WorkflowStatusBadge status={r.status} />
              </div>
            </Link>
            <button
              onClick={(e) => void handleDelete(e, r.id)}
              disabled={deletingId === r.id}
              title="Delete requirement"
              className="mr-3 flex h-7 w-7 shrink-0 items-center justify-center rounded border border-red-900/40 bg-red-950/20 text-red-500 hover:border-red-700/60 hover:bg-red-950/40 hover:text-red-400 disabled:opacity-40 transition-colors"
            >
              {deletingId === r.id
                ? <i className="ti ti-loader-2 animate-spin text-sm" aria-hidden />
                : <i className="ti ti-trash text-sm" aria-hidden />}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
