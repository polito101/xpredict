/**
 * Plan 09-04 — Live-odds block wrapper (MKT-04 surfaced on the detail page).
 *
 * A small `"use client"` bridge so the SSR Server Component page can mount the
 * client-only `useMarketSocket` hook (SP-5: SSR-fetch initial, client-subscribe
 * deltas — only the live odds delta is client-driven; the chart + activity stay
 * SSR). Composes the Plan 03 pieces:
 *   - `useMarketSocket(marketId, initialOdds)` → live odds map + ConnState
 *   - `OddsDisplay` (canonical YES/NO renderer, reused verbatim)
 *   - `LiveIndicator` (Live / Stale / Reconnecting…)
 *
 * The odds update IN PLACE from the socket with no page refresh; on stale the
 * last-known odds STAY VISIBLE (the hook never blanks them — Pitfall 5).
 * Money/odds are strings on the wire; we only round for display (SP-1).
 */
"use client";

import { useMemo } from "react";

import { OddsDisplay } from "@/components/odds-display";
import { LiveIndicator } from "@/components/live-indicator";
import { useMarketSocket } from "@/hooks/use-market-socket";

interface MarketDetailLiveOddsProps {
  marketId: string;
  yesOutcomeId: string;
  noOutcomeId: string;
  /** Initial odds map keyed by outcome id (SSR seed). */
  initialOdds: Record<string, string>;
}

function toPct(odds: string | undefined): number {
  if (!odds) return 0;
  const n = parseFloat(odds);
  return Number.isNaN(n) ? 0 : Math.round(n * 100);
}

export function MarketDetailLiveOdds({
  marketId,
  yesOutcomeId,
  noOutcomeId,
  initialOdds,
}: MarketDetailLiveOddsProps) {
  const { odds, state } = useMarketSocket(marketId, initialOdds);

  // Derive YES/NO percentages from the live odds map (falls back to the SSR
  // seed before the first socket message). Render the EXPLICIT NO odds whenever
  // the backend supplies the NO key — the complement (100 - yesPct) is only the
  // fallback when the NO key is genuinely ABSENT (WR-06). The previous `> 0`
  // guard conflated "NO odds missing" with "NO odds round to 0%", discarding a
  // legitimately tiny NO probability (e.g. "0.004") and silently substituting
  // the binary complement — wrong for any non-binary / non-complementary market.
  const yesPct = useMemo(() => toPct(odds[yesOutcomeId]), [odds, yesOutcomeId]);
  const noPct = useMemo(
    () =>
      odds[noOutcomeId] !== undefined ? toPct(odds[noOutcomeId]) : 100 - yesPct,
    [odds, noOutcomeId, yesPct],
  );

  return (
    <div className="flex flex-col gap-2 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-zinc-500">
          Live odds
        </span>
        <LiveIndicator state={state} />
      </div>
      <OddsDisplay yes={yesPct} no={noPct} />
    </div>
  );
}
