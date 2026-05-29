"""MKT-04 fan-out: a publish to prices:{id} reaches a connected WS client <2s.

Asserts the PRODUCTION payload shape only — {type:"price_update", market_id,
outcomes:[{outcome_id, odds}], ts}. Never asserts on the spike's dev-only
``_latency_ms``/``_server_ts`` forensic fields (stripped — SP-4).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

import pytest
import websockets

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_publish_reaches_connected_client_within_2s(
    ws_server: str,
    publish_delta: Callable[[str, dict], int],
) -> None:
    """A client on /ws/markets/{id} receives a delta published to prices:{id} in <2s."""
    market_id = "fanout-market-001"
    outcome_yes = "00000000-0000-0000-0000-0000000000a1"
    outcome_no = "00000000-0000-0000-0000-0000000000a2"

    async with websockets.connect(f"{ws_server}/ws/markets/{market_id}") as ws:
        # Give the subscriber a beat to register the new connection.
        await _wait_for_listener(publish_delta, market_id)

        payload = {
            "type": "price_update",
            "market_id": market_id,
            "outcomes": [
                {"outcome_id": outcome_yes, "odds": "0.700000"},
                {"outcome_id": outcome_no, "odds": "0.300000"},
            ],
            "ts": time.time(),
        }
        published_at = time.time()
        publish_delta(market_id, payload)

        msg = await _recv_price_update(ws, timeout=5.0)
        elapsed = time.time() - published_at

    assert elapsed < 2.0, f"fan-out took {elapsed:.3f}s (>2s)"
    assert msg["type"] == "price_update"
    assert msg["market_id"] == market_id
    assert msg["outcomes"] == payload["outcomes"]
    assert "ts" in msg
    # The production delta must NOT leak the spike's dev-only forensic fields.
    assert "_latency_ms" not in msg
    assert "_server_ts" not in msg


async def _wait_for_listener(
    publish_delta: Callable[[str, dict], int],
    market_id: str,
) -> None:
    """Poll a throwaway publish until Redis reports >=1 subscriber for the channel.

    Confirms the in-process subscriber's psubscribe('prices:*') is live before the
    real delta is sent, removing a connect/subscribe race without a fixed sleep.
    """
    import asyncio

    for _ in range(100):
        # A pattern subscriber counts as a listener on every matching channel.
        if publish_delta(market_id, {"type": "warmup"}) >= 1:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("subscriber never registered as a listener for the channel")


async def _recv_price_update(ws: websockets.ClientConnection, *, timeout: float) -> dict:
    """Receive messages until a price_update arrives (skipping any warmup frames)."""
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise AssertionError("no price_update received before timeout")
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        data = json.loads(raw)
        if data.get("type") == "price_update":
            return data
