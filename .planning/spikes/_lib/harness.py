"""Shared spike harness for the Phase 3 wallet/ledger concurrency & atomicity spikes.

Validates Phase 3 ROADMAP success criteria (SC#1/#2/#3) against a *real* Postgres 16
(via testcontainers) using the *exact* Phase 3 stack: SQLAlchemy 2.0 async + asyncpg.

Why a real Postgres and not sqlite: sqlite serializes all writers and has no MVCC,
`SELECT ... FOR UPDATE`, `SERIALIZABLE` aborts, or row-level lock waits — so it cannot
reproduce the race this spike exists to study.

The schema is the LOCKED design from `.planning/research/STACK.md` §3.2
(accounts / transfers / entries, NUMERIC(18,4), version column, idempotency_key UNIQUE,
append-only entries). Money is `Decimal` end-to-end (PITFALLS #4).

Run scripts import from here; see `.planning/spikes/00*/run.py`.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# --------------------------------------------------------------------------- #
# Schema — verbatim shape from STACK.md §3.2 (UUID PKs; ARCHITECTURE.md BIGINT
# model is SUPERSEDED). The balance CHECK is toggled per scenario so spike 001
# can show raw corruption with the safety net OFF.
# --------------------------------------------------------------------------- #

SCHEMA_DDL = """
CREATE TABLE accounts (
    id          UUID PRIMARY KEY,
    owner_type  TEXT NOT NULL,
    owner_id    UUID,
    kind        TEXT NOT NULL,
    currency    TEXT NOT NULL DEFAULT 'PLAY_USD',
    balance     NUMERIC(18,4) NOT NULL DEFAULT 0,
    version     INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE transfers (
    id              UUID PRIMARY KEY,
    kind            TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE entries (
    id          UUID PRIMARY KEY,
    transfer_id UUID NOT NULL REFERENCES transfers(id),
    account_id  UUID NOT NULL REFERENCES accounts(id),
    direction   TEXT NOT NULL CHECK (direction IN ('debit','credit')),
    amount      NUMERIC(18,4) NOT NULL CHECK (amount > 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX entries_account_idx ON entries(account_id);
"""

BALANCE_CHECK_DDL = (
    "ALTER TABLE accounts ADD CONSTRAINT balance_non_negative CHECK (balance >= 0)"
)

# Postgres SQLSTATE codes we branch on.
SQLSTATE_UNIQUE_VIOLATION = "23505"
SQLSTATE_CHECK_VIOLATION = "23514"
SQLSTATE_SERIALIZATION_FAILURE = "40001"
SQLSTATE_DEADLOCK_DETECTED = "40P01"

GENESIS_FUNDING = Decimal("1000000000000.0000")  # system source; never goes negative


def _sqlstate(err: DBAPIError) -> str | None:
    return getattr(err.orig, "sqlstate", None)


class OptimisticConflict(Exception):
    """Raised when an optimistic version CAS update affects 0 rows."""


# --------------------------------------------------------------------------- #
# Ledger world — three accounts: a contended user_wallet, a market_liability
# counterparty, and a genesis system account that funds the opening balance.
# --------------------------------------------------------------------------- #


@dataclass
class Ledger:
    engine: AsyncEngine
    session: async_sessionmaker[AsyncSession]
    wallet_id: UUID
    counterparty_id: UUID
    genesis_id: UUID


async def setup_schema(engine: AsyncEngine, *, balance_check: bool) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS entries"))
        await conn.execute(text("DROP TABLE IF EXISTS transfers"))
        await conn.execute(text("DROP TABLE IF EXISTS accounts"))
        for stmt in SCHEMA_DDL.strip().split(";\n"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))
        if balance_check:
            await conn.execute(text(BALANCE_CHECK_DDL))


async def seed_ledger(
    engine: AsyncEngine,
    session: async_sessionmaker[AsyncSession],
    *,
    opening_balance: Decimal,
) -> Ledger:
    """Create the 3 accounts and book an opening double-entry transfer that
    credits the wallet its starting balance (so balance == credits - debits holds
    exactly and drift is measurable)."""
    wallet_id, counterparty_id, genesis_id = uuid4(), uuid4(), uuid4()
    async with session() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO accounts (id, owner_type, kind, balance) VALUES "
                "(:g,'system','genesis',:gf),"
                "(:w,'user','user_wallet',0),"
                "(:c,'market','market_liability',0)"
            ),
            {"g": genesis_id, "gf": GENESIS_FUNDING, "w": wallet_id, "c": counterparty_id},
        )
        tid = uuid4()
        await s.execute(
            text("INSERT INTO transfers (id, kind) VALUES (:t,'opening')"), {"t": tid}
        )
        await s.execute(
            text(
                "INSERT INTO entries (id,transfer_id,account_id,direction,amount) VALUES "
                "(:e1,:t,:g,'debit',:amt),(:e2,:t,:w,'credit',:amt)"
            ),
            {"e1": uuid4(), "e2": uuid4(), "t": tid, "g": genesis_id, "w": wallet_id, "amt": opening_balance},
        )
        await s.execute(
            text("UPDATE accounts SET balance = balance - :amt WHERE id=:g"),
            {"amt": opening_balance, "g": genesis_id},
        )
        await s.execute(
            text("UPDATE accounts SET balance = balance + :amt WHERE id=:w"),
            {"amt": opening_balance, "w": wallet_id},
        )
    return Ledger(engine, session, wallet_id, counterparty_id, genesis_id)


@asynccontextmanager
async def provision(
    dsn: str,
    *,
    balance_check: bool,
    opening_balance: Decimal,
    pool: int = 64,
    isolation_level: str | None = None,
):
    """Build an async engine against an already-running Postgres, (re)create the
    schema, seed the ledger, yield a Ledger, then dispose.

    `isolation_level` (e.g. "SERIALIZABLE") is applied engine-wide — the robust,
    well-supported way to do per-strategy isolation in SQLAlchemy async.
    """
    kwargs: dict = {"pool_size": pool, "max_overflow": 0, "pool_pre_ping": False, "future": True}
    if isolation_level:
        kwargs["isolation_level"] = isolation_level
    engine = create_async_engine(dsn, **kwargs)
    session = async_sessionmaker(engine, expire_on_commit=False)
    await setup_schema(engine, balance_check=balance_check)
    ledger = await seed_ledger(engine, session, opening_balance=opening_balance)
    try:
        yield ledger
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# The single "spend `amount` from wallet -> counterparty" double-entry transfer.
# Strategy only changes HOW the wallet debit is guarded against concurrency.
# --------------------------------------------------------------------------- #


async def _spend_once(
    ledger: Ledger,
    amount: Decimal,
    *,
    strategy: str,
    read_delay: float,
    idempotency_key: str | None,
) -> str:
    s = ledger.session()
    async with s:
        async with s.begin():
            # SERIALIZABLE isolation is applied engine-wide via provision(isolation_level=...),
            # so the "serializable" strategy here just reads plainly and lets Postgres SSI
            # abort conflicting txns with 40001 (caught + retried in spend()).
            if strategy == "for_update":
                row = (
                    await s.execute(
                        text("SELECT balance, version FROM accounts WHERE id=:id FOR UPDATE"),
                        {"id": ledger.wallet_id},
                    )
                ).one()
            else:
                row = (
                    await s.execute(
                        text("SELECT balance, version FROM accounts WHERE id=:id"),
                        {"id": ledger.wallet_id},
                    )
                ).one()
            balance: Decimal = row.balance
            version: int = row.version

            # Widen the read->write window so the lost-update race is deterministic
            # for the naive strategies (no-op for guarded strategies that block/abort).
            if read_delay:
                await asyncio.sleep(read_delay)

            if balance < amount:
                return "rejected_insufficient"

            # --- the double-entry move (always 2 entries that net to zero) ---
            tid = uuid4()
            await s.execute(
                text("INSERT INTO transfers (id, kind, idempotency_key) VALUES (:t,'spend',:k)"),
                {"t": tid, "k": idempotency_key},
            )
            await s.execute(
                text(
                    "INSERT INTO entries (id,transfer_id,account_id,direction,amount) VALUES "
                    "(:e1,:t,:w,'debit',:m),(:e2,:t,:c,'credit',:m)"
                ),
                {"e1": uuid4(), "e2": uuid4(), "t": tid, "w": ledger.wallet_id, "c": ledger.counterparty_id, "m": amount},
            )

            # --- the wallet debit: the part that races ---
            # The guarded strategies (for_update / serializable / optimistic) all use
            # the SAME read->decide->write-computed pattern as the naive bug, so the
            # comparison isolates the *concurrency control*, not an incidental atomic
            # SQL decrement (which a CHECK constraint alone would already protect).
            if strategy in ("naive_lost_update", "for_update", "serializable"):
                await s.execute(
                    text("UPDATE accounts SET balance=:nb, version=version+1 WHERE id=:id"),
                    {"nb": balance - amount, "id": ledger.wallet_id},
                )
            elif strategy == "optimistic":
                res = await s.execute(
                    text(
                        "UPDATE accounts SET balance=:nb, version=version+1 "
                        "WHERE id=:id AND version=:v"
                    ),
                    {"nb": balance - amount, "id": ledger.wallet_id, "v": version},
                )
                if res.rowcount == 0:
                    raise OptimisticConflict
            elif strategy == "naive_overdraw":
                # atomic SQL decrement with NO guard: shows the DB go negative
                # (or, with the CHECK on, chaotic 23514s) — used only by spike 001.
                await s.execute(
                    text("UPDATE accounts SET balance=balance-:m, version=version+1 WHERE id=:id"),
                    {"m": amount, "id": ledger.wallet_id},
                )

            # counterparty credit (uniform across strategies)
            await s.execute(
                text("UPDATE accounts SET balance=balance+:m WHERE id=:id"),
                {"m": amount, "id": ledger.counterparty_id},
            )
            return "ok"


async def spend(
    ledger: Ledger,
    amount: Decimal,
    *,
    strategy: str,
    read_delay: float = 0.0,
    max_retries: int = 50,
    idempotency_key: str | None = None,
    attempts_sink: list[int] | None = None,
) -> str:
    """Run one transfer; retry strategies loop on conflict/abort with backoff.

    Returns an outcome tag: ok | rejected_insufficient | rejected_check |
    idempotent_dup | retry_exhausted | error:<sqlstate>. If `attempts_sink` is
    given, the number of attempts this transfer took is appended (retry metric).
    """
    attempts = 0
    outcome = "error:unset"
    while True:
        attempts += 1
        try:
            outcome = await _spend_once(
                ledger, amount, strategy=strategy, read_delay=read_delay, idempotency_key=idempotency_key
            )
            break
        except OptimisticConflict:
            if attempts > max_retries:
                outcome = "retry_exhausted"
                break
            await asyncio.sleep(_backoff(attempts))
            continue
        except DBAPIError as err:
            state = _sqlstate(err)
            if state == SQLSTATE_UNIQUE_VIOLATION:
                outcome = "idempotent_dup"
                break
            if state == SQLSTATE_CHECK_VIOLATION:
                outcome = "rejected_check"
                break
            if state in (SQLSTATE_SERIALIZATION_FAILURE, SQLSTATE_DEADLOCK_DETECTED):
                if attempts > max_retries:
                    outcome = "retry_exhausted"
                    break
                await asyncio.sleep(_backoff(attempts))
                continue
            outcome = f"error:{state}"
            break
    if attempts_sink is not None:
        attempts_sink.append(attempts)
    return outcome


def _backoff(attempt: int) -> float:
    # tiny exponential backoff with deterministic jitter to break lockstep retries
    base = min(0.001 * (2 ** attempt), 0.05)
    return base * (0.5 + (attempt % 3) / 3.0)


# --------------------------------------------------------------------------- #
# Concurrent load runner + invariant verification
# --------------------------------------------------------------------------- #


@dataclass
class LoadResult:
    label: str
    n: int
    per_amount: Decimal
    opening: Decimal
    outcomes: Counter = field(default_factory=Counter)
    wall_seconds: float = 0.0
    total_attempts: int = 0  # sum of attempts across all transfers (retry metric)
    final_balance: Decimal | None = None
    ledger_balance: Decimal | None = None  # SUM(credit)-SUM(debit) over wallet
    counterparty_balance: Decimal | None = None
    global_entry_sum: Decimal | None = None  # SUM(credit)-SUM(debit) over ALL accounts

    @property
    def drift(self) -> Decimal:
        if self.final_balance is None or self.ledger_balance is None:
            return Decimal("NaN")
        return self.final_balance - self.ledger_balance

    @property
    def expected_ok(self) -> int:
        return int(self.opening // self.per_amount)

    @property
    def correct(self) -> bool:
        """The wallet invariants Phase 3 SC#2 demands."""
        if self.final_balance is None:
            return False
        expected_balance = self.opening - self.per_amount * self.outcomes["ok"]
        return (
            self.final_balance >= 0
            and self.drift == 0
            and self.final_balance == expected_balance
            and (self.global_entry_sum == 0)
        )


async def run_load(
    ledger: Ledger,
    *,
    label: str,
    n: int,
    per_amount: Decimal,
    opening: Decimal,
    strategy: str,
    read_delay: float = 0.0,
) -> LoadResult:
    res = LoadResult(label=label, n=n, per_amount=per_amount, opening=opening)
    sink: list[int] = []
    start = time.perf_counter()
    tags = await asyncio.gather(
        *(
            spend(ledger, per_amount, strategy=strategy, read_delay=read_delay, attempts_sink=sink)
            for _ in range(n)
        )
    )
    res.wall_seconds = time.perf_counter() - start
    res.outcomes = Counter(tags)
    res.total_attempts = sum(sink)
    await _measure(ledger, res)
    return res


async def _measure(ledger: Ledger, res: LoadResult) -> None:
    async with ledger.session() as s:
        res.final_balance = (
            await s.execute(text("SELECT balance FROM accounts WHERE id=:id"), {"id": ledger.wallet_id})
        ).scalar_one()
        res.ledger_balance = (
            await s.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN direction='credit' THEN amount ELSE -amount END),0) "
                    "FROM entries WHERE account_id=:id"
                ),
                {"id": ledger.wallet_id},
            )
        ).scalar_one()
        res.counterparty_balance = (
            await s.execute(text("SELECT balance FROM accounts WHERE id=:id"), {"id": ledger.counterparty_id})
        ).scalar_one()
        res.global_entry_sum = (
            await s.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN direction='credit' THEN amount ELSE -amount END),0) FROM entries"
                )
            )
        ).scalar_one()


