# Spike Manifest

## Idea

XPredict — validate highest-risk technical unknowns across phases: (1) concurrent async wallet locking in SQLAlchemy 2.0 with Postgres (Phase 3), (2) Polymarket Gamma API response parsing (Phase 6), (3) WebSocket price streaming (Phase 9), and (4) settlement ACID transactions (Phase 5).

Primary references: STACK.md §3, PITFALLS.md #1 (race), #2 (closed vs resolved), #4 (Decimal), #5 (idempotent settlement), #9 (rate limits), #10 (single-transaction boundary).

## Requirements

- Money is `Decimal` + `NUMERIC(18,4)` end-to-end — never float (PITFALLS #4; locked Phase 1)
- Wallet transfers must be ACID-wrapped with `SELECT ... FOR UPDATE` pessimistic locking
- Balance must never go negative under any concurrency level (`CHECK (balance >= 0)`)
- `transfers.idempotency_key` is `UNIQUE`; duplicate keys must short-circuit, never double-apply
- Lock ordering by account ID is mandatory for cross-account transfers (96% deadlock rate without it)
- **Locking strategy (DECIDED by Spike 002): `SELECT ... FOR UPDATE`** — pessimistic 1.00x amplification vs optimistic 3.38x vs SERIALIZABLE 5.70x at N=50
- Polymarket `closed` vs `resolved` distinction must be enforced at the parser level
- Gamma API fields `outcomes`/`outcomePrices`/`clobTokenIds` are stringified JSON — `json.loads()` required
- Use string numeric fields (`volume`), never float variants (`volumeNum`) for Decimal precision
- `umaResolutionStatus` is absent (not null) when no UMA process — always check for `None`
- Settlement must atomically set `markets.status = SETTLING` before querying bets (prevents late-bet pot imbalance)
- Losers' stakes stay in market_liability (no separate debit during settlement) — they fund winner payouts
- `settled_at IS NULL` is the idempotency gate for settlement replay protection

## Spikes

### Phase 3 — Wallet Concurrency (detailed comparison)

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | race-baseline-harness | standard | Naive read-check-write under READ COMMITTED proves the race + builds shared harness | VALIDATED | concurrency, harness, race |
| 002a | lock-pessimistic-for-update | comparison | `SELECT ... FOR UPDATE` inside `AsyncSession.begin()` — exact balance, zero drift | WINNER 1.00x | locking, for-update |
| 002b | lock-optimistic-version-cas | comparison | `UPDATE ... SET version=version+1 WHERE version=?` + retry — correct, 3.38x | correct, 3.38x | locking, optimistic |
| 002c | lock-serializable-retry | comparison | `SERIALIZABLE` + retry-on-40001 — correct, 5.70x | correct, 5.70x | locking, serializable |
| 003 | atomic-transfer-idempotency | standard | Fault injection mid-tx -> nothing commits; concurrent idempotency keys -> exactly one persists | VALIDATED | atomicity, idempotency |
| 004 | deadlock-ordering | standard | Unordered locks -> deadlock 40P01; canonical UUID order -> no deadlock | VALIDATED | locking, deadlock |

### Phase 6+ — Polymarket, WebSocket, Settlement

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 002 | polymarket-gamma-parser | standard | Pydantic v2 parsing of stringified JSON, mixed numerics, umaResolutionStatus state machine | **VALIDATED** | polymarket, gamma-api, pydantic |
| 003 | websocket-price-streaming | standard | FastAPI WebSocket + Redis pub/sub broadcast, <2s latency, auto-reconnect | **VALIDATED** | fastapi, websocket, redis |
| 004 | settlement-acid-transaction | standard | SettlementService.resolve_market() with 50 concurrent bets, correct multi-entry ledger, zero drift, idempotent replay | **VALIDATED** | settlement, ledger, concurrency |
