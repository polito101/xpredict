/**
 * Player-facing multi-outcome event detail page `/events/[slug]` (EVT-02/03/05).
 *
 * Clones `app/markets/[slug]/page.tsx`: an async Server Component shell that
 * SSR-fetches the event, picks a default outcome (the first OPEN child by YES
 * desc), and SSR-fetches THAT child's market detail + 7d price history in
 * parallel so the bet panel is immediately actionable (no client-fetch flash).
 * The per-outcome rows + the bet/chart/live-odds for the selected child live in
 * the `EventDetailView` client island.
 *
 * A missing/<2-child slug → "Event not found" (the backend 404s it); other fetch
 * failures → "Unable to load this event". Money/odds are strings on the wire.
 */
import { Suspense } from "react";
import Link from "next/link";
import { cookies } from "next/headers";

import { fetchMarket, fetchPriceHistory } from "@/lib/api";
import { SESSION_COOKIE_NAME } from "@/lib/config";
import {
  fetchEvent,
  EventNotFound,
  type EventDetail,
  type EventOutcomeRead,
} from "@/lib/catalog";
import { SourceBadge } from "@/components/source-badge";
import { EventStatusBadge } from "@/components/event/event-status-badge";
import { EventDetailView } from "@/components/event/event-detail-view";
import { MarketDetailSkeleton } from "@/components/market-detail-skeleton";

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";

/** "Event not found" state with a Back-to-markets link. */
function EventNotFoundState() {
  return (
    <main className={PAGE_SHELL}>
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        role="status"
      >
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Event not found
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This event doesn&apos;t exist or is no longer available.
        </p>
        <Link
          href="/"
          className="mt-4 text-sm text-foreground underline underline-offset-4 hover:text-brand-primary"
        >
          Back to markets
        </Link>
      </div>
    </main>
  );
}

/** Generic fetch-failure state (distinct from the 404 not-found state). */
function EventErrorState() {
  return (
    <main className={PAGE_SHELL}>
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        role="status"
      >
        <h1 className="font-display text-3xl font-semibold tracking-tight text-red-400">
          Unable to load this event
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong. Try refreshing the page.
        </p>
      </div>
    </main>
  );
}

/** Default outcome = the highest-YES OPEN child, else the first outcome. */
function pickDefaultOutcome(event: EventDetail): EventOutcomeRead | undefined {
  const open = event.outcomes
    .filter((o) => o.child_status === "OPEN")
    .sort((a, b) => parseFloat(b.yes_price) - parseFloat(a.yes_price));
  return open[0] ?? event.outcomes[0];
}

async function EventDetailBody({ slug }: { slug: string }) {
  let event: EventDetail;
  try {
    event = await fetchEvent(slug);
  } catch (err) {
    if (err instanceof EventNotFound) return <EventNotFoundState />;
    return <EventErrorState />;
  }

  const def = pickDefaultOutcome(event);
  if (!def) return <EventErrorState />;

  // SSR-fetch the default child's detail (full YES+NO outcomes for the bet form)
  // + its 7d history, so the panel is immediately actionable. History degrades
  // to [] (its chart shows its own empty state); the child read is the gate.
  const [childResult, historyResult] = await Promise.allSettled([
    fetchMarket(def.child_slug),
    fetchPriceHistory(def.child_slug, "7d"),
  ]);
  if (childResult.status === "rejected") return <EventErrorState />;
  const defaultChild = childResult.value;
  const defaultHistory =
    historyResult.status === "fulfilled" ? historyResult.value.points : [];

  const store = await cookies();
  const isAuthenticated = Boolean(store.get(SESSION_COOKIE_NAME)?.value);

  return (
    <main className={PAGE_SHELL}>
      <header className="mb-8 flex flex-col gap-3">
        {event.category && (
          <span className="text-xs font-medium uppercase tracking-wide text-subtle-foreground">
            {event.category}
          </span>
        )}
        <h1 className="font-display text-3xl font-semibold leading-tight tracking-tight">
          {event.title}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <SourceBadge source={event.source} sourceUrl={null} />
          <EventStatusBadge status={event.status} />
        </div>
      </header>

      <EventDetailView
        event={event}
        defaultChild={defaultChild}
        defaultHistory={defaultHistory}
        isAuthenticated={isAuthenticated}
      />
    </main>
  );
}

export default async function EventDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <Suspense fallback={<MarketDetailSkeleton />}>
      <EventDetailBody slug={slug} />
    </Suspense>
  );
}
