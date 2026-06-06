/**
 * EventCard — the catalog card for a multi-outcome event (EVT-04).
 *
 * Visually distinct from the binary `MarketCard`: an "Event · N outcomes" badge
 * plus the top 2–4 outcomes, each with its OWN independent YES probability on
 * its OWN bar — NEVER a single bar summing to 100% across outcomes (the
 * per-outcome framing LOCK). A "+N more" row when there are more than 4. Links
 * to `/events/{slug}`. Server Component (no "use client").
 */
import Link from "next/link";

import {
  Card,
  CardHeader,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SourceBadge } from "@/components/source-badge";
import { formatVolume, formatDeadline } from "@/lib/api";
import type { CatalogItem, CatalogOutcome } from "@/lib/catalog";

const MAX_SHOWN = 4;

/** Round a probability string (0..1) to a whole percent for display. */
function toPct(odds: string): number {
  const n = parseFloat(odds);
  return Number.isNaN(n) ? 0 : Math.round(n * 100);
}

interface EventCardProps {
  event: CatalogItem;
}

export function EventCard({ event }: EventCardProps) {
  // Most-likely outcomes first; show the top few, overflow into "+N more".
  const sorted = [...event.outcomes].sort(
    (a, b) => parseFloat(b.yes_price) - parseFloat(a.yes_price),
  );
  const shown = sorted.slice(0, MAX_SHOWN);
  const more = sorted.length - shown.length;

  const deadline = formatDeadline(event.deadline ?? "");
  const isEnded = deadline === "Ended";

  return (
    <Card className="group relative flex flex-col overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:border-brand-primary/40 hover:shadow-pop focus-within:ring-2 focus-within:ring-brand-primary/60">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 -top-px h-px bg-gradient-brand opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      />
      <CardHeader className="flex-row items-start justify-between gap-2 p-5 pb-3">
        <Badge
          variant="secondary"
          className="relative z-10 shrink-0 border-brand-primary/25 bg-brand-primary/10 text-brand-primary"
        >
          Event · {event.outcomes.length} outcomes
        </Badge>
        <div className="relative z-10 shrink-0">
          <SourceBadge source={event.source} sourceUrl={null} />
        </div>
      </CardHeader>
      <CardContent className="flex-1 p-5 py-0">
        <h3 className="mb-4 text-[0.95rem] font-semibold leading-snug line-clamp-2 text-foreground">
          <Link
            href={`/events/${event.slug}`}
            className="outline-none after:absolute after:inset-0"
            aria-label={event.title}
          >
            {event.title}
          </Link>
        </h3>
        {/* Each outcome's OWN YES probability on its OWN bar — never summed. */}
        <ul className="flex flex-col gap-2.5">
          {shown.map((o: CatalogOutcome, idx) => {
            const pct = toPct(o.yes_price);
            return (
              <li
                key={o.yes_outcome_id ?? `${o.label}-${idx}`}
                className="flex flex-col gap-1"
              >
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="min-w-0 truncate text-muted-foreground">
                    {o.label}
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums text-foreground">
                    {pct}%
                  </span>
                </div>
                <div
                  className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                  role="img"
                  aria-label={`${o.label}: ${pct}% YES`}
                >
                  <div
                    className="h-full rounded-full bg-gradient-brand"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })}
          {more > 0 && (
            <li className="pt-0.5 text-xs font-medium text-subtle-foreground">
              +{more} more
            </li>
          )}
        </ul>
      </CardContent>
      <CardFooter className="mt-4 p-5 pt-3">
        <div className="flex w-full items-center justify-between border-t border-border/60 pt-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">
            {formatVolume(event.volume)}{" "}
            <span className="font-normal text-subtle-foreground">vol</span>
          </span>
          <span className={isEnded ? "text-subtle-foreground" : undefined}>
            {deadline}
          </span>
        </div>
      </CardFooter>
    </Card>
  );
}
