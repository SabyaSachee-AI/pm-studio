"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, type SRS } from "@/lib/api";

export default function SrsDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [srs, setSrs] = useState<SRS | null>(null);

  useEffect(() => {
    api.getSrs(id).then(setSrs);
  }, [id]);

  if (!srs || !srs.content_json) {
    return <p className="text-gray-400">Loading SRS...</p>;
  }

  const frs =
    (srs.content_json.functional_requirements as Array<Record<string, string>>) ??
    [];
  const nfrs =
    (srs.content_json.nonfunctional_requirements as Array<Record<string, string>>) ??
    [];

  return (
    <div className="space-y-6 print-document">
      <div className="flex flex-wrap items-center gap-2 no-print">
        <h1 className="text-2xl font-semibold">SRS v{srs.version}</h1>
        <span className="rounded-full border border-gray-700 px-2 py-0.5 text-xs">
          {srs.status}
        </span>
        <Button variant="outline" onClick={() => api.submitSrs(id).then(setSrs)}>
          Submit for approval
        </Button>
        <Button onClick={() => api.approveSrs(id).then(setSrs)}>
          Approve (architect)
        </Button>
        <a href={api.getSrsPdfUrl(id)} target="_blank" rel="noreferrer">
          <Button variant="outline">Export PDF</Button>
        </a>
        <Button
          variant="outline"
          onClick={() =>
            api.saveToKnowledge({ source_type: "srs", source_id: id }).then(() =>
              alert("Saved to knowledge base"),
            )
          }
        >
          Save to KB
        </Button>
      </div>

      <section>
        <h2 className="text-lg font-medium">
          Functional requirements ({frs.length})
        </h2>
        <ul className="mt-2 space-y-2">
          {frs.map((fr, i) => (
            <li key={i} className="rounded-md border border-gray-800 p-3 text-sm">
              <strong>
                {fr.fr_number} — {fr.title}
              </strong>
              <p className="mt-1 text-gray-400">{fr.description}</p>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-medium">
          Non-functional requirements ({nfrs.length})
        </h2>
        <ul className="mt-2 space-y-2">
          {nfrs.map((nfr, i) => (
            <li key={i} className="rounded-md border border-gray-800 p-3 text-sm">
              <strong>{nfr.category}</strong> — {nfr.threshold}
              <p className="mt-1 text-gray-400">{nfr.description}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
