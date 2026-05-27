---
phase: 03-wallet-double-entry-ledger
plan: 02
subsystem: payments
tags: [wallet, ledger, double-entry, sqlalchemy, postgres, for-update, idempotency, concurrency, atomicity, money, asyncio]

# Dependency graph
requires:
  - phase: 03-wallet-double-entry-ledger
    plan: 01
    provides: "accounts/transfers/entries ORM models, migration 0003 (CHECK balance>=0, immutability trigger+REVOKE, idempotency_key UNIQUE), wallet constants (house_promo/house_revenue UUIDs, owner/kind/direction literals), InsufficientBalance/UserToUserTransferForbidden exceptions, funded_wallet fixture, begin_nested savepoint test pattern"
  - phase: 01-scaffold-foundations
    provides: "Mapped[Money] NUMERIC(18,4) + money-column lint gate, AuditService caller-owned-transaction contract, testcontainers engine/async_session fixtures, lazy _get_engine/_get_session_maker factories"
provides:
  - "WalletService — the ONLY ledger writer: create_wallet (caller-owned tx), _post_transfer (atomic double-entry), transfer (FOR UPDATE + balance-checked debit->credit), recharge (house->user, idempotent), get_balance"
  - "Race-safe transfer engine (WAL-07): pessimistic SELECT ... FOR UPDATE inside one session.begin(), canonical UUID lock order, 23505->return-existing idempotency"
  - "SC#2 signature concurrent gate proven on production code (50 concurrent overdraft transfers, drift 0, balance exact, overdraw rejected)"
  - "Idempotency + atomicity integration tests (duplicate key credited once; fault mid-tx full rollback)"
