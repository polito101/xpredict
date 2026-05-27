"""Wallet-test fixtures — extend the parent conftest with ledger-scoped helpers.

These REUSE the parent ``tests/conftest.py`` ``engine`` / ``async_session``
fixtures (session-scoped, wrapped in a rolled-back transaction) — there is NO
duplicate testcontainer spin-up here. All fixtures share the session event loop
(``loop_scope="session"``) so asyncpg connections stay on one loop under
pytest-asyncio 0.25.

``funded_wallet`` INSERTs a ``user_wallet`` account with a starting balance and
yields its id; the balance is set directly on the mutable ``accounts`` cache
(legitimate — only ``transfers``/``entries`` are immutable). Cleanup deletes the
row so other tests in the same session don't see it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD

# A starting balance for the funded test wallet. Decimal end-to-end (PITFALLS #4).
FUNDED_WALLET_OPENING = Decimal("500.0000")


@pytest_asyncio.fixture(loop_scope="session")
async def funded_wallet(async_session: AsyncSession) -> AsyncGenerator[UUID, None]:
    """INSERT a ``user_wallet`` account with ``FUNDED_WALLET_OPENING`` balance.

    Yields the account id. Balance is set directly (accounts.balance is a
    mutable cache; immutability only guards transfers/entries).

    No explicit teardown DELETE: the parent ``async_session`` fixture wraps the
    whole session in a transaction that rolls back at teardown, so every row
    this fixture writes is discarded. A manual ``DELETE FROM accounts`` would
    additionally FAIL once a test books an (immutable) ``entries`` row against
    this wallet — the FK ``entries_account_id_fkey`` blocks the delete and the
    entry cannot be removed. Relying on the rollback is both correct and the
    pattern the parent fixture is designed for.
    """
    wallet_id = uuid4()
    owner_id = uuid4()
    await async_session.execute(
        text(
            """
            INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance)
            VALUES (:id, :owner_type, :owner_id, :kind, :currency, :balance)
            """
        ),
        {
            "id": wallet_id,
            "owner_type": OWNER_USER,
            "owner_id": owner_id,
            "kind": KIND_USER_WALLET,
            "currency": PLAY_USD,
            "balance": FUNDED_WALLET_OPENING,
        },
    )
    await async_session.flush()
    yield wallet_id
