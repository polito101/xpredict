---
phase: LB-B-frontend-surface
plan: 03
subsystem: testing
tags: [vitest, testing-library, react, next, server-actions, live-bets, jsdom, node]

# Dependency graph
requires:
  - phase: LB-B-01
    provides: Live nav entry, live-bets Server Actions (live-actions.ts), api.ts live helpers + LiveTableUnconfigured
  - phase: LB-B-02
    provides: /live Server Component (page.tsx) + <LiveTable> client island (DOM-event wiring, in-island balance)
provides:
  - Hermetic Vitest coverage for the LB-B surface (nav, /live page states, client event wiring)
  - Direct Server Action contract tests for the live-bets money path (plan-check M-1)
  - Regression guard for the four widget DOM-event -> Server-Action + wallet-refresh mappings (SC3, M-2)
affects: [LB-C, live-bets, frontend-testing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Async Server Component test without Suspense-fallback deadlock: invoke the Suspense child (async LiveBody) directly and render its resolved tree — mirrors render(await Component()) when the default export wraps the body in <Suspense>"
    - "Custom-element DOM-event wiring test: dispatch CustomEvent on the real <live-bets-table> host inside act(), flushing the handler's void-async chain with two microtask turns"
    - "Stable hoisted action mocks (one fn per action, not fresh vi.fn() per render) so getLiveBalance refresh calls are assertable (M-2)"

key-files:
  created:
    - frontend/src/app/live/__tests__/live-page.test.tsx
    - frontend/src/app/live/__tests__/live-table.test.tsx
    - frontend/src/lib/__tests__/live-actions.test.ts
  modified:
    - frontend/src/components/player-nav.test.tsx

key-decisions:
  - "Mirrored the existing admin-api.test.ts / auth.test.ts Server-Action pattern for M-1 (NOT a non-existent file); admin-api.test.ts does exist and is the canonical hoisted-cookies + fetch-spy pattern"
  - "Rendered the async LiveBody (the Suspense child) directly rather than the <Suspense> wrapper, because React's jsdom client renderer never resolves an async Server Component inside Suspense (it renders the fallback forever) — no source change needed (LiveBody stays unexported)"
  - "Used the real LiveTableUnconfigured via importActual so the page's `reason instanceof LiveTableUnconfigured` branch is exercised, not stubbed away"

patterns-established:
  - "Server Component state tests await the async body element's resolved tree"
  - "Client custom-element tests drive real CustomEvents under act() with microtask flushing"

requirements-completed: [SC1, SC2, SC3, SC5]

# Metrics
duration: 7min
completed: 2026-06-06
---

# Phase LB-B Plan 03: Frontend Surface Tests Summary

**Hermetic Vitest coverage for the LB-B live surface — the Live nav entry, the `/live` Server Component states (signed-out / empty / happy / error), the client island's four DOM-event -> Server-Action + in-island wallet-refresh mappings with listener cleanup, plus direct contract tests for the live-bets money-path Server Actions (M-1).**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-06T08:02:50Z
- **Completed:** 2026-06-06T08:09:34Z
- **Tasks:** 3 plan tasks + 1 plan-check MEDIUM (M-1)
- **Files modified:** 4 (1 extended, 3 created — all tests)

## Accomplishments
- Locked SC5: `cd frontend && pnpm vitest run` is green for the new suite AND the whole frontend suite (32 files / 186 tests, up from 29 / 152 — +34 tests, no regression).
- Proved the four widget DOM-event mappings (`live-bets-bet-placed`/`-result`/`-session-expired`/`-error`) each call the correct Server Action, refresh the in-island balance via `getLiveBalance` (M-2), surface toasts, treat `applied:false` as a benign no-op, and remove listeners on unmount (SC3).
- Added the previously-missing direct tests for the only authed live-bets money path (`recordLivePlaced`/`recordLiveSettled`/`mintLiveSession`/`getLiveBalance`) — cookie forwarding, URL/method, and full status mapping (M-1).
- Covered the `/live` page states hermetically including the default LB-B "No live table configured yet" empty state (must not look like an error) and the signed-out short-circuit (no session/balance reads fire).

## Task Commits

Each task was committed atomically on `gsd/livebets-demo`:

1. **Task 1: Nav test — Live entry links to /live** — `abfab2e` (test)
2. **Task 2: /live Server Component state tests** — `2214d25` (test)
3. **Task 3: live-table client DOM-event wiring tests** — `2e31483` (test)
4. **Plan-check M-1: live-actions Server Action contract tests** — `b9b3a7b` (test)

_All TDD: assertions written against the LB-B-01/02 contracts, then mocks adjusted to green. No production source changed._

## Files Created/Modified
- `frontend/src/components/player-nav.test.tsx` — extended the existing `<PlayerNav />` describe block with one case asserting the "Live" entry renders and links to `/live` (existing four cases untouched).
- `frontend/src/app/live/__tests__/live-page.test.tsx` — Server Component tests: signed-out notice (no balance, no session/balance reads), real-`LiveTableUnconfigured` empty state (friendly copy, NO `role=alert`, balance shown, island absent), happy path (stubbed island receives resolved token/table/balance), generic failure -> `role=alert` retry.
- `frontend/src/app/live/__tests__/live-table.test.tsx` — client island tests: host attributes; `bet-placed` -> `recordLivePlaced` + `getLiveBalance` refresh moving the balance 100.0000 -> 150.0000; `result(WON)` -> `recordLiveSettled` + refresh + WON toast; `session-expired` -> `mintLiveSession(tableId)` + new `session-token`; `error` -> non-silent `toast.error(message)`; `applied:false` no-op; listener cleanup on unmount.
- `frontend/src/lib/__tests__/live-actions.test.ts` — direct Server Action tests (node env): cookie-forwarded URL/method for all four actions, betId url-encoding, `mintLiveSession` body shaping (`{}` vs `{table_id}`), the SP-1 string-balance contract, and the 200/401/404/409/error + no-cookie status mappings.

## Decisions Made
- **M-1 mirror source:** Used the established `admin-api.test.ts` / `auth.test.ts` hoisted-cookies + `vi.spyOn(globalThis, "fetch")` pattern (the repo's canonical Server-Action test shape). The plan-check note called `admin-api.test.ts` "non-existent" — it actually exists and is the right mirror; followed the authoritative intent (mirror the existing Server-Action test pattern, not invent one).
- **Async page rendering:** The `/live` default export wraps the async `LiveBody` in `<Suspense>`. React's jsdom client renderer renders the Suspense fallback forever for an async Server Component, so the test reaches the Suspense child element, invokes it to resolve its promise, and renders the resolved tree — the same "await the async server component" idea as `render(await WalletPage())`, with zero source changes (`LiveBody` stays unexported).
- **Real error class:** `@/lib/api` is mocked with `importActual` so the genuine `LiveTableUnconfigured` flows through and the page's `instanceof` branch is genuinely exercised.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Async-Server-Component render strategy adjusted to avoid a Suspense-fallback deadlock**
- **Found during:** Task 2 (/live page tests)
- **Issue:** The plan/wallet pattern is `render(await Component())`, but `/live`'s default export returns `<Suspense><LiveBody/></Suspense>` (the async work is in the non-exported `LiveBody`). Rendering the page element directly leaves the jsdom renderer stuck on the `LiveSkeleton` fallback — all four page tests failed (timeout on `findBy*`).
- **Fix:** Added a `renderLive()` helper that reaches the Suspense child (`LivePage().props.children`), invokes its async `type()` to resolve, and renders the resolved tree — exactly the wallet "await the async component" semantics, no source change.
- **Files modified:** frontend/src/app/live/__tests__/live-page.test.tsx (test only)
- **Verification:** All 4 page tests green; the empty-state test confirms the real `LiveTableUnconfigured instanceof` branch fires.
- **Committed in:** `2214d25` (Task 2 commit)

**2. [Rule 3 - Blocking] Typed the hoisted cookie getter to allow `undefined`**
- **Found during:** M-1 (live-actions tests) — surfaced by `pnpm exec tsc --noEmit`
- **Issue:** The default `vi.fn(() => ({value}))` narrowed the getter's return type, so the no-session cases `mockReturnValue(undefined)` failed typecheck (TS2345).
- **Fix:** Gave the mock an explicit `(name) => { value: string } | undefined` signature in the `vi.hoisted` factory.
- **Files modified:** frontend/src/lib/__tests__/live-actions.test.ts (test only)
- **Verification:** `pnpm exec tsc --noEmit` exit 0; the 22 M-1 tests stay green.
- **Committed in:** `b9b3a7b` (M-1 commit)

---

**Total deviations:** 2 (both Rule 3 — blocking, test-only, no production change).
**Impact on plan:** No scope creep. Both were mechanical test-harness fixes required to make the planned assertions run; the assertions themselves are unchanged from the plan's intent. No assertion was loosened, skipped, or xfail'd.

## Issues Encountered
- None beyond the two test-harness blockers above. **No test exposed a real bug in the wave-1/2 source** — `page.tsx`, `live-table.tsx`, `live-actions.ts`, and `api.ts` all behaved exactly as their LB-B-01/02 contracts specify (cookie forwarding, status mapping, `applied:false` no-op, `getLiveBalance` in-island refresh, listener cleanup). No production source was modified.

## Plan-check coverage confirmation
- **M-1 (live-actions.test.ts, node env):** COVERED — all four actions assert the forwarded `Cookie: xpredict_session=...` header to the correct backend URL/method, and the 200 -> parsed/`applied` · 401 · 404 · 409 · other -> error mapping (plus no-cookie short-circuit and the SP-1 string-balance contract).
- **M-2 (wallet-refresh assertion):** COVERED — `live-table.test.tsx` uses a single stable hoisted `getLiveBalance` mock and asserts that after `live-bets-bet-placed` / `live-bets-result` it is called once AND the in-island balance text updates (100.0000 -> 150.0000).

## Verification (actual output)
- `cd frontend && pnpm vitest run` → **32 test files passed, 186 tests passed** (baseline was 29 / 152; this plan adds 3 files and +34 tests). New files: `player-nav.test.tsx` (5), `live-page.test.tsx` (4), `live-table.test.tsx` (7), `live-actions.test.ts` (22).
- `cd frontend && pnpm exec tsc --noEmit` → **exit 0 (clean)**, test files included.
- `pnpm --version` → **9.15.0** (standalone, never corepack).
- Hermetic: `@/lib/live-actions`, `@/lib/api`, `next/script`, `next/navigation`, `next/headers`, `sonner` all mocked; global `fetch` stubbed. No real widget / live-bets / network touched.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- SC5 locked: the LB-B surface is regression-guarded ahead of the LB-C manual demo (which depends on the event wiring proved here).
- No blockers. Branch `gsd/livebets-demo`; no push/PR per the run constraints.

## Self-Check: PASSED

- `frontend/src/components/player-nav.test.tsx` — FOUND (modified)
- `frontend/src/app/live/__tests__/live-page.test.tsx` — FOUND (created)
- `frontend/src/app/live/__tests__/live-table.test.tsx` — FOUND (created)
- `frontend/src/lib/__tests__/live-actions.test.ts` — FOUND (created)
- Commit `abfab2e` (Task 1) — FOUND
- Commit `2214d25` (Task 2) — FOUND
- Commit `2e31483` (Task 3) — FOUND
- Commit `b9b3a7b` (M-1) — FOUND

---
*Phase: LB-B-frontend-surface*
*Completed: 2026-06-06*
