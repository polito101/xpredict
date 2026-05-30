---
phase: 09-user-app-ux-polish-market-detail-real-time
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 42
files_reviewed_list:
  - backend/app/integrations/polymarket/adapter.py
  - backend/app/integrations/polymarket/tasks.py
  - backend/app/main.py
  - backend/app/markets/router.py
  - backend/app/markets/schemas.py
  - backend/app/markets/service.py
  - backend/app/realtime/__init__.py
  - backend/app/realtime/manager.py
  - backend/app/realtime/publisher.py
  - backend/app/realtime/router.py
  - backend/app/realtime/subscriber.py
  - backend/pyproject.toml
  - backend/tests/markets/test_activity_feed.py
  - backend/tests/markets/test_price_history.py
  - backend/tests/markets/test_service.py
  - backend/tests/markets/test_update_market_publishes.py
  - backend/tests/polymarket/test_poll_publishes.py
  - backend/tests/realtime/__init__.py
  - backend/tests/realtime/conftest.py
  - backend/tests/realtime/test_ws_fanout.py
  - backend/tests/realtime/test_ws_isolation.py
  - backend/tests/realtime/test_ws_reconnect.py
  - frontend/package.json
  - frontend/src/app/markets/[slug]/page.tsx
  - frontend/src/app/portfolio/loading.tsx
  - frontend/src/components/bet-confirm-dialog.tsx
  - frontend/src/components/live-indicator.tsx
  - frontend/src/components/market-detail-live-odds.tsx
  - frontend/src/components/market-detail-skeleton.tsx
  - frontend/src/components/order-entry-form.test.tsx
  - frontend/src/components/order-entry-form.tsx
  - frontend/src/components/price-history-chart.test.tsx
  - frontend/src/components/price-history-chart.tsx
  - frontend/src/components/price-history-section.tsx
  - frontend/src/components/recent-activity-feed.tsx
  - frontend/src/components/ui/dialog.tsx
  - frontend/src/components/ui/select.tsx
  - frontend/src/hooks/use-market-socket.test.ts
  - frontend/src/hooks/use-market-socket.ts
  - frontend/src/lib/api.ts
  - frontend/src/lib/bet-actions.ts
  - frontend/src/lib/bet-schemas.ts
findings:
  critical: 1
  blocker: 1
  warning: 8
  info: 6
  total: 15
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-05-29
**Depth:** standard
**Files Reviewed:** 42
**Status:** issues_found

## Summary

Phase 9 ships the real-time price pipeline (FastAPI WebSocket + Redis pub/sub) and the
player-facing market-detail page (SSR shell + order-entry Server Action + Recharts chart +
WS client hook). The implementation is, on the whole, careful and well-documented: the
money/odds-as-string convention holds end-to-end (`format_odds` quantizes to `Numeric(8,6)`
so the socket string matches the SSR string; `OutcomeRead`/`PricePoint`/`ActivityItem` all
serialize Decimals as strings, and there are explicit `"amount":12.5` negative tests), the
activity feed is anonymized server-side in BOTH the query and the schema (with a load-bearing
raw-JSON negative assertion), the price-history `window` param is a FastAPI `Literal` allowlist
(422 before SQL; no interpolation), the producer hooks publish strictly post-commit and
on-change-only, the order-entry Server Action never carries a `user_id` and the backend
`current_betting_player` gate remains authoritative, and the WS ConnectionManager broadcast
snapshots under the lock and sends outside it.

The adversarial review nonetheless surfaces one genuine security gap and one correctness
defect that should block, plus several robustness/maintainability warnings.

The headline concern is the **public, unauthenticated WebSocket endpoint with no connection
cap, no origin check, and no market-existence validation** — a resource-exhaustion vector
flagged in the review brief and confirmed in code. The correctness blocker is a **disconnect
race in the WS hook's `onclose` reconnect path** that can spawn parallel sockets.

## Critical Issues

### CR-01: Public WebSocket has no connection cap, no Origin check, and accepts any market_id — unbounded per-process resource growth

**File:** `backend/app/realtime/router.py:25-36`, `backend/app/realtime/manager.py:29-34`
**Issue:**
The endpoint accepts every connection unconditionally and never validates `market_id`:

```python
@realtime_router.websocket("/ws/markets/{market_id}")
async def ws_market(websocket: WebSocket, market_id: str) -> None:
    await manager.connect(market_id, websocket)   # ws.accept() with no gate
```

