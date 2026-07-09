"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, type Decision, type Project } from "@/lib/api";

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("");
  const [decision, setDecision] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .listProjects()
      .then((p) => {
        setProjects(p);
        if (p[0]) setProjectId(p[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    api
      .listDecisions(projectId || undefined)
      .then(setDecisions)
      .catch((e: Error) => setError(e.message));
  }, [projectId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || saving) return;
    setSaving(true);
    setError("");
    try {
      await api.createDecision({ project_id: projectId, title, decision, reason });
      setTitle("");
      setDecision("");
      setReason("");
      setDecisions(await api.listDecisions(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save decision");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Decision registry</h1>

      <form onSubmit={handleCreate} className="space-y-3 rounded-xl border border-gray-800 bg-gray-900 p-4">
        <select
          className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input
          className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
          placeholder="Decision title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        <textarea
          className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
          placeholder="What was decided?"
          rows={2}
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          required
        />
        <textarea
          className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
          placeholder="Why?"
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Record decision"}
        </Button>
      </form>

      <div className="space-y-3">
        {decisions.map((d) => (
          <div key={d.id} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <p className="font-medium">{d.title}</p>
            <p className="mt-2 text-sm text-gray-300">{d.decision}</p>
            <p className="mt-1 text-sm text-gray-500">
              <strong>Reason:</strong> {d.reason}
            </p>
            <p className="mt-1 text-xs text-gray-600">
              {new Date(d.decided_at).toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
