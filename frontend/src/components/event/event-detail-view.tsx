/**
 * EventDetailView — the multi-outcome event detail island (EVT-02/03/05).
 *
 * LEFT: every outcome as an INDEPENDENT `OutcomeRow` (its own YES odds — never a
 * single bar summing to 100%). RIGHT (sticky): the selected outcome's panel —
 * the reused `MarketDetailLiveOdds` + `OrderEntryForm` + `PriceHistorySection`,
 * all targeting the selected child binary market. Selecting another outcome
 * client-fetches that child (`fetchMarket(child_slug)` gives the real YES+NO
 * outcomes the bet form needs) and re-renders the panel.
 *
 * WS cap (criterion 3): exactly ONE live socket is mounted — the selected
 * child's `MarketDetailLiveOdds` — so a 60-outcome event never opens a
 * connection storm; switching selection tears the old socket down and opens one
 * for the new child.
 */
"use client";

import { useRef, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MarketDetailLiveOdds } from "@/components/market-detail-live-odds";
import { PriceHistorySection } from "@/components/price-history-section";
import {
  OrderEntryForm,
  type OrderEntryOutcome,
} from "@/components/order-entry-form";
import { OutcomeRow } from "@/components/event/outcome-row";
import {
  fetchMarket,
  fetchPriceHistory,
  type MarketDetail,
  type PricePoint,
} from "@/lib/api";
import type { EventDetail, EventOutcomeRead } from "@/lib/catalog";
import { cn } from "@/lib/utils";

/** Round a probability string (0..1) to a whole percent for display. */
function toPct(odds: string): number {
  const n = parseFloat(odds);
  return Number.isNaN(n) ? 0 : Math.round(n * 100);
}

/** Normalize a child market's outcomes to the YES/NO tokens the order form expects. */
function normalizeOutcomes(market: MarketDetail): OrderEntryOutcome[] {
  return market.outcomes.map((o) => ({
    id: o.id,
    label: o.label.toUpperCase() === "YES" ? "YES" : "NO",
    current_odds: o.current_odds,
  }));
}

interface EventDetailViewProps {
  event: EventDetail;
  defaultChild: MarketDetail;
  defaultHistory: PricePoint[];
  isAuthenticated: boolean;
}

export function EventDetailView({
  event,
  defaultChild,
  defaultHistory,
  isAuthenticated,
}: EventDetailViewProps) {
  const [child, setChild] = useState<MarketDetail>(defaultChild);
  const [history, setHistory] = useState<PricePoint[]>(defaultHistory);
  const [selectedMarketId, setSelectedMarketId] = useState(defaultChild.id);
  const [loading, setLoading] = useState(false);
  // Tracks the most recent selection so a late, out-of-order fetch response from
  // an earlier selection can't clobber the panel (rapid outcome switching).
  const latestSelectionRef = useRef(defaultChild.id);

  async function select(outcome: EventOutcomeRead) {
    if (outcome.market_id === selectedMarketId) return;
    setSelectedMarketId(outcome.market_id);
    latestSelectionRef.current = outcome.market_id;
    setLoading(true);
    const [mRes, hRes] = await Promise.allSettled([
      fetchMarket(outcome.child_slug),
      fetchPriceHistory(outcome.child_slug, "7d"),
    ]);
    // Drop a stale response if the selection moved on while we were fetching.
    if (latestSelectionRef.current !== outcome.market_id) return;
    if (mRes.status === "fulfilled") {
      setChild(mRes.value);
      setHistory(hRes.status === "fulfilled" ? hRes.value.points : []);
    }
    // On failure the previous child stays selected (the user can retry).
    setLoading(false);
  }

  // Most-likely outcomes first — mirrors the catalog `EventCard` ordering so the
  // list reads the same inside the event as it does on the overview grid.
  const sortedOutcomes = [...event.outcomes].sort(
    (a, b) => parseFloat(b.yes_price) - parseFloat(a.yes_price),
  );

  const outcomes = normalizeOutcomes(child);
  const yesOutcome = outcomes.find((o) => o.label === "YES") ?? outcomes[0];
  const noOutcome = outcomes.find((o) => o.label === "NO") ?? outcomes[1];
  const initialOdds: Record<string, string> = Object.fromEntries(
    child.outcomes.map((o) => [o.id, o.current_odds]),
  );
  const selectedLabel =
    event.outcomes.find((o) => o.market_id === selectedMarketId)?.label ??
    child.question;

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
      {/* LEFT: independent per-outcome rows (own YES odds; never sum-to-100). */}
      <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
        <h2 className="text-lg font-semibold">Outcomes</h2>
        <ul className="flex flex-col gap-2">
          {sortedOutcomes.map((o) => (
            <li key={o.market_id}>
              <OutcomeRow
                label={o.label}
                yesPct={toPct(o.yes_price)}
                status={o.child_status}
                selected={o.market_id === selectedMarketId}
                onSelect={() => void select(o)}
              />
            </li>
          ))}
        </ul>
      </div>

      {/* RIGHT: the selected outcome's bet + chart + the SINGLE live socket. */}
      <div className="lg:col-span-1">
        <Card className="lg:sticky lg:top-8">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">
              {selectedLabel}
            </CardTitle>
          </CardHeader>
          <CardContent
            className={cn(loading && "opacity-60")}
            aria-busy={loading}
          >
            {/* Keyed by the selected child: switching outcomes atomically
                remounts the WHOLE panel, so the old child's SINGLE live socket
                tears down and exactly one opens for the new child — the WS cap.
                (An explicit key on the conditionally-rendered live-odds alone
                mis-reconciled against its positionally-keyed siblings and leaked
                a second mount; the single panel key avoids that.) */}
            <div key={child.id} className="flex flex-col gap-6">
              {/* The ONLY live socket on the page — the selected child. */}
              {yesOutcome && noOutcome && (
                <MarketDetailLiveOdds
                  marketId={child.id}
                  yesOutcomeId={yesOutcome.id}
                  noOutcomeId={noOutcome.id}
                  initialOdds={initialOdds}
                />
              )}

              {/* Reused bet path against the constituent binary child (EVT-03).
                  Any non-OPEN child is treated as closed (no bets). */}
              <OrderEntryForm
                marketId={child.id}
                outcomes={outcomes}
                marketStatus={child.status === "OPEN" ? "OPEN" : "CLOSED"}
                isAuthenticated={isAuthenticated}
                minStake={child.min_stake}
                maxStake={child.max_stake}
              />

              {/* Reused per-outcome price history (EVT-05). */}
              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Price history</h3>
                <PriceHistorySection slug={child.slug} initialPoints={history} />
              </section>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
