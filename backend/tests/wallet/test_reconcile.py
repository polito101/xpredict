"""SC#7 / PLT-09 — nightly wallet reconciliation: clean -> INFO; drift -> CRITICAL + Sentry.

Against testcontainers Postgres 16 (parent ``engine`` fixture runs ``alembic
upgrade head``, so the seeded house accounts exist). We exercise
``app.wallet.reconcile._reconcile_async`` DIRECTLY with the session-scoped test
session: the task body uses ``asyncio.run`` (Celery 5.5 has no native async), so
calling the sync ``reconcile_wallets()`` here would try to nest event loops and
would also open a FRESH session that cannot see the test's uncommitted,
rolled-back rows. Passing ``async_session`` lets the reconciliation read the
seeded ledger inside the same transaction (the path the plan prescribes).

Isolation discipline: each test seeds inside a SAVEPOINT
(``async_session.begin_nested()``) that is **explicitly rolled back** in a
``finally`` (a ``begin_nested`` context manager RELEASES — i.e. *persists* — the
savepoint on clean exit, so the implicit-CM form is wrong here; we need the
writes discarded). This keeps every test order-independent w.r.t. the
session-scoped fixture.

Robustness to cross-file leakage: other wallet test files seed a ``funded_wallet``
(balance, no entries) that is flushed but not savepoint-rolled-back, so by the
time this file runs there may be pre-existing drifting accounts in the shared
session transaction. The clean/summary assertions are therefore made
**relative to a pre-seed baseline** (a clean seed must not INCREASE the drift
count) rather than asserting a global ``drift_count == 0``; the drift case
asserts on the SPECIFIC seeded account in the CRITICAL log + Sentry call.

The seeded ``house_promo`` (balance 1e9, no entries) is *intentionally* excluded
from reconciliation (``_RECONCILE_EXCLUDED_ACCOUNT_IDS``) — see reconcile.py.

Covers SC#7:
  - test_reconcile_clean_logs_info: balance == SUM(entries) -> INFO, no Sentry, no new drift.
  - test_reconcile_injected_drift_logs_critical: mutated balance -> CRITICAL + Sentry.
  - test_reconcile_returns_summary: returns {accounts_checked, drift_count}; a clean
    seed adds checked accounts without adding drift.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

import app.wallet.reconcile as reconcile
from app.wallet.constants import (
    DIRECTION_CREDIT,
    DIRECTION_DEBIT,
    HOUSE_PROMO_ACCOUNT_ID,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
    TRANSFER_OPENING,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# A clean opening amount for the seeded wallet (Decimal end-to-end, PITFALLS #4).
_OPENING = Decimal("250.0000")


async def _book_clean_wallet(session: AsyncSession, amount: Decimal) -> UUID:
    """Seed a user_wallet whose ``balance`` is backed by a real opening transfer.

    Books a double-entry opening transfer: CREDIT ``amount`` to the new wallet,
    DEBIT ``amount`` from ``house_promo`` (the funded source). The wallet's
    ``SUM(credit) - SUM(debit)`` therefore equals its ``balance`` -> zero drift.
    Returns the wallet account id.
    """
    wallet_id = uuid4()
    transfer_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance)
            VALUES (:id, :owner_type, :owner_id, :kind, :currency, :balance)
            """
        ),
        {
            "id": wallet_id,
            "owner_type": OWNER_USER,
            "owner_id": uuid4(),
            "kind": KIND_USER_WALLET,
            "currency": PLAY_USD,
            "balance": amount,
        },
    )
    await session.execute(
        text("INSERT INTO transfers (id, kind) VALUES (:id, :kind)"),
        {"id": transfer_id, "kind": TRANSFER_OPENING},
    )
    # Two legs that net to zero: credit the wallet, debit house_promo.
    await session.execute(
        text(
            """
            INSERT INTO entries (id, transfer_id, account_id, direction, amount) VALUES
              (:e1, :tid, :wallet, :credit, :amt),
              (:e2, :tid, :house,  :debit,  :amt)
            """
        ),
        {
            "e1": uuid4(),
            "e2": uuid4(),
            "tid": transfer_id,
            "wallet": wallet_id,
            "house": HOUSE_PROMO_ACCOUNT_ID,
            "credit": DIRECTION_CREDIT,
            "debit": DIRECTION_DEBIT,
            "amt": amount,
        },
    )
    await session.flush()
    return wallet_id


# ---------------------------------------------------------------------------
# SC#7 clean path — a properly-booked wallet adds no drift, logs INFO, no Sentry.
# ---------------------------------------------------------------------------


