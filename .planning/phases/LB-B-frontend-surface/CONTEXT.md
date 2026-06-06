# Fase LB-B: Frontend surface — CONTEXT

Part of milestone **v1.3 Live-Bets demo** (off-grid). Design contract (READ FIRST):
[`../../../docs/superpowers/specs/2026-06-05-live-bets-integration-design.md`](../../../docs/superpowers/specs/2026-06-05-live-bets-integration-design.md) (§4 topology, §5 widget contract, §6 frontend, §7 session, §8 money).
Milestone plan-of-record: [`../../milestones/v1.3-MILESTONE-CONTEXT.md`](../../milestones/v1.3-MILESTONE-CONTEXT.md).
Backend already built in **LB-A** (DONE): routes `POST /api/live/session`, `GET /api/live/tables`, `POST /api/live/bets/{bet_id}/placed`, `POST /api/live/bets/{bet_id}/settled` (all player-authed).

## Goal
A new **`/live`** route in the XPredict player app embeds the live-bets `<live-bets-table>` widget wrapped in XPredict chrome (header/nav + the player's XPredict wallet balance). The page mints a live-bets session via the backend, renders the widget, and wires the widget's DOM events to the backend so the **XPredict wallet** debits on bet-placed and credits on settle (the LB-A ledger mirror). Frontend only.

## Scope — IN
- **`src/app/live/page.tsx`** — async Server Component (mirror `src/app/markets/[slug]/page.tsx` + `portfolio/page.tsx`): read auth via `cookies()` (`next/headers`), call the backend to mint a session + get the table, fetch the player's wallet balance, compose chrome + the client widget. If no table is configured yet (LB-A ships `LIVEBETS_DEFAULT_TABLE_ID=None`; the real table arrives in LB-C), render a friendly empty/zero state ("No live table configured yet") instead of erroring — so LB-B builds and demos its shell without live-bets running.
- **`src/app/live/live-table.tsx`** — `"use client"` component: load the widget script via `next/script` (src from `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC`, e.g. `http://localhost:8080/static/widget.js` in LB-C; no SRI in dev). Render the custom element `<live-bets-table session-token={token} table-id={tableId}>` via a `ref` (handle the hyphenated attributes with `setAttribute`; React 19 custom-element support). In a `useEffect`, `addEventListener` on the element for the widget DOM events and wire them to the backend + wallet refresh:
  - `live-bets-bet-placed` `{bet_id,...}` → `POST /api/live/bets/{bet_id}/placed` → refresh wallet balance.
  - `live-bets-result` `{bet_id, status, payout}` → `POST /api/live/bets/{bet_id}/settled` → refresh wallet + non-silent WON/LOST toast.
  - `live-bets-session-expired` → re-mint via `POST /api/live/session`, `setAttribute("session-token", new)`.
  - `live-bets-error` → non-silent error UI (mirror the project's error/toast pattern, e.g. `order-entry-form` error states).
  Clean up listeners on unmount.
- **`src/lib/api.ts`** — add typed helpers (mirror the existing `fetchMarket`/auth-cookie-forwarding pattern): `fetchLiveSession()` (POST /api/live/session), `fetchLiveTables()` (GET /api/live/tables), `recordLivePlaced(betId)`, `recordLiveSettled(betId)`. Money/odds stay strings on the wire (SP-1).
- **`src/components/player-nav.tsx`** — add `{ href: "/live", label: "Live" }` to the nav links (after Markets, or where it reads best).
- **Wallet balance display** around the widget — reuse the existing wallet-balance fetch/component that `/wallet` uses (grep it), and refresh it after placed/settled.
- **Component test** (`pnpm vitest run`): mock the api helpers + the custom element; assert dispatching each widget DOM event calls the right backend helper and triggers a wallet refresh; assert the "Live" nav entry renders; assert the no-table empty state. Hermetic — no real widget/live-bets/network.

## Scope — OUT (do NOT build here)
- live-bets local stack, port remap, CORS, operator key with `bets:read`, ingest clips, run orchestrator, pre-fund → **LB-C**.
- Any backend change (LB-A is done; if a backend gap appears, STOP and report — do not edit `app/integrations/livebets/`).
- Real end-to-end widget play (needs live-bets running — that is LB-C + the manual demo script).

## Success Criteria (what must be TRUE)
1. `/live` renders under the player app with XPredict header/nav + the player's wallet balance; it is reachable only when authenticated (mirror the existing player-page auth behavior) and shows a clean empty state when no table is configured.
2. The "Live" nav entry appears in `player-nav` and routes to `/live`.
3. The client component loads the widget script via `next/script` and renders `<live-bets-table>` with the `session-token` + `table-id` from the backend; the four widget DOM events are wired to `POST /api/live/bets/{id}/placed|settled`, session renewal, and a non-silent error/result UI; listeners are cleaned up on unmount.
4. `src/lib/api.ts` exposes typed `fetchLiveSession`/`fetchLiveTables`/`recordLivePlaced`/`recordLiveSettled` that forward the auth cookie like the existing helpers.
5. `cd frontend && pnpm vitest run` is green for the new tests (event→backend wiring, nav entry, empty state); existing frontend tests still pass. `pnpm build`/typecheck + `pnpm lint` clean.

## Patterns to mirror (grep/read — do NOT invent)
- `src/app/markets/[slug]/page.tsx` + `src/app/portfolio/page.tsx` — async Server Component shell, `cookies()` auth, parallel SSR fetch, loading skeleton, not-found/empty states.
- `src/lib/api.ts` — typed fetch helpers + how they forward the session cookie to the backend (confirm the exact base-URL/cookie mechanism).
- `src/components/player-nav.tsx` — the nav link list (add "Live").
- `src/app/wallet/` — how the wallet balance is fetched + displayed (reuse the component/fetch; confirm its name).
- `src/components/order-entry-form.tsx` — the project's success/error/toast + loading patterns to mirror for the result/error UI.
- Brand white-label: every new surface respects the operator's `--brand-*` tokens (v1.1 Fase A). The widget interior is the widget's own styling (partially brandable) — note this; the XPredict chrome around it must be on-brand.

## Open items for the planner to resolve (grep, don't guess)
- The exact auth-cookie forwarding mechanism in `src/lib/api.ts` (cookie header pass-through for server-side fetch vs client-side `credentials: "include"`).
- The wallet-balance component/fetch name used by `/wallet` (reuse it; add a refresh trigger after placed/settled).
- How to render a custom element + set hyphenated attributes cleanly in React 19 (ref + setAttribute), and load a third-party script with `next/script` (strategy).
- New public env var(s): `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` (+ document in `.env.example`); the `table-id` comes from the backend (`/api/live/session` or `/tables`), the `session-token` from `/api/live/session`.

## Constraints / gotchas
- **pnpm: use the standalone `pnpm@9.15.0` ONLY (`pnpm --version` must be 9.15.x). NEVER `corepack pnpm` — it resolves to a destructive 11.x that wipes node_modules and rewrites the lockfile (CLAUDE.md).** If pnpm is not 9.15.x, STOP and report.
- Next.js 15 + React 19 + Tailwind 4 + shadcn/ui. Test: `cd frontend && pnpm vitest run`.
- This worktree's `frontend/node_modules` may be absent — `pnpm install --frozen-lockfile` (standalone) before building/testing.
