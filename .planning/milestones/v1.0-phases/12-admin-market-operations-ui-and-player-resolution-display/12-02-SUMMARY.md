---
phase: 12-admin-market-operations-ui-and-player-resolution-display
plan: 02
subsystem: ui
tags: [nextjs, server-actions, bearer-auth, vitest, tanstack, shadcn, typescript]

# Dependency graph
requires:
  - phase: 12-admin-market-operations-ui-and-player-resolution-display (Plan 12-01)
    provides: "MarketRead resolution + stake fields (winning_outcome_id / resolution_source / resolution_justification / min_stake / max_stake) — mirrored into admin-markets-types.ts"
  - phase: 08-admin-crm (Plan 08-03)
    provides: "admin-api.ts Bearer-forward core + admin-api.test.ts URL-contract guard + user-status-badge.tsx chip — the clone sources"
provides:
  - "admin-markets-api.ts ('use server'): fetchMarkets / fetchMarketAdmin / createMarket / updateMarket / closeMarket (/api/v1) + resolveMarket / reverseSettlement / forceSettle (bare /admin/markets)"
  - "admin-markets-types.ts: MarketListItem / MarketDetail(=MarketRead) / OutcomeRead / MarketCreateBody / MarketUpdateBody / ResolveMarketBody / ReverseBody / ForceSettleBody / PaginatedResponse<T> / MarketListParams / MarketStatus / MarketSource"
  - "admin-markets-api.test.ts: Wave-0 URL-prefix contract guard (the regression lock for Pitfall 1)"
  - "MarketStatusBadge: shared 5-state status chip (OPEN/CLOSED/RESOLVED/CANCELLED/DRAFT) with the locked UI-SPEC palette + a11y chip"
affects: [12-03, 12-04, 12-05, 12-06, markets-data-table, market-form, resolve-market-dialog, reverse-settlement-dialog, force-settle-dialog, market-resolution-panel]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-prefix Bearer-forward API split: CRUD under /api/v1, settlement bare — full path passed per call, guarded by a URL-contract unit test"
    - "'use server' / types-sibling split (async-only export constraint): admin-markets-api.ts + admin-markets-types.ts"
    - "Shared status-chip clone: 5-key palette map keyed by the wire status string with a neutral fallback"

key-files:
  created:
    - frontend/src/lib/admin-markets-types.ts
    - frontend/src/lib/admin-markets-api.ts
    - frontend/src/lib/__tests__/admin-markets-api.test.ts
    - frontend/src/components/admin/market-status-badge.tsx
    - frontend/src/components/admin/__tests__/market-status-badge.test.tsx
  modified: []

key-decisions:
  - "Money/odds fields typed `string` end-to-end (SP-1): volume, volume_24hr, min_stake, max_stake, initial_odds, current_odds — never parseFloat for storage."
  - "MarketDetail declared as an explicit interface (+ MarketRead alias) rather than `extends MarketListItem` — the backend MarketRead omits polymarket_slug/source_url and adds resolution_criteria + the resolution/stake projection, so an explicit shape matches the wire exactly."
  - "createMarket uses `initial_odds_yes`; updateMarket uses `odds_yes` — the verified backend field-name discrepancy is encoded in the two body types so Wave-2 forms cannot send the wrong key."
  - "MarketStatusBadge renders the raw uppercase status token as the label (matches how markets-data-table passes market.status) and ships a neutral FALLBACK_COLOR for unknown tokens (non-crash guard, not a stub)."

patterns-established:
  - "Pattern 1: settlement wrappers are BARE /admin/markets/{id}/... (clone of rechargeWallet); CRUD wrappers keep /api/v1/admin/markets — the split is asserted by not.toContain('/api/v1') in the contract test."
  - "Pattern 2: a 'use server' data module exports only async fns; all shared interfaces live in a sibling *-types.ts file."

requirements-completed: [ADM-01, ADM-02, ADM-03, ADM-04, ADM-05, ADM-06, STL-02, STL-07]

# Metrics
duration: 6min
completed: 2026-06-03
---

# Phase 12 Plan 02: Admin-Markets Frontend Foundation Summary

**Two-prefix `"use server"` Bearer-forward API layer for market CRUD (`/api/v1`) + settlement (bare `/admin/markets`), locked by a URL-contract guard test, plus a shared 5-state `MarketStatusBadge` — the Wave-1 foundation every admin slice (12-04/05/06) imports.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-03T14:09:20Z
- **Completed:** 2026-06-03T14:15:05Z
- **Tasks:** 3
- **Files modified:** 5 (all created)

## Accomplishments
- **The phase's #1 landmine is now structurally impossible:** `admin-markets-api.ts` carries market CRUD under `/api/v1/admin/markets` and settlement (resolve/reverse/force-settle) under the BARE `/admin/markets/{id}/...` prefix, and `admin-markets-api.test.ts` asserts `not.toContain("/api/v1")` on every settlement wrapper — the regression that already shipped+got-caught for recharge cannot recur here.
- The `admin_jwt` HttpOnly cookie is read server-side via `bearerHeader` and forwarded as `Authorization: Bearer`; the token never reaches client JS (threat T-12-05). The test asserts the Bearer header is forwarded on both a CRUD and a settlement wrapper.
- `admin-markets-types.ts` transcribes the verified backend shapes (incl. the Plan 12-01 resolution + stake fields on `MarketRead`) with money/odds as strings — Wave-2 has zero cross-plan file collisions for api/types/badge.
- `MarketStatusBadge` renders all 5 statuses with the locked UI-SPEC palette + the `aria-label="Status: {status}"` chip convention, built TDD (RED→GREEN).

