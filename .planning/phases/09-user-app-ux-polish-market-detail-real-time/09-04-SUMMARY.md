---
phase: 09-user-app-ux-polish-market-detail-real-time
plan: 04
subsystem: ui
tags: [nextjs, react, react-hook-form, zod, server-actions, recharts, websocket, shadcn, tailwind]

# Dependency graph
requires:
  - phase: 09-user-app-ux-polish-market-detail-real-time (Plan 02)
    provides: GET /{slug}/price-history + GET /{slug}/activity public read endpoints (anonymized, server-downsampled)
  - phase: 09-user-app-ux-polish-market-detail-real-time (Plan 03)
    provides: PriceHistoryChart, useMarketSocket hook, LiveIndicator, lib/api.ts fetchers + types (MarketDetail/PricePoint/ActivityItem/MarketNotFound), hand-copied shadcn dialog+select, NEXT_PUBLIC_WS_URL
  - phase: 05-bets-settlement
    provides: POST /bets (cookie-gated place_bet) + 402/409/403/422/401 status contract
  - phase: 02-auth-identity
    provides: xpredict_session cookie + Server-Action cookie-forward pattern (auth.ts, auth-schemas.ts ActionState)
provides:
  - "/markets/[slug] player market-detail page (SSR shell, parallel fetch, two-column responsive grid, sticky order panel, always-visible resolution criteria)"
  - "OrderEntryForm — rhf+zod order entry → BetConfirmDialog → placeBetAction with backend-status→specific-inline-copy mapping (no toast)"
  - "placeBetAction Server Action — cookie-forward POST /bets, status→error mapping (bypasses no server gate)"
  - "RecentActivityFeed — anonymized last-20 feed + empty state"
  - "MarketDetailSkeleton + portfolio loading.tsx Suspense skeletons (no layout shift)"
  - "MarketDetailLiveOdds + PriceHistorySection client wrappers composing the Plan 03 socket + chart into the SSR page"
