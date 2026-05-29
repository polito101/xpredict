/**
 * Plan 08-03 — User status badge.
 *
 * "Active" (emerald) / "Banned" (red) chip per UI-SPEC §Semantic colors.
 * `aria-label="Status: Active|Banned"` per UI-SPEC §Accessibility.
 */
import { cn } from "@/lib/utils";
import type { UserStatus } from "@/lib/admin-types";

export function UserStatusBadge({
  status,
  className,
}: {
  status: UserStatus;
  className?: string;
}) {
  const isActive = status === "active";
  return (
    <span
      aria-label={`Status: ${isActive ? "Active" : "Banned"}`}
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        isActive
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
          : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        className,
      )}
    >
      {isActive ? "Active" : "Banned"}
    </span>
  );
}
