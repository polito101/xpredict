---
spike: 003
name: atomic-transfer-idempotency
type: standard
validates: "Given a transfer = insert transfer + 2 entries + balance update in one tx, when a fault is injected mid-tx then nothing commits and entries net to zero; and given concurrent identical Idempotency-Keys, then exactly one transfer/entry-pair persists"
verdict: VALIDATED
related: [001, 002]
tags: [atomicity, idempotency, transaction]
---

# Spike 003: Atomic Transfer + Idempotency

## What This Validates

Two non-negotiable Phase 3 properties:
- **Atomicity (PITFALLS #10):** the whole transfer (transfer row + ≥2 entries + balance
  mutations) commits or rolls back as one unit. This is the pattern Phase 5 bet placement reuses.
- **Idempotency (ROADMAP SC#3):** the `transfers.idempotency_key` UNIQUE constraint makes a
  retried/duplicated request apply exactly once, even under concurrency.

## Research

- STACK.md §3.2 rules 1 & 4: one transaction per transfer; `idempotency_key UNIQUE` short-circuits.
- PITFALLS.md #10: no transaction boundary ⇒ orphaned bet or ledger; #5: idempotency prevents
  double-apply under at-least-once retries.
- Postgres: a UNIQUE violation (`23505`) inside the tx aborts it ⇒ the duplicate's balance change
  never persists; `AsyncSession.begin()` rolls back the entire unit on any exception.

## How to Run

```
<repo>\backend\.venv\Scripts\python.exe .planning\spikes\003-atomic-transfer-idempotency\run.py
```

## What to Expect

- **Atomicity:** row counts identical before/after the injected fault (only the seed's opening
  transfer present); wallet balance unchanged.
- **Idempotency:** 10 concurrent calls sharing `charge:req-42` ⇒ `ok=1`, `idempotent_dup=9`,
  wallet debited exactly once, exactly one new transfer + one entry-pair.

## Investigation Trail

- **Atomicity:** injected a fault after the full move; row counts identical before/after (seed only:
  transfers=1, entries=2); balance 100→100 — the whole unit rolled back.
- **Idempotency:** 10 concurrent calls sharing `charge:req-42` → 1 ok + 9 idempotent_dup (23505); wallet
  debited once (balance 80); exactly one new transfer + entry-pair (transfers=2, entries=4).

## Results

**VERDICT: VALIDATED.** `AsyncSession.begin()` gives all-or-nothing (PITFALLS #10), and the
`transfers.idempotency_key UNIQUE` constraint dedupes concurrent retries to exactly one apply (SC#3).
Build note: on `23505`, SELECT + return the existing transfer (a true idempotent response), don't error.
