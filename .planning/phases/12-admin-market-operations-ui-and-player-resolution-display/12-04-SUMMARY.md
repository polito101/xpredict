---
phase: 12-admin-market-operations-ui-and-player-resolution-display
plan: 04
subsystem: ui
tags: [next, react, server-component, vitest, jsdom, tailwind, settled-position, play-money]

# Dependency graph
requires:
  - phase: 12-01
    provides: "MarketRead returns 200 for RESOLVED with winning_outcome_id / resolution_source / resolution_justification / resolved_at + min_stake/max_stake (money as string-or-null)"
  - phase: 12-02
    provides: "MarketStatusBadge shared 5-state chip + admin-markets-types shapes (reused for the RESOLVED header chip)"
  - phase: 12-03
    provides: "OrderEntryForm minStake/maxStake props (the BET-06 per-market client mirror the page now feeds)"
  - phase: 09-04
    provides: "the player detail Server Component layout (two-column grid, lg:sticky right slot, Promise.allSettled market gate, cookie read)"
  - phase: 05
    provides: "/bets/me/portfolio SettledPosition shape (the player's own self-scoped result)"
provides:
  - "MarketResolutionPanel — the STL-06 player resolution display (winner + token-derived source attribution + settled date + escaped justification + the player's own Won/Lost + payout + realized P&L)"
  - "markets/[slug]/page.tsx renders the panel in the right column on RESOLVED markets (order form replaced), with a RESOLVED header chip + the self-scoped own-result fetch"
  - "MarketDetail carries the 4 resolution fields + the 2 stake-limit fields (the typed read surface for the panel and the order-form bounds)"
affects: [12-05, 12-06, "player-detail UX", "any future resolution-display work"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Player resolution display composes shipped pieces (portfolio PnL sign-coloring + settled-card copy + the order-panel Card slot) — no new layout primitive; the panel occupies the existing lg:col-span-1 sticky slot"
    - "Self-scoped own-result read: SSR fetch forwards the player's own xpredict_session cookie to /bets/me/portfolio (no user_id param), filtered by market_id — another user's payout is structurally unreachable"
    - "Operator-authored justification rendered as escaped {justification} React text — never dangerouslySetInnerHTML (XSS-safe by construction)"
    - "A-LOSS-NEUTRAL: a lost bet renders neutral zinc-700, never red (red reserved for errors/destructive)"

key-files:
  created:
    - frontend/src/components/market-resolution-panel.tsx
    - frontend/src/components/__tests__/market-resolution-panel.test.tsx
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/app/markets/[slug]/page.tsx

key-decisions:
  - "HOUSE source renders a bare 'Resolved by Operator' (no name) — 12-01 stores the resolution_source TOKEN only; the panel is written defensively to render 'Operator: {name}' the moment a backend resolver display-name snapshot lands on MarketRead. Flagged for Pol."
  - "The own-result fetch uses a local getBackendUrl() (BACKEND_URL || localhost:8000) mirroring portfolio/page.tsx — SSR-internal base, never NEXT_PUBLIC_, so it stays out of the client bundle."
  - "ResolutionResult is exported from the panel (a transcription of the portfolio SettledPosition shape) so the page imports a single typed contract for both the fetch and the render."

patterns-established:
  - "RESOLVED-branch on the player detail page: market.status === RESOLVED swaps the right-column order panel for MarketResolutionPanel; the LEFT column (odds/criteria/chart/activity) is untouched — same skeleton, swapped panel."
  - "Token-derived source attribution: POLYMARKET_UMA -> 'Polymarket UMA' (+ SourceBadge source link); HOUSE/other -> 'Operator' (+ optional name)."

requirements-completed: [STL-06]

# Metrics
duration: ~18min
completed: 2026-06-03
---

# Phase 12 Plan 04: Player Resolution Display (STL-06) Summary

**RESOLVED markets now render a MarketResolutionPanel in the player detail page's right column (winning outcome + token-derived source attribution + settled date + XSS-safe escaped justification + the logged-in bettor's own self-scoped Won/Lost + payout + realized P&L), replacing the order-entry form — the player-visible end of Flows 1 & 2.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-03 (phase execution session)
- **Completed:** 2026-06-03
- **Tasks:** 3 (Task 2 is TDD: RED + GREEN)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- **STL-06 player surface shipped** — the headline v1.0-audit blocker is closed end-to-end on the frontend: with 12-01 persisting the winner and un-404ing RESOLVED markets, a resolved market's detail page now SHOWS the resolution (winner, source, justification, settled date) instead of a dead order form.
- **Self-scoped own-result** — a logged-in bettor sees their own Won/Lost + payout + realized P&L, read from `/bets/me/portfolio` forwarding only their own `xpredict_session` cookie (no `user_id` param, filtered by `market_id`); a logged-in non-bettor sees "You didn't bet on this market."; a logged-out visitor sees only the public facts. Another user's payout is structurally unreachable (T-12-11/T-12-13).
- **XSS-safe justification** — the operator-authored public justification renders as escaped `{justification}` React text; a `<b>` in the text renders the literal characters (asserted in the panel test — T-12-12). No `dangerouslySetInnerHTML` anywhere.
- **A-LOSS-NEUTRAL honored** — a lost bet renders in neutral `text-zinc-700`, never red (grep-confirmed no `text-red` on the loss path).
- **12-03 hand-off completed** — the order form (non-resolved branch) now receives `minStake`/`maxStake` from the market read, so the BET-06 per-market bounds reach the client mirror.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend MarketDetail with the resolution + stake-limit fields** — `f1cfb1b` (feat)
2. **Task 2: MarketResolutionPanel component + test (TDD)** — `959c7bb` (test / RED) → `05a05ab` (feat / GREEN)
3. **Task 3: RESOLVED branch + own-result fetch in markets/[slug]/page.tsx** — `753f44e` (feat)