def print_result(res: LoadResult) -> None:
    flag = "OK  " if res.correct else "FAIL"
    print(f"  [{flag}] {res.label}")
    print(f"        outcomes      : {dict(res.outcomes)}")
    print(f"        wall          : {res.wall_seconds*1000:.0f} ms for {res.n} concurrent")
    print(f"        attempts      : {res.total_attempts} total ({res.total_attempts / res.n:.2f}x per transfer)")
    print(f"        final balance : {res.final_balance}  (expected_ok={res.expected_ok} succeeded={res.outcomes['ok']})")
    print(f"        ledger sum    : {res.ledger_balance}  -> drift={res.drift}")
    print(f"        counterparty  : {res.counterparty_balance}   global_entry_sum={res.global_entry_sum}")


# --------------------------------------------------------------------------- #
# Helpers for spike 003 (atomicity / idempotency) and 004 (deadlock ordering)
# --------------------------------------------------------------------------- #


class FaultInjected(Exception):
    """Raised on purpose mid-transaction to prove rollback (PITFALLS #10)."""


async def attempt_with_fault(ledger: Ledger, amount: Decimal) -> None:
    """Run the full double-entry move, then raise BEFORE commit. The
    `session.begin()` block must roll EVERYTHING back: no transfer, no entries,
    no balance change persist. Always raises FaultInjected."""
    s = ledger.session()
    async with s:
        async with s.begin():
            tid = uuid4()
            await s.execute(text("INSERT INTO transfers (id, kind) VALUES (:t,'spend')"), {"t": tid})
            await s.execute(
                text(
                    "INSERT INTO entries (id,transfer_id,account_id,direction,amount) VALUES "
                    "(:e1,:t,:w,'debit',:m),(:e2,:t,:c,'credit',:m)"
                ),
                {"e1": uuid4(), "e2": uuid4(), "t": tid, "w": ledger.wallet_id, "c": ledger.counterparty_id, "m": amount},
            )
            await s.execute(
                text("UPDATE accounts SET balance=balance-:m, version=version+1 WHERE id=:id"),
                {"m": amount, "id": ledger.wallet_id},
            )
            await s.execute(
                text("UPDATE accounts SET balance=balance+:m WHERE id=:id"),
                {"m": amount, "id": ledger.counterparty_id},
            )
            raise FaultInjected


