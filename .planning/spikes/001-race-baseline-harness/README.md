---
spike: 001
name: race-baseline-harness
type: standard
validates: "Given naïve read→check→write under READ COMMITTED async + N concurrent overdrafts on one wallet, when run via asyncio.gather on real Postgres, then balance corrupts (drift / negative) — proving the race and building the shared load harness"
verdict: VALIDATED
related: [002, 003, 004]
tags: [concurrency, harness, race]
---

# Spike 001: Race Baseline + Shared Harness

## What This Validates

Given the naïve `read balance → check in Python → write` pattern under SQLAlchemy 2.0
async (READ COMMITTED, asyncpg), when N transfers hit the **same** wallet concurrently
via `asyncio.gather`, then the wallet corrupts — establishing that PITFALLS #1 is real on
*our* stack and producing the reusable concurrent-load harness (`_lib/harness.py`) that
spikes 002–004 build on.

## Research

- PITFALLS.md #1: "two concurrent bet requests both read balance=100, both check 100≥50,
  both insert −50 … balance ends at −50." Root cause: READ COMMITTED does not lock rows on
  `SELECT`; async handlers multiply the overlap.
- STACK.md §3.2: locked `accounts`/`transfers`/`entries` schema (UUID PKs), `NUMERIC(18,4)`,
  `version` column, append-only entries, balance as a denormalized cache.
- Faithfulness: a real Postgres is mandatory — sqlite serializes writers and lacks MVCC,
  `FOR UPDATE`, lock waits, and `SERIALIZABLE` aborts, so it cannot reproduce this race.

## How to Run

```
<repo>\backend\.venv\Scripts\python.exe .planning\spikes\001-race-baseline-harness\run.py
```

(Backend venv = exact Phase 3 versions: SQLAlchemy 2.0.43, asyncpg, Python 3.12. Needs Docker.)

## What to Expect

20 concurrent "spend 20 from a wallet of 100" (only 5 affordable). A correct system → final
balance 0, exactly 5 succeeded, drift 0. The three naïve variants:

- **A — naive_lost_update, CHECK off:** Python-computed write → DRIFT (balance ≠ ledger) and
  money created from nothing. **FAIL.**
- **B — naive_overdraw, CHECK off:** atomic decrement, no guard → NEGATIVE balance. **FAIL.**
- **C — naive_overdraw, CHECK on:** atomic decrement + `CHECK (balance >= 0)` → DB saves this
  single-row case (nuance, not a general fix).

## Investigation Trail

- First run reproduced the race deterministically on Postgres 16 / SQLAlchemy 2.0 async / asyncpg (Docker 29.4.3).
- **A** (lost_update, CHECK off): 20/20 "succeeded"; balance=80 (last-writer-wins from a stale read) but
  ledger=−300 and counterparty credited 400 → **drift=380, money created from nothing**.
- **B** (overdraw, CHECK off): 20/20 "succeeded"; **balance=−300** → wallet went deeply negative.
- **C** (overdraw, CHECK on): 5 ok / 15 rejected_check (23514); balance=0, drift=0 → atomic single-row
  decrement + `CHECK` protected THIS case. Nuance: does NOT generalize to multi-step logic (ANALYSIS §3).
- `global_entry_sum` stayed 0 throughout — double-entry itself is balanced; the corruption is in the
  balance cache + overdraw, which is what locking must protect.

## Results

**VERDICT: VALIDATED** — the naive race is real and harmful on our exact stack, and the shared harness
works. Evidence: A drift=380 + money created; B balance=−300. ⇒ the wallet debit MUST be guarded (spike 002).
