"""Settlement plan — pure resolution logic (Phase 5 settlement core).

No I/O, no ORM. Given the bets on a market (each carrying its ``price`` locked at
placement — the "odds locked at placement" model, ARCHITECTURE.md) and the
winning outcome, :func:`build_settlement_plan` classifies every bet as won/lost
and computes its payout + P&L, plus the two aggregate ledger flows settlement
posts in one ACID transaction (SC#5):

  - winners: ``market_liability -> user_wallet``  (sum == :attr:`SettlementPlan.total_payout`)
  - losers:  ``market_liability -> house_revenue`` (sum == :attr:`SettlementPlan.total_loser_stake`)

This is the pure heart the (gated) transactional ``SettlementService`` applies to
the ledger; it depends on neither Phase 4's models nor migration 0005. The
``price`` per bet is the Phase 4 odds seam — captured at placement, supplied here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.bets.constants import BET_SETTLED_LOST, BET_SETTLED_WON
from app.settlement.payout import compute_payout, profit_or_loss, quantize_money

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class BetToSettle:
    """One pending bet's settlement-relevant facts (price locked at placement)."""

    bet_id: UUID
    outcome_id: UUID
    stake: Decimal
    price: Decimal  # chosen outcome's price/probability at placement, in (0, 1]


@dataclass(frozen=True, slots=True)
class SettledBet:
    """The computed outcome for one bet — what settlement writes back."""

    bet_id: UUID
    won: bool
    payout: Decimal  # gross credited to the wallet on a win; 0 on a loss
    pnl: Decimal  # realized P&L = payout - stake (positive win / negative loss)
    status: str  # BET_SETTLED_WON | BET_SETTLED_LOST


@dataclass(frozen=True, slots=True)
class SettlementPlan:
    """The full per-market settlement: per-bet results + the aggregate flows."""

    winning_outcome_id: UUID
    settled: tuple[SettledBet, ...]
    total_payout: Decimal  # winners -> wallets (market_liability debit)
    total_loser_stake: Decimal  # losers -> house_revenue (market_liability debit)


def build_settlement_plan(
    bets: Sequence[BetToSettle],
    *,
    winning_outcome_id: UUID,
) -> SettlementPlan:
    """Classify ``bets`` against ``winning_outcome_id`` and compute payouts + flows.

    A bet on the winning outcome wins ``stake / price`` (:func:`compute_payout`);
    every other bet loses (payout 0, P&L ``-stake``). Pure and total — an empty
    market yields an empty plan with zero flows.
    """
    settled: list[SettledBet] = []
    total_payout = _ZERO
    total_loser_stake = _ZERO

    for bet in bets:
        if bet.outcome_id == winning_outcome_id:
            payout = compute_payout(bet.stake, bet.price)
            total_payout += payout
            settled.append(
                SettledBet(
                    bet_id=bet.bet_id,
                    won=True,
                    payout=payout,
                    pnl=profit_or_loss(bet.stake, payout),
                    status=BET_SETTLED_WON,
                )
            )
        else:
            total_loser_stake += bet.stake
            settled.append(
                SettledBet(
                    bet_id=bet.bet_id,
                    won=False,
                    payout=quantize_money(_ZERO),
                    pnl=profit_or_loss(bet.stake, _ZERO),
                    status=BET_SETTLED_LOST,
                )
            )

    return SettlementPlan(
        winning_outcome_id=winning_outcome_id,
        settled=tuple(settled),
        total_payout=quantize_money(total_payout),
        total_loser_stake=quantize_money(total_loser_stake),
    )
