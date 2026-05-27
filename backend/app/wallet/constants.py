"""Wallet/ledger constants (Phase 3, WAL-06).

Single source of truth for the string literals and system-account UUIDs the
ledger uses. The two ``house_*`` account UUIDs are singletons seeded by Alembic
migration ``0003_phase3_wallet_ledger`` and referenced by the recharge service
(Plan 03-04) and settlement (Phase 5). Keeping them here (not inline in the
migration) lets the service and the migration agree on a single literal.

All values are intentionally plain ``str`` / ``UUID`` constants — no enums — to
match the lightweight literal style used elsewhere in the codebase and to keep
raw SQL seeds and ORM defaults trivially comparable.
"""

from __future__ import annotations

import uuid

# --------------------------------------------------------------------------- #
# Currency — v1 is single-currency play money (CONTEXT §decisions).
# --------------------------------------------------------------------------- #
PLAY_USD = "PLAY_USD"

# --------------------------------------------------------------------------- #
# Account owner types — who an account belongs to.
# --------------------------------------------------------------------------- #
OWNER_SYSTEM = "system"
OWNER_USER = "user"
OWNER_MARKET = "market"

# --------------------------------------------------------------------------- #
# Account kinds — the role an account plays in the ledger.
# --------------------------------------------------------------------------- #
KIND_USER_WALLET = "user_wallet"
KIND_HOUSE_PROMO = "house_promo"
KIND_HOUSE_REVENUE = "house_revenue"

# --------------------------------------------------------------------------- #
# Transfer kinds — the business event a transfer records.
# --------------------------------------------------------------------------- #
TRANSFER_RECHARGE = "recharge"
TRANSFER_OPENING = "opening"

# --------------------------------------------------------------------------- #
# Entry direction — the two legs of every double-entry transfer.
# --------------------------------------------------------------------------- #
DIRECTION_DEBIT = "debit"
DIRECTION_CREDIT = "credit"

# --------------------------------------------------------------------------- #
# Seeded system-account singletons (migration 0003 ON CONFLICT DO NOTHING).
# Fixed UUIDs so the recharge service (03-04) and settlement (Phase 5) can
# reference them without a runtime lookup-by-kind.
# --------------------------------------------------------------------------- #
HOUSE_PROMO_ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
"""Recharge SOURCE — funded with a large opening balance so admin recharges
never hit the ``balance >= 0`` floor."""

HOUSE_REVENUE_ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
"""House revenue SINK — seeded with balance 0; exercised by settlement (Phase 5)."""
