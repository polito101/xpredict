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

/**
 * Status badge palette — dark-tuned "tint" chips (Phase 19). Each is a soft
 * translucent fill + a vivid ink, legible on the obsidian card surface. The
 * asserted three (OPEN / RESOLVED / CANCELLED) are kept in lockstep with
 * market-status-badge.test.tsx.
 */
const STATUS_COLORS: Record<string, string> = {
  // active/healthy
  OPEN: "bg-emerald-500/15 text-emerald-400",
  // awaiting resolution, not terminal
  CLOSED: "bg-amber-500/15 text-amber-400",
  // terminal/done — a neutral, solid "settled" chip
  RESOLVED: "bg-foreground/10 text-foreground",
  // terminal-negative
  CANCELLED: "bg-red-500/15 text-red-400",
  // neutral/inactive
  DRAFT: "bg-muted text-subtle-foreground",
};

// Fallback for an unexpected status token — neutral, never a crash.
const FALLBACK_COLOR = "bg-muted text-muted-foreground";

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
