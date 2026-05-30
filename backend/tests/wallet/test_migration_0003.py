"""Wave-0 integration tests for migration 0003 — the DB-level ledger invariants.

Against testcontainers Postgres 16 (parent ``engine`` fixture runs
``alembic upgrade head``). Uses raw ``text()`` SQL via ``async_session`` so the
deny-trigger + REVOKE fire on PUBLIC roles, exactly like
``tests/core/test_audit_immutability.py``.

Savepoint discipline (IMPORTANT): every statement expected to raise is wrapped
in ``async with async_session.begin_nested()`` so the resulting transaction
abort is scoped to the savepoint. Without this, the first ``DBAPIError`` would
leave the session-scoped outer transaction in a ``current transaction is
aborted`` state and every subsequent test would fail with
``InFailedSQLTransactionError`` (observed on the audit suite under shared
session scope). The savepoint rolls back cleanly and the outer tx stays usable.

Covers:
  - test_balance_check_rejects_negative: CHECK (balance >= 0) → 23514 (WAL-08).
  - test_transfers_update_blocked / _delete_blocked: append-only (WAL-06).
  - test_entries_update_blocked / _delete_blocked: append-only (WAL-06).
  - test_idempotency_key_unique: UNIQUE idempotency_key → 23505.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


def _sqlstate(err: DBAPIError) -> str | None:
    """Extract the Postgres SQLSTATE from a wrapped asyncpg error."""
    return getattr(err.orig, "sqlstate", None)


# ---------------------------------------------------------------------------
# WAL-08: CHECK (balance >= 0) rejects an overdraw at the DB level
# ---------------------------------------------------------------------------


async def test_balance_check_rejects_negative(funded_wallet, async_session: AsyncSession) -> None:
    """An UPDATE driving a wallet balance below 0 raises CHECK violation 23514.

    This proves WAL-08 at the DB level (not app-level) — the last line of
    defense behind the FOR UPDATE service guard (Plan 03-02).
    """
    with pytest.raises(DBAPIError) as exc_info:
        async with async_session.begin_nested():
            await async_session.execute(
                text("UPDATE accounts SET balance = balance - :amt WHERE id = :id"),
                {"amt": 999999, "id": funded_wallet},
            )
    assert (
        _sqlstate(exc_info.value) == "23514"
    ), f"expected CHECK violation 23514, got {_sqlstate(exc_info.value)}"


# ---------------------------------------------------------------------------
# WAL-06: transfers are append-only (deny-trigger + REVOKE)
# ---------------------------------------------------------------------------


async def test_transfers_update_blocked(async_session: AsyncSession) -> None:
    """UPDATE on transfers raises; message contains 'append-only' or 'permission denied'."""
    transfer_id = uuid4()
    async with async_session.begin_nested():
        await async_session.execute(
            text("INSERT INTO transfers (id, kind) VALUES (:id, 'opening')"),
            {"id": transfer_id},
        )

    with pytest.raises(DBAPIError) as exc_info:
        async with async_session.begin_nested():
            await async_session.execute(
                text("UPDATE transfers SET kind = 'mutated' WHERE id = :id"),
                {"id": transfer_id},
            )
    msg = str(exc_info.value).lower()
    assert "append-only" in msg or "permission denied" in msg


async def test_transfers_delete_blocked(async_session: AsyncSession) -> None:
    """DELETE on transfers raises (REVOKE + trigger fire on PUBLIC)."""
    transfer_id = uuid4()
    async with async_session.begin_nested():
        await async_session.execute(
            text("INSERT INTO transfers (id, kind) VALUES (:id, 'opening')"),
            {"id": transfer_id},
        )

    with pytest.raises(DBAPIError) as exc_info:
        async with async_session.begin_nested():
            await async_session.execute(
                text("DELETE FROM transfers WHERE id = :id"), {"id": transfer_id}
            )
    msg = str(exc_info.value).lower()
    assert "append-only" in msg or "permission denied" in msg


# ---------------------------------------------------------------------------
# WAL-06: entries are append-only (deny-trigger + REVOKE)
# ---------------------------------------------------------------------------


async def test_entries_update_blocked(funded_wallet, async_session: AsyncSession) -> None:
    """UPDATE on entries raises; needs a transfer + account to satisfy the FKs."""
    transfer_id = uuid4()
    entry_id = uuid4()
    async with async_session.begin_nested():
        await async_session.execute(
            text("INSERT INTO transfers (id, kind) VALUES (:t, 'opening')"),
            {"t": transfer_id},
        )
        await async_session.execute(
            text(
                """
                INSERT INTO entries (id, transfer_id, account_id, direction, amount)
                VALUES (:e, :t, :a, 'credit', :amt)
                """
            ),
            {"e": entry_id, "t": transfer_id, "a": funded_wallet, "amt": 10},
        )

    with pytest.raises(DBAPIError) as exc_info:
        async with async_session.begin_nested():
            await async_session.execute(
                text("UPDATE entries SET amount = 99 WHERE id = :id"), {"id": entry_id}
            )
    msg = str(exc_info.value).lower()
    assert "append-only" in msg or "permission denied" in msg


async def test_entries_delete_blocked(funded_wallet, async_session: AsyncSession) -> None:
    """DELETE on entries raises (REVOKE + trigger fire on PUBLIC)."""
    transfer_id = uuid4()
    entry_id = uuid4()
    async with async_session.begin_nested():
        await async_session.execute(
            text("INSERT INTO transfers (id, kind) VALUES (:t, 'opening')"),
            {"t": transfer_id},
        )
        await async_session.execute(
            text(
                """
                INSERT INTO entries (id, transfer_id, account_id, direction, amount)
                VALUES (:e, :t, :a, 'credit', :amt)
                """
            ),
            {"e": entry_id, "t": transfer_id, "a": funded_wallet, "amt": 10},
        )

    with pytest.raises(DBAPIError) as exc_info:
        async with async_session.begin_nested():
            await async_session.execute(
                text("DELETE FROM entries WHERE id = :id"), {"id": entry_id}
            )
    msg = str(exc_info.value).lower()
    assert "append-only" in msg or "permission denied" in msg


# ---------------------------------------------------------------------------
# WAL: idempotency_key UNIQUE → 23505 on a duplicate
# ---------------------------------------------------------------------------


async def test_idempotency_key_unique(async_session: AsyncSession) -> None:
    """Two transfers with the same idempotency_key raise unique violation 23505.

    The service (Plan 03-04) turns this into a true idempotent response; here we
    just prove the constraint fires at the DB level.
    """
    key = f"test-idem-{uuid4()}"
    async with async_session.begin_nested():
        await async_session.execute(
            text("INSERT INTO transfers (id, kind, idempotency_key) VALUES (:id, 'recharge', :k)"),
            {"id": uuid4(), "k": key},
        )

    with pytest.raises(DBAPIError) as exc_info:
        async with async_session.begin_nested():
            await async_session.execute(
                text(
                    "INSERT INTO transfers (id, kind, idempotency_key) VALUES (:id, 'recharge', :k)"
                ),
                {"id": uuid4(), "k": key},
            )
    assert (
        _sqlstate(exc_info.value) == "23505"
    ), f"expected unique violation 23505, got {_sqlstate(exc_info.value)}"
