# Spike Manifest

## Idea

De-risk the concurrency-control and atomicity foundations of the **Phase 3 wallet /
double-entry ledger** (`accounts` / `transfers` / `entries`) on the *exact* Phase 3 stack
— SQLAlchemy 2.0 async + asyncpg + Postgres 16 (testcontainers) — so Phase 3 planning can
choose a wallet-debit locking strategy with empirical evidence and lock in the invariants
that ROADMAP Success Criteria **SC#2** (50 concurrent transfers, exact balance, zero drift,
`CHECK (balance >= 0)`) and **SC#3** (idempotent transfers) demand.

Primary references: `.planning/research/STACK.md` §3 (locked schema §3.2), `.planning/research/PITFALLS.md`
#1 (race), #4 (Decimal), #5 (idempotent settlement), #10 (single-transaction boundary).

## Requirements

Design decisions to carry into the Phase 3 build (updated as spikes validate them):

- Money is `Decimal` + `NUMERIC(18,4)` end-to-end — never float (PITFALLS #4; locked Phase 1).
- Schema = `accounts` / `transfers` / `entries` per STACK §3.2 with **UUID** PKs (ARCHITECTURE.md
  BIGINT model is SUPERSEDED). `entries` are append-only and net to zero per transfer; `accounts.balance`
  is a denormalized cache whose truth is `SUM(credit) - SUM(debit)` over `entries`.
- `transfers.idempotency_key` is `UNIQUE`; duplicate keys must short-circuit, never double-apply.
- Each transfer is exactly one DB transaction (`AsyncSession.begin()`): insert transfer → insert ≥2 entries
  → mutate balances → commit, all-or-nothing (PITFALLS #10).
- **Locking strategy (DECIDED by Spike 002): `SELECT … FOR UPDATE` on the wallet row inside
  `AsyncSession.begin()`** — pessimistic 1.00× amplification vs optimistic 3.38× vs SERIALIZABLE 5.70×
  at N=50 (all correct; FOR UPDATE fastest, least wasted work). `CHECK (balance >= 0)` as DB
  defense-in-depth; keep `version` for non-hot optimistic paths. Multi-account transfers lock in
  canonical UUID order (Spike 004). Docs follow-up: reconcile STACK §3.2 rule 5 wording for Pol.

## Spikes

| #    | Name                       | Type       | Validates (Given/When/Then)                                                                                                                            | Verdict | Tags |
|------|----------------------------|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|---------|------|
| 001  | race-baseline-harness      | standard   | Given naïve read→check→write under READ COMMITTED async + N concurrent overdrafts on one wallet, when run via `asyncio.gather` on real PG, then balance corrupts (drift / negative) — proving the race + building the shared load harness | VALIDATED ✓ | concurrency, harness, race |
| 002a | lock-pessimistic-for-update| comparison | Given the same load, when the wallet row is `SELECT … FOR UPDATE` inside `AsyncSession.begin()`, then exactly affordable transfers succeed, balance ≥ 0, zero drift; measure throughput/latency | ✓ WINNER 1.00× | locking, for-update |
| 002b | lock-optimistic-version-cas| comparison | Given the same load, when `UPDATE … SET version=version+1 WHERE id=? AND version=?` + retry-on-0-rows, then same correctness; measure retry counts under contention | correct, 3.38× | locking, optimistic, cas |
| 002c | lock-serializable-retry    | comparison | Given the same load under `SERIALIZABLE`, when `40001` serialization_failure aborts a tx, then retry-with-backoff converges to the correct balance; measure abort/retry rate | correct, 5.70× | locking, serializable, retry |
| 003  | atomic-transfer-idempotency| standard   | Given transfer = insert transfer + 2 entries + balance update in one tx, when a fault is injected mid-tx, then nothing commits AND entries net to zero; and given concurrent identical `Idempotency-Key`s, then exactly one transfer/entry-pair persists | VALIDATED ✓ | atomicity, idempotency, transaction |
| 004  | deadlock-ordering          | standard   | Given two concurrent transfers touching the same two accounts in opposite order, when locks are unordered then deadlock `40P01`; when locked in canonical (UUID) order then no deadlock | VALIDATED ✓ | locking, deadlock, ordering |

**Build order (by risk):** 001 → 002a → 002b → 002c → 003 → 004.
The output of 002 is the locking-strategy recommendation that feeds the Phase 3 PLAN.
