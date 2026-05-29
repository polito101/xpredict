"""SC#3 (service-level) — idempotent recharge: a duplicate key never double-credits.

Drives the production ``WalletService.recharge`` against testcontainers Postgres.
Reproduces Spike 003 part 2 (10 concurrent same-key → 1 applied + 9 deduped) on
production code (T-03-07, WAL-07):

  - Two SEQUENTIAL recharges with the same ``idempotency_key`` return the SAME
    transfer id; exactly one transfer + one entry-pair exist for that key; the
    wallet is credited ONCE.
  - K CONCURRENT recharges with one shared key → exactly 1 applied, K-1 deduped,
    balance credited once.

The mechanism (RESEARCH Pattern 2 / Pitfall 2): the ``transfers`` INSERT raises
``IntegrityError`` (sqlstate 23505) on the UNIQUE ``idempotency_key``; the service
catches it and SELECTs + returns the existing transfer — a true idempotent
response, NOT a 409/500.

Each recharge opens its OWN committed session from ``_get_session_maker()``
(concurrency cannot share the rollback fixture). A fresh user wallet with a unique
``owner_id`` and a per-test unique ``idempotency_key`` isolate every assertion;
committed transfers/entries are immutable (no teardown) but scoped reads keep tests
independent.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.db.session import _get_session_maker
from app.wallet.constants import (
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
    TRANSFER_RECHARGE,
)
from app.wallet.service import WalletService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine):
    """Depend on ``engine`` so the testcontainer is up + ``DATABASE_URL`` rewritten.

    These tests open their own committed sessions via ``_get_session_maker()``
    (concurrency cannot share the rollback ``async_session``); they still need
    the ``engine`` fixture's side effects (container start, alembic upgrade, env
    rewrite, cache clear) before the production engine factory is used.
    """
    return engine


RECHARGE_AMOUNT = Decimal("250.0000")


async def _seed_user_wallet() -> UUID:
    """Commit a fresh empty ``user_wallet`` and return the owning user_id.

    Returns the ``owner_id`` (the recharge target key), not the account id —
    ``WalletService.recharge`` resolves the wallet account from the user id.
    """
    session_maker = _get_session_maker()
    user_id = uuid4()
    async with session_maker() as s, s.begin():
        await s.execute(
            text(
                """
                INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance)
                VALUES (:id, :owner_user, :uid, :kind, :cur, 0)
                """
            ),
            {
                "id": uuid4(),
                "owner_user": OWNER_USER,
                "uid": user_id,
                "kind": KIND_USER_WALLET,
                "cur": PLAY_USD,
            },
        )
    return user_id


async def _wallet_balance(user_id: UUID) -> Decimal:
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return (
            await s.execute(
                text(
                    """
                    SELECT balance FROM accounts
                    WHERE owner_type = :owner_user AND owner_id = :uid
                      AND kind = :kind AND currency = :cur
                    """
                ),
                {
                    "owner_user": OWNER_USER,
                    "uid": user_id,
                    "kind": KIND_USER_WALLET,
                    "cur": PLAY_USD,
                },
            )
        ).scalar_one()


async def _counts_for_key(key: str) -> tuple[int, int]:
    """Return (transfer_count, entry_count) booked under ``idempotency_key``."""
    session_maker = _get_session_maker()
    async with session_maker() as s:
        transfers = (
            await s.execute(
                text("SELECT count(*) FROM transfers WHERE idempotency_key = :k"),
                {"k": key},
            )
        ).scalar_one()
        entries = (
            await s.execute(
                text(
                    "SELECT count(*) FROM entries e JOIN transfers t "
                    "ON e.transfer_id = t.id WHERE t.idempotency_key = :k"
                ),
                {"k": key},
            )
        ).scalar_one()
    return int(transfers), int(entries)


async def _one_recharge(user_id: UUID, key: str) -> UUID:
    """Drive ONE production recharge on its own committed session; return transfer id."""
    session_maker = _get_session_maker()
    async with session_maker() as s:
        transfer = await WalletService.recharge(
            s,
            user_id=user_id,
            amount=RECHARGE_AMOUNT,
            reason="test idempotent recharge",
            idempotency_key=key,
        )
        return transfer.id


async def test_idempotent_recharge_returns_same_transfer() -> None:
    """Two recharges, same key → same transfer id, one entry-pair, credited once."""
    user_id = await _seed_user_wallet()
    key = f"idem-recharge-{uuid4()}"

    first_id = await _one_recharge(user_id, key)
    second_id = await _one_recharge(user_id, key)

    # True idempotent response: the second call returns the FIRST transfer.
    assert first_id == second_id, "duplicate key must return the existing transfer id"

    # Exactly one transfer + one (debit, credit) entry-pair under this key.
    transfers, entries = await _counts_for_key(key)
    assert transfers == 1, f"expected 1 transfer for the key, got {transfers}"
    assert entries == 2, f"expected 1 entry-pair (2 rows), got {entries}"

    # The wallet is credited exactly ONCE, not twice.
    assert await _wallet_balance(user_id) == RECHARGE_AMOUNT


async def test_concurrent_same_key_one_applied() -> None:
    """K concurrent recharges, one shared key → 1 applied, K-1 deduped, credited once."""
    user_id = await _seed_user_wallet()
    key = f"idem-concurrent-{uuid4()}"
    k = 10

    transfer_ids = await asyncio.gather(*(_one_recharge(user_id, key) for _ in range(k)))

    # Every concurrent caller returns the SAME single applied transfer id.
    assert len(set(transfer_ids)) == 1, (
        f"expected all {k} callers to resolve to one transfer id, "
        f"got {len(set(transfer_ids))} distinct ids"
    )

    # Exactly one transfer + one entry-pair were actually applied (K-1 deduped).
    transfers, entries = await _counts_for_key(key)
    assert transfers == 1, f"expected exactly 1 applied transfer, got {transfers}"
    assert entries == 2, f"expected exactly 1 entry-pair, got {entries}"
    assert all(t.kind == TRANSFER_RECHARGE for t in await _transfers_for_key(key))

    # Credited exactly once despite K concurrent attempts.
    assert await _wallet_balance(user_id) == RECHARGE_AMOUNT


async def _transfers_for_key(key: str) -> list:
    """Fetch the Transfer ORM rows booked under ``idempotency_key`` (assert helper)."""
    from sqlalchemy import select

    from app.wallet.models import Transfer

    session_maker = _get_session_maker()
    async with session_maker() as s:
        return list(
            (await s.execute(select(Transfer).where(Transfer.idempotency_key == key))).scalars()
        )
