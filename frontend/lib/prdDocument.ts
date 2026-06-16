export type PrdContentMeta = Record<string, unknown>;

export function getPrdMeta(content: Record<string, unknown>): PrdContentMeta {
  return (content._meta as PrdContentMeta) ?? {};
}

export function stripPrdMeta(content: Record<string, unknown>): Record<string, unknown> {
  const { _meta: _, ...rest } = content;
  return rest;
}

export function formatPrdDocumentDate(isoOrFallback?: string): string {
  if (isoOrFallback) {
    return new Date(isoOrFallback).toLocaleDateString(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
  return new Date().toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function prdDocumentStatusLabel(
  prdStatus: string,
  meta: PrdContentMeta,
): string {
  if (prdStatus === "approved") return "APPROVED";
  if (meta.workflow_finalized === true) return "FINALIZED";
  if (prdStatus === "submitted" || meta.workflow_confirmed === true) {
    return "CONFIRMED — CLIENT REVIEW";
  }
  return prdStatus.replace(/_/g, " ").toUpperCase();
}

export function getFinalizedPrdBody(
  content: Record<string, unknown>,
): Record<string, unknown> | null {
  const meta = getPrdMeta(content);
  const snapshot = meta.finalized_content_json;
  if (
    snapshot &&
    typeof snapshot === "object" &&
    !Array.isArray(snapshot) &&
    Object.keys(snapshot as Record<string, unknown>).length > 0
  ) {
    return snapshot as Record<string, unknown>;
  }
  if (meta.workflow_finalized === true) {
    return stripPrdMeta(content);
  }
  return null;
}

export function isPrdLocked(prdStatus: string, meta: PrdContentMeta): boolean {
  if (prdStatus === "approved") return true;
  return meta.workflow_finalized === true && prdStatus === "submitted";
}

export function resolvePrdDocumentFields(
  content: Record<string, unknown>,
  opts: {
    prdStatus: string;
    version: number;
    fallbackPreparedBy?: string;
    sourceRequirementName?: string | null;
    stats?: Record<string, unknown>;
  },
) {
  const meta = getPrdMeta(content);
  const locked = isPrdLocked(opts.prdStatus, meta);
  const finalizedBody = getFinalizedPrdBody(content);
  const displayVersion = locked
    ? Number(meta.finalized_version ?? opts.version)
    : opts.version;
  const displayContent =
    locked && finalizedBody ? finalizedBody : stripPrdMeta(content);
  const confirmedBy = String(meta.confirmed_by_name ?? opts.fallbackPreparedBy ?? "PM");
  const confirmedDate = formatPrdDocumentDate(
    typeof meta.confirmed_at === "string" ? meta.confirmed_at : undefined,
  );
  const clientApproved = opts.prdStatus === "approved" || meta.client_approval_status === "approved";
  const clientApprovedDate =
    typeof meta.client_approved_at === "string"
      ? formatPrdDocumentDate(meta.client_approved_at)
      : undefined;

  return {
    meta,
    displayContent,
    displayVersion,
    isLocked: locked,
    confirmedBy,
    confirmedDate,
    statusLabel: prdDocumentStatusLabel(opts.prdStatus, meta),
    clientApproved,
    clientApprovedDate,
    featureCount: Number(opts.stats?.feature_count ?? 0),
    storyCount: Number(opts.stats?.user_story_count ?? 0),
    qualityScore:
      typeof meta.quality_score === "number" ? meta.quality_score : null,
    sourceRequirementName: opts.sourceRequirementName ?? undefined,
  };
}

export const PRD_PRINT_STYLES = `
  @page {
    size: A4 portrait;
    margin: 2cm 2cm 2.5cm 2cm;
  }
  @media print {
    html,
    body {
      background: #fff !important;
      color: #000 !important;
    }
    aside,
    header,
    nav,
    .no-print,
    .print-document {
      display: none !important;
    }
    main {
      padding: 0 !important;
      margin: 0 !important;
      overflow: visible !important;
    }
    body * {
      visibility: hidden;
    }
    .prd-print-sheet,
    .prd-print-sheet * {
      visibility: visible;
    }
    .prd-print-sheet {
      position: absolute;
      left: 0;
      top: 0;
      width: 100%;
      margin: 0;
      padding: 0;
      background: #fff !important;
      color: #000 !important;
      font-size: 11pt;
      line-height: 1.5;
    }
    .prd-print-sheet h1 {
      font-size: 16pt;
      line-height: 1.3;
    }
    .prd-print-sheet h2 {
      font-size: 11pt;
      margin-top: 14pt;
      margin-bottom: 6pt;
      page-break-after: avoid;
    }
    .prd-print-sheet .print-section {
      page-break-inside: avoid;
    }
    .print-only {
      display: block !important;
    }
  }
  .print-only {
    display: none;
  }
`;
