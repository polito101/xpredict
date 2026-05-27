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
- Gamma API fields `outcomes`/`outcomePrices`/`clobTokenIds` are stringified JSON — `json.loads()` required
- Use string numeric fields (`volume`), never float variants (`volumeNum`) for Decimal precision
- `umaResolutionStatus` is absent (not null) when no UMA process — always check for `None`
- Settlement must atomically set `markets.status = SETTLING` before querying bets (prevents late-bet pot imbalance)
- Losers' stakes stay in market_liability (no separate debit during settlement) — they fund winner payouts
- `settled_at IS NULL` is the idempotency gate for settlement replay protection

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | async-wallet-concurrency | standard | Given 50 concurrent transfers, when `SELECT ... FOR UPDATE` + `CHECK (balance >= 0)`, then zero drift and no deadlocks | **VALIDATED** | sqlalchemy, asyncpg, postgres, concurrency, wallet |
| 002 | polymarket-gamma-parser | standard | Given real Gamma API responses, when parsed with Pydantic v2, then stringified JSON, mixed numerics, and umaResolutionStatus state machine produce correct status | **VALIDATED** | polymarket, gamma-api, pydantic, parsing |
| 003 | websocket-price-streaming | standard | Given a FastAPI WebSocket endpoint broadcasting odds changes, when a Celery task publishes a price update via Redis pub/sub, then a Next.js client receives the update in <2s with auto-reconnect on disconnect | **VALIDATED** | fastapi, websocket, redis, pubsub, nextjs |
| 004 | settlement-acid-transaction | standard | Given a bet on a resolved market, when SettlementService.resolve_market() runs with 50 concurrent bets, then all bets are settled in one ACID transaction with correct multi-entry ledger, zero drift, and idempotent replay | **VALIDATED** | sqlalchemy, asyncpg, settlement, ledger, concurrency |
