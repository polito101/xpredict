"""Public WebSocket endpoint for live price broadcasts — /ws/markets/{market_id}.

Lifted from the VALIDATED spike 003 ``ws_prices`` (lines 175-189); only the path
changed (``/ws/prices/`` → ``/ws/markets/``, per CONTEXT Area 3) and it is an
``APIRouter`` so ``app/main.py`` can ``include_router`` it.

Public / unauthenticated by design (SP-3 / 09-RESEARCH Pattern 4): odds are
already public data (same as ``GET /api/v1/markets``), the browser WebSocket API
cannot send an Authorization header, and the socket is READ-ONLY broadcast. The
only inbound message handled is ``"ping"`` → ``{"type":"pong","ts":...}`` (T-09-04);
any other inbound text is ignored — a client cannot inject a price.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.manager import manager

realtime_router = APIRouter()


@realtime_router.websocket("/ws/markets/{market_id}")
async def ws_market(websocket: WebSocket, market_id: str) -> None:
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
