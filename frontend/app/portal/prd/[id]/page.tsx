"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { PrdFormalDocument } from "@/components/features/prd/PrdFormalDocument";
import { FinalizedBadge, WorkflowStatusBadge } from "@/components/ui/FinalizedBadge";
import { Button } from "@/components/ui/button";
import { api, type Client, type PRD, type Project } from "@/lib/api";
import { PRD_PRINT_STYLES, resolvePrdDocumentFields } from "@/lib/prdDocument";

type EnrichedPRD = PRD & {
  workflow_status?: string;
  source_requirement_name?: string | null;
  stats?: Record<string, unknown>;
};

export default function PrdPortalPage() {
  const { id } = useParams<{ id: string }>();
  const [prd, setPrd] = useState<EnrichedPRD | null>(null);
  const [projectName, setProjectName] = useState<string | undefined>(undefined);
  const [clientName, setClientName] = useState<string | undefined>(undefined);
  const [error, setError] = useState("");
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    api
      .getPrd(id)
      .then((p) => {
        const loaded = p as EnrichedPRD;
        setPrd(loaded);
        // Load project + client names (may fail for unauthenticated portal visitors)
        Promise.all([api.listProjects(), api.listClients()])
          .then(([projects, clients]: [Project[], Client[]]) => {
            const project = projects.find((pr) => pr.id === loaded.project_id);
            if (project) {
              setProjectName(project.name);
              const client = clients.find((c) => c.id === project.client_id);
              if (client) setClientName(client.company_name || client.name);
            }
          })
          .catch(() => {/* not available for unauthenticated visitors */});
      })
      .catch((e: Error) =>
        setError(e.message || "Please log in as a client to review this PRD."),
      );
  }, [id]);

  const doc = useMemo(() => {
    if (!prd?.content_json) return null;
    return resolvePrdDocumentFields(prd.content_json, {
      prdStatus: prd.status,
      version: prd.version,
      sourceRequirementName: prd.source_requirement_name,
      stats: prd.stats,
    });
  }, [prd]);

  const showApprove =
    doc &&
    !doc.clientApproved &&
    (prd?.status === "submitted" ||
      prd?.status === "confirmed" ||
      prd?.status === "finalized" ||
      doc.meta.workflow_confirmed === true ||
      doc.meta.workflow_finalized === true);

  async function handleApprove() {
    setApproving(true);
    try {
      const updated = await api.approvePrd(id);
      setPrd(updated as EnrichedPRD);
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

  if (!prd?.content_json || !doc) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <>
      <style>{PRD_PRINT_STYLES}</style>
      <div className="min-h-screen bg-gray-950 p-6 text-white md:p-10">
        <div className="mx-auto max-w-4xl space-y-6">
          <div className="no-print flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold">PRD client review</h1>
              {doc.clientApproved ? (
                <FinalizedBadge label="Approved" />
              ) : (
                <WorkflowStatusBadge status={doc.statusLabel.toLowerCase()} />
              )}
            </div>
            <Button variant="outline" onClick={() => window.print()}>
              Print PRD
            </Button>
          </div>

          {showApprove ? (
            <div className="no-print rounded-xl border border-blue-800 bg-blue-950/30 p-4">
              <p className="text-sm text-blue-100">
                Please review the document below. Approve when you accept this PRD.
              </p>
              <Button className="mt-3" disabled={approving} onClick={() => void handleApprove()}>
                {approving ? "Approving..." : "Approve PRD"}
              </Button>
            </div>
          ) : null}

          <PrdFormalDocument
            variant="portal"
            className="prd-print-sheet"
            projectName={projectName}
            clientName={clientName}
            version={prd.version}
            statusLabel={doc.statusLabel}
            confirmedBy={doc.confirmedBy}
            confirmedDate={doc.confirmedDate}
            content={doc.displayContent}
            sourceRequirementName={doc.sourceRequirementName}
            featureCount={doc.featureCount}
            storyCount={doc.storyCount}
            qualityScore={doc.qualityScore}
            clientApproved={doc.clientApproved}
            clientApprovedDate={doc.clientApprovedDate}
          />
        </div>
      </div>
    </>
  );
}