`manager.connect` does `await ws.accept()` then `self._connections[market_id] = set()` for any
string. There is:
- **No connection cap** (global or per-IP). A single client can open thousands of sockets; each
  is a live ASGI task + an entry in the unbounded `_connections` dict. This is the
  connection-flood / resource-exhaustion vector the review brief explicitly calls out
  ("connection-flood/resource exhaustion"). Unlike the HTTP surface (which has `SlowAPIMiddleware`
  + `@limiter.limit`), the WS path is mounted with zero rate limiting — `SlowAPIMiddleware` only
  bridges `@limiter.limit` decorators on HTTP routes, so the WS endpoint is completely
  unprotected.
- **No `Origin` validation.** `CORSMiddleware` does not apply to the WebSocket handshake (it is
  HTTP-only). Any web origin can open the socket cross-site. Odds are public data so this is not
  a data-confidentiality issue, but combined with the missing cap it widens the DoS surface to
  any malicious page a victim visits.
- **No market-existence check.** `market_id` is a free-form path string never checked against the
  DB. `prices:{anything}` registers a bucket in `_connections`. A loop over random ids inflates
  the dict with sockets that will never receive a broadcast, so the only outcome is memory/task
  growth — there is no natural backpressure.

The module docstring justifies "public/unauthenticated by design" (odds are public, the browser
WS API can't send Authorization, read-only broadcast) — that reasoning is sound for *auth*, but
it conflates "no auth" with "no abuse controls." A public endpoint still needs a flood ceiling.

**Fix:** Add a per-process (and ideally per-IP) connection ceiling and reject over-limit
handshakes with a close code BEFORE registering; optionally validate the Origin header and the
market_id shape. Minimal cap example:

```python
MAX_TOTAL_CONNECTIONS = 5000          # per worker process
MAX_PER_MARKET = 1000

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._total = 0

    async def connect(self, market_id: str, ws: WebSocket) -> bool:
        async with self._lock:
            if self._total >= MAX_TOTAL_CONNECTIONS:
                return False
            bucket = self._connections.setdefault(market_id, set())
            if len(bucket) >= MAX_PER_MARKET:
                return False
            await ws.accept()
            bucket.add(ws)
            self._total += 1
            return True
```

```python
@realtime_router.websocket("/ws/markets/{market_id}")
async def ws_market(websocket: WebSocket, market_id: str) -> None:
    # Optional: validate Origin against settings.FRONTEND_BASE_URL
    if not await manager.connect(market_id, websocket):
        await websocket.close(code=1013)  # try again later
        return
    try:
        ...
```

(Decrement `self._total` in `disconnect`.) If a connection cap is deliberately deferred to the
edge/proxy layer (e.g. nginx `limit_conn`), document that decision explicitly in the module
docstring and the phase VERIFICATION — right now nothing bounds it at any layer in this repo.

## Warnings

### BL-01: WS hook `onclose` can spawn parallel sockets — `wsRef` is overwritten without closing the prior socket on rapid reconnect

**File:** `frontend/src/hooks/use-market-socket.ts:66-133`
**Issue:**
The reconnect path has a window where two live sockets exist and only one is tracked. Trace:

1. Socket A drops → `A.onclose` fires → `scheduleReconnect()` sets a timer.
2. Timer fires → `connect()` runs → creates socket B, `wsRef.current = B`. A's handlers were
   never detached and A is still the object whose `onclose` already ran (fine), BUT:
3. If socket B then errors synchronously-ish, `B.onerror` calls `B.close()`, which later fires
   `B.onclose` → `scheduleReconnect()` again. Meanwhile, if the *stale/ping* interval or a late
   `A` event runs, `wsRef.current` now points at B and A is unreferenced but never explicitly
   `.close()`d (its `onclose` already returned). A is GC-eligible only once the browser tears
   down its underlying connection — its handlers (`onmessage`) are still attached, so a late
   message on A still calls `setOdds`/`setState` on an orphaned socket.

The core gap: `connect()` (line 82) overwrites `wsRef.current` (line 86) **without first
closing/detaching the previous `wsRef.current`**. `scheduleReconnect` guards against double
*timers* (`if (reconnectTimerRef.current ...) return`), but nothing guards against a stale
socket whose handlers are still live when a new one is created. On a flaky connection
(open→error→close repeatedly) this leaks sockets and lets a late frame from an old socket mutate
state after a newer socket is authoritative — i.e. odds can briefly regress to an older value.

**Fix:** At the top of `connect()`, tear down any existing socket before creating the new one:

```javascript
function connect() {
  if (closedByUnmountRef.current) return;
  const prev = wsRef.current;
  if (prev) {
    prev.onopen = prev.onmessage = prev.onclose = prev.onerror = null;
    try { prev.close(); } catch { /* noop */ }
  }
  const url = `${WS_BASE}/ws/markets/${marketId}`;
  const ws = new WebSocket(url);
  wsRef.current = ws;
  ...
}
```

(Classified Critical-tier via the `BL-` prefix because it is a correctness defect in the
reconnect state machine — stale-socket writes after reconnect — but it degrades gracefully and is
not a security/data-loss issue, so impact is bounded. Treat as must-fix-before-ship alongside
CR-01.)

### WR-01: Reconnect backoff counter grows unbounded → `2 ** attempt` overflows to `Infinity`

**File:** `frontend/src/hooks/use-market-socket.ts:70-75`
**Issue:**
`reconnectAttemptRef.current` is incremented on every failed attempt and only reset in `onopen`.
If the server is down for a long stretch (or the market id is wrong and the server keeps closing
the socket), the counter climbs without bound. `1000 * 2 ** reconnectAttemptRef.current` is
`Math.min`-capped at `MAX_RECONNECT_DELAY_MS`, so the *delay* is safe, but once `attempt >= 1024`
the expression `2 ** 1024` is `Infinity`; `Math.min(Infinity, 30000)` is `30000` and
`Math.round(30000 + Infinity*0.2*rand)` — wait, `jitter = delay * 0.2 * Math.random()` uses the
already-capped `delay` (30000), so jitter stays finite. The delay math survives, but the
ever-growing integer ref is a latent smell and the attempt count is meaningless past the cap.

**Fix:** Cap the attempt counter at the point the delay saturates so it never grows without
bound:

```javascript
const MAX_RECONNECT_ATTEMPTS_FOR_BACKOFF = 5; // 2**5 * 1000 = 32s > cap
const attempt = Math.min(
  reconnectAttemptRef.current,
  MAX_RECONNECT_ATTEMPTS_FOR_BACKOFF,
);
const delay = Math.min(1000 * 2 ** attempt, MAX_RECONNECT_DELAY_MS);
...
reconnectAttemptRef.current = Math.min(
  reconnectAttemptRef.current + 1,
  MAX_RECONNECT_ATTEMPTS_FOR_BACKOFF,
);
```

### WR-02: `publish_odds_change` opens a fresh sync Redis connection on every admin odds edit (no pooling) and runs inside the request event loop

**File:** `backend/app/realtime/publisher.py:62-75`, called from `backend/app/markets/router.py:113`
**Issue:**
The admin-edit producer calls the **synchronous** `redis.from_url(...)` inside an `async` route
handler (`update_market`). Two problems:

1. `client.publish(...)` is a blocking socket call executed on the asyncio event loop thread — it
   blocks the entire worker's event loop for the duration of the Redis round-trip (connect +
   PUBLISH + close). Under a slow/over-loaded Redis this stalls every concurrent request on that
   worker, not just the admin edit.
