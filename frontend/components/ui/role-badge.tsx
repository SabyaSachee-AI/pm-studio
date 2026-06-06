import { studioButtonSurfaceClassName } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatRoleLabel } from "@/lib/roles";

export const studioChipClassName = cn(
  "inline-flex items-center rounded-lg px-2.5 py-1 text-xs",
  studioButtonSurfaceClassName,
);

interface RoleBadgeProps {
  role: string;
  className?: string;
}

export function RoleBadge({ role, className }: RoleBadgeProps) {
  return (
    <span className={cn(studioChipClassName, className)}>
      {formatRoleLabel(role)}
    </span>
  );
}
