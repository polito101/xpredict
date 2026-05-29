"""SC#2 SIGNATURE GATE — 50 concurrent overdraft transfers, drift 0, CHECK rejects.

This is the phase's headline observable (CONTEXT "the signature test is the phase
gate"). It reproduces the validated spike harness ``run_load`` / ``LoadResult.correct``
invariant — but bound to the PRODUCTION ``WalletService.transfer`` code, not the
harness's raw ``text()`` SQL.

The race this defeats (Spike 001 demonstrated the bug; Spike 002 the fix): N
concurrent debits of one hot wallet row, where the opening balance funds only
``N // 2`` of them. Without ``SELECT ... FOR UPDATE`` a read->decide->write window
lets two txns both observe "enough balance" and both debit — creating money and
driving drift (cache != SUM(entries)) or the balance negative. WITH FOR UPDATE the
debits serialize on the row lock, exactly ``opening // per_amount`` succeed, the
rest are rejected with :class:`InsufficientBalance`, and:

    final_balance >= 0  AND  drift == 0  AND
    final_balance == opening - per_amount * succeeded  AND  global_entry_sum == 0

which is ``harness.LoadResult.correct`` verbatim (T-03-06, WAL-07).

Concurrency note: each transfer opens its OWN ``AsyncSession`` from the production
``_get_session_maker()`` and COMMITS — true concurrency cannot share the parent
``async_session`` rollback fixture (one connection, one transaction). The seeded
ledger rows are therefore real committed rows; they are isolated from every other
test by a unique ``owner_id`` per account and all assertions are scoped to those
account ids (``transfers``/``entries`` are immutable and cannot be deleted, so we
never attempt teardown — ``global_entry_sum`` is invariably 0 because every
transfer nets to zero regardless of accumulated rows).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.db.session import _get_session_maker
from app.wallet.constants import (
    DIRECTION_CREDIT,
    KIND_USER_WALLET,
    OWNER_MARKET,
    OWNER_SYSTEM,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.exceptions import InsufficientBalance
from app.wallet.service import WalletService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine):
    """Depend on the session-scoped ``engine`` fixture so the testcontainer is up.

    These tests open their OWN sessions via ``_get_session_maker()`` (true
    concurrency cannot share the rollback ``async_session``), so they do not
    request ``async_session`` directly. They DO need the ``engine`` fixture's
    side effects: start Postgres, run ``alembic upgrade head``, rewrite
    ``DATABASE_URL`` to the container, and clear the ``_get_engine`` /
    ``_get_session_maker`` caches — otherwise the production engine factory
    connects to the (absent) default ``localhost:5432``.
    """
    return engine


# The load shape: 50 concurrent transfers, opening funds exactly N // 2 of them.
N_CONCURRENT = 50
PER_AMOUNT = Decimal("10.0000")
OPENING = PER_AMOUNT * (N_CONCURRENT // 2)  # funds exactly 25 successes
TRANSFER_KIND = "test_spend"


@dataclass
class _Outcome:
    """Mirror of ``harness.LoadResult`` — the measured invariants."""

    final_balance: Decimal
    ledger_balance: Decimal  # SUM(credit) - SUM(debit) over the wallet
    global_entry_sum: Decimal  # SUM(credit) - SUM(debit) over the 2 test accounts
    succeeded: int
    rejected: int

    @property
    def drift(self) -> Decimal:
        return self.final_balance - self.ledger_balance

    @property
    def expected_balance(self) -> Decimal:
        return OPENING - PER_AMOUNT * self.succeeded

    @property
    def correct(self) -> bool:
        """``LoadResult.correct`` — exactly the SC#2 invariant."""
        return (
            self.final_balance >= 0
            and self.drift == Decimal("0")
            and self.final_balance == self.expected_balance
            and self.global_entry_sum == Decimal("0")
        )


