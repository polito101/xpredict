# Phase 19 Premium Experience — Audit: Backend API & Data Contracts

Read-only audit. Goal: ensure the dark-first premium redesign wires to the REAL endpoints that
already exist (no mocks, no parallel APIs), and preserve the white-label runtime branding system.

All paths are relative to the repo root
`C:/Users/Usuario/Documents/XPredict/xpredict/.claude/worktrees/loving-meitner-387810`.

Conventions used everywhere (must be honored by the redesign):
- **Money + odds are STRINGS on the wire** (Decimal serialized as JSON string — `Numeric(18,4)` money,
  `Numeric(8,6)` odds). The frontend rounds for display ONLY; never `parseFloat`/`Number()` for storage.
  This is enforced in backend schemas via `field_serializer`/`PlainSerializer` and documented in
  `frontend/src/lib/api.ts`, `kpi-types.ts`, `bet-schemas.ts`.
- **Timestamps** are tz-aware ISO-8601 strings.
- **`apiBase()` split** (repeated verbatim in `api.ts`, `catalog.ts`, `branding-public.ts`): server-side
  reads `BACKEND_URL` (Docker-internal `http://backend:8000`) → `NEXT_PUBLIC_API_URL` → `http://localhost:8000`;
  browser reads `NEXT_PUBLIC_API_URL` → localhost. The browser CANNOT resolve the Docker-internal `backend`
  hostname — keep the split.
- Public reads use `cache: "no-store"` (fresh per Server-Component render / per navigation).

---

## 1. Router mounting map (source of truth)

`backend/app/main.py` mounts these routers (lines 191-207). Note the mixed prefixes — there is **no global
`/api/v1` prefix**; each router declares its own:

| Router (file) | Prefix | Auth |
|---|---|---|
| `health.router` | `/healthz`, `/readyz` | none |
| `build_auth_routers()` (`auth/router.py` + `auth/admin_router.py`) | `/auth`, `/auth/users`, `/admin/auth` | cookie (player) / Bearer (admin) |
| `admin_crm_router` (`admin/router.py`) | `/api/v1/admin/...` | admin Bearer |
| `admin_export_router`, `kpi_router` (`admin/kpi_router.py`) | `/api/v1/admin/...` | admin Bearer |
| `audit_admin_router` (`core/audit/router.py`) | `/api/v1/admin/...` | admin Bearer |
| `admin_market_router` (`markets/router.py`) | `/api/v1/admin/markets` | admin Bearer |
| `tenant_config_admin_router` (`branding/admin_router.py`) | `/api/v1/admin/tenant-config` | admin Bearer |
| `public_market_router` (`markets/router.py`) | `/api/v1/markets` | **public** |
| `public_catalog_router` (`catalog/router.py`) | `/api/v1` (`/catalog`, `/events/{slug}`, `/categories`) | **public** |
| `wallet_admin_router` (`wallet/admin_router.py`) | `/admin/wallets` | admin Bearer |
| `wallet_router` (`wallet/router.py`) | `/wallet/me` | player cookie |
| `bets_router` (`bets/router.py`) | `/bets` | player cookie |
| `settlement_admin_router` (`settlement/router.py`) | `/admin/markets` | admin Bearer |
| `event_admin_router` (`settlement/event_router.py`) | `/admin/events` | admin Bearer |
| `realtime_router` (`realtime/router.py`) | `/ws/markets/{market_id}` (WebSocket) | public |
| `branding_router` (`branding/router.py`) | `/branding/current`, `/branding/logo` | **public** |

CORS: single allowed origin = `settings.FRONTEND_BASE_URL`, `allow_credentials=True` (cookie flow).

---

## 2. Consolidated endpoint catalog (player + public surface — what the redesign touches)

### Catalog / browse (the HOME page `/`)

