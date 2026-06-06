"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, type Requirement } from "@/lib/api";

export default function RequirementDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [req, setReq] = useState<Requirement | null>(null);
  const [cost, setCost] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.getRequirement(id).then(setReq);
    api.getCostEstimate(id).then(setCost).catch(() => null);
  }, [id]);

  if (!req) return <p className="text-gray-400">Loading...</p>;

  const analysis = req.analysis_result as Record<string, unknown> | null;
  const gaps = (analysis?.gaps as Array<Record<string, string>>) ?? [];

  return (
    <div className="space-y-6 print-document">
      <div className="flex items-center justify-between no-print">
        <h1 className="text-2xl font-semibold">Requirement analysis</h1>
        <div className="flex gap-2">
          <a href={api.getClarificationPdfUrl(id)} target="_blank" rel="noreferrer">
            <Button variant="outline">Download clarification PDF</Button>
          </a>
        </div>
      </div>
      <p className="text-sm text-gray-400">{req.original_filename} · {req.status}</p>

      {cost && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h2 className="font-medium">Preliminary cost estimate</h2>
          <p className="mt-2 text-sm text-gray-300">
            ${String(cost.min_budget_usd)} – ${String(cost.max_budget_usd)} {String(cost.currency)}
          </p>
          <p className="text-xs text-gray-500">{String(cost.note)}</p>
        </div>
      )}

      {analysis && (
        <>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <h2 className="font-medium">Summary</h2>
            <p className="mt-2 text-sm text-gray-300">{String(analysis.summary)}</p>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <h2 className="font-medium">Gaps</h2>
            <ul className="mt-3 space-y-2">
              {gaps.map((gap, i) => (
                <li key={i} className="rounded-md border border-gray-800 p-3 text-sm">
                  <span className="mr-2 rounded bg-gray-800 px-2 py-0.5 text-xs uppercase">
                    {gap.category}
                  </span>
                  {gap.description}
                  {gap.question && (
                    <p className="mt-1 text-gray-400">Q: {gap.question}</p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
