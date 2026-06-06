"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { api, type Project, type Requirement } from "@/lib/api";

export default function RequirementsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [taskStatus, setTaskStatus] = useState("");
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      if (p[0]) setProjectId(p[0].id);
    });
  }, []);

  useEffect(() => {
    if (!projectId) return;
    api.listRequirements(projectId).then(setRequirements);
  }, [projectId]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !projectId) return;
    const { task_id } = await api.uploadRequirement(projectId, file);
    setTaskStatus("Uploading...");
    const es = api.subscribeTask(task_id, (data) => {
      setTaskStatus(data.status);
      if (data.status === "SUCCESS") {
        api.listRequirements(projectId).then(setRequirements);
      }
    });
    return () => es.close();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Requirements</h1>
      <div className="flex gap-2">
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
      </div>
      <form onSubmit={handleUpload} className="flex flex-wrap items-center gap-2">
        <input
          type="file"
          accept=".pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm text-gray-400"
        />
        <Button type="submit" disabled={!file}>
          Upload PDF
        </Button>
        {taskStatus && (
          <span className="text-sm text-gray-400">Status: {taskStatus}</span>
        )}
      </form>
      <div className="rounded-xl border border-gray-800">
        {requirements.map((r) => (
          <Link
            key={r.id}
            href={`/requirements/${r.id}`}
            className="block border-b border-gray-800 px-4 py-3 last:border-0 hover:bg-gray-900"
          >
            <p className="font-medium">{r.original_filename}</p>
            <p className="text-xs text-gray-500">{r.status}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
