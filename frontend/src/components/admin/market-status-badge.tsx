/**
 * Plan 12-02 — Market status badge (shared 5-state chip).
 *
 * Clone of `user-status-badge.tsx` — the binary active/banned color logic is
 * replaced by the 5-state UI-SPEC §Status badge palette, keyed by the market
 * status string. The `px-2.5 py-0.5 text-xs font-semibold` chip inset is the
 * locked inherited convention (UI-SPEC §Spacing inherited locked exceptions)
 * and `aria-label="Status: {status}"` is the a11y chip convention
 * (UI-SPEC §Accessibility).
 *
 * Wave-2 consumers (the player resolution display + the admin markets table)
 * import this with no collision — it is the single source of the status palette.
 */
import { cn } from "@/lib/utils";

/** UI-SPEC §Status badge palette — the locked 5-state color map (incl. dark). */
const STATUS_COLORS: Record<string, string> = {
  // active/healthy — matches the "Active" user chip
  OPEN: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  // awaiting resolution, not terminal
  CLOSED: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  // terminal/done — matches the "House" source chip emphasis
  RESOLVED: "bg-zinc-900 text-zinc-50 dark:bg-zinc-50 dark:text-zinc-900",
  // terminal-negative — matches the "Banned" user chip
  CANCELLED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  // neutral/inactive — matches the secondary Polymarket chip
  DRAFT: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
};

// Fallback for an unexpected status token — neutral, never a crash.
const FALLBACK_COLOR =
  "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300";

export function MarketStatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const colorClasses = STATUS_COLORS[status] ?? FALLBACK_COLOR;
  return (
    <span
      aria-label={`Status: ${status}`}
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        colorClasses,
        className,
      )}
    >
      {status}
    </span>
  );
}
