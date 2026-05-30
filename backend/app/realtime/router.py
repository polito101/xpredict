"""Public WebSocket endpoint for live price broadcasts — /ws/markets/{market_id}.

Lifted from the VALIDATED spike 003 ``ws_prices`` (lines 175-189); the path
changed (``/ws/prices/`` → ``/ws/markets/``, per CONTEXT Area 3) and it is an
``APIRouter`` so ``app/main.py`` can ``include_router`` it.

Public / unauthenticated by design (SP-3 / 09-RESEARCH Pattern 4): odds are
already public data (same as ``GET /api/v1/markets``), the browser WebSocket API
cannot send an Authorization header, and the socket is READ-ONLY broadcast. The
only inbound message handled is ``"ping"`` → ``{"type":"pong","ts":...}`` (T-09-04);
any other inbound text is ignored — a client cannot inject a price.

"Public/unauthenticated" is NOT "no abuse controls" (CR-01). The handshake is
bounded BEFORE registration by three cheap, in-process gates — none of which
add auth or break the public read design:
  1. Connection ceiling — ``manager.connect`` rejects over the per-process /
     per-market cap (close 1013, "try again later"). This is the flood /
     resource-exhaustion guard; ``CORSMiddleware`` + ``SlowAPIMiddleware`` are
     HTTP-only and do NOT touch the WS handshake, so the cap is the only thing
     bounding socket count at the app layer.
  2. Origin allow-list — a browser sends ``Origin`` on the WS handshake; we
     reject cross-site origins (close 1008) so a random page a victim visits
     cannot open sockets against us. NON-browser clients omit ``Origin`` and are
     allowed (the odds are public; this only narrows the drive-by browser
     surface, it is not a confidentiality control).
  3. ``market_id`` shape — reject absurdly long ids (close 1008) so the
     ``_connections`` dict can't be inflated with junk-keyed buckets. We do NOT
     hit the DB on the handshake (a per-connect query is its own DoS lever);
     unknown-but-well-formed ids simply never receive a broadcast.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.realtime.manager import manager

realtime_router = APIRouter()

# Close codes (RFC 6455): 1008 = policy violation, 1013 = try again later.
_WS_POLICY_VIOLATION = 1008
_WS_TRY_AGAIN_LATER = 1013

# A market_id is a UUID in production (36 chars) but tests use short slugs; cap
# generously so junk can't bloat the registry while never rejecting a real id.
_MAX_MARKET_ID_LEN = 128


def _origin_allowed(origin: str | None) -> bool:
    """Allow same-site browser origins and all non-browser clients.

    A browser ALWAYS sends ``Origin`` on a cross-origin WS handshake; a missing
    Origin means a non-browser client (curl, a server, the test client), which
    we allow because the data is public and no cookie/credential rides the WS.
    A present Origin must match the configured frontend (the same single origin
    ``CORSMiddleware`` allows for HTTP), rejecting drive-by cross-site sockets.
    """
    if origin is None:
        return True
    return origin == get_settings().FRONTEND_BASE_URL


@realtime_router.websocket("/ws/markets/{market_id}")
async def ws_market(websocket: WebSocket, market_id: str) -> None:
    # Cheap shape gate first (no accept, no DB) — reject junk-length ids so they
    # can never register a bucket in the connection registry.
    if not market_id or len(market_id) > _MAX_MARKET_ID_LEN:
        await websocket.close(code=_WS_POLICY_VIOLATION)
        return

    # Origin allow-list — reject cross-site browser handshakes (non-browser
    # clients omit Origin and are allowed; the odds are public data).
    if not _origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=_WS_POLICY_VIOLATION)
        return

    # Connection ceiling — reject (without accepting) once the per-process or
    # per-market cap is hit. This is the flood/resource-exhaustion guard (CR-01).
    if not await manager.connect(market_id, websocket):
        await websocket.close(code=_WS_TRY_AGAIN_LATER)
        return

    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(market_id, websocket)
