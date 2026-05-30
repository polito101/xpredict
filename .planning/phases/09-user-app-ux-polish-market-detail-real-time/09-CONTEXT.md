# Phase 9: User App UX Polish (Market Detail & Real-Time) - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — 4 grey areas, all recommended sets accepted by Agustin

<domain>
## Phase Boundary

Polish the **player-facing** surface to "feels real" quality and add real-time price movement. Two requirements: **MKT-03** (market detail page) and **MKT-04** (real-time WebSocket price updates).

In scope:
- Player market detail page at `/markets/{slug}`: question, full description, **publicly-visible resolution criteria**, price-history chart (Recharts, from Phase 6 `OddsSnapshot`), an **order-entry form** (built here — see note below), and a recent-activity feed.
- A backend **WebSocket** that pushes odds changes to open detail pages (mirrored markets on each Polymarket poll; house markets on admin odds edit) — no browser polling.
- Reconnect/backoff + "Live" / "Stale" connection UX.
- Empty / loading / error states across home, market list, market detail, and portfolio.

Out of scope (deferred / other phases): admin KPI dashboard & branding (Phase 10), mobile-responsiveness *validation* pass + hardening (Phase 11), secondary trading / selling positions (`sell_position` already returns 405 by design), multi-outcome markets (v2).

