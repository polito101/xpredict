---
spike: 004
name: deadlock-ordering
type: standard
validates: "Given two concurrent transfers touching the same two accounts in opposite order, when locks are unordered then deadlock 40P01; when locked in canonical (UUID) order then no deadlock"
verdict: VALIDATED
related: [002]
tags: [locking, deadlock, ordering]
---

# Spike 004: Deadlock Ordering

## What This Validates

PITFALLS.md #1's last bullet: "acquire locks in a consistent order (always wallet then bet,
never the reverse) to prevent deadlocks." Settlement and multi-account transfers (debit
`user_wallet`, credit `market_liability`, credit `house_revenue`) lock more than one account,
so lock-acquisition order is a real Phase 3/5 concern.

## Research

- Postgres detects deadlocks and aborts a victim with SQLSTATE `40P01` (`deadlock_detected`).
- The canonical mitigation: impose a total order on lockable rows (here: sort account IDs) so a
  cycle can never form. Alternative: retry on `40P01` (also tested implicitly via the retry path).
- This composes with 002's chosen strategy — if FOR UPDATE wins, ordered acquisition is the rule.

## How to Run

```
<repo>\backend\.venv\Scripts\python.exe .planning\spikes\004-deadlock-ordering\run.py
```

## What to Expect

- **Unordered:** 30 concurrent bidirectional transfers ⇒ some `deadlock` outcomes.
- **Canonical order:** zero `deadlock` — every transfer locks the two rows in the same UUID order.

## Investigation Trail

- 30 concurrent bidirectional transfers between the same two accounts.
- **Unordered** locking: 6 ok / **24 deadlock** (Postgres aborted 24 victims with `40P01`).
- **Canonical** (UUID-sorted) lock order: **30 ok / 0 deadlock**.

## Results

**VERDICT: VALIDATED.** Acquiring multi-account row locks in a canonical total order eliminates
deadlocks (PITFALLS #1). Load-bearing for Phase 5 settlement (credits multiple accounts). A bounded
retry-on-`40P01` is the belt-and-suspenders fallback.
