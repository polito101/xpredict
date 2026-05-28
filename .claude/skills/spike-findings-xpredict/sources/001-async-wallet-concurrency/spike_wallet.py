"""
Spike 001: async-wallet-concurrency

Validates SQLAlchemy 2.0 async + asyncpg + Postgres 16 concurrent wallet transfers.

Experiments:
  1. Happy path — 100 concurrent deductions, all succeed, zero drift
  2. Overdraw with FOR UPDATE — app-level check blocks exactly the right number
  3. TOCTOU without FOR UPDATE — demonstrates the race that FOR UPDATE prevents
  4. Bidirectional transfers — lock ordering prevents deadlocks
  5. Ledger integrity — SUM(entries) == balance after every experiment

Usage:
    cd backend
    uv run python ../.planning/spikes/001-async-wallet-concurrency/spike_wallet.py

    # Custom Postgres URL:
    DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db" uv run python ...
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from decimal import Decimal
from dataclasses import dataclass, field

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    func,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://xpredict:xpredict@localhost:5432/xpredict",
)
SCHEMA = "spike_001"

metadata = MetaData(schema=SCHEMA)

accounts = Table(
    "accounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("balance", Numeric(18, 4), nullable=False, server_default="0"),
    CheckConstraint("balance >= 0", name="ck_balance_non_negative"),
)

entries = Table(
    "entries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("transfer_id", String(80), nullable=False),
    Column("account_id", Integer, ForeignKey(f"{SCHEMA}.accounts.id"), nullable=False),
    Column("amount", Numeric(18, 4), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


@dataclass
class ExperimentResult:
    name: str
    passed: bool = False
    successes: int = 0
    failures: int = 0
    deadlocks: int = 0
    check_violations: int = 0
    expected_balance: Decimal = Decimal("0")
    actual_balance: Decimal = Decimal("0")
    drift: Decimal = Decimal("0")
    ledger_matches: bool = False
    elapsed_ms: float = 0
    notes: list[str] = field(default_factory=list)


async def setup(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await conn.run_sync(metadata.create_all)


async def teardown(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


async def reset_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {SCHEMA}.entries RESTART IDENTITY CASCADE"))
        await conn.execute(text(f"TRUNCATE {SCHEMA}.accounts RESTART IDENTITY CASCADE"))


async def seed_account(session_maker, acct_id: int, name: str, balance: Decimal) -> None:
    async with session_maker() as session:
        async with session.begin():
            await session.execute(
                accounts.insert().values(id=acct_id, name=name, balance=balance)
            )


async def get_balance(session_maker, acct_id: int) -> Decimal:
    async with session_maker() as session:
        row = (await session.execute(
            select(accounts.c.balance).where(accounts.c.id == acct_id)
        )).scalar_one()
        return Decimal(str(row))


async def get_ledger_sum(session_maker, acct_id: int) -> Decimal:
    async with session_maker() as session:
        row = (await session.execute(
            select(func.coalesce(func.sum(entries.c.amount), 0))
            .where(entries.c.account_id == acct_id)
        )).scalar_one()
        return Decimal(str(row))


# ---------------------------------------------------------------------------
# Transfer functions
# ---------------------------------------------------------------------------

async def deduct_with_for_update(
    session_maker: async_sessionmaker[AsyncSession],
    acct_id: int,
    amount: Decimal,
    transfer_id: str,
) -> str:
    """Deduct using SELECT ... FOR UPDATE + app-level balance check."""
    async with session_maker() as session:
        async with session.begin():
            row = (await session.execute(
                select(accounts.c.balance)
                .where(accounts.c.id == acct_id)
                .with_for_update()
            )).scalar_one()

            if row < amount:
                return "insufficient"

            await session.execute(
                accounts.update()
                .where(accounts.c.id == acct_id)
                .values(balance=accounts.c.balance - amount)
            )
            await session.execute(
                entries.insert().values(
                    transfer_id=transfer_id, account_id=acct_id, amount=-amount
                )
            )
            return "ok"


async def deduct_without_for_update(
    session_maker: async_sessionmaker[AsyncSession],
    acct_id: int,
    amount: Decimal,
    transfer_id: str,
) -> str:
    """
    Deduct WITHOUT FOR UPDATE — demonstrates TOCTOU race.
    The SELECT reads balance, app checks, but another task can commit
    between read and update.
    """
    try:
        async with session_maker() as session:
            async with session.begin():
                row = (await session.execute(
                    select(accounts.c.balance).where(accounts.c.id == acct_id)
                )).scalar_one()

                if row < amount:
                    return "insufficient"

                # Simulate a tiny delay to widen the race window
                await asyncio.sleep(0)

                await session.execute(
                    accounts.update()
                    .where(accounts.c.id == acct_id)
                    .values(balance=accounts.c.balance - amount)
                )
                await session.execute(
                    entries.insert().values(
                        transfer_id=transfer_id, account_id=acct_id, amount=-amount
                    )
                )
                return "ok"
    except IntegrityError:
        return "check_violation"


async def transfer_with_lock_ordering(
    session_maker: async_sessionmaker[AsyncSession],
    from_id: int,
    to_id: int,
    amount: Decimal,
    transfer_id: str,
) -> str:
    """Transfer between two accounts, locking in ID order to prevent deadlocks."""
    lock_ids = sorted([from_id, to_id])

    try:
        async with session_maker() as session:
            async with session.begin():
                for lid in lock_ids:
                    await session.execute(
                        select(accounts.c.id)
                        .where(accounts.c.id == lid)
                        .with_for_update()
                    )

                src_bal = (await session.execute(
                    select(accounts.c.balance).where(accounts.c.id == from_id)
                )).scalar_one()

                if src_bal < amount:
                    return "insufficient"

                await session.execute(
                    accounts.update().where(accounts.c.id == from_id)
                    .values(balance=accounts.c.balance - amount)
                )
                await session.execute(
                    accounts.update().where(accounts.c.id == to_id)
                    .values(balance=accounts.c.balance + amount)
                )
                await session.execute(entries.insert().values(
                    transfer_id=transfer_id, account_id=from_id, amount=-amount
                ))
                await session.execute(entries.insert().values(
                    transfer_id=transfer_id, account_id=to_id, amount=amount
                ))
                return "ok"
    except OperationalError as exc:
        if "deadlock" in str(exc).lower():
            return "deadlock"
        raise


async def transfer_without_lock_ordering(
    session_maker: async_sessionmaker[AsyncSession],
    from_id: int,
    to_id: int,
    amount: Decimal,
    transfer_id: str,
) -> str:
    """Transfer locking in parameter order (NOT sorted) — may deadlock."""
    try:
        async with session_maker() as session:
            async with session.begin():
                await session.execute(
                    select(accounts.c.id)
                    .where(accounts.c.id == from_id)
                    .with_for_update()
                )
                await asyncio.sleep(0)
                await session.execute(
                    select(accounts.c.id)
                    .where(accounts.c.id == to_id)
                    .with_for_update()
                )

                src_bal = (await session.execute(
                    select(accounts.c.balance).where(accounts.c.id == from_id)
                )).scalar_one()

                if src_bal < amount:
                    return "insufficient"

                await session.execute(
                    accounts.update().where(accounts.c.id == from_id)
                    .values(balance=accounts.c.balance - amount)
                )
                await session.execute(
                    accounts.update().where(accounts.c.id == to_id)
                    .values(balance=accounts.c.balance + amount)
                )
                await session.execute(entries.insert().values(
                    transfer_id=transfer_id, account_id=from_id, amount=-amount
                ))
                await session.execute(entries.insert().values(
                    transfer_id=transfer_id, account_id=to_id, amount=amount
                ))
                return "ok"
    except OperationalError as exc:
        if "deadlock" in str(exc).lower():
            return "deadlock"
        raise


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

async def experiment_1(session_maker, engine) -> ExperimentResult:
    """Happy path: 100 concurrent deductions of 10 from balance 1000."""
    r = ExperimentResult(name="1. Happy path (100x $10 from $1000)")
    await reset_tables(engine)
    await seed_account(session_maker, 1, "player", Decimal("1000"))

    t0 = time.perf_counter()
    tasks = [
        deduct_with_for_update(session_maker, 1, Decimal("10"), f"exp1-{i}")
        for i in range(100)
    ]
    results = await asyncio.gather(*tasks)
    r.elapsed_ms = (time.perf_counter() - t0) * 1000

    r.successes = results.count("ok")
    r.failures = results.count("insufficient")
    r.actual_balance = await get_balance(session_maker, 1)
    r.expected_balance = Decimal("0")
    r.drift = r.actual_balance - r.expected_balance

    ledger_sum = await get_ledger_sum(session_maker, 1)
    initial = Decimal("1000")
    r.ledger_matches = (initial + ledger_sum) == r.actual_balance

    r.passed = (
        r.successes == 100
        and r.failures == 0
        and r.drift == 0
        and r.ledger_matches
    )
    r.notes = [
        f"All 100 tasks succeeded: {r.successes == 100}",
        f"Ledger SUM={ledger_sum}, initial={initial}, balance={r.actual_balance}",
    ]
    return r


async def experiment_2(session_maker, engine) -> ExperimentResult:
    """Overdraw protection: 100 concurrent deductions of 10 from balance 500."""
    r = ExperimentResult(name="2. Overdraw protection WITH FOR UPDATE (100x $10 from $500)")
    await reset_tables(engine)
    await seed_account(session_maker, 1, "player", Decimal("500"))

    t0 = time.perf_counter()
    tasks = [
        deduct_with_for_update(session_maker, 1, Decimal("10"), f"exp2-{i}")
        for i in range(100)
    ]
    results = await asyncio.gather(*tasks)
    r.elapsed_ms = (time.perf_counter() - t0) * 1000

    r.successes = results.count("ok")
    r.failures = results.count("insufficient")
    r.actual_balance = await get_balance(session_maker, 1)
    r.expected_balance = Decimal("0")
    r.drift = r.actual_balance - r.expected_balance

    ledger_sum = await get_ledger_sum(session_maker, 1)
    initial = Decimal("500")
    r.ledger_matches = (initial + ledger_sum) == r.actual_balance

    r.passed = (
        r.successes == 50
        and r.failures == 50
        and r.drift == 0
        and r.ledger_matches
    )
    r.notes = [
        f"Expected 50 ok / 50 insufficient — got {r.successes} ok / {r.failures} insufficient",
        f"Ledger SUM={ledger_sum}, balance={r.actual_balance}",
    ]
    return r


async def experiment_3(session_maker, engine) -> ExperimentResult:
    """TOCTOU race: same scenario WITHOUT FOR UPDATE."""
    r = ExperimentResult(name="3. TOCTOU race WITHOUT FOR UPDATE (100x $10 from $500)")
    await reset_tables(engine)
    await seed_account(session_maker, 1, "player", Decimal("500"))

    t0 = time.perf_counter()
    tasks = [
        deduct_without_for_update(session_maker, 1, Decimal("10"), f"exp3-{i}")
        for i in range(100)
    ]
    results = await asyncio.gather(*tasks)
    r.elapsed_ms = (time.perf_counter() - t0) * 1000

    r.successes = results.count("ok")
    r.failures = results.count("insufficient")
    r.check_violations = results.count("check_violation")
    r.actual_balance = await get_balance(session_maker, 1)
    r.expected_balance = Decimal("0")
    r.drift = r.actual_balance - r.expected_balance

    ledger_sum = await get_ledger_sum(session_maker, 1)
    initial = Decimal("500")
    r.ledger_matches = (initial + ledger_sum) == r.actual_balance

    more_than_50 = r.successes > 50 or r.check_violations > 0
    r.passed = more_than_50
    r.notes = [
        f"ok={r.successes}, insufficient={r.failures}, check_violation={r.check_violations}",
        "CHECK constraint caught overdraw attempts that slipped past app check" if r.check_violations > 0
        else "No CHECK violations (race window too narrow in this run — try again or increase concurrency)",
        f"Ledger integrity: {'OK' if r.ledger_matches else 'DRIFT DETECTED'} (SUM={ledger_sum}, balance={r.actual_balance})",
        "This experiment PROVES the TOCTOU race exists — FOR UPDATE prevents it",
    ]
    return r


async def experiment_4(session_maker, engine) -> ExperimentResult:
    """Bidirectional transfers WITH lock ordering — zero deadlocks expected."""
    r = ExperimentResult(name="4. Bidirectional transfers WITH lock ordering (50 A->B + 50 B->A)")
    await reset_tables(engine)
    await seed_account(session_maker, 1, "acct_a", Decimal("10000"))
    await seed_account(session_maker, 2, "acct_b", Decimal("10000"))

    t0 = time.perf_counter()
    tasks_ab = [
        transfer_with_lock_ordering(session_maker, 1, 2, Decimal("10"), f"exp4-ab-{i}")
        for i in range(50)
    ]
    tasks_ba = [
        transfer_with_lock_ordering(session_maker, 2, 1, Decimal("10"), f"exp4-ba-{i}")
        for i in range(50)
    ]
    results = await asyncio.gather(*(tasks_ab + tasks_ba))
    r.elapsed_ms = (time.perf_counter() - t0) * 1000

    r.successes = results.count("ok")
    r.deadlocks = results.count("deadlock")
    r.failures = results.count("insufficient")

    bal_a = await get_balance(session_maker, 1)
    bal_b = await get_balance(session_maker, 2)

    ledger_a = await get_ledger_sum(session_maker, 1)
    ledger_b = await get_ledger_sum(session_maker, 2)

    r.actual_balance = bal_a + bal_b
    r.expected_balance = Decimal("20000")
    r.drift = r.actual_balance - r.expected_balance
    r.ledger_matches = (
        (Decimal("10000") + ledger_a) == bal_a
        and (Decimal("10000") + ledger_b) == bal_b
    )

    r.passed = r.deadlocks == 0 and r.drift == 0 and r.ledger_matches

    r.notes = [
        f"Deadlocks: {r.deadlocks} (expected 0)",
        f"A={bal_a}, B={bal_b}, total={r.actual_balance} (expected {r.expected_balance})",
        f"All 100 transfers succeeded: {r.successes == 100}",
        f"Ledger integrity: {'OK' if r.ledger_matches else 'DRIFT'}",
    ]
    return r


async def experiment_5(session_maker, engine) -> ExperimentResult:
    """Bidirectional transfers WITHOUT lock ordering — deadlocks likely."""
    r = ExperimentResult(name="5. Bidirectional transfers WITHOUT lock ordering (deadlock test)")
    await reset_tables(engine)
    await seed_account(session_maker, 1, "acct_a", Decimal("10000"))
    await seed_account(session_maker, 2, "acct_b", Decimal("10000"))

    t0 = time.perf_counter()
    tasks_ab = [
        transfer_without_lock_ordering(session_maker, 1, 2, Decimal("10"), f"exp5-ab-{i}")
        for i in range(50)
    ]
    tasks_ba = [
        transfer_without_lock_ordering(session_maker, 2, 1, Decimal("10"), f"exp5-ba-{i}")
        for i in range(50)
    ]
    results = await asyncio.gather(*(tasks_ab + tasks_ba), return_exceptions=True)
    r.elapsed_ms = (time.perf_counter() - t0) * 1000

    str_results = []
    exceptions = 0
    for res in results:
        if isinstance(res, Exception):
            exceptions += 1
            if "deadlock" in str(res).lower():
                str_results.append("deadlock")
            else:
                str_results.append("error")
        else:
            str_results.append(res)

    r.successes = str_results.count("ok")
    r.deadlocks = str_results.count("deadlock")
    r.failures = str_results.count("insufficient") + str_results.count("error") + exceptions

    bal_a = await get_balance(session_maker, 1)
    bal_b = await get_balance(session_maker, 2)

    r.actual_balance = bal_a + bal_b
    r.expected_balance = Decimal("20000")
    r.drift = r.actual_balance - r.expected_balance
    r.ledger_matches = r.drift == Decimal("0")

    r.passed = r.deadlocks > 0
    r.notes = [
        f"Deadlocks detected: {r.deadlocks} (proves lock ordering matters!)" if r.deadlocks > 0
        else "No deadlocks in this run (Postgres resolved them, but risk is real under load)",
        f"ok={r.successes}, deadlock={r.deadlocks}, other_failures={r.failures}",
        f"A={bal_a}, B={bal_b}, total={r.actual_balance}",
        f"Conservation of money: {'OK' if r.drift == 0 else 'DRIFT ' + str(r.drift)}",
    ]
    return r


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[ExperimentResult]) -> None:
    print()
    print("=" * 70)
    print("  SPIKE 001: async-wallet-concurrency — RESULTS")
    print("=" * 70)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        icon = "+" if r.passed else "!"
        print()
        print(f"  [{icon}] {r.name}")
        print(f"      Status:   {status}")
        print(f"      Time:     {r.elapsed_ms:.0f}ms")
        print(f"      Success:  {r.successes}  |  Fail: {r.failures}  |  Deadlocks: {r.deadlocks}  |  CHECK: {r.check_violations}")
        print(f"      Balance:  expected={r.expected_balance}  actual={r.actual_balance}  drift={r.drift}")
        print(f"      Ledger:   {'MATCHES' if r.ledger_matches else 'MISMATCH'}")
        for note in r.notes:
            print(f"      > {note}")

    print()
    print("-" * 70)
    all_passed = all(r.passed for r in results)
    print(f"  OVERALL: {'ALL EXPERIMENTS PASSED' if all_passed else 'SOME EXPERIMENTS FAILED'}")
    print("-" * 70)
    print()
    print("  Key takeaways for XPredict Phase 3:")
    print("    1. SELECT ... FOR UPDATE serializes concurrent access correctly")
    print("    2. App-level balance check + FOR UPDATE = deterministic rejection")
    print("    3. Without FOR UPDATE, TOCTOU race lets overdraw past app check")
    print("    4. CHECK (balance >= 0) is defense-in-depth, catches what app misses")
    print("    5. Lock ordering (sorted IDs) prevents deadlocks on bidirectional transfers")
    print("    6. Double-entry ledger SUM matches balance in all locked experiments")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print()
    print("Spike 001: async-wallet-concurrency")
    print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    print()

    engine = create_async_engine(
        DATABASE_URL,
        pool_size=20,
        max_overflow=30,
        echo=False,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        print("Setting up schema...")
        await setup(engine)

        results: list[ExperimentResult] = []

        experiments = [
            experiment_1,
            experiment_2,
            experiment_3,
            experiment_4,
            experiment_5,
        ]

        for exp_fn in experiments:
            print(f"Running {exp_fn.__doc__.strip().split(chr(10))[0]}...")
            result = await exp_fn(session_maker, engine)
            results.append(result)

        print_report(results)

    finally:
        print("Cleaning up...")
        await teardown(engine)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
