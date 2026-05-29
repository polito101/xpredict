/**
 * Plan 09-04 — Player-facing market detail page `/markets/[slug]` (MKT-03).
 *
 * An async Server Component shell (mirrors `app/page.tsx` + `portfolio/page.tsx`)
 * that SSR-fetches the market + price-history (default 7d) + recent activity IN
 * PARALLEL (SP-5), then composes the Plan 03 reusable pieces (chart, live
 * indicator, socket hook via small client wrappers, shadcn dialog/select) with
 * the order-entry form, the anonymized activity feed, and the loading skeleton.
 *
 * Layout (UI-SPEC §Layout & Interaction Contract):
 *   - page shell `max-w-6xl mx-auto px-4 sm:px-6 py-12`
 *   - `grid grid-cols-1 lg:grid-cols-3 gap-8`
 *   - LEFT (`lg:col-span-2`): question + description + ALWAYS-VISIBLE
 *     "Resolution criteria" (the transparency trust signal — never collapsed) +
 *     price-history chart + recent-activity feed
 *   - RIGHT: sticky (`lg:sticky lg:top-8`) order-entry panel
 *
 * An unknown slug → "Market not found" + a "Back to markets" link. Money/odds
 * are strings on the wire (SP-1).
 */
import { Suspense } from "react";
import Link from "next/link";
import { cookies } from "next/headers";

import {
  fetchActivity,
  fetchMarket,
  fetchPriceHistory,
  MarketNotFound,
  type ActivityItem,
  type MarketDetail,
  type PricePoint,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SourceBadge } from "@/components/source-badge";
import { RecentActivityFeed } from "@/components/recent-activity-feed";
import { MarketDetailSkeleton } from "@/components/market-detail-skeleton";
import { MarketDetailLiveOdds } from "@/components/market-detail-live-odds";
import { PriceHistorySection } from "@/components/price-history-section";
import {
  OrderEntryForm,
  type OrderEntryOutcome,
} from "@/components/order-entry-form";

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";

/** "Market not found" state with a Back-to-markets link (UI-SPEC 404 copy). */
function MarketNotFoundState() {
  return (
    <main className={PAGE_SHELL}>
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        role="status"
      >
        <h1 className="text-3xl font-semibold tracking-tight">Market not found</h1>
        <p className="mt-2 text-sm text-zinc-500">
          This market doesn&apos;t exist or is no longer available.
        </p>
        <Link href="/" className="mt-4 text-sm text-zinc-900 underline dark:text-zinc-100">
          Back to markets
        </Link>
      </div>
    </main>
  );
}

/** Generic fetch-failure state (distinct from the 404 not-found state). */
function MarketErrorState() {
  return (
    <main className={PAGE_SHELL}>
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        role="status"
      >
        <h1 className="text-3xl font-semibold tracking-tight text-rose-700">
          Unable to load this market
        </h1>
        <p className="mt-2 text-sm text-zinc-500">
          Something went wrong. Try refreshing the page.
        </p>
      </div>
    </main>
  );
}

/** Normalize outcome labels to the YES/NO tokens the order form expects. */
function normalizeOutcomes(market: MarketDetail): OrderEntryOutcome[] {
  return market.outcomes.map((o) => ({
    id: o.id,
    label: o.label.toUpperCase() === "YES" ? "YES" : "NO",
    current_odds: o.current_odds,
  }));
}

async function MarketDetailBody({ slug }: { slug: string }) {
  let market: MarketDetail;
  let points: PricePoint[] = [];
  let activity: ActivityItem[] = [];

  try {
    // SP-5: SSR parallel fetch of market + history + activity. The market read
    // is the gate — a 404 throws MarketNotFound; history/activity degrade to
    // empty (their components render their own empty states) rather than
    // failing the whole page.
    const [marketResult, historyResult, activityResult] = await Promise.allSettled([
      fetchMarket(slug),
      fetchPriceHistory(slug, "7d"),
      fetchActivity(slug),
    ]);

    if (marketResult.status === "rejected") {
      throw marketResult.reason;
    }
    market = marketResult.value;
    if (historyResult.status === "fulfilled") points = historyResult.value.points;
    if (activityResult.status === "fulfilled") activity = activityResult.value;
  } catch (err) {
    if (err instanceof MarketNotFound) return <MarketNotFoundState />;
    return <MarketErrorState />;
  }

  const outcomes = normalizeOutcomes(market);
  const yesOutcome = outcomes.find((o) => o.label === "YES") ?? outcomes[0];
  const noOutcome = outcomes.find((o) => o.label === "NO") ?? outcomes[1];
  const initialOdds: Record<string, string> = Object.fromEntries(
    market.outcomes.map((o) => [o.id, o.current_odds]),
  );

  // `isAuthenticated` is derived from the HttpOnly session cookie presence
  // (the order form shows the login affordance when absent). The cookie value
  // never reaches the client — only the boolean does.
  const store = await cookies();
  const isAuthenticated = Boolean(store.get("xpredict_session")?.value);

  return (
    <main className={PAGE_SHELL}>
      {/* Header: question + source chip (Live indicator lives in the odds block). */}
      <header className="mb-8 flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          {market.question}
        </h1>
        <SourceBadge source={market.source} sourceUrl={market.source_url} />
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        {/* LEFT: description + criteria + chart + activity */}
        <div className="flex flex-col gap-8 lg:col-span-2">
          {/* Live odds + Live/Stale indicator (updates in place from the socket) */}
          {yesOutcome && noOutcome && (
            <MarketDetailLiveOdds
              marketId={market.id}
              yesOutcomeId={yesOutcome.id}
              noOutcomeId={noOutcome.id}
              initialOdds={initialOdds}
            />
          )}

          {market.category && (
            <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
              {market.category}
            </p>
          )}

          {/* ALWAYS-VISIBLE resolution criteria — the transparency trust signal. */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg font-semibold">
                Resolution criteria
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                {market.resolution_criteria}
              </p>
            </CardContent>
          </Card>

          {/* Price history */}
          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-semibold">Price history</h2>
            <PriceHistorySection slug={market.slug} initialPoints={points} />
          </section>

          {/* Recent activity (anonymized) */}
          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">Recent activity</h2>
            <RecentActivityFeed items={activity} />
          </section>
        </div>

        {/* RIGHT: sticky order panel */}
        <div className="lg:col-span-1">
          <Card className="lg:sticky lg:top-8">
            <CardHeader>
              <CardTitle className="text-lg font-semibold">Order entry</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderEntryForm
                marketId={market.id}
                outcomes={outcomes}
                marketStatus={market.status}
                isAuthenticated={isAuthenticated}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}

export default async function MarketDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <Suspense fallback={<MarketDetailSkeleton />}>
      <MarketDetailBody slug={slug} />
    </Suspense>
  );
}
