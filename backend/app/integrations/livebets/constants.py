"""Live-bets bridge constants (v1.3, LB-A) — account/transfer/status literals.

Single source of truth for the string literals and the system-account UUID the
live-bets ledger mirror uses. Plain ``str`` / ``UUID`` constants — no enums — to
match the lightweight literal style of ``app/wallet/constants.py`` and
``app/bets/constants.py``, so raw SQL seeds and ORM defaults stay trivially
comparable AND the new ledger vocabulary stays migration-free (``accounts.kind``
and ``transfers.kind`` are ``Text``, not Postgres enums).

The ``livebets_escrow`` singleton account UUID is seeded by Alembic migration
``0011_livebets_bridge`` and referenced by ``LiveBetsBridge`` without a runtime
lookup-by-kind — exactly like ``HOUSE_PROMO_ACCOUNT_ID`` / ``HOUSE_REVENUE_ACCOUNT_ID``.

The mirror-table status vocabulary tracks live-bets' REAL ``BetStatus`` enum
(``live-bets/live_bets/models.py``): ``PENDING | WON | LOST | REFUNDED | VOIDED``.
There is NO ``VOID`` status — both ``REFUNDED`` and ``VOIDED`` take the stake-return
leg on settlement.
"""

from __future__ import annotations

import uuid

# --------------------------------------------------------------------------- #
# Account kind — the role the new singleton plays in the ledger.
# --------------------------------------------------------------------------- #
KIND_LIVEBETS_ESCROW = "livebets_escrow"
"""Account kind for the live-bets escrow singleton (``owner_type='system'``,
``owner_id=NULL``) — the sink a stake is credited to on placement and the source
the stake is returned from on win/refund/void."""

# --------------------------------------------------------------------------- #
# Seeded system-account singleton (migration 0011 ON CONFLICT DO NOTHING).
# Fixed UUID in the ``...00b1`` block (HOUSE_PROMO is ``...00a1``, HOUSE_REVENUE
# ``...00a2``) so it never collides with the house singletons and the service can
# reference it directly, mirroring HOUSE_PROMO_ACCOUNT_ID.
# --------------------------------------------------------------------------- #
LIVEBETS_ESCROW_ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
"""Live-bets escrow SINK/SOURCE — seeded with balance 0; nets to zero across any
full placed -> settled cycle (placed credits +stake; win/loss/refund debits -stake)."""

# --------------------------------------------------------------------------- #
# Transfer kinds — the business event each transfer records. Migration-free
# (the ``transfers.kind`` column is ``Text``).
# --------------------------------------------------------------------------- #
TRANSFER_LIVEBETS_PLACED = "livebets_placed"
"""Placement debit: ``user_wallet -> livebets_escrow`` (the stake)."""

TRANSFER_LIVEBETS_SETTLE_STAKE_RETURN = "livebets_settle_stake_return"
"""WON leg 1: ``livebets_escrow -> user_wallet`` — returns the winner's own stake."""

TRANSFER_LIVEBETS_SETTLE_WINNINGS = "livebets_settle_winnings"
"""WON leg 2: ``house_promo -> user_wallet`` — the net winnings (payout - stake)."""

TRANSFER_LIVEBETS_SETTLE_LOSS = "livebets_settle_loss"
"""LOST leg: ``livebets_escrow -> house_revenue`` — the lost stake becomes house
revenue. Loss sink is ``house_revenue`` (LOCKED DECISION), mirroring the
settlement loser sweep ``market_liability -> house_revenue``."""

TRANSFER_LIVEBETS_VOID_REFUND = "livebets_void_refund"
"""REFUNDED/VOIDED leg: ``livebets_escrow -> user_wallet`` — returns the stake."""

# --------------------------------------------------------------------------- #
# Mirror-table status literals — live-bets' REAL BetStatus enum (no ``VOID``).
# --------------------------------------------------------------------------- #
LIVEBETS_PENDING = "PENDING"
LIVEBETS_WON = "WON"
LIVEBETS_LOST = "LOST"
LIVEBETS_REFUNDED = "REFUNDED"
LIVEBETS_VOIDED = "VOIDED"

LIVEBETS_REFUND_STATUSES = frozenset({LIVEBETS_REFUNDED, LIVEBETS_VOIDED})
"""Both REFUNDED and VOIDED take the same stake-return leg
(``livebets_escrow -> user_wallet``)."""

LIVEBETS_SETTLED_STATUSES = frozenset(
    {LIVEBETS_WON, LIVEBETS_LOST, LIVEBETS_REFUNDED, LIVEBETS_VOIDED}
)
"""The terminal statuses ``record_settled`` accepts (anything not PENDING)."""


# --------------------------------------------------------------------------- #
# Idempotency-key helpers (mirror ``settle_idempotency_key`` in
# ``app/settlement/constants.py``). Centralized here so the service and the
# LB-A-02 tests agree on ONE literal.
#
# ``transfers.idempotency_key`` is UNIQUE, so the two WON legs (stake + winnings)
# in a single settle CANNOT share one key — they are suffixed ``:stake`` /
# ``:winnings`` exactly as settlement uses per-leg ``settle:{bet_id}:{leg}`` keys.
# LOST, REFUNDED and VOIDED each post a SINGLE leg, so they use the bare
# ``livebets:{bet_id}:settled`` key directly.
# --------------------------------------------------------------------------- #
def placed_idempotency_key(bet_id: object) -> str:
    """Deterministic placement key — ``livebets:{bet_id}:placed``."""
    return f"livebets:{bet_id}:placed"


def settled_idempotency_key(bet_id: object) -> str:
    """Deterministic single-leg settle key — ``livebets:{bet_id}:settled``.

    Used directly by the LOST / REFUNDED / VOIDED single-leg settles. The WON
    settle posts TWO legs and MUST NOT reuse this bare key for both — use
    :func:`settled_stake_idempotency_key` / :func:`settled_winnings_idempotency_key`.
    """
    return f"livebets:{bet_id}:settled"


def settled_stake_idempotency_key(bet_id: object) -> str:
    """WON leg-1 key — ``livebets:{bet_id}:settled:stake`` (distinct from leg 2)."""
    return f"livebets:{bet_id}:settled:stake"


def settled_winnings_idempotency_key(bet_id: object) -> str:
    """WON leg-2 key — ``livebets:{bet_id}:settled:winnings`` (distinct from leg 1)."""
    return f"livebets:{bet_id}:settled:winnings"
