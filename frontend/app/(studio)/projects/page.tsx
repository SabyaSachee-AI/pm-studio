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

  useEffect(() => {
    Promise.all([api.listProjects(), api.listClients()]).then(([p, c]) => {
      setProjects(p);
      setClients(c);
      if (c[0]) setClientId(c[0].id);
    });
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    await api.createProject({ name, client_id: clientId });
    setName("");
    setProjects(await api.listProjects());
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Projects</h1>
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
        <Button type="submit">Add project</Button>
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
