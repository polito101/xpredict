# Phase 9: User App UX Polish (Market Detail & Real-Time) - Pattern Map

**Mapped:** 2026-05-29
**Files analyzed:** 24 new/modified (11 backend, 13 frontend)
**Analogs found:** 22 with a strong analog / 24 total (2 genuinely new: the WS client hook + the Recharts chart, both with a spike/UI-SPEC reference instead of a codebase analog)

> All paths are relative to the repo root `backend/` and `frontend/` unless noted. Line numbers are from the files read at mapping time; treat them as anchors, re-confirm the exact lines before copying.
>
> **The headline:** the highest-risk piece (cross-process WS fan-out) is a VALIDATED in-repo spike (`.planning/spikes/003-websocket-price-streaming/`). Lift it almost verbatim into `app/realtime/`. Everything else follows an existing codebase analog closely.

---

## File Classification

### Backend (FastAPI / SQLAlchemy 2 async)

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `app/realtime/manager.py` (NEW) | service (connection registry) | streaming / pub-sub | `.planning/spikes/003-.../spike_ws_server.py` `ConnectionManager` (lines 35-75) | exact (lift verbatim) |
| `app/realtime/subscriber.py` (NEW) | service (background task) | event-driven / pub-sub | `spike_ws_server.py` `redis_subscriber` (lines 97-143) | exact (lift, drop forensic event_log) |
| `app/realtime/publisher.py` (NEW) | utility (producer publish) | pub-sub | `spike_ws_publisher.py` (lines 31-45) + RESEARCH Pattern 3 | exact (shape) |
| `app/realtime/router.py` (NEW) | route (WebSocket endpoint) | streaming / request-response | `spike_ws_server.py` `ws_prices` (lines 175-189) | exact (rename path `/ws/prices/` → `/ws/markets/`) |
| `app/main.py` (MODIFIED) | config (app factory + lifespan) | — | self — existing `lifespan` (lines 83-92) + `include_router` block (lines 140-149) | exact (extend in place) |
| `app/markets/router.py` (MODIFIED) | route / controller | request-response (CRUD read) | self — `get_market_public` (lines 140-148), `bet_check` (lines 151-169) | exact (add 2 GET endpoints) |
| `app/markets/service.py` (MODIFIED) | service | CRUD read + pub-sub hook | self — `get_market_by_slug` (lines 263-277), `update_market` odds branch (lines 126-142) | exact |
| `app/markets/schemas.py` (MODIFIED) | model (Pydantic) | transform (Decimal→string) | self — `OutcomeRead.serialize_decimal` (lines 73-85), `MarketRead` (lines 87-111) | exact |
| `app/integrations/polymarket/tasks.py` (MODIFIED) | service (Celery task) | event-driven + pub-sub hook | self — `_run_poll_sync` (lines 60-111) | exact (add publish on change) |
| `app/integrations/polymarket/adapter.py` (MODIFIED) | service (sync adapter) | transform + pub-sub hook | self — `sync_top25` outcome upsert (lines 230-258) | exact (return/track changed) |
| `app/celery_app.py` (REVIEW, likely NO CHANGE) | config (Beat schedule) | — | self — `beat_schedule` (lines 48-64) | N/A — research says NO new Beat task |

### Frontend (Next.js 16 / React 19 / Tailwind 4 / shadcn)

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `src/app/markets/[slug]/page.tsx` (NEW) | route / page (Server Component) | request-response (SSR fetch) | `src/app/page.tsx` (Suspense shell) + `src/app/portfolio/page.tsx` (cookie-forward fetch) | exact |
| `src/components/market-detail-skeleton.tsx` (NEW) | component (skeleton) | — | `src/components/market-list-skeleton.tsx` | exact |
| `src/components/recent-activity-feed.tsx` (NEW) | component | request-response (read list) | `src/app/portfolio/page.tsx` list rendering (lines 122-141) + `market-list.tsx` empty state | role-match |
| `src/components/order-entry-form.tsx` (NEW, `"use client"`) | component (form) | request-response (POST) | `src/app/(auth)/login/login-form.tsx` (rhf+zod+useActionState) | exact |
| `src/components/bet-confirm-dialog.tsx` (NEW, `"use client"`) | component (modal) | — | NEW shadcn `dialog` (hand-copy) — no in-repo analog; pattern = `ui/form.tsx`/`button.tsx` header convention | partial |
| `src/components/price-history-chart.tsx` (NEW, `"use client"`) | component (chart) | transform (render) | **NO ANALOG** — Recharts is new; reference = RESEARCH Code Examples + UI-SPEC chart contract | new-file |
| `src/components/live-indicator.tsx` (NEW, `"use client"`) | component | — | `src/components/odds-display.tsx` (semantic color + small-chip pattern) | role-match |
| `src/components/ui/dialog.tsx` (NEW, hand-copy) | component (primitive) | — | `src/components/ui/form.tsx` / `button.tsx` (hand-copy convention + `cn` alias) | exact (convention) |
| `src/components/ui/select.tsx` (NEW, hand-copy) | component (primitive) | — | same as dialog | exact (convention) |
| `src/hooks/use-market-socket.ts` (NEW, `"use client"`) | hook | streaming (WS client) | **NO ANALOG** (first client-side data path) — reference = spike `index.html` reconnect + RESEARCH Pattern 6 | new-file |
| `src/lib/api.ts` (MODIFIED) | utility (fetch + types) | request-response | self — `fetchMarkets` (lines 42-52), `MarketItem`/`MarketOutcome` types (lines 9-31), formatters (lines 63-103) | exact |
| `src/lib/bet-actions.ts` (NEW, `"use server"`) | utility (Server Action) | request-response (POST + cookie) | `src/lib/auth.ts` `loginAction` + cookie-forward (lines 68-121) + `portfolio/page.tsx` `loadPortfolio` cookie-read (lines 65-83) | exact |
| `src/lib/bet-schemas.ts` (NEW) | model (zod) | — | `src/lib/auth-schemas.ts` (`LoginSchema`, `ActionState`, lines 13-82) | exact |