affects: [phase-10-admin-dashboard-branding, phase-11-hardening-demo-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SSR-fetch initial + client-subscribe deltas (SP-5): a Server Component page fetches market/history/activity in parallel; only the live odds delta is client-driven via a thin client wrapper around useMarketSocket"
    - "Submit→confirm-dialog→Server-Action: the order form opens a controlled shadcn Dialog on submit (after client zod); only the dialog's Confirm fires placeBetAction (the irreversible-action guard)"
    - "Backend-status→specific-inline-copy map (no toast): each bet error status (402/409/403/422/401) renders its exact UI-SPEC string in a role=alert region"
    - "Client wrapper bridge: small \"use client\" components (MarketDetailLiveOdds, PriceHistorySection) let an async Server Component mount client-only hooks without becoming a client page"

key-files:
  created:
    - frontend/src/lib/bet-schemas.ts
    - frontend/src/lib/bet-actions.ts
    - frontend/src/components/order-entry-form.tsx
    - frontend/src/components/order-entry-form.test.tsx
    - frontend/src/components/bet-confirm-dialog.tsx
    - frontend/src/components/recent-activity-feed.tsx
    - frontend/src/components/market-detail-skeleton.tsx
    - frontend/src/components/market-detail-live-odds.tsx
    - frontend/src/components/price-history-section.tsx
    - frontend/src/app/markets/[slug]/page.tsx
    - frontend/src/app/portfolio/loading.tsx
  modified: []

key-decisions:
  - "Outcome Select defaults to YES so the form is submittable without forcing a Radix Select interaction (keeps the order-form test off Radix's jsdom portal/pointer path); the player can still switch to NO."
  - "403 disambiguation: placeBetAction reads the FastAPI detail and uses the banned copy when the detail contains 'ban', else the unverified copy (the plan's default) — the backend banned gate sends 'Account is banned from placing bets.'"
  - "SSR fetch uses Promise.allSettled: the market read is the gate (404→MarketNotFound state), while price-history/activity degrade to empty (their own empty states) rather than failing the whole page."
  - "Two thin client wrappers (MarketDetailLiveOdds, PriceHistorySection) were added (not in the frontmatter file list) to bridge the SSR page to the Plan 03 client hooks — a Server Component cannot call useMarketSocket/useState directly."

patterns-established:
  - "SP-5 SSR-initial / client-subscribe: SSR seeds odds + chart points; the socket updates odds in place and the window toggle re-fetches client-side; chart/activity stay SSR."
  - "Order-entry safety: the form never bypasses a server gate — placeBetAction forwards xpredict_session and the backend (current_betting_player) is the authority; client zod is pre-flight UX only."

requirements-completed: [MKT-03]

# Metrics
duration: 8min
completed: 2026-05-29
---

# Phase 9 Plan 04: Player Market Detail Page + Order Entry Summary

**`/markets/[slug]` SSR detail page (parallel fetch, two-column sticky-panel grid, always-visible resolution criteria) composing the Plan 03 chart/socket/LiveIndicator with a rhf+zod order-entry form → confirm modal → cookie-forwarded `place_bet` whose every backend status maps to a specific inline message — no toasts — plus an anonymized recent-activity feed and Suspense skeletons.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-29T17:09:57Z
- **Completed:** 2026-05-29T17:17:13Z
- **Tasks:** 2
- **Files created:** 11

## Accomplishments

- Shipped the user-observable MKT-03 slice: a player can open `/markets/{slug}`, read the question + always-visible resolution criteria, watch the YES-probability chart, see live odds + a Live/Stale/Reconnecting indicator update in place over the WebSocket, see anonymized recent activity, and place a bet end-to-end through a confirm modal.
- Order-entry form routes through `placeBetAction` (cookie-forward `POST /bets`) and surfaces SPECIFIC inline copy for each backend status (402 insufficient balance, 409 market closed, 403 unverified/banned, 422 stake-limit, 401 login affordance) — no generic toast anywhere in the bet flow (T-09-12/13).
- Composed the Plan 03 reusable pieces (PriceHistoryChart, useMarketSocket, LiveIndicator, shadcn dialog/select) + the Plan 02 read endpoints rather than rebuilding them, via two thin `"use client"` wrappers that bridge the SSR Server Component to the client-only hooks (SP-5).
- Added the MarketDetailSkeleton (two-column mirror with an `h-64` chart-area block) and a portfolio `loading.tsx`, both no-layout-shift; the activity feed renders the already-anonymized payload with no user-identity field (T-09-14, defense-in-depth).

## Task Commits

Each task was committed atomically:

1. **Task 1: Bet schemas + placeBetAction + order-entry form + confirm dialog (inline error mapping)** — `e67d5f2` (feat)
2. **Task 2: Market detail page (SSR shell + two-column grid) + recent-activity feed + skeletons** — `e33bdce` (feat)

**Plan metadata:** committed separately (docs: complete plan).

_Note: Task 1 is `tdd="true"` — the order-form error-mapping test (`order-entry-form.test.tsx`) was authored alongside its implementation and is GREEN (7/7). Both schemas/action/form/dialog landed in one cohesive feat commit since they are a single inseparable form slice._

## Files Created/Modified

- `frontend/src/lib/bet-schemas.ts` — `BetSchema` (YES/NO + positive decimal-as-string stake within tenant min/max) + `ActionState`/`ActionErrors` contract (mirrors auth-schemas; separate from the `"use server"` file).
- `frontend/src/lib/bet-actions.ts` — `placeBetAction` Server Action: reads `xpredict_session`, cookie-forward `POST /bets` `{market_id, outcome_id, stake}`, maps 402/409/403/422/401 + 201 + fallback to exact UI-SPEC inline copy.
- `frontend/src/components/order-entry-form.tsx` — rhf + `zodResolver(BetSchema)` + `useActionState`; submit opens the confirm dialog, only Confirm fires the action; inline `role=alert` errors, live expected-payout preview, CLOSED-disabled + unauthenticated login affordance.
- `frontend/src/components/bet-confirm-dialog.tsx` — controlled shadcn Dialog: stake / current odds / expected payout rows + "Odds may move before your bet is placed." footer + Confirm/Cancel.
- `frontend/src/components/order-entry-form.test.tsx` — asserts each of 402/409/403/422 inline copy strings renders + no-toast (role=alert) + auth/closed states (7 tests).
- `frontend/src/components/recent-activity-feed.tsx` — anonymized "Someone backed {YES|NO} · {amount} PLAY_USD · {rel-time}" rows + "No bets yet" empty state.
- `frontend/src/components/market-detail-skeleton.tsx` — two-column loading mirror with `h-64` chart block, aria-busy/aria-hidden.
- `frontend/src/components/market-detail-live-odds.tsx` — `"use client"` wrapper composing `useMarketSocket` + `OddsDisplay` + `LiveIndicator` (odds update in place; stale keeps odds visible).
- `frontend/src/components/price-history-section.tsx` — `"use client"` wrapper owning the chart window state + re-fetch on 24h/7d/30d toggle.
- `frontend/src/app/markets/[slug]/page.tsx` — async Server Component: parallel SSR fetch, `grid grid-cols-1 lg:grid-cols-3`, always-visible Resolution criteria, sticky `lg:top-8` order panel, MarketNotFound state, Suspense + MarketDetailSkeleton, `isAuthenticated` from cookie presence.
- `frontend/src/app/portfolio/loading.tsx` — portfolio route Suspense skeleton mirroring its layout.

## Decisions Made

- **Outcome Select defaults to "YES".** Makes the form submittable without forcing a Radix Select interaction, which keeps the order-form test off Radix's jsdom portal/pointer-event path (a known testing-flakiness source). The player can still switch to NO; the Select is fully rendered and wired through rhf.
- **403 disambiguation on the backend detail.** `placeBetAction` reads the FastAPI `detail` and uses the banned copy when it contains "ban" (the gate sends "Account is banned from placing bets."), otherwise the unverified copy — the plan's stated default.
- **`Promise.allSettled` for the SSR fetch.** The market read is the gate (404 → "Market not found"); price-history/activity degrade to empty and render their own empty states rather than failing the whole page.
- **Expected payout = `stake / current_odds_of_chosen`** as display-only 2-dp string math (RESEARCH Pattern 7) — never stored as a float (SP-1); shows "—" until both inputs are valid.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added two thin `"use client"` wrapper components to bridge the SSR page to the Plan 03 client hooks**
- **Found during:** Task 2 (market detail page)
- **Issue:** The plan's Task 2 `<files>` list names only `recent-activity-feed.tsx`, `market-detail-skeleton.tsx`, `markets/[slug]/page.tsx`, `portfolio/loading.tsx`, but its `<action>` explicitly requires the page to "wire `use-market-socket` ... via a small `"use client"` wrapper" and the chart toggle to "re-fetch via `fetchPriceHistory` on change — a small `"use client"` wrapper". An async Server Component cannot call `useMarketSocket`/`useState` directly, so the wrappers are mandatory to complete the task as written.
- **Fix:** Created `market-detail-live-odds.tsx` (composes `useMarketSocket` + `OddsDisplay` + `LiveIndicator`) and `price-history-section.tsx` (owns the chart window state + client re-fetch). Both are the exact wrappers the plan's action text calls for.
- **Files modified:** frontend/src/components/market-detail-live-odds.tsx, frontend/src/components/price-history-section.tsx
- **Verification:** `pnpm build` exits 0 (app-graph typecheck passes); the page renders the live-odds block + chart toggle.
- **Committed in:** `e33bdce` (Task 2 commit)

**2. [Rule 2 - Missing Critical] Added a `DialogDescription` to the confirm dialog for accessibility**
- **Found during:** Task 1 (order-entry form / confirm dialog)
- **Issue:** Radix `DialogContent` emits "Missing `Description` or `aria-describedby={undefined}`" — the modal had no accessible description, an a11y gap for screen-reader users.
- **Fix:** Added a `DialogDescription` ("Review your stake, the current odds, and the expected payout before placing this bet.") under the title.
- **Files modified:** frontend/src/components/bet-confirm-dialog.tsx
- **Verification:** The Radix warning no longer appears in the test run; all 7 order-form tests still GREEN.
- **Committed in:** `e67d5f2` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing-critical a11y)
**Impact on plan:** Both necessary to complete the task as written / for accessibility. No scope creep — the wrappers are the exact bridge the plan's action text mandates; the dialog description is a one-line a11y fix.