2. A brand-new TCP connection is opened and closed on every single odds edit (`from_url` →
   `publish` → `close`). No connection reuse. The async poll path correctly reuses its held
   `AioRedis`; the admin path does not.

The try/except around the call (router.py:112-115) correctly prevents a Redis hiccup from 500ing
the edit, which is good — but the blocking call is still on the hot path.

**Fix:** Use the async client off the request's existing Redis (or run the sync publish in a
threadpool). Preferred: an `async def publish_odds_change_async` reusing a shared
`redis.asyncio` pool, awaited in the handler. If a sync client must be kept, wrap it:
`await anyio.to_thread.run_sync(_publish_sync, ...)` so it never blocks the loop. (Note: the
project's "out of scope: performance" caveat covers algorithmic complexity, but blocking the
event loop is a correctness/robustness issue under concurrency, not a Big-O concern.)

### WR-03: `redis_subscriber` has no reconnect — a transient Redis drop silently kills live updates for the worker's lifetime

**File:** `backend/app/realtime/subscriber.py:26-60`, `backend/app/main.py:102-108`
**Issue:**
The subscriber task `psubscribe`s once and iterates `pubsub.listen()`. If the Redis connection
drops (failover, restart, network blip), `pubsub.listen()` raises (or the iterator ends) and the
exception propagates out of the `async for`. The only `except` is `asyncio.CancelledError`; any
other exception falls straight to `finally` (punsubscribe + aclose) and the coroutine **returns**.
The lifespan started the task with `asyncio.create_task(...)` and never observes its result
(line 102) — so when it dies, nothing restarts it and nothing logs it. The worker keeps serving
WS clients that are silently frozen (they'll go "stale" then "reconnecting" client-side but the
server never republishes because the subscriber is gone). This is the classic "background task
dies and no one notices" failure.

