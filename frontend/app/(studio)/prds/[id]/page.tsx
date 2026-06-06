"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, type PRD } from "@/lib/api";

export default function PrdDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [prd, setPrd] = useState<PRD | null>(null);
  const [editing, setEditing] = useState(false);
  const [editJson, setEditJson] = useState("");

  useEffect(() => {
    api.getPrd(id).then(setPrd);
  }, [id]);

  if (!prd || !prd.content_json) {
    return <p className="text-gray-400">Loading PRD...</p>;
  }

  const content = prd.content_json;

  async function handleSaveEdit() {
    const parsed = JSON.parse(editJson) as Record<string, unknown>;
    const updated = await api.updatePrd(id, parsed, "Manual edit via UI");
    setPrd(updated);
    setEditing(false);
  }

  return (
    <div className="space-y-6 print-document">
      <div className="flex flex-wrap items-center gap-2 no-print">
        <h1 className="text-2xl font-semibold">PRD v{prd.version}</h1>
        <span className="rounded-full border border-gray-700 px-2 py-0.5 text-xs">
          {prd.status}
        </span>
        <Button variant="outline" onClick={() => api.submitPrd(id).then(setPrd)}>
          Submit for approval
        </Button>
        <Button onClick={() => api.approvePrd(id).then(setPrd)}>Approve</Button>
        <Button
          variant="outline"
          onClick={() => {
            setEditJson(JSON.stringify(content, null, 2));
            setEditing((v) => !v);
          }}
        >
          {editing ? "Cancel edit" : "Edit JSON"}
        </Button>
        <a href={api.getPrdPdfUrl(id)} target="_blank" rel="noreferrer">
          <Button variant="outline">Export PDF</Button>
        </a>
        <Button
          variant="outline"
          onClick={() =>
            api.saveToKnowledge({ source_type: "prd", source_id: id }).then(() =>
              alert("Saved to knowledge base"),
            )
          }
        >
          Save to KB
        </Button>
        <a href={`/portal/prd/${id}`} className="text-sm text-blue-400 underline">
          Client portal link
        </a>
      </div>

      {editing ? (
        <div className="no-print space-y-2">
          <textarea
            className="h-96 w-full rounded-md border border-gray-700 bg-gray-950 p-3 font-mono text-xs"
            value={editJson}
            onChange={(e) => setEditJson(e.target.value)}
          />
          <Button onClick={handleSaveEdit}>Save new version</Button>
        </div>
      ) : (
        <>
          <section>
            <h2 className="text-lg font-medium">Executive summary</h2>
            <p className="mt-2 text-sm text-gray-300">{String(content.executive_summary)}</p>
          </section>

          <section>
            <h2 className="text-lg font-medium">Features</h2>
            <ul className="mt-2 space-y-2">
              {((content.features as Array<Record<string, string>>) ?? []).map((f, i) => (
                <li key={i} className="rounded-md border border-gray-800 p-3 text-sm">
                  <strong>{f.title}</strong> [{f.priority}] — {f.description}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-medium">User stories</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-300">
              {((content.user_stories as Array<Record<string, string>>) ?? []).map((s, i) => (
                <li key={i}>
                  As a {s.as_a}, I want to {s.i_want_to}, so that {s.so_that}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
