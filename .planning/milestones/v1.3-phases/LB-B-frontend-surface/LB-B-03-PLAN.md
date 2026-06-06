---
phase: LB-B-frontend-surface
plan: 03
type: tdd
wave: 3
depends_on: ["LB-B-01", "LB-B-02"]
files_modified:
  - frontend/src/components/player-nav.test.tsx
  - frontend/src/app/live/__tests__/live-page.test.tsx
  - frontend/src/app/live/__tests__/live-table.test.tsx
autonomous: true
requirements: [SC1, SC2, SC3, SC5]
must_haves:
  truths:
    - "A hermetic test asserts the 'Live' nav entry renders and links to /live"
    - "A hermetic test asserts /live shows the 'No live table configured yet' empty state when the session helper signals no table"
    - "A hermetic test asserts /live shows the signed-out notice with no session and the wallet balance on the happy path"
    - "Hermetic tests assert each of the four widget DOM events calls the correct Server Action and triggers a wallet refresh, with mocked widget + mocked actions"
    - "cd frontend && pnpm vitest run is green (new + existing tests); no real widget/network"
  artifacts:
    - path: "frontend/src/app/live/__tests__/live-page.test.tsx"
      provides: "Server Component tests: signed-out, empty state, happy-path balance"
      contains: "vi.mock"
    - path: "frontend/src/app/live/__tests__/live-table.test.tsx"
      provides: "Client component tests: 4 DOM events → actions + refresh; cleanup"
      contains: "dispatchEvent"
  key_links:
    - from: "live-table.test.tsx"
      to: "recordLivePlaced / recordLiveSettled / mintLiveSession"
      via: "vi.mock of @/lib/live-actions asserting calls per dispatched event"
      pattern: "recordLivePlaced|recordLiveSettled|mintLiveSession"
    - from: "live-page.test.tsx"
      to: "fetchLiveSession / LiveTableUnconfigured"
      via: "vi.mock of @/lib/api + next/headers cookies"
      pattern: "LiveTableUnconfigured|fetchLiveSession"
---

<objective>
Prove the LB-B surface behaves correctly WITHOUT a real widget, live-bets, or network: hermetic Vitest
tests for the "Live" nav entry, the `/live` Server Component states (signed-out / empty / happy), and the
client widget's four DOM-event → Server-Action + wallet-refresh wiring with cleanup.

Purpose: Lock SC5 (green `pnpm vitest run`) and regression-guard the event wiring that the LB-C manual
demo depends on.
Output: extended `player-nav.test.tsx` + two new test files under `src/app/live/__tests__/`.

TDD plan: write the assertions first against the LB-B-01/02 contracts, then adjust mocks until green.
This plan adds ONLY test files. If a test reveals a real bug in the page/client, STOP and report — do not
fix production code from this plan (that is a gap-closure plan).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/LB-B-frontend-surface/CONTEXT.md
@.planning/phases/LB-B-frontend-surface/LB-B-01-SUMMARY.md
@.planning/phases/LB-B-frontend-surface/LB-B-02-SUMMARY.md

# The exact test patterns to mirror (copy the mocking style, do NOT invent):
# Async Server Component test: hoisted next/headers cookies() + stubbed global fetch, await the component:
@frontend/src/app/wallet/__tests__/wallet-page.test.tsx
# Server-Action test: hoisted next/headers + global fetch spy asserting URL/method:
@frontend/src/lib/__tests__/admin-api.test.ts
# Nav render test to extend (mocks next/link + next/navigation + the logout action):
@frontend/src/components/player-nav.test.tsx
# Client effect + stubbed event-source + fake timers precedent:
@frontend/src/hooks/use-market-socket.test.ts
# The vitest env routing (.test.tsx → jsdom, .test.ts → node) + setup:
@frontend/vitest.config.ts
@frontend/vitest.setup.ts
# The units under test (read their final shapes from the LB-B-01/02 source):
@frontend/src/app/live/page.tsx
@frontend/src/app/live/live-table.tsx
@frontend/src/lib/live-actions.ts
@frontend/src/lib/api.ts
</context>

<constraints>
- This plan adds ONLY the three test files in `files_modified`. Do NOT modify any production source. If a
  test fails because of a real defect in `page.tsx` / `live-table.tsx` / `live-actions.ts`, STOP and
  report it as a gap — do not patch production code here.
- pnpm: standalone `pnpm@9.15.0` ONLY. NEVER `corepack pnpm` (destructive 11.x). If not 9.15.x, STOP and
  report. Run `pnpm install --frozen-lockfile` (standalone) first if `frontend/node_modules` is absent.
