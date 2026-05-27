"""Settlement ledger vocabulary (Phase 5).

Plain ``str`` literals (no enums) — matches ``app/wallet/constants.py`` /
``app/bets/constants.py`` so the new transfer kinds are migration-free (the
``transfers.kind`` column is ``Text``) and raw SQL stays trivially comparable.
"""

from __future__ import annotations

from uuid import UUID

# --------------------------------------------------------------------------- #
# Transfer kinds the settlement pass posts (migration-free; kind is Text).
# A WINNING bet posts two legs (stake return + winnings); a LOSING bet, one.
# --------------------------------------------------------------------------- #
TRANSFER_SETTLE_STAKE_RETURN = "settle_stake_return"
"""Winner leg 1: ``market_liability -> user_wallet`` — returns the winner's own stake."""

TRANSFER_SETTLE_WINNINGS = "settle_winnings"
"""Winner leg 2: ``house_promo -> user_wallet`` — the net winnings (payout - stake)."""

TRANSFER_SETTLE_LOSS = "settle_loss"
"""Loser leg: ``market_liability -> house_revenue`` — the lost stake becomes house revenue."""

# --------------------------------------------------------------------------- #
# Idempotency leg suffixes (one transfer per leg per bet).
# --------------------------------------------------------------------------- #
SETTLE_LEG_STAKE = "stake"
SETTLE_LEG_WIN = "win"
SETTLE_LEG_LOSS = "loss"


def settle_idempotency_key(bet_id: UUID, leg: str) -> str:
    """Deterministic per-bet, per-leg idempotency key — ``settle:{bet_id}:{leg}``.

    Reuses the EXISTING ``transfers.idempotency_key`` UNIQUE (no new constraint, no
    migration): a concurrent double-resolve collides on Postgres ``23505`` and the whole
    settlement transaction rolls back rather than double-paying (SC#6 defense-in-depth;
    the primary idempotency guard is the ``status = PENDING`` filter in the service).
    """
    return f"settle:{bet_id}:{leg}"
