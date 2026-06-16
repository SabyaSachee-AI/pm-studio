import { cn } from "@/lib/utils";

/** Green pill badge — finalized / approved documents. */
export const finalizedBadgeClassName =
  "inline-flex items-center rounded-full border border-green-600 bg-green-950 px-3 py-1 font-serif text-xs font-semibold uppercase tracking-wide text-emerald-300";

export function isLockedStatus(status: string): boolean {
  const normalized = status.toLowerCase();
  return normalized === "finalized" || normalized === "approved";
}

export type FinalizedBadgeProps = {
  label?: string;
  className?: string;
};

export function FinalizedBadge({
  label = "Finalized",
  className,
}: FinalizedBadgeProps) {
  return (
    <span className={cn(finalizedBadgeClassName, className)}>{label}</span>
  );
}

/** Green pill for finalized/approved; neutral badge for other statuses. */
export function WorkflowStatusBadge({
  status,
  className,
  neutralClassName = "rounded-full border border-gray-700 bg-gray-800 px-2 py-0.5 text-xs text-gray-400",
}: {
  status: string;
  className?: string;
  neutralClassName?: string;
}) {
  if (isLockedStatus(status)) {
    const label =
      status.toLowerCase() === "approved" ? "Approved" : "Finalized";
    return <FinalizedBadge label={label} className={className} />;
  }
  return (
    <span className={cn(neutralClassName, className)}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
