---
phase: 12-admin-market-operations-ui-and-player-resolution-display
plan: 03
subsystem: api
tags: [bets, fastapi, sqlalchemy, decimal, zod, react-hook-form, stake-limits]

# Dependency graph
requires:
  - phase: 12-01
    provides: "nullable markets.min_stake / max_stake columns (Numeric(18,4)) + migration 0010 applied to the project Postgres; MarketRead/Create/Update already carry the stake fields"
  - phase: 05-bets-settlement
    provides: "BetService.place_bet (ACID), MarketReadPort / MarketView / HouseMarketReadAdapter, the bets router error->4xx mapping, BET_MIN/MAX_STAKE config defaults"
  - phase: 09-user-app-ux-polish-market-detail-real-time
    provides: "OrderEntryForm + bet-schemas.ts (BetSchema, BET_MIN/MAX_STAKE) client mirror; the BetConfirmDialog flow"
provides:
  - "Per-market stake limits (BET-06) enforced server-side INSIDE BetService.place_bet — prefers market.min_stake/max_stake, falls back to settings.BET_MIN_STAKE/BET_MAX_STAKE when NULL"
  - "MarketView carries nullable min_stake/max_stake; HouseMarketReadAdapter populates them from the loaded Market row"
  - "new StakeOutOfRange domain error mapped to HTTP 422 by the bets router (the router-level global-only check is removed — RESEARCH A4)"
  - "order-entry client mirror prefers per-market bounds via a makeBetSchema(min, max) factory; the out-of-range copy reads 'Stake must be between {min} and {max} PLAY_USD.'"
