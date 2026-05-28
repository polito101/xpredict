---
spike: 001
name: async-wallet-concurrency
type: standard
validates: "Given 50+ concurrent async transfers against the same wallet (SQLAlchemy 2.0 + asyncpg + Postgres 16), when using SELECT ... FOR UPDATE + CHECK (balance >= 0), then final balance is exactly correct with zero drift and no deadlocks"
verdict: VALIDATED
related: []
tags: [sqlalchemy, asyncpg, postgres, concurrency, wallet, double-entry, phase-3]
---

# Spike 001: async-wallet-concurrency

## What This Validates
Given 50+ concurrent async wallet transfers using SQLAlchemy 2.0 async + asyncpg + Postgres 16,
when using `SELECT ... FOR UPDATE` inside `AsyncSession.begin()` with consistent lock ordering and `CHECK (balance >= 0)`,
then the final balance is exactly correct, the double-entry ledger matches, and no deadlocks occur.

## Research

| Approach | Tool/Library | Pros | Cons | Verdict |
|----------|-------------|------|------|---------|
| `SELECT ... FOR UPDATE` (pessimistic) | SQLAlchemy `with_for_update()` | Serializes access, reliable app-level checks, READ COMMITTED sufficient | Holds lock until commit | **Chosen** |
| Optimistic locking (version column) | SQLAlchemy `version_id_col` | No lock contention | Retry storms under wallet-level contention | Rejected |
| SERIALIZABLE isolation | Postgres | Strongest guarantees | High overhead, overkill for row-level locking | Alternative noted |
| No locking + SQL arithmetic | `balance = balance - N` | Simplest code | TOCTOU: app check unreliable, CHECK becomes primary guard | Tested as comparison |

Sources: SQLAlchemy 2.0 asyncio docs, PostgreSQL SELECT FOR UPDATE docs, PITFALLS.md Pitfall #1.

## How to Run
```bash
cd backend
uv run python ../.planning/spikes/001-async-wallet-concurrency/spike_wallet.py
```

Requires Postgres running on localhost:5432 (docker-compose up from Phase 1).
Override with `DATABASE_URL` env var.

## What to Expect
5 experiments run sequentially, each with 100 concurrent async tasks. All should report PASS.

## Investigation Trail

### Iteration 1: Core experiments
Built 5 experiments testing the full spectrum:

1. **Happy path (100x $10 from $1000)** — all 100 succeed, balance = 0, ledger matches
2. **Overdraw with FOR UPDATE (100x $10 from $500)** — exactly 50 ok / 50 rejected by app, zero CHECK violations
3. **TOCTOU without FOR UPDATE (100x $10 from $500)** — THE KEY FINDING (see below)
4. **Bidirectional with lock ordering (50 A→B + 50 B→A)** — zero deadlocks, 100% success
5. **Bidirectional without lock ordering** — catastrophic deadlock rate

### Key discovery: TOCTOU race quantified
Experiment 3 proved the race is real and frequent:
- **50 ok** — tasks that happened to run sequentially
- **1 insufficient** — one caught by the app-level check
- **49 check_violation** — 49 tasks slipped past the app check but were caught by the DB CHECK

Without FOR UPDATE, **49% of overdraw attempts bypass the application logic** and must be caught by the database constraint. The CHECK constraint prevents data corruption, but the app receives ugly `IntegrityError` instead of clean "insufficient balance" responses.

### Key discovery: Deadlock severity without lock ordering
Experiment 5 showed **96 out of 100 bidirectional transfers deadlocked** without sorted lock ordering. Performance impact: 23,850ms vs 1,613ms (15x slower due to Postgres deadlock detection + rollback overhead).

## Results

**Verdict: VALIDATED**

All 5 experiments passed. Concrete evidence:

| Experiment | Time | Success | Drift | Ledger | Deadlocks |
|-----------|------|---------|-------|--------|-----------|
| 1. Happy path (100x $10) | 1444ms | 100/100 | 0 | OK | 0 |
| 2. Overdraw + FOR UPDATE | 955ms | 50/100 | 0 | OK | 0 |
| 3. TOCTOU (no FOR UPDATE) | 949ms | 50/100 | 0 | OK | 0 |
| 4. Bidirectional + ordering | 1613ms | 100/100 | 0 | OK | 0 |
| 5. Bidirectional (no ordering) | 23850ms | 4/100 | 0 | OK | **96** |

### Non-negotiable patterns for Phase 3:

1. **`SELECT ... FOR UPDATE` on the wallet row** — without it, 49% of overdraw attempts bypass app logic
2. **Lock ordering by account ID** — without it, 96% of bidirectional transfers deadlock
3. **`CHECK (balance >= 0)`** — defense-in-depth; catches what app misses, but should NOT be the primary mechanism
4. **Double-entry SUM verification** — ledger matched balance in every experiment, even under deadlock chaos
5. **`AsyncSession.begin()` context manager** — auto-rollback on exception; clean transaction boundaries

### Performance baseline:
- FOR UPDATE serialized transfers: ~16ms/transfer (1613ms / 100)
- Without lock ordering (deadlock-heavy): ~240ms/transfer (23850ms / 100) — 15x slower
- Pool size 20 + max_overflow 30 handled 100 concurrent tasks without pool exhaustion

### What NOT to do:
- Do NOT rely on `balance = balance - amount` SQL arithmetic alone — app-level check is unreliable without FOR UPDATE
- Do NOT skip lock ordering for transfers between accounts — deadlock rate is catastrophic
- Do NOT use SERIALIZABLE isolation as the default — READ COMMITTED + FOR UPDATE is sufficient and faster
