---
name: spike-findings-xpredict
description: Implementation blueprint from spike experiments. Requirements, proven patterns, and verified knowledge for building xpredict. Auto-loaded during implementation work.
---

<context>
## Project: xpredict

White-label, production-grade prediction market platform. Spikes validated the four highest-risk technical unknowns: (1) concurrent async wallet locking, (2) Polymarket Gamma API parsing, (3) WebSocket real-time price streaming via Redis pub/sub, and (4) ACID settlement transactions with multi-entry ledger.

Spike sessions wrapped: 2026-05-27
</context>

<requirements>
## Requirements

These are non-negotiable design decisions that emerged from spike validation. Every feature area reference must honor these.

- Wallet transfers must be ACID-wrapped with `SELECT ... FOR UPDATE` pessimistic locking
- Balance must never go negative under any concurrency level (`CHECK (balance >= 0)`)
- Polymarket `closed` vs `resolved` distinction must be enforced at the parser level
- All money amounts must be `Decimal` / `NUMERIC(18,4)` -- never float
- Lock ordering by account ID is mandatory for cross-account transfers (96% deadlock rate without it)
- App-level balance check + FOR UPDATE together -- neither alone is sufficient
- Gamma API fields `outcomes`/`outcomePrices`/`clobTokenIds` are stringified JSON -- `json.loads()` required
- Use string numeric fields (`volume`), never float variants (`volumeNum`) for Decimal precision
- `umaResolutionStatus` is absent (not null) when no UMA process -- always check for `None`
- Settlement must atomically set `markets.status = SETTLING` before querying bets (prevents late-bet pot imbalance)
- Losers' stakes stay in market_liability (no separate debit during settlement) -- they fund winner payouts
- `settled_at IS NULL` is the idempotency gate for settlement replay protection
</requirements>

<findings_index>
## Feature Areas

| Area | Reference | Key Finding |
|------|-----------|-------------|
| Wallet & Concurrency | references/wallet-concurrency.md | FOR UPDATE + lock ordering + CHECK constraint = zero drift, zero deadlocks under 100 concurrent tasks |
| Polymarket Integration | references/polymarket-integration.md | Pydantic v2 parser handles stringified JSON, dual numeric encoding, and closed-vs-resolved state machine correctly |
| Real-Time Streaming | references/real-time-streaming.md | Redis pub/sub + FastAPI native WebSocket = sub-ms latency, zero message loss, perfect market isolation |
| Settlement | references/settlement.md | One ACID transaction settles 50 bets with multi-entry ledger in 155ms, idempotent replay, zero drift |

## Source Files

Original spike source files are preserved in `sources/` for complete reference.

- `sources/001-async-wallet-concurrency/` -- spike_wallet.py, README.md
- `sources/002-polymarket-gamma-parser/` -- gamma_parser.py, spike_gamma.py, README.md, fixtures/
- `sources/003-websocket-price-streaming/` -- spike_ws_server.py, spike_ws_publisher.py, spike_ws_test.py, index.html, README.md
- `sources/004-settlement-acid-transaction/` -- spike_settlement.py, README.md
</findings_index>

<metadata>
## Processed Spikes

- 001-async-wallet-concurrency
- 002-polymarket-gamma-parser
- 003-websocket-price-streaming
- 004-settlement-acid-transaction
</metadata>
