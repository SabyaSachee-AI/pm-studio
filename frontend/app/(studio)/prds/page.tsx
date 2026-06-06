"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { api, type PRD, type Project, type Requirement } from "@/lib/api";

export default function PrdsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [prds, setPrds] = useState<PRD[]>([]);
  const [reqId, setReqId] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      if (p[0]) setProjectId(p[0].id);
    });
  }, []);

  useEffect(() => {
    if (!projectId) return;
    api.listRequirements(projectId).then((r) => {
      setRequirements(r.filter((x) => x.status === "analyzed"));
      if (r[0]) setReqId(r[0].id);
    });
    api.listPrds(projectId).then(setPrds);
  }, [projectId]);

  async function handleGenerate() {
    if (!projectId || !reqId) return;
    const { task_id } = (await api.generatePrd(projectId, reqId)) as {
      task_id: string;
    };
    setStatus("Generating...");
    api.subscribeTask(task_id, (data) => {
      setStatus(data.status);
      if (data.status === "SUCCESS") api.listPrds(projectId).then(setPrds);
    });
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">PRDs</h1>
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
          value={reqId}
          onChange={(e) => setReqId(e.target.value)}
        >
          {requirements.map((r) => (
            <option key={r.id} value={r.id}>
              {r.original_filename}
            </option>
          ))}
        </select>
        <Button onClick={handleGenerate}>Generate PRD</Button>
        {status && <span className="text-sm text-gray-400">{status}</span>}
      </div>
      <div className="rounded-xl border border-gray-800">
        {prds.map((p) => (
          <Link
            key={p.id}
            href={`/prds/${p.id}`}
            className="block border-b border-gray-800 px-4 py-3 last:border-0 hover:bg-gray-900"
          >
            <p className="font-medium">
              PRD v{p.version} · {p.status}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
