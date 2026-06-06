"use client";

import { useEffect, useState } from "react";
import { api, type KnowledgeItem, type Project } from "@/lib/api";

export default function KnowledgePage() {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");

  useEffect(() => {
    api.listProjects().then(setProjects);
    api.listKnowledgeItems().then(setItems);
  }, []);

  useEffect(() => {
    api.listKnowledgeItems(projectId || undefined).then(setItems);
  }, [projectId]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Knowledge base</h1>
      <select
        className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
        value={projectId}
        onChange={(e) => setProjectId(e.target.value)}
      >
        <option value="">All projects</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <div className="space-y-3">
        {items.length === 0 && (
          <p className="text-sm text-gray-500">
            No items saved yet. Save PRDs, SRS, or specs from their detail pages.
          </p>
        )}
        {items.map((item) => (
          <div
            key={item.id}
            className="rounded-xl border border-gray-800 bg-gray-900 p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium">{item.title}</p>
                <p className="text-xs text-gray-500">
                  {item.item_type} · {item.source_type} ·{" "}
                  {new Date(item.created_at).toLocaleDateString()}
                </p>
              </div>
              <span className="rounded-full border border-gray-700 px-2 py-0.5 text-xs">
                {item.item_type}
              </span>
            </div>
            {item.tags && item.tags.length > 0 && (
              <p className="mt-2 text-xs text-gray-400">Tags: {item.tags.join(", ")}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
