"""Pure portfolio / P&L read model (Phase 5, SC#7 / BET-07) — no I/O, no DB.

``build_portfolio`` partitions a player's bets into OPEN (still PENDING) and SETTLED
positions and computes the P&L for each from the price locked at placement, reusing the
same pure ``compute_payout`` / ``profit_or_loss`` the settlement engine uses. An open
position's "potential" payout is what it would pay IF its outcome wins, at the LOCKED odds
(the current-odds / live-unrealized view is enriched at integration when the market read
port is wired — see the service).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.bets.constants import BET_PENDING, BET_SETTLED_LOST, BET_SETTLED_WON
from app.bets.portfolio import PositionInput, build_portfolio


def _pos(status: str, *, stake: str = "40", odds: str = "0.5") -> PositionInput:
    return PositionInput(
        bet_id=uuid4(),
        market_id=uuid4(),
        outcome_id=uuid4(),
        stake=Decimal(stake),
        odds_at_placement=Decimal(odds),
        status=status,
    )


def test_open_position_potential_payout_at_locked_odds() -> None:
    p = build_portfolio([_pos(BET_PENDING, stake="40", odds="0.5")])
    assert len(p.open) == 1
    assert p.settled == ()
    op = p.open[0]
    assert op.potential_payout == Decimal("80.0000")  # 40 / 0.5
    assert op.potential_pnl == Decimal("40.0000")  # 80 - 40


def test_settled_won_realized_pnl() -> None:
    p = build_portfolio([_pos(BET_SETTLED_WON, stake="40", odds="0.5")])
    assert p.open == ()
    assert len(p.settled) == 1
    sp = p.settled[0]
    assert sp.won is True
    assert sp.payout == Decimal("80.0000")
    assert sp.realized_pnl == Decimal("40.0000")


def test_settled_lost_realized_pnl_is_negative_stake() -> None:
    p = build_portfolio([_pos(BET_SETTLED_LOST, stake="60", odds="0.5")])
    sp = p.settled[0]
    assert sp.won is False
    assert sp.payout == Decimal("0.0000")
    assert sp.realized_pnl == Decimal("-60.0000")


def test_mixed_portfolio_partitions_by_status() -> None:
    p = build_portfolio([_pos(BET_PENDING), _pos(BET_SETTLED_WON), _pos(BET_SETTLED_LOST)])
    assert len(p.open) == 1
    assert len(p.settled) == 2


def test_empty_portfolio() -> None:
    p = build_portfolio([])
    assert p.open == ()
    assert p.settled == ()