**Fix:** Wrap the subscribe loop in an outer reconnect loop with backoff, and/or have the lifespan
add a done-callback that logs + restarts:

```python
async def redis_subscriber(manager, redis_url: str) -> None:
    while True:
        try:
            r = AioRedis.from_url(redis_url)
            pubsub = r.pubsub()
            await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
            try:
                async for message in pubsub.listen():
                    ...
            finally:
                await pubsub.punsubscribe(f"{CHANNEL_PREFIX}*")
                await r.aclose()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("realtime.subscriber_reconnect", exc_info=True)
            await asyncio.sleep(1.0)
```

Also attach `task.add_done_callback(...)` in the lifespan to surface an unexpected exit to
Sentry/logs.

### WR-04: `_run_detect_resolutions` closes the session twice on the success path

**File:** `backend/app/integrations/polymarket/tasks.py:295-307`
**Issue:**
On the happy path the function closes the session inside the `try` block (lines 295-297):

```python
        if session_override is None:
            with contextlib.suppress(Exception):
                await session.close()
    except Exception as exc:
        ...
        if session is not None and session_override is None:
            with contextlib.suppress(Exception):
                await session.close()   # second close on the error path only
```

The success-path close at 295-297 is inside `try`, so if it somehow raised it'd be caught by the
outer `except` which closes again. More importantly, the close logic is duplicated and asymmetric
versus `_run_poll_sync` / `_run_snapshot_odds`, which both use a clean `finally:` to close exactly
once. Double-`close()` on an AsyncSession is generally idempotent (suppressed here anyway), so this
is not a crash — but the control flow is fragile and inconsistent with the sibling tasks, and a
reader cannot easily prove the session is closed exactly once on every path.

**Fix:** Move the session close into a single `finally:` block (matching `_run_poll_sync`), and
drop the in-`try` and in-`except` closes:

```python
    finally:
        await redis.delete(DETECT_LOCK_KEY)
        if session is not None and session_override is None:
            with contextlib.suppress(Exception):
                await session.close()
        if redis_override is None:
            await redis.aclose()
```

### WR-05: Poll/detect lock release is not owner-checked — a slow task can delete a lock another task acquired

**File:** `backend/app/integrations/polymarket/tasks.py:56-58, 121, 309`
**Issue:**
`acquire_poll_lock` sets the lock with `SET NX EX ttl` (good — auto-expires). But
`release_poll_lock` does an unconditional `redis.delete(LOCK_KEY)`. If task A acquires the lock,
runs longer than `POLYMARKET_LOCK_TTL_SECONDS` (the lock expires), task B then acquires a fresh
lock, and task A finally reaches its `finally:` and `delete`s the key — it deletes **B's** lock,
not its own. Two polls can then overlap, which is exactly what the lock exists to prevent
(T-06-05). Same pattern for `DETECT_LOCK_KEY` (line 309). The TTL is tuned to be < the poll
interval to mitigate this, but a single slow Gamma API call (the poll fetches 25 markets +
upserts each) can blow past 25s.

**Fix:** Use a unique token per acquisition and release via a compare-and-delete (Lua) so a task
only deletes the lock it owns:

```python
import uuid
token = uuid.uuid4().hex
acquired = await redis.set(LOCK_KEY, token, nx=True, ex=ttl)
...
# release: only if we still own it
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
await redis.eval(_RELEASE, 1, LOCK_KEY, token)
```

### WR-06: `MarketDetailLiveOdds` falls back to `100 - yesPct` whenever live NO odds round to 0 — can desync from the authoritative NO odds

