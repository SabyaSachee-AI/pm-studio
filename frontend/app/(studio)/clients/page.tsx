"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, type Client } from "@/lib/api";

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setClients(await api.listClients());
  }

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    await api.createClient({ name });
    setName("");
    await load();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Clients</h1>
      {error && <p className="text-sm text-red-400">{error}</p>}
      <form onSubmit={handleCreate} className="flex gap-2">
        <input
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          placeholder="Client name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Button type="submit">Add client</Button>
      </form>
      <div className="rounded-xl border border-gray-800">
        {clients.map((c) => (
          <div
            key={c.id}
            className="flex items-center justify-between border-b border-gray-800 px-4 py-3 last:border-0"
          >
            <div>
              <p className="font-medium">{c.name}</p>
              {c.email && <p className="text-xs text-gray-500">{c.email}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
