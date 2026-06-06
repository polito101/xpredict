---
phase: LB-B-frontend-surface
plan: 02
type: execute
wave: 2
depends_on: ["LB-B-01"]
files_modified:
  - frontend/src/app/live/page.tsx
  - frontend/src/app/live/loading.tsx
  - frontend/src/app/live/live-table.tsx
autonomous: true
requirements: [SC1, SC3, D-2, D-3]
must_haves:
  truths:
    - "/live renders the XPredict chrome + the player's wallet balance and is gated to authenticated players"
    - "When no table is configured, /live shows a friendly 'No live table configured yet' empty state instead of erroring"
    - "The client component loads the widget via next/script and renders <live-bets-table> with session-token + table-id set via ref+setAttribute"
    - "All four widget DOM events are wired: bet-placed→recordLivePlaced, result→recordLiveSettled+toast, session-expired→re-mint, error→non-silent UI"
    - "Event listeners are removed on unmount"
  artifacts:
    - path: "frontend/src/app/live/page.tsx"
      provides: "Async Server Component: auth gate, session+table mint, wallet balance, empty state, chrome"
      min_lines: 60
    - path: "frontend/src/app/live/live-table.tsx"
      provides: "Client widget loader + DOM-event wiring + wallet refresh + cleanup"
      contains: "use client"
    - path: "frontend/src/app/live/loading.tsx"
      provides: "Route loading skeleton"
  key_links:
    - from: "frontend/src/app/live/page.tsx"
      to: "fetchLiveSession / wallet balance fetch"
      via: "server-side cookie-forwarded fetch"
      pattern: "fetchLiveSession|/wallet/me/balance"
    - from: "frontend/src/app/live/live-table.tsx"
      to: "recordLivePlaced / recordLiveSettled / mintLiveSession"
      via: "Server Action calls from DOM-event handlers"
      pattern: "recordLivePlaced|recordLiveSettled|mintLiveSession"
    - from: "frontend/src/app/live/live-table.tsx"
      to: "<live-bets-table> element"
      via: "ref + setAttribute for hyphenated attrs; addEventListener/removeEventListener"
      pattern: "setAttribute|addEventListener"
---

<objective>
Build the `/live` surface: an authenticated async Server Component that mints the live-bets session +
table and shows the player's XPredict wallet balance inside XPredict chrome (with a clean
"no table configured" empty state), plus the `"use client"` widget host that loads `widget.js` via
`next/script`, renders `<live-bets-table>`, and wires the four widget DOM events to the LB-B Server
Actions and a wallet refresh.

Purpose: Deliver the demo surface — the page a player opens to see the embedded live-bets table with
their unified XPredict balance reacting to bets.
Output: `page.tsx` (server), `loading.tsx` (skeleton), `live-table.tsx` (client).

Consumes the helpers/types/actions from LB-B-01. Does NOT touch `backend/`. Real end-to-end widget play
needs live-bets running (LB-C) — out of scope here; the wiring + states are what this plan proves.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/LB-B-frontend-surface/CONTEXT.md
@docs/superpowers/specs/2026-06-05-live-bets-integration-design.md
@.planning/phases/LB-B-frontend-surface/LB-B-01-SUMMARY.md

# The exact patterns to mirror (read the real shape, copy it — do NOT invent):
# Async Server Component shell: cookies() auth, parallel SSR fetch, Suspense, empty/not-found states:
@frontend/src/app/markets/[slug]/page.tsx
@frontend/src/app/portfolio/page.tsx
# The wallet-balance fetch + display (REUSE this exact mechanism: /wallet/me/balance returns {balance}):
@frontend/src/app/wallet/page.tsx
# Route loading skeleton shape:
@frontend/src/app/wallet/loading.tsx
# Toast usage (sonner is already wired in the root layout via <Toaster/>):
@frontend/src/components/admin/reverse-settlement-dialog.tsx
# Client effect + listener cleanup precedent:
@frontend/src/hooks/use-market-socket.test.ts
# The helpers/actions/types this plan consumes (from LB-B-01):
@frontend/src/lib/api.ts
@frontend/src/lib/live-actions.ts
</context>

<constraints>
- This is the EXECUTE plan. The executor's ONLY writes are the three files in `files_modified`. Do NOT
  modify any other `frontend/` file (the nav + helpers + env already landed in LB-B-01) or anything
  under `backend/`.