**Important boundary note:** the frontend bet/order UI was **not** delivered by Phase 5 (Phase 5 shipped the `place_bet` backend endpoint + a portfolio page, but no order-entry component). MKT-03 explicitly lists "order entry form" as part of the detail page, so building that form (wired to the existing `POST` place-bet endpoint, with a confirm modal showing stake / current odds / expected payout per Phase 5 SC#3) is **in Phase 9 scope**.

</domain>

<decisions>
## Implementation Decisions

### Area 1 — Market Detail Page (layout & content)
- **Layout:** responsive — two-column on desktop (price chart + market info on the left, sticky order-entry panel on the right), collapsing to a single stacked column on mobile (≥360px readable, anticipating Phase 11).
- **Order-entry form:** build it in Phase 9 (no existing frontend bet UI to reuse). Confirmation modal before submit showing stake, current odds, and expected payout (Phase 5 SC#3). Submits to the existing backend place-bet endpoint (`backend/app/bets/router.py::place_bet`). Reuse the auth/session pattern already established (cookie-gated player).
- **Recent activity feed:** show the **last 20** bets on the market.
- **Activity feed privacy:** fully anonymized — e.g. "Someone backed YES · $50 · 2m ago". No username, initials, or user id exposed.

### Area 2 — Price History Chart (Recharts)
- **Default window:** 7 days, with toggles for 24h / 7d / 30d (30d is the hard cap from Phase 6 snapshots).
- **Series plotted:** YES probability line only (binary market; NO is the complement — cleaner, fewer points). NO line is an explicit non-goal for v1.
- **Downsampling:** downsample server-side beyond 7 days (target ~hourly buckets) so the 30-day view renders without perf regression; raw 5-min snapshots only for the 24h/7d windows.
- **Empty / low-data state:** friendly "Not enough price history yet — check back soon" placeholder until the market has ≥2 snapshots.
- **Library:** Recharts, with `react-is` matched to React 19 (per STACK.md §10 — see Phase 9 ROADMAP SC#2).

### Area 3 — Real-Time (WebSocket)
- **Connection model:** one WebSocket per open market detail page — `/ws/markets/{id}` (or `/{slug}`) — subscribed to that single market. No global multiplexed socket in v1.
- **Backend publish transport:** **Redis pub/sub**. The Celery Beat poll worker and the admin odds-edit handler run in **separate processes** from the FastAPI web server that holds the WebSocket connections, so an in-process event bus would never reach connected clients. Producers (poll task, admin edit) publish an odds-change event to a Redis channel; the FastAPI WS layer subscribes and fans out to connected sockets for that market.
- **Message payload:** lean delta — `{ outcome_id, odds (string), ts }` per changed outcome. Money/odds as strings (project money-as-string convention).
- **WS auth:** public / unauthenticated. Odds are public data (same as the public market list); the WS is read-only price broadcast. (Bet placement stays on the authenticated REST endpoint.)

### Area 4 — Polish (loading / stale / errors / live indicator)
- **Loading:** Next.js Suspense boundaries + skeleton loaders (reuse/extend the existing `market-list-skeleton` pattern) on home, market list, market detail, and portfolio.
- **Stale handling:** if no WS update arrives for >30s, show an amber "Stale" badge **and keep the last-known odds visible** (never blank the price). Per PITFALLS UX rule: explicit staleness, never silent.
- **Bet/error states:** inline, specific error messages (insufficient balance, market closed, unverified-email → 403, banned) — no generic "transaction failed" toasts on the bet flow.
- **"Live" indicator:** small pulsing green dot + "Live" label adjacent to the odds block; switches to "Stale" (amber) / "Reconnecting…" on disconnect, driven by the reconnect-with-exponential-backoff client.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (frontend — Next.js 15, React 19, Tailwind 4, shadcn/ui)
- `frontend/src/components/`: `market-card.tsx`, `market-list.tsx`, `market-list-skeleton.tsx`, `odds-display.tsx`, `source-badge.tsx`, plus shadcn `ui/` (badge, button, card, input).
- `frontend/src/lib/api.ts`: `MarketItem` / `MarketOutcome` types, `fetchMarkets()` (Server Component fetch, `cache: "no-store"`, `NEXT_PUBLIC_API_URL` base), `formatVolume()`, `formatDeadline()`. Detail page should extend this with a `fetchMarket(slug)` helper + price-history + activity types.
- `frontend/src/lib/auth.ts`, `auth-schemas.ts`: established auth/session + zod + react-hook-form patterns (auth pages already use them) — reuse for the order-entry form.
- `frontend/src/app/`: `(auth)`, `admin`, `api`, `portfolio` (has `page.tsx` + tests), `wallet`, root `page.tsx` (home / market list). **No `markets/` route yet** — Phase 9 creates `markets/[slug]/`.
- No `frontend/src/hooks/` dir yet — Phase 9 adds the WebSocket client hook here (e.g. `use-market-socket.ts`).
- No chart library installed yet — Phase 9 adds Recharts.

### Reusable Assets (backend — FastAPI, SQLAlchemy 2 async, Postgres, Redis, Celery)
- `backend/app/markets/`: `models.py` (Market, Outcome, `OddsSnapshot` at line ~180 with `Market.odds_snapshots` relationship), `router.py` (`list_markets_public`, `get_market_public`, `bet_check`, admin CRUD incl. `update_market`/`close_market`), `service.py`, `schemas.py`, `enums.py`.
- `backend/app/bets/router.py`: `place_bet`, `read_portfolio`, `sell_position` (405 by design), `current_betting_player`, `get_market_source` (MarketReadPort). The detail-page order form targets `place_bet`.
- `backend/app/integrations/polymarket/tasks.py`: `snapshot_odds` (5-min OddsSnapshot writer) and the 30s poll task — these are the producers that must publish odds-change events to Redis for the WS.
- Redis already in the stack (Celery broker + RedBeat distributed lock) — reuse the same Redis for pub/sub.
- **No WebSocket infrastructure exists** (`grep` found zero refs) — Phase 9 builds the FastAPI WS endpoint + Redis pub/sub fan-out from scratch.

### Established Patterns
- Frontend data fetching: async Server Components calling the backend REST via `lib/api.ts` (no client-side fetch lib). Real-time is the first client-side data path — isolate it in a `"use client"` hook.
- Empty/error states already modeled in `market-list.tsx` (role="status", friendly copy) — extend that style.
- Money & odds as **strings** across the wire (never JSON floats) — keep for the delta payload and chart data.
- Backend money columns `NUMERIC(18,4)` + `Decimal`; odds stored/served as strings.

### Integration Points
- New route `frontend/src/app/markets/[slug]/page.tsx` (detail) + components (chart, activity feed, order-entry form, live indicator) + `hooks/use-market-socket.ts`.
- New backend: market-detail endpoint extension (criteria + price-history + recent-activity), price-history endpoint (with downsampling + window param), FastAPI WebSocket route, Redis pub/sub publisher hooked into the poll task + admin `update_market`/`close_market`.
- `MarketCard` on the home page should link to `/markets/{slug}`.

</code_context>

<specifics>
## Specific Ideas

- Resolution criteria is a **transparency trust signal** — render it prominently/always-visible on the detail page, never hidden behind a toggle (PITFALLS UX section).
- Activity-feed copy tone: neutral, anonymized, human ("Someone backed YES · $50 · 2m ago").
- "Live" → "Stale" → "Reconnecting…" connection states must be explicit and visible; staleness is never silent.

</specifics>

<deferred>
## Deferred Ideas

- Global multiplexed WebSocket (one socket, many market topics) — revisit if/when a live "all markets" ticker is wanted; per-market socket is enough for v1's "open one detail page" flow.
- Authenticated WebSocket / per-user real-time (e.g. live portfolio P&L push) — out of scope; v1 WS is public read-only odds.
- NO-probability line on the chart, multi-outcome chart series — v2 (binary-only in v1).
- Selling/closing a position before resolution — explicitly out of scope (`sell_position` returns 405).

</deferred>