affects: [03-03, 03-04, 03-05, 03-06, phase-05, recharge, registration, wallet-reads, reconciliation, bets, settlement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "WalletService as the single ledger writer (stateless static/class methods, mirrors AuditService) — every value movement funnels through one place so the FOR UPDATE / double-entry / idempotency / lock-order invariants hold in exactly one location (WAL-07)"
    - "Caller-owned-transaction contract for create_wallet (add+flush only, never commit) — the registration override owns the single commit so user+wallet land in one tx (SC#1), mirroring AuditService.record"
    - "Concurrency integration tests open their OWN committed sessions via _get_session_maker() (true concurrency cannot share the rollback async_session); fresh unique-owner accounts + idempotency-key/account-scoped reads isolate the immutable, un-deletable ledger without teardown"
    - "Opening double-entry seed (genesis->wallet credit) so SUM(entries) == balance at t0 and drift is genuinely measurable (port of harness.seed_ledger) — a bare cache write would make drift a seeding artifact"
    - "global_entry_sum measured over ALL entries as a permanent global invariant (every transfer nets to zero) — isolation-safe across accumulated rows"

key-files:
  created:
    - backend/app/wallet/service.py
    - backend/tests/wallet/test_concurrent_transfers.py
    - backend/tests/wallet/test_idempotency.py
    - backend/tests/wallet/test_atomicity.py
  modified: []

key-decisions:
  - "Added a public WalletService.transfer (the race-safe, balance-checked debit->credit primitive) that recharge specializes and Phase 5 bet-placement reuses — required to drive the SC#2 overdraft gate on production code (recharge alone debits the billion-funded house_promo and never rejects)"
  - "recharge resolves the target wallet INSIDE session.begin() — a SELECT before begin() autobegins an implicit tx and makes begin() raise InvalidRequestError"
  - "create_wallet opens the wallet at balance=0 (funding is a subsequent recharge, not an opening grant) so the ledger truth SUM(entries) stays consistent from creation"
  - "Idempotency catches IntegrityError (ORM subclass of DBAPIError) and reads .orig.sqlstate == '23505' (RESEARCH Pitfall 2) — the begin() block rolls back, then a fresh SELECT returns the existing transfer (true idempotent response, no double-credit)"

patterns-established:
  - "FOR UPDATE row lock inside one session.begin() unit of work is the PRIMARY concurrency guard; CHECK (balance >= 0) is the DB-level net; InsufficientBalance is raised in front of the DB so callers get a domain error not a raw 23514"
  - "Canonical UUID lock order sorted((a,b), key=str) before any mutate on every multi-account move (recharge + transfer) — Spike 004, prevents 40P01 deadlock"
  - "Fault-injection rollback test monkeypatches _post_transfer to do the real work then raise inside transfer()'s begin() block — tests the production transaction boundary, not a synthetic one"

requirements-completed: [WAL-07]

# Metrics
duration: ~8min
completed: 2026-05-27
---

# Phase 03 Plan 02: WalletService Race-Safe Transfer Engine Summary

**`WalletService` — the only ledger writer — ported verbatim from the validated spike harness: pessimistic `SELECT ... FOR UPDATE` inside one `session.begin()`, atomic paired-entry double-entry, `23505`→return-existing idempotency, and canonical UUID lock order; proven on production code by the SC#2 signature gate (50 concurrent overdraft transfers → drift 0, balance exact, overdraw rejected).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-27T14:57:02Z
- **Completed:** 2026-05-27T15:05:27Z
- **Tasks:** 2
- **Files modified:** 4 (4 created, 0 modified)

## Accomplishments
- `WalletService` (`app/wallet/service.py`, 363 lines) — the single race-safe ledger writer (WAL-07), a faithful ORM port of the empirically-validated harness (`_spend_once`/`spend`/`locked_transfer`):
  - `create_wallet(session, *, user)` — `add`+`flush` only, NEVER commits (caller-owned-transaction contract for SC#1, mirrors `AuditService.record`).
  - `_post_transfer(...)` — the atomic double-entry move: a transfer row + two `Entry` legs (debit + credit, both positive, netting to zero) + both balance-cache updates via ORM `update(Account)`.
  - `transfer(...)` — the public race-safe, balance-checked debit→credit primitive: canonical-order `FOR UPDATE` locks, locked-balance read → `InsufficientBalance` on overdraw, then `_post_transfer`.
  - `recharge(...)` — house→user funding: canonical-order locks, idempotent via `IntegrityError`/`23505`→return-existing, `payment_provider="stripe"`→`NotImplementedError` (SC#6 stub), `amount > 0` defense-in-depth.
- **SC#2 signature gate green on production code:** `test_50_concurrent_overdraft` reproduces the harness `LoadResult.correct` invariant (`final_balance >= 0 AND drift == 0 AND final_balance == opening - per_amount*succeeded AND global_entry_sum == 0`) — 25 succeed, 25 rejected, zero ledger drift.
- **Idempotency + atomicity proven:** duplicate `idempotency_key` (sequential and 10-concurrent) returns the same transfer id and credits the wallet exactly once; a fault injected after the writes but before commit rolls back the whole unit of work (zero transfers, zero entries, balances intact).
- Full `tests/wallet` suite (8 schema scaffold + 4 new service tests) = 12 passed against testcontainers Postgres 16; non-integration regression suite = 59 passed / 2 skipped; `ruff check app/wallet/` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: WalletService — recharge/transfer engine (FOR UPDATE, idempotency, canonical lock order)** — `21a8760` (feat)
2. **Task 2: SC#2 concurrent gate + idempotency + atomicity integration tests** — `0ce1263` (test)

**Plan metadata:** _(this SUMMARY + STATE + ROADMAP + REQUIREMENTS — final docs commit)_

_Note: Both tasks carried `tdd="true"`. See "TDD Gate Compliance" below — Task 1 is the implementation, Task 2 the behavioral test suite that exercises it; the genuine RED→GREEN behavioral proof lives in Task 2 (and surfaced two real bugs in the Task 1 service, fixed as deviations)._

## Files Created/Modified
- `backend/app/wallet/service.py` — `WalletService`: `create_wallet` (caller-owned tx), `_post_transfer` (atomic double-entry), `transfer` (FOR UPDATE + balance-checked debit→credit), `recharge` (house→user, idempotent, stripe stub), `get_balance` / `_resolve_user_wallet_id` (minimal read helpers; full read shaping is 03-05). `SQLSTATE_UNIQUE_VIOLATION = "23505"` + `PROVIDER_HOUSE`/`PROVIDER_STRIPE` module constants.
- `backend/tests/wallet/test_concurrent_transfers.py` — the SC#2 signature gate: 50 concurrent `WalletService.transfer` via `asyncio.gather`, `_Outcome` mirror of `harness.LoadResult`, opening double-entry seed so drift is measurable.
- `backend/tests/wallet/test_idempotency.py` — `test_idempotent_recharge_returns_same_transfer` (sequential) + `test_concurrent_same_key_one_applied` (10 concurrent): same transfer id, one entry-pair, credited once.
- `backend/tests/wallet/test_atomicity.py` — `test_fault_mid_transaction_rolls_back`: monkeypatches `_post_transfer` to do the real work then raise inside `transfer()`'s `begin()` block; asserts full rollback (zero rows, balances intact).

## Decisions Made
- **Added a public `WalletService.transfer`** (not enumerated in Task 1's action list, but required by the plan's must_haves debit truth — "WalletService debits a wallet via SELECT ... FOR UPDATE inside one transaction" — and by the SC#2 gate). `recharge` alone debits the billion-funded `house_promo`, which never rejects an overdraw, so it cannot reproduce the wallet-overdraft race on production code. `transfer` is the general race-safe primitive `recharge` specializes and Phase 5 bet-placement reuses; the SC#2 gate drives it directly. (Deviation Rule 2.)
- **`recharge` resolves the target wallet inside `session.begin()`.** Issuing the resolve SELECT before `begin()` autobegins an implicit transaction, so `begin()` then raised `InvalidRequestError: A transaction is already begun on this Session`. (Deviation Rule 1.)
- **Concurrency tests use their own committed sessions** (`_get_session_maker()`), not the shared rollback `async_session` — true concurrency requires distinct connections. Because `transfers`/`entries` are immutable (deny-trigger blocks DELETE for everyone, including the table owner), there is no teardown: each test seeds fresh accounts with unique `owner_id` and scopes all assertions to those account ids / the run's `idempotency_key`. `global_entry_sum` is measured over ALL entries as a permanent invariant (every transfer nets to zero), so accumulated rows from prior tests keep it at 0 — isolation without deletion.
- **Opening balance seeded via a proper opening double-entry** (genesis→wallet credit), not a bare cache write, so `SUM(entries for wallet) == balance` at t0 and `drift` measures real divergence rather than a seeding gap (port of `harness.seed_ledger`).
- **`create_wallet` opens at `balance=0`.** Funding (if any) is a subsequent recharge, keeping the ledger truth `SUM(entries)` consistent from the moment of creation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added the public `WalletService.transfer` debit primitive**
- **Found during:** Task 2 (writing the SC#2 concurrent overdraft gate)
- **Issue:** The plan's must_haves require "WalletService debits a wallet via SELECT ... FOR UPDATE inside one transaction" and the SC#2 gate fires "50 concurrent `WalletService` transfers" with overdraw rejection — but Task 1's enumerated methods (`create_wallet`, `_post_transfer`, `recharge`) expose no public wallet-debit path. `recharge` debits `house_promo` (opening balance 1,000,000,000), which never hits the balance floor, so it cannot reproduce the wallet-overdraft race on production code. Driving the gate through raw test-only SQL would have proven the harness, not the service.
- **Fix:** Added `WalletService.transfer(session, *, kind, debit_account_id, credit_account_id, amount, actor_user_id=None, idempotency_key=None, reason=None)` — the general race-safe, balance-checked debit→credit primitive (canonical-order `FOR UPDATE`, locked-balance read → `InsufficientBalance`, then `_post_transfer`). `recharge` is now conceptually a specialization of it; Phase 5 bet-placement reuses it.
- **Files modified:** backend/app/wallet/service.py
- **Verification:** `test_50_concurrent_overdraft` green (25 succeed / 25 rejected, drift 0); ruff clean; `transfer` signature asserted.
- **Committed in:** `0ce1263` (Task 2 commit)

**2. [Rule 1 - Bug] `recharge` autobegin collision with `session.begin()`**
- **Found during:** Task 2 (running the idempotency tests)
- **Issue:** `recharge` resolved the target wallet id via `_resolve_user_wallet_id` (a SELECT) BEFORE entering `async with session.begin()`. On a fresh session that first SELECT autobegins an implicit transaction, so `session.begin()` then raised `sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session` — every recharge failed before doing any work.
- **Fix:** Moved the `_resolve_user_wallet_id` call INSIDE the `session.begin()` block (the resolve is a read that legitimately belongs to the same unit of work). `transfer` was already correct (its first statement is the FOR UPDATE select inside `begin()`), which is why the concurrent gate passed before this fix.
- **Files modified:** backend/app/wallet/service.py
- **Verification:** `test_idempotent_recharge_returns_same_transfer` + `test_concurrent_same_key_one_applied` green (same transfer id, one entry-pair, credited once).
- **Committed in:** `0ce1263` (Task 2 commit)

**3. [Rule 1 - Bug] `staticmethod.__func__` unwrap in the atomicity test**
- **Found during:** Task 2 (running the atomicity fault-injection test)
- **Issue:** `WalletService._post_transfer.__func__` raised `AttributeError: 'function' object has no attribute '__func__'` — class access on a `@staticmethod` already yields the plain underlying function, so there is no descriptor to unwrap.
- **Fix:** Referenced `WalletService._post_transfer` directly (it is already the callable function on class access).
- **Files modified:** backend/tests/wallet/test_atomicity.py
- **Verification:** `test_fault_mid_transaction_rolls_back` green (full rollback, zero rows, balances intact).
- **Committed in:** `0ce1263` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (1 missing-critical, 2 bugs).
**Impact on plan:** All three were necessary to make the plan's own must_haves and verification pass on production code. The `transfer` primitive is plan-mandated functionality the Task 1 enumeration under-specified, not scope creep; the other two are bugs in the Task 1 service / Task 2 test caught by running the suite. No schema, migration, or external-contract change; the `recharge`/`create_wallet` signatures are exactly as the plan specified.

## Issues Encountered
- **Integration tests need the `engine` fixture for its side effects.** The three new test files open their own committed sessions via `_get_session_maker()` and so do not request `async_session` directly — but `_get_session_maker()`/`_get_engine()` are lazy singletons that, without the `engine` fixture, connect to the absent default `localhost:5432` (asyncpg `ConnectionRefusedError`). The `engine` fixture (session-scoped) starts the testcontainer, runs `alembic upgrade head`, rewrites `DATABASE_URL`, and clears the factory caches. Resolved by adding a small autouse `_require_testcontainer(engine)` fixture to each test module so those side effects run before the production factory is used.
- **Immutable ledger means no test teardown by deletion.** `transfers`/`entries` carry a `BEFORE UPDATE OR DELETE` deny-trigger that fires `FOR EACH ROW` regardless of role (not just the REVOKE), so committed rows from a concurrency test cannot be deleted. Handled by per-test fresh accounts (unique `owner_id`) + assertion scoping (by account id / `idempotency_key`) + the `global_entry_sum`-over-all-entries permanent invariant — true isolation without ever deleting a ledger row. (Same constraint the 03-01 `funded_wallet` fixture documents.)
- **`ResourceWarning: unclosed socket`** prints after the suite — the known testcontainers Docker-probe teardown artifact (also present in the 03-01 + audit suites), not a test failure; the suite reports all green.

## TDD Gate Compliance
Both tasks carried `tdd="true"`. The plan splits the feature so that **Task 1 is the implementation** (`WalletService`) and **Task 2 is the behavioral test suite** that exercises it (the SC#2 concurrent gate + idempotency + atomicity). The genuine behavioral proof therefore lives in Task 2 and it did its job: running the suite surfaced two real production bugs in the Task 1 service (the `recharge` autobegin collision and — by exposing the need — the missing `transfer` debit primitive), both fixed as deviations before the suite went green. The plan is `type: execute` (not a plan-level `type: tdd`), so the per-plan RED/GREEN/REFACTOR gate-commit sequence does not apply; commits are `feat` (Task 1 implementation) and `test` (Task 2 suite), consistent with the work performed. No test was skipped and no behavioral assertion passed without first having driven the production service.

## Known Stubs
- `WalletService.recharge(payment_provider="stripe")` raises `NotImplementedError("stripe recharge is a v2 stub")` — an **intentional, plan-mandated stub (SC#6)** so the method signature is final now and 03-04/03-05 need no breaking refactor when Stripe arrives in v2. The `stripe_recharge_enabled` feature flag is already seeded `FALSE` (Phase 1). This is not a goal-blocking stub: v1 recharge funds from the house and is fully implemented.
- `get_balance` / `_resolve_user_wallet_id` are minimal read-only helpers; the full read surface (balance shaping, paginated transactions, money-as-string serialization SC#4) is owned by Plan 03-05 as the plan specifies. No empty/mock data flows anywhere — `get_balance` reads the real cache.

## Next Phase Readiness
- The race-safe transfer engine (WAL-07) is locked and DB-verified on production code — the technical heart of the phase. Downstream plans consume it directly:
  - **03-03 (registration hook):** calls `WalletService.create_wallet(session, *, user)` inside the user-creation transaction (SC#1); the caller-owned-transaction contract is honored and grep-verifiable (no `commit(` in the method).
  - **03-04 (recharge endpoint):** wraps `WalletService.recharge(...)` (signature final, idempotency + stripe stub ready) behind the admin route + `Idempotency-Key` header.
  - **03-05 (wallet reads):** owns `get_balance`/`get_transactions` shaping + SC#4 money-as-string; the minimal read helpers here are the seam.
  - **03-06 (reconciliation):** asserts `balance == SUM(entries)` per account — the invariant every `transfer`/`recharge` already maintains and the tests measure as `drift == 0`.
  - **Phase 5 (bets/settlement):** reuses `WalletService.transfer` (and `_post_transfer`) for stake debits + payout credits.
- No blockers.

---
*Phase: 03-wallet-double-entry-ledger*
*Completed: 2026-05-27*

## Self-Check: PASSED

All 4 created files verified present on disk (`backend/app/wallet/service.py` + the three `backend/tests/wallet/test_*.py`); both task commits (`21a8760`, `0ce1263`) verified in git history; this SUMMARY file is present. Plan verification gates all pass: `ruff check app/wallet/` clean, `pytest tests/wallet -q` → 12 passed (8 schema scaffold + 4 service), `pytest -m "not integration" -q` → 59 passed / 2 skipped, and the SC#2 signature gate `test_50_concurrent_overdraft` is green (drift 0, balance exact, 25/25 succeed/reject).
