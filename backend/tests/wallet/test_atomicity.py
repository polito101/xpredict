"""PITFALLS #10 — a fault mid-transaction rolls EVERYTHING back (atomic double-entry).

Drives the production ``WalletService.transfer`` against testcontainers Postgres and
proves Spike 003 part 1 / ``harness.attempt_with_fault`` on production code
(T-03-08, WAL-07): if anything raises after the transfer row, the two entries, and
both balance updates have been written but BEFORE the ``session.begin()`` block
commits, the transaction rolls back wholesale — no transfer, no entries, no balance
change persists. There is never a half-applied ledger (an orphan entry, an
unbalanced transfer, or a debited cache with no matching entry).

The fault is injected by monkeypatching ``_post_transfer`` to do the FULL real work
(via the genuine implementation) and then raise ``FaultInjected`` while still inside
``transfer``'s ``session.begin()`` unit of work — so we are testing the production
transaction boundary, not a synthetic one. A fresh session (from the production
``_get_session_maker()``) commits the seed wallet; the fault attempt and the
post-fault counts use their own sessions, mirroring ``harness.count_rows``.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.db.session import _get_session_maker
from app.wallet.constants import (
    KIND_USER_WALLET,
    OWNER_MARKET,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.service import WalletService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine):
    """Depend on ``engine`` so the testcontainer is up + ``DATABASE_URL`` rewritten.

    This test opens its own committed sessions via ``_get_session_maker()`` and
    monkeypatches the service, so it does not use the rollback ``async_session``;
    it still needs the ``engine`` fixture's side effects (container start, alembic
    upgrade, env rewrite, cache clear) before the production engine factory runs.
    """
    return engine


OPENING = Decimal("500.0000")
MOVE_AMOUNT = Decimal("100.0000")
TRANSFER_KIND = "test_fault"


class FaultInjected(Exception):
    """Raised on purpose mid-transaction to prove rollback (mirrors the harness)."""


async def _seed_two_accounts() -> tuple[UUID, UUID]:
    """Commit a funded wallet + a counterparty; return (wallet_id, counterparty_id)."""
    session_maker = _get_session_maker()
    wallet_id, counterparty_id = uuid4(), uuid4()
    async with session_maker() as s, s.begin():
        await s.execute(
            text(
                """
                INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance)
                VALUES
                  (:w, :owner_user, :wo, :wallet_kind, :cur, :opening),
                  (:c, :owner_market, :co, 'market_liability', :cur, 0)
                """
            ),
            {
                "w": wallet_id,
                "wo": uuid4(),
                "wallet_kind": KIND_USER_WALLET,
                "owner_user": OWNER_USER,
                "c": counterparty_id,
                "co": uuid4(),
                "owner_market": OWNER_MARKET,
                "cur": PLAY_USD,
                "opening": OPENING,
            },
        )
    return wallet_id, counterparty_id


async def _counts_for_accounts(wallet_id: UUID, counterparty_id: UUID) -> tuple[int, int]:
    """(transfer_count, entry_count) touching either test account — harness count_rows."""
    session_maker = _get_session_maker()
    async with session_maker() as s:
        entries = (
            await s.execute(
                text("SELECT count(*) FROM entries WHERE account_id IN (:w, :c)"),
                {"w": wallet_id, "c": counterparty_id},
            )
        ).scalar_one()
        transfers = (
            await s.execute(
                text(
                    "SELECT count(DISTINCT transfer_id) FROM entries "
                    "WHERE account_id IN (:w, :c)"
                ),
                {"w": wallet_id, "c": counterparty_id},
            )
        ).scalar_one()
    return int(transfers), int(entries)


async def _balance(account_id: UUID) -> Decimal:
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return (
            await s.execute(text("SELECT balance FROM accounts WHERE id = :id"), {"id": account_id})
        ).scalar_one()


async def test_fault_mid_transaction_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a fault after the writes but before commit; assert NOTHING persisted."""
    wallet_id, counterparty_id = await _seed_two_accounts()

    # Baseline: clean ledger for these accounts, opening balances intact.
    transfers_before, entries_before = await _counts_for_accounts(wallet_id, counterparty_id)
    assert (transfers_before, entries_before) == (0, 0)
    assert await _balance(wallet_id) == OPENING
    assert await _balance(counterparty_id) == Decimal("0")

    # Wrap the REAL _post_transfer: do all the genuine work (insert transfer + 2
    # entries + both balance updates), then raise inside transfer()'s begin() block.
    # Class access on a @staticmethod yields the plain underlying function already.
    real_post_transfer = WalletService._post_transfer

    async def faulting_post_transfer(session, **kwargs):
        await real_post_transfer(session, **kwargs)  # the writes really happen...
        raise FaultInjected  # ...then we blow up before the begin() block commits

    monkeypatch.setattr(
        WalletService,
        "_post_transfer",
        staticmethod(faulting_post_transfer),
    )

    session_maker = _get_session_maker()
    with pytest.raises(FaultInjected):
        async with session_maker() as s:
            await WalletService.transfer(
                s,
                kind=TRANSFER_KIND,
                debit_account_id=wallet_id,
                credit_account_id=counterparty_id,
                amount=MOVE_AMOUNT,
            )

    # The whole unit of work rolled back: no transfer, no entries, balances intact.
    transfers_after, entries_after = await _counts_for_accounts(wallet_id, counterparty_id)
    assert transfers_after == 0, f"transfer leaked despite fault: {transfers_after}"
    assert entries_after == 0, f"entries leaked despite fault: {entries_after}"
    assert await _balance(wallet_id) == OPENING, "debit cache changed despite rollback"
    assert await _balance(counterparty_id) == Decimal("0"), "credit cache changed despite rollback"