## Issues Encountered

- **DEF-FE-01 (pre-existing, NOT fixed — out of scope per the plan):** `frontend/src/__tests__/middleware.test.ts` is a Phase 02-05 orphan importing `../middleware` (renamed `../proxy` in Next 16). It is the ONLY failure in the repo-wide `pnpm test` (its suite fails to LOAD) and the ONLY error in repo-wide `pnpm typecheck` (1 error). Already documented in `deferred-items.md`. Every 09-04 new file is type-clean and `pnpm build` (app-graph typecheck) exits 0; the full suite is **52/52 actual tests passing** with this single orphan suite failing to load. Per the plan's `<known_preexisting_defect>`, this is expected, noted, and deliberately untouched.

## Verification

- `cd frontend && pnpm test src/components/order-entry-form.test.tsx` → 7/7 GREEN (each 402/409/403/422 inline copy + no-toast + auth/closed states).
- `cd frontend && pnpm build` → exits 0; `/markets/[slug]` present as a dynamic server-rendered route; Next's own TypeScript pass passes.
- `cd frontend && pnpm test` → 52/52 actual tests pass across 12 suites; the only failing suite is the pre-existing DEF-FE-01 orphan (`middleware.test.ts`, fails to load — documented out of scope).
- `cd frontend && pnpm typecheck` → exactly 1 error, the DEF-FE-01 orphan; zero errors attributable to any 09-04 file.
- **Manual-verify (documented, stack-dependent):** full MKT-04 round-trip (admin odds edit / Polymarket poll → odds animate on `/markets/{slug}` + Live dot within 2s) and the Recharts emerald line painting in a real browser — both require the full stack + a browser (the automated tests cover the pipeline + chart-not-blank in isolation).

