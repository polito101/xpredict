# Real-Time Streaming

## Requirements

- Price updates must reach connected clients in <2s end-to-end (proven: avg 0.8ms, 2500x margin)
- Zero message loss under burst conditions (100 rapid messages, 0 drops)
- Market-level isolation: clients subscribed to market A never receive market B updates
- Auto-reconnect with exponential backoff on client disconnect
- Stale data detection if no update received within 30s

## How to Build It

### 1. ConnectionManager (per-market client tracking)

```python
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

    async def broadcast(self, market_id: str, data: dict) -> tuple[int, int]:
        sent = 0
        failed = 0
        async with self._lock:
            clients = list(self._connections.get(market_id, set()))

        stale: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(data)
                sent += 1
            except Exception:
                stale.append(ws)
                failed += 1

        for ws in stale:
            await self.disconnect(market_id, ws)

        return sent, failed
```

### 2. Redis pub/sub subscriber (background task)

```python
async def redis_subscriber(manager: ConnectionManager) -> None:
    r = aioredis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.psubscribe("prices:*")

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()

            market_id = channel.replace("prices:", "")

            raw = message["data"]
            if isinstance(raw, bytes):
                raw = raw.decode()

            data = json.loads(raw)
            await manager.broadcast(market_id, data)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.punsubscribe("prices:*")
        await r.aclose()
```

### 3. FastAPI WebSocket endpoint

```python
@app.websocket("/ws/prices/{market_id}")
async def ws_prices(websocket: WebSocket, market_id: str):
    await manager.connect(market_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(market_id, websocket)
```

### 4. Publisher pattern (from Celery task or admin action)

```python
# Celery Beat polls Polymarket every 30s
r = redis.from_url(REDIS_URL)
data = {
    "type": "price_update",
    "market_id": market_id,
    "yes_price": str(yes_price),
    "no_price": str(no_price),
    "ts": time.time(),
}
r.publish(f"prices:{market_id}", json.dumps(data))
```

### 5. Client reconnect pattern (JavaScript)

```javascript
const MAX_RECONNECT_DELAY_MS = 30000;
let reconnectAttempt = 0;

function scheduleReconnect() {
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), MAX_RECONNECT_DELAY_MS);
    const jitter = delay * 0.2 * Math.random();
    reconnectAttempt++;
    setTimeout(() => connectWS(), delay + jitter);
}

// Stale detection
setInterval(() => {
    if (Date.now() - lastMsgTime > 30000) {
        showStaleBadge();
    }
}, 5000);
```

### 6. App lifecycle (start subscriber on startup)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(redis_subscriber(manager))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

### 7. Architecture (Phase 9)

```
Celery Beat (30s poll)
  -> Polymarket Gamma API
  -> Upsert odds_snapshots
  -> redis.publish("prices:{market_id}", json)

Admin edits house odds
  -> Update DB
  -> redis.publish("prices:{market_id}", json)

FastAPI server (background task)
  -> redis.asyncio psubscribe("prices:*")
  -> ConnectionManager.broadcast(market_id, data)
  -> All connected WS clients on that market

Next.js client
  -> new WebSocket("/ws/prices/{market_id}")
  -> onmessage: update price display
  -> onclose: exponential backoff reconnect
  -> Stale badge if no data >30s
```

## What to Avoid

1. **DO NOT use the `broadcaster` library** -- stale maintenance, unnecessary dependency
2. **DO NOT use SSE (Server-Sent Events)** -- unidirectional, worse reconnect handling, no binary support
3. **DO NOT add explicit backpressure mechanisms** -- asyncio event loop + Redis pub/sub handles it natively (100 rapid messages, 0 drops in spike testing)
4. **DO NOT try to restore state on reconnect** -- prices are live-only; historical data comes from `odds_snapshots` table, not the stream
5. **DO NOT add `websockets` as a server dependency** -- FastAPI native WebSocket support is sufficient. The `websockets` library is only needed for test clients.

## Constraints

- `redis.asyncio` (from `redis>=5.0` already in project) is the only new import needed
- `psubscribe("prices:*")` pattern routing handles per-market isolation without explicit subscription management
- Sub-millisecond latency through the full pipeline (avg=0.8ms) -- bottleneck will be the Polymarket poll interval (30s), never the streaming pipeline
- 5 concurrent clients per market tested with 100% message delivery
- ConnectionManager uses `asyncio.Lock` for thread safety -- suitable for single-process deployment; for multi-process, each worker subscribes independently to Redis

## Origin

Synthesized from spikes: 003
Source files available in: sources/003-websocket-price-streaming/
