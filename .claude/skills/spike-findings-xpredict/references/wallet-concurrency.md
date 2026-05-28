# Wallet & Concurrency

## Requirements

- Wallet transfers must be ACID-wrapped with `SELECT ... FOR UPDATE` pessimistic locking
- Balance must never go negative under any concurrency level (`CHECK (balance >= 0)`)
- All money amounts must be `Decimal` / `NUMERIC(18,4)` — never float
- Lock ordering by account ID is mandatory for cross-account transfers (96% deadlock rate without it)
- App-level balance check + FOR UPDATE together — neither alone is sufficient

## How to Build It

### 1. Schema

```python
from sqlalchemy import CheckConstraint, Column, Integer, Numeric, String, Table, MetaData

accounts = Table(
    "accounts", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("balance", Numeric(18, 4), nullable=False, server_default="0"),
    CheckConstraint("balance >= 0", name="ck_balance_non_negative"),
)

entries = Table(
    "entries", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("transfer_id", String(80), nullable=False),
    Column("account_id", Integer, ForeignKey("accounts.id"), nullable=False),
    Column("amount", Numeric(18, 4), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
```

### 2. Single-account deduction (the proven pattern)

```python
async def deduct_with_for_update(
    session_maker: async_sessionmaker[AsyncSession],
    acct_id: int,
    amount: Decimal,
    transfer_id: str,
) -> str:
    async with session_maker() as session:
        async with session.begin():
            # Step 1: Lock the row
            row = (await session.execute(
                select(accounts.c.balance)
                .where(accounts.c.id == acct_id)
                .with_for_update()
            )).scalar_one()

            # Step 2: App-level check (deterministic rejection)
            if row < amount:
                return "insufficient"

            # Step 3: Update + ledger entry
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
```

### 3. Cross-account transfer with lock ordering

```python
async def transfer_with_lock_ordering(
    session_maker, from_id: int, to_id: int, amount: Decimal, transfer_id: str
) -> str:
    lock_ids = sorted([from_id, to_id])  # CRITICAL: sort by ID

    async with session_maker() as session:
        async with session.begin():
            # Lock both in sorted order
            for lid in lock_ids:
                await session.execute(
                    select(accounts.c.id)
                    .where(accounts.c.id == lid)
                    .with_for_update()
                )

            # Check source balance
            src_bal = (await session.execute(
                select(accounts.c.balance).where(accounts.c.id == from_id)
            )).scalar_one()

            if src_bal < amount:
                return "insufficient"

            # Debit + Credit + double-entry ledger
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
```

### 4. Engine configuration

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    echo=False,
)
session_maker = async_sessionmaker(engine, expire_on_commit=False)
```

Pool size 20 + max_overflow 30 handled 100 concurrent tasks without pool exhaustion in spike testing.

## What to Avoid

1. **DO NOT use optimistic locking (version column)** for wallets — retry storms under wallet-level contention make it impractical
2. **DO NOT rely on SQL arithmetic alone** (`balance = balance - amount` without FOR UPDATE) — the app-level check becomes unreliable (TOCTOU). In spike testing, 49% of overdraw attempts bypassed the application logic without FOR UPDATE
3. **DO NOT skip lock ordering for cross-account transfers** — 96 out of 100 bidirectional transfers deadlocked without sorted lock ordering (15x slower due to deadlock detection overhead)
4. **DO NOT use SERIALIZABLE isolation as the default** — READ COMMITTED + FOR UPDATE is sufficient and faster
5. **DO NOT use `CHECK (balance >= 0)` as the primary mechanism** — it's defense-in-depth only. The app receives `IntegrityError` instead of a clean "insufficient balance" response
6. **DO NOT use floats for money** — always `Decimal` / `NUMERIC(18,4)`

## Constraints

- Requires Postgres (tested with 16) — `SELECT ... FOR UPDATE` is Postgres-specific behavior
- SQLAlchemy 2.0+ async API required (`AsyncSession.begin()` context manager)
- asyncpg driver — tested and proven
- `READ COMMITTED` isolation level is sufficient (Postgres default)
- Performance baseline: ~16ms/transfer with FOR UPDATE serialization

## Origin

Synthesized from spikes: 001
Source files available in: sources/001-async-wallet-concurrency/
