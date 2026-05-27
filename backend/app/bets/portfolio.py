"""Pure portfolio / P&L read model (Phase 5, SC#7 / BET-07).

No I/O, no ORM — given a player's bets (each carrying the price locked at placement),
:func:`build_portfolio` partitions them into OPEN (still ``PENDING``) and SETTLED positions
and computes each one's P&L, reusing the SAME pure ``compute_payout`` / ``profit_or_loss``
the settlement engine uses (``app/settlement/payout.py``, which documents this exact reuse).

For an OPEN position the "potential" payout is what it would pay IF its outcome wins, at the
LOCKED odds — a deterministic, Phase-4-free view. The live "current odds / unrealized P&L at
current odds" (SC#7) is layered on at integration when the market read port is wired; the
read service can enrich open positions then without changing this pure core.

For a SETTLED position the realized P&L equals exactly what settlement posted: a winner's
``compute_payout(stake, price) - stake``, a loser's ``-stake``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.bets.constants import BET_PENDING, BET_SETTLED_WON
from app.settlement.payout import compute_payout, profit_or_loss, quantize_money

_ZERO = quantize_money(Decimal("0"))


@dataclass(frozen=True, slots=True)
class PositionInput:
    """One bet's portfolio-relevant facts (price locked at placement)."""

    bet_id: UUID
    market_id: UUID
    outcome_id: UUID
    stake: Decimal
    odds_at_placement: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class OpenPosition:
    """A still-pending bet — payout/P&L are POTENTIAL (if the outcome wins, at locked odds)."""

    bet_id: UUID
    market_id: UUID
    outcome_id: UUID
    stake: Decimal
    odds_at_placement: Decimal
    potential_payout: Decimal  # stake / odds — what a win pays at the locked price
    potential_pnl: Decimal  # potential_payout - stake


@dataclass(frozen=True, slots=True)
class SettledPosition:
    """A resolved bet — payout/P&L are REALIZED (exactly what settlement posted)."""

    bet_id: UUID
    market_id: UUID
    outcome_id: UUID
    stake: Decimal
    odds_at_placement: Decimal
    won: bool
    payout: Decimal  # compute_payout on a win; 0 on a loss
    realized_pnl: Decimal  # payout - stake (positive win / -stake loss)


@dataclass(frozen=True, slots=True)
class Portfolio:
    """A player's positions split into open + settled."""

    open: tuple[OpenPosition, ...]
    settled: tuple[SettledPosition, ...]


def build_portfolio(positions: Sequence[PositionInput]) -> Portfolio:
    """Partition ``positions`` into open/settled and compute each one's payout + P&L."""
    open_positions: list[OpenPosition] = []
    settled_positions: list[SettledPosition] = []

    for p in positions:
        if p.status == BET_PENDING:
            potential = compute_payout(p.stake, p.odds_at_placement)
            open_positions.append(
                OpenPosition(
                    bet_id=p.bet_id,
                    market_id=p.market_id,
                    outcome_id=p.outcome_id,
                    stake=p.stake,
                    odds_at_placement=p.odds_at_placement,
                    potential_payout=potential,
                    potential_pnl=profit_or_loss(p.stake, potential),
                )
            )
        else:
            won = p.status == BET_SETTLED_WON
            payout = compute_payout(p.stake, p.odds_at_placement) if won else _ZERO
            settled_positions.append(
                SettledPosition(
                    bet_id=p.bet_id,
                    market_id=p.market_id,
                    outcome_id=p.outcome_id,
                    stake=p.stake,
                    odds_at_placement=p.odds_at_placement,
                    won=won,
                    payout=payout,
                    realized_pnl=profit_or_loss(p.stake, payout),
                )
            )

    return Portfolio(open=tuple(open_positions), settled=tuple(settled_positions))
