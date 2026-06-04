---
phase: 09-user-app-ux-polish-market-detail-real-time
plan: 03
subsystem: ui
tags: [recharts, react-is, websocket, radix, shadcn, nextjs, react19, vitest, tdd]

# Dependency graph
requires:
  - phase: 09-01
    provides: "public /ws/markets/{id} WS endpoint + lean string-odds delta payload {type, market_id, outcomes:[{outcome_id, odds}], ts}"
  - phase: 09-02
    provides: "GET /{slug}/price-history?window= and GET /{slug}/activity public read endpoints"
provides:
  - "Recharts YES-probability PriceHistoryChart (react-is pin + pnpm override neutralize the React 19 blank-chart bug) with 24h/7d/30d toggle + <2-snapshot empty state"
  - "useMarketSocket 'use client' hook: WS connect + exponential-backoff reconnect + Live/Stale(>30s, keeps odds)/Reconnecting state machine"
  - "LiveIndicator dot+label component driven by ConnState (aria-live=polite)"
  - "lib/api.ts fetchMarket / fetchPriceHistory / fetchActivity + MarketDetail/PriceHistoryResponse/ActivityItem/PricePoint/PriceWindow types + MarketNotFound (money/odds typed as string)"
  - "hand-copied shadcn dialog + select primitives (new-york) wrapping @radix-ui/react-dialog + react-select"
affects: [09-04, phase-10-admin-dashboard]

# Tech tracking
tech-stack:
  added: [recharts@3.8.1, react-is@19.2.6, "@radix-ui/react-dialog@1.1.15", "@radix-ui/react-select@2.2.6"]
  patterns:
    - "pnpm.overrides.react-is = \"$react-is\" collapses ALL transitive react-is to the installed React version (the canonical Recharts-on-React-19 fix)"
    - "chart-not-blank smoke test asserts path.recharts-line-curve renders under jsdom (ResizeObserver + getBoundingClientRect stubbed) — the react-is sentinel"
    - "WS connection state machine ported from validated spike 003 into a React hook (refs for socket/attempt/lastMsg, 5s stale poll, never blank odds on stale)"
    - ".test.ts hook test opts into jsdom via a // @vitest-environment jsdom docblock (file name kept per plan; env overridden per-file)"

key-files:
  created:
    - frontend/src/components/price-history-chart.tsx
    - frontend/src/components/price-history-chart.test.tsx
    - frontend/src/hooks/use-market-socket.ts
    - frontend/src/hooks/use-market-socket.test.ts
    - frontend/src/components/live-indicator.tsx
    - frontend/src/components/ui/dialog.tsx
    - frontend/src/components/ui/select.tsx
  modified:
    - frontend/package.json
    - frontend/pnpm-lock.yaml
    - frontend/src/lib/api.ts
    - .env.example
    - docker-compose.yml

key-decisions:
  - "react-is pinned to 19.2.6 (exact installed React) + pnpm.overrides — pnpm why react-is now reports a SINGLE version (was 16.13.1 + 17.0.2 transitive)"
  - "NEXT_PUBLIC_WS_URL documented in the existing root .env.example (no frontend/.env.example exists — single-file convention) + docker-compose frontend env"
  - "recharts kept at ^3.8.1 caret (lockfile pins exact 3.8.1) matching every other dep's caret convention"
  - "chart window toggle implemented as a ToggleGroup of Button size=sm (executor discretion per UI-SPEC; lighter than Radix tabs)"

patterns-established:
  - "react-is pnpm override is the project-wide Recharts guard — Phase 10's KPI dashboard inherits it for free"
  - "useMarketSocket is the first client-side data path / WS hook; future live surfaces follow its state-machine + cleanup shape"

requirements-completed: [MKT-03, MKT-04]

# Metrics
duration: ~33min
completed: 2026-05-29
---

# Phase 9 Plan 03: Frontend real-time slice + Recharts foundation Summary

**Recharts YES-probability chart (blank-chart bug on React 19 neutralized by a react-is pin + pnpm override, gated by a chart-not-blank smoke test), a WebSocket `useMarketSocket` hook driving Live/Stale/Reconnecting with backoff that never blanks the odds, a LiveIndicator, the detail/price-history/activity typed fetchers, and hand-copied shadcn dialog + select primitives.**

