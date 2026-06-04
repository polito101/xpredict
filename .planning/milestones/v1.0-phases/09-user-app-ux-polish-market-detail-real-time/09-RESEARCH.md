# Phase 9: User App UX Polish (Market Detail & Real-Time) - Research

**Researched:** 2026-05-29
**Domain:** Cross-process real-time fan-out (FastAPI WebSocket + Redis pub/sub), Recharts on Next 16/React 19, Next.js SSR-initial + client-subscribe, order-entry form
**Confidence:** HIGH

## Summary

This phase is **mostly de-risked already**. The single highest-risk piece — cross-process WebSocket fan-out from the Celery poll worker / admin-edit process to the FastAPI process holding the sockets — was fully built and **VALIDATED in spike 003** (`.planning/spikes/003-websocket-price-streaming/`, verdict VALIDATED, 6/6 tests pass, avg 0.8 ms end-to-end). The proven pattern is **FastAPI native WebSocket + `redis.asyncio` pub/sub** with a per-market `ConnectionManager`, a `psubscribe("prices:*")` background task started in the app lifespan, and producers (poll task + admin odds edit) calling `redis.publish(f"prices:{market_id}", json)`. **Zero new backend dependencies** — `fastapi[standard]`, `uvicorn[standard]`, and `redis>=5.0` are all already pinned in `backend/pyproject.toml` [VERIFIED: codebase grep]. This is the rare case where the planner can lift a proven reference implementation almost verbatim; research effort shifts to *integrating* it into the real app factory, real models, and real producer hooks rather than designing it.

