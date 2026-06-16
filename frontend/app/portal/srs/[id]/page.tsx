"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { FinalizedBadge, WorkflowStatusBadge } from "@/components/ui/FinalizedBadge";
import { Button } from "@/components/ui/button";
import { api, type Client, type Project, type SRS } from "@/lib/api";

type EnrichedSRS = SRS & {
  workflow_status?: string;
  source_prd_display_name?: string | null;
  stats?: Record<string, unknown>;
};

function stripMeta(content: Record<string, unknown>): Record<string, unknown> {
  const { _meta: _, ...rest } = content;
  return rest;
}

function getMeta(content: Record<string, unknown>): Record<string, unknown> {
  return (content._meta as Record<string, unknown>) ?? {};
}

export default function SrsPortalPage() {
  const { id } = useParams<{ id: string }>();
  const [srs, setSrs] = useState<EnrichedSRS | null>(null);
  const [projectName, setProjectName] = useState<string>("");
  const [clientName, setClientName] = useState<string>("");
  const [error, setError] = useState("");
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    api
      .getSrs(id)
      .then((s) => {
        const loaded = s as EnrichedSRS;
        setSrs(loaded);
        Promise.all([api.listProjects(), api.listClients()])
          .then(([projects, clients]: [Project[], Client[]]) => {
            const project = projects.find((p) => p.id === loaded.project_id);
            if (project) {
              setProjectName(project.name);
              const client = clients.find((c) => c.id === project.client_id);
              if (client) setClientName(client.company_name || client.name);
            }
          })
          .catch(() => {/* unauthenticated visitor */});
      })
      .catch((e: Error) =>
        setError(e.message || "Please log in to review this SRS."),
      );
  }, [id]);

  const content = useMemo(
    () => (srs?.content_json ? (srs.content_json as Record<string, unknown>) : null),
    [srs],
  );
  const meta = useMemo(() => (content ? getMeta(content) : {}), [content]);
  const displayContent = useMemo(
    () => (content ? stripMeta(content) : null),
    [content],
  );

  const isFinalized =
    meta.workflow_finalized === true ||
    srs?.status === "approved" ||
    srs?.status === "finalized";

  const confirmedBy = String(meta.confirmed_by_name ?? "PM");
  const confirmedDate = meta.confirmed_at
    ? new Date(String(meta.confirmed_at)).toLocaleDateString(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : new Date().toLocaleDateString();

  const stats = (srs?.stats ?? {}) as Record<string, unknown>;
  const qualityScore =
    typeof meta.quality_score === "number" ? meta.quality_score : null;

  const showApprove =
    !isFinalized &&
    (srs?.status === "submitted" ||
      srs?.status === "confirmed" ||
      meta.workflow_confirmed === true);

  async function handleApprove() {
    setApproving(true);
    try {
      const updated = await api.approveSrs(id);
      setSrs(updated as EnrichedSRS);
    } finally {
      setApproving(false);
    }
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 p-6 text-center text-gray-300">
        <div>
          <p>{error}</p>
          <a href="/login" className="mt-4 inline-block text-blue-400 underline">
            Go to login
          </a>
        </div>
      </div>
    );
  }

  if (!srs?.content_json || !displayContent) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <>
      <style>{`
        @page { size: A4 portrait; margin: 2cm 2cm 2.5cm 2cm; }
        @media print {
          html, body { background: #fff !important; color: #000 !important; }
          .no-print { display: none !important; }
          .srs-print-sheet, .srs-print-sheet * { visibility: visible; }
          body * { visibility: hidden; }
          .srs-print-sheet { position: absolute; left: 0; top: 0; width: 100%; }
        }
      `}</style>

      <div className="min-h-screen bg-gray-950 p-6 text-white md:p-10">
        <div className="mx-auto max-w-4xl space-y-6">

          {/* Header bar */}
          <div className="no-print flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold">SRS client review</h1>
              {isFinalized ? (
                <FinalizedBadge label="Finalized" />
              ) : (
                <WorkflowStatusBadge status={srs.status} />
              )}
            </div>
            <Button variant="outline" onClick={() => window.print()}>
              Print SRS
            </Button>
          </div>

          {/* Approve panel */}
          {showApprove ? (
            <div className="no-print rounded-xl border border-blue-800 bg-blue-950/30 p-4">
              <p className="text-sm text-blue-100">
                Please review the document below. Approve when you accept this SRS.
              </p>
              <Button
                className="mt-3"
                disabled={approving}
                onClick={() => void handleApprove()}
              >
                {approving ? "Approving..." : "Approve SRS"}
              </Button>
            </div>
          ) : null}

          {isFinalized ? (
            <div className="no-print rounded-xl border border-green-800 bg-green-950/30 p-4">
              <FinalizedBadge label="SRS approved" />
              <p className="mt-2 text-sm text-gray-300">
                This SRS has been approved and is locked for development.
              </p>
            </div>
          ) : null}

          {/* Formal document — print + screen */}
          <div className="srs-print-sheet rounded-xl border border-gray-200 bg-white p-10 text-black font-serif text-sm shadow-lg">
            <div className="mb-8 text-center">
              <h1 className="text-2xl font-bold tracking-wide uppercase">
                Software Requirements Specification
              </h1>
              <p className="mt-1 text-xs uppercase tracking-widest text-gray-500">
                IEEE 830 Compliant
              </p>
            </div>

            <table className="w-full mb-8 border-collapse">
              <tbody>
                {[
                  ["Project", projectName || "—"],
                  ["Client", clientName || "—"],
                  ["Version", `v${srs.version}`],
                  ["Date", confirmedDate],
                  ["Prepared by", confirmedBy],
                  ["Source PRD", srs.source_prd_display_name ?? "—"],
                  ["Status", isFinalized ? "FINALIZED" : srs.status.toUpperCase()],
                  ["Scope", `${String(stats.fr_count ?? 0)} FRs · ${String(stats.nfr_count ?? 0)} NFRs${qualityScore != null ? ` · Quality ${qualityScore}/100` : ""}`],
                ].map(([label, value]) => (
                  <tr key={label} className="border-b border-gray-200">
                    <td className="py-2 pr-4 font-semibold w-36 text-gray-700">{label}</td>
                    <td className="py-2 text-gray-900">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <hr className="my-6 border-gray-300" />

            {/* SRS Sections */}
            <div className="space-y-6 text-sm text-gray-800">
              {(() => {
                const intro = (displayContent.introduction as Record<string, unknown>) ?? {};
                const overall = (displayContent.overall_description as Record<string, unknown>) ?? {};
                const frs = (displayContent.functional_requirements as Array<Record<string, unknown>>) ?? [];
                const nfrs = (displayContent.non_functional_requirements as Array<Record<string, unknown>>) ?? [];
                return (
                  <>
                    <section>
                      <h2 className="text-base font-bold">1. Introduction</h2>
                      <p className="mt-2"><strong>Purpose:</strong> {String(intro.purpose ?? "")}</p>
                      <p className="mt-1"><strong>Scope:</strong> {String(intro.scope ?? "")}</p>
                    </section>
                    <section>
                      <h2 className="text-base font-bold">2. Overall Description</h2>
                      <p className="mt-2">{String(overall.product_perspective ?? "")}</p>
                    </section>
                    <section>
                      <h2 className="text-base font-bold">3. Functional Requirements</h2>
                      <div className="mt-3 space-y-3">
                        {frs.map((fr, i) => (
                          <div key={i} className="rounded border border-gray-200 p-3">
                            <p className="font-semibold">{String(fr.id ?? `FR-${i + 1}`)}: {String(fr.title ?? "")}</p>
                            <p className="mt-1 text-gray-700">{String(fr.description ?? "")}</p>
                          </div>
                        ))}
                      </div>
                    </section>
                    <section>
                      <h2 className="text-base font-bold">4. Non-Functional Requirements</h2>
                      <div className="mt-3 space-y-2">
                        {nfrs.map((nfr, i) => (
                          <p key={i}><strong>{String(nfr.id ?? "")}</strong> [{String(nfr.category ?? "")}]: {String(nfr.description ?? "")}</p>
                        ))}
                      </div>
                    </section>
                    {(displayContent.security_requirements as string[] ?? []).length > 0 && (
                      <section>
                        <h2 className="text-base font-bold">5. Security Requirements</h2>
                        <ul className="mt-2 list-disc pl-5">
                          {(displayContent.security_requirements as string[]).map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      </section>
                    )}
                    {(displayContent.constraints as string[] ?? []).length > 0 && (
                      <section>
                        <h2 className="text-base font-bold">6. Constraints</h2>
                        <ul className="mt-2 list-disc pl-5">
                          {(displayContent.constraints as string[]).map((c, i) => <li key={i}>{c}</li>)}
                        </ul>
                      </section>
                    )}
                  </>
                );
              })()}
            </div>

            <hr className="my-8 border-gray-300" />
            <div className="grid grid-cols-2 gap-8 text-xs text-gray-600">
              <div>
                <p className="font-semibold">Confirmed by</p>
                <p className="mt-1">{confirmedBy}</p>
                <p className="mt-6 border-t border-gray-400 pt-1">Signature</p>
              </div>
              <div>
                <p className="font-semibold">Date</p>
                <p className="mt-1">{confirmedDate}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
