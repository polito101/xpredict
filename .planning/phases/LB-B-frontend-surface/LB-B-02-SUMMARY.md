---
phase: LB-B-frontend-surface
plan: 02
subsystem: frontend
tags: [livebets, server-component, client-island, custom-element, dom-events, wallet-refresh]
requires:
  - "LB-B-01: fetchLiveSession / fetchLiveTables / LiveTableUnconfigured (api.ts)"
  - "LB-B-01: recordLivePlaced / recordLiveSettled / mintLiveSession (live-actions.ts)"
provides:
  - "/live route: authed async Server Component (session+table+balance, empty state, chrome)"
  - "live/loading.tsx route skeleton"
  - "live/live-table.tsx client island: widget script load + <live-bets-table> + 4 DOM events + in-island wallet refresh"
  - "live-actions.ts: getLiveBalance Server Action (M-2 in-island balance refresh)"
affects:
  - "LB-B-03 (hermetic component tests target this island's event wiring + empty state + nav)"
  - "LB-C (provides the running widget + table id this surface consumes)"
tech-stack:
  added: []
  patterns:
    - "React 19 custom element: declare module 'react' { namespace JSX { interface IntrinsicElements } } (NOT a global JSX namespace) + ref+setAttribute for hyphenated attrs"
    - "next/script strategy=afterInteractive for the third-party widget; notice fallback when src unset"
    - "addEventListener/removeEventListener for all listeners in one effect with full cleanup"
    - "in-island wallet refresh via a getLiveBalance Server Action + setState (NOT router.refresh)"
key-files:
  created:
    - frontend/src/app/live/page.tsx
    - frontend/src/app/live/loading.tsx
    - frontend/src/app/live/live-table.tsx
  modified:
    - frontend/src/lib/live-actions.ts
decisions:
  - "JSX-namespace: augment React.JSX.IntrinsicElements via `declare module 'react' { namespace JSX }` (verified vs @types/react 19.2.15 where JSX is NOT global); scoped eslint-disable for no-namespace (module augmentation requires a namespace)"
  - "M-2 wallet refresh: getLiveBalance Server Action updates the island's useState balance; router.refresh() would leave the client island's copy stale"
  - "table-id resolved from fetchLiveTables()[0] (SessionResponse carries no table_id); empty/unreachable catalog falls back to the friendly empty state"
  - "untrusted widget event detail: only bet_id passed to the backend (LB-A re-verifies); missing bet_id is a no-op; applied:false is a benign no-op, not an error toast"
metrics:
  duration: "~20 min"
  completed: 2026-06-06
  tasks: 3
  files: 4
---

# Phase LB-B Plan 02: /live surface Summary

The `/live` player surface: an authed async Server Component that mints the live-bets session, resolves the demo table, and shows the XPredict wallet balance inside XPredict chrome (with a clean "No live table configured yet" empty state), plus the `"use client"` widget host that loads `widget.js` via `next/script`, renders `<live-bets-table>` (ref + setAttribute), wires all four widget DOM events to the LB-B-01 Server Actions, and refreshes the in-island wallet balance so it visibly moves after a settle.

## What was built

- **`page.tsx` + `loading.tsx` (Task 1)** — Async Server Component mirroring `markets/[slug]/page.tsx` + `wallet/page.tsx`. Gates on the `xpredict_session` cookie (`SignedOutNotice resource="live"` when absent). On an authed player it mints the live session (`fetchLiveSession`) and reads the wallet balance (`GET /wallet/me/balance`, reusing the exact `wallet/page.tsx` mechanism) IN PARALLEL via `Promise.allSettled` (SP-5). `LiveTableUnconfigured` → the friendly "No live table configured yet" empty state, still inside chrome and still showing the balance (the default LB-B demo state — NOT an error). Other session failure → `RetryError`; a balance-only failure with a working session → `RetryError` (never a misleading "0"). On success it resolves `table-id` from `fetchLiveTables()[0]` (SessionResponse carries no table_id) — an empty/unreachable catalog falls back to the same empty state — and renders `<LiveTable sessionToken tableId initialBalance>` inside a `<Suspense>` shell. `loading.tsx` clones `wallet/loading.tsx`. Money rendered as a string throughout (SP-1).
- **`live-table.tsx` script load + custom element (Task 2)** — `"use client"` `LiveTable({sessionToken, tableId, initialBalance})`. Loads the widget via `next/script` `strategy="afterInteractive"`; renders a "Live widget not configured" notice when `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` is unset (no broken `<script src="undefined">`, T-LBB-07). Renders `<live-bets-table>` via `useRef<HTMLElement>` and sets `session-token` / `table-id` via `setAttribute` in an effect. Holds the balance in `useState(initialBalance)` (labelled element, `aria-label="wallet balance"`). The custom element is typed via a `declare module "react" { namespace JSX { interface IntrinsicElements } }` augmentation — no `any`.
- **`live-table.tsx` event wiring + `getLiveBalance` (Task 3)** — One effect `addEventListener`s the four widget events, cleanup `removeEventListener`s all four (SC3): `live-bets-bet-placed` → `recordLivePlaced` → balance refresh (missing `bet_id` = no-op); `live-bets-result` → `recordLiveSettled` → balance refresh + WON/LOST/settled toast; `live-bets-session-expired` → `mintLiveSession(tableId)` → re-set `session-token` on the element; `live-bets-error` → non-silent error toast. The event detail is read defensively (third-party/untrusted); only `bet_id` reaches the backend (LB-A re-verifies — T-LBB-04); `applied:false` is treated as a benign no-op, never an error. The in-island balance refresh calls the new **`getLiveBalance`** Server Action and writes the result into local state (M-2).

