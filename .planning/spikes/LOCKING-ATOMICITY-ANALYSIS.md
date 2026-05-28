# Phase 3 Wallet/Ledger — Locking & Atomicity: Technical Analysis

> **STATUS — empirically confirmed.** Spikes 001–004 were executed against Postgres 16 (testcontainers,
> Docker 29.4.3) on the exact Phase 3 stack (SQLAlchemy 2.0.43 async + asyncpg). All verdicts are in and
> recorded in each spike README + MANIFEST.md; the §5 recommendation is **confirmed by the spike 002
> numbers** (§4/§9). Reproduce: `uv run --directory backend python .planning\spikes\00N-*\run.py`.

## 1. The decision this resolves

Phase 3 **SC#2** requires: *50 concurrent "spend X" transfers on one wallet → final balance exact,
zero ledger drift, `CHECK (balance >= 0)` rejects overdraw.* There is a **documentation conflict**
about how to guard the wallet debit:

- `STACK.md` §3.2 **rule 5** → **optimistic** locking: `UPDATE … SET version = version+1 WHERE id=? AND version=?`; 0 rows ⇒ retry.
- `PITFALLS.md` #1 **and** `ROADMAP.md` Phase 3 ("via `FOR UPDATE`") → **pessimistic** `SELECT … FOR UPDATE`.

