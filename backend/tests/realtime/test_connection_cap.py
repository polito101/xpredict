"""CR-01: ConnectionManager bounded-abuse controls (cap + reject + counting).

Fast unit tests (no Redis, no socket) for the per-process / per-market
connection ceiling added in CR-01. A fake WebSocket records whether ``accept``
was called so we can assert that over-cap handshakes are rejected WITHOUT being
accepted, and that the running ``_total`` count stays correct across
connect/disconnect (including the broadcast prune path).
"""

from __future__ import annotations

import pytest

from app.realtime import manager as manager_mod
from app.realtime.manager import ConnectionManager

pytestmark = pytest.mark.unit


class FakeWebSocket:
    """Minimal WebSocket stand-in: records accept() and send_json() calls."""

    def __init__(self, *, fail_send: bool = False) -> None:
        self.accepted = False
        self.fail_send = fail_send
        self.sent: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        if self.fail_send:
            raise RuntimeError("socket closed")
        self.sent.append(data)


async def test_connect_accepts_and_counts_under_cap() -> None:
    mgr = ConnectionManager()
    ws = FakeWebSocket()

    accepted = await mgr.connect("m1", ws)  # type: ignore[arg-type]

    assert accepted is True
    assert ws.accepted is True
    assert mgr._total == 1


async def test_per_market_cap_rejects_without_accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once a market hits MAX_PER_MARKET, further sockets are rejected un-accepted."""
    monkeypatch.setattr(manager_mod, "MAX_PER_MARKET", 2)
    mgr = ConnectionManager()

    a, b = FakeWebSocket(), FakeWebSocket()
    assert await mgr.connect("m1", a) is True  # type: ignore[arg-type]
    assert await mgr.connect("m1", b) is True  # type: ignore[arg-type]

    over = FakeWebSocket()
    assert await mgr.connect("m1", over) is False  # type: ignore[arg-type]
    # The rejected socket must NEVER be accepted, and must not be counted.
    assert over.accepted is False
    assert mgr._total == 2


async def test_total_cap_rejects_across_markets(monkeypatch: pytest.MonkeyPatch) -> None:
    """The global per-process ceiling is enforced across distinct markets."""
    monkeypatch.setattr(manager_mod, "MAX_TOTAL_CONNECTIONS", 2)
    mgr = ConnectionManager()

    assert await mgr.connect("m1", FakeWebSocket()) is True  # type: ignore[arg-type]
    assert await mgr.connect("m2", FakeWebSocket()) is True  # type: ignore[arg-type]

    over = FakeWebSocket()
    assert await mgr.connect("m3", over) is False  # type: ignore[arg-type]
    assert over.accepted is False
    assert mgr._total == 2


async def test_over_cap_market_does_not_leak_empty_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected first-connect for a brand-new market must not leave an empty set."""
    monkeypatch.setattr(manager_mod, "MAX_TOTAL_CONNECTIONS", 0)
    mgr = ConnectionManager()

    assert await mgr.connect("brand-new", FakeWebSocket()) is False  # type: ignore[arg-type]
    assert "brand-new" not in mgr._connections


async def test_disconnect_decrements_total_once() -> None:
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect("m1", ws)  # type: ignore[arg-type]
    assert mgr._total == 1

    await mgr.disconnect("m1", ws)  # type: ignore[arg-type]
    assert mgr._total == 0
    assert "m1" not in mgr._connections

    # A second disconnect of an already-removed socket must not go negative.
    await mgr.disconnect("m1", ws)  # type: ignore[arg-type]
    assert mgr._total == 0


async def test_broadcast_prune_keeps_total_consistent() -> None:
    """A socket that raises on send is pruned and the total is decremented."""
    mgr = ConnectionManager()
    good = FakeWebSocket()
    bad = FakeWebSocket(fail_send=True)
    await mgr.connect("m1", good)  # type: ignore[arg-type]
    await mgr.connect("m1", bad)  # type: ignore[arg-type]
    assert mgr._total == 2

    sent, failed = await mgr.broadcast("m1", {"type": "price_update"})

    assert (sent, failed) == (1, 1)
    assert mgr._total == 1  # the dead socket was pruned and uncounted
    assert good.sent == [{"type": "price_update"}]
