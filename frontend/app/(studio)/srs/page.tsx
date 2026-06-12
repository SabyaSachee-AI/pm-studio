"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { Button } from "@/components/ui/button";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import {
  aiButtonClassName,
  aiButtonLabel,
  useAiJob,
} from "@/lib/hooks/useAiJob";
import { api, type PRD, type Project, type SRS } from "@/lib/api";

export default function SrsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [prds, setPrds] = useState<PRD[]>([]);
  const [srsList, setSrsList] = useState<SRS[]>([]);
  const [prdId, setPrdId] = useState("");

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
      const approved = p.filter((x) => x.status === "approved");
      setPrds(approved);
      if (approved[0]) setPrdId(approved[0].id);
    });
    api.listSrs(projectId).then(setSrsList);
  }, [projectId]);

  async function handleGenerate() {
    if (!projectId || !prdId) return;
    const { task_id } = (await api.generateSrs(projectId, prdId)) as {
      task_id: string;
    };
    aiJob.startJob(task_id, "Generating SRS");
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
          {prds.map((p) => (
            <option key={p.id} value={p.id}>
              PRD v{p.version} ({p.status})
            </option>
          ))}
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
        {srsList.map((s) => (
          <Link
            key={s.id}
            href={`/srs/${s.id}`}
            className="block border-b border-gray-800 px-4 py-3 last:border-0 hover:bg-gray-900"
          >
            <p className="font-medium">
              SRS v{s.version} · {s.status}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