affects: [12-04 (player resolved-panel display), 12-05 (admin market-form min/max stake fields will pass the bounds into OrderEntryForm)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-market limit lives in the SERVICE, not the router (RESEARCH A4): the router has no market loaded; place_bet validates the market via the port, so the [min,max] check is computed there with the market in hand, BEFORE session.begin() (no DB work on a rejected stake)"
    - "Nullable-bound fallback: `bound = market.bound if market.bound is not None else settings.GLOBAL` — a NULL per-market column transparently inherits the global config (no behavior change for existing markets)"
    - "Client schema factory: a static zod schema becomes makeBetSchema(min, max) so per-market bounds drive the pre-flight check while the global constants remain the default; the wire value stays a string (SP-1), parsed only to compare"

key-files:
  created: []
  modified:
    - backend/app/bets/market_port.py
    - backend/app/bets/adapters.py
    - backend/app/bets/exceptions.py
    - backend/app/bets/service.py
    - backend/app/bets/router.py
    - backend/tests/bets/test_bet_router.py
    - backend/tests/bets/test_place_bet.py
    - frontend/src/lib/bet-schemas.ts
    - frontend/src/components/order-entry-form.tsx
    - frontend/src/components/order-entry-form.test.tsx

key-decisions:
  - "The per-market stake check moved from the bets router INTO BetService.place_bet (RESEARCH A4) because only the service loads the market via MarketReadPort. The former router-level global-only check (the 'Phase 10 (TenantConfig)' deferral block) is removed; the limit is now checked once, with the market in hand."
  - "A dedicated StakeOutOfRange(BetError) carries the user-facing message and is mapped to 422 in the router's existing except chain — distinct from the non-positive-stake ValueError guard, which is kept."
  - "The global BET_MIN_STAKE/BET_MAX_STAKE config constants are NOT removed — they are the documented NULL fallback. NULL per-market columns => identical behavior to today (1..100000)."
  - "Client mirror exposes makeBetSchema(min, max); BetSchema is redefined as makeBetSchema(BET_MIN_STAKE, BET_MAX_STAKE) so existing importers stay valid. OrderEntryForm gains optional minStake/maxStake props (12-05 will wire them from the market read); absent => globals."

patterns-established:
  - "Read-port DTO extension ripple: adding a field to the frozen MarketView dataclass with a default keeps all 6 existing construction sites (prod adapter + test stubs) valid; the adapter and the two test _market builders opt in to the new field where a per-market case needs it."

requirements-completed: [BET-06]

# Metrics
duration: ~12min
completed: 2026-06-03
---

# Phase 12 Plan 03: Per-Market Stake Limits End-to-End (BET-06) Summary

**Wires the nullable `markets.min_stake`/`max_stake` columns (added by 12-01) through the bets read port into a server-authoritative range check inside `BetService.place_bet` (preferring the per-market bound, falling back to the global config on NULL), and extends the order-entry client mirror to prefer those bounds via a `makeBetSchema(min, max)` factory — server stays authoritative, client is UX-only.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-03T14:21:09Z
- **Completed:** 2026-06-03T14:34:04Z
- **Tasks:** 2 (both `tdd="true"`)
- **Files modified:** 10 (7 backend, 3 frontend)

## Accomplishments
- **Server-authoritative per-market limits (BET-06):** `BetService.place_bet` now computes `min = market.min_stake if not None else settings.BET_MIN_STAKE` / `max = market.max_stake if not None else settings.BET_MAX_STAKE` and rejects an out-of-range stake with `StakeOutOfRange` (→ 422) BEFORE `session.begin()` — a market with `min=10/max=50` rejects 5 and 60, accepts 25; a NULL-limit market keeps the global 1..100000 behavior.
- **Read port carries the columns:** `MarketView` gained nullable `min_stake`/`max_stake` (defaulted, preserving all 6 existing constructions) and `HouseMarketReadAdapter.get_market` populates them from the loaded `Market` row.
- **Router check superseded (RESEARCH A4):** removed the global-only stake check (the literal "Phase 10 (TenantConfig)" deferral block) — the limit is now enforced once, in the service, with the market loaded; the router maps `StakeOutOfRange` → 422.
- **Client mirror prefers per-market bounds:** `makeBetSchema(min, max)` factory + optional `minStake`/`maxStake` props on `OrderEntryForm`; the out-of-range copy reads "Stake must be between {min} and {max} PLAY_USD." and the `expectedPayout` "—" gate uses the same effective bounds so preview and submit agree. Money stays a string (SP-1); the server remains authoritative (T-12-08).
- **Coverage:** +6 backend cases (router: global-min/max fallback, per-market reject 5/60, accept 25; service: per-market preferred-over-config reject below-min/above-max, accept-in-range, NULL→global-fallback) and +2 frontend cases (below-min / above-max show the range message and never fire the Server Action).

## Task Commits

Each task was committed atomically:

1. **Task 1: MarketView limits + adapter population + place_bet per-market check (global fallback)** — `8f07cab` (feat)
2. **Task 2: Client mirror — order-entry-form + bet-schemas read per-market bounds** — `1683c3a` (feat)

**Plan metadata:** (final docs commit — see git log after this SUMMARY)

_Note on the `tdd="true"` shape (same rationale 12-01 documented): both tasks are additive read-port / Protocol ripples where the test surface and implementation are inseparable — the new tests cannot construct against the old `MarketView` shape, and the service check + router removal must change in lockstep. The RED/GREEN gate here is the verification suite (mypy + `tests/bets` + the order-form vitest + typecheck): every new per-market/fallback assertion fails without the change and passes with it. Both tasks landed as a single `feat` commit each rather than separate test→impl commits._

## Files Created/Modified
- `backend/app/bets/market_port.py` — `MarketView` frozen dataclass gains `min_stake: Decimal | None = None` and `max_stake: Decimal | None = None` (defaults mandatory).
- `backend/app/bets/adapters.py` — `HouseMarketReadAdapter.get_market` passes `min_stake=market.min_stake, max_stake=market.max_stake` into the `MarketView(...)` construction.
- `backend/app/bets/exceptions.py` — new `StakeOutOfRange(BetError)` carrying the user-facing range message.
- `backend/app/bets/service.py` — `place_bet` computes the effective bounds (per-market preferred, `settings.BET_MIN_STAKE`/`BET_MAX_STAKE` fallback) after outcome validation and BEFORE `session.begin()`; raises `StakeOutOfRange` on a violation. Imports `get_settings`. The non-positive `ValueError` guard is kept.
- `backend/app/bets/router.py` — REMOVED the global-only stake check block (+ its now-unused `get_settings` import); added `StakeOutOfRange` → `HTTP_422_UNPROCESSABLE_ENTITY` in the existing except chain; docstring notes the supersession.
- `backend/tests/bets/test_bet_router.py` — `_market` builder accepts `min_stake`/`max_stake`; replaced the two router-level stake tests (which relied on the removed pre-market check) with global-fallback cases and added per-market reject(5/60)/accept(25) cases wiring a stub market + seeded wallet.
- `backend/tests/bets/test_place_bet.py` — `_market` builder accepts the bounds; added 4 service-level cases (per-market preferred-over-config below-min/above-max, accept-in-range, NULL→global-config fallback with an inclusive at-min accept). Imports `StakeOutOfRange`.
- `frontend/src/lib/bet-schemas.ts` — added `makeBetSchema(min, max)` factory; `BetSchema = makeBetSchema(BET_MIN_STAKE, BET_MAX_STAKE)` (importers unaffected); `BET_MIN_STAKE`/`BET_MAX_STAKE` still exported.
- `frontend/src/components/order-entry-form.tsx` — optional `minStake?`/`maxStake?` props; derives `minNum`/`maxNum` (per-market preferred, global fallback); builds the resolver from `makeBetSchema` via `useMemo`; `expectedPayout` now takes the bounds; the `BetConfirmDialog` flow and the `role="alert"` bet-error region are unchanged.
- `frontend/src/components/order-entry-form.test.tsx` — +2 per-market-bounds cases asserting the range message renders and the Server Action is not fired.

## Decisions Made
- **Per-market check in the service, not the router (RESEARCH A4).** The router never loads the market (only the service does, via `MarketReadPort`), so the global-only router check was structurally unable to apply per-market bounds. Moving it into `place_bet` (where the validated market is in hand, right after outcome validation, before `session.begin()`) makes the limit checked exactly once with no DB work on a rejected stake. The old block (with the "Phase 10 (TenantConfig)" deferral comment) is removed.
- **`StakeOutOfRange` over reusing `ValueError`.** A distinct domain error carries the precise "Stake must be between {min} and {max}." message and maps cleanly to 422 in the router's except chain, while the existing non-positive-stake `ValueError` guard (also 422 via Pydantic `gt=0`) stays untouched.
- **Global config kept as the NULL fallback.** `settings.BET_MIN_STAKE`/`BET_MAX_STAKE` are unchanged and are the fallback when a market's column is NULL — existing markets behave exactly as before (no migration/backfill needed; 12-01 already added the columns).
- **`makeBetSchema` factory + optional form props.** The previously-static `BetSchema` became `makeBetSchema(BET_MIN_STAKE, BET_MAX_STAKE)` so no current importer breaks, and `OrderEntryForm` accepts optional `minStake`/`maxStake` (12-05 will pass the market's values from the page); absent → the globals.

## Deviations from Plan

None affecting code/scope — the plan executed exactly as written (every acceptance criterion met verbatim). One in-scope test-adjustment and one tooling issue are documented below.

### In-scope test adjustment (not a deviation — explicitly mandated by the plan)

The two pre-existing router stake tests (`test_post_bets_422_when_stake_below_min` / `_above_max`) fired with NO market wired (`_auth_as(_User(uuid4()))`), relying on the removed router-level pre-market check. Because the check moved into the service (which loads the market), those exact tests would have hit the real adapter → 404 instead of 422. The plan's Task-1 action #4/#5 directs removing the router check and extending the tests "where a per-market case needs them," so they were replaced with the global-fallback equivalents (a stub market with NULL limits, stake below/above the global bound → 422) plus the new per-market cases. This is the planned consequence of RESEARCH A4, not unplanned work.

## Issues Encountered

- **`corepack pnpm` resolves to pnpm 11.5.1 and is destructive on this Windows host (tooling, not code).** The corepack-pinned pnpm (11.5.1) runs a `runDepsStatusCheck` auto-install before every script; on this repo it (a) aborted on no-TTY, then (b) under `CI=true` **recreated/wiped `frontend/node_modules`**, and (c) on `--no-frozen-lockfile` reconcile it rewrote `pnpm-lock.yaml` (removing the `overrides:` block → a new `pnpm-workspace.yaml`, adding `libc:` fields) and finally failed on `ERR_PNPM_IGNORED_BUILDS`. Resolution: (1) restored `node_modules` via one `corepack pnpm install --no-frozen-lockfile` (same resolved versions — react-is 19.2.6 pin intact), then (2) **reverted the lockfile to HEAD and deleted the pnpm-11 `pnpm-workspace.yaml`** so the committed frontend dependency manifest stays byte-identical to HEAD (the react-is override location is load-bearing per STATE — it keeps Recharts from going blank on React 19; the Dockerfile CI pnpm is 9.15.0). (3) Ran the frontend verification with the **standalone pnpm 9.15.0 on PATH** (`pnpm typecheck`/`pnpm lint`, which the pre-commit `frontend-lint` hook also uses — bare `pnpm`, not `corepack pnpm`) and vitest directly via `node node_modules/vitest/vitest.mjs`. No `--no-verify` was used; the commit hooks passed. **No lockfile or workspace-config change is included in this plan.** (Follow-up for Pol: align the corepack cache to pnpm 9.15.0, or add a committed `packageManager` pin, so `corepack pnpm` stops drifting to 11 — DEF-FE-PNPM11.)

## Known Stubs
None — every change is real wiring (read-port field, adapter population, service range check, router 422 mapping, zod factory, form props + payout gate). Diff scan for stub/placeholder markers in the touched files is clean (`order-entry-form.tsx`'s `placeholder="0.00"` is the unchanged HTML input attribute).

## User Setup Required
None — no external service configuration required. The `markets.min_stake`/`max_stake` columns + migration 0010 were already applied to the project Postgres by 12-01; this plan adds no migration. NULL columns mean existing markets are unaffected.

## Next Phase Readiness
- **BET-06 enforcement complete end-to-end.** Plan 12-05 (admin market-form) can add the optional Min/Max stake (PLAY_USD) `Input`s that PATCH `markets.min_stake`/`max_stake`; plan 12-04 (player resolution display) is independent of this work.
- **OrderEntryForm bounds-wiring seam ready.** The form already accepts `minStake`/`maxStake`; `markets/[slug]/page.tsx` need only pass `market.min_stake`/`market.max_stake` (already on `MarketRead` per 12-01) when it renders `OrderEntryForm` — a one-line prop pass in a future edit.
- **Open follow-up for Pol:** DEF-FE-PNPM11 — the host's `corepack pnpm` resolves to 11.5.1 and is destructive to `node_modules`/lockfile; align it to 9.15.0 (or pin `packageManager`).

## Self-Check: PASSED

- All 10 created/modified source files verified present on disk, plus the SUMMARY.
- Both task commits verified in `git log`: `8f07cab` (Task 1, backend), `1683c3a` (Task 2, frontend).
- Static + test gates green: `uv run mypy app/bets` → 0 issues; ruff check/format clean; `uv run pytest tests/bets -q` → 46 passed (was 36, +10 per-market/fallback cases); money-lint OK (2 pre-existing 12-01 nullable-stake warnings, non-failing); `order-entry-form.test.tsx` → 9 passed (was 7, +2 per-market cases); `tsc --noEmit` exit 0; `pnpm lint` exit 0 (14 warnings, 0 errors — all pre-existing).
- The "Phase 10 (TenantConfig)" router-check comment is gone (grep → 0); `service.py` references `market.min_stake`/`market.max_stake` with the config fallback before `session.begin()`; `adapters.py` passes both into `MarketView(...)`.

---
*Phase: 12-admin-market-operations-ui-and-player-resolution-display*
*Completed: 2026-06-03*