**`GET /api/v1/catalog?q&category&status&sort`** — curated, bounded browse grid.
- Purpose: the single home grid mixing standalone binary `markets` and multi-outcome `events`.
- Query params (all optional): `q` (str ≤200, local pg_trgm search — never proxied to Gamma),
  `category` (str ≤100), `status` ∈ `{open, closing_soon, resolved}` (bad value → 422),
  `sort` ∈ `{volume, closing_soonest, newest}` default `volume` (bad value → 422). **No page/offset param —
  bounded server-side to `LIMIT 100`.** Every accepted combination returns 200 + a (possibly empty) array.
- Response: `CatalogItem[]` (`backend/app/catalog/schemas.py`):
  - `type` `"market"|"event"`, `id` UUID, `slug`, `title`, `category` `str|null`, `source`, `status` (public
    vocabulary string), `deadline` `string|null`, `volume` STRING (events = SUM of children's volume),
    `created_at`, `outcomes: CatalogOutcome[]` where `CatalogOutcome = {label, yes_outcome_id: string|null, yes_price: STRING}`.
  - For a `market`: 1 outcome (the YES leg). For an `event`: N outcomes (one YES row per child).
- Consumed by: `fetchCatalog()` in `frontend/src/lib/catalog.ts`, called by `frontend/src/app/page.tsx` (Home).
  `catalogMarketToMarketItem()` adapts a `type:"market"` item to the `MarketItem` shape the binary
  `MarketCard` consumes (so the same card is reused).

**`GET /api/v1/events/{slug}`** — multi-outcome event detail.
- 404 on missing slug OR a group with `<2` children (EVT-07: 1-child groups live on `/markets/{slug}`).
- Response: `EventDetail`: `id, slug, title, category|null, source, status` (RICHER 4-value derived status
  `{open, partially_resolved, resolved, void}` — not the 3-value public vocabulary), `deadline|null`,
  `created_at`, `outcomes: EventOutcomeRead[]` where
  `EventOutcomeRead = {label, yes_outcome_id: string|null, yes_price: STRING, market_id: UUID, child_slug, child_status}`.
  The `market_id` + `yes_outcome_id` are the bet seam; `child_slug` is the chart/detail seam.
- Consumed by: `fetchEvent()` in `catalog.ts`, called by `frontend/src/app/events/[slug]/page.tsx`.

**`GET /api/v1/categories`** — `string[]`, sorted non-empty DISTINCT union of categories over markets + events.
- Consumed by: `fetchCategories()` in `catalog.ts` (Home filter chips; degrades to `[]` on failure).

### Market detail (the `/markets/[slug]` page)

**`GET /api/v1/markets/{slug}`** — single binary market detail.
- 404 unless status ∈ `{OPEN, CLOSED, RESOLVED}` (RESOLVED is public so the player sees winner + justification).
- Response: `MarketRead` (`backend/app/markets/schemas.py`), consumed as `MarketDetail` in `api.ts`:
  `id, question, slug, resolution_criteria, category|null, source, source_market_id|null, status, deadline,
  bet_count, volume STRING, volume_24hr STRING, created_at, updated_at, closed_at|null, resolved_at|null`,
  the resolution projection `winning_outcome_id|null, resolution_source|null, resolution_justification|null`,
  the per-market stake bounds `min_stake STRING|null, max_stake STRING|null` (null = global default), and
  `outcomes: OutcomeRead[]` where `OutcomeRead = {id: UUID, label, initial_odds: STRING, current_odds: STRING}`.
  (Note: `MarketRead` does NOT carry `volume`/`source_url` derivation the way `MarketListItem` does — see below.)
- Consumed by: `fetchMarket()` in `api.ts`, called by `frontend/src/app/markets/[slug]/page.tsx`. Throws typed
  `MarketNotFound` on 404.

**`GET /api/v1/markets/{slug}/price-history?window=24h|7d|30d`** (default `7d`).
- Bad window → 422 (allowlist). 24h/7d serve raw 5-min snapshots; 30d is downsampled server-side to hourly buckets.
- Response: `PriceHistoryResponse = {window: string, points: PricePoint[]}`, `PricePoint = {ts: ISO, probability: STRING}`
  (the YES probability). `points` may be empty/single-element for a low-data market → frontend shows a
  "not enough history yet" placeholder.
- Consumed by: `fetchPriceHistory()` in `api.ts` (price-history chart on the detail page).

**`GET /api/v1/markets/{slug}/activity`** — anonymized recent activity (last 20 bets).
- Response: `ActivityItem[]`, `ActivityItem = {outcome: "YES"|"NO", amount: STRING, created_at: ISO}`.
  **Intentionally NO user identity field** — anonymized server-side; do NOT add one.
- Consumed by: `fetchActivity()` in `api.ts` (activity feed on the detail page).

### Bets (player, cookie-gated)

**`POST /bets`** — place a bet. Body `PlaceBetRequest` (`extra="forbid"` — exactly three keys):
`{market_id: UUID, outcome_id: UUID, stake: Decimal>0}`. Status map (the order-form maps each to a specific
inline message — see `frontend/src/lib/bet-actions.ts`):
`201` success (`BetResponse = {bet_id, market_id, outcome_id, stake STRING, odds_at_placement STRING, status}`),
`402` insufficient balance, `409` market closed, `403` unverified (default) / banned (detail contains "is banned"),
`422` stake out of range / invalid outcome, `401`/no-cookie → "Log in to place a bet", `404` market/wallet not found.
- Consumed by: `placeBetAction` (Server Action) in `bet-actions.ts` — forwards `Cookie: xpredict_session=...`.
  Pre-flight zod schema in `bet-schemas.ts` (`BET_MIN_STAKE=1`, `BET_MAX_STAKE=100000`; per-market bounds via
  `makeBetSchema(min,max)`). Backend is authoritative.

**`GET /bets/me/portfolio`** — the caller's positions (self-scoped; no `user_id` param).
- Response: `PortfolioResponse = {open: OpenPositionItem[], settled: SettledPositionItem[]}`.
  `OpenPositionItem = {bet_id, market_id, outcome_id, stake STRING, odds_at_placement STRING, potential_payout STRING, potential_pnl STRING}`.
  `SettledPositionItem = {bet_id, market_id, outcome_id, stake STRING, odds_at_placement STRING, won: bool, payout STRING, realized_pnl STRING}`.
  P&L strings already carry a leading "-" for losses.
- Consumed by: INLINE fetch in `frontend/src/app/portfolio/page.tsx` (`loadPortfolio()`, forwards the session
  cookie). There is NO `lib/` helper for this — the page fetches `${BACKEND_URL}/bets/me/portfolio` directly.

**`POST /bets/{bet_id}/sell`** — always `405` (no secondary market / cash-out in v1). Not consumed by the UI.

### Wallet (player, cookie-gated, prefix `/wallet/me`)

**`GET /wallet/me/balance`** → `BalanceResponse = {balance: STRING, currency: str}` (currency `PLAY_USD`).
**`GET /wallet/me/transactions?page&page_size`** (`page≥1` default 1, `page_size` 1..200 default 50) →
`TransactionPage = {items: TransactionItem[], page, page_size, total, has_next}`,
`TransactionItem = {kind, amount STRING, direction ("debit"|"credit"|str), created_at ISO, reason: str|null}`.
- Both strictly self-scoped (no `user_id` param). Consumed by INLINE fetch in
  `frontend/src/app/wallet/page.tsx` (`loadWallet()`, forwards the session cookie, `Promise.all` of the two).
  Again NO `lib/` helper. The "Add funds" button is intentionally DISABLED (v2 Stripe stub).

### Auth (player surface, prefix `/auth`)

| Endpoint | Body / form | Notes | Frontend consumer (`frontend/src/lib/auth.ts`) |
|---|---|---|---|
| `POST /auth/register` | JSON `{email, password, display_name?}` (`UserCreate`) | 201 → `UserRead`; 400 `REGISTER_USER_ALREADY_EXISTS` / invalid password; 429 rate-limited | `registerAction` |
| `POST /auth/login` | **form-urlencoded** OAuth2 `{username, password}` | sets `Set-Cookie: xpredict_session=...` (HttpOnly, SameSite=Lax, Path=/, Max-Age=`REFRESH_TOKEN_LIFETIME_SECONDS`); 400 `LOGIN_BAD_CREDENTIALS`; 403 banned; 429 | `loginAction` |
| `POST /auth/logout` | (cookie) | revokes server-side + clears cookie | `logoutAction` |
| `POST /auth/forgot-password` | JSON `{email}` | always `202 {"status":"accepted"}` (enumeration-safe) | `forgotPasswordAction` |
| `POST /auth/request-verify-token` | JSON `{email}` | always `202`; NOT consumed by current UI | (none) |
| `POST /auth/verify` | JSON `{token}` | single-use email verify | `verifyEmailAction` |
| `POST /auth/reset-password` | JSON `{token, password}` | 400 invalid/expired token | `resetPasswordAction` |
| `GET /auth/users/me` | (cookie) | `UserRead` — `requires_verification=True` | **NOT consumed** (see §5) |

`UserRead` (`backend/app/auth/schemas.py`) = fastapi-users `BaseUser` + `display_name: str|null` +
`is_admin: bool` (computed from internal `is_superuser`, which is `exclude=True` — never serialized).
Fields therefore: `id, email, is_active, is_verified, display_name, is_admin`.

### Branding (PUBLIC — the white-label runtime system; MUST be preserved)

**`GET /branding/current`** → `BrandingPublic = {brand_name, primary_hex, secondary_hex, logo_url: str|null}`.
- 4 fields, NO bytes. `primary_hex`/`secondary_hex` are server-validated `^#[0-9a-fA-F]{6}$`. On an unseeded DB
  the backend returns safe defaults (`brand_name:"XPredict"`, `#4f46e5` / `#0ea5e9`, `logo_url:null`) — these are
  the indigo/sky fallbacks the redesign is replacing visually, but the MECHANISM stays.
- Consumed by: `fetchBrandingPublic()` in `frontend/src/lib/branding-public.ts`, awaited in
  `frontend/src/app/layout.tsx` on EVERY navigation (`cache:"no-store"`). The layout injects
  `<style>:root{--brand-primary:…;--brand-primary-foreground:…;--brand-secondary:…}</style>` (head, line 75).
  `DEFAULT_BRANDING` applies on fetch failure (try/catch) so the UI is never unbranded-broken.

**`GET /branding/logo`** → the stored logo bytes with the stored Content-Type + `X-Content-Type-Options: nosniff`
+ `Content-Disposition: inline` + `Content-Security-Policy: default-src 'none'; sandbox`; `404` when no logo set.
- Consumed by: `frontend/src/components/brand-logo.tsx` as `<img src="{NEXT_PUBLIC_API_URL}{logo_url}">` (raw `<img>`,
  not `next/image`, by design). When `logo_url` is null it renders a brand-color accent dot + the wordmark text.

---

## 3. The proxy / auth pattern (how the Next layer forwards & how sessions work)

There are **two distinct transports**, and one Next "proxy" file that is actually edge middleware:

1. **Player = HttpOnly cookie `xpredict_session`** (fastapi-users `CookieTransport`, opaque DB-strategy token —
   NOT a JWT). Set by `POST /auth/login`'s `Set-Cookie`. Because Next Server Actions cannot transparently relay
   a cross-origin `Set-Cookie`, `auth.ts > forwardSessionCookie()` parses the header and re-sets the cookie via
   `next/headers > cookies().set(...)` (HttpOnly, SameSite=Lax, Path=/, mirrored Max-Age). Authenticated reads
   (wallet, portfolio, place-bet) read the cookie server-side and forward it as a `Cookie: xpredict_session=...`
   request header to `${BACKEND_URL}/...`. The cookie value NEVER enters client JS. `BACKEND_URL` is server-only
   (no `NEXT_PUBLIC_` prefix) so the backend origin never leaks into the client bundle.

2. **Admin = HttpOnly cookie `admin_jwt`** scoped to `path:/admin` (15-min Max-Age). `adminLoginAction` POSTs
   form-urlencoded to `/admin/auth/login`, receives JSON `{access_token, token_type:"bearer"}`, and re-wraps the
   token as the cookie. Admin Server Actions (`kpi-api.ts`, `branding-admin-api.ts`, `admin-*-api.ts`) read it and
   forward `Authorization: Bearer <token>` to `/api/v1/admin/...`.

3. **`frontend/src/proxy.ts`** is Next.js 16 middleware (the `middleware.ts` → `proxy.ts` rename; exports
   `function proxy(req)` + `config.matcher=["/admin/:path*"]`). It is an OPTIMISTIC gate: redirects anonymous
   browsers off `/admin/*` to `/admin/login` based on `admin_jwt` cookie PRESENCE only (no verification — the
   backend `current_active_admin` dependency is authoritative). It does NOT proxy/rewrite player API calls. **This
   file is not in `lib/` — it is `src/proxy.ts`.** The redesign must not break the matcher or the admin redirect.

There is **no Next API route that proxies the backend** (only `/api/healthz` and `/api/sentry-test` route handlers
exist). All data fetching is direct server→backend `fetch` (Server Components / Server Actions) or browser→backend
for the logo `<img>` and the WebSocket.

---

## 4. Realtime WebSocket contract

**URL:** `${NEXT_PUBLIC_WS_URL || "ws://localhost:8000"}/ws/markets/{market_id}` (browser-readable env var; MUST
be `NEXT_PUBLIC_`-prefixed). Public/unauthenticated, READ-ONLY broadcast (odds are public). Backend gates the
handshake by: per-process/per-market connection ceiling (close 1013), Origin allow-list = `FRONTEND_BASE_URL`
(close 1008; non-browser clients omit Origin and are allowed), and a `market_id` length cap of 128 (close 1008).

**Server→client message (price delta):**
`{ "type": "price_update", "market_id": "<uuid>", "outcomes": [{"outcome_id": "<uuid>", "odds": "<string>"}], "ts": <number> }`.
Odds are STRINGS. Any non-`price_update` message (e.g. pong) is ignored by the client.

**Client→server:** the only handled inbound text is the literal `"ping"` → server replies
`{"type":"pong","ts":<float>}`. The hook sends `"ping"` every 25s. Any other inbound text is ignored (a client
cannot inject a price).

**Consumer:** `frontend/src/hooks/use-market-socket.ts` (`useMarketSocket(marketId, initialOdds)` →
`{odds: Record<outcome_id,string>, state: "live"|"stale"|"reconnecting"}`). State machine: `live` (msg within 30s),
`stale` (open but >30s silent — last odds STAY VISIBLE, never blanked), `reconnecting` (dropped; exp backoff +
jitter capped 30s). Used by the market-detail live-odds component + `live-indicator.tsx`. The redesign can restyle
the indicator/odds freely as long as it keeps reading `{odds, state}`.

---

## 5. Endpoints that EXIST but are NOT consumed by the UI (redesign opportunities)

- **`GET /api/v1/markets`** (`public_market_router.list_markets_public`, "house first, then Polymarket by volume").
  `fetchMarkets()` still exists in `frontend/src/lib/api.ts` (lines 120-130) but is **no longer called by any
  player page** — Phase 17 switched the Home page (`app/page.tsx`) to `GET /catalog`. Its richer
  `MarketListItem` shape carries fields the catalog item lacks: `bet_count`, `volume_24hr`, and a derived
  `source_url` (a real `https://polymarket.com/event/{polymarket_slug}` link for Polymarket-sourced markets) plus
  `source_market_id` / `polymarket_slug`. **Opportunity:** a premium grid card / market-detail header could surface
  the "View on Polymarket" provenance link and a 24h volume delta badge using this endpoint (or fold those fields
  into the catalog DTO) without inventing anything.
- **`GET /auth/users/me`** — exists (fastapi-users), returns the player's `display_name` + `is_admin`. The current
  UI only derives a boolean "is authenticated" from cookie presence in `layout.tsx`. **Opportunity:** a real
  account menu / avatar / "Hi, {display_name}" in a premium header — the data is already there, just not fetched.
- **`GET /api/v1/markets/{slug}/bet-check`** — returns `{eligible: true}` or 400 with `{code, reason}`
  (`MARKET_NOT_OPEN` / `MARKET_EXPIRED`). No frontend consumer. **Opportunity:** a pre-flight "is this market still
  open" check to gray out / annotate the bet CTA before the user types a stake.
- **Settled-position richness** is fully present in `/bets/me/portfolio` (won/lost, realized P&L) but rendered as a
  flat list — a premium portfolio could chart cumulative realized P&L from the same payload (no new endpoint).
- **`volume_buckets` / KPI cards** (`GET /api/v1/admin/dashboard/kpis?window=24h|7d|30d` → `KpiResponse` with five
  cards + ≤30 daily `{day, volume STRING}` buckets) are admin-only but already consumed by the admin dashboard;
  the redesign of the admin shell can reuse them as-is (`kpi-api.ts` / `kpi-types.ts`).

---

## 6. Constraints the redesign must NOT break

- The white-label runtime branding loop: `layout.tsx` awaits `GET /branding/current` per navigation, injects
  `--brand-primary` / `--brand-primary-foreground` / `--brand-secondary` into `:root` via a `<style>` block in
  `<head>`, and renders the logo via `<img src="/branding/logo">` (raw `<img>`). Tailwind utility `bg-brand-primary`
  reads these CSS vars. The dark-first restyle must keep injecting from the endpoint (no hardcoded brand colors;
  the new "electric royal blue / liquid silver" identity is the DEFAULT/fallback, not a replacement of the
  injection mechanism). `pickReadableForeground()` derives a legible foreground from the operator's primary.
- Money/odds stay STRINGS end to end — no `parseFloat` for storage; format for display only.
- The `apiBase()` server/browser split (`BACKEND_URL` vs `NEXT_PUBLIC_API_URL`) and the WS `NEXT_PUBLIC_WS_URL`
  env contract.
- Session cookie discipline: `xpredict_session` (player) and `admin_jwt` (admin, `path:/admin`) are HttpOnly and
  never cross into client JS; authenticated calls forward them server-side.
- The anonymized `/activity` feed must never gain a user-identity field.
- `proxy.ts` matcher `["/admin/:path*"]` + the `admin_jwt`-presence redirect to `/admin/login`.
- The WS message contract (`price_update` + `outcomes[].odds` string + `ping`/`pong`) and the
  `useMarketSocket` `{odds,state}` return shape.

---

## Inventory (key files)

- `frontend/src/lib/api.ts` — public market read helpers (`fetchMarkets` UNUSED, `fetchMarket`, `fetchPriceHistory`, `fetchActivity`) + `formatVolume`/`formatDeadline`.
- `frontend/src/lib/catalog.ts` — `fetchCatalog`/`fetchEvent`/`fetchCategories` + `catalogMarketToMarketItem` adapter (drives the Home page).
- `frontend/src/lib/auth.ts` — player + admin auth Server Actions; session cookie forwarding.
- `frontend/src/lib/bet-actions.ts` + `bet-schemas.ts` — `placeBetAction` + status→copy map + pre-flight zod.
- `frontend/src/lib/branding-public.ts` — `fetchBrandingPublic` + `DEFAULT_BRANDING` (white-label loop).
- `frontend/src/lib/kpi-api.ts` + `kpi-types.ts` — admin KPI dashboard (Bearer-forwarded).
- `frontend/src/proxy.ts` — Next.js middleware optimistic `/admin/*` gate.
- `frontend/src/hooks/use-market-socket.ts` — live-odds WebSocket hook.
- `frontend/src/app/layout.tsx` — branding injection + logo + nav (white-label consumer).
- `frontend/src/app/page.tsx` — Home = catalog browse; `markets/[slug]/page.tsx`, `events/[slug]/page.tsx`, `wallet/page.tsx`, `portfolio/page.tsx` — the player surface (wallet/portfolio fetch inline, no lib helper).
- Backend routers: `catalog/router.py`, `markets/router.py`, `bets/router.py`, `wallet/router.py`, `auth/router.py`, `branding/router.py`, `realtime/router.py`, `settlement/router.py`, `settlement/event_router.py`; schemas in the sibling `schemas.py` of each.