- pnpm: standalone `pnpm@9.15.0` ONLY. NEVER `corepack pnpm` (destructive 11.x). If not 9.15.x, STOP
  and report. `pnpm install --frozen-lockfile` (standalone) if `frontend/node_modules` is absent.
- Auth gate MUST mirror the existing player pages: derive the boolean from the HttpOnly
  `xpredict_session` cookie presence server-side; the cookie value never crosses into client JS.
- Money is a STRING on the wire (SP-1) — render the balance as the backend serialized it; never parse to
  a float.
- Stack note: this app is on Next 16 + React 19 (package.json), not Next 15 — React 19 renders custom
  elements and passes unknown props through, but HYPHENATED attributes (`session-token`, `table-id`) are
  set via `ref` + `setAttribute` to be robust (see Task 3). English copy/identifiers.
</constraints>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: /live Server Component — auth gate, session+table+balance, empty state, chrome</name>
  <files>frontend/src/app/live/page.tsx, frontend/src/app/live/loading.tsx</files>
  <behavior>
    `page.tsx` — async Server Component (mirror `markets/[slug]/page.tsx` + `portfolio/page.tsx`):
    - Read the `xpredict_session` cookie via `next/headers`. If absent → render the signed-out affordance
      (`SignedOutNotice resource="live"` — the same component the wallet/portfolio pages use) and STOP
      (SC1: reachable only when authenticated).
    - When authenticated, fetch IN PARALLEL (Promise.allSettled, SP-5): the live session
      (`fetchLiveSession(session)`) and the wallet balance (server-side `GET {BACKEND_URL}/wallet/me/balance`
      with the forwarded cookie — REUSE the exact mechanism in `wallet/page.tsx:62-90`; balance is a
      string).
    - If `fetchLiveSession` throws `LiveTableUnconfigured` (LB-A ships `LIVEBETS_DEFAULT_TABLE_ID=None`)
      → render the friendly empty state: heading "No live table configured yet" + a short explanatory
      line (a live table arrives in LB-C), STILL inside the normal chrome and STILL showing the wallet
      balance. This is the default LB-B demo state and must NOT look like an error (SC1, CONTEXT bullet 1).
    - On any other session/balance failure → a non-silent `RetryError` (mirror wallet/portfolio).
    - On success → render the page shell (mirror the `markets/[slug]` `PAGE_SHELL` container), a header
      with the wallet balance (a labelled element, e.g. `aria-label="wallet balance"`, mirroring
      `wallet/page.tsx`), and the `<LiveTable>` client component passing `sessionToken`, `tableId`, and
      the `initialBalance` string.
    `loading.tsx` — a route loading skeleton (clone `wallet/loading.tsx`'s structure).
  </behavior>
  <action>
    Create `frontend/src/app/live/page.tsx` and `frontend/src/app/live/loading.tsx`. Wrap the body in a
    `<Suspense fallback={<LiveSkeleton/>}>` async sub-component exactly like `markets/[slug]/page.tsx`.
    Reuse `getBackendUrl()` inline (server-only) for the balance fetch and the LB-B-01 `fetchLiveSession`
    for the session; both forward `Cookie: xpredict_session=${session}`. Resolve the `tableId` from the
    session flow: `fetchLiveSession` returns the token; for the `table-id` attribute, call
    `fetchLiveTables(session)` and use the first table's `table_id` (the demo runs one table — design §9),
    OR, if you prefer a single round-trip, read it from whatever `SessionResponse`/tables expose — verify
    against `backend/app/integrations/livebets/schemas.py` and do NOT hardcode a UUID. If no table is
    configured, `fetchLiveSession` raises `LiveTableUnconfigured` BEFORE you need a table id, so the empty
    state needs no table. Use `SignedOutNotice`, `RetryError`, and the `Card`/shell primitives already in
    the repo; do NOT introduce new UI deps. Keep all money as strings. Note in a comment that the widget
    interior is the widget's own (partially brandable) styling while the XPredict chrome around it is
    on-brand (CONTEXT brand white-label note).
  </action>
  <verify>
    <automated>cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src/app/live</automated>
  </verify>
  <done>
    `/live` renders chrome + wallet balance for an authed player, the signed-out notice when no session,
    the "No live table configured yet" empty state on `LiveTableUnconfigured`, and a RetryError on other
    failures; `loading.tsx` exists; typecheck + lint clean.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: live-table.tsx — widget script load + custom element render (ref + setAttribute)</name>
  <files>frontend/src/app/live/live-table.tsx</files>
  <behavior>
    A `"use client"` component `LiveTable({ sessionToken, tableId, initialBalance })`:
    - Loads the widget script via `next/script` with `src={process.env.NEXT_PUBLIC_LIVEBETS_WIDGET_SRC}`
      and `strategy="afterInteractive"` (a third-party interactive widget; no SRI in dev — design §4).
      If the env var is unset, render a non-blocking notice ("Live widget not configured") instead of an
      empty `<script src="undefined">`.
    - Renders `<live-bets-table>` through a `ref` (a `useRef<HTMLElement>`). In a `useEffect`, set the
      hyphenated attributes on the element via `setAttribute("session-token", sessionToken)` and
      `setAttribute("table-id", tableId)` (React 19 passes props to custom elements, but `setAttribute`
      is the robust path for hyphenated names and lets the session-expired handler in Task 3 re-set the
      token imperatively).
    - Holds the current balance in `useState(initialBalance)` and renders it (a labelled element) so
      Task 3's wallet refresh can update it in place. (Task 3 adds the event wiring + the refresh.)
    - TypeScript: declare the custom element in JSX without `any` — add a minimal module augmentation for
      `JSX.IntrinsicElements["live-bets-table"]` (a `React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>`)
      local to this file (or a colocated `.d.ts`), so `<live-bets-table>` typechecks.
  </behavior>
  <action>
    Create `frontend/src/app/live/live-table.tsx` starting with `"use client"`. Import `Script` from
    `next/script`. Use `useRef`, `useEffect`, `useState` from React. Set `session-token` / `table-id` via
    `setAttribute` in an effect keyed on `[sessionToken, tableId]`. Add the `JSX.IntrinsicElements`
    augmentation so the element typechecks without `any` (confirm the exact React 19 typing shape against
    the installed `@types/react` — do NOT guess the namespace; if `React.JSX` is required over the global
    `JSX`, use that). Render the wallet-balance display reusing the same `aria-label="wallet balance"`
    convention as `wallet/page.tsx` so the page and the client agree. Do NOT wire the DOM events yet — that
    is Task 3 (kept separate so the event-wiring diff is reviewable on its own). Add a house-style JSDoc
    block citing design §4 (widget served locally) and §5 (the element contract).
  </action>
  <verify>
    <automated>cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src/app/live/live-table.tsx</automated>
  </verify>
  <done>
    `LiveTable` loads the widget via `next/script`, renders `<live-bets-table>` with `session-token` +
    `table-id` set via `setAttribute`, shows the balance from `initialBalance`, and typechecks with no
    `any` for the custom element; lint clean.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Wire the four widget DOM events to the backend + wallet refresh, with cleanup</name>
  <files>frontend/src/app/live/live-table.tsx</files>
  <behavior>
    Extend `LiveTable` with a `useEffect` that `addEventListener`s on the `<live-bets-table>` element for
    the four widget events and wires each to the LB-B-01 Server Actions + a wallet-balance refresh, then
    REMOVES every listener in the effect cleanup (design §5/§6, SC3):
    - `live-bets-bet-placed` `{ bet_id }` → `await recordLivePlaced(bet_id)` → on `{ok:true}` refresh the
      balance; on `{ok:false}` surface a non-silent error (toast). A `bet_id` missing from the event
      detail is ignored defensively (no call).
    - `live-bets-result` `{ bet_id, status, payout }` → `await recordLiveSettled(bet_id)` → refresh the
      balance + a non-silent WON/LOST toast (`sonner` `toast`, already wired in the root layout).
    - `live-bets-session-expired` → `await mintLiveSession(tableId)` → on success
      `element.setAttribute("session-token", newToken)` (and update local state if held); on failure a
      non-silent error toast.
    - `live-bets-error` `{ message? }` → a non-silent error toast / inline `role="alert"` (mirror the
      project's error pattern; never swallow it).
    The wallet refresh re-reads the balance after placed/settled and updates the displayed value in place
    (so the unified XPredict balance visibly moves — the whole point of the demo, design §8).
  </behavior>
  <action>
    Add the event-wiring `useEffect` to `live-table.tsx`. Read `bet_id` / `status` / `payout` / `message`
    from `(e as CustomEvent).detail` with defensive typing (the widget is third-party). Import
    `recordLivePlaced`, `recordLiveSettled`, `mintLiveSession` from `@/lib/live-actions` and `toast` from
    `sonner`. For the wallet refresh, add a small refresh function: the cleanest XPredict-idiomatic option
    is `router.refresh()` (from `next/navigation`) to re-run the Server Component balance fetch — confirm
    that updates the header balance; if the balance must update inside the client island specifically,
    instead expose a tiny `getLiveBalance` read (server action returning the current balance) and set
    local state. Pick ONE and note the choice in a comment — do NOT leave a stale balance. Ensure the
    effect's cleanup calls `removeEventListener` for ALL four events (store the handler refs); guard the
    effect on the element ref being present. Keep handlers idempotent-friendly: `applied:false` from a
    Server Action is a no-op success (a duplicate event), NOT an error toast (design §8 idempotency).
  </action>
  <verify>
    <automated>cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src/app/live/live-table.tsx</automated>
  </verify>
  <done>
    All four DOM events are wired to the correct Server Action + a wallet refresh + non-silent
    result/error UI, session-expired re-mints and re-sets `session-token`, and the effect cleanup removes
    every listener; typecheck + lint clean. (Behavioral assertions land in LB-B-03's hermetic tests.)
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| third-party widget → XPredict page | The widget (live-bets origin) dispatches DOM events carrying `bet_id`/`status`/`payout`. These are UNTRUSTED client input. |
| browser → Next server (Server Action) | The only authed path to mirror money; HttpOnly cookie read server-side, never in client JS. |
| Next server → XPredict backend | Cookie-forwarded; LB-A re-verifies every bet against live-bets before any ledger move. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-LBB-04 | Tampering | DOM-event detail (`bet_id`, `payout`) | mitigate | The handler passes only `bet_id` to the Server Action; LB-A re-reads status/stake/payout from live-bets (`GET /v2/bets/{id}`) and is authoritative — a tampered `payout` in the event is ignored (design §8). Missing `bet_id` → no call. |
| T-LBB-05 | Repudiation / double-post | duplicate placed/settled events | accept (handled upstream) | LB-A transfers are idempotent by `livebets:{bet_id}:...` keys; `applied:false` is a benign no-op, not an error. The client treats it as success (design §8). |
| T-LBB-06 | Information disclosure | session token in the DOM | accept | The live-bets `session-token` is a short-lived per-player JWT intended to be set on the widget element (design §5/§7); it is NOT the XPredict session cookie (which stays HttpOnly and server-side). Re-mint on expiry. |
| T-LBB-07 | Denial of service | widget script load failure | mitigate | `next/script` `afterInteractive`; if `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` is unset, render a notice instead of a broken `<script>`; a `live-bets-error` event surfaces non-silently. |
</threat_model>

<verification>
- `cd frontend && pnpm exec tsc --noEmit` — clean (custom element typed without `any`).
- `cd frontend && pnpm exec eslint src/app/live` — clean.
- Manual reasoning trace (no live-bets needed): each of the four events maps to the right action +
  refresh + UI, and cleanup removes every listener (proved hermetically in LB-B-03).
- No diff under `backend/`; no `frontend/` file changed outside `files_modified`.
</verification>

<success_criteria>
- `/live` renders under the player app with XPredict chrome + the player's wallet balance, is gated to
  authenticated players, and shows the "No live table configured yet" empty state when no table is
  configured (SC1).
- The client component loads `widget.js` via `next/script`, renders `<live-bets-table>` with
  `session-token` + `table-id` from the backend, wires all four DOM events to placed/settled/re-mint/error
  + wallet refresh, and cleans up listeners on unmount (SC3, D-2, D-3).
- Typecheck + lint clean; `backend/` untouched.
</success_criteria>

<output>
Create `.planning/phases/LB-B-frontend-surface/LB-B-02-SUMMARY.md` when done.
</output>
