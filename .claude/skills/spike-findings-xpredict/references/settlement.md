# Settlement

## Requirements

- Settlement must atomically set `markets.status = SETTLING` before querying bets (prevents late-bet pot imbalance)
- Losers' stakes stay in market_liability (no separate debit during settlement) -- they fund winner payouts
- `settled_at IS NULL` is the idempotency gate for settlement replay protection
- All money amounts must be `Decimal` / `NUMERIC(18,4)` -- never float
- Double-entry invariant: SUM of all bet + settlement entries = 0
- FOR UPDATE on market row serializes concurrent settlements

## How to Build It

### 1. Schema

```python
accounts = Table(
    "accounts", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("kind", String(50), nullable=False),
    Column("balance", Numeric(18, 4), nullable=False, server_default="0"),
    CheckConstraint("balance >= 0", name="ck_balance_non_negative"),
)

markets = Table(
    "markets", metadata,
    Column("id", Integer, primary_key=True),
    Column("question", String(500), nullable=False),
    Column("status", String(20), nullable=False, server_default="OPEN"),
    Column("winning_outcome", String(10)),
    Column("settled_at", DateTime(timezone=True)),
)

bets = Table(
    "bets", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("market_id", Integer, nullable=False),
    Column("user_account_id", Integer, nullable=False),
    Column("outcome", String(10), nullable=False),
    Column("stake", Numeric(18, 4), nullable=False),
    Column("status", String(20), nullable=False, server_default="OPEN"),
)
```

### 2. Settlement service (resolve_market)

```python
async def resolve_market(session_maker, market_id, winning_outcome, resolver="admin"):
    async with session_maker() as session:
        async with session.begin():
            # 1. Lock market + idempotency check
            mkt = (await session.execute(
                select(markets.c.id, markets.c.status, markets.c.settled_at)
                .where(markets.c.id == market_id)
                .with_for_update()
            )).one_or_none()

            if mkt is None:
                return {"status": "error", "reason": "market_not_found"}
            if mkt.settled_at is not None:
                return {"status": "idempotent_skip", "reason": "already_settled"}

            # 2. Lock all bets for this market
            bet_rows = (await session.execute(
                select(bets.c.id, bets.c.user_account_id, bets.c.outcome, bets.c.stake)
                .where(bets.c.market_id == market_id, bets.c.status == "OPEN")
                .with_for_update()
            )).all()

            # 3. Classify winners/losers
            winners = [b for b in bet_rows if b.outcome == winning_outcome]
            losers = [b for b in bet_rows if b.outcome != winning_outcome]

            # 4. Lock all affected accounts in sorted order (deadlock prevention)
            account_ids = {house_revenue_id, market_liability_id}
            for b in bet_rows:
                account_ids.add(b.user_account_id)
            for aid in sorted(account_ids):
                await session.execute(
                    select(accounts.c.id).where(accounts.c.id == aid).with_for_update()
                )

            # 5. Pay winners: market_liability -> user_wallet
            transfer_id = f"settle:{market_id}:{uuid.uuid4().hex[:8]}"
            for b in winners:
                payout = b.stake * 2  # binary 50/50
                # Credit winner + debit market_liability + ledger entries
                ...

            # 6. Mark losers as SETTLED_LOST (no money movement)
            for b in losers:
                await session.execute(
                    bets.update().where(bets.c.id == b.id).values(status="SETTLED_LOST")
                )

            # 7. Transfer remaining pot to house_revenue
            # (0 in balanced market, >0 if more losers than winners)

            # 8. Update market status + settled_at
            # 9. Write audit_log entry
```

### 3. Accounting model

```
BET PLACEMENT:
  user_wallet     -stake
  market_liability +stake
  (2 entries per bet)

SETTLEMENT (market resolved, YES wins):
  For each YES bettor:
    market_liability  -(stake * payout_ratio)
    user_wallet       +(stake * payout_ratio)
    bet.status = SETTLED_WON

  For each NO bettor:
    bet.status = SETTLED_LOST
    (no money movement -- their stake already funds winners)

  Remaining pot (market_liability balance after payouts):
    market_liability  -> house_revenue
    (0 in a balanced market; positive if more losers than winners)

  markets.status = RESOLVED
  markets.winning_outcome = "YES"
  markets.settled_at = now()
  audit_log entry with full details
```

### 4. Bet placement with market lock

```python
async def place_bet(session_maker, market_id, user_account_id, outcome, stake):
    async with session_maker() as session:
        async with session.begin():
            # Lock market first to check status
            mkt = (await session.execute(
                select(markets.c.status)
                .where(markets.c.id == market_id)
                .with_for_update()
            )).one_or_none()

            if mkt is None or mkt.status != "OPEN":
                return {"status": "rejected", "reason": "market_not_open"}

            # Lock accounts in sorted order, check balance, debit/credit, insert bet
            ...
```

### 5. Integrity verification

```python
async def verify_ledger_integrity(session_maker):
    """Check SUM(entries) == balance for every operational account."""
    # For each non-system account, verify balance matches SUM(entries)
    # Returns {clean: bool, total_drift: Decimal, drifts: [...]}
```

## What to Avoid

1. **DO NOT double-debit losers' stakes during settlement** -- first attempt had this bug. Losers' stakes are ALREADY in market_liability from bet placement. Only debit market_liability for winner payouts, then sweep remaining pot to house_revenue.
2. **DO NOT settle without transitioning to SETTLING status first** -- a late bet between market lock and payout calculation unbalances the pot. Production code must: (a) lock market FOR UPDATE, (b) set status = SETTLING, (c) then query bets.
3. **DO NOT rely on `settled_at IS NOT NULL` check without FOR UPDATE** -- two concurrent settlements could both read `settled_at IS NULL` without the row lock.
4. **DO NOT skip lock ordering when touching multiple accounts** -- same deadlock risk as spike 001 (96% deadlock rate without sorting).
5. **DO NOT build settlement for dynamic payout ratios yet** -- spike used fixed 2x for binary 50/50. Dynamic parimutuel ratios are a Phase 5+ extension.

## Constraints

- Performance: 50-bet settlement in ~155ms (including 50+ ledger entries, status updates, audit log)
- 10-bet settlement in ~30ms
- Concurrent settlement serialization overhead: ~50ms (FOR UPDATE wait)
- Pool size 20 + max_overflow 30 handles all tested loads
- In a balanced 50/50 binary market, house_revenue = 0 -- the house only profits from market imbalance
- System/mint accounts are excluded from integrity checks (play-money minting is one-sided by design)

## Origin

Synthesized from spikes: 004
Source files available in: sources/004-settlement-acid-transaction/