## Deviations from Plan

### Auto-fixed / authoritative-override Issues

**1. [Authoritative override M-2 / Rule 2] Added `getLiveBalance` Server Action to `live-actions.ts`**
- **Found during:** Task 3.
- **Why:** The plan-check M-2 override mandates the wallet refresh update the island's LOCAL `useState` balance (so the visible balance actually moves after a settle), NOT `router.refresh()` (which re-runs the Server Component but leaves the client island's `useState` copy stale). The plan's own Task 3 `<action>` anticipates "expose a tiny `getLiveBalance` read (server action returning the current balance) and set local state."
- **What:** Added `getLiveBalance(): Promise<LiveBalanceResult>` to `live-actions.ts`, reading `GET /wallet/me/balance` with the forwarded cookie (same mechanism as `wallet/page.tsx`). The island's `refreshBalance` calls it after placed/settled and `setBalance`s the result.
- **Scope note:** `live-actions.ts` is an LB-B-01 file, not in LB-B-02's `files_modified`. The M-2 override is authoritative and supersedes that narrow list for this specific, plan-anticipated addition. No other LB-B-01 export changed.
- **Files modified:** `frontend/src/lib/live-actions.ts`
- **Commit:** 3d9915c

**2. [Rule 3 - Blocking] `@typescript-eslint/no-namespace` error on the JSX augmentation**
- **Found during:** Task 2.
- **Issue:** The custom-element typing requires `declare module "react" { namespace JSX { ... } }` (declaration merging into `React.JSX` — verified empirically: tsc passes only with this form, because in `@types/react` 19.2.15 `JSX` is NOT a global namespace, it lives under the `react` module export and the `react-jsx` runtime resolves intrinsics through `React.JSX.IntrinsicElements`). But eslint's `no-namespace` rule flags the `namespace` keyword as an ERROR (`pnpm lint` would fail).
- **Fix:** A single scoped `// eslint-disable-next-line @typescript-eslint/no-namespace` on the `namespace JSX` line — the canonical escape hatch for JSX intrinsic-element augmentation (there is no ES-module equivalent for this declaration merge). No `any`, no rule config change.
- **Files modified:** `frontend/src/app/live/live-table.tsx`
- **Commit:** ed71641

### Implementation choices worth recording (not deviations)
- **JSX-namespace decision (the brief asked for this explicitly):** verified against the installed `@types/react@19.2.15`. The global `JSX` namespace does not exist there; the augmentation MUST target `React.JSX.IntrinsicElements` via `declare module "react" { namespace JSX { interface IntrinsicElements } }`. `tsc --noEmit` passes with this and fails without it. A bare `declare global { namespace JSX }` would compile but be ignored by the React 19 runtime.
- **Session-expired re-mint without extra state:** the re-mint handler sets `session-token` directly on the element via `setAttribute` (the attribute effect keys on the `sessionToken` prop). This avoids a redundant token `useState` + sync effect that would have introduced a (tolerated-but-avoidable) `react-hooks/set-state-in-effect` warning. Net result: zero warnings in any LB-B file.

## Authentication gates
None. The page derives auth from the existing session cookie (signed-out → `SignedOutNotice`); no interactive auth was required during the build.

## Verification

All commands from `frontend/` with standalone **pnpm 9.15.0** (verified; never `corepack`).

- `pnpm exec tsc --noEmit` → **exit 0** (clean — custom element typed without `any`).
- `pnpm exec eslint src/app/live src/lib/live-actions.ts` → **exit 0**, zero warnings in the LB-B files.
- `pnpm lint` (`eslint src`) → **exit 0** — 19 pre-existing warnings (0 errors), **none in any LB-B file**. The warnings are repo-wide pre-existing items in untouched files (the `react-hooks/set-state-in-effect` rule the repo downgraded to "warn", React Compiler `incompatible-library` notes on TanStack Table / react-hook-form, a `brand-logo` `<img>` note, etc.).
- Scope: exactly the 7 planned frontend files changed across LB-B (4 in LB-B-01, 3 in LB-B-02) plus `live-actions.ts` (the M-2 addition); **`backend/` untouched**.
- Component tests are LB-B-03 (out of scope here, per the plan). A full `pnpm build` was not the gate for this build step (typecheck + lint were).

## Self-Check: PASSED

- Files exist: `frontend/src/app/live/page.tsx` (FOUND), `frontend/src/app/live/loading.tsx` (FOUND), `frontend/src/app/live/live-table.tsx` (FOUND), `frontend/src/lib/live-actions.ts` (FOUND, modified).
- Commits exist: `02e177b` (Task 1), `ed71641` (Task 2), `3d9915c` (Task 3) — all on `gsd/livebets-demo`.
