"""Pure payout & P&L math for settlement (Phase 5).

No I/O, no ORM — just the deterministic money arithmetic that the settlement
orchestration (and the portfolio P&L read, BET-07) build on. Kept pure so it is
trivially unit-testable and reusable UNCHANGED by Phase 7's Polymarket
auto-resolution (the ``SettlementService`` is built once — ARCHITECTURE.md
§"settlement", ``payout.py`` = "pure payout math").

v1 payout model (ARCHITECTURE.md, "odds locked at placement"): a WINNING bet's
gross payout is ``stake / price`` where ``price`` is the chosen outcome's
price/probability captured at placement — the simple "bet at the current price"
model (no order book, no AMM, no house edge in v1; house edge is a v2 MAYBE per
FEATURES.md). A LOSING bet pays 0.

Money is ``NUMERIC(18, 4)`` (``app/db/types.py``); every result is quantized to
4 decimal places with ``ROUND_HALF_UP`` so it is ledger-ready, and ``Decimal``
inputs are expected to be built from strings (never float) per WAL-05.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# The ledger's monetary scale (NUMERIC(18, 4)). Every money value is rounded to
# this exponent so a service-computed payout matches what the DB stores.
_MONEY_QUANTUM = Decimal("0.0001")


def quantize_money(value: Decimal) -> Decimal:
    """Round ``value`` to the ledger's 4-dp money scale (``ROUND_HALF_UP``)."""
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def compute_payout(stake: Decimal, price: Decimal) -> Decimal:
    """Gross payout for a WINNING bet: ``stake / price``, money-quantized.

    ``price`` is the chosen outcome's price/probability at placement, in the
    half-open range ``(0, 1]`` (``1.0`` == a certainty, which pays the stake
    back with no winnings). The decimal-odds payout ``stake * (1 / price)``
    simplifies to ``stake / price`` (ARCHITECTURE.md "odds locked at placement").

    Raises :class:`ValueError` if ``stake <= 0`` or ``price`` is outside
    ``(0, 1]``. A losing bet must NOT be routed here — its payout is simply 0.
    """
    if stake <= 0:
        raise ValueError("stake must be > 0")
    if not (0 < price <= 1):
        raise ValueError("price must be in (0, 1]")
    return quantize_money(stake / price)


def profit_or_loss(stake: Decimal, payout: Decimal) -> Decimal:
    """Signed P&L of a position: ``payout - stake`` (money-quantized).

    Serves both realized P&L (pass the settled payout — ``0`` for a loss) and
    unrealized P&L (pass the current :func:`compute_payout` at the live price).
    A winner is positive; a loser is exactly ``-stake``.
    """
    return quantize_money(payout - stake)