## Performance

- **Duration:** ~33 min
- **Started:** 2026-05-29T16:30Z (approx — first action)
- **Completed:** 2026-05-29T17:03Z
- **Tasks:** 3 executed (Task 1 was the package-legitimacy checkpoint, approved by the user before this run)
- **Files modified:** 12 (11 source/config + the lockfile)

## Accomplishments

- **Neutralized the single highest-risk item in the phase** — Recharts rendering blank on React 19. `react-is` is pinned to the exact installed React (`19.2.6`) and a `pnpm.overrides.react-is = "$react-is"` block collapses ALL transitive `react-is` (was `16.13.1` + `17.0.2`) to one version. `pnpm why react-is` reports a single version; the chart-not-blank smoke test asserts a real Recharts `path.recharts-line-curve` renders (the react-is sentinel).
- **PriceHistoryChart**: `"use client"` Recharts `LineChart` with the emerald-600 (`#059669`) YES line, zinc-200 grid, 0–100% Y axis, sized `h-64` parent (Pitfall 2), a 24h/7d/30d toggle defaulting to 7d, and the `<2`-snapshot empty state ("Not enough price history yet") at the same height.
- **useMarketSocket**: ports the validated spike 003 reconnect/stale logic into a React hook — connects to `${NEXT_PUBLIC_WS_URL}/ws/markets/{id}`, drives `live → stale(>30s) → reconnecting`, **keeps the last odds visible on stale** (Pitfall 5), reconnects with exponential backoff capped at 30s + jitter, pings periodically, ignores non-`price_update` frames, and tears down the socket + intervals + timer on unmount. Proven by a fake-timers + stub-WebSocket state-machine test.
- **LiveIndicator**: dot + label per `ConnState` (emerald Live / amber Stale / amber-pulse Reconnecting), `aria-live="polite"`, mirroring the `odds-display.tsx` semantic-color idiom.
- **lib/api.ts**: added `fetchMarket` (typed `MarketNotFound` on 404), `fetchPriceHistory(slug, window)`, `fetchActivity(slug)` and the `MarketDetail`/`PriceHistoryResponse`/`ActivityItem`/`PricePoint`/`PriceWindow` types — money/odds typed as `string` throughout (SP-1).
- **shadcn dialog + select** hand-copied (new-york, `cn` from `@/lib/utils`, zinc + `dark:` variants) wrapping the two newly-installed Radix packages — ready for the Plan 04 order form + confirm modal.

## Task Commits

Each task was committed atomically:

1. **Task 2: install recharts + react-is pin + Radix dialog/select; add NEXT_PUBLIC_WS_URL** — `c366f1e` (feat)
2. **Task 3: PriceHistoryChart + chart-not-blank smoke test** — `1300ad4` (feat) — TDD: RED (resolve-failure, component absent) → GREEN (component + 4 passing tests, incl. the react-is `path` sentinel)
3. **Task 4: use-market-socket + LiveIndicator + api.ts fetchers** — `32c0bf8` (feat) — TDD: RED (resolve-failure) → GREEN (hook + 4 passing fake-timer tests). One Rule-1 timing fix applied (see Deviations).

_Task 1 (the blocking package-legitimacy checkpoint) was satisfied by the user's "approved" response before this execution; no code was committed for it._

## Files Created/Modified

