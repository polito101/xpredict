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
# Reversal (SC#8) — compensating transfer kinds, the INVERSE of each settle leg.
# A reversal NEVER deletes/updates the original entries (WAL-06 append-only); it
# posts new, opposite-direction transfers that restore the pre-settlement state.
# --------------------------------------------------------------------------- #
TRANSFER_REVERSE_STAKE_RETURN = "reverse_stake_return"
"""Inverse of a winner's stake return: ``user_wallet -> market_liability``."""

TRANSFER_REVERSE_WINNINGS = "reverse_winnings"
"""Inverse of a winner's winnings: ``user_wallet -> house_promo``."""

TRANSFER_REVERSE_LOSS = "reverse_loss"
"""Inverse of a loser's sweep: ``house_revenue -> market_liability``."""

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


def reverse_idempotency_key(bet_id: UUID, leg: str) -> str:
    """Deterministic per-bet, per-leg reversal key — ``reverse:{bet_id}:{leg}``.

    Same role as :func:`settle_idempotency_key` for the reversal pass: a concurrent
    double-reverse collides on ``23505`` and rolls back. Distinct namespace from settle
    keys, and a reversal flips bets back to ``PENDING`` so a re-reverse is a status-guarded
    no-op — the keys are never reused within a single settlement round.

    NOTE (follow-up): re-RESOLVING a market AFTER a reversal would reuse the original
    ``settle:{bet_id}:{leg}`` keys and collide. Re-resolution after reversal therefore needs
    a per-bet settlement epoch in the key (deferred); v1 reversal restores the pre-settlement
    state for audit/correction, it does not yet re-resolve.
    """
    return f"reverse:{bet_id}:{leg}"
