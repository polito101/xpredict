"""Bets/settlement constants (Phase 5).

Plain ``str`` literals (no enums) — matches the wallet ledger convention
(``app/wallet/constants.py``) so raw SQL seeds and ORM defaults stay trivially
comparable, AND so the new ledger vocabulary below is migration-free (the
``accounts.kind`` / ``transfers.kind`` columns are ``Text``, not Postgres enums).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Bet lifecycle status. Settlement transitions PENDING -> SETTLED_WON/_LOST.
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
