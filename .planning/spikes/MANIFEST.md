# Spike Manifest

## Idea
XPredict — validate the two highest-risk technical unknowns before building Phase 3 (Wallet & Ledger) and Phase 6 (Polymarket Sync): (1) concurrent async wallet locking in SQLAlchemy 2.0 with Postgres, and (2) Polymarket Gamma API response parsing with its undocumented quirks.

## Requirements

- Wallet transfers must be ACID-wrapped with `SELECT ... FOR UPDATE` pessimistic locking
- Balance must never go negative under any concurrency level (`CHECK (balance >= 0)`)
- Polymarket `closed` vs `resolved` distinction must be enforced at the parser level
- All money amounts must be `Decimal` / `NUMERIC(18,4)` — never float
- Lock ordering by account ID is mandatory for cross-account transfers (96% deadlock rate without it)
- App-level balance check + FOR UPDATE together — neither alone is sufficient

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | async-wallet-concurrency | standard | Given 50 concurrent transfers, when `SELECT ... FOR UPDATE` + `CHECK (balance >= 0)`, then zero drift and no deadlocks | **VALIDATED** | sqlalchemy, asyncpg, postgres, concurrency, wallet |
| 002 | polymarket-gamma-parser | standard | Given real Gamma API responses, when parsed with Pydantic v2, then stringified JSON, mixed numerics, and umaResolutionStatus state machine produce correct status | PENDING | polymarket, gamma-api, pydantic, parsing |
