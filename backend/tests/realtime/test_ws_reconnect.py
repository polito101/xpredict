"""MKT-04 reconnect: a client connecting AFTER an earlier publish still receives
subsequent deltas — and never a replay of the earlier one (live-only stream).

Spike test 6 ported. Asserts the production payload shape only.
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


async def test_late_connection_receives_new_deltas_no_replay(
    ws_server: str,
    publish_delta: Callable[[str, dict], int],
) -> None:
    """An earlier delta is not replayed; a delta after (re)connect IS delivered."""
    market_id = "reconnect-market-001"
    url = f"{ws_server}/ws/markets/{market_id}"

    # First connection receives the first delta, then disconnects.
    async with websockets.connect(url) as ws1:
        await _wait_for_listener(publish_delta, market_id)
        first = {
            "type": "price_update",
            "market_id": market_id,
            "outcomes": [{"outcome_id": "yes", "odds": "0.500000"}],
            "ts": time.time(),
        }
        publish_delta(market_id, first)
        msg1 = json.loads(await asyncio.wait_for(ws1.recv(), timeout=5.0))
        assert msg1["outcomes"][0]["odds"] == "0.500000"

    # Publish while NO client is connected — this delta must be lost (no buffer).
    publish_delta(
        market_id,
        {
            "type": "price_update",
            "market_id": market_id,
            "outcomes": [{"outcome_id": "yes", "odds": "0.999999"}],
            "ts": time.time(),
        },
    )
    await asyncio.sleep(0.2)

    # Reconnect; the gap delta must NOT be replayed, but a fresh one IS delivered.
    async with websockets.connect(url) as ws2:
        await _wait_for_listener(publish_delta, market_id)
        second = {
            "type": "price_update",
            "market_id": market_id,
            "outcomes": [{"outcome_id": "yes", "odds": "0.600000"}],
            "ts": time.time(),
        }
        publish_delta(market_id, second)
        msg2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5.0))

    # The reconnected client gets the post-reconnect delta, NOT the missed 0.999999.
    assert msg2["outcomes"][0]["odds"] == "0.600000"
    assert msg2["outcomes"][0]["odds"] != "0.999999"


async def _wait_for_listener(
    publish_delta: Callable[[str, dict], int],
    market_id: str,
) -> None:
    """Warm up against a sentinel channel (never the market under test) until the
    psubscribe('prices:*') subscriber registers as a listener."""
    for _ in range(100):
        if publish_delta(f"__warmup__{market_id}", {"type": "warmup"}) >= 1:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("subscriber never registered as a listener for the channel")
