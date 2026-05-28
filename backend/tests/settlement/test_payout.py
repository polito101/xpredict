"""Pure payout & P&L math (Phase 5 settlement core).

Unit tests — NO database, NO Docker. They pin the locked v1 payout model from
``.planning/research/ARCHITECTURE.md`` (§"settlement", line ~316/509):

    odds are locked at placement; a winning bet's gross payout is
    ``stake / price_at_placement`` (the simple "bet at current price" model,
    no order book, no AMM). House edge / spread is a v2 MAYBE — NOT v1.

Money is ``NUMERIC(18, 4)`` (``app/db/types.py``), so every monetary result is
quantized to 4 decimal places, ROUND_HALF_UP. Decimals are built from strings
(never float) per the WAL-05 money discipline.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.settlement.payout import compute_payout, profit_or_loss, quantize_money


# --------------------------------------------------------------------------- #
# compute_payout — gross payout for a winning bet = stake / price.
# --------------------------------------------------------------------------- #
def test_compute_payout_even_division() -> None:
    # price 0.5 == decimal odds 2.0 → double your stake.
    assert compute_payout(Decimal("30"), Decimal("0.5")) == Decimal("60.0000")


def test_compute_payout_long_odds() -> None:
    # price 0.25 == decimal odds 4.0.
    assert compute_payout(Decimal("10"), Decimal("0.25")) == Decimal("40.0000")


def test_compute_payout_price_one_returns_stake() -> None:
    # A certainty (price 1.0) pays exactly the stake back — no winnings.
    assert compute_payout(Decimal("50"), Decimal("1")) == Decimal("50.0000")


def test_compute_payout_rounds_half_up_to_four_dp() -> None:
    # 1 / 0.7 = 1.428571... → 5th decimal is 7 → 4th rounds 5→6.
    assert compute_payout(Decimal("1"), Decimal("0.7")) == Decimal("1.4286")


def test_compute_payout_recurring_rounds_down() -> None:
    # 10 / 0.3 = 33.33333... → 5th decimal is 3 → stays 33.3333.
    assert compute_payout(Decimal("10"), Decimal("0.3")) == Decimal("33.3333")


def test_compute_payout_result_is_money_scale() -> None:
    # Always exactly 4-dp scale so the value is ledger-ready (NUMERIC(18,4)).
    assert compute_payout(Decimal("30"), Decimal("0.5")).as_tuple().exponent == -4


def test_compute_payout_rejects_nonpositive_stake() -> None:
    with pytest.raises(ValueError):
        compute_payout(Decimal("0"), Decimal("0.5"))
    with pytest.raises(ValueError):
        compute_payout(Decimal("-5"), Decimal("0.5"))


def test_compute_payout_rejects_price_at_or_below_zero() -> None:
    with pytest.raises(ValueError):
        compute_payout(Decimal("10"), Decimal("0"))
    with pytest.raises(ValueError):
        compute_payout(Decimal("10"), Decimal("-0.1"))


def test_compute_payout_rejects_price_above_one() -> None:
    # price is a probability/price in (0, 1]; > 1 is impossible.
    with pytest.raises(ValueError):
        compute_payout(Decimal("10"), Decimal("1.5"))


# --------------------------------------------------------------------------- #
# profit_or_loss — realized/unrealized P&L = payout - stake (works for both).
# --------------------------------------------------------------------------- #
def test_profit_or_loss_winner_is_positive() -> None:
    # Won: payout 60 on a 30 stake → +30 profit.
    assert profit_or_loss(Decimal("30"), Decimal("60")) == Decimal("30.0000")


def test_profit_or_loss_loser_is_negative_stake() -> None:
    # Lost: payout 0 → the whole stake is the loss.
    assert profit_or_loss(Decimal("30"), Decimal("0")) == Decimal("-30.0000")


def test_profit_or_loss_is_money_scale() -> None:
    assert profit_or_loss(Decimal("30"), Decimal("60")).as_tuple().exponent == -4


# --------------------------------------------------------------------------- #
# quantize_money — the 4-dp ROUND_HALF_UP money rounding the ledger expects.
# --------------------------------------------------------------------------- #
def test_quantize_money_rounds_half_up() -> None:
    assert quantize_money(Decimal("1.23455")) == Decimal("1.2346")


def test_quantize_money_rounds_down_below_half() -> None:
    assert quantize_money(Decimal("1.234549")) == Decimal("1.2345")


def test_quantize_money_passthrough_when_already_four_dp() -> None:
    assert quantize_money(Decimal("10.0000")) == Decimal("10.0000")
    assert quantize_money(Decimal("10.0000")).as_tuple().exponent == -4