## User Setup Required

None — no new external service configuration. `NEXT_PUBLIC_WS_URL` + `BACKEND_URL` were already documented (Plan 03 / Phase 1); no new env vars, no new dependencies (the Radix dialog/select packages were vetted + added in Plan 03).

## Next Phase Readiness

- **Phase 9 is COMPLETE (4/4 plans).** The full MKT-03 + MKT-04 user story is shipped end-to-end: backend WS broadcast (09-01) → read endpoints (09-02) → frontend real-time slice + chart (09-03) → composed detail page + order entry (09-04).
- Ready for `/gsd-verify-work 9` then `/gsd-code-review` → PR. The two manual-verify items (live WS round-trip + browser chart paint) move to the verify step.
- **Note for the verifier/PM:** the DEF-FE-01 orphan (`middleware.test.ts` → `../middleware`) should be fixed in a dedicated cleanup (import `../proxy` or delete) so repo-wide `pnpm typecheck`/`pnpm test` go fully green — tracked in `deferred-items.md`, out of scope here.

## Self-Check: PASSED

- All 11 created source files verified present on disk (+ this SUMMARY).
- Both task commits verified in git history: `e67d5f2` (Task 1), `e33bdce` (Task 2).

---
*Phase: 09-user-app-ux-polish-market-detail-real-time*
*Completed: 2026-05-29*