## Task Commits

Each task was committed atomically:

1. **Task 1: admin-markets-types.ts + admin-markets-api.ts** - `56b9cf2` (feat)
2. **Task 2: admin-markets-api.test.ts (URL-prefix contract guard)** - `b5a0467` (test)
3. **Task 3: market-status-badge.tsx + test (TDD)** - `80c2d55` (test/RED) → `a089b73` (feat/GREEN)

**Plan metadata:** see final docs commit.

## Files Created/Modified
- `frontend/src/lib/admin-markets-types.ts` - Shared types (MarketListItem, MarketDetail/MarketRead, OutcomeRead, the 5 request bodies, PaginatedResponse<T>, MarketListParams, MarketStatus, MarketSource); money/odds typed string.
- `frontend/src/lib/admin-markets-api.ts` - `"use server"` Bearer-forward wrappers; CRUD on `/api/v1`, settlement bare; cloned `bearerHeader` + `adminApiFetch` from admin-api.ts.
- `frontend/src/lib/__tests__/admin-markets-api.test.ts` - Wave-0 URL-prefix contract guard (10 tests): CRUD keeps `/api/v1`, settlement is bare + `not.toContain("/api/v1")`, Bearer forwarded.
- `frontend/src/components/admin/market-status-badge.tsx` - Shared 5-state status chip; locked palette + a11y chip; neutral fallback for unknown tokens.
- `frontend/src/components/admin/__tests__/market-status-badge.test.tsx` - Behavior contract (15 tests): all 5 statuses render label + aria-label, locked inset, OPEN/RESOLVED/CANCELLED palette, className merge.

## Decisions Made
- **MarketDetail as an explicit interface (+ `MarketRead` alias), not `extends MarketListItem`.** The backend `MarketRead` differs from `MarketListItem` (no `polymarket_slug`/`source_url`; adds `resolution_criteria` + the STL-06 resolution projection + BET-06 stake limits), so an explicit shape matches the wire 1:1 and avoids inheriting list-only fields the detail read never sends.
- **The odds field-name split is type-encoded:** `MarketCreateBody.initial_odds_yes` vs `MarketUpdateBody.odds_yes` (the verified backend discrepancy from PATTERNS), so Wave-2's create/edit form cannot send the wrong key.
- **`buildQuery` reused from `admin-query.ts`** (the existing sync, client-safe helper) for the list querystring (source/status/category/page/page_size/sort) — no new query builder.
- **Money/odds string discipline (SP-1, CLAUDE.md)** applied to every wire field.

## Deviations from Plan

None - plan executed exactly as written.

The plan anticipated the only divergence-prone detail (the `MarketDetail` shape) by listing the exact field set in Task 1's `<action>`; I declared it as an explicit interface to match the backend `MarketRead` (which is what the admin detail endpoint returns) rather than extending the list item — this is faithful to the plan's transcription instruction, not a scope change. The pre-existing DEF-FE-01 orphan `middleware.test.ts` did not surface during scoped typecheck/test, so no deferred-items entry was needed.

## Issues Encountered
None. The clone sources (admin-api.ts, admin-api.test.ts, user-status-badge.tsx) transferred verbatim; the backend two-prefix split was confirmed directly at `markets/router.py:32` (`/api/v1/admin/markets`) vs `settlement/router.py:46` (bare `/admin/markets`) before writing the wrappers.

## Known Stubs
None. The `FALLBACK_COLOR` in `market-status-badge.tsx` is a defensive non-crash default for an unexpected status token (documented in-file), not unwired/placeholder data — all five real statuses have explicit palette entries.

## Verification

- `cd frontend && pnpm test -- src/lib/__tests__/admin-markets-api.test.ts` → **10/10 green** (two-prefix guard).
- `cd frontend && pnpm test -- src/components/admin/__tests__/market-status-badge.test.tsx` → **15/15 green**.
- Both together → **25/25 green**.
- `cd frontend && pnpm typecheck` → **exit 0** (zero errors; the known DEF-FE-01 orphan did not surface in scoped typecheck).
- Build was NOT gated (DEF-FE-BUILD-01 Turbopack/pnpm-symlink deep-path build fails identically on pristine HEAD — pre-existing/out-of-scope per environment notes).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **Wave-2 ready.** Plans 12-04/05/06 import `admin-markets-api.ts` (the 8 wrappers), `admin-markets-types.ts` (the shapes), and `MarketStatusBadge` with no collision. The **load-bearing fact for Wave-2:** the two-prefix split is locked — call CRUD via `/api/v1/admin/markets...` wrappers and settlement via the bare `/admin/markets/{id}/...` wrappers; never hand-build a settlement URL with `/api/v1`.
- `markets-data-table.tsx` (12-04) consumes `fetchMarkets` + `MarketListItem` + `MarketStatusBadge`; the settlement dialogs (12-05/06) consume `resolveMarket`/`reverseSettlement`/`forceSettle` + the body types; `market-resolution-panel.tsx` (12-03) consumes `MarketDetail`'s resolution fields.
- No blockers.

## Self-Check: PASSED

All 5 created files verified on disk; all 4 task commits (`56b9cf2`, `b5a0467`, `80c2d55`, `a089b73`) verified in git log.

---
*Phase: 12-admin-market-operations-ui-and-player-resolution-display*
*Completed: 2026-06-03*
