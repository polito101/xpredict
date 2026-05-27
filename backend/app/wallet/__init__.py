"""Wallet & double-entry ledger (Phase 3 — see ROADMAP.md).

Re-exports the three ORM models so importing ``app.wallet`` is enough to
register ``Account`` / ``Transfer`` / ``Entry`` against ``Base.metadata`` for
Alembic autogenerate and the test fixtures.
"""

from __future__ import annotations

from app.wallet.models import Account, Entry, Transfer

__all__ = ["Account", "Entry", "Transfer"]
