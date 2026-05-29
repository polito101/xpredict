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
import contextlib
import json

import structlog
from redis.asyncio import Redis as AioRedis

from app.realtime.manager import ConnectionManager

log = structlog.get_logger()

CHANNEL_PREFIX = "prices:"

# Backoff between reconnect attempts when the Redis connection drops (WR-03).
_RECONNECT_DELAY_SECONDS = 1.0


async def _subscribe_and_fan_out(manager: ConnectionManager, redis_url: str) -> None:
    """One Redis connection's lifetime: psubscribe, then fan each delta out.

    Returns (or raises) when the connection ends; the outer ``redis_subscriber``
    loop decides whether to reconnect. The pattern is always unsubscribed and the
    connection closed in ``finally`` so a dropped/cycled connection never leaks.
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
    finally:
        # Best-effort teardown — the connection may already be broken, in which
        # case unsubscribe/close raise; swallow so the reconnect path is reached.
        with contextlib.suppress(Exception):
            await pubsub.punsubscribe(f"{CHANNEL_PREFIX}*")
        with contextlib.suppress(Exception):
            await r.aclose()


async def redis_subscriber(manager: ConnectionManager, redis_url: str) -> None:
    """Subscribe to ``prices:*`` and fan each decoded delta out to its market.

    Wrapped in an outer reconnect loop (WR-03): if the Redis connection drops
    (failover, restart, network blip) ``pubsub.listen()`` raises or ends, which
    previously let the coroutine RETURN — the lifespan never observed the result,
    so live updates silently froze for the worker's lifetime. Now any non-cancel
    error is logged and the connection is re-established after a short backoff, so
    a transient Redis blip self-heals.

    Cancellable: on ``asyncio.CancelledError`` (lifespan shutdown) the loop exits
    cleanly — the inner ``finally`` unsubscribes + closes the connection, so there
    is no leak and no "Event loop is closed" on shutdown (09-RESEARCH Pitfall 4).
    """
    while True:
        try:
            await _subscribe_and_fan_out(manager, redis_url)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("realtime.subscriber_reconnect", exc_info=True)
            await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
        else:
            # listen() ended without an exception (e.g. connection closed
            # gracefully) — reconnect rather than silently returning.
            log.warning("realtime.subscriber_stream_ended")
            await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