- `frontend/package.json` — recharts/react-is/Radix deps + `pnpm.overrides.react-is`
- `frontend/pnpm-lock.yaml` — regenerated; single react-is version
- `frontend/src/components/price-history-chart.tsx` — Recharts YES line + window toggle + empty state
- `frontend/src/components/price-history-chart.test.tsx` — chart-not-blank smoke (react-is sentinel) + empty-state + toggle tests
- `frontend/src/hooks/use-market-socket.ts` — WS hook + backoff + Live/Stale/Reconnecting machine
- `frontend/src/hooks/use-market-socket.test.ts` — connection-state-machine test (fake timers + stub WebSocket; jsdom via docblock)
- `frontend/src/components/live-indicator.tsx` — dot+label by ConnState, aria-live=polite
- `frontend/src/components/ui/dialog.tsx` — hand-copied shadcn dialog (wraps @radix-ui/react-dialog)
- `frontend/src/components/ui/select.tsx` — hand-copied shadcn select (wraps @radix-ui/react-select)
- `frontend/src/lib/api.ts` — MarketDetail/PriceHistoryResponse/ActivityItem/PricePoint/PriceWindow + MarketNotFound + fetchMarket/fetchPriceHistory/fetchActivity
- `.env.example` — documented NEXT_PUBLIC_WS_URL (browser WS base; wss:// in prod)
- `docker-compose.yml` — NEXT_PUBLIC_WS_URL in the frontend service env

## Decisions Made

- **`react-is` pinned to `19.2.6` exact + `pnpm.overrides`**: the canonical Recharts-on-React-19 fix. Verified `pnpm why react-is` reports exactly one version (the two prior transitive versions `16.13.1`/`17.0.2`, both in dev tooling, collapse to `19.2.6` — backward-compatible for the `typeOf`/`isElement` checks those tools use).
- **`recharts` left at the `^3.8.1` caret** (lockfile pins exact `3.8.1`) — consistent with every other dependency in `package.json`; the lockfile is the exact-version source of truth.
- **Chart window toggle = ToggleGroup of `Button size="sm"`** (executor discretion per UI-SPEC) — lighter than pulling in Radix tabs; active button marked `aria-pressed`.
- **`PricePoint`/`PriceWindow` added to `lib/api.ts` during Task 3** (the chart depends on them) rather than deferring all api.ts types to Task 4 — the natural dependency order; the remaining types + fetchers landed in Task 4.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pnpm invoked via `corepack pnpm` (not on PATH)**
- **Found during:** Task 2 (before any install)
- **Issue:** `pnpm` is not on the bash PATH in this Windows worktree (`pnpm: command not found`); only `node`, `npm`, and `corepack` are available. PowerShell invocation is denied by the environment.
- **Fix:** Used `corepack pnpm …` for every pnpm command. corepack ships with Node 24 and is the canonical pnpm launcher; it resolved pnpm `10.33.1` (the project has no `packageManager` pin). Also ran an initial `pnpm install --frozen-lockfile` first because the freshly-created worktree had no `node_modules` (required to resolve the exact installed React version).
- **Files modified:** none (tooling only)
- **Verification:** `corepack pnpm install/add/build/test/typecheck` all run correctly.

**2. [Rule 3 - Blocking] `NEXT_PUBLIC_WS_URL` added to the ROOT `.env.example`, not a new `frontend/.env.example`**
- **Found during:** Task 2
- **Issue:** The plan's `files_modified` lists `frontend/.env.example`, but no such file exists — the project uses a single root `.env.example` that already documents the frontend section (`NEXT_PUBLIC_API_URL` lives there). Creating a second env file would fragment the documented convention.
- **Fix:** Added `NEXT_PUBLIC_WS_URL=ws://localhost:8000` (with a browser-readable / NEXT_PUBLIC_-prefix / wss-in-prod comment) to the root `.env.example` Frontend section next to `NEXT_PUBLIC_API_URL`, and mirrored it into the docker-compose `frontend` env block (`ws://backend:8000`, matching how `NEXT_PUBLIC_API_URL` is wired there). Honors the plan's intent ("`.env.example` contains `NEXT_PUBLIC_WS_URL`") against the real file.
- **Files modified:** `.env.example`, `docker-compose.yml`
- **Verification:** `NEXT_PUBLIC_WS_URL` present in both files; `pnpm build` clean.

**3. [Rule 1 - Bug] Stale-detection test advanced to 35s, not 31s (5s poll granularity)**
- **Found during:** Task 4 (GREEN — the stale test initially failed: state stayed "live")
- **Issue:** The stale detector polls every 5s and flags stale only when elapsed is strictly `> 30s`. Advancing fake time by exactly `31_000ms` meant the last interval tick before that was at `t=30_000` (elapsed = exactly 30s, not `> 30s`), so stale never fired within the window — a real boundary in the 5s-granularity poller, not a logic error in the hook.
- **Fix:** Advanced the test clock to `35_000ms` (the first interval tick strictly past the 30s threshold), with a comment documenting the 5s detection granularity (matches the validated spike 003 stale timer). The hook's `> STALE_THRESHOLD_MS` check is correct and unchanged.
- **Files modified:** `frontend/src/hooks/use-market-socket.test.ts`
- **Verification:** All 4 hook tests pass.

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug)
**Impact on plan:** All necessary to execute on this environment / to make the timing test correct. No scope creep — the WS-URL deviation honors the plan's intent against the real file layout.