The spike exists to settle this empirically. SERIALIZABLE + retry is the third credible candidate
(PITFALLS #1 explicitly suggests "consider SERIALIZABLE for bet placement").

## 2. Invariants that are LOCKED (not under debate)

- `accounts` / `transfers` / `entries`, **UUID** PKs (ARCHITECTURE.md BIGINT model SUPERSEDED).
- Money is `Decimal` + `NUMERIC(18,4)` end-to-end; never float (PITFALLS #4 — locked in Phase 1).
- `entries` are append-only and **net to zero** per transfer; `accounts.balance` is a **denormalized
  cache** whose truth is `SUM(credit) - SUM(debit)` over `entries` (reconciled nightly — SC#7).
- `transfers.idempotency_key` is `UNIQUE`. One DB transaction per transfer.

## 3. Why the naive pattern corrupts (spike 001 demonstrates)

The danger is the application-level `read balance → decide in Python → write` sequence under the
default `READ COMMITTED` isolation, run concurrently by async handlers:

| Variant | Write style | Failure | Severity |
|---|---|---|---|
| `naive_lost_update` | `balance = :python_computed` (stale read) | **Lost update** → drift (balance ≠ ledger), **money created** | CRITICAL |
| `naive_overdraw` (CHECK off) | `balance = balance - :amount` (atomic) | **Negative balance** | CRITICAL |
| `naive_overdraw` (CHECK on) | atomic decrement + `CHECK (balance>=0)` | DB saves *this* single-row case | (nuance) |

**Key nuance for the design:** an atomic single-statement decrement + `CHECK` *does* protect a bare
balance column. But it does **not** generalize — the moment the transaction makes a decision from the
read value (bet payout computed from read odds, conditional inserts across multiple tables, multi-row
balance moves), the stale read corrupts again. So the wallet debit **must** be guarded by a real
concurrency-control mechanism, and `CHECK (balance >= 0)` stays as defense-in-depth, not the primary guard.

## 4. The three candidates (mechanism + analysis)

| Dimension | `FOR UPDATE` (pessimistic) | version CAS (optimistic) | `SERIALIZABLE` + retry |
|---|---|---|---|
| Mechanism | Row lock on the wallet `SELECT`; concurrent writers block until commit | No lock; conflict detected by affected-rowcount on `WHERE version=?` | SSI; Postgres aborts conflicting txns with SQLSTATE `40001` |
| Correctness | Trivial — serialized at the row; computed write is safe | Needs the retry loop to be correct | Automatic for **all** invariants in the tx, not just balance |
| Contention on ONE hot row (expected) | Writers queue; ~**1×** attempts | **Retry storms** — O(N)…O(N²) attempts as everyone targets the same `version` | Abort+retry; abort rate rises with contention |
| Latency profile | Lock-wait latency, predictable | Low until contention, then tail-latency from retries | Mid; retry on abort |
| App complexity | Lowest (one `with_for_update`) | Higher (retry policy, max-attempts, surface 503) | Global retry wrapper on every serializable tx |
| Deadlock exposure | Yes on multi-account moves → needs canonical lock ordering (§8) | Lower (no held locks) | Possible; SSI may abort |
| Best fit | A single hot contended row with a strict invariant (**our wallet**) | Low contention, or contention spread across many rows | Multi-table / multi-invariant units of work |

These rows marked "expected" are the ones spike **002** measures (`wall ms` + attempt amplification).

## 5. Recommendation (confirmed by spike 002)

1. **Wallet debit → pessimistic `SELECT … FOR UPDATE` inside `AsyncSession.begin()`.** A user wallet is
   a *single hot row* with a strict balance invariant — the textbook FOR UPDATE case. Lowest retry
   amplification, simplest code, deterministic. This matches PITFALLS #1 + ROADMAP. **Confirmed by spike
   002 at N=50:** FOR UPDATE 1.00× / 1140 ms vs optimistic CAS 3.38× / 1325 ms vs SERIALIZABLE 5.70× /
   1488 ms — all three correct, FOR UPDATE fastest with the least wasted work (everyone else fights over one row).
2. **Keep `CHECK (balance >= 0)`** as a DB-level last line of defense (SC#2 requires it anyway).
3. **Keep the `version` column** for optimistic concurrency on *non-hot* aggregates / future use, but it
   is **not** the primary wallet-debit guard. → This means **reconciling STACK §3.2 rule 5** so the wallet
   debit is FOR UPDATE-first; flag to Pol as a docs-alignment item.
4. **SERIALIZABLE** is held in reserve for *multi-invariant* units (e.g., settlement touching many bets
   in Phase 5) if consistent FOR UPDATE ordering becomes unwieldy there — decide per-service, not globally.

## 6. Atomicity — one transaction per transfer (PITFALLS #10)

Pattern (spike 003 part 1 proves it via mid-transaction fault injection):

```
async with session.begin():          # one unit of work
    insert transfers(row)             # the business event
    insert entries(debit, credit)     # ≥2 lines, net to zero
    update accounts.balance (+ version)   # guarded per §5
    # commit on clean exit; ANY exception ⇒ full rollback (no orphan bet/ledger)
```

This is the exact shape **Phase 5 bet placement** reuses (lock wallet → check → insert bet → insert
paired entries → update cache → commit). FK `entries.transfer_id → transfers.id` makes an orphan entry
impossible.

## 7. Idempotency (SC#3)

`transfers.idempotency_key UNIQUE`. Two concurrent calls with the same key: the second's transfer
`INSERT` raises `23505` → the transaction aborts → its balance change never applies (spike 003 part 2
proves: 1 applied, K−1 deduped, balance debited once). **Implementation note for the build:** on `23505`,
the service should `SELECT` the existing transfer by key and return it (a *true* idempotent response —
same transfer id, HTTP 200), not surface an error. The admin-recharge endpoint (SC#3) is the first consumer.

## 8. Deadlock ordering (PITFALLS #1)

Any transfer that locks **more than one** account (settlement: debit `market_liability`, credit
`user_wallet`, credit `house_revenue`) must acquire row locks in a **canonical total order** (e.g.,
sort account IDs) so a lock cycle can never form. Spike 004 proves: unordered opposite-direction
transfers deadlock (`40P01`); canonical ordering → zero deadlocks. A bounded retry-on-`40P01` is the
belt-and-suspenders fallback. This rule is load-bearing in **Phase 5 settlement**, not just Phase 3.

## 9. Spike results (executed — Postgres 16 / SQLAlchemy 2.0.43 async / asyncpg)

| Spike | Verdict | Evidence |
|---|---|---|
| 001 race-baseline | VALIDATED | naive lost_update → drift=380 + money created; overdraw → balance=−300; CHECK+atomic protects only the single-row case |
| 002 locking | VALIDATED · **FOR UPDATE wins** | all 3 correct at N=50; amplification 1.00× / 3.38× / 5.70× (FOR UPDATE / optimistic / SERIALIZABLE) |
| 003 atomicity+idempotency | VALIDATED | fault → full rollback (0 rows persisted); 10 concurrent same-key → 1 applied + 9 deduped |
| 004 deadlock-ordering | VALIDATED | unordered → 24/30 deadlock (40P01); canonical UUID order → 0 deadlock |

Next: carry the confirmed §5 recommendation into `/gsd-plan-phase 3`.

---
*Authored during the Phase 3 ledger concurrency spike. Empirical sections pending spike execution
(blocked on Docker daemon only). Run: `uv run --directory backend python .planning\spikes\00N-*\run.py`.*