**Plan metadata:** (final docs commit — see below)

_Task 2 is `tdd="true"`: the RED commit (`959c7bb`) adds the failing test pinning all four player states + the HTML-escape assertion; the GREEN commit (`05a05ab`) implements the panel and turns 10/10 green. No REFACTOR commit was needed (the composed implementation was clean on first GREEN)._

## Files Created/Modified
- `frontend/src/components/market-resolution-panel.tsx` — **created.** The STL-06 panel. Composes the order-panel Card shell + an inline portfolio-style `PnL` span (loss neutral zinc-700, gain emerald with "+" prefix; sign read from the string, SP-1) + the won/lost settled-card copy; reuses `SourceBadge` (Polymarket link) + `Separator`; `formatDate` for the settled timestamp. Token-derived source line; escaped justification; logged-in-only personal-result section. Exports `ResolutionResult` (the portfolio `SettledPosition` shape).
- `frontend/src/components/__tests__/market-resolution-panel.test.tsx` — **created.** 10 jsdom tests: public facts (Resolution title, winning label, HOUSE→Operator, POLYMARKET_UMA→Polymarket UMA + source link, formatted settled date, "Why this resolved"), the HTML-escape assertion (`<b>` renders literal + no injected `<b>` element), WON (emerald `+` P&L), LOST (neutral zinc-700, asserts NOT red), no-bet copy, logged-out omission.
- `frontend/src/lib/api.ts` — **modified.** `MarketDetail` gains `winning_outcome_id` / `resolution_source` / `resolution_justification` / `resolved_at` + `min_stake` / `max_stake`, all `string | null`. `fetchMarket` 404 logic unchanged (a RESOLVED slug now returns 200 carrying this shape).
- `frontend/src/app/markets/[slug]/page.tsx` — **modified.** Added `loadMyResult` (cookie-forwarded, self-scoped `/bets/me/portfolio` read, filtered by `market_id`, degrades to null). The RIGHT column renders `MarketResolutionPanel` when `market.status === "RESOLVED"`, else the order panel; `winningOutcomeLabel` derived from `market.outcomes` by `winning_outcome_id`; `MarketStatusBadge` added to the header; `OrderEntryForm` now passed `minStake`/`maxStake`. LEFT column untouched.