async def _seed_two_accounts() -> tuple[UUID, UUID]:
    """Commit a funded ``user_wallet`` + a ``market_liability`` counterparty.

    The wallet's opening balance is established by a proper OPENING double-entry
    transfer (a genesis funding account debited, the wallet credited) — NOT a bare
    cache write — exactly like ``harness.seed_ledger``. This is what makes
    ``drift`` measurable: ``SUM(entries for wallet)`` then includes the opening
    ``+OPENING`` credit, so the cache and the ledger sum agree at the start and any
    later divergence is real drift, not a seeding artifact.

    Distinct ``owner_id`` per run so concurrent committed rows never collide with
    any other test. Returns ``(wallet_id, counterparty_id)``.
    """
    session_maker = _get_session_maker()
    wallet_id, counterparty_id, genesis_id = uuid4(), uuid4(), uuid4()
    opening_transfer_id = uuid4()
    async with session_maker() as s, s.begin():
        await s.execute(
            text(
                """
                INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance)
                VALUES
                  (:g, :owner_system, :go, 'genesis', :cur, :opening),
                  (:w, :owner_user, :wo, :wallet_kind, :cur, 0),
                  (:c, :owner_market, :co, 'market_liability', :cur, 0)
                """
            ),
            {
                "g": genesis_id,
                "go": uuid4(),
                "owner_system": OWNER_SYSTEM,
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
        # Opening double-entry: genesis -> wallet, so the wallet's entry-sum starts
        # at +OPENING and drift == 0 at t0 (mirror harness.seed_ledger).
        await s.execute(
            text("INSERT INTO transfers (id, kind) VALUES (:t, 'opening')"),
            {"t": opening_transfer_id},
        )
        await s.execute(
            text(
                """
                INSERT INTO entries (id, transfer_id, account_id, direction, amount)
                VALUES (:e1, :t, :g, 'debit', :amt), (:e2, :t, :w, 'credit', :amt)
                """
            ),
            {
                "e1": uuid4(),
                "e2": uuid4(),
                "t": opening_transfer_id,
                "g": genesis_id,
                "w": wallet_id,
                "amt": OPENING,
            },
        )
        await s.execute(
            text("UPDATE accounts SET balance = balance - :amt WHERE id = :g"),
            {"amt": OPENING, "g": genesis_id},
        )
        await s.execute(
            text("UPDATE accounts SET balance = balance + :amt WHERE id = :w"),
            {"amt": OPENING, "w": wallet_id},
        )
    return wallet_id, counterparty_id


async def _one_transfer(wallet_id: UUID, counterparty_id: UUID) -> str:
    """Drive ONE production ``WalletService.transfer`` on its own committed session."""
    session_maker = _get_session_maker()
    async with session_maker() as s:
        try:
            await WalletService.transfer(
                s,
                kind=TRANSFER_KIND,
                debit_account_id=wallet_id,
                credit_account_id=counterparty_id,
                amount=PER_AMOUNT,
            )
            return "ok"
        except InsufficientBalance:
            return "rejected_insufficient"


async def _measure(wallet_id: UUID, tags: list[str]) -> _Outcome:
    """Port of ``harness._measure`` — read the cache + ledger sums via a fresh session."""
    session_maker = _get_session_maker()
    async with session_maker() as s:
        final_balance = (
            await s.execute(text("SELECT balance FROM accounts WHERE id = :id"), {"id": wallet_id})
        ).scalar_one()
        ledger_balance = (
            await s.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN direction = :credit THEN amount "
                    "ELSE -amount END), 0) FROM entries WHERE account_id = :id"
                ),
                {"credit": DIRECTION_CREDIT, "id": wallet_id},
            )
        ).scalar_one()
        # global_entry_sum over ALL entries (harness._measure verbatim). Every
        # transfer nets to zero, so this is a permanent global invariant (== 0)
        # regardless of rows accumulated by other tests — making it isolation-safe
        # despite the immutable, un-deletable ledger.
        global_entry_sum = (
            await s.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN direction = :credit THEN amount "
                    "ELSE -amount END), 0) FROM entries"
                ),
                {"credit": DIRECTION_CREDIT},
            )
        ).scalar_one()
    return _Outcome(
        final_balance=final_balance,
        ledger_balance=ledger_balance,
        global_entry_sum=global_entry_sum,
        succeeded=tags.count("ok"),
        rejected=tags.count("rejected_insufficient"),
    )


async def test_50_concurrent_overdraft() -> None:
    """SC#2: 50 concurrent transfers, balance exact, drift 0, overdraw rejected.

    The signature gate — proves ``WalletService.transfer`` is race-safe on
    production code (FOR UPDATE serialization), not just in the spike harness.
    """
    wallet_id, counterparty_id = await _seed_two_accounts()

    tags = await asyncio.gather(
        *(_one_transfer(wallet_id, counterparty_id) for _ in range(N_CONCURRENT))
    )

    outcome = await _measure(wallet_id, list(tags))

    # The exact harness LoadResult.correct invariant.
    assert outcome.correct, (
        f"SC#2 invariant violated: final={outcome.final_balance} "
        f"ledger={outcome.ledger_balance} drift={outcome.drift} "
        f"expected={outcome.expected_balance} "
        f"global_entry_sum={outcome.global_entry_sum} "
        f"succeeded={outcome.succeeded} rejected={outcome.rejected}"
    )
    # Exactly opening // per_amount succeed; the rest are rejected (CHECK net +
    # FOR UPDATE balance guard). Both halves must be non-trivial.
    assert outcome.succeeded == int(OPENING // PER_AMOUNT) == N_CONCURRENT // 2
    assert outcome.rejected == N_CONCURRENT - outcome.succeeded
    assert outcome.rejected > 0, "no overdraw was rejected — the guard never fired"
    assert outcome.final_balance >= 0
    assert outcome.drift == Decimal("0")
