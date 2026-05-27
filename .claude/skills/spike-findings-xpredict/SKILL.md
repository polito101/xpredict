---
name: spike-findings-xpredict
description: Implementation blueprint from spike experiments. Requirements, proven patterns, and verified knowledge for building xpredict. Auto-loaded during implementation work.
---

<context>
## Project: xpredict

White-label, production-grade prediction market platform. Spikes validated the two highest-risk technical unknowns: (1) concurrent async wallet locking in SQLAlchemy 2.0 with Postgres, and (2) Polymarket Gamma API response parsing with its undocumented quirks.

Spike sessions wrapped: 2026-05-27
</context>

<requirements>
## Requirements

These are non-negotiable design decisions that emerged from spike validation. Every feature area reference must honor these.

- Wallet transfers must be ACID-wrapped with `SELECT ... FOR UPDATE` pessimistic locking
- Balance must never go negative under any concurrency level (`CHECK (balance >= 0)`)
- Polymarket `closed` vs `resolved` distinction must be enforced at the parser level
- All money amounts must be `Decimal` / `NUMERIC(18,4)` — never float
- Lock ordering by account ID is mandatory for cross-account transfers (96% deadlock rate without it)
- App-level balance check + FOR UPDATE together — neither alone is sufficient
- Gamma API fields `outcomes`/`outcomePrices`/`clobTokenIds` are stringified JSON — `json.loads()` required
- Use string numeric fields (`volume`), never float variants (`volumeNum`) for Decimal precision
- `umaResolutionStatus` is absent (not null) when no UMA process — always check for `None`
</requirements>

<findings_index>
## Feature Areas

| Area | Reference | Key Finding |
|------|-----------|-------------|
| Wallet & Concurrency | references/wallet-concurrency.md | FOR UPDATE + lock ordering + CHECK constraint = zero drift, zero deadlocks under 100 concurrent tasks |
| Polymarket Integration | references/polymarket-integration.md | Pydantic v2 parser handles stringified JSON, dual numeric encoding, and closed-vs-resolved state machine correctly |

## Source Files

Original spike source files are preserved in `sources/` for complete reference.

- `sources/001-async-wallet-concurrency/` — spike_wallet.py, README.md
- `sources/002-polymarket-gamma-parser/` — gamma_parser.py, spike_gamma.py, README.md, fixtures/
</findings_index>

<metadata>
## Processed Spikes

- 001-async-wallet-concurrency
- 002-polymarket-gamma-parser
</metadata>
