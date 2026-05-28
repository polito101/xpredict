"""Settlement plan — pure resolution logic (Phase 5 settlement core).

Unit tests — NO database, NO Docker. Given the bets on a market (each carrying
its price locked at placement) and the winning outcome, ``build_settlement_plan``
classifies every bet as won/lost and computes its payout + P&L plus the two
aggregate ledger flows settlement will post (SC#5):

  - winners: ``market_liability -> user_wallet`` (sum = ``total_payout``)
  - losers:  ``market_liability -> house_revenue`` (sum = ``total_loser_stake``)

This is the pure heart that the (gated) transactional ``SettlementService`` will
apply to the ledger; it depends on neither Phase 4 nor migration 0005.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.bets.constants import BET_SETTLED_LOST, BET_SETTLED_WON
from app.settlement.plan import BetToSettle, build_settlement_plan

YES = uuid4()
NO = uuid4()


def _bet(outcome_id, stake: str, price: str) -> BetToSettle:
    return BetToSettle(
        bet_id=uuid4(),
        outcome_id=outcome_id,
        stake=Decimal(stake),
        price=Decimal(price),
    )


# --------------------------------------------------------------------------- #
# Mixed market: two winners + one loser.
# --------------------------------------------------------------------------- #
def test_plan_classifies_winners_and_losers() -> None:
    bets = [
        _bet(YES, "30", "0.5"),  # win -> payout 60, pnl +30
        _bet(YES, "10", "0.25"),  # win -> payout 40, pnl +30
        _bet(NO, "20", "0.5"),  # lose -> payout 0, pnl -20
    ]
    plan = build_settlement_plan(bets, winning_outcome_id=YES)

    by_id = {b.bet_id: b for b in plan.settled}
    assert by_id[bets[0].bet_id].won is True
    assert by_id[bets[0].bet_id].payout == Decimal("60.0000")
    assert by_id[bets[0].bet_id].pnl == Decimal("30.0000")
    assert by_id[bets[0].bet_id].status == BET_SETTLED_WON

    assert by_id[bets[2].bet_id].won is False
    assert by_id[bets[2].bet_id].payout == Decimal("0.0000")
    assert by_id[bets[2].bet_id].pnl == Decimal("-20.0000")
    assert by_id[bets[2].bet_id].status == BET_SETTLED_LOST


def test_plan_aggregate_flows() -> None:
    bets = [
        _bet(YES, "30", "0.5"),  # winner payout 60
        _bet(YES, "10", "0.25"),  # winner payout 40
        _bet(NO, "20", "0.5"),  # loser stake 20
    ]
    plan = build_settlement_plan(bets, winning_outcome_id=YES)
    assert plan.total_payout == Decimal("100.0000")  # 60 + 40 (-> winner wallets)
    assert plan.total_loser_stake == Decimal("20.0000")  # 20 (-> house_revenue)
    assert plan.winning_outcome_id == YES


def test_plan_one_settled_row_per_bet() -> None:
    bets = [_bet(YES, "5", "0.5"), _bet(NO, "5", "0.5"), _bet(YES, "5", "0.5")]
    plan = build_settlement_plan(bets, winning_outcome_id=YES)
    assert len(plan.settled) == 3
    assert {b.bet_id for b in plan.settled} == {b.bet_id for b in bets}


# --------------------------------------------------------------------------- #
# Degenerate distributions.
# --------------------------------------------------------------------------- #
def test_plan_all_winners_no_house_intake() -> None:
    bets = [_bet(YES, "10", "0.5"), _bet(YES, "20", "0.5")]
    plan = build_settlement_plan(bets, winning_outcome_id=YES)
    assert plan.total_loser_stake == Decimal("0.0000")
    assert plan.total_payout == Decimal("60.0000")  # 20 + 40
    assert all(b.won for b in plan.settled)


def test_plan_all_losers_no_payout() -> None:
    bets = [_bet(NO, "10", "0.5"), _bet(NO, "20", "0.5")]
    plan = build_settlement_plan(bets, winning_outcome_id=YES)
    assert plan.total_payout == Decimal("0.0000")
    assert plan.total_loser_stake == Decimal("30.0000")
    assert not any(b.won for b in plan.settled)


def test_plan_empty_market_is_zero() -> None:
    plan = build_settlement_plan([], winning_outcome_id=YES)
    assert plan.settled == ()
    assert plan.total_payout == Decimal("0.0000")
    assert plan.total_loser_stake == Decimal("0.0000")
