"""MarketReadPort contract + MarketView behavior (Phase 5 ↔ Phase 4 integration contract).

Pure unit tests (no DB): they pin the narrow, read-only contract Phase 5 consumes from
Phase 4 and the bet-eligibility logic on a market snapshot. ``StubMarketSource`` stands
in for Phase 4's adapter during parallel development (and is reused by the BetService
tests once place_bet lands).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.bets.market_port import (
    MARKET_CLOSED,
    MARKET_OPEN,
    MARKET_RESOLVED,
    MarketReadPort,
    MarketView,
    OutcomeView,
)


def _market(
    status: str,
    *,
    deadline: datetime,
    outcomes: tuple[OutcomeView, ...] | None = None,
) -> MarketView:
    outs = outcomes or (
        OutcomeView(id=uuid4(), label="YES"),
        OutcomeView(id=uuid4(), label="NO"),
    )
    return MarketView(id=uuid4(), status=status, deadline=deadline, outcomes=outs)


class StubMarketSource:
    """In-memory ``MarketReadPort`` for tests — fully controllable, no DB."""

    def __init__(self) -> None:
        self._markets: dict[UUID, MarketView] = {}

    def add(self, market: MarketView) -> None:
        self._markets[market.id] = market

    async def get_market(self, market_id: UUID) -> MarketView | None:
        return self._markets.get(market_id)


def test_stub_satisfies_market_read_port() -> None:
    """The stub structurally conforms to the runtime-checkable port."""
    assert isinstance(StubMarketSource(), MarketReadPort)


async def test_get_market_returns_configured_and_none_for_unknown() -> None:
    src = StubMarketSource()
    m = _market(MARKET_OPEN, deadline=datetime.now(UTC) + timedelta(days=1))
    src.add(m)
    assert await src.get_market(m.id) is m
    assert await src.get_market(uuid4()) is None


def test_is_open_true_only_when_open_and_before_deadline() -> None:
    now = datetime.now(UTC)
    future = now + timedelta(hours=1)
    past = now - timedelta(hours=1)
    assert _market(MARKET_OPEN, deadline=future).is_open(now) is True
    assert _market(MARKET_OPEN, deadline=past).is_open(now) is False  # past deadline
    assert _market(MARKET_CLOSED, deadline=future).is_open(now) is False  # not OPEN
    assert _market(MARKET_RESOLVED, deadline=future).is_open(now) is False


def test_outcome_lookup() -> None:
    yes = OutcomeView(id=uuid4(), label="YES")
    no = OutcomeView(id=uuid4(), label="NO")
    m = _market(
        MARKET_OPEN,
        deadline=datetime.now(UTC) + timedelta(days=1),
        outcomes=(yes, no),
    )
    assert m.outcome(yes.id) is yes
    assert m.outcome(no.id) is no
    assert m.outcome(uuid4()) is None


def test_views_are_frozen() -> None:
    o = OutcomeView(id=uuid4(), label="YES")
    with pytest.raises(FrozenInstanceError):
        o.label = "NO"  # type: ignore[misc]
