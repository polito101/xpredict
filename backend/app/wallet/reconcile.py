"""Nightly wallet reconciliation — the ledger-vs-cache drift detector (SC#7 / PLT-09).

``accounts.balance`` is a *denormalized cache*; the truth is
``SUM(credit) - SUM(debit)`` over ``entries`` (WAL-06). This module ships the
safety net that proves the double-entry invariant holds over time and alerts
loudly if the cache ever silently diverges (PITFALLS #4 invariant-check job).

Design (RESEARCH Pattern 6 + Pitfall 5):
  - Celery 5.5 has **no native async**, so the task body is SYNC and wraps the
    async DB work in ``asyncio.run(...)`` — it does NOT share the FastAPI event
    loop. Writing ``async def`` here would make Celery unable to run it.
  - The task is registered on ``celery_app`` under the importable name
    ``app.wallet.reconcile.reconcile_wallets`` and scheduled via RedBeat
    (``reconcile-wallets-nightly``, nightly 03:00 UTC) — see ``app/celery_app.py``.
    The worker imports this module (``celery_app.autodiscover_tasks(["app.wallet"])``)
    so the task registers; an unregistered task would hide drift forever (T-03-22).

Clean (zero drift) → a single INFO line (``reconcile_clean``).
Any drift → a CRITICAL ``wallet_ledger_drift`` line per drifting account AND a
Sentry ``capture_message`` so an operator alert fires (T-03-21).

All money math is ``Decimal`` — never ``float`` (NUMERIC(18,4) / WAL-05).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import sentry_sdk
import structlog
from sqlalchemy import case, func, select

from app.celery_app import celery_app
from app.db.session import _get_session_maker
from app.wallet.constants import DIRECTION_CREDIT, HOUSE_PROMO_ACCOUNT_ID
from app.wallet.models import Account, Entry

# Accounts whose balance is an intentional, non-ledger-backed seed and so MUST
# be excluded from the drift check (otherwise the detector cries wolf nightly).
#
# ``house_promo`` (migration 0003) is seeded with a 1,000,000,000.0000 opening
# balance and NO offsetting entries — it is the recharge SOURCE, funded so admin
# recharges never hit the ``balance >= 0`` floor (03-01 decision). Its balance is
# therefore *deliberately* != SUM(entries); reconciling it would emit a CRITICAL
# + Sentry alert every single night and bury real drift under false positives
# (alert fatigue defeats PLT-09). Every OTHER account — user wallets AND
# house_revenue — is fully ledger-backed and IS reconciled.
_RECONCILE_EXCLUDED_ACCOUNT_IDS: frozenset[UUID] = frozenset({HOUSE_PROMO_ACCOUNT_ID})

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def _reconcile_async(session: AsyncSession | None = None) -> dict[str, int]:
    """Compute ``SUM(credit) - SUM(debit)`` per account and compare to ``balance``.

    For each account, ``ledger_sum`` is the signed sum over its ``entries``
    (credit positive, debit negative); ``drift = balance - ledger_sum``. Accounts
    with a non-zero drift are logged at CRITICAL and reported to Sentry; a fully
    clean ledger logs a single INFO line. The seeded ``house_promo`` singleton is
    excluded (``_RECONCILE_EXCLUDED_ACCOUNT_IDS``) — its opening balance is a
    deliberate non-ledger-backed seed.

    ``session`` is optional so tests can inject the testcontainer-backed
    session (whose seeded rows live in an uncommitted, rolled-back transaction
    that a fresh ``_get_session_maker()`` session would not see). The Celery
    task passes nothing → a fresh ``AsyncSession`` is opened and closed here so
    the reconciliation never piggybacks on the FastAPI event loop.

    Returns ``{"accounts_checked": N, "drift_count": M}``.
    """
    if session is not None:
        return await _reconcile_with_session(session)

    session_maker = _get_session_maker()
    async with session_maker() as owned_session:
        return await _reconcile_with_session(owned_session)


async def _reconcile_with_session(session: AsyncSession) -> dict[str, int]:
    """Run the reconciliation query + drift handling against ``session``."""
    # SUM(CASE WHEN direction='credit' THEN amount ELSE -amount END) per account
    # (the validated harness ``_measure`` aggregate shape). LEFT OUTER JOIN so an
    # account with zero entries still appears with a ledger_sum of 0.
    ledger_sum = func.coalesce(
        func.sum(
            case(
                (Entry.direction == DIRECTION_CREDIT, Entry.amount),
                else_=-Entry.amount,
            )
        ),
        0,
    )
    stmt = (
        select(Account.id, Account.balance, ledger_sum.label("ledger_sum"))
        .outerjoin(Entry, Entry.account_id == Account.id)
        .where(Account.id.notin_(_RECONCILE_EXCLUDED_ACCOUNT_IDS))
        .group_by(Account.id)
    )
    rows: Sequence[Any] = (await session.execute(stmt)).all()

    drifts: list[dict[str, Any]] = []
    for account_id, balance, summed in rows:
        # Decimal end-to-end: balance is NUMERIC, the SUM is NUMERIC/int.
        balance_dec = Decimal(balance)
        ledger_dec = Decimal(summed)
        drift = balance_dec - ledger_dec
        if drift != 0:
            drifts.append(
                {
                    "account_id": account_id,
                    "balance": balance_dec,
                    "ledger_sum": ledger_dec,
                    "drift": drift,
                }
            )

    accounts_checked = len(rows)

    if not drifts:
        logger.info("reconcile_clean", accounts_checked=accounts_checked)
        return {"accounts_checked": accounts_checked, "drift_count": 0}

    for d in drifts:
        logger.critical(
            "wallet_ledger_drift",
            account_id=str(d["account_id"]),
            balance=str(d["balance"]),
            ledger_sum=str(d["ledger_sum"]),
            drift=str(d["drift"]),
        )
        sentry_sdk.capture_message(
            f"wallet ledger drift on {d['account_id']}: "
            f"balance={d['balance']} ledger_sum={d['ledger_sum']} drift={d['drift']}",
            level="error",
        )

    return {"accounts_checked": accounts_checked, "drift_count": len(drifts)}


@celery_app.task(name="app.wallet.reconcile.reconcile_wallets")  # type: ignore[untyped-decorator]
def reconcile_wallets() -> dict[str, int]:
    """Nightly Celery task — reconcile every account's cached balance vs its ledger.

    SYNC body wrapping ``asyncio.run(_reconcile_async())`` (Celery 5.5 has no
    native async — RESEARCH Pattern 6 / STACK §1.4). Returns the reconciliation
    summary ``{"accounts_checked": N, "drift_count": M}`` for observability /
    flower. Scheduled via RedBeat as ``reconcile-wallets-nightly`` at 03:00 UTC.
    """
    return asyncio.run(_reconcile_async())