## Issues Encountered

- **Pre-existing, out-of-scope: `pnpm typecheck` and the full `pnpm test` suite are non-zero** because of ONE orphaned file — `src/__tests__/middleware.test.ts` imports `../middleware`, but the Edge middleware was renamed `src/middleware.ts → src/proxy.ts` in Phase 02-05 (commit `8a9c186`). This breaks `tsc --noEmit` (1 error) and the full-suite run (1 suite fails to load; **all 45 actual tests still pass**, including this plan's chart 4 + hook 4). NOT caused by any 09-03 change — every Phase 09 source file I added is type-clean (verified: zero tsc errors attributable to them) and `next build` (which type-checks the app source graph, not the orphan test) exits 0. Logged to `09 deferred-items.md` with a one-line recommended fix (`../middleware → ../proxy`); left untouched per the executor scope boundary (unrelated subsystem, possible parallel ownership).
- **Pre-existing, informational: `@sentry/nextjs` build notice** asks for an `onRouterTransitionStart` export in `instrumentation-client.ts`. `pnpm build` still exits 0. Pre-existing since Phase 1; logged to `deferred-items.md`.

## Manual-Verify (honest caveats)

- **Recharts renders a real emerald line in a browser** (not just a jsdom `path` element): jsdom does not paint SVG dimensions — `ResponsiveContainer` reports `-1×-1` (a benign console warning appears on one re-render in the toggle test). The smoke test asserts the **structural** presence of `path.recharts-line-curve` (the react-is sentinel); a human must confirm the **visual** emerald line by opening `/markets/{slug}` with ≥2 snapshots. (This is exactly the manual-verify item pre-listed in `09-VALIDATION.md`.)
- **Full MKT-04 browser round-trip** (admin odds edit / Polymarket poll → odds animate within 2s on the live page) requires the full stack (`bin/dev`) + a browser; the fake-timer hook test covers the state machine in isolation but not the end-to-end render. NOTE: the docker-compose `NEXT_PUBLIC_WS_URL: ws://backend:8000` mirrors `NEXT_PUBLIC_API_URL` — `backend` is an in-network host not resolvable from the host browser, identical to the existing `NEXT_PUBLIC_API_URL` caveat; the live round-trip is validated via `bin/dev`, not compose. The detail page itself (which composes these pieces) is Plan 09-04.

## User Setup Required

None — `NEXT_PUBLIC_WS_URL` ships with a working `ws://localhost:8000` dev default in `.env.example`; no external service configuration is required for this plan.

## Next Phase Readiness

- The reusable client layer for the market-detail page is ready: `PriceHistoryChart`, `useMarketSocket`, `LiveIndicator`, the typed fetchers, and the shadcn `dialog`/`select` primitives. **Plan 09-04** composes these into `/markets/[slug]` (Server Component shell + Suspense), builds the order-entry form + bet-confirm dialog (using the new primitives), and the recent-activity feed — fully satisfying MKT-03's player-facing surface.
- The react-is override also de-risks **Phase 10**'s Recharts KPI dashboard.
- Recommend the orphaned `middleware.test.ts → proxy` fix be picked up in a small dedicated change (tracked in `deferred-items.md`) so the repo-wide `pnpm typecheck`/`pnpm test` return green again.

## Self-Check: PASSED

- All 8 created files verified present on disk (3 chart/hook/test files, LiveIndicator, dialog, select, this SUMMARY).
- All 3 task commits verified in git history: `c366f1e` (Task 2), `1300ad4` (Task 3), `32c0bf8` (Task 4).

---
*Phase: 09-user-app-ux-polish-market-detail-real-time*
*Completed: 2026-05-29*
