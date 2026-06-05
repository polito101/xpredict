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
    <Card className="group relative transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus-within:ring-2 focus-within:ring-brand-primary focus-within:ring-offset-2">
      <CardHeader className="p-6 pb-2">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-base font-semibold leading-snug line-clamp-2">
            <Link
              href={`/events/${event.slug}`}
              className="after:absolute after:inset-0"
              aria-label={event.title}
            >
              {event.title}
            </Link>
          </h3>
          <Badge variant="secondary" className="relative z-10 shrink-0">
            Event · {event.outcomes.length} outcomes
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-6 pt-0">
        {/* Each outcome's OWN YES probability on its OWN bar — never summed. */}
        <ul className="flex flex-col gap-2">
          {shown.map((o: CatalogOutcome) => {
            const pct = toPct(o.yes_price);
            return (
              <li
                key={o.yes_outcome_id ?? o.label}
                className="flex flex-col gap-1"
              >
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="min-w-0 truncate text-zinc-700 dark:text-zinc-300">
                    {o.label}
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums">
                    {pct}%
                  </span>
                </div>
                <div
                  className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700"
                  role="img"
                  aria-label={`${o.label}: ${pct}% YES`}
                >
                  <div
                    className="h-full bg-brand-primary"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })}
          {more > 0 && (
            <li className="text-xs text-zinc-500">+{more} more</li>
          )}
        </ul>
      </CardContent>
      <CardFooter className="p-6 pt-0 flex items-end justify-between gap-2">
        <div className="min-w-0 truncate text-sm text-zinc-500">
          <span>Vol: {formatVolume(event.volume)}</span>
          <span className="mx-2">|</span>
          <span className={isEnded ? "text-zinc-400" : undefined}>
            {deadline}
          </span>
        </div>
        <div className="relative z-10 shrink-0">
          <SourceBadge source={event.source} sourceUrl={null} />
        </div>
      </CardFooter>
    </Card>
  );
}
