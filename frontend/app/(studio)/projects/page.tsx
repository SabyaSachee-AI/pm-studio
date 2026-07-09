"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, type Client, type Project } from "@/lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [name, setName] = useState("");
  const [clientId, setClientId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([api.listProjects(), api.listClients()])
      .then(([p, c]) => {
        setProjects(p);
        setClients(c);
        if (c[0]) setClientId(c[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (saving) return; // guard against double-submit creating duplicates
    if (!clientId) {
      setError("Create a client first — a project must belong to a client.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.createProject({ name, client_id: clientId });
      setName("");
      setProjects(await api.listProjects());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create project");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Projects</h1>
      {error && <p className="text-sm text-red-400">{error}</p>}
      <form onSubmit={handleCreate} className="flex flex-wrap gap-2">
        <input
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          placeholder="Project name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <select
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
        >
          {clients.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <Button type="submit" disabled={saving}>
          {saving ? "Adding…" : "Add project"}
        </Button>
      </form>
      <div className="rounded-xl border border-gray-800">
        {projects.map((p) => (
          <div key={p.id} className="flex items-center justify-between border-b border-gray-800 px-4 py-3 last:border-0">
            <div>
              <p className="font-medium">{p.name}</p>
              <p className="text-xs text-gray-500">{p.status}</p>
            </div>
            <Link
              href={`/tasks?project=${p.id}`}
              className="text-xs text-blue-400 underline"
            >
              Open Kanban
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
