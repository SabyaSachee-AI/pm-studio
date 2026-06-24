export type SrsContentMeta = Record<string, unknown>;

export function getSrsMeta(content: Record<string, unknown>): SrsContentMeta {
  return (content._meta as SrsContentMeta) ?? {};
}

export function stripSrsMeta(content: Record<string, unknown>): Record<string, unknown> {
  const { _meta: _, ...rest } = content;
  return rest;
}

export function formatSrsDocumentDate(isoOrFallback?: string): string {
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

export function srsDocumentStatusLabel(
  srsStatus: string,
  meta: SrsContentMeta,
): string {
  if (srsStatus === "approved") return "APPROVED";
  if (meta.workflow_finalized === true) return "FINALIZED";
  if (srsStatus === "submitted" || meta.workflow_confirmed === true) {
    return "CONFIRMED — CLIENT REVIEW";
  }
  return srsStatus.replace(/_/g, " ").toUpperCase();
}

export { FORMAL_PRINT_STYLES } from "@/lib/prdDocument";