---

## Shared Patterns

These cross-cutting patterns apply to MANY files below — read them once, apply everywhere.

### SP-1: Money / odds as STRING on the wire (project non-negotiable)
**Apply to:** every new backend schema (price-history points, activity items, WS delta) AND every frontend type/render.
**Backend source:** `app/markets/schemas.py` lines 81-85
```python
@field_serializer("initial_odds", "current_odds")
@classmethod
def serialize_decimal(cls, v: Decimal) -> str:
    return str(v)
```
**Alternative serializer (annotated type, used in bets):** `app/bets/schemas.py` lines 20-23
```python
DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
]
```
**Column types** (`app/db/types.py` lines 20-28): `Money = Numeric(18,4)`, `Odds = Numeric(8,6)`. `OddsSnapshot.probability` and `Outcome.current_odds` are `Odds`; `Bet.stake` is `Money`. Both serialize to string.
**Frontend rule** (`portfolio/page.tsx` lines 36-41 + comment lines 10-12): types are `string`, never `parseFloat` for storage — only round for display, e.g. `Math.round(parseFloat(current_odds) * 100)` (`market-card.tsx` line 39).

### SP-2: Datetime is `DateTime(timezone=True)` → serialize ISO-8601
**Apply to:** price-history `ts`, activity `created_at`.
**Source:** `app/markets/models.py` `OddsSnapshot.snapshot_at` (lines 208-211), `app/bets/models.py` `Bet.created_at` (lines 59-61) — both `DateTime(timezone=True)`, `server_default=func.now()`. Pydantic serializes `datetime` to ISO automatically; keep tz.

### SP-3: Public-read endpoints are unauthenticated on `public_market_router`
**Apply to:** new `GET /{slug}/price-history` and `GET /{slug}/activity`, and the WS endpoint.
**Source:** `app/markets/router.py` lines 125-148 — `public_market_router = APIRouter(prefix="/api/v1/markets", tags=["markets"])`, no auth dependency. The WS is also public (RESEARCH Pattern 4 + CONTEXT Area 3).

### SP-4: Decimal→string is the ONLY transform; never JSON float (PITFALLS #4)
Repeated for emphasis: `_latency_ms`/forensic fields from the spike are dev-only and MUST NOT ship in the production WS payload. The production delta is exactly `{type, market_id, outcomes:[{outcome_id, odds}], ts}` (CONTEXT Area 3).

### SP-5: SSR-fetch initial, client-subscribe deltas (frontend data path)
**Apply to:** the whole detail page. Server Component fetches market + history + activity (matches `MarketList` `cache:"no-store"`); only the live odds delta is client-driven (the `use-market-socket` hook). Do NOT fetch chart/activity client-side. Source: `market-list.tsx` (Server Component fetch), `portfolio/page.tsx` (server cookie-forward), RESEARCH Pattern 6 + Anti-Patterns.

### SP-6: shadcn hand-copy convention (no CLI, no registry)
**Apply to:** new `ui/dialog.tsx`, `ui/select.tsx`.
**Source:** `ui/button.tsx` header (lines 1-8) + `ui/form.tsx` header (lines 1-8): copy canonical "new-york", change ONLY the `cn` import to `@/lib/utils`, keep zinc palette + `dark:` variants. Each new primitive's Radix package must be `pnpm add`-ed (`@radix-ui/react-dialog`, `@radix-ui/react-select`) — see RESEARCH Standard Stack.

