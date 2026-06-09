"""Bets/settlement constants (Phase 5).

Plain ``str`` literals (no enums) — matches the wallet ledger convention
(``app/wallet/constants.py``) so raw SQL seeds and ORM defaults stay trivially
comparable, AND so the new ledger vocabulary below is migration-free (the
``accounts.kind`` / ``transfers.kind`` columns are ``Text``, not Postgres enums).
"""

from __future__ import annotations

from uuid import UUID

# --------------------------------------------------------------------------- #
# Bet lifecycle status. Settlement transitions PENDING -> SETTLED_WON/_LOST;
# early close (cash-out) transitions PENDING -> CLOSED (see BET_CLOSED below).
# --------------------------------------------------------------------------- #
BET_PENDING = "PENDING"
BET_SETTLED_WON = "SETTLED_WON"
BET_SETTLED_LOST = "SETTLED_LOST"

# --------------------------------------------------------------------------- #
# Ledger vocabulary Phase 5 adds — all migration-free (kind columns are Text).
# --------------------------------------------------------------------------- #
KIND_MARKET_LIABILITY = "market_liability"
"""Account kind for a per-market liability account
(``owner_type='market'``, ``owner_id=market_id``) — the sink a stake is credited to
on bet placement and the source winners are paid from on settlement."""

TRANSFER_BET_PLACED = "bet_placed"
"""Transfer kind for a stake debit ``user_wallet`` -> credit ``market_liability``."""

# --------------------------------------------------------------------------- #
# Early-close status.
# --------------------------------------------------------------------------- #
BET_CLOSED = "CLOSED"
"""Terminal status for a position the player cashed out before resolution (early close)."""

# --------------------------------------------------------------------------- #
# Early-close ledger vocabulary (migration-free; transfers.kind is Text). Mirrors the
# settlement legs but for a single bet cashed out at the live price.
# --------------------------------------------------------------------------- #
TRANSFER_CLOSE_STAKE_RETURN = "close_stake_return"
"""Close leg: ``market_liability -> user_wallet`` — releases the stake (gain) or the
cash-out value (loss) from the per-market liability pool."""

TRANSFER_CLOSE_WINNINGS = "close_winnings"
"""Close leg (gain): ``house_promo -> user_wallet`` — the gain above stake (cash_out - stake)."""

TRANSFER_CLOSE_LOSS = "close_loss"
"""Close leg (loss): ``market_liability -> house_revenue`` — the shortfall (stake - cash_out)."""

CLOSE_LEG_STAKE = "stake"
CLOSE_LEG_WIN = "win"
CLOSE_LEG_LOSS = "loss"


def close_idempotency_key(bet_id: UUID, leg: str) -> str:
    """Deterministic per-bet, per-leg early-close key — ``close:{bet_id}:{leg}``.

    Distinct namespace from settle/reverse keys; a CLOSED bet leaves ``PENDING`` so a
    re-close is status-guarded, and a concurrent double-close collides on ``23505``.
    """
    return f"close:{bet_id}:{leg}"