## Decisions Made
- **HOUSE renders a bare "Operator" (no name) — defensive copy for a future backend name snapshot.** 12-01 deliberately stores the `resolution_source` TOKEN only (no admin display-name join on the public read). The panel formats `POLYMARKET_UMA` → "Resolved by Polymarket UMA" (+ the `SourceBadge` source link) and `HOUSE`/any other token → "Resolved by Operator". An optional `operatorName` prop is already wired so the panel renders "Resolved by Operator: {name}" the instant a backend resolver display-name field appears on `MarketRead` — **no panel change needed, only the backend snapshot**. Flagged for Pol below.
- **Local `getBackendUrl()` for the own-result fetch** (mirrors `portfolio/page.tsx:56-58`) rather than reusing the non-exported `apiBase()` in `lib/api.ts` — keeps the SSR-internal base (`BACKEND_URL`) consistent with the established portfolio read and out of the client bundle.
- **`ResolutionResult` exported from the panel** (a transcription of the portfolio `SettledPosition` shape) so the page has one typed contract for both `loadMyResult` and the render.

## Deviations from Plan

None — plan executed exactly as written. All three tasks (and the TDD RED/GREEN cycle for Task 2) ran per the plan; every acceptance criterion and the threat-model mitigations (T-12-11 self-scoped read, T-12-12 escaped justification, T-12-13 server-side cookie) were satisfied directly by the planned implementation. No bugs, missing functionality, or blocking issues required auto-fixing.

## Issues Encountered
None. The clone sources (portfolio `PnL`/`SettledPosition`, `SourceBadge`, `Separator`, `formatDate`, `MarketStatusBadge`, the order-panel Card slot) all matched the plan's `read_first` citations; the order-entry-form already carried the `minStake`/`maxStake` props from 12-03. Tooling note: used the standalone `pnpm` 9.15.0 on PATH (NOT `corepack pnpm`, which resolves to the destructive 11.x on this host); `pnpm-lock.yaml` and `pnpm-workspace.yaml` stayed pristine — verified after every commit.

## Known Stubs
None. The panel is fully wired to real `MarketRead` data: `winningOutcomeLabel`, `resolution_source`, `resolution_justification`, `resolved_at` come from the public read, and the personal result comes from the live `/bets/me/portfolio`. The `winningOutcomeLabel ?? "—"` and `formatDate(null) → "—"` are graceful-degradation fallbacks for an incompletely-resolved market (e.g. a pre-Phase-12 RESOLVED market with no persisted winner — the 12-01 "no backfill" decision), NOT a placeholder for unwired data.

## Flag for Pol (per <output>)
The HOUSE resolution-source line shows **"Resolved by Operator"** without the resolving admin's name, because 12-01's public `MarketRead` stores the `resolution_source` token only (no admin display-name snapshot — there is no admin join on the public read). The **only** change needed to show **"Resolved by Operator: {name}"** is to persist a resolver display-name snapshot on the market at resolve time and expose it on `MarketRead`; the panel already accepts an `operatorName` prop and will render the named form with zero frontend change. Non-blocking — the bare "Operator" is correct and complete for v1.0.

## Next Phase Readiness
- **STL-06 closed on the frontend** — the player resolution display is reachable and renders all four states. The end-to-end exercise (a RESOLVED house market detail page showing winner + "Resolved by Operator" + justification + settled date + a bettor's Won/Lost + P&L) is covered by SC#5 in 12-06's integration acceptance.
- **12-05 / 12-06 unblocked** — the admin resolve/reverse/force-settle UI (12-05) and the integration acceptance (12-06) can rely on the player surface now rendering persisted resolutions.
- **One open flag for Pol** — the "Operator" (no name) fallback (above); a one-field backend snapshot upgrades it to "Operator: {name}" with no frontend change.

## Self-Check: PASSED

- All created/modified files verified present on disk (see Self-Check appendix below).
- All 4 task commits verified in `git log`: `f1cfb1b` (Task 1), `959c7bb` (Task 2 RED), `05a05ab` (Task 2 GREEN), `753f44e` (Task 3).
- Verification gates green: `pnpm test -- src/components/__tests__/market-resolution-panel.test.tsx` → 10/10; `pnpm typecheck` → exit 0; no `text-red` on the loss path; no `dangerouslySetInnerHTML`; no lock/workspace churn; no file deletions across all 4 commits.

---
*Phase: 12-admin-market-operations-ui-and-player-resolution-display*
*Completed: 2026-06-03*