async def count_rows(ledger: Ledger) -> dict[str, int]:
    async with ledger.session() as s:
        transfers = (await s.execute(text("SELECT count(*) FROM transfers"))).scalar_one()
        entries = (await s.execute(text("SELECT count(*) FROM entries"))).scalar_one()
    return {"transfers": int(transfers), "entries": int(entries)}


async def wallet_balance(ledger: Ledger) -> Decimal:
    async with ledger.session() as s:
        return (
            await s.execute(text("SELECT balance FROM accounts WHERE id=:id"), {"id": ledger.wallet_id})
        ).scalar_one()


async def fund(ledger: Ledger, account_id: UUID, amount: Decimal) -> None:
    """Top up an account's balance cache directly (test-setup convenience)."""
    async with ledger.session() as s, s.begin():
        await s.execute(
            text("UPDATE accounts SET balance=balance+:m WHERE id=:id"),
            {"m": amount, "id": account_id},
        )


async def locked_transfer(
    ledger: Ledger, a_id: UUID, b_id: UUID, amount: Decimal, *, canonical_order: bool, hold: float = 0.05
) -> str:
    """Move `amount` from a -> b, taking row locks on BOTH accounts.

    Lock order follows the (a, b) argument order UNLESS canonical_order is set,
    in which case both rows are locked in a deterministic UUID order. Two
    concurrent opposite-direction transfers with canonical_order=False deadlock
    (40P01); with canonical_order=True they serialize cleanly.
    """
    first, second = (a_id, b_id)
    if canonical_order:
        first, second = tuple(sorted((a_id, b_id), key=str))
    s = ledger.session()
    try:
        async with s:
            async with s.begin():
                await s.execute(text("SELECT 1 FROM accounts WHERE id=:id FOR UPDATE"), {"id": first})
                await asyncio.sleep(hold)  # let the opposite tx grab its first lock
                await s.execute(text("SELECT 1 FROM accounts WHERE id=:id FOR UPDATE"), {"id": second})
                tid = uuid4()
                await s.execute(text("INSERT INTO transfers (id, kind) VALUES (:t,'move')"), {"t": tid})
                await s.execute(
                    text(
                        "INSERT INTO entries (id,transfer_id,account_id,direction,amount) VALUES "
                        "(:e1,:t,:a,'debit',:m),(:e2,:t,:b,'credit',:m)"
                    ),
                    {"e1": uuid4(), "e2": uuid4(), "t": tid, "a": a_id, "b": b_id, "m": amount},
                )
                await s.execute(text("UPDATE accounts SET balance=balance-:m WHERE id=:id"), {"m": amount, "id": a_id})
                await s.execute(text("UPDATE accounts SET balance=balance+:m WHERE id=:id"), {"m": amount, "id": b_id})
                return "ok"
    except DBAPIError as err:
        state = _sqlstate(err)
        if state == SQLSTATE_DEADLOCK_DETECTED:
            return "deadlock"
        return f"error:{state}"