- Tests MUST be hermetic: mock `@/lib/live-actions`, mock `@/lib/api` (or stub global `fetch`), mock
  `next/script` (render nothing or a stub), and mock `next/navigation` / `next/headers` — NO real widget,
  NO live-bets, NO network. Name files `*.test.tsx` so they run under `jsdom` (per `vitest.config.ts`).
- The test command of record is `cd frontend && pnpm vitest run` (CONTEXT SC5). English copy/identifiers.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Nav test — assert the "Live" entry renders and links to /live</name>
  <files>frontend/src/components/player-nav.test.tsx</files>
  <behavior>
    - Test: `renders the Live destination` — `render(<PlayerNav isAuthenticated={false} />)`,
      `expect(screen.getByText("Live")).toBeInTheDocument()` and
      `expect(screen.getByText("Live").closest("a")).toHaveAttribute("href", "/live")`.
    - Keep the existing four tests passing unchanged (extend, do not rewrite).
  </behavior>
  <action>
    Add one `test(...)` to the existing `describe("<PlayerNav />")` block in `player-nav.test.tsx`,
    reusing the file's existing `next/link` + `next/navigation` + `@/lib/auth` mocks. Do not alter the
    existing cases.
  </action>
  <verify>
    <automated>cd frontend && pnpm vitest run src/components/player-nav.test.tsx</automated>
  </verify>
  <done>The nav test file asserts a "Live" link to `/live` and the whole file passes.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: /live Server Component tests — signed-out, empty state, happy-path balance</name>
  <files>frontend/src/app/live/__tests__/live-page.test.tsx</files>
  <behavior>
    Mirror `wallet-page.test.tsx` (hoisted `next/headers` cookies mock; mock `next/navigation` for the
    client error/notice islands; mock `@/lib/api` so the session helper is controllable). Await the async
    Server Component and assert on the rendered DOM:
    - `prompts sign-in with no session` — `cookieGet` returns undefined → the signed-out notice renders,
      no wallet balance, and `fetchLiveSession` is NOT called.
    - `shows the empty state when no table is configured` — cookie present; `fetchLiveSession` rejects
      with `LiveTableUnconfigured`; balance fetch stubbed ok → the page shows "No live table configured
      yet" (NOT an error/alert) AND still shows the wallet balance.
    - `shows chrome + wallet balance on the happy path` — cookie present; `fetchLiveSession` resolves
      `{session_token, expires_at}`; `fetchLiveTables` resolves one table; balance fetch returns
      `{balance:"100.0000"}` → the labelled wallet balance shows `100.0000` and the `<live-bets-table>`
      host (or the LiveTable island) renders. Mock the `LiveTable` client child to a stub so this test
      stays a pure page-state test.
    - (Optional) `shows a retry error on a non-unconfigured failure` — `fetchLiveSession` rejects with a
      generic Error → a `role="alert"` retry surface renders.
  </behavior>
  <action>
    Create `frontend/src/app/live/__tests__/live-page.test.tsx`. Use `vi.hoisted` for the `cookieGet`
    mock and `vi.mock("next/headers", ...)` exactly like `wallet-page.test.tsx`. `vi.mock("@/lib/api")`
    to expose a controllable `fetchLiveSession` / `fetchLiveTables` and the real `LiveTableUnconfigured`
    class (re-export the actual class via `importActual` so `instanceof` checks in the page hold).
    `vi.mock("@/app/live/live-table", ...)` (or the correct relative path) to stub `LiveTable` to a
    simple marker so the test asserts page composition, not widget internals. Stub global `fetch` for the
    `/wallet/me/balance` call (mirror `wallet-page.test.tsx`'s `vi.stubGlobal("fetch", ...)`). Reset mocks
    in `beforeEach`. Assert text via the exact copy the page renders (read it from `page.tsx`).
  </action>
  <verify>
    <automated>cd frontend && pnpm vitest run src/app/live/__tests__/live-page.test.tsx</automated>
  </verify>
  <done>
    The page test asserts signed-out, empty-state (no error + balance shown), and happy-path (balance +
    LiveTable host) states hermetically; the file passes.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: live-table client tests — 4 DOM events → actions + wallet refresh, with cleanup</name>
  <files>frontend/src/app/live/__tests__/live-table.test.tsx</files>
  <behavior>
    Render `<LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />` under jsdom with
    `@/lib/live-actions`, `next/script`, and `next/navigation` mocked, then drive the real
    `<live-bets-table>` element and assert wiring:
    - `mounts the widget host with session-token + table-id` — query the `live-bets-table` element and
      assert `getAttribute("session-token")==="t"` and `getAttribute("table-id")==="tbl"`.
    - `bet-placed → recordLivePlaced + refresh` — dispatch
      `new CustomEvent("live-bets-bet-placed", { detail: { bet_id: "B1" } })` on the element →
      `expect(recordLivePlaced).toHaveBeenCalledWith("B1")` and the wallet-refresh mock fired (e.g.
      `router.refresh` called, OR the balance-read action called — whichever LB-B-02 chose; read the
      source to know which to assert).
    - `result → recordLiveSettled + refresh + toast` — dispatch
      `live-bets-result {bet_id:"B2", status:"WON", payout:"50"}` →
      `expect(recordLiveSettled).toHaveBeenCalledWith("B2")`, refresh fired, and the `sonner` `toast`
      mock called (WON copy).
    - `session-expired → mintLiveSession + new token` — `mintLiveSession` mock resolves
      `{ok:true, session_token:"t2", ...}`; dispatch `live-bets-session-expired` →
      `expect(mintLiveSession).toHaveBeenCalled()` and the element's `session-token` becomes `"t2"`
      (await a microtask/flush).
    - `error → non-silent UI` — dispatch `live-bets-error {message:"boom"}` → the `toast` mock (or a
      `role="alert"`) shows it; nothing is swallowed.
    - `removes listeners on unmount` — after `unmount()`, dispatching `live-bets-bet-placed` again does
      NOT call `recordLivePlaced` a second time (proves cleanup, SC3).
    - `applied:false is a no-op success` — `recordLivePlaced` resolves `{ok:true, applied:false}` → no
      error toast (duplicate-event idempotency, design §8).
  </behavior>
  <action>
    Create `frontend/src/app/live/__tests__/live-table.test.tsx`. `vi.mock("@/lib/live-actions")` with
    `vi.fn()`s for `recordLivePlaced` / `recordLiveSettled` / `mintLiveSession` (set resolved values per
    case). `vi.mock("next/script", () => ({ default: () => null }))` so no real script loads.
    `vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }))` — and capture the
    refresh mock if the component uses `router.refresh()` for the wallet refresh; if LB-B-02 instead used
    a balance-read Server Action, mock that and assert it. Set
    `process.env.NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` to a dummy value in `beforeEach`. Query the custom
    element with `container.querySelector("live-bets-table")` and dispatch `CustomEvent`s on it; wrap
    dispatch + awaits in `await act(async () => {...})` so React state updates and async handlers flush
    (mirror the `act`/`renderHook` usage in `use-market-socket.test.ts`). For the unmount case, keep a
    handle from `render()` and call `unmount()` before re-dispatching. Assert the four happy mappings, the
    cleanup, and the `applied:false` no-op. Read `live-table.tsx` to use the exact event names, detail
    keys, and refresh mechanism — do NOT assume; match the source.
  </action>
  <verify>
    <automated>cd frontend && pnpm vitest run src/app/live/__tests__/live-table.test.tsx</automated>
  </verify>
  <done>
    The client test asserts the host attributes, all four event→action+refresh+UI mappings, the
    `applied:false` no-op, and listener cleanup on unmount — fully hermetic; the file passes.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| test harness → units | Tests exercise the units in isolation with all I/O (widget, actions, fetch, router) mocked; no trust boundary is crossed at runtime. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-LBB-08 | Tampering (test integrity) | hermetic isolation | mitigate | `next/script`, `@/lib/live-actions`, `@/lib/api`, `next/headers`, `next/navigation` are all mocked; global `fetch` stubbed. A leak (real network/widget) fails CI rather than passing silently — the page/client tests assert mocks were/were not called. |
</threat_model>

<verification>
- `cd frontend && pnpm vitest run` — GREEN for the new files AND the pre-existing suite (SC5).
- `cd frontend && pnpm exec tsc --noEmit` — clean (test files included).
- No production source modified; only the three test files changed.
</verification>

<success_criteria>
- The "Live" nav entry, the `/live` Server Component states (signed-out / empty / happy), and the four
  widget DOM-event → Server-Action + wallet-refresh mappings + listener cleanup are all proved by
  hermetic tests (SC1, SC2, SC3).
- `cd frontend && pnpm vitest run` is green, including existing tests; `pnpm exec tsc --noEmit` clean
  (SC5). No real widget / live-bets / network touched.
</success_criteria>

<output>
Create `.planning/phases/LB-B-frontend-surface/LB-B-03-SUMMARY.md` when done.
</output>
