"""redis_subscriber — psubscribe('prices:*') → ConnectionManager.broadcast.

Lifted from the VALIDATED spike 003 (``spike_ws_server.py`` lines 97-143), with
ALL forensic instrumentation STRIPPED: no ``log_event``, no ``_latency_ms``, no
``_server_ts`` (SP-4 — production payloads are the lean delta only). The Redis
URL comes from Settings, not the spike's hardcoded constant.

One task runs per FastAPI worker process (started in the app lifespan). Because
each uvicorn worker runs its own lifespan, each gets its own subscriber and
broadcasts to its own local sockets — multi-worker is correct with zero extra
code (09-RESEARCH Pattern 2).
"""

from __future__ import annotations

import asyncio
import json

from redis.asyncio import Redis as AioRedis

from app.realtime.manager import ConnectionManager

CHANNEL_PREFIX = "prices:"


async def redis_subscriber(manager: ConnectionManager, redis_url: str) -> None:
    """Subscribe to ``prices:*`` and fan each decoded delta out to its market.

    Cancellable: on ``asyncio.CancelledError`` (lifespan shutdown) the pattern is
    unsubscribed and the connection closed in ``finally`` — no leak, no
    "Event loop is closed" on shutdown (09-RESEARCH Pitfall 4).
    """
    r = AioRedis.from_url(redis_url)
    pubsub = r.pubsub()
    await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()
            market_id = channel.removeprefix(CHANNEL_PREFIX)

            raw = message["data"]
            if isinstance(raw, bytes):
                raw = raw.decode()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            await manager.broadcast(market_id, data)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.punsubscribe(f"{CHANNEL_PREFIX}*")
        await r.aclose()
