"""MKT-04 per-market isolation: a client on market A never receives market B deltas.

Threat T-09-02 / spike test 4. Asserts the production payload shape only.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

import pytest
import websockets

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_client_on_market_a_never_receives_market_b(
    ws_server: str,
    publish_delta: Callable[[str, dict], int],
) -> None:
    """Publishing to prices:B must not deliver anything to a /ws/markets/A client."""
    market_a = "iso-market-a"
    market_b = "iso-market-b"

    async with (
        websockets.connect(f"{ws_server}/ws/markets/{market_a}") as ws_a,
        websockets.connect(f"{ws_server}/ws/markets/{market_b}") as ws_b,
    ):
        await _wait_for_listener(publish_delta, market_b)

        payload_b = {
            "type": "price_update",
            "market_id": market_b,
            "outcomes": [{"outcome_id": "b-yes", "odds": "0.420000"}],
            "ts": time.time(),
        }
        publish_delta(market_b, payload_b)

        # Market B's client must receive it.
        msg_b = json.loads(await asyncio.wait_for(ws_b.recv(), timeout=5.0))
        assert msg_b["market_id"] == market_b
        assert msg_b["outcomes"] == payload_b["outcomes"]

        # Market A's client must receive NOTHING (no cross-market leak).
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(ws_a.recv(), timeout=1.5)


async def _wait_for_listener(
    publish_delta: Callable[[str, dict], int],
    market_id: str,
) -> None:
    for _ in range(100):
        if publish_delta(market_id, {"type": "warmup"}) >= 1:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("subscriber never registered as a listener for the channel")
