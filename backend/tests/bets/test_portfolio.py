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

import pytest

from app.bets.constants import BET_CLOSED, BET_PENDING, BET_SETTLED_LOST, BET_SETTLED_WON
from app.bets.portfolio import PositionInput, build_portfolio


def _pos(
    status: str,
    *,
    stake: str = "40",
    odds: str = "0.5",
    current_odds: str | None = None,
    exit_odds: str | None = None,
) -> PositionInput:
    return PositionInput(
        bet_id=uuid4(),
        market_id=uuid4(),
        outcome_id=uuid4(),
        stake=Decimal(stake),
        odds_at_placement=Decimal(odds),
        status=status,
        current_odds=Decimal(current_odds) if current_odds is not None else None,
        exit_odds=Decimal(exit_odds) if exit_odds is not None else None,
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


# --------------------------------------------------------------------------- #
# Mark-to-market: live current_odds enrichment on open positions (BET-07).
# --------------------------------------------------------------------------- #
def test_open_priced_gain() -> None:
    # entry 0.5, live 0.6 → 40 * 0.6 / 0.5 = 48 (outcome got more likely).
    p = build_portfolio([_pos(BET_PENDING, stake="40", odds="0.5", current_odds="0.6")])
    op = p.open[0]
    assert op.current_value == Decimal("48.0000")
    assert op.unrealized_pnl == Decimal("8.0000")
    assert op.priced is True


def test_open_priced_loss() -> None:
    # entry 0.5, live 0.4 → 40 * 0.4 / 0.5 = 32 (outcome got less likely).
    p = build_portfolio([_pos(BET_PENDING, stake="40", odds="0.5", current_odds="0.4")])
    op = p.open[0]
    assert op.current_value == Decimal("32.0000")
    assert op.unrealized_pnl == Decimal("-8.0000")
    assert op.priced is True


def test_open_priced_equal() -> None:
    # live price unchanged → zero unrealized P&L.
    p = build_portfolio([_pos(BET_PENDING, stake="40", odds="0.5", current_odds="0.5")])
    op = p.open[0]
    assert op.unrealized_pnl == Decimal("0.0000")
    assert op.priced is True


def test_open_unpriced_neutral_fallback() -> None:
    # No live price → current_value == stake, unrealized_pnl == 0, priced False.
    p = build_portfolio([_pos(BET_PENDING, stake="40", odds="0.5")])
    op = p.open[0]
    assert op.current_value == Decimal("40.0000")
    assert op.unrealized_pnl == Decimal("0.0000")
    assert op.priced is False
    # Existing potential fields must remain unchanged.
    assert op.potential_payout == Decimal("80.0000")
    assert op.potential_pnl == Decimal("40.0000")


def test_settled_position_carries_status() -> None:
    # SettledPosition must expose the bet's terminal status string.
    p = build_portfolio([_pos(BET_SETTLED_WON, stake="40", odds="0.5")])
    sp = p.settled[0]
    assert sp.status == BET_SETTLED_WON

    p2 = build_portfolio([_pos(BET_SETTLED_LOST, stake="40", odds="0.5")])
    sp2 = p2.settled[0]
    assert sp2.status == BET_SETTLED_LOST


def test_closed_position_realized_gain_from_exit_odds() -> None:
    # Bet 40 @ 0.5, cashed out when the outcome rose to 0.625 -> cash-out 50, realized +10.
    p = build_portfolio([_pos(BET_CLOSED, stake="40", odds="0.5", exit_odds="0.625")])
    assert p.open == ()
    sp = p.settled[0]
    assert sp.status == "CLOSED"
    assert sp.payout == Decimal("50.0000")
    assert sp.realized_pnl == Decimal("10.0000")
    assert sp.won is True


def test_closed_position_realized_loss_from_exit_odds() -> None:
    # Bet 40 @ 0.5, cashed out when the outcome fell to 0.375 -> cash-out 30, realized -10.
    p = build_portfolio([_pos(BET_CLOSED, stake="40", odds="0.5", exit_odds="0.375")])
    sp = p.settled[0]
    assert sp.status == "CLOSED"
    assert sp.payout == Decimal("30.0000")
    assert sp.realized_pnl == Decimal("-10.0000")
    assert sp.won is False


def test_closed_position_null_exit_odds_raises() -> None:
    # A CLOSED bet with NULL exit_odds is a data integrity violation — must raise, not silently
    # substitute odds_at_placement (which would produce a misleading zero P&L).
    with pytest.raises(ValueError, match="NULL exit_odds"):
        build_portfolio([_pos(BET_CLOSED, stake="40", odds="0.5", exit_odds=None)])
