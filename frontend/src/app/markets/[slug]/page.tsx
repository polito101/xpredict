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
import { getBackendUrl, SESSION_COOKIE_NAME } from "@/lib/config";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SourceBadge } from "@/components/source-badge";
import { RecentActivityFeed } from "@/components/recent-activity-feed";
import { MarketDetailSkeleton } from "@/components/market-detail-skeleton";
import { MarketDetailLiveOdds } from "@/components/market-detail-live-odds";
import { PriceHistorySection } from "@/components/price-history-section";
import { MarketStatusBadge } from "@/components/admin/market-status-badge";
import {
  MarketResolutionPanel,
  type ResolutionResult,
} from "@/components/market-resolution-panel";
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
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Market not found
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This market doesn&apos;t exist or is no longer available.
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
function MarketErrorState() {
  return (
    <main className={PAGE_SHELL}>
      <div
        className="flex flex-col items-center justify-center py-24 text-center"
        role="status"
      >
        <h1 className="font-display text-3xl font-semibold tracking-tight text-red-400">
          Unable to load this market
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
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

/**
 * Reads the logged-in player's OWN settled result for this market (STL-06).
 *
 * SECURITY (T-12-11 / T-12-13): self-scoped by the player's own HttpOnly
 * `xpredict_session` cookie forwarded server-side to `/bets/me/portfolio` — there
 * is NO `user_id` parameter, so another user's payout is structurally
 * unreachable. The cookie value never reaches the client; only the rendered
 * result does. Mirrors `portfolio/page.tsx:65-83` and degrades to `null` on any
 * failure (a non-bettor or a logged-out visitor simply gets `null`).
 */
async function loadMyResult(
  session: string | undefined,
  marketId: string,
): Promise<ResolutionResult | null> {
  if (!session) return null;
  try {
    const res = await fetch(`${getBackendUrl()}/bets/me/portfolio`, {
      headers: { Cookie: `${SESSION_COOKIE_NAME}=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = await res.json();
    const settled: ResolutionResult[] = data.settled ?? [];
    return settled.find((p) => p.market_id === marketId) ?? null;
  } catch {
    return null;
  }
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
  // never reaches the client — only the boolean (and, server-side, the
  // self-scoped portfolio read below) does.
  const store = await cookies();
  const session = store.get(SESSION_COOKIE_NAME)?.value;
  const isAuthenticated = Boolean(session);

  // STL-06: when the market is RESOLVED, the right column shows the resolution
  // panel instead of the order form. Load the player's OWN result (self-scoped
  // by their cookie) so they see their Won/Lost + P&L; non-bettors / logged-out
  // visitors get `null` (the panel shows only the public facts).
  const isResolved = market.status === "RESOLVED";
  const myResult = isResolved
    ? await loadMyResult(session, market.id)
    : null;
  const winningOutcomeLabel =
    market.outcomes.find((o) => o.id === market.winning_outcome_id)?.label ??
    null;

  return (
    <main className={PAGE_SHELL}>
      {/* Header: category eyebrow + question + source/status chips. */}
      <header className="mb-8 flex flex-col gap-3">
        {market.category && (
          <span className="text-xs font-medium uppercase tracking-wide text-subtle-foreground">
            {market.category}
          </span>
        )}
        <h1 className="font-display text-3xl font-semibold leading-tight tracking-tight">
          {market.question}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <SourceBadge source={market.source} sourceUrl={market.source_url} />
          <MarketStatusBadge status={market.status} />
        </div>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        {/* LEFT: description + criteria + chart + activity.
            order-2 below lg so the order-entry panel (order-1) sits up top on
            tablet/portrait instead of being buried under the chart + activity. */}
        <div className="order-2 flex min-w-0 flex-col gap-8 lg:order-1 lg:col-span-2">
          {/* Live odds + Live/Stale indicator (updates in place from the socket) */}
          {yesOutcome && noOutcome && (
            <MarketDetailLiveOdds
              marketId={market.id}
              yesOutcomeId={yesOutcome.id}
              noOutcomeId={noOutcome.id}
              initialOdds={initialOdds}
            />
          )}

          {/* ALWAYS-VISIBLE resolution criteria — the transparency trust signal. */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg font-semibold">
                Resolution criteria
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-foreground/80">
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

        {/* RIGHT: sticky panel — resolution display when RESOLVED, else order entry.
            order-1 below lg lifts the bet CTA above the fold on tablet/portrait. */}
        <div className="order-1 lg:order-2 lg:col-span-1">
          {isResolved ? (
            <MarketResolutionPanel
              winningOutcomeLabel={winningOutcomeLabel}
              resolutionSource={market.resolution_source}
              justification={market.resolution_justification}
              resolvedAt={market.resolved_at}
              sourceUrl={market.source_url}
              source={market.source}
              myResult={myResult}
              isAuthenticated={isAuthenticated}
            />
          ) : (
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
                  minStake={market.min_stake}
                  maxStake={market.max_stake}
                />
              </CardContent>
            </Card>
          )}
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
