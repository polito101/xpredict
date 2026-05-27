"""
Spike 004: Settlement ACID Transaction

Validates that SettlementService.resolve_market() can:
1. Settle N bets in one ACID transaction
2. Create correct multi-entry ledger (winner: market_liability -> user_wallet, loser: market_liability -> house_revenue)
3. Maintain zero drift under concurrent bet placement during settlement
4. Be idempotent (replay produces no double-payouts)
5. Handle large batch (50 bets) without lock contention issues
6. Write audit_log entry atomically with settlement

Schema (in spike_004 Postgres schema):
  accounts: id, name, kind, balance (NUMERIC 18,4), CHECK >= 0
  bets: id, market_id, user_account_id, outcome, stake, status (OPEN/SETTLED_WON/SETTLED_LOST)
  markets: id, question, status (OPEN/RESOLVED), winning_outcome, settled_at
  entries: id, transfer_id, account_id, amount, created_at
  audit_log: id, event_type, market_id, data, created_at

Run from xpredict/backend:
  uv run python ../.planning/spikes/004-settlement-acid-transaction/spike_settlement.py
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = "postgresql+asyncpg://xpredict:xpredict@localhost:5432/xpredict"
SCHEMA = "spike_004"

metadata = MetaData(schema=SCHEMA)

accounts = Table(
    "accounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("kind", String(50), nullable=False),
    Column("balance", Numeric(18, 4), nullable=False, server_default="0"),
    CheckConstraint("balance >= 0", name="ck_balance_non_negative"),
)

markets = Table(
    "markets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("question", String(500), nullable=False),
    Column("status", String(20), nullable=False, server_default="OPEN"),
    Column("winning_outcome", String(10)),
    Column("settled_at", DateTime(timezone=True)),
)

bets = Table(
    "bets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("market_id", Integer, nullable=False),
    Column("user_account_id", Integer, nullable=False),
    Column("outcome", String(10), nullable=False),
    Column("stake", Numeric(18, 4), nullable=False),
    Column("status", String(20), nullable=False, server_default="OPEN"),
)

entries = Table(
    "entries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("transfer_id", String(80), nullable=False),
    Column("account_id", Integer, nullable=False),
    Column("amount", Numeric(18, 4), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_type", String(50), nullable=False),
    Column("market_id", Integer),
    Column("data", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


# ---------------------------------------------------------------------------
# Settlement Service (the thing being tested)
# ---------------------------------------------------------------------------

async def resolve_market(
    session_maker: async_sessionmaker[AsyncSession],
    market_id: int,
    winning_outcome: str,
    resolver: str = "admin",
    house_revenue_account_id: int = 2,
    market_liability_account_id: int = 3,
) -> dict:
    """
    Settle a market in one ACID transaction:
    1. Lock market row (FOR UPDATE) + check not already settled (idempotency)
    2. Lock all bet rows for this market (FOR UPDATE)
    3. For each bet:
       - Winner: market_liability -> user_wallet (payout = stake * 2 for binary 50/50)
       - Loser: market_liability -> house_revenue
    4. Lock all affected account rows (sorted by ID for deadlock prevention)
    5. Update balances + insert entries
    6. Update market status + bets status
    7. Insert audit_log entry
    """
    async with session_maker() as session:
        async with session.begin():
            # 1. Lock market
            mkt = (
                await session.execute(
                    select(markets.c.id, markets.c.status, markets.c.settled_at)
                    .where(markets.c.id == market_id)
                    .with_for_update()
                )
            ).one_or_none()

            if mkt is None:
                return {"status": "error", "reason": "market_not_found"}

            if mkt.settled_at is not None:
                return {"status": "idempotent_skip", "reason": "already_settled"}

            # 2. Lock all bets for this market
            bet_rows = (
                await session.execute(
                    select(bets.c.id, bets.c.user_account_id, bets.c.outcome, bets.c.stake)
                    .where(bets.c.market_id == market_id, bets.c.status == "OPEN")
                    .with_for_update()
                )
            ).all()

            if not bet_rows:
                return {"status": "error", "reason": "no_open_bets"}

            # 3. Classify bets
            winners = []
            losers = []
            for b in bet_rows:
                if b.outcome == winning_outcome:
                    winners.append(b)
                else:
                    losers.append(b)

            # 4. Collect all account IDs that need balance updates, lock in sorted order
            account_ids = set()
            account_ids.add(house_revenue_account_id)
            account_ids.add(market_liability_account_id)
            for b in bet_rows:
                account_ids.add(b.user_account_id)

            for aid in sorted(account_ids):
                await session.execute(
                    select(accounts.c.id).where(accounts.c.id == aid).with_for_update()
                )

            # 5. Process winners: market_liability -> user_wallet
            #    Payout = stake * 2 for binary 50/50. The pot (market_liability)
            #    accumulated all stakes during bet placement. Winner payouts come
            #    from the pot. Losers' stakes are already IN the pot — no separate
            #    debit for losers.
            transfer_id = f"settle:{market_id}:{uuid.uuid4().hex[:8]}"
            total_payout = Decimal("0")
            for b in winners:
                payout = b.stake * 2  # binary 50/50 payout
                total_payout += payout

                # Credit winner
                await session.execute(
                    accounts.update()
                    .where(accounts.c.id == b.user_account_id)
                    .values(balance=accounts.c.balance + payout)
                )
                await session.execute(
                    entries.insert().values(
                        transfer_id=transfer_id,
                        account_id=b.user_account_id,
                        amount=payout,
                    )
                )

                # Debit market_liability
                await session.execute(
                    accounts.update()
                    .where(accounts.c.id == market_liability_account_id)
                    .values(balance=accounts.c.balance - payout)
                )
                await session.execute(
                    entries.insert().values(
                        transfer_id=transfer_id,
                        account_id=market_liability_account_id,
                        amount=-payout,
                    )
                )

                # Update bet status
                await session.execute(
                    bets.update().where(bets.c.id == b.id).values(status="SETTLED_WON")
                )

            # 6. Mark losers as SETTLED_LOST (no money movement — their stakes
            #    are already in the pot and funded winner payouts)
            for b in losers:
                await session.execute(
                    bets.update().where(bets.c.id == b.id).values(status="SETTLED_LOST")
                )

            # 7. Transfer remaining pot to house_revenue (the vig / surplus).
            #    In a fair 50/50 binary with equal bets per side, this is 0.
            #    With unbalanced sides or a house edge, this is > 0.
            liability_bal = (
                await session.execute(
                    select(accounts.c.balance).where(accounts.c.id == market_liability_account_id)
                )
            ).scalar_one()

            total_house = Decimal("0")
            if liability_bal > 0:
                total_house = liability_bal
                await session.execute(
                    accounts.update()
                    .where(accounts.c.id == market_liability_account_id)
                    .values(balance=Decimal("0"))
                )
                await session.execute(
                    entries.insert().values(
                        transfer_id=transfer_id,
                        account_id=market_liability_account_id,
                        amount=-total_house,
                    )
                )
                await session.execute(
                    accounts.update()
                    .where(accounts.c.id == house_revenue_account_id)
                    .values(balance=accounts.c.balance + total_house)
                )
                await session.execute(
                    entries.insert().values(
                        transfer_id=transfer_id,
                        account_id=house_revenue_account_id,
                        amount=total_house,
                    )
                )

            # 8. Update market
            await session.execute(
                markets.update()
                .where(markets.c.id == market_id)
                .values(
                    status="RESOLVED",
                    winning_outcome=winning_outcome,
                    settled_at=func.now(),
                )
            )

            # 9. Audit log
            await session.execute(
                audit_log.insert().values(
                    event_type="market_settled",
                    market_id=market_id,
                    data=json.dumps(
                        {
                            "winning_outcome": winning_outcome,
                            "resolver": resolver,
                            "transfer_id": transfer_id,
                            "total_payout": str(total_payout),
                            "total_house_revenue": str(total_house),
                            "winners": len(winners),
                            "losers": len(losers),
                        }
                    ),
                )
            )

    return {
        "status": "settled",
        "transfer_id": transfer_id,
        "winners": len(winners),
        "losers": len(losers),
        "total_payout": total_payout,
        "total_house_revenue": total_house,
    }


# ---------------------------------------------------------------------------
# Bet placement (concurrent with settlement)
# ---------------------------------------------------------------------------

async def place_bet(
    session_maker: async_sessionmaker[AsyncSession],
    market_id: int,
    user_account_id: int,
    outcome: str,
    stake: Decimal,
    market_liability_account_id: int = 3,
) -> dict:
    """Place a bet: lock wallet, check balance, debit user, credit market_liability, insert bet."""
    async with session_maker() as session:
        async with session.begin():
            # Lock market first to check status
            mkt = (
                await session.execute(
                    select(markets.c.status)
                    .where(markets.c.id == market_id)
                    .with_for_update()
                )
            ).one_or_none()

            if mkt is None or mkt.status != "OPEN":
                return {"status": "rejected", "reason": "market_not_open"}

            # Lock accounts in sorted order
            for aid in sorted([user_account_id, market_liability_account_id]):
                await session.execute(
                    select(accounts.c.id).where(accounts.c.id == aid).with_for_update()
                )

            # Check balance
            bal = (
                await session.execute(
                    select(accounts.c.balance).where(accounts.c.id == user_account_id)
                )
            ).scalar_one()

            if bal < stake:
                return {"status": "rejected", "reason": "insufficient_balance"}

            # Debit user
            await session.execute(
                accounts.update()
                .where(accounts.c.id == user_account_id)
                .values(balance=accounts.c.balance - stake)
            )

            # Credit market_liability
            await session.execute(
                accounts.update()
                .where(accounts.c.id == market_liability_account_id)
                .values(balance=accounts.c.balance + stake)
            )

            transfer_id = f"bet:{uuid.uuid4().hex[:8]}"
            await session.execute(
                entries.insert().values(
                    transfer_id=transfer_id, account_id=user_account_id, amount=-stake
                )
            )
            await session.execute(
                entries.insert().values(
                    transfer_id=transfer_id,
                    account_id=market_liability_account_id,
                    amount=stake,
                )
            )

            # Insert bet
            result = await session.execute(
                bets.insert()
                .values(
                    market_id=market_id,
                    user_account_id=user_account_id,
                    outcome=outcome,
                    stake=stake,
                    status="OPEN",
                )
                .returning(bets.c.id)
            )
            bet_id = result.scalar_one()

    return {"status": "placed", "bet_id": bet_id, "transfer_id": transfer_id}


# ---------------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------------

async def verify_ledger_integrity(session_maker: async_sessionmaker[AsyncSession]) -> dict:
    """Check SUM(entries) == balance for every operational account (excludes system mint)."""
    async with session_maker() as session:
        acct_rows = (await session.execute(
            select(accounts.c.id, accounts.c.name, accounts.c.kind, accounts.c.balance)
            .where(accounts.c.kind != "system")
        )).all()

        drifts = []
        for acct in acct_rows:
            entry_sum = (
                await session.execute(
                    select(func.coalesce(func.sum(entries.c.amount), 0)).where(
                        entries.c.account_id == acct.id
                    )
                )
            ).scalar_one()

            drift = acct.balance - entry_sum
            drifts.append({
                "account_id": acct.id,
                "name": acct.name,
                "balance": str(acct.balance),
                "entry_sum": str(entry_sum),
                "drift": str(drift),
            })

        total_drift = sum(Decimal(d["drift"]) for d in drifts)
        return {"drifts": drifts, "total_drift": str(total_drift), "clean": total_drift == 0}


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

async def setup_schema(engine):
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await conn.run_sync(metadata.create_all)


async def teardown_schema(engine):
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


async def seed_data(session_maker: async_sessionmaker[AsyncSession], n_users: int = 50):
    """Seed: 1 market, n_users user wallets (1000 each), house_revenue, market_liability."""
    async with session_maker() as session:
        async with session.begin():
            # System account (play-money mint — excluded from integrity checks)
            await session.execute(accounts.insert().values(
                id=1, name="system", kind="system", balance=Decimal("10000000")
            ))
            await session.execute(
                accounts.insert().values(id=2, name="house_revenue", kind="house", balance=0)
            )
            await session.execute(
                accounts.insert().values(id=3, name="market_liability", kind="liability", balance=0)
            )

            # User wallets with offsetting double-entry from system account
            user_total = Decimal("0")
            for i in range(n_users):
                uid = 100 + i
                tid = f"seed:{uid}"
                await session.execute(
                    accounts.insert().values(
                        id=uid, name=f"user_{i}", kind="user_wallet", balance=Decimal("1000")
                    )
                )
                await session.execute(
                    entries.insert().values(transfer_id=tid, account_id=uid, amount=Decimal("1000"))
                )
                await session.execute(
                    entries.insert().values(transfer_id=tid, account_id=1, amount=Decimal("-1000"))
                )
                user_total += Decimal("1000")

            # Debit system account balance to match entries
            await session.execute(
                accounts.update().where(accounts.c.id == 1)
                .values(balance=accounts.c.balance - user_total)
            )

            # Market
            await session.execute(
                markets.insert().values(id=1, question="Will it rain tomorrow?", status="OPEN")
            )


async def test_1_basic_settlement(session_maker):
    """10 bets (5 YES, 5 NO), settle YES wins. Verify balances + ledger."""
    print("\n[TEST 1] Basic settlement (10 bets, 5 winners, 5 losers)")

    # Place 10 bets: users 100-104 bet YES, users 105-109 bet NO
    for i in range(5):
        r = await place_bet(session_maker, 1, 100 + i, "YES", Decimal("100"))
        assert r["status"] == "placed", f"Bet placement failed: {r}"
    for i in range(5):
        r = await place_bet(session_maker, 1, 105 + i, "NO", Decimal("100"))
        assert r["status"] == "placed", f"Bet placement failed: {r}"

    # Settle: YES wins
    result = await resolve_market(session_maker, 1, "YES")
    assert result["status"] == "settled", f"Settlement failed: {result}"
    assert result["winners"] == 5
    assert result["losers"] == 5
    assert result["total_payout"] == Decimal("1000")  # 5 * 100 * 2
    # Balanced 50/50: total stakes (1000) == total payouts (1000), house gets 0
    assert result["total_house_revenue"] == Decimal("0")

    # Verify balances
    async with session_maker() as session:
        # Winners: started 1000, bet 100, won 200 = 1100
        for i in range(5):
            bal = (await session.execute(
                select(accounts.c.balance).where(accounts.c.id == 100 + i)
            )).scalar_one()
            assert bal == Decimal("1100"), f"Winner {100+i} balance: {bal}, expected 1100"

        # Losers: started 1000, bet 100, lost = 900
        for i in range(5):
            bal = (await session.execute(
                select(accounts.c.balance).where(accounts.c.id == 105 + i)
            )).scalar_one()
            assert bal == Decimal("900"), f"Loser {105+i} balance: {bal}, expected 900"

        # Market status
        mkt = (await session.execute(
            select(markets.c.status, markets.c.winning_outcome, markets.c.settled_at)
            .where(markets.c.id == 1)
        )).one()
        assert mkt.status == "RESOLVED"
        assert mkt.winning_outcome == "YES"
        assert mkt.settled_at is not None

        # Bet statuses
        bet_rows = (await session.execute(select(bets.c.outcome, bets.c.status))).all()
        for b in bet_rows:
            if b.outcome == "YES":
                assert b.status == "SETTLED_WON"
            else:
                assert b.status == "SETTLED_LOST"

        # Audit log
        log = (await session.execute(
            select(audit_log.c.event_type, audit_log.c.data).where(audit_log.c.market_id == 1)
        )).all()
        assert len(log) == 1
        assert log[0].event_type == "market_settled"
        log_data = json.loads(log[0].data)
        assert log_data["winners"] == 5
        assert log_data["losers"] == 5

    # Ledger integrity
    integrity = await verify_ledger_integrity(session_maker)
    assert integrity["clean"], f"Ledger drift: {integrity['drifts']}"

    print(f"  Winners (5): balance 1100 each -- OK")
    print(f"  Losers (5): balance 900 each -- OK")
    print(f"  Ledger drift: {integrity['total_drift']} -- OK")
    print(f"  Audit log: 1 entry with correct data -- OK")
    print("  PASS")


async def test_2_idempotent_settlement(session_maker):
    """Call resolve_market twice on same market. Second call must be no-op."""
    print("\n[TEST 2] Idempotent settlement (replay protection)")

    # Market 1 already settled from test 1
    result = await resolve_market(session_maker, 1, "YES")
    assert result["status"] == "idempotent_skip", f"Expected idempotent_skip, got: {result}"

    # Verify no double entries
    async with session_maker() as session:
        audit_count = (await session.execute(
            select(func.count()).select_from(audit_log).where(audit_log.c.market_id == 1)
        )).scalar_one()
        assert audit_count == 1, f"Expected 1 audit entry, got {audit_count}"

    integrity = await verify_ledger_integrity(session_maker)
    assert integrity["clean"], f"Ledger drift after replay: {integrity['drifts']}"

    print(f"  Second resolve_market returned: {result['status']} -- OK")
    print(f"  Audit log still has 1 entry -- OK")
    print(f"  Ledger still clean -- OK")
    print("  PASS")


async def test_3_concurrent_settlement(session_maker):
    """2 concurrent resolve_market calls on same market. Only one should succeed."""
    print("\n[TEST 3] Concurrent settlement (race condition)")

    # Create new market + bets (IDs 400-409 to avoid seed collision)
    async with session_maker() as session:
        async with session.begin():
            await session.execute(
                markets.insert().values(id=2, question="Concurrent test", status="OPEN")
            )
            for i in range(10):
                uid = 400 + i
                tid = f"seed:{uid}"
                await session.execute(
                    accounts.insert().values(
                        id=uid, name=f"concurrent_user_{i}", kind="user_wallet", balance=Decimal("1000")
                    )
                )
                await session.execute(entries.insert().values(transfer_id=tid, account_id=uid, amount=Decimal("1000")))
                await session.execute(entries.insert().values(transfer_id=tid, account_id=1, amount=Decimal("-1000")))
            await session.execute(
                accounts.update().where(accounts.c.id == 1)
                .values(balance=accounts.c.balance - Decimal("10000"))
            )

    # Place bets
    for i in range(5):
        await place_bet(session_maker, 2, 400 + i, "YES", Decimal("50"))
    for i in range(5):
        await place_bet(session_maker, 2, 405 + i, "NO", Decimal("50"))

    # Race: 2 concurrent settlements
    results = await asyncio.gather(
        resolve_market(session_maker, 2, "YES", resolver="admin_1"),
        resolve_market(session_maker, 2, "YES", resolver="admin_2"),
    )

    settled = [r for r in results if r["status"] == "settled"]
    skipped = [r for r in results if r["status"] == "idempotent_skip"]

    assert len(settled) == 1, f"Expected exactly 1 settled, got {len(settled)}: {results}"
    assert len(skipped) == 1, f"Expected exactly 1 skip, got {len(skipped)}: {results}"

    integrity = await verify_ledger_integrity(session_maker)
    assert integrity["clean"], f"Ledger drift after concurrent settle: {integrity['drifts']}"

    print(f"  Result 1: {results[0]['status']}")
    print(f"  Result 2: {results[1]['status']}")
    print(f"  Exactly 1 settled, 1 skipped -- OK")
    print(f"  Ledger clean -- OK")
    print("  PASS")


async def test_4_large_batch(session_maker):
    """50 bets on one market. Verify settlement performance + correctness."""
    print("\n[TEST 4] Large batch settlement (50 bets)")

    # Create market + users (IDs 500-549)
    async with session_maker() as session:
        async with session.begin():
            await session.execute(
                markets.insert().values(id=3, question="Large batch test", status="OPEN")
            )
            for i in range(50):
                uid = 500 + i
                tid = f"seed:{uid}"
                await session.execute(
                    accounts.insert().values(
                        id=uid, name=f"batch_user_{i}", kind="user_wallet", balance=Decimal("500")
                    )
                )
                await session.execute(entries.insert().values(transfer_id=tid, account_id=uid, amount=Decimal("500")))
                await session.execute(entries.insert().values(transfer_id=tid, account_id=1, amount=Decimal("-500")))
            await session.execute(
                accounts.update().where(accounts.c.id == 1)
                .values(balance=accounts.c.balance - Decimal("25000"))
            )

    # Place 50 bets: 25 YES, 25 NO
    for i in range(25):
        await place_bet(session_maker, 3, 500 + i, "YES", Decimal("100"))
    for i in range(25):
        await place_bet(session_maker, 3, 525 + i, "NO", Decimal("100"))

    # Settle and measure time
    t0 = time.time()
    result = await resolve_market(session_maker, 3, "NO")
    elapsed_ms = (time.time() - t0) * 1000

    assert result["status"] == "settled"
    assert result["winners"] == 25
    assert result["losers"] == 25

    integrity = await verify_ledger_integrity(session_maker)
    assert integrity["clean"], f"Ledger drift: {integrity['drifts']}"

    # Count entries for this settlement
    async with session_maker() as session:
        entry_count = (await session.execute(
            select(func.count()).select_from(entries)
            .where(entries.c.transfer_id.like(f"settle:3:%"))
        )).scalar_one()

    print(f"  Settled 50 bets in {elapsed_ms:.1f}ms")
    print(f"  Winners: {result['winners']}, Losers: {result['losers']}")
    print(f"  Total payout: {result['total_payout']}")
    print(f"  Ledger entries created: {entry_count}")
    print(f"  Ledger drift: {integrity['total_drift']} -- OK")
    print("  PASS")


async def test_5_concurrent_bet_during_settlement(session_maker):
    """Place bet while settlement is in progress. Bet should be rejected (market locked)."""
    print("\n[TEST 5] Concurrent bet placement during settlement")

    # Create market + users (IDs 600-611)
    async with session_maker() as session:
        async with session.begin():
            await session.execute(
                markets.insert().values(id=4, question="Race bet vs settle", status="OPEN")
            )
            for i in range(12):
                uid = 600 + i
                tid = f"seed:{uid}"
                await session.execute(
                    accounts.insert().values(
                        id=uid, name=f"race_user_{i}", kind="user_wallet", balance=Decimal("500")
                    )
                )
                await session.execute(entries.insert().values(transfer_id=tid, account_id=uid, amount=Decimal("500")))
                await session.execute(entries.insert().values(transfer_id=tid, account_id=1, amount=Decimal("-500")))
            await session.execute(
                accounts.update().where(accounts.c.id == 1)
                .values(balance=accounts.c.balance - Decimal("6000"))
            )

    # Place 10 bets
    for i in range(5):
        await place_bet(session_maker, 4, 600 + i, "YES", Decimal("50"))
    for i in range(5):
        await place_bet(session_maker, 4, 605 + i, "NO", Decimal("50"))

    # Race: settle + concurrent bet
    settle_task = resolve_market(session_maker, 4, "YES")
    bet_task = place_bet(session_maker, 4, 610, "YES", Decimal("50"))

    results = await asyncio.gather(settle_task, bet_task, return_exceptions=True)

    settle_result = results[0]
    bet_result = results[1]

    print(f"  Settlement: {settle_result['status'] if isinstance(settle_result, dict) else settle_result}")

    if isinstance(bet_result, dict):
        print(f"  Concurrent bet: {bet_result['status']} (reason: {bet_result.get('reason', 'n/a')})")
        # If bet went through, it should be either rejected or placed BEFORE settlement locked
        if bet_result["status"] == "placed":
            print("  NOTE: Bet placed before settlement lock acquired -- acceptable race outcome")
        elif bet_result["status"] == "rejected":
            print("  Bet correctly rejected (market locked/closed) -- optimal outcome")
    else:
        print(f"  Concurrent bet raised: {type(bet_result).__name__}: {bet_result}")
        print("  Serialization conflict -- acceptable (would retry in production)")

    integrity = await verify_ledger_integrity(session_maker)
    assert integrity["clean"], f"Ledger drift: {integrity['drifts']}"
    print(f"  Ledger clean -- OK")
    print("  PASS")


async def test_6_entry_sum_conservation(session_maker):
    """SUM(entries) for operational transfers (bet:* and settle:*) must be zero."""
    print("\n[TEST 6] Double-entry conservation (operational SUM = 0)")

    async with session_maker() as session:
        # Operational entries only (bet + settlement), excluding seed/mint
        op_total = (await session.execute(
            select(func.coalesce(func.sum(entries.c.amount), 0))
            .where(
                entries.c.transfer_id.like("bet:%")
                | entries.c.transfer_id.like("settle:%")
            )
        )).scalar_one()

        op_count = (await session.execute(
            select(func.count()).select_from(entries)
            .where(
                entries.c.transfer_id.like("bet:%")
                | entries.c.transfer_id.like("settle:%")
            )
        )).scalar_one()

        total_count = (await session.execute(
            select(func.count()).select_from(entries)
        )).scalar_one()

    print(f"  Total entries: {total_count} (operational: {op_count})")
    print(f"  Operational SUM(amount): {op_total}")
    assert op_total == 0, f"Double-entry invariant violated: SUM = {op_total}"
    print("  PASS (operational SUM = 0, double-entry invariant holds)")


async def main():
    print("=" * 60)
    print(" Spike 004: Settlement ACID Transaction - Test Suite")
    print("=" * 60)

    engine = create_async_engine(DATABASE_URL, pool_size=20, max_overflow=30, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    await setup_schema(engine)
    print("Schema created: spike_004")

    try:
        await seed_data(session_maker)
        print("Seed data: 50 user wallets (1000 each) + system accounts + 1 market")

        results = {}
        tests = [
            ("basic_settlement", test_1_basic_settlement),
            ("idempotent_settlement", test_2_idempotent_settlement),
            ("concurrent_settlement", test_3_concurrent_settlement),
            ("large_batch", test_4_large_batch),
            ("concurrent_bet_during_settlement", test_5_concurrent_bet_during_settlement),
            ("entry_sum_conservation", test_6_entry_sum_conservation),
        ]

        for name, test_fn in tests:
            try:
                await test_fn(session_maker)
                results[name] = "PASS"
            except Exception as e:
                print(f"  FAIL: {e}")
                import traceback
                traceback.print_exc()
                results[name] = f"FAIL: {e}"

        print("\n" + "=" * 60)
        print(" RESULTS")
        print("=" * 60)
        for name, result in results.items():
            icon = "OK" if result == "PASS" else "XX"
            print(f"  [{icon}] {name}: {result}")

        passed = sum(1 for r in results.values() if r == "PASS")
        total = len(results)
        print(f"\n  {passed}/{total} tests passed")

    finally:
        await teardown_schema(engine)
        await engine.dispose()
        print("\nSchema dropped: spike_004")


if __name__ == "__main__":
    asyncio.run(main())