async def test_reconcile_clean_logs_info(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wallet whose balance == SUM(entries) reconciles clean: INFO, no Sentry.

    Asserted relative to a pre-seed baseline so any drift leaked by other test
    files does not make this a false negative — a *clean* seed must leave the
    drift count unchanged while increasing the checked-account count.
    """
    captured_msgs: list[str] = []
    monkeypatch.setattr(
        reconcile.sentry_sdk,
        "capture_message",
        lambda *a, **k: captured_msgs.append(a[0] if a else ""),
    )

    savepoint = await async_session.begin_nested()
    try:
        baseline = await reconcile._reconcile_async(async_session)

        wallet_id = await _book_clean_wallet(async_session, _OPENING)

        captured_msgs.clear()  # only care about Sentry calls from the post-seed run
        with capture_logs() as logs:
            summary = await reconcile._reconcile_async(async_session)
    finally:
        await savepoint.rollback()

    # A clean wallet adds one checked account and ZERO new drift (robust to any
    # drift leaked into the shared session by other test files).
    assert summary["accounts_checked"] == baseline["accounts_checked"] + 1
    assert summary["drift_count"] == baseline["drift_count"]
    # MY clean wallet is never flagged: no CRITICAL line, no Sentry alert for it.
    assert not any(
        log["event"] == "wallet_ledger_drift" and log["account_id"] == str(wallet_id)
        for log in logs
    )
    assert not any(str(wallet_id) in msg for msg in captured_msgs)
    # When the whole ledger is clean, reconcile emits a single INFO reconcile_clean
    # line and ZERO Sentry alerts (the literal SC#7 clean path — only assertable
    # when no drift was leaked into this session).
    if summary["drift_count"] == 0:
        clean = [log for log in logs if log["event"] == "reconcile_clean"]
        assert len(clean) == 1
        assert clean[0]["log_level"] == "info"
        assert clean[0]["accounts_checked"] == summary["accounts_checked"]
        assert captured_msgs == []
        assert not any(log["event"] == "wallet_ledger_drift" for log in logs)


# ---------------------------------------------------------------------------
# SC#7 alert path / PLT-09 — injected drift logs CRITICAL and fires Sentry.
# ---------------------------------------------------------------------------


async def test_reconcile_injected_drift_logs_critical(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutating accounts.balance (mutable cache) diverges it from the immutable
    ledger -> CRITICAL wallet_ledger_drift + a Sentry capture_message.

    The ledger entries stay immutable (WAL-06), so a raw balance bump is the
    realistic way drift would appear in production — proving entries are the
    source of truth and the cache is what gets reconciled against them.
    """
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        reconcile.sentry_sdk,
        "capture_message",
        lambda message, **kwargs: captured.append({"message": message, **kwargs}),
    )

    savepoint = await async_session.begin_nested()
    try:
        wallet_id = await _book_clean_wallet(async_session, _OPENING)
        # Inject drift on the MUTABLE cache (entries remain immutable).
        await async_session.execute(
            text("UPDATE accounts SET balance = balance + 1 WHERE id = :id"),
            {"id": wallet_id},
        )
        await async_session.flush()

        with capture_logs() as logs:
            summary = await reconcile._reconcile_async(async_session)
    finally:
        await savepoint.rollback()

    assert summary["drift_count"] >= 1
    # A CRITICAL wallet_ledger_drift line naming the drifted wallet.
    drift_logs = [log for log in logs if log["event"] == "wallet_ledger_drift"]
    assert len(drift_logs) >= 1
    mine = [log for log in drift_logs if log["account_id"] == str(wallet_id)]
    assert len(mine) == 1
    assert mine[0]["log_level"] == "critical"
    assert mine[0]["drift"] == "1.0000"
    assert mine[0]["balance"] == "251.0000"
    assert mine[0]["ledger_sum"] == "250.0000"
    # NO reconcile_clean line when drift is present.
    assert not any(log["event"] == "reconcile_clean" for log in logs)
    # Sentry alert fired exactly once for my account, error level.
    mine_sentry = [c for c in captured if str(wallet_id) in str(c["message"])]
    assert len(mine_sentry) == 1
    assert mine_sentry[0].get("level") == "error"


# ---------------------------------------------------------------------------
# Summary shape — returns {accounts_checked, drift_count} coherent with seed.
# ---------------------------------------------------------------------------


async def test_reconcile_returns_summary(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The task returns {accounts_checked, drift_count}; two clean wallets add
    two checked accounts and no drift (relative to the pre-seed baseline)."""
    monkeypatch.setattr(reconcile.sentry_sdk, "capture_message", lambda *a, **k: None)

    savepoint = await async_session.begin_nested()
    try:
        baseline = await reconcile._reconcile_async(async_session)

        await _book_clean_wallet(async_session, _OPENING)
        await _book_clean_wallet(async_session, Decimal("10.0000"))

        summary = await reconcile._reconcile_async(async_session)
    finally:
        await savepoint.rollback()

    assert set(summary.keys()) == {"accounts_checked", "drift_count"}
    # Two clean wallets -> +2 checked accounts, +0 drift vs baseline.
    assert summary["accounts_checked"] == baseline["accounts_checked"] + 2
    assert summary["drift_count"] == baseline["drift_count"]