**File:** `frontend/src/components/market-detail-live-odds.tsx:49-51`
**Issue:**
```javascript
const noPctRaw = toPct(odds[noOutcomeId]);
const noPct = noPctRaw > 0 ? noPctRaw : 100 - yesPct;
```
The backend always publishes BOTH YES and NO deltas (verified in `update_market` and the poll
adapter, which iterate all outcomes). So the explicit NO odds are virtually always present. But
the `> 0` guard means a *legitimately tiny* NO probability that rounds to 0% (e.g. NO odds
`"0.004"` → `toPct` → 0) is discarded and replaced by `100 - yesPct`. For a near-certain market
(YES 0.997 / NO 0.003) the display would show NO as `100 - 100 = 0` either way, so the visible
result is the same here — but the logic conflates "NO odds genuinely ~0%" with "NO odds missing,"
which is a latent correctness trap if a future market is non-binary or the complement assumption
breaks. The complement (`100 - yesPct`) is only correct for a strict binary market.

**Fix:** Distinguish "key absent" from "rounds to 0." Use the presence of the key, not the rounded
value:

```javascript
const noPct =
  odds[noOutcomeId] !== undefined ? toPct(odds[noOutcomeId]) : 100 - yesPct;
```

### WR-07: 403 banned-vs-unverified disambiguation relies on a fragile substring match (`detail.includes("ban")`)

**File:** `frontend/src/lib/bet-actions.ts:131-141`
**Issue:**
The action distinguishes a banned player from an unverified one by lowercasing the backend
`detail` and testing `detail.includes("ban")`:

```javascript
const detail = (await readDetail(res)).toLowerCase();
if (detail.includes("ban")) {
  return { errors: { _form: [COPY.banned] } };
}
return { errors: { _form: [COPY.unverified] } };   // default
```

The backend banned message is `"Account is banned from placing bets."` (confirmed in
`bets/router.py::current_betting_player`), so `"ban"` matches today. Risks: (1) the substring
`"ban"` is broad — any future 403 detail containing the letters "ban" (e.g. "bandwidth",
"abandoned request") would be mis-mapped to the banned copy; (2) fastapi-users' unverified 403
detail is not asserted anywhere in this code, so the "default to unverified" branch is an
assumption. If fastapi-users ever returns a 403 for some *other* reason, the player sees
"Verify your email" incorrectly. This is brittle coupling to a human-readable string across a
service boundary.

**Fix:** Have the backend return a machine-readable code in the 403 body (the codebase already
uses `detail={"code": ..., "reason": ...}` elsewhere, e.g. `bet-check` and `update_market`), and
branch on `code` instead of a substring. Short of a backend change, tighten the match to the full
sentinel (`detail.includes("is banned")`) to avoid false positives.

### WR-08: `expectedPayout` accepts unbounded-precision stake and can render misleading payouts for sub-`BET_MIN_STAKE` amounts

**File:** `frontend/src/components/order-entry-form.tsx:80-85`, `bet-schemas.ts:33-44`
**Issue:**
`expectedPayout` computes `(s / p).toFixed(2)` for any `s > 0`, independent of the
`BET_MIN_STAKE`/`BET_MAX_STAKE` bounds the zod schema enforces. The preview therefore shows a
plausible payout for a stake the form will reject on submit (e.g. stake `"0.5"` with
`BET_MIN_STAKE=1` shows a payout, then the bet is blocked). Minor UX inconsistency, not a money
bug (the payout is display-only and never feeds storage math, per SP-1). Separately, the zod
`refine` parses `Number(v)` for the bound check — for an 18-significant-digit stake string this
loses precision in the comparison, but since the backend re-validates with `Decimal` this is
pre-flight-only and acceptable.

**Fix:** Gate the payout preview on the same min/max (return `"—"` outside the valid range) so the
preview and the submit gate agree:

```javascript
if (Number.isNaN(s) || Number.isNaN(p) || p <= 0 || s < BET_MIN_STAKE || s > BET_MAX_STAKE)
  return "—";
```

## Info

### IN-01: `update_market` computes `updated_id` with a misleading comment placement

**File:** `backend/app/markets/router.py:104-113`
**Issue:** The comment "Publish the odds-change deltas AFTER commit" sits at line 105 *before*
`await session.commit()` (line 108), with the actual `publish_odds_change` call at line 113. The
code is correct (publish is genuinely post-commit), but the comment-above-commit ordering reads as
if the publish happens before the commit. `updated_id = updated.id` is captured pre-commit to
survive expiry — fine with `expire_on_commit=False`, but the dance is subtle.
**Fix:** Move the "publish AFTER commit" comment down to sit directly above the
`if odds_deltas:` block (line 111) where the publish actually occurs.

