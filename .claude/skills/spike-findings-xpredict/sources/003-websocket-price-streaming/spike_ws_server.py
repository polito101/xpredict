"""
Spike 003: WebSocket Price Streaming Server

FastAPI app with:
- WebSocket endpoint per market (/ws/prices/{market_id})
- Redis pub/sub subscription for price broadcasts
- Connection manager tracking clients per market
- Built-in latency measurement (publish timestamp vs receive timestamp)
- Serves an interactive HTML dashboard

Run from xpredict/backend:
  uv run python ../.planning/spikes/003-websocket-price-streaming/spike_ws_server.py
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

REDIS_URL = "redis://localhost:6379/0"
CHANNEL_PREFIX = "prices:"

# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------

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

    def stats(self) -> dict[str, int]:
        return {mid: len(clients) for mid, clients in self._connections.items()}


manager = ConnectionManager()

# ---------------------------------------------------------------------------
# Event log (forensic observability)
# ---------------------------------------------------------------------------

event_log: list[dict[str, Any]] = []

def log_event(category: str, **kwargs: Any) -> None:
    entry = {"ts": time.time(), "iso": time.strftime("%H:%M:%S"), "cat": category, **kwargs}
    event_log.append(entry)
    if len(event_log) > 500:
        event_log.pop(0)


# ---------------------------------------------------------------------------
# Redis subscriber background task
# ---------------------------------------------------------------------------

async def redis_subscriber(app_state: dict[str, Any]) -> None:
    r = aioredis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
    log_event("redis", action="subscribed", pattern=f"{CHANNEL_PREFIX}*")

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()

            market_id = channel.replace(CHANNEL_PREFIX, "")

            raw = message["data"]
            if isinstance(raw, bytes):
                raw = raw.decode()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                log_event("error", action="bad_json", channel=channel)
                continue

            receive_ts = time.time()
            publish_ts = data.get("ts", receive_ts)
            latency_ms = (receive_ts - publish_ts) * 1000

            data["_latency_ms"] = round(latency_ms, 2)
            data["_server_ts"] = receive_ts

            sent, failed = await manager.broadcast(market_id, data)
            log_event(
                "broadcast",
                market=market_id,
                sent=sent,
                failed=failed,
                latency_ms=round(latency_ms, 2),
            )
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.punsubscribe(f"{CHANNEL_PREFIX}*")
        await r.aclose()


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(redis_subscriber({}))
    log_event("lifecycle", action="started")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    log_event("lifecycle", action="stopped")


app = FastAPI(title="Spike 003: WS Price Streaming", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.websocket("/ws/prices/{market_id}")
async def ws_prices(websocket: WebSocket, market_id: str):
    await manager.connect(market_id, websocket)
    log_event("ws", action="connected", market=market_id)
    try:
        while True:
            # Keep connection alive; client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(market_id, websocket)
        log_event("ws", action="disconnected", market=market_id)


@app.get("/api/stats")
async def stats():
    return {
        "connections": manager.stats(),
        "events": len(event_log),
        "recent_events": event_log[-20:],
    }


@app.get("/api/events")
async def events():
    return {"events": event_log}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print(" Spike 003: WebSocket Price Streaming")
    print(" Server: http://localhost:8099")
    print(" Dashboard: http://localhost:8099/")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8099, log_level="info")
