"""ConnectionManager — per-market WebSocket registry + lock-safe broadcast.

Lifted from the VALIDATED spike 003 (``spike_ws_server.py`` lines 35-72;
6/6 tests, avg 0.8ms end-to-end), with bounded abuse controls added on top
(CR-01): the spike's ``accept()``-everything ``connect`` had no connection
ceiling, so a single client could open unbounded sockets (each a live ASGI
task + an entry in ``_connections``) — a flood/resource-exhaustion vector. The
endpoint stays PUBLIC and READ-ONLY by design (odds are public data); the cap
bounds abuse WITHOUT adding auth. The ``stats()`` forensic helper is dropped —
production does not expose connection counts.

Design (do NOT redesign the isolation/broadcast core — spike-validated for
isolation, backpressure, and dead-socket pruning):
  - ``_connections``: dict[market_id, set[WebSocket]] guarded by an asyncio.Lock.
  - ``_total``: running global socket count guarded by the SAME lock, so the cap
    check + ``accept()`` + registration are atomic (no accept-then-reject race).
  - ``connect`` rejects (returns ``False``, WITHOUT calling ``accept()``) once the
    per-process or per-market ceiling is hit; the router closes the handshake.
  - ``broadcast`` snapshots the client set UNDER the lock, then sends OUTSIDE the
    lock (no head-of-line blocking) and prunes sockets that raise on send.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

# Per-worker-process connection ceilings (CR-01). A FastAPI worker holds at most
# MAX_TOTAL_CONNECTIONS live sockets across all markets, and at most
# MAX_PER_MARKET on any single market — well above any legitimate fan-out, low
# enough to bound a flood. If a deployment needs a different ceiling, tune here
# (and/or add an edge-layer ``limit_conn``). These are generous: real clients
# open one socket per open market tab.
MAX_TOTAL_CONNECTIONS = 5000
MAX_PER_MARKET = 1000


class ConnectionManager:
    """Tracks connected WebSocket clients per market and broadcasts to them."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._total = 0

    async def connect(self, market_id: str, ws: WebSocket) -> bool:
        """Accept + register a socket, or reject (return ``False``) if over the cap.

        The cap check, ``ws.accept()`` and registration all happen UNDER the lock
        so the global/per-market counts can never be raced past their ceiling by
        concurrent handshakes. When the cap is hit we return ``False`` WITHOUT
        accepting — the caller closes the handshake (CR-01).
        """
        async with self._lock:
            if self._total >= MAX_TOTAL_CONNECTIONS:
                return False
            bucket = self._connections.setdefault(market_id, set())
            if len(bucket) >= MAX_PER_MARKET:
                # Drop the bucket if we created an empty one just now, so a flood
                # of over-cap markets can't leak empty sets into _connections.
                if not bucket:
                    del self._connections[market_id]
                return False
            await ws.accept()
            bucket.add(ws)
            self._total += 1
            return True

    async def disconnect(self, market_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if market_id in self._connections:
                bucket = self._connections[market_id]
                if ws in bucket:
                    bucket.discard(ws)
                    self._total -= 1
                if not bucket:
                    del self._connections[market_id]

    async def broadcast(self, market_id: str, data: dict[str, Any]) -> tuple[int, int]:
        async with self._lock:  # snapshot client set UNDER the lock
            clients = list(self._connections.get(market_id, set()))

        sent = 0
        failed = 0
        stale: list[WebSocket] = []
        for ws in clients:  # send OUTSIDE the lock (no head-of-line block)
            try:
                await ws.send_json(data)
                sent += 1
            except Exception:
                stale.append(ws)
                failed += 1

        for ws in stale:  # prune dead sockets
            await self.disconnect(market_id, ws)

        return sent, failed


# Module-level singleton — the subscriber + router import this one instance.
manager = ConnectionManager()