### IN-02: `_run_poll_sync` releases the lock in `finally` even when the lock was never acquired in this call

**File:** `backend/app/integrations/polymarket/tasks.py:76-78, 120-124`
**Issue:** When `acquire_poll_lock` returns `False` (lock held by another task), the function
returns early at line 78 — but only after the `if not await acquire_poll_lock(redis): ... return`
short-circuits *before* the `try`, so the `finally` (which calls `release_poll_lock`) does NOT run
for the lock-not-acquired path. Good. However, if `acquire_poll_lock` itself raises (Redis down),
the exception propagates before the `try`, and `redis.aclose()` in `finally` also won't run
because `finally` is attached to the `try` that starts at line 80. This leaves the Redis
connection unclosed on an acquire failure. Edge case (Redis down at acquire time), low impact.
**Fix:** Move Redis creation + lock acquisition inside the `try`, or add a narrower guard so the
client is always closed.

### IN-03: `relativeTime` uses `Date.now()` in a Server Component → SSR/CSR hydration drift risk

**File:** `frontend/src/components/recent-activity-feed.tsx:22-33`
**Issue:** `RecentActivityFeed` is a Server Component (no `"use client"`) and `relativeTime` calls
`Date.now()` at render. Since the component renders on the server and is not hydrated as an
interactive client component, the relative time is frozen at SSR time and never updates without a
full page reload — and if any parent ever makes this a client component, the server vs client
`Date.now()` would mismatch and warn. Functionally acceptable for v1 (the feed is a point-in-time
snapshot), but worth noting the timestamps are static.
**Fix:** Document that the feed is a server-rendered snapshot, or move `relativeTime` to a tiny
client component if live-updating relative times are desired.

### IN-04: `MarketRead` exposes `source_market_id` on the public `GET /{slug}` response

**File:** `backend/app/markets/schemas.py:96`, `router.py:156-164`
**Issue:** `MarketRead` (returned by the public, unauthenticated `GET /api/v1/markets/{slug}`)
includes `source_market_id` (the raw Polymarket/Gamma numeric id). `MarketListItem` deliberately
derives a friendly `source_url` from `polymarket_slug` instead and notes the numeric id "is not a
valid Polymarket event URL segment." Exposing the internal source id on the public detail payload
is harmless (it's not a secret) but is inconsistent with the list endpoint's deliberate choice to
surface only the slug-based URL. Not a leak, just an inconsistency.
**Fix:** Confirm `source_market_id` is intended on the public detail payload; if not, drop it from
`MarketRead` (or gate it to the admin `MarketRead` usage) for parity with `MarketListItem`.

### IN-05: WS hook silently swallows all JSON parse + send errors with empty catch blocks

**File:** `frontend/src/hooks/use-market-socket.ts:96-100, 125-129, 153-157, 175-179`
**Issue:** Multiple `catch { /* noop */ }` / `catch { return; }` blocks. These are individually
defensible (a malformed frame should be dropped, a send-after-close should not crash), and the
brief notes the socket is read-only, so this is not a security issue. But four silent catches in
one file means a genuine client-side bug (e.g. the server starts sending a subtly different
payload) would be invisible — no `console.warn`, no telemetry.
**Fix:** Keep the swallow but add a dev-only `console.debug` (or a Sentry breadcrumb) in the
message-parse catch so payload-contract drift is observable in development.

### IN-06: `MarketDetailSkeleton` is rendered with no page-shell padding wrapper → layout shift vs the resolved page

**File:** `frontend/src/components/market-detail-skeleton.tsx:16`, `app/markets/[slug]/page.tsx:219`
**Issue:** The resolved `MarketDetailBody` wraps content in `<main className={PAGE_SHELL}>`
(`max-w-6xl mx-auto px-4 sm:px-6 py-12`), but `MarketDetailSkeleton` renders a bare
`<div aria-busy="true">` with no equivalent `max-w-6xl mx-auto px-...` wrapper. The skeleton grid
will be full-bleed while the real content is centered/max-width-constrained, producing a visible
horizontal jump when Suspense resolves — the exact layout-shift the skeleton's own docstring says
it exists to prevent ("so there is NO layout shift").
**Fix:** Wrap the skeleton's root in the same `PAGE_SHELL` classes (or render it inside a `<main
className={PAGE_SHELL}>`) so its width/padding matches the resolved page.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
