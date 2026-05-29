"""ConnectionManager — per-market WebSocket registry + lock-safe broadcast.

Lifted verbatim from the VALIDATED spike 003 (``spike_ws_server.py`` lines 35-72;
6/6 tests, avg 0.8ms end-to-end). The ``stats()`` forensic helper is dropped —
production does not expose connection counts.

Design (do NOT redesign — spike-validated for isolation, backpressure, and
dead-socket pruning):
  - ``_connections``: dict[market_id, set[WebSocket]] guarded by an asyncio.Lock.
  - ``broadcast`` snapshots the client set UNDER the lock, then sends OUTSIDE the
    lock (no head-of-line blocking) and prunes sockets that raise on send.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Tracks connected WebSocket clients per market and broadcasts to them."""

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
