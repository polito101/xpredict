"""Wave-0 schema tests for the wallet ledger — table shape + seeded singletons.

Integration tests against testcontainers Postgres 16 (lazy ``engine`` fixture in
the parent conftest, which runs ``alembic upgrade head`` — so migration 0003 is
applied). They consume ``async_session`` (session-scoped, rolled back), mirroring
``tests/core/test_audit_immutability.py``.

Covers:
  - test_accounts_table_shape: INSERT without tenant_id defaults to
    TENANT_ID_DEFAULT (mirror of test_tenant_id_default) — PLT-01.
  - test_system_accounts_seeded: house_promo + house_revenue rows exist after
    ``alembic upgrade head`` with the constants.py UUIDs + correct kinds.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
    KIND_HOUSE_PROMO,
    KIND_HOUSE_REVENUE,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
)

pytestmark = [
    pytest.mark.integration,
    # Share the session-scoped event loop with engine + async_session fixtures.
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# PLT-01: tenant_id ghost column default on accounts
# ---------------------------------------------------------------------------


async def test_accounts_table_shape(async_session: AsyncSession) -> None:
    """INSERT into accounts without ``tenant_id`` defaults to TENANT_ID_DEFAULT.

    Mirrors ``tests/core/test_audit_immutability.py::test_tenant_id_default``.
    Also confirms the column defaults (currency=PLAY_USD, balance=0, version=0)
    the ORM/migration declare.
    """
    account_id = uuid4()
    owner_id = uuid4()
    await async_session.execute(
        text(
            """
            INSERT INTO accounts (id, owner_type, owner_id, kind)
            VALUES (:id, :owner_type, :owner_id, :kind)
            """
        ),
        {
            "id": account_id,
            "owner_type": OWNER_USER,
            "owner_id": owner_id,
            "kind": KIND_USER_WALLET,
        },
    )

    row = (
        await async_session.execute(
            text(
                """
                SELECT tenant_id, currency, balance, version
                FROM accounts WHERE id = :id
                """
            ),
            {"id": account_id},
        )
    ).one()

    assert row.tenant_id == UUID("00000000-0000-0000-0000-000000000001")
    assert row.tenant_id == Settings().TENANT_ID_DEFAULT
    assert row.currency == PLAY_USD
    assert row.balance == 0
    assert row.version == 0

    # Cleanup (mutable table — plain DELETE allowed).
    await async_session.execute(text("DELETE FROM accounts WHERE id = :id"), {"id": account_id})


# ---------------------------------------------------------------------------
# Migration 0003 seed: house_promo + house_revenue singletons
# ---------------------------------------------------------------------------


async def test_system_accounts_seeded(async_session: AsyncSession) -> None:
    """house_promo + house_revenue exist after ``alembic upgrade head``.

    The migration seeds both with the fixed constants.py UUIDs. house_promo is
    funded (balance > 0, the recharge source); house_revenue starts at 0.
    """
    promo = (
        await async_session.execute(
            text("SELECT owner_type, kind, currency, balance FROM accounts WHERE id = :id"),
            {"id": HOUSE_PROMO_ACCOUNT_ID},
        )
    ).one()
    assert promo.kind == KIND_HOUSE_PROMO
    assert promo.owner_type == "system"
    assert promo.currency == PLAY_USD
    assert promo.balance > 0, "house_promo must be funded so recharges never underflow"

    revenue = (
        await async_session.execute(
            text("SELECT owner_type, kind, currency, balance FROM accounts WHERE id = :id"),
            {"id": HOUSE_REVENUE_ACCOUNT_ID},
        )
    ).one()
    assert revenue.kind == KIND_HOUSE_REVENUE
    assert revenue.owner_type == "system"
    assert revenue.currency == PLAY_USD
    assert revenue.balance == 0