### SP-7: Env var prefixing (the WS-URL gotcha)
- Server-only (Server Actions / SSR fetch): `process.env.BACKEND_URL` (`auth.ts` line 50, `portfolio/page.tsx` line 57).
- Browser-readable (Server Component fetch): `process.env.NEXT_PUBLIC_API_URL` (`api.ts` lines 35-36).
- **NEW, browser WS (in the `"use client"` hook): `process.env.NEXT_PUBLIC_WS_URL`** — MUST be `NEXT_PUBLIC_`-prefixed or the browser reads `undefined` (RESEARCH Pitfall 7). Add to `.env.example` + docker-compose frontend env.

---

## Pattern Assignments — Backend

### `app/realtime/manager.py` (NEW — service, pub-sub)

**Analog:** `.planning/spikes/003-websocket-price-streaming/spike_ws_server.py` lines 35-75 — **lift verbatim**, drop the `stats()` helper if unused.

```python
# spike_ws_server.py lines 35-72 — the VALIDATED ConnectionManager (6/6 tests, avg 0.8ms)
class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, market_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if market_id not in self._connections:
                self._connections[market_id] = set()
            self._connections[market_id].add(ws)

    async def disconnect(self, market_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if market_id in self._connections:
                self._connections[market_id].discard(ws)
                if not self._connections[market_id]:
                    del self._connections[market_id]

    async def broadcast(self, market_id: str, data: dict[str, Any]) -> tuple[int, int]:
        async with self._lock:                       # snapshot client set UNDER the lock
            clients = list(self._connections.get(market_id, set()))
        sent = failed = 0
        stale: list[WebSocket] = []
        for ws in clients:                            # send OUTSIDE the lock (no head-of-line block)
            try:
                await ws.send_json(data)
                sent += 1
            except Exception:
                stale.append(ws); failed += 1
        for ws in stale:                              # prune dead sockets
            await self.disconnect(market_id, ws)
        return sent, failed
```
**Module-level singleton:** `manager = ConnectionManager()` (spike line 78). The subscriber + router both import this one instance.

---

### `app/realtime/subscriber.py` (NEW — background task, event-driven)

**Analog:** `spike_ws_server.py` `redis_subscriber` lines 97-143. Strip the forensic `log_event`/`_latency_ms`/`event_log` (dev-only). Read `REDIS_URL` from Settings, not the hardcoded spike constant.

```python
# spike_ws_server.py lines 97-143 (cleaned) + RESEARCH Pattern 2
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
            market_id = channel.removeprefix("prices:")     # spike used .replace(); removeprefix is cleaner
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
```
**Multi-worker note (RESEARCH Pattern 2):** each uvicorn worker runs its own lifespan → its own subscriber → broadcasts to its own local sockets. Multi-worker is correct with ZERO extra code.

---

### `app/realtime/publisher.py` (NEW — utility, pub-sub)

**Analog:** `spike_ws_publisher.py` lines 31-45 (payload shape) + RESEARCH Pattern 3. The PRODUCTION payload is the lean delta (CONTEXT Area 3), NOT the spike's `yes_price/no_price/volume_24h` fields.

```python
# RESEARCH Pattern 3 — payload contract = CONTEXT Area 3 lean delta
import json, time, redis
from app.core.config import get_settings

def publish_odds_change(market_id, deltas: list[dict]) -> None:
    # deltas = [{"outcome_id": str(o.id), "odds": str(o.current_odds)} for changed outcomes]
    payload = {
        "type": "price_update",
        "market_id": str(market_id),
        "outcomes": deltas,            # [{outcome_id, odds(string)}]  ← SP-1, SP-4
        "ts": time.time(),
    }
    r = redis.from_url(str(get_settings().REDIS_URL))
    r.publish(f"prices:{market_id}", json.dumps(payload))
```
> `REDIS_URL` is a `RedisDsn` Setting (`config.py` line 40). The poll path already holds an `AioRedis` (tasks.py line 24/73) — RESEARCH Open Q2 recommends `await aioredis...publish()` there and a short-lived sync `redis` client in the admin-edit router (post-commit). Either works.

---

### `app/realtime/router.py` (NEW — route, WebSocket)

**Analog:** `spike_ws_server.py` `ws_prices` lines 175-189. **Only the path changes** (`/ws/prices/` → `/ws/markets/`, per CONTEXT + RESEARCH "Deprecated" note). Use an `APIRouter` (the spike used `@app.websocket`) so it can be `include_router`-ed.

