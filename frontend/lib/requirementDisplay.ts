import type { Requirement } from "@/lib/api";

/** Human-readable requirement label using the viewer's local date/time. */
export function formatRequirementLabel(r: Requirement): string {
  const file = r.original_filename;
  const ar = r.analysis_result;
  const isFinalized = r.status === "finalized" || ar?.finalized === true;

  if (isFinalized) {
    const when =
      (typeof ar?.finalized_at === "string" && ar.finalized_at) ||
      r.updated_at ||
      r.created_at;
    const date = new Date(when).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
    return `${file} — finalized ${date}`;
  }

  const uploaded = new Date(r.created_at).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
  return `${file} — uploaded ${uploaded}`;
}
