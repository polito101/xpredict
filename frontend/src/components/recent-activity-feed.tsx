/**
 * Plan 09-04 — Recent-activity feed (MKT-03).
 *
 * Renders the last-20 bets for a market as FULLY ANONYMIZED rows
 * (UI-SPEC §Recent-activity feed):
 *
 *   Someone backed {YES|NO} · {amount} PLAY_USD · {relative-time}
 *
 * Defense-in-depth on top of the Plan 02 server-side anonymization (T-09-14):
 * the `ActivityItem` shape carries NO user identity field, and this component
 * never derives or displays a username / initials / id. The YES/NO token uses
 * the emerald/rose semantic color (`text-xs`); rows are separated by `·`.
 *
 * Money is a string on the wire (SP-1) — rendered verbatim, never parsed.
 * Server Component (no "use client").
 */
import type { ActivityItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const CURRENCY = "PLAY_USD";

/** Compact relative time from an ISO timestamp ("just now", "2m ago", …). */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

interface RecentActivityFeedProps {
  items: ActivityItem[];
}

export function RecentActivityFeed({ items }: RecentActivityFeedProps) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-1" role="status">
        <h3 className="text-lg font-semibold">No bets yet</h3>
        <p className="text-sm text-muted-foreground">
          Be the first to make a prediction on this market.
        </p>
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-2" data-testid="recent-activity">
      {items.map((item, i) => {
        const isYes = item.outcome === "YES";
        return (
          <li
            key={`${item.created_at}-${i}`}
            className="flex flex-wrap items-center gap-1.5 rounded-lg border border-transparent px-3 py-2 text-sm text-muted-foreground transition-colors odd:bg-surface/50 hover:border-border"
          >
            <span
              aria-hidden="true"
              className={cn(
                "h-1.5 w-1.5 shrink-0 rounded-full",
                isYes ? "bg-emerald-400" : "bg-red-400",
              )}
            />
            <span>Someone backed</span>
            <span
              className={
                isYes
                  ? "text-xs font-semibold uppercase tracking-wide text-emerald-400"
                  : "text-xs font-semibold uppercase tracking-wide text-red-400"
              }
            >
              {item.outcome}
            </span>
            <span aria-hidden="true" className="text-subtle-foreground">
              ·
            </span>
            <span className="font-medium text-foreground/80">
              {item.amount} {CURRENCY}
            </span>
            <span aria-hidden="true" className="text-subtle-foreground">
              ·
            </span>
            <span className="text-subtle-foreground">
              {relativeTime(item.created_at)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
