"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { api, type PRD, type Project, type SRS } from "@/lib/api";

export default function SrsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [prds, setPrds] = useState<PRD[]>([]);
  const [srsList, setSrsList] = useState<SRS[]>([]);
  const [prdId, setPrdId] = useState("");
  const [status, setStatus] = useState("");

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
    setStatus("Generating...");
    api.subscribeTask(task_id, (data) => {
      setStatus(data.status);
      if (data.status === "SUCCESS") api.listSrs(projectId).then(setSrsList);
    });
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">SRS documents</h1>
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
        <Button onClick={handleGenerate}>Generate SRS</Button>
        {status && <span className="text-sm text-gray-400">{status}</span>}
      </div>
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
