# Plan 17-03 Summary — Event Detail

**Status:** ✅ Complete
**Completed:** 2026-06-06

## What shipped
- `app/events/[slug]/page.tsx` — Server Component clone of the market detail: `fetchEvent(slug)` (404→"Event not found"), default-outcome pick (highest-YES OPEN child), SSR `Promise.allSettled([fetchMarket(child_slug), fetchPriceHistory])` so the bet panel is immediately actionable; header (title + `SourceBadge` + `EventStatusBadge`) + `EventDetailView`.
- `app/events/[slug]/error.tsx` — route error boundary ("Unable to load this event").
- `components/event/event-detail-view.tsx` — client island: LEFT = independent `OutcomeRow`s (own YES odds, never sum-to-100); RIGHT (sticky) = the selected child's reused `MarketDetailLiveOdds` + `OrderEntryForm` + `PriceHistorySection`. Selecting → client `fetchMarket(child_slug)` re-targets the panel.
- `components/event/outcome-row.tsx` — one independent outcome (own YES% + own bar + status chip + brand-ring selection), keyboard-accessible button.
- `components/event/event-status-badge.tsx` — derived 4-status chip.
- Test: `event-detail-view.test.tsx` (3) — independent rows (60+40+20=120%), exactly one socket, order form targets the selected child, select→fetch→re-target.

## Verification
- `tsc --noEmit` clean; `eslint` clean; `vitest run src/components/event` 3/3 green.

## Bug caught & fixed (WS cap)
- An explicit changing `key` on the **conditionally-rendered** `MarketDetailLiveOdds` mis-reconciled against its positionally-keyed siblings and **leaked a second socket** on outcome switch (proven by `getByTestId` finding 2). Fixed by wrapping the whole selected-child panel in a single `key={child.id}` div so it remounts atomically — exactly one live socket at any time (criterion 3). Real catch, not a test artifact.

## Notes
- Non-OPEN children are passed to `OrderEntryForm` as `marketStatus="CLOSED"` (reuses the existing closed affordance; no bets on a resolved/closed outcome).
- The reused `OrderEntryForm` needs the child's real YES+NO outcome ids → fetched via `fetchMarket(child_slug)` (the event payload only carries the YES leg).
</content>
