/**
 * Plan 12-06 — Admin market detail client island (Surface 3 action host).
 *
 * Mirrors the shipped `/admin/users/[id]` detail-page-hosts-actions convention
 * (`user-detail-tabs.tsx`): the Server Component (`app/admin/markets/[id]/page.tsx`)
 * fetches the market and hands it to THIS `"use client"` island, which hosts:
 *   1. the shared 12-05 `<MarketForm mode="edit" ... />` (criteria auto-locks
 *      when bet_count > 0; ADM-07);
 *   2. the status/source-gated settlement/close action buttons + their dialogs.
 *
 * Action gating (UI-SPEC §Surface 3):
 *   - OPEN/CLOSED + HOUSE       → Resolve        (ResolveMarketDialog)
 *   - OPEN/CLOSED + POLYMARKET  → Force-settle   (ForceSettleDialog)
 *   - RESOLVED                  → Reverse        (ReverseSettlementDialog)
 *   - OPEN                      → Close market   (CloseMarketDialog)
 *
 * On any dialog success the island calls `router.refresh()` so the Server
 * Component re-fetches and the page reflects the new status (the buttons + form
 * lock re-gate off the fresh `status`/`bet_count`).
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { MarketForm, type MarketFormValues } from "@/components/admin/market-form";
import { ResolveMarketDialog } from "@/components/admin/resolve-market-dialog";
import { ReverseSettlementDialog } from "@/components/admin/reverse-settlement-dialog";
import { ForceSettleDialog } from "@/components/admin/force-settle-dialog";
import { CloseMarketDialog } from "@/components/admin/close-market-dialog";
import type { MarketDetail } from "@/lib/admin-markets-types";

export function MarketDetailActions({ market }: { market: MarketDetail }) {
  const router = useRouter();

  const [resolveOpen, setResolveOpen] = React.useState(false);
  const [reverseOpen, setReverseOpen] = React.useState(false);
  const [forceSettleOpen, setForceSettleOpen] = React.useState(false);
  const [closeOpen, setCloseOpen] = React.useState(false);

  // After any settlement/close mutation, re-fetch the Server Component so the
  // status, bet-count lock, and the gated action set all reflect the new state.
  const refresh = React.useCallback(() => router.refresh(), [router]);

  const isHouse = market.source === "HOUSE";
  const isPolymarket = market.source === "POLYMARKET";
  const isOpenOrClosed =
    market.status === "OPEN" || market.status === "CLOSED";

  const canResolve = isOpenOrClosed && isHouse;
  const canForceSettle = isOpenOrClosed && isPolymarket;
  const canReverse = market.status === "RESOLVED";
  const canClose = market.status === "OPEN";

  // Build the edit-form initial values from the detail read. The deadline must
  // be reshaped from the backend ISO-8601 string to the `datetime-local` input
  // format (YYYY-MM-DDTHH:mm); odds come off the YES outcome (current_odds).
  const yesOutcome =
    market.outcomes.find((o) => o.label === "YES") ?? market.outcomes[0];
  const initialValues: MarketFormValues = {
    question: market.question,
    resolution_criteria: market.resolution_criteria,
    deadline: toDatetimeLocal(market.deadline),
    odds_yes: yesOutcome?.current_odds ?? "0.5",
    category: market.category ?? "",
    min_stake: market.min_stake ?? "",
    max_stake: market.max_stake ?? "",
  };

  return (
    <div className="flex flex-col gap-8">
      {/* Status/source-gated action buttons. Hidden entirely when no action
          applies to the current state (e.g. a CANCELLED market). */}
      {(canResolve || canForceSettle || canReverse || canClose) && (
        <div className="flex flex-wrap items-center gap-3">
          {canResolve && (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setResolveOpen(true)}
            >
              Resolve
            </Button>
          )}
          {canForceSettle && (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setForceSettleOpen(true)}
            >
              Force-settle
            </Button>
          )}
          {canReverse && (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setReverseOpen(true)}
            >
              Reverse settlement
            </Button>
          )}
          {canClose && (
            <Button
              type="button"
              variant="destructive"
              onClick={() => setCloseOpen(true)}
            >
              Close market
            </Button>
          )}
        </div>
      )}

      {/* Shared 12-05 create/edit form in edit-mode. Criteria auto-disables when
          bet_count > 0 (ADM-07); the form owns the create/edit odds wire-name
          split internally — we only pass mode/marketId/initialValues/betCount. */}
      <MarketForm
        mode="edit"
        marketId={market.id}
        initialValues={initialValues}
        betCount={market.bet_count}
      />

      {/* Dialogs (each mounted; visibility owned by its `open` state). */}
      <ResolveMarketDialog
        open={resolveOpen}
        onOpenChange={setResolveOpen}
        marketId={market.id}
        outcomes={market.outcomes}
        onResolved={refresh}
      />
      <ForceSettleDialog
        open={forceSettleOpen}
        onOpenChange={setForceSettleOpen}
        marketId={market.id}
        outcomes={market.outcomes}
        onForceSettled={refresh}
      />
      <ReverseSettlementDialog
        open={reverseOpen}
        onOpenChange={setReverseOpen}
        marketId={market.id}
        onReversed={refresh}
      />
      <CloseMarketDialog
        open={closeOpen}
        onOpenChange={setCloseOpen}
        marketId={market.id}
        onClosed={refresh}
      />
    </div>
  );
}

/**
 * Reshape a backend ISO-8601 timestamp into the `datetime-local` input value
 * (`YYYY-MM-DDTHH:mm`) in LOCAL time, so the edit form pre-fills the existing
 * deadline. Falls back to the raw string if it does not parse (the form's zod
 * "future" rule will surface an invalid value to the operator rather than
 * silently clearing it).
 */
function toDatetimeLocal(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}