```python
# spike_ws_server.py lines 175-189 → APIRouter form, path renamed
realtime_router = APIRouter()

@realtime_router.websocket("/ws/markets/{market_id}")
async def ws_market(websocket: WebSocket, market_id: str):
    await manager.connect(market_id, websocket)      # public, no auth — SP-3 / RESEARCH Pattern 4
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

---

### `app/main.py` (MODIFIED — app factory + lifespan)

**Analog:** self. Two edits, both in patterns already present.

**1. Extend the EXISTING lifespan** (current, lines 83-92 — only configure_logging + init_sentry):
```python
# CURRENT app/main.py lines 83-92
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings)
    init_sentry(service="api", settings=settings,
                integrations=[FastApiIntegration(), SqlalchemyIntegration()])
    yield
```
Add (RESEARCH Pattern 2 — start subscriber, cancel in `finally`):
```python
    task = asyncio.create_task(redis_subscriber(manager, str(settings.REDIS_URL)))  # NEW
    try:
        yield
    finally:                                                                          # NEW
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
```

**2. Register the WS router** — mirror the existing late-import include block (lines 140-149):
```python
from app.realtime.router import realtime_router   # alongside the existing imports
app.include_router(realtime_router)                # alongside the existing include_router(...) calls
```
> `settings = Settings()` is already read at module load (line 50). `REDIS_URL` is on it (`config.py` line 40).

---

### `app/markets/router.py` (MODIFIED — 2 new public GET endpoints)

**Analog:** self — `get_market_public` (lines 140-148) is the exact shape (slug lookup → 404 → `model_validate`). Add to `public_market_router`.

```python
# Existing analog — app/markets/router.py lines 140-148
@public_market_router.get("/{slug}", response_model=MarketRead)
async def get_market_public(slug: str, session: Annotated[AsyncSession, Depends(get_async_session)]) -> MarketRead:
    market = await MarketService.get_market_by_slug(session, slug)
    if not market or market.status not in (MarketStatus.OPEN.value, MarketStatus.CLOSED.value):
        raise HTTPException(status_code=404, detail="Market not found")
    return MarketRead.model_validate(market)
```
**New endpoints to add (same skeleton):**
- `GET /{slug}/price-history?window=24h|7d|30d` → returns `PriceHistoryResponse` (use `Query` like `bet_check` neighbors). Window param via `Query(default="7d")`.
- `GET /{slug}/activity` → returns `list[ActivityItem]` (last 20, anonymized server-side).

> `MarketRead` (the detail payload) ALREADY includes `resolution_criteria` (schemas.py line 93) and `outcomes[].id`/`current_odds` (lines 73-85). MKT-03's "criteria + outcomes" need NO schema change — only the two NEW read endpoints are added. RESEARCH Open Q1: keep price-history a SEPARATE endpoint (not embedded in `MarketRead`).

---

### `app/markets/service.py` (MODIFIED — price_history, recent_activity, producer-hook #1)

**Analog A — read by slug** (lines 263-277): `get_market_by_slug` shows the `select(...).where(Market.slug == slug).options(selectinload(...))` pattern. The new `price_history(slug, window)` and `recent_activity(slug, 20)` use the same async `session.execute` + `scalars()` shape.

**Analog B — producer hook #1** is the `update_market` odds branch (lines 126-142) — **this is one of the two producer sites for MKT-04**:
```python
# app/markets/service.py lines 126-142 — VERIFIED producer site #1
if body.odds_yes is not None:
    odds_no = Decimal("1") - body.odds_yes
    stmt = select(Outcome).where(Outcome.market_id == market.id)
    result = await session.execute(stmt)
    for outcome in result.scalars():
        if outcome.label == "YES":
            outcome.current_odds = body.odds_yes
        else:
            outcome.current_odds = odds_no
        session.add(OddsSnapshot(market_id=market.id, outcome_id=outcome.id,
                                 probability=outcome.current_odds))
    changed_fields.append("odds")
```
**Hook placement (RESEARCH Pitfall 3 — publish POST-COMMIT):** `service.update_market` only `flush()`es; the COMMIT happens in `router.update_market` (router lines 99). So collect the deltas in the service and `publish_odds_change()` in the ROUTER after `await session.commit()`, OR have the service return the deltas. Never publish inside the transaction.

**Price-history downsampling (RESEARCH Pattern 5):** 24h/7d → raw `OddsSnapshot` rows for the YES outcome; 30d → bucket hourly via `func.date_trunc("hour", OddsSnapshot.snapshot_at)` (or `DISTINCT ON`). Serialize each point `{ts: iso, probability: str}` (SP-1, SP-2). The `OddsSnapshot.outcome_id`/`snapshot_at` are indexed (models.py lines 201-211).

**Recent-activity (RESEARCH Pattern 8 — anonymize server-side):** `SELECT b.stake, b.created_at, o.label FROM bets b JOIN outcomes o ON o.id = b.outcome_id WHERE b.market_id = :id ORDER BY b.created_at DESC LIMIT 20`. Serialize `{outcome: o.label, amount: str(b.stake), created_at: iso}` — **NEVER** `user_id`/email. `Bet.market_id`/`outcome_id` are plain UUIDs (`bets/models.py` lines 50-51); the join is valid post-integration-migration 0005 (RESEARCH Assumption A3).

---

### `app/markets/schemas.py` (MODIFIED — new response schemas)

**Analog:** `OutcomeRead` (lines 73-85) for the `field_serializer` Decimal→string idiom; `MarketRead` (lines 87-111) for the `model_config = ConfigDict(from_attributes=True)` + field-serializer composite.

**New schemas to add (all strings on the wire — SP-1):**
```python
class PricePoint(BaseModel):
    ts: datetime                       # ISO-8601, tz-aware (SP-2)
    probability: Decimal               # YES probability
    @field_serializer("probability")   # ← copy from OutcomeRead.serialize_decimal (lines 81-85)
    @classmethod
    def _s(cls, v: Decimal) -> str: return str(v)

