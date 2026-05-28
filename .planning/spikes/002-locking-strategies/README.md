---
spike: 002
name: locking-strategies
type: comparison
validates: "Given 50 concurrent overdraft transfers on one wallet, when guarded by FOR UPDATE vs optimistic version-CAS vs SERIALIZABLE+retry, then all are correct (balance>=0, drift 0, exactly affordable succeed) and we can compare throughput + retry amplification to pick the Phase 3 strategy"
verdict: VALIDATED — winner FOR UPDATE
related: [001, 004]
tags: [locking, for-update, optimistic, serializable, comparison]
---

# Spike 002: Locking Strategy Comparison

## What This Validates

The core Phase 3 decision. STACK.md §3.2 rule 5 prescribes **optimistic** locking (`version`
column); PITFALLS.md #1 and the ROADMAP prescribe **pessimistic** `SELECT … FOR UPDATE`. This
spike runs all three candidates (plus SERIALIZABLE) head-to-head over the identical
read→decide→write transfer so the comparison isolates the concurrency control itself.

All three must satisfy ROADMAP SC#2: final balance exact, zero drift, `CHECK (balance >= 0)`
holds. The tie-breaker is wall time, total attempts (retry amplification), and code complexity.

## Research

- PITFALLS.md #1: `SELECT … FOR UPDATE` on the wallet row inside the ledger transaction;
  "consider SERIALIZABLE for the bet placement and retry."
- STACK.md §3.2 rule 5: `UPDATE … SET version = version + 1 WHERE id = ? AND version = ?`;
  0 rows affected ⇒ raise and retry.
- Postgres: `FOR UPDATE` takes a row lock (writers block); SERIALIZABLE uses SSI and aborts
  conflicting txns with SQLSTATE `40001`; optimistic CAS detects via affected-rowcount.
- SQLAlchemy async: engine-level `isolation_level="SERIALIZABLE"`; `AsyncSession.begin()` for
  the unit-of-work; asyncpg surfaces `40001`/`23514` via `DBAPIError.orig.sqlstate`.

## How to Run

```
<repo>\backend\.venv\Scripts\python.exe .planning\spikes\002-locking-strategies\run.py
```

## What to Expect

For each strategy: `ok=5`, `rejected_insufficient` (or retry_exhausted) for the rest, final
balance `0`, drift `0`. Head-to-head table prints wall ms + attempt amplification:
- FOR UPDATE: low amplification (~1x); writers queue on the lock.
- optimistic CAS: high amplification under max contention (retry storms).
- SERIALIZABLE: abort+retry; amplification between the two, sensitive to SSI.

## Investigation Trail

- N=50 concurrent overdrafts; **all three strategies converged to the correct state** (5 ok, 45
  rejected_insufficient, balance 0, drift 0, global_entry_sum 0).
- The differentiator is retry amplification on the single hot wallet row:

  | strategy | correct | ok | wall ms | attempts | amplification |
  |---|---|---|---|---|---|
  | FOR UPDATE (pessimistic) | YES | 5 | 1140 | 50 | **1.00×** |
  | version CAS (optimistic) | YES | 5 | 1325 | 169 | 3.38× |
  | SERIALIZABLE + retry | YES | 5 | 1488 | 285 | 5.70× |

## Results

**VERDICT: VALIDATED — WINNER: FOR UPDATE (pessimistic).** All three are correct, but on a hot single
row FOR UPDATE has the lowest amplification (1.00×) and lowest latency; optimistic CAS and SERIALIZABLE
waste 3.4–5.7× the work in retries because every contender fights over the same row/`version`.
⇒ Phase 3 wallet debit = `SELECT … FOR UPDATE` inside `AsyncSession.begin()`, `CHECK (balance>=0)` as
defense-in-depth. Full reasoning in `LOCKING-ATOMICITY-ANALYSIS.md` §4–§5.