The genuinely new external dependency is **Recharts**, and it carries one sharp, current pitfall: **Recharts renders a blank chart on React 19 unless `react-is` is pinned to the exact React 19 version and overridden in the package manager** (multiple 2026 reports; the project's `react@^19.0.0` resolves to React 19.2.6 today) [VERIFIED: npm registry + CITED: github.com/recharts/recharts/issues/6857]. The project uses **pnpm**, so the fix is a pnpm-specific override block. This is exactly the `react-is` pin the UI-SPEC and STACK.md §10 anticipate — research confirms the precise mechanism and version.

The remaining work is conventional and follows established codebase patterns: a new public price-history endpoint with server-side downsampling beyond 7d (the `OddsSnapshot` table already exists and is populated every 5 min by `snapshot_odds`), a market-detail extension (criteria + recent-activity), an order-entry form (react-hook-form + zod + a hand-copied shadcn `dialog`/`select`, POSTing to the existing `place_bet`), and a `"use client"` WebSocket hook driving the Live/Stale/Reconnecting state machine. Money and odds stay **strings on the wire** throughout (the project's non-negotiable convention; odds are `Numeric(8,6)`, money is `Numeric(18,4)`).

**Primary recommendation:** Lift spike 003's `ConnectionManager` + `redis_subscriber` + WS endpoint into `app/realtime/`, wire the subscriber into the existing `lifespan` in `app/main.py`, add a `publish_odds_change()` call at the two producer sites (`snapshot_odds`/poll path and `MarketService.update_market`'s odds branch), install Recharts with a matched `react-is` pnpm override, and build the detail page as a Server Component shell (initial fetch) hydrating a `"use client"` socket hook for live deltas.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Market detail initial render (question, criteria, history, activity) | Frontend Server (Next SSR) | API / Backend | Server Component fetches once from REST; matches the existing `MarketList` Server-Component pattern (`cache: "no-store"`). |
| Price-history query + downsampling | API / Backend | Database | Downsampling/bucketing is a SQL concern over `odds_snapshots`; never ship raw 30d snapshots to the browser. |
| Live odds delta broadcast | API / Backend (FastAPI WS) | — | The WS connection lives in the uvicorn process; this is the only tier that holds sockets. |
| Cross-process event transport | Database/Storage (Redis pub/sub) | — | Celery worker + admin-edit run in separate processes; Redis is the message bus already in the stack. |
| Live odds rendering + connection state machine | Browser / Client (`"use client"` hook) | — | Real-time is the first client-side data path; isolate in a hook per CONTEXT Area 3. |
| Order entry (validate + submit) | Browser / Client (rhf+zod) | API / Backend (authoritative) | Client validation is pre-flight UX only; `place_bet` is the authority (stake limits, balance, ban, verify). |
| Bet placement (ACID) | API / Backend | Database | Reuse Phase 5 `BetService.place_bet` unchanged. |
| Recent-activity feed (anonymized) | API / Backend | Database | Anonymization (strip user identity) MUST happen server-side; the browser must never receive user_id. |

<user_constraints>
## User Constraints (from CONTEXT.md)

> CONTEXT.md records this as **Smart discuss (autonomous) — 4 grey areas, all recommended sets accepted by Agustin**. All four areas are LOCKED. Research these, not alternatives.

### Locked Decisions

**Area 1 — Market Detail Page (layout & content)**
- **Layout:** responsive — two-column on desktop (price chart + market info left, sticky order-entry panel right), collapsing to a single stacked column on mobile (≥360px readable, anticipating Phase 11).
- **Order-entry form:** build it in Phase 9 (no existing frontend bet UI to reuse). Confirmation modal before submit showing stake, current odds, and expected payout (Phase 5 SC#3). Submits to the existing backend place-bet endpoint (`backend/app/bets/router.py::place_bet`). Reuse the auth/session pattern already established (cookie-gated player).
- **Recent activity feed:** show the **last 20** bets on the market.
- **Activity feed privacy:** fully anonymized — e.g. "Someone backed YES · $50 · 2m ago". No username, initials, or user id exposed.

**Area 2 — Price History Chart (Recharts)**
- **Default window:** 7 days, with toggles for 24h / 7d / 30d (30d is the hard cap from Phase 6 snapshots).
- **Series plotted:** YES probability line only (binary market; NO is the complement). NO line is an explicit non-goal for v1.
- **Downsampling:** downsample server-side beyond 7 days (target ~hourly buckets) so the 30-day view renders without perf regression; raw 5-min snapshots only for the 24h/7d windows.
- **Empty / low-data state:** friendly "Not enough price history yet — check back soon" placeholder until the market has ≥2 snapshots.
- **Library:** Recharts, with `react-is` matched to React 19 (per STACK.md §10 — see Phase 9 ROADMAP SC#2).

**Area 3 — Real-Time (WebSocket)**
- **Connection model:** one WebSocket per open market detail page — `/ws/markets/{id}` (or `/{slug}`) — subscribed to that single market. No global multiplexed socket in v1.
- **Backend publish transport:** **Redis pub/sub.** Producers (poll task, admin edit) publish an odds-change event to a Redis channel; the FastAPI WS layer subscribes and fans out to connected sockets for that market.
- **Message payload:** lean delta — `{ outcome_id, odds (string), ts }` per changed outcome. Money/odds as strings.
- **WS auth:** public / unauthenticated. Odds are public data; the WS is read-only price broadcast. (Bet placement stays on the authenticated REST endpoint.)

**Area 4 — Polish (loading / stale / errors / live indicator)**
- **Loading:** Next.js Suspense boundaries + skeleton loaders (reuse/extend `market-list-skeleton`) on home, market list, market detail, and portfolio.
- **Stale handling:** if no WS update arrives for >30s, show an amber "Stale" badge **and keep the last-known odds visible** (never blank the price). Explicit staleness, never silent.
- **Bet/error states:** inline, specific error messages (insufficient balance, market closed, unverified-email → 403, banned) — no generic "transaction failed" toasts on the bet flow.
- **"Live" indicator:** small pulsing green dot + "Live" label adjacent to the odds block; switches to "Stale" (amber) / "Reconnecting…" on disconnect, driven by reconnect-with-exponential-backoff.

### Claude's Discretion
- Connection identifier (`/ws/markets/{id}` vs `/{slug}`) — CONTEXT lists both; researcher recommends **`{market_id}` (UUID)** because the producer side (poll task, admin edit) holds `market.id`, the channel is keyed `prices:{market_id}`, and publishing by UUID avoids a slug lookup in the hot path. The detail page already has the market UUID from the SSR fetch.
- Chart window-toggle implementation: shadcn `tabs` OR a `ToggleGroup` of `Button size="sm"` (UI-SPEC marks this executor's discretion).
- Whether new bets prepend onto the activity feed over the socket (UI-SPEC: "MAY prepend"; chart/odds is the primary real-time surface). Researcher recommends deferring activity-over-socket — keep the v1 stream odds-only (matches spike scope).

### Deferred Ideas (OUT OF SCOPE)
- Global multiplexed WebSocket (one socket, many market topics) — revisit for a live "all markets" ticker; per-market socket is enough for v1.
- Authenticated WebSocket / per-user real-time (e.g. live portfolio P&L push) — v1 WS is public read-only odds.
- NO-probability line on the chart, multi-outcome chart series — v2 (binary-only in v1).
- Selling/closing a position before resolution — explicitly out of scope (`sell_position` returns 405).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MKT-03 | Player market detail page: question, resolution criteria, price-history chart, order-entry form, recent-activity feed | `get_market_public(slug)` already returns question + criteria + outcomes; extend with price-history + recent-activity endpoints. Chart via Recharts (Standard Stack). Order form reuses `place_bet` (Phase 5, present). Activity feed reads `Bet` rows, anonymized server-side. |
| MKT-04 | Real-time WebSocket price updates: mirrored markets update on each Polymarket poll; house markets update on admin odds edit | Spike 003 VALIDATED the full pipeline. Producer hooks: `snapshot_odds`/poll path (`PolymarketAdapter.sync_top25` updates `Outcome.current_odds`) and `MarketService.update_market` (odds branch updates `current_odds` + writes `OddsSnapshot`). Add `redis.publish()` at both sites; FastAPI subscriber fans out. |
</phase_requirements>

## Standard Stack

### Core (backend — all already installed; ZERO new backend deps)
| Library | Version (pinned) | Purpose | Why Standard |
|---------|------------------|---------|--------------|
| `fastapi[standard]` | `>=0.115.7,<0.116.0` | Native WebSocket endpoint (`@app.websocket(...)`, `WebSocket`, `WebSocketDisconnect`) | `[standard]` bundles `websockets`; FastAPI WS is sufficient — spike 003 proved it [VERIFIED: codebase pyproject + CITED: fastapi.tiangolo.com/advanced/websockets]. |
| `uvicorn[standard]` | `>=0.32,<0.36` | ASGI server with WebSocket protocol support | `[standard]` includes the `websockets`/`wsproto` server impl. Already the runtime. [VERIFIED: codebase pyproject] |
| `redis` (`redis.asyncio`) | `>=5.0,<6.0` | Async pub/sub subscriber in FastAPI; sync `redis` publish in producers | Already the Celery broker + RedBeat lock. `redis.asyncio` ships in `redis>=4.2`. The Celery tasks already `from redis.asyncio import Redis as AioRedis`. [VERIFIED: codebase grep] |

### Core (frontend — ONE new dependency + its peer)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `recharts` | `3.8.1` (latest, published 2026-05-24) | YES-probability line chart (price history) | The de-facto React charting library; declarative composition API; already chosen project-wide (also used by Phase 10 KPI dashboard). [VERIFIED: npm registry] |
| `react-is` | **match React** — `19.2.6` today (whatever `react@^19.0.0` resolves to) | Recharts peer dependency; **must equal the installed React version or charts render blank** | See Pitfall 1 — this is the single most important frontend detail in the phase. [VERIFIED: npm registry + CITED: github.com/recharts/recharts/issues/6857] |

### Supporting (frontend — hand-copied shadcn primitives, NOT npm installs)
| Component | Source | Purpose | When to Use |
|-----------|--------|---------|-------------|
| shadcn `dialog` | hand-copy canonical "new-york" | Bet confirmation modal (`BetConfirmDialog`) | Wraps Radix `@radix-ui/react-dialog` — this Radix pkg is NOT yet a dependency; copying `dialog.tsx` requires `pnpm add @radix-ui/react-dialog`. [VERIFIED: codebase grep — not in package.json] |
| shadcn `select` | hand-copy canonical "new-york" | Outcome selector (YES/NO) in order form | Wraps `@radix-ui/react-select` — also NOT yet a dependency; copying requires `pnpm add @radix-ui/react-select`. [VERIFIED: codebase grep] |

> **Note on shadcn install model:** UI-SPEC §"Design System" locks **manual hand-copy mode** (no `components.json`, no CLI, no registry fetch). The two new primitives are copied by hand the same way `button.tsx`/`card.tsx`/`form.tsx` already were. BUT each shadcn primitive's underlying Radix package must still be `pnpm add`-ed — the existing ones (`@radix-ui/react-slot`, `@radix-ui/react-label`) are in package.json; `dialog` and `select` need their Radix packages added. [VERIFIED: codebase grep]

### Alternatives Considered (and rejected by spike/CONTEXT)
| Instead of | Could Use | Tradeoff / Why Rejected |
|------------|-----------|--------------------------|
| FastAPI native WS + `redis.asyncio` | `broadcaster` library | Stale maintenance, unnecessary dep — spike 003 "What to Avoid" #1. [CITED: spike-findings real-time-streaming.md] |
| FastAPI native WS | `fastapi-websocket-pubsub` | Opinionated, overkill for one read-only channel — spike 003 Research table "Skip". |
| WebSocket | SSE (Server-Sent Events) | Unidirectional, worse reconnect, no ping/pong — spike 003 "What to Avoid" #2 (kept as backup only). |
| Recharts | visx / Chart.js / lightweight-charts | Recharts is locked project-wide (Phase 10 reuses it); no reason to diverge. |

**Installation:**
```bash
# Backend: NOTHING to install — all deps present.

# Frontend (from frontend/):
pnpm add recharts react-is@19.2.6        # pin react-is to the EXACT installed React version
pnpm add @radix-ui/react-dialog @radix-ui/react-select   # for hand-copied shadcn dialog + select
```
Then add the pnpm override (see Pitfall 1) and re-run `pnpm install`.

**Version verification (run before locking the plan):**
```bash
npm view recharts version            # confirm latest 3.x at plan time (was 3.8.1 on 2026-05-29)
cd frontend && node -p "require('react/package.json').version"   # the EXACT react-is target
```

## Package Legitimacy Audit

> slopcheck was not available in this research session (no network package-install). Per protocol, the two NEW npm packages below are tagged for the planner to confirm. Both are extremely well-known with massive download counts and official source repos; registry + provenance were verified directly via `npm view`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `recharts` | npm | mature (3.x line; 2.x since 2020) | tens of millions/wk | github.com/recharts/recharts | n/a (unavailable) | Approved — verified via npm view + official GitHub. Pin `3.8.1` (or current latest 3.x at plan time). |
| `react-is` | npm | React's own (published in lockstep with React) | hundreds of millions/wk | github.com/facebook/react | n/a (unavailable) | Approved — it is a first-party React package. Pin to the exact installed React version. |
| `@radix-ui/react-dialog` | npm | mature (Radix UI) | tens of millions/wk | github.com/radix-ui/primitives | n/a | Approved — same Radix family already in package.json (`react-slot`, `react-label`). |
| `@radix-ui/react-select` | npm | mature (Radix UI) | tens of millions/wk | github.com/radix-ui/primitives | n/a | Approved — same family. |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable; the planner SHOULD run `slopcheck install recharts react-is @radix-ui/react-dialog @radix-ui/react-select --json` (or a `pnpm` dry-run) at plan time as a belt-and-suspenders check. All four are first-party/established packages with official repos, so risk is minimal.*

## Architecture Patterns

### System Architecture Diagram

```
                          PRODUCERS (separate processes)
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ Celery Beat worker process                Admin-edit (FastAPI request)    │
  │   poll_polymarket_top25 (30s)               PATCH /admin/markets/{id}     │
  │     └─ PolymarketAdapter.sync_top25           └─ MarketService.update_     │
  │          sets Outcome.current_odds                 market (odds branch:    │
  │          (on change)                               current_odds + new      │
  │   snapshot_odds (5min)                             OddsSnapshot)           │
  │     └─ writes OddsSnapshot rows                                            │
  └───────────────┬─────────────────────────────────────────┬────────────────┘
                  │ redis.publish("prices:{market_id}", json) │   (NEW hook)
                  ▼                                            ▼
        ┌──────────────────────────── REDIS ────────────────────────────┐
        │  pub/sub channel  prices:{market_id}   (broker already in stack)│
        └───────────────────────────────┬───────────────────────────────┘
                                         │  psubscribe("prices:*")
                  ┌──────────────────────┴───────────────────────┐
                  ▼                                               ▼
   ┌─────────────────────────────┐                 ┌─────────────────────────────┐
   │ FastAPI/uvicorn worker #1   │                 │ FastAPI/uvicorn worker #N   │
   │  lifespan starts            │   (each worker  │  lifespan starts            │
   │  redis_subscriber task      │    subscribes    │  redis_subscriber task      │
   │   → ConnectionManager       │    independently │   → ConnectionManager       │
   │   → broadcast(market_id,…)  │    = multi-worker│   → broadcast(market_id,…)  │
   │  @websocket /ws/markets/{id}│    correct)      │  @websocket /ws/markets/{id}│
   └───────────────┬─────────────┘                 └───────────────┬─────────────┘
                   │ ws.send_json(delta)                           │
                   ▼                                               ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │ Next.js client — market detail page /markets/[slug]                         │
   │   Server Component: initial fetch (market + history + activity) via REST     │
   │   "use client" use-market-socket hook:                                       │
   │     new WebSocket(`${NEXT_PUBLIC_WS_URL}/ws/markets/${id}`)                   │
   │       onmessage → update YES/NO odds in place (transition, no layout shift)   │
   │       onclose   → exponential-backoff reconnect                              │
   │       no msg >30s → Stale badge (last odds kept visible)                     │
   └───────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/app/
├── realtime/                      # NEW module (lift from spike 003)
│   ├── __init__.py
│   ├── manager.py                 # ConnectionManager (per-market set[WebSocket] + asyncio.Lock)
│   ├── subscriber.py              # redis_subscriber(manager) — psubscribe("prices:*")
│   ├── publisher.py               # publish_odds_change(market_id, deltas) — sync redis.publish
│   └── router.py                  # @websocket("/ws/markets/{market_id}")
├── markets/
│   ├── router.py                  # EXTEND: add GET /{slug}/price-history, GET /{slug}/activity
│   ├── service.py                 # EXTEND: price_history(slug, window), recent_activity(slug, 20)
│   │                              #   + publish_odds_change() call in update_market odds branch
│   └── schemas.py                 # EXTEND: PricePoint, PriceHistoryResponse, ActivityItem (strings)
├── integrations/polymarket/
│   └── tasks.py                   # EXTEND: publish_odds_change() after sync detects current_odds change
└── main.py                        # EXTEND: lifespan starts redis_subscriber; include realtime router

frontend/src/
├── app/markets/[slug]/
│   ├── page.tsx                   # NEW Server Component shell + Suspense (initial fetch)
│   └── loading.tsx OR <Suspense>  # MarketDetailSkeleton fallback
├── components/
│   ├── price-history-chart.tsx    # NEW "use client" — Recharts YES line + window toggle + empty state
│   ├── order-entry-form.tsx       # NEW "use client" — rhf+zod, Select+Input, inline errors
│   ├── bet-confirm-dialog.tsx     # NEW "use client" — shadcn dialog (stake/odds/payout)
│   ├── recent-activity-feed.tsx   # NEW — anonymized last-20 list + empty state
│   ├── live-indicator.tsx         # NEW "use client" — dot+label driven by socket state
│   ├── market-detail-skeleton.tsx # NEW — two-column loading mirror
│   └── ui/{dialog,select}.tsx     # NEW hand-copied shadcn primitives
├── hooks/
│   └── use-market-socket.ts       # NEW "use client" — WS + backoff + Live/Stale/Reconnecting state
└── lib/
    ├── api.ts                     # EXTEND: fetchMarket(slug), fetchPriceHistory, fetchActivity + types
    └── bet-actions.ts (or use auth.ts pattern)  # placeBetAction Server Action (cookie-forward)
```

### Pattern 1: ConnectionManager (per-market client tracking) — LIFT FROM SPIKE 003
**What:** A dict of `market_id → set[WebSocket]` guarded by an `asyncio.Lock`, with `connect`/`disconnect`/`broadcast`. `broadcast` snapshots the client set under the lock, sends outside the lock, and prunes dead sockets.
**When to use:** Exactly as-is — this is the validated implementation. Do not redesign.
**Example:**
```python
# Source: .planning/spikes/003-websocket-price-streaming/spike_ws_server.py (VALIDATED, 6/6 tests)
class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, market_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(market_id, set()).add(ws)

    async def disconnect(self, market_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(market_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    del self._connections[market_id]

    async def broadcast(self, market_id: str, data: dict) -> tuple[int, int]:
        async with self._lock:                       # snapshot under lock
            clients = list(self._connections.get(market_id, set()))
        sent = failed = 0
        stale: list[WebSocket] = []
        for ws in clients:                            # send OUTSIDE lock
            try:
                await ws.send_json(data)
                sent += 1
            except Exception:
                stale.append(ws); failed += 1
        for ws in stale:
            await self.disconnect(market_id, ws)
        return sent, failed
```

### Pattern 2: Redis subscriber background task, started in lifespan
**What:** A single `asyncio` task per FastAPI process that `psubscribe("prices:*")`, decodes each `pmessage`, parses the channel suffix as the market_id, and calls `manager.broadcast(market_id, data)`. Started/cancelled in the app lifespan.
**When to use:** Wire into the **existing** `lifespan` in `app/main.py` (which currently only does `configure_logging` + `init_sentry`).
**Multi-worker note:** because each uvicorn worker process runs its own lifespan, each gets its own subscriber and broadcasts to its own local connections — **multi-worker is correct with zero extra code** [CITED: spike real-time-streaming.md "for multi-process, each worker subscribes independently"; corroborated by websocket.org/guides/frameworks/fastapi].
**Example:**
```python
# Source: spike_ws_server.py + app/main.py existing lifespan (MERGE the two)
import redis.asyncio as aioredis

async def redis_subscriber(manager: ConnectionManager, redis_url: str) -> None:
    r = aioredis.from_url(redis_url)
    pubsub = r.pubsub()
    await pubsub.psubscribe("prices:*")
    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            channel = message["channel"]
            channel = channel.decode() if isinstance(channel, bytes) else channel
            market_id = channel.removeprefix("prices:")
            raw = message["data"]
            raw = raw.decode() if isinstance(raw, bytes) else raw
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await manager.broadcast(market_id, data)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.punsubscribe("prices:*")
        await r.aclose()

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings)
    init_sentry(service="api", settings=settings, integrations=[FastApiIntegration(), SqlalchemyIntegration()])
    task = asyncio.create_task(redis_subscriber(manager, str(settings.REDIS_URL)))   # NEW
    try:
        yield
    finally:                                  # NEW
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
```

### Pattern 3: Publisher hook (sync redis.publish from producers)
**What:** A tiny helper called at the two producer sites. Producers run in Celery/request contexts where a **sync** `redis` publish is simplest; the Celery tasks already use `redis.asyncio`, so either a sync `redis.from_url().publish()` or an `await aioredis...publish()` works. The payload is the lean delta the CONTEXT locked.
**When to use:**
1. In the poll path — after `sync_top25` (or inside it) when an outcome's `current_odds` actually changes. Publish only changed markets to avoid noise.
2. In `MarketService.update_market` — inside the `if body.odds_yes is not None:` branch, after `current_odds` is updated and the `OddsSnapshot` is written, but only after the surrounding `session.commit()` succeeds (publish post-commit so clients never see a rolled-back price).
**Example:**
```python
# Source: spike_ws_publisher.py (shape) + app/markets/models.py (Odds is str-on-wire)
def publish_odds_change(market_id, deltas: list[dict]) -> None:
    # deltas = [{"outcome_id": str(o.id), "odds": str(o.current_odds)} for changed outcomes]
    payload = {"type": "price_update", "market_id": str(market_id),
               "outcomes": deltas, "ts": time.time()}
    r = redis.from_url(str(get_settings().REDIS_URL))
    r.publish(f"prices:{market_id}", json.dumps(payload))
```
> **Payload contract (CONTEXT Area 3):** lean delta `{ outcome_id, odds (string), ts }` per changed outcome. `odds` is `str(Outcome.current_odds)` — a `Numeric(8,6)` Decimal serialized as a string (NEVER a JSON float), identical to how `OutcomeRead` serializes it [VERIFIED: codebase markets/schemas.py `serialize_decimal`].

### Pattern 4: FastAPI WebSocket endpoint (public, with ping/pong)
**What:** `@app.websocket("/ws/markets/{market_id}")` — accept (public, no auth), register with the manager, loop on `receive_text()` answering `ping`→`pong`, clean up on `WebSocketDisconnect` in `finally`.
**When to use:** Verbatim from spike (only the path changes from `/ws/prices/` to `/ws/markets/` to match CONTEXT).
**Example:**
```python
# Source: spike_ws_server.py ws_prices()
@realtime_router.websocket("/ws/markets/{market_id}")
async def ws_market(websocket: WebSocket, market_id: str):
    await manager.connect(market_id, websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(market_id, websocket)
```
> **WS auth is public by design (CONTEXT Area 3) and this is the correct call:** the browser WebSocket API cannot set `Authorization` headers and CORS does not apply to WebSocket handshakes the way it does to HTTP, so a Bearer-on-WS pattern would be fragile [CITED: websocket.org/guides/frameworks/fastapi]. Odds are already public (same data as `GET /api/v1/markets`). Bet placement stays on the authenticated REST endpoint.

### Pattern 5: Server-side price-history downsampling (SQL bucketing)
**What:** A new endpoint `GET /api/v1/markets/{slug}/price-history?window=24h|7d|30d`. For 24h/7d return raw `OddsSnapshot` rows for the YES outcome; for 30d bucket to ~hourly using Postgres `date_trunc('hour', snapshot_at)` (or `date_bin`) and take one representative point per bucket (e.g. `last`/`avg` probability).
**When to use:** Always — never ship 30 days of 5-min snapshots (~8,640 points/outcome) to the browser.
**Example:**
```python
# Source: codebase OddsSnapshot model + SQLAlchemy 2 async patterns in markets/service.py
# 30d bucketed (one row per hour, latest snapshot in each bucket):
from sqlalchemy import func, select
yes_outcome_id = ...  # the outcome with label == "YES" for this market
bucket = func.date_trunc("hour", OddsSnapshot.snapshot_at).label("bucket")
stmt = (
    select(bucket, func.max(OddsSnapshot.snapshot_at).label("ts"))
    .where(OddsSnapshot.outcome_id == yes_outcome_id)
    .where(OddsSnapshot.snapshot_at >= cutoff_30d)
    .group_by(bucket).order_by(bucket)
)
# Then join back / re-select probability at each max(snapshot_at), or use DISTINCT ON.
# Serialize each point as {"ts": iso8601, "probability": str(prob)}  ← STRING, not float.
```
> **DISTINCT ON alternative (cleaner in Postgres):** `SELECT DISTINCT ON (date_trunc('hour', snapshot_at)) snapshot_at, probability ... ORDER BY date_trunc('hour', snapshot_at), snapshot_at DESC`. Both are fine; the planner picks one. The 24h/7d windows skip bucketing entirely (raw rows). `snapshot_at` and `probability` indices already exist via the FK `index=True` and the table is small per market. [VERIFIED: codebase markets/models.py OddsSnapshot]

### Pattern 6: Next.js SSR-initial + client-subscribe
**What:** The detail page is a Server Component that fetches market + price-history + activity once (matching the existing `MarketList` `cache: "no-store"` Server-Component pattern). It passes the initial odds/history into client components. The `use-market-socket` hook then opens the WS for live deltas and patches the odds in place.
**When to use:** This is THE integration pattern for the page. Do NOT fetch the chart/activity client-side; only the live odds delta is client-driven.
**Example:**
```typescript
// Source: codebase frontend/src/lib/api.ts (extend) + frontend/src/app/page.tsx (Server Component shell)
// lib/api.ts — server-side initial fetch (mirrors fetchMarkets):
export async function fetchMarket(slug: string): Promise<MarketDetail> {
  const res = await fetch(`${API_BASE}/api/v1/markets/${slug}`, { cache: "no-store" });
  if (res.status === 404) throw new MarketNotFound();
  if (!res.ok) throw new Error(`Failed to fetch market: ${res.status}`);
  return res.json();
}
```
```typescript
// hooks/use-market-socket.ts — "use client": connection + Live/Stale/Reconnecting state machine
// Source: spike index.html reconnect/stale pattern, ported to a React hook.
const MAX_RECONNECT_DELAY_MS = 30000;
type ConnState = "live" | "stale" | "reconnecting";
// onmessage: setOdds(delta); lastMsg = Date.now(); setState("live")
// setInterval 5s: if (Date.now() - lastMsg > 30000) setState("stale")  // KEEP last odds visible
// onclose: setState("reconnecting"); delay = min(1000 * 2**attempt, MAX) + jitter; reconnect
```
> **WS URL must use a `NEXT_PUBLIC_` env var** (browser-readable): `NEXT_PUBLIC_WS_URL` (e.g. `ws://localhost:8000` in dev, `wss://...` in prod). This is distinct from the Server-Action `BACKEND_URL` (server-only) and the Server-Component `NEXT_PUBLIC_API_URL`. The WS URL is read in the browser, so it MUST be `NEXT_PUBLIC_`-prefixed. [CITED: websocket.org/guides/frameworks/fastapi; corroborated by codebase api.ts using NEXT_PUBLIC_API_URL]

### Pattern 7: Order-entry form → confirm dialog → place_bet (reuse Phase 5 + Phase 2 auth)
**What:** rhf+zod form (Select YES/NO + Stake input) → on submit, open `BetConfirmDialog` showing stake/current-odds/expected-payout → on confirm, POST to `place_bet`. Errors mapped inline (no toast).
**When to use:** Exactly per UI-SPEC §"Order-entry form". Reuse the existing `ui/form.tsx` (`Form`/`FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormMessage`) and the auth `Server Action` + cookie-forward pattern from `lib/auth.ts`.
**Backend error → inline copy map (the authoritative status codes from `place_bet`):**

| Backend response (from `app/bets/router.py`) | UI inline message (UI-SPEC copy) |
|----------------------------------------------|----------------------------------|
| `402 PAYMENT_REQUIRED` (`InsufficientBalance`) | `Not enough play balance. Lower your stake or check your wallet.` |
| `409 CONFLICT` (`MarketClosed`) | `This market is closed and no longer accepting bets.` |
| `403` from `current_active_player` (unverified email, fastapi-users) | `Verify your email to place bets.` + link `Resend verification` → `/verify-email` |
| `403` "Account is banned…" (`current_betting_player`) | `Your account can't place bets right now. Contact support if you think this is a mistake.` |
| `422 UNPROCESSABLE_ENTITY` (stake limits `BET_MIN_STAKE`/`BET_MAX_STAKE`) | `Stake must be between {min} and {max} PLAY_USD.` |
| `422` (`InvalidOutcome`) | (defensive — should not happen via UI) generic fallback |
| `401` (unauthenticated) | Show `Log in to place a bet` affordance → `/login` (don't render a dead form) |
| any other non-2xx | `Your bet couldn't be placed. Try again.` |

> **Critical contract detail:** `place_bet` requires `market_id` (UUID) AND `outcome_id` (UUID), not the slug — `PlaceBetRequest{market_id, outcome_id, stake}` with `extra="forbid"` [VERIFIED: codebase bets/schemas.py]. The detail page's SSR fetch already returns the market id + outcome ids (`MarketRead.outcomes[].id`), so the form has them. **Expected payout** preview = `stake / current_odds_of_chosen_outcome` (the Phase 5 payout model: a winning bet pays `stake / odds_at_placement`) — display-only, computed from the string odds without lossy float math beyond rendering [VERIFIED: codebase bets/service.py + bets/models.py docstring].

### Pattern 8: Recent-activity feed (anonymized, server-side)
**What:** `GET /api/v1/markets/{slug}/activity` returns the last 20 `Bet` rows for the market, anonymized server-side to `{ outcome_label: "YES"|"NO", amount: str, created_at: iso }`. The endpoint MUST NOT return `user_id`/email/display_name.
**When to use:** For MKT-03's activity feed. Anonymization is a privacy requirement (CONTEXT Area 1) — strip identity in the query/serializer, not in the client.
**Example:**
```python
# Source: codebase bets/models.py Bet + markets join
# SELECT b.stake, b.created_at, o.label
#   FROM bets b JOIN outcomes o ON o.id = b.outcome_id
#  WHERE b.market_id = :id ORDER BY b.created_at DESC LIMIT 20
# Serialize: {"outcome": o.label, "amount": str(b.stake), "created_at": b.created_at.isoformat()}
# Client renders: "Someone backed {YES|NO} · {amount} PLAY_USD · {relative-time}"
```
> Note: `Bet.market_id`/`outcome_id` are plain UUIDs (FK added by integration migration 0005) — joining `outcomes` is valid since both tables exist post-integration. The amount is `Numeric(18,4)` money → string [VERIFIED: codebase bets/models.py].

### Anti-Patterns to Avoid
- **Re-designing the WS layer.** Spike 003 is VALIDATED; deviating risks re-introducing solved problems (backpressure, market isolation, reconnect). Lift, don't reinvent.
- **Publishing the odds delta before the DB transaction commits.** Clients would render a price that gets rolled back. Publish post-commit in both producer sites.
- **Adding `websockets` as a *server* dependency.** It's already bundled by `fastapi[standard]`/`uvicorn[standard]`; an explicit add is redundant. `websockets` is only needed in test clients. [CITED: spike "What to Avoid" #5]
- **Shipping raw 30d snapshots to the browser.** Always downsample server-side beyond 7d.
- **Float math on odds/money in the client.** Keep strings; only the rendered percentage/payout is computed, mirroring `odds-display.tsx`.
- **Fetching chart/activity data client-side.** SSR-fetch initial; only live odds deltas are client-driven.
- **Restoring stream state on reconnect.** Prices are live-only; history comes from `odds_snapshots`, not the socket. [CITED: spike "What to Avoid" #4]
- **Custom Tooltip typed as `TooltipProps`.** In Recharts 3.x the custom-content prop type is `TooltipContentProps` (renamed). [CITED: github.com/recharts/recharts/wiki/3.0-migration-guide]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process event delivery to sockets | A custom in-process event bus or DB-polling-from-FastAPI | Redis pub/sub (already in stack) + spike 003 subscriber | An in-process bus can't cross the Celery/uvicorn process boundary; DB polling defeats the "no polling" requirement. |
| WebSocket connection tracking + broadcast | A bespoke connection registry | spike 003 `ConnectionManager` (verbatim) | Already validated for isolation, backpressure, dead-socket pruning, 100-msg bursts. |
| Reconnect/backoff logic | A naive `setTimeout(reconnect, 1000)` loop | Exponential backoff + jitter (spike pattern) | Avoids thundering-herd reconnects; spike provides the exact formula. |
| Time-series line chart | SVG/canvas by hand | Recharts `LineChart`/`Line`/`XAxis`/`YAxis`/`ResponsiveContainer`/`Tooltip` | Axes, tooltips, responsive sizing, ticks are deceptively complex. |
| Form validation + error surfacing | Manual state + onChange validators | react-hook-form + zod + shadcn `ui/form.tsx` | The established project pattern (auth pages); `FormMessage` already styles inline errors. |
| Confirm modal / outcome select | A custom div-overlay / native `<select>` | shadcn `dialog` / `select` (hand-copy) | Accessibility (focus trap, ARIA, keyboard) is solved by Radix; matches the existing design system. |
| Decimal-as-string serialization | `float()` casts | The existing `field_serializer`/`PlainSerializer`/`DecimalStr` patterns | The money/odds-as-string convention is enforced project-wide; reuse it for new schemas. |

**Key insight:** The hardest problem in this phase (cross-process fan-out) already has a proven, tested, codebase-specific solution. The planner's job is integration discipline (wire it into the real lifespan, real models, real producer sites), not invention.

## Runtime State Inventory

> This phase is **additive/greenfield**, not a rename/refactor/migration. No stored strings are being renamed. The "runtime state" relevant here is the *producer-side hooks* that must be added so the new WS receives events — captured below for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None being renamed. `OddsSnapshot` rows already accumulate (5-min cadence via `snapshot_odds`) — the price-history source is already populated. | None — read-only consumption. |
| Live service config | **Celery Beat schedule** (`app/celery_app.py` `beat_schedule`) already runs `poll_polymarket_top25` (30s) + `snapshot_odds` (5min). No new Beat task needed for Phase 9 (the producers are the EXISTING tasks; we add a publish call inside them). The schedule is RedBeat-backed in Redis. | Add `publish_odds_change()` *inside* the existing poll path + admin edit; do NOT add a new Beat entry. |
| OS-registered state | None. | None. |
| Secrets/env vars | NEW client env var **`NEXT_PUBLIC_WS_URL`** (browser-readable WS base, e.g. `ws://localhost:8000`). `REDIS_URL` already exists (Settings). No new backend secret. | Add `NEXT_PUBLIC_WS_URL` to frontend env (`.env.local` / docker-compose frontend env) + document in `.env.example`. |
| Build artifacts / installed packages | Frontend adds `recharts` + `react-is` + 2 Radix packages → `pnpm-lock.yaml` changes; the **pnpm `overrides` block** (Pitfall 1) must be present before `pnpm install` regenerates the lock. | `pnpm add ...` + add override + `pnpm install`; commit the updated lockfile. |

**Producer-hook verification (the canonical "what already writes odds" question):**
- **House odds edit** → `MarketService.update_market`, `if body.odds_yes is not None:` branch — updates `Outcome.current_odds` and inserts an `OddsSnapshot` [VERIFIED: codebase markets/service.py lines 126-142]. **This is producer site #1.**
- **Mirrored poll** → `PolymarketAdapter.sync_top25` — sets `existing_outcome.current_odds = price` (or inserts a new Outcome) on every sync [VERIFIED: codebase integrations/polymarket/adapter.py line 247]. **This is producer site #2.** Publish only when the value actually changed (compare pre/post) to avoid 30s-cadence noise on unchanged markets.

## Common Pitfalls

### Pitfall 1: Recharts renders a BLANK chart on React 19 (react-is version mismatch) — HIGHEST RISK frontend item
**What goes wrong:** After installing Recharts, the chart area is empty/blank with **no console error**. Reported repeatedly in 2026 against React 19.2.x (the project's `react@^19.0.0` resolves to **19.2.6** today).
**Why it happens:** Recharts depends on `react-is` (a first-party React utility for element-type checks). If the resolved `react-is` version does not exactly match the installed React version, Recharts' internal type checks silently fail and it renders nothing. With pnpm's strict node_modules, a transitively-resolved older `react-is` is the common culprit.
**How to avoid (the canonical fix):**
1. Install `react-is` pinned to the **exact** installed React version: `pnpm add react-is@19.2.6` (use whatever `node -p "require('react/package.json').version"` reports at plan time).
2. Add a pnpm override so ALL transitive `react-is` resolves to that version:
```json
// frontend/package.json
{
  "pnpm": { "overrides": { "react-is": "$react-is" } }
}
```
3. Re-run `pnpm install` and commit `pnpm-lock.yaml`.
**Warning signs:** Empty chart box, no error; `pnpm why react-is` shows two versions; the chart works in a fresh CRA but not in the app.
[VERIFIED: npm registry react-is@19.2.6 + CITED: github.com/recharts/recharts/issues/6857, bstefanski.com/blog/recharts-empty-chart-react-19]

### Pitfall 2: Recharts ResponsiveContainer needs a sized parent (no zero-height container)
**What goes wrong:** Even with the react-is fix, `<ResponsiveContainer>` collapses to 0 height if its parent has no explicit height, so the chart is invisible.
**Why it happens:** ResponsiveContainer measures its parent; a parent with `height: auto` and no content yields 0.
**How to avoid:** Give the chart wrapper a fixed height matching the skeleton (UI-SPEC: `h-64`/256px). Set `<ResponsiveContainer width="100%" height="100%">` inside a `className="h-64"` div. This also prevents layout shift between skeleton and chart (UI-SPEC requirement). [CITED: github.com/recharts/recharts/issues/4590 — historical React 19 ResponsiveContainer reports; the sized-parent rule is the standard mitigation]

### Pitfall 3: Publishing odds deltas before the transaction commits
**What goes wrong:** Client sees a price that the DB then rolls back (e.g., admin edit fails validation after the odds were published, or a poll upsert hits IntegrityError and rolls back).
**Why it happens:** Naively calling `publish_odds_change()` immediately after mutating `current_odds`, inside the transaction.
**How to avoid:** Publish **after** the surrounding `session.commit()` succeeds. In `update_market`, the router commits after the service returns — emit the publish in the router (post-commit) or pass the deltas back and publish there. In the poll path, publish only for markets whose sync committed successfully (the per-market loop already rolls back on IntegrityError and `continue`s).
**Warning signs:** Occasional price flicker that reverts within a second; "ghost" prices in the log that don't match the DB.

### Pitfall 4: WS subscriber task not cancelled on shutdown (or not started per worker)
**What goes wrong:** Either the subscriber leaks on reload (task never cancelled), or it's started outside the lifespan and never runs under multi-worker.
**Why it happens:** Forgetting the `finally: task.cancel()` in the lifespan, or starting the task at module import.
**How to avoid:** Start the task inside the existing `lifespan` `asynccontextmanager` and cancel it in `finally` (Pattern 2). Because lifespan runs once per worker process, each worker gets its own subscriber — which is exactly what makes multi-worker correct.
**Warning signs:** Sockets stop receiving after a reload; "Event loop is closed" on shutdown; broadcasts work with 1 worker but not 4.

### Pitfall 5: Stale badge that blanks the odds (UX trust violation)
**What goes wrong:** On >30s silence the UI clears the price or shows "—", making users think the market is broken.
**Why it happens:** Treating "stale" as "no data".
**How to avoid:** The Stale/Reconnecting states MUST keep the last-known odds rendered behind the amber badge (CONTEXT Area 4 + UI-SPEC color table). The hook keeps the last odds in state; only the indicator changes. `aria-live="polite"` announces the state change. [CITED: PITFALLS.md UX rule via CONTEXT/UI-SPEC]

### Pitfall 6: Generic error toast on the bet flow
**What goes wrong:** A "Transaction failed" toast hides which specific failure occurred (balance vs closed vs unverified vs banned).
**Why it happens:** Catch-all error handling.
**How to avoid:** Map each backend status to the specific inline message (Pattern 7 table), rendered via `FormMessage`/an inline `role="alert"` region. NO toast on the bet flow (CONTEXT Area 4). [VERIFIED: codebase bets/router.py status codes + UI-SPEC copy table]

### Pitfall 7: WS URL hardcoded or using a non-`NEXT_PUBLIC_` var
**What goes wrong:** The browser can't read `BACKEND_URL` (server-only); the socket connects to the wrong host or `undefined`.
**Why it happens:** Copying the Server-Action `BACKEND_URL` pattern into a client hook.
**How to avoid:** Use `process.env.NEXT_PUBLIC_WS_URL` in the `"use client"` hook (browser-exposed). Default to `ws://localhost:8000` in dev; `wss://` in prod (TLS). [VERIFIED: codebase api.ts uses NEXT_PUBLIC_API_URL for the analogous client/SSR case]

### Pitfall 8: Timezone / Decimal serialization on price-history and activity
**What goes wrong:** Chart x-axis times shift, or odds/amounts arrive as JSON floats (lossy).
**Why it happens:** Forgetting the project's string-on-wire convention for the NEW schemas, or naive `datetime` without tz.
**How to avoid:** All `OddsSnapshot.snapshot_at` / `Bet.created_at` are `DateTime(timezone=True)` — serialize as ISO-8601 with tz. Serialize `probability`/`stake`/odds as **strings** via the existing `field_serializer`/`DecimalStr` pattern. [VERIFIED: codebase models use timezone=True; schemas serialize Decimals as strings]

## Code Examples

### Wiring the realtime router into the existing app factory
```python
# Source: app/main.py (existing include_router block) + spike realtime router
from app.realtime.router import realtime_router   # @websocket("/ws/markets/{market_id}")
app.include_router(realtime_router)
# manager + redis_subscriber live in app/realtime/; lifespan starts/cancels the subscriber (Pattern 2)
```

### Recharts YES-probability line (3.x, React 19, sized container)
```typescript
// Source: recharts 3.x composition API (verified peer deps react@^19) + UI-SPEC color contract
"use client";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export function PriceHistoryChart({ points }: { points: { ts: string; probability: string }[] }) {
  if (points.length < 2) return <ChartEmptyState />;            // "Not enough price history yet"
  const data = points.map(p => ({ ts: p.ts, yes: Math.round(parseFloat(p.probability) * 100) }));
  return (
    <div className="h-64 w-full">                                {/* sized parent — Pitfall 2 */}
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke="#e4e4e7" strokeDasharray="3 3" />
          <XAxis dataKey="ts" tick={{ fontSize: 12, fill: "#71717a" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "#71717a" }} unit="%" />
          <Tooltip /* custom content prop type is TooltipContentProps in v3 */ />
          <Line type="monotone" dataKey="yes" stroke="#059669" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### pnpm override block (the react-is fix, in full)
```json
// frontend/package.json — Source: github.com/recharts/recharts/issues/6857 + pnpm overrides docs
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-is": "19.2.6",
    "recharts": "3.8.1"
  },
  "pnpm": { "overrides": { "react-is": "$react-is" } }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Recharts 2.x (no formal React 19 peer) | Recharts 3.x declares `react@^19` + `react-is@^19` as peer deps | 3.0 (2025) → latest 3.8.1 (2026-05-24) | Composition API preserved; custom Tooltip type renamed `TooltipProps`→`TooltipContentProps`; internal state mgmt rewritten (now uses Redux Toolkit internally — invisible to basic line charts). [CITED: recharts 3.0 migration guide] |
| react-is auto-resolves fine | react-is **must be pinned + overridden** to match React 19 or charts render blank | React 19.2.x era (2026) | The single most-reported Recharts+React-19 gotcha; mitigation is a one-line pnpm override. [CITED: github.com/recharts/recharts/issues/6857] |
| `broadcaster` / SSE for real-time | FastAPI native WS + `redis.asyncio` pub/sub | Project spike 003 (2026-05-27) | Zero new deps; sub-ms latency; validated. |
| Next 15 (Phase 1 pin) | **Next 16.2.6 + React 19** (current `package.json`) | package.json resolves `next@^16.2.6`, `react@^19.0.0` | App Router patterns hold; `async cookies()/headers()` already in use; the realtime hook is a standard `"use client"` component. [VERIFIED: codebase package.json] |

**Deprecated/outdated:**
- The STACK.md §10 note about pinning `react-is` for "Recharts 2.x" — still correct in spirit, but the project should install **Recharts 3.x** (latest) with `react-is` matched to React **19.2.6** (not 19.0.0). The mechanism (pin + pnpm override) is unchanged.
- spike 003 used path `/ws/prices/{market_id}` — CONTEXT locks `/ws/markets/{id}`. Rename the path; everything else lifts verbatim.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `react@^19.0.0` resolves to **19.2.6** at plan/install time (so `react-is` should pin to 19.2.6) | Standard Stack, Pitfall 1 | LOW — planner re-checks with `node -p "require('react/package.json').version"`; the override uses `$react-is` so it tracks whatever is installed regardless. |
| A2 | Recharts **3.8.1** is the version to install (latest 3.x on 2026-05-29) | Standard Stack | LOW — planner re-runs `npm view recharts version`; any current 3.x with the react-is override works. |
| A3 | The integration migration **0005** (adding FK from `bets` to `markets`/`outcomes`) has shipped by Phase 9, so the activity-feed join is valid | Pattern 8 | MEDIUM — if 0005 is not yet applied at execution time, the activity endpoint can still query by `Bet.market_id` (plain UUID) and join `outcomes` by `outcome_id`; the FK is not required for the SELECT. Planner verifies migration state. |
| A4 | Publishing from the poll path should be gated on an actual `current_odds` change (not every 30s tick) | Pattern 3, Pitfall 3 | LOW — worst case is extra no-op deltas (clients re-render identical odds). Recommended optimization, not correctness. |
| A5 | The detail page reuses the cookie-session Server-Action pattern (`lib/auth.ts`) for `place_bet`, forwarding `xpredict_session` | Pattern 7 | LOW — this mirrors the established login flow; the bet POST needs the session cookie, which the Server-Action cookie-forward pattern already handles. |
| A6 | `NEXT_PUBLIC_WS_URL` is the chosen client env var name | Pattern 6, Runtime State | LOW — naming is discretionary; any `NEXT_PUBLIC_`-prefixed var works. |

## Open Questions

1. **Should the price-history endpoint live on the market detail payload or a separate endpoint?**
   - What we know: `MarketRead` already returns `outcomes` with `current_odds`; the chart needs a *time series*, which is a different shape and can be large.
   - What's unclear: whether to embed a small initial window in the detail response or always fetch history separately.
   - Recommendation: **Separate endpoint** `GET /{slug}/price-history?window=` — keeps the detail payload small, lets the window toggle re-fetch without re-fetching the whole market, and matches the "fetch initial in Server Component" pattern (the page can call both in parallel server-side).

2. **Does publishing happen as sync `redis.publish` or async `aioredis.publish` in the poll task?**
   - What we know: the poll task already holds an `AioRedis` connection for the lock; a sync `redis.from_url().publish()` is simplest in `update_market` (request context).
   - What's unclear: whether to reuse the task's existing `AioRedis` for the publish vs a fresh sync client.
   - Recommendation: reuse the task's `AioRedis` in the poll path (`await redis.publish(...)`); use a short-lived sync `redis` client in the admin-edit router (post-commit). Both are trivial; the planner picks per-site.

3. **Window-toggle component: `tabs` vs `ToggleGroup` of buttons?**
   - UI-SPEC marks this executor's discretion. Recommendation: a `ToggleGroup` of `Button size="sm"` (lighter — no extra Radix `tabs` package to add), but `tabs` is acceptable.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Redis | WS pub/sub transport (MKT-04) | ✓ (docker-compose `redis` service; Celery broker + RedBeat) | 7.x (Phase 1) | — (hard requirement; already core infra) |
| `fastapi[standard]` (websockets bundled) | WS endpoint | ✓ | `>=0.115.7,<0.116.0` | — |
| `uvicorn[standard]` (WS protocol) | WS server | ✓ | `>=0.32,<0.36` | — |
| `redis.asyncio` (in `redis>=5.0`) | async subscriber | ✓ | `>=5.0,<6.0` | — |
| Node/pnpm (frontend build) | Recharts + Radix installs | ✓ | pnpm 9.15.0 pinned (docker) | — |
| Polymarket sync producing odds changes | MKT-04 mirrored-market path demo | ✓ (Phase 6 complete; poll runs every 30s) | — | For a deterministic demo, the **admin house-odds edit** path is fully self-contained (no external dep) — use it as the primary real-time demo trigger. |
| `recharts` / `react-is` / Radix dialog+select | chart + form UI | ✗ (NOT yet in package.json) | install this phase | — (must install; see Standard Stack) |

**Missing dependencies with no fallback:** none (Redis + FastAPI WS stack all present).
**Missing dependencies with fallback:** the frontend packages are not yet installed but installing them is the phase's own work; the admin-edit path is a self-contained real-time demo trigger that doesn't depend on live Polymarket movement.

## Validation Architecture

> `workflow.nyquist_validation` is **enabled** (config.json: `true`). This section lets a VALIDATION.md be derived.

### Test Framework
| Property | Value |
|----------|-------|
| Framework (backend) | `pytest` + `pytest-asyncio` (`loop_scope="session"` for integration); markers `integration`, `asyncio`. [VERIFIED: codebase test conventions in STATE.md decisions] |
| Framework (frontend) | `vitest` + `@testing-library/react` + `jsdom` (`pnpm test` = `vitest run`). [VERIFIED: codebase package.json] |
| Config file | backend: `pyproject.toml` pytest config; frontend: `vitest.config.*` (present — Phase 1 scaffold) |
| Quick run command (backend) | `cd backend && uv run pytest -x -m "not integration"` |
| Quick run command (frontend) | `cd frontend && pnpm test` |
| Full suite command | backend `uv run pytest` (incl. integration/testcontainers); frontend `pnpm test && pnpm build` |
| WS test client | `websockets` library (test-only) — connect to `/ws/markets/{id}`, publish to Redis, assert receipt (spike 003 `spike_ws_test.py` is the template). [CITED: spike "What to Avoid" #5 — websockets is test-only] |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MKT-04 | Publish→subscribe→broadcast delivers a delta to a connected WS client <2s | integration | `uv run pytest tests/realtime/test_ws_fanout.py -x` (publish to `prices:{id}`, assert client receives `{outcomes,ts}`) | ❌ Wave 0 |
| MKT-04 | Cross-market isolation: client on market A never gets market B deltas | integration | `uv run pytest tests/realtime/test_ws_isolation.py -x` | ❌ Wave 0 |
| MKT-04 | Admin odds edit publishes a delta (producer hook #1) | integration | `uv run pytest tests/markets/test_update_market_publishes.py -x` (patch redis.publish; PATCH odds; assert called post-commit) | ❌ Wave 0 |
| MKT-04 | Poll-path publishes on a real `current_odds` change (producer hook #2) | unit | `uv run pytest tests/integrations/test_poll_publishes.py -x` | ❌ Wave 0 |
| MKT-04 | Reconnect: a fresh connection immediately receives subsequent deltas | integration | `uv run pytest tests/realtime/test_ws_reconnect.py -x` | ❌ Wave 0 |
| MKT-03 | `GET /{slug}/price-history?window=7d` returns string-serialized points for the YES outcome | integration | `uv run pytest tests/markets/test_price_history.py -x` | ❌ Wave 0 |
| MKT-03 | 30d window is downsampled (point count << raw 5-min count) and renders without regression | integration | `uv run pytest tests/markets/test_price_history.py::test_30d_downsampled -x` (seed a 30-day backfill fixture per ROADMAP SC#2) | ❌ Wave 0 |
| MKT-03 | `GET /{slug}/activity` returns last 20 bets ANONYMIZED (no user_id/email in payload) | integration | `uv run pytest tests/markets/test_activity_feed.py -x` (negative assert: no `user_id` key) | ❌ Wave 0 |
| MKT-03 | Order form maps each backend status (402/409/403/422) to the specific inline copy | unit (frontend) | `pnpm test src/components/order-entry-form.test.tsx` | ❌ Wave 0 |
| MKT-03 | Chart renders (NOT blank) with the react-is override — sentinel that the override is in place | smoke (frontend) | `pnpm test src/components/price-history-chart.test.tsx` (assert SVG path present) + `pnpm build` | ❌ Wave 0 |
| MKT-04 | Live/Stale/Reconnecting state machine: >30s silence → Stale, odds still rendered | unit (frontend) | `pnpm test src/hooks/use-market-socket.test.ts` (fake timers) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest -x -m "not integration"` + `cd frontend && pnpm test` (the relevant new test files).
- **Per wave merge:** `cd backend && uv run pytest` (incl. realtime integration + testcontainers) + `cd frontend && pnpm test && pnpm build`.
- **Phase gate:** Full suite green before `/gsd-verify-work`. The WS fan-out + downsampling + anonymization tests are the load-bearing ones; the chart-renders smoke test is the react-is-override sentinel.

### Wave 0 Gaps
- [ ] `backend/tests/realtime/test_ws_fanout.py` — covers MKT-04 (publish→broadcast<2s)
- [ ] `backend/tests/realtime/test_ws_isolation.py` — covers MKT-04 (per-market isolation)
- [ ] `backend/tests/realtime/test_ws_reconnect.py` — covers MKT-04 (reconnect receives new deltas)
- [ ] `backend/tests/realtime/conftest.py` — WS test client (`websockets`) + fakeredis/real-redis pub/sub fixture
- [ ] `backend/tests/markets/test_update_market_publishes.py` — producer hook #1 (admin edit, post-commit)
- [ ] `backend/tests/integrations/test_poll_publishes.py` — producer hook #2 (poll on change)
- [ ] `backend/tests/markets/test_price_history.py` — price-history endpoint + 30d downsample (+ 30-day backfill fixture)
- [ ] `backend/tests/markets/test_activity_feed.py` — anonymized last-20 (negative: no user identity)
- [ ] `frontend/src/hooks/use-market-socket.test.ts` — connection state machine (fake timers)
- [ ] `frontend/src/components/order-entry-form.test.tsx` — backend-error→inline-copy mapping
- [ ] `frontend/src/components/price-history-chart.test.tsx` — chart-not-blank smoke (react-is sentinel)
- [ ] Test dep: confirm `websockets` is available as a backend test-only client (it ships with `fastapi[standard]`; otherwise `uv add --dev websockets`).

> **Note on fakeredis + pub/sub:** the project pins `fakeredis>=2.20`. fakeredis supports pub/sub, but cross-connection pub/sub semantics can differ from real Redis; the WS fan-out integration tests are most reliable against the **real** docker-compose `redis` service (mark them `integration`). The spike validated against real Redis.

## Sources

### Primary (HIGH confidence)
- **Codebase (authoritative for this repo):**
  - `.planning/spikes/003-websocket-price-streaming/{spike_ws_server.py, spike_ws_publisher.py, spike_ws_test.py, README.md}` — VALIDATED WS+pub/sub reference impl.
  - `.claude/skills/spike-findings-xpredict/references/real-time-streaming.md` + `SKILL.md` — synthesized spike findings + non-negotiable constraints.
  - `backend/app/{main.py, celery_app.py, core/config.py, db/session.py, db/types.py}` — app factory, lifespan, Beat schedule, Settings, money/odds aliases.
  - `backend/app/markets/{models.py, router.py, service.py, schemas.py}` — Market/Outcome/OddsSnapshot, public endpoints, update_market odds branch (producer #1), string serializers.
  - `backend/app/integrations/polymarket/{tasks.py, adapter.py}` — poll/snapshot tasks, `sync_top25` current_odds update (producer #2).
  - `backend/app/bets/{router.py, service.py, schemas.py, models.py}` — `place_bet` contract + status codes, payout model, Bet rows for activity feed.
  - `frontend/{package.json, src/lib/api.ts, src/lib/auth.ts, src/app/page.tsx, src/components/{market-list,odds-display,market-list-skeleton,ui/card,ui/button}.tsx}` — Next 16/React 19, Server-Component + Server-Action patterns, design primitives.
  - `.planning/phases/09-.../{09-CONTEXT.md, 09-UI-SPEC.md}`, `.planning/{REQUIREMENTS.md, ROADMAP.md, config.json, STATE.md}` — locked decisions + requirements.
- **npm registry (verified live 2026-05-29):** `recharts@3.8.1` (peer `react@^19`, `react-is@^19`); `react-is@19.2.6`; `fastapi[standard]`/`uvicorn[standard]`/`redis>=5.0` present in `backend/pyproject.toml`.

### Secondary (MEDIUM confidence — verified against authoritative source)
- FastAPI WebSockets docs — https://fastapi.tiangolo.com/advanced/websockets/ (native WS, accept/receive/disconnect).
- Recharts 3.0 migration guide — https://github.com/recharts/recharts/wiki/3.0-migration-guide (composition API preserved; `TooltipProps`→`TooltipContentProps`; ResponsiveContainer change; min React 16.8).
- WebSocket scaling + multi-worker + Redis pub/sub + CORS-doesn't-apply-to-WS — https://websocket.org/guides/frameworks/fastapi/ (corroborates per-worker independent subscribe).

### Tertiary (LOW confidence — community, used only for the react-is fix which is corroborated by the GitHub issue)
- Recharts blank-chart-on-React-19 issue — https://github.com/recharts/recharts/issues/6857 (the react-is override; "needs reproduction" but the override is the consistently-reported fix).
- Recharts empty chart + React 19 fix (pnpm override syntax) — https://www.bstefanski.com/blog/recharts-empty-chart-react-19/.
- Historical ResponsiveContainer + React 19 — https://github.com/recharts/recharts/issues/4590.

## Metadata

**Confidence breakdown:**
- **Standard stack: HIGH** — backend deps verified present in pyproject; frontend deps verified on npm registry; WS approach is a VALIDATED in-repo spike.
- **Architecture: HIGH** — the WS pipeline is lifted from a passing spike; producer hook sites are confirmed in the actual codebase (`update_market`, `sync_top25`); the SSR-initial + client-subscribe pattern mirrors existing code.
- **Pitfalls: HIGH for the WS/producer pitfalls** (grounded in codebase + spike), **MEDIUM-HIGH for the Recharts react-is pitfall** (reproduced across multiple 2026 reports + a first-party-package fix; the GitHub issue itself is "needs reproduction" but the override is the canonical, widely-confirmed mitigation).
- **Validation architecture: HIGH** — test framework + commands verified in codebase; the spike's own 6-test suite is the template for the WS tests.

**Research date:** 2026-05-29
**Valid until:** 2026-06-12 for the Recharts/react-is version specifics (fast-moving React 19.x + Recharts 3.x — re-verify `react`/`react-is`/`recharts` versions at plan time); ~30 days for the architecture/pattern sections (codebase-grounded, stable).