class PriceHistoryResponse(BaseModel):
    window: str                        # "24h" | "7d" | "30d"
    points: list[PricePoint]

class ActivityItem(BaseModel):         # anonymized — NO user identity (RESEARCH Pattern 8)
    outcome: str                       # "YES" | "NO"
    amount: Decimal                    # str on wire
    created_at: datetime
    @field_serializer("amount")
    @classmethod
    def _s(cls, v: Decimal) -> str: return str(v)
```

---

### `app/integrations/polymarket/tasks.py` + `adapter.py` (MODIFIED — producer-hook #2)

**Analog:** self. This is **producer site #2** for MKT-04.

**Where odds change (`adapter.py` `sync_top25`, lines 245-256 — VERIFIED):**
```python
# app/integrations/polymarket/adapter.py lines 245-256
existing_outcome = existing.scalar_one_or_none()
if existing_outcome:
    existing_outcome.current_odds = price          # ← the change to detect/publish
else:
    session.add(Outcome(market_id=market.id, label=label[:50],
                        initial_odds=price, current_odds=price))
```
**Hook (RESEARCH Pattern 3 + Pitfall 4 — publish only on ACTUAL change):** compare `existing_outcome.current_odds != price` before assigning; collect changed `(market_id, [deltas])`. Publish AFTER the poll's `await session.commit()` (`tasks.py` line 96), per-market, only for markets whose sync committed (the per-market loop already `rollback()`+`continue`s on `IntegrityError`, adapter.py lines 265-271). The poll task already holds `AioRedis` (`tasks.py` line 24, 73) — reuse it for `await redis.publish(...)`.

> **Do NOT add a new Beat task** (RESEARCH Runtime State + celery_app.py lines 48-64). The producers are the EXISTING `poll_polymarket_top25` (30s) + the admin edit; the publish call goes INSIDE them. `celery_app.py` likely needs no change.

---

## Pattern Assignments — Frontend

### `src/app/markets/[slug]/page.tsx` (NEW — Server Component shell)

**Analog A — Suspense shell** (`src/app/page.tsx` lines 11-20):
```tsx
// app/page.tsx — the page-shell + Suspense pattern to mirror
export default function Home() {
  return (
    <main className="w-full max-w-6xl mx-auto px-4 sm:px-6 py-12">
      <h1 className="text-xl font-semibold mb-8">Markets</h1>
      <Suspense fallback={<MarketListSkeleton />}>
        <MarketList />
      </Suspense>
    </main>
  );
}
```
**Analog B — server-side data load** (`portfolio/page.tsx` `loadPortfolio`, lines 65-83): async function, `BACKEND_URL` (server) or `NEXT_PUBLIC_API_URL` (via `api.ts` helpers), graceful degrade. Detail page fetches market + history + activity in parallel server-side (RESEARCH Open Q1).
**Layout contract (UI-SPEC):** `max-w-6xl mx-auto px-4 sm:px-6 py-12`, `grid grid-cols-1 lg:grid-cols-3 gap-8`, sticky right panel `lg:sticky lg:top-8`, H1 `text-3xl font-semibold tracking-tight`. 404 → "Market not found" copy + `Back to markets` link.

---

### `src/lib/api.ts` (MODIFIED — fetchers + types)

**Analog:** self. `fetchMarkets` (lines 42-52) is the exact `fetch(..., {cache:"no-store"})` + `res.ok` guard shape. `MarketItem`/`MarketOutcome` (lines 9-31) are the type-shape convention (all string money/odds).

```ts
// api.ts lines 42-52 — the fetch idiom to copy for fetchMarket / fetchPriceHistory / fetchActivity
export async function fetchMarkets(): Promise<MarketItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/markets`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch markets: ${res.status}`);
  return res.json() as Promise<MarketItem[]>;
}
```
**Add:** `MarketDetail` (extends `MarketItem` with `resolution_criteria: string` — note `MarketRead` already returns it), `PricePoint {ts: string; probability: string}`, `ActivityItem {outcome: "YES"|"NO"; amount: string; created_at: string}`, and `fetchMarket(slug)` / `fetchPriceHistory(slug, window)` / `fetchActivity(slug)`. A 404 in `fetchMarket` should throw a typed `MarketNotFound` (RESEARCH Pattern 6) so the page renders the not-found state. Keep `API_BASE = NEXT_PUBLIC_API_URL` (lines 35-36).

---

### `src/lib/bet-schemas.ts` (NEW — zod) + `src/lib/bet-actions.ts` (NEW — Server Action)

**Analog (schemas):** `src/lib/auth-schemas.ts` (lines 13-82) — zod schemas + the `ActionState`/`ActionErrors` discriminated-union return contract live in a SEPARATE file from the `"use server"` action (Next forbids non-async exports from `"use server"` files — auth-schemas.ts header lines 1-12).
```ts
// auth-schemas.ts lines 72-80 — the Server-Action return contract to reuse
export type ActionErrors = Record<string, string[] | undefined> & { _form?: string[] };
export type ActionState =
  | { errors: ActionErrors }
  | { success: true; message: string }
  | undefined;
```
**New:** `BetSchema = z.object({ outcome: z.enum(["YES","NO"]), stake: <positive decimal-as-string within min/max> })`. Client validation is pre-flight only; backend is authoritative (auth-schemas.ts header).

**Analog (action + cookie-forward):** `src/lib/auth.ts` `loginAction` (lines 92-121) + `forwardSessionCookie` (lines 68-86). The bet POST is cookie-gated; forward the player's `xpredict_session`. Two valid shapes:
- **Server Action** reading the cookie via `next/headers` `cookies()` and POSTing to `BACKEND_URL` (mirror `loginAction` exactly, but read the existing session cookie like `portfolio/page.tsx` lines 68-74 rather than re-setting one).
- The POST target is `POST /bets` (`bets/router.py` line 77) with body `{market_id, outcome_id, stake}` (`PlaceBetRequest`, `extra="forbid"`, `bets/schemas.py` lines 26-33) — **market_id + outcome_id are UUIDs, NOT slug** (RESEARCH Pattern 7 critical note; the SSR `MarketDetail.outcomes[].id` supplies them).

**Backend status → inline copy map** (RESEARCH Pattern 7 — authoritative, from `bets/router.py`):

| Backend (status, source) | Inline copy (UI-SPEC) |
|--------------------------|------------------------|
| `402` `InsufficientBalance` (router line 115) | `Not enough play balance. Lower your stake or check your wallet.` |
| `409` `MarketClosed` (router line 111) | `This market is closed and no longer accepting bets.` |
| `403` unverified (`current_active_player`) | `Verify your email to place bets.` + link `Resend verification` → `/verify-email` |
| `403` banned (`current_betting_player`, router lines 58-62) | `Your account can't place bets right now. Contact support…` |
| `422` stake limits (router lines 93-97; `BET_MIN_STAKE=1`, `BET_MAX_STAKE=100000`, config.py 80-81) | `Stake must be between {min} and {max} PLAY_USD.` |
| `401` unauthenticated | `Log in to place a bet` affordance → `/login` (don't render a dead form) |
| any other non-2xx | `Your bet couldn't be placed. Try again.` |

> **No generic toast** on the bet flow (CONTEXT Area 4 / RESEARCH Pitfall 6). Render inline via `FormMessage` / a `role="alert"` region.

---

### `src/components/order-entry-form.tsx` (NEW, `"use client"`)

**Analog:** `src/app/(auth)/login/login-form.tsx` (lines 1-127) — the canonical rhf + zod + `useActionState` + `Form`/`FormField`/`FormItem`/`FormControl`/`FormMessage` pattern.
```tsx
// login-form.tsx lines 35-64 — the form-wiring shape to copy
const [state, formAction, pending] = useActionState<ActionState, FormData>(loginAction, undefined);
const form = useForm<LoginValues>({ resolver: zodResolver(LoginSchema),
  defaultValues: { email: "", password: "" }, mode: "onSubmit" });
const formError = state && "errors" in state ? state.errors._form?.[0] : undefined;
const onSubmit = form.handleSubmit((values) => {
  const fd = new FormData(); fd.append("email", values.email); fd.append("password", values.password);
  startTransition(() => formAction(fd));
});
```
**Form-level error render** (login-form.tsx lines 112-120) → reuse verbatim for the bet-error region:
```tsx
{formError && (
  <p role="alert" className="text-sm font-medium text-red-500" data-testid="form-error">
    {formError}
  </p>
)}
```
**Fields (UI-SPEC §Order-entry form):** outcome `Select` (YES/NO, NEW `ui/select.tsx`), `Stake` `Input` (`inputMode="decimal"`, label `Stake (PLAY_USD)`), live "Expected payout" preview = `stake / current_odds_of_chosen` (display-only string math, RESEARCH Pattern 7). Primary CTA `Button size="lg"` (44px) labeled `Place bet`. On submit → open `BetConfirmDialog` (not direct POST). Disabled when market `CLOSED`; `Log in to place a bet` affordance when unauthenticated.

---

### `src/components/bet-confirm-dialog.tsx` (NEW, `"use client"`) + `ui/dialog.tsx`, `ui/select.tsx` (NEW hand-copy)

**Analog (primitives):** SP-6 — hand-copy canonical shadcn `dialog`/`select` (new-york), `cn` from `@/lib/utils`, keep zinc + `dark:`. `pnpm add @radix-ui/react-dialog @radix-ui/react-select` first (RESEARCH Standard Stack — not yet in package.json lines 14-29).
**Dialog content (UI-SPEC Copywriting):** title `Confirm your bet`; three rows `Stake → {stake} PLAY_USD`, `Current odds → {yes}% YES / {no}% NO`, `Expected payout → {payout} PLAY_USD`; footer `Odds may move before your bet is placed.`; buttons `Confirm bet` / `Cancel`. Only `Confirm bet` fires the Server Action.

---

### `src/components/price-history-chart.tsx` (NEW, `"use client"`) — **NO ANALOG**

**Reference:** RESEARCH Code Examples (lines 534-557) + UI-SPEC chart contract. Recharts is new to the repo — no codebase analog exists. Flag for the planner:

```tsx
"use client";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export function PriceHistoryChart({ points }: { points: { ts: string; probability: string }[] }) {
  if (points.length < 2) return <ChartEmptyState />;              // "Not enough price history yet" (UI-SPEC)
  const data = points.map(p => ({ ts: p.ts, yes: Math.round(parseFloat(p.probability) * 100) }));  // SP-1
  return (
    <div className="h-64 w-full">                                {/* sized parent — RESEARCH Pitfall 2 */}
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke="#e4e4e7" strokeDasharray="3 3" />
          <XAxis dataKey="ts" tick={{ fontSize: 12, fill: "#71717a" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "#71717a" }} unit="%" />
          <Tooltip /> {/* custom-content prop type is TooltipContentProps in Recharts 3.x — NOT TooltipProps */}
          <Line type="monotone" dataKey="yes" stroke="#059669" strokeWidth={2} dot={false} />  {/* emerald-600 */}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```
**CRITICAL GOTCHAS (RESEARCH Pitfall 1 + 2):**
- **`react-is` MUST pin to the exact installed React (19.2.6 today) + a pnpm override `{"pnpm":{"overrides":{"react-is":"$react-is"}}}` in `frontend/package.json`** — or the chart renders BLANK with no error. Re-verify with `node -p "require('react/package.json').version"` at plan time. This is the single highest-risk frontend item.
- Chart wrapper needs a fixed height (`h-64`/256px) — `ResponsiveContainer` collapses to 0 in an auto-height parent.
**Window toggle (24h/7d/30d, default 7d):** executor's discretion — `ToggleGroup` of `Button size="sm"` (lighter) or shadcn `tabs` (RESEARCH Open Q3 / UI-SPEC). Color contract: emerald-600 line, zinc-200 grid, no red/amber in the chart, YES-only (NO not plotted).

---

### `src/hooks/use-market-socket.ts` (NEW, `"use client"`) — **NO ANALOG**

**Reference:** spike `index.html` reconnect/stale logic ported to a React hook + RESEARCH Pattern 6. First client-side data path in the repo — no analog. Flag for the planner.
```ts
// RESEARCH Pattern 6 — the state machine contract
const MAX_RECONNECT_DELAY_MS = 30000;
type ConnState = "live" | "stale" | "reconnecting";
// new WebSocket(`${process.env.NEXT_PUBLIC_WS_URL}/ws/markets/${marketId}`)   ← SP-7
// onmessage: parse delta → setOdds(delta); lastMsg = Date.now(); setState("live")
// setInterval(5s): if (Date.now() - lastMsg > 30000) setState("stale")  // KEEP last odds visible (Pitfall 5)
// onclose: setState("reconnecting"); delay = min(1000 * 2**attempt, MAX) + jitter; reconnect
// send "ping" periodically; server answers {type:"pong"} (matches realtime/router.py)
```
**State→UX (UI-SPEC connection-state table + Pitfall 5):** `live` = emerald pulsing dot + "Live"; `stale` (>30s) = solid amber + "Stale", **odds stay rendered**; `reconnecting` = pulsing amber + "Reconnecting…". `aria-live="polite"`. NEVER blank the odds.

---

### `src/components/live-indicator.tsx` (NEW, `"use client"`)

**Analog:** `src/components/odds-display.tsx` (lines 12-49) — the small inline cluster + semantic color idiom (`text-emerald-700 dark:text-emerald-400` for YES). Dot is `h-2 w-2` rounded; label `text-xs`; colors per UI-SPEC table (emerald=Live, amber=Stale/Reconnecting). Driven by the hook's `ConnState`.

---

### `src/components/recent-activity-feed.tsx` (NEW)

**Analog:** `portfolio/page.tsx` list rendering (lines 122-141 — `ul`/`li` + `Card` rows + empty-state `<p data-testid>`) and `market-list.tsx` empty state (lines 27-38). Renders anonymized rows `Someone backed {YES|NO} · {amount} PLAY_USD · {relative-time}` (UI-SPEC). YES/NO token uses emerald/rose `text-xs`. Empty: `No bets yet` / `Be the first to make a prediction on this market.` Last-20 comes from `fetchActivity(slug)` (SSR).

---

### `src/components/market-detail-skeleton.tsx` (NEW)

**Analog:** `src/components/market-list-skeleton.tsx` (lines 1-37) — `Card` + `Skeleton` blocks, `aria-busy`/`aria-hidden`, same box dimensions as resolved content (no layout shift). Mirror the two-column shell: title, criteria block, a `h-64` chart-area block (matches the chart wrapper), order panel.

```tsx
// market-list-skeleton.tsx lines 10-24 — the skeleton-box idiom to copy
function SkeletonCard() {
  return (
    <Card>
      <CardHeader className="p-6 pb-2"><Skeleton className="h-12 w-full" aria-hidden="true" /></CardHeader>
      <CardContent className="p-6 pt-0"><Skeleton className="h-8 w-full" aria-hidden="true" /></CardContent>
      <CardFooter className="p-6 pt-0"><Skeleton className="h-4 w-3/4" aria-hidden="true" /></CardFooter>
    </Card>
  );
}
```

---

### `src/components/market-card.tsx` (already links to detail — NO CHANGE expected)

`market-card.tsx` line 51 already links `href={`/markets/${market.slug}`}` — the home→detail link exists. No change unless the planner wants live odds on cards (out of scope).

---

## Reuse-Verbatim (no new file, just import)

| Component | Source | Used by |
|-----------|--------|---------|
| `OddsDisplay` | `src/components/odds-display.tsx` | Detail live-odds block (canonical YES/NO renderer) |
| `SourceBadge` | `src/components/source-badge.tsx` | Detail header source chip |
| `Card`/`Button`/`Input`/`Badge`/`Skeleton`/`Form*`/`Label` | `src/components/ui/*` | Throughout |
| `cn` | `src/lib/utils.ts` | Every new component |

---

## No Analog Found

| File | Role | Data Flow | Reason | Reference to use instead |
|------|------|-----------|--------|--------------------------|
| `src/components/price-history-chart.tsx` | component (chart) | transform | Recharts is new to the repo (not in package.json) — no chart exists | RESEARCH Code Examples (lines 534-557) + UI-SPEC chart contract; **react-is pin + pnpm override is mandatory** |
| `src/hooks/use-market-socket.ts` | hook | streaming (WS client) | First client-side data path; no `hooks/` dir, no client fetch exists | spike `index.html` reconnect + RESEARCH Pattern 6; `NEXT_PUBLIC_WS_URL` (SP-7) |

> Both `app/realtime/*` files are technically "new files" but have an EXACT in-repo reference (the validated spike), so they are NOT listed here — they are lift-verbatim, the strongest possible analog.

---

## Metadata

**Analog search scope:**
- Backend: `.planning/spikes/003-websocket-price-streaming/`, `backend/app/{main.py, celery_app.py}`, `backend/app/markets/{router,service,schemas,models}.py`, `backend/app/bets/{router,schemas,service,models}.py`, `backend/app/integrations/polymarket/{tasks,adapter}.py`, `backend/app/core/config.py`, `backend/app/db/types.py`.
- Frontend: `frontend/package.json`, `frontend/src/lib/{api,auth,auth-schemas,utils}.ts`, `frontend/src/app/{page.tsx, portfolio/page.tsx, (auth)/login/login-form.tsx}`, `frontend/src/components/{market-card, market-list, market-list-skeleton, odds-display, source-badge}.tsx`, `frontend/src/components/ui/{form,button,card}.tsx`.

**Files scanned:** ~30 (all read in full or targeted ranges; no re-reads).
**Pattern extraction date:** 2026-05-29
**Upstream inputs:** `09-CONTEXT.md` (locked decisions), `09-RESEARCH.md` (712 lines — confirms hook sites, spike reuse, deps, pitfalls), `09-UI-SPEC.md` (component inventory + visual contract).
