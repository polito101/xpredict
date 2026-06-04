---
phase: 03-wallet-double-entry-ledger
plan: 01
subsystem: database
tags: [ledger, double-entry, postgres, sqlalchemy, alembic, numeric, immutability, idempotency, money]

# Dependency graph
requires:
  - phase: 01-scaffold-foundations
    provides: "Money alias (NUMERIC(18,4)), money-column lint gate, audit_log immutability trigger + REVOKE pattern, tenant_id ghost convention, testcontainers engine/async_session fixtures, alembic env.py"
  - phase: 02-auth-identity
    provides: "0002_phase2_auth migration (down_revision anchor), UUID PK dual-default pattern (RefreshToken), users table for future actor_user_id / owner_id FKs"
provides:
  - "accounts / transfers / entries double-entry ledger schema (UUID PKs, NUMERIC(18,4) money, version column, tenant_id ghost)"
  - "Alembic migration 0003 (single head off 0002): schema + immutability + CHECK + seeded system accounts"
  - "Account / Transfer / Entry ORM models with Mapped[Money]"
  - "Wallet constants (PLAY_USD, owner/kind/transfer/direction literals, house_promo/house_revenue UUID singletons)"
  - "Wallet exceptions (InsufficientBalance, UserToUserTransferForbidden)"
  - "Wave-0 schema-layer test scaffold (tenant_id default, CHECK>=0, append-only immutability, idempotency UNIQUE, seeded singletons) + funded_wallet fixture"
affects: [wallet-service, recharge, wallet-reads, reconciliation, bets, settlement, 03-02, 03-03, 03-04, 03-05, 03-06, phase-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared deny-trigger function (raise_ledger_immutable) generalized across multiple immutable tables — extends the single-table Phase 1 audit_log pattern"
    - "System-account UUID singletons defined in constants.py and seeded by migration (ON CONFLICT DO NOTHING) so service + migration share one literal"
    - "JSONB column under a reserved attribute name mapped via mapped_column(\"metadata\", ...) to avoid SQLAlchemy's reserved Declarative attribute"
    - "begin_nested() savepoint isolation for integration tests whose statements intentionally raise (prevents the shared session-scoped transaction from entering an aborted state)"

key-files:
  created:
    - backend/app/wallet/constants.py
    - backend/app/wallet/exceptions.py
    - backend/app/wallet/models.py
    - backend/alembic/versions/0003_phase3_wallet_ledger.py
    - backend/tests/wallet/__init__.py
    - backend/tests/wallet/conftest.py
    - backend/tests/wallet/test_models.py
    - backend/tests/wallet/test_migration_0003.py
  modified:
    - backend/app/wallet/__init__.py
    - backend/alembic/env.py

key-decisions:
  - "house_promo / house_revenue UUIDs fixed in constants.py (a1 / a2 suffixes) so the recharge service (03-04) and settlement (Phase 5) reference singletons without a runtime lookup-by-kind"
  - "house_promo seeded with a 1,000,000,000.0000 opening balance so admin recharges (which debit it) never hit the CHECK (balance >= 0) floor in v1"
  - "funded_wallet fixture relies on the parent async_session session-rollback for cleanup — a manual DELETE FROM accounts would FAIL once an immutable entries row references the wallet (FK entries_account_id_fkey)"
  - "Integration tests that expect a DBAPIError wrap the failing statement in begin_nested() so the abort is savepoint-scoped and does not poison the shared session-scoped transaction"

patterns-established:
  - "raise_ledger_immutable() shared deny-trigger applied to transfers + entries ONLY; accounts excluded (its balance is a mutable denormalized cache)"
  - "LEDGER_IMMUTABLE_MSG defined once as a migration module constant and asserted verbatim by tests"
  - "Wallet test fixtures reuse the parent engine/async_session (no duplicate testcontainer spin-up)"

requirements-completed: [WAL-06, WAL-08]

# Metrics
duration: ~12min
completed: 2026-05-27
---

# Phase 03 Plan 01: Wallet Double-Entry Ledger Skeleton Summary

**The accounts/transfers/entries double-entry ledger — UUID schema locked to STACK §3.2, NUMERIC(18,4) money, append-only immutability (deny-trigger + REVOKE), CHECK (balance >= 0), idempotency_key UNIQUE, and seeded house_promo/house_revenue singletons — shipped as ORM models + Alembic migration 0003 + a green Wave-0 test scaffold.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-27T14:37:55Z
- **Completed:** 2026-05-27T14:49:13Z
- **Tasks:** 3
- **Files modified:** 10 (8 created, 2 modified)

## Accomplishments
- Account / Transfer / Entry ORM models with `Mapped[Money]` on `balance` + `amount` (passes the money-column lint gate), matching the validated spike harness DDL verbatim.
- Alembic migration 0003 chains cleanly off `0002_phase2_auth` (single head): creates the three tables, ports the Phase 1 audit_log immutability pattern (generalized to a shared `raise_ledger_immutable()` deny-trigger + `REVOKE UPDATE, DELETE` on transfers + entries only), adds `CHECK (balance >= 0)` and the idempotency UNIQUE, and idempotently seeds the two system accounts.
- Wallet constants + exceptions: `PLAY_USD`, owner/kind/transfer/direction literals, the two house-account UUID singletons, and the `InsufficientBalance` / `UserToUserTransferForbidden` (SC#5 firewall) exceptions.
- Wave-0 test scaffold (8 tests) proving every DB-level invariant against testcontainers Postgres: tenant_id default (PLT-01), `CHECK (balance >= 0)` → 23514 (WAL-08), transfers/entries UPDATE+DELETE blocked (WAL-06), idempotency_key UNIQUE → 23505, and the seeded singletons.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wallet constants + exceptions + Account/Transfer/Entry ORM models** — `f4e466f` (feat)
2. **Task 2: Alembic migration 0003 — schema + immutability + CHECK + seed system accounts** — `97990de` (feat)
3. **Task 3: Wave-0 test scaffold — conftest fixtures + schema/immutability/CHECK integration tests** — `23b210f` (test)

**Plan metadata:** _(this SUMMARY + STATE + ROADMAP — final docs commit)_

_Note: Task 3 carried `tdd="true"`. See "TDD Gate Compliance" below — it is a scaffold-over-existing-schema task, not a RED→GREEN implementation cycle._

## Files Created/Modified
- `backend/app/wallet/constants.py` — PLAY_USD, OWNER_*/KIND_*/TRANSFER_*/DIRECTION_* literals, HOUSE_PROMO_ACCOUNT_ID + HOUSE_REVENUE_ACCOUNT_ID UUID singletons.
- `backend/app/wallet/exceptions.py` — InsufficientBalance, UserToUserTransferForbidden.
- `backend/app/wallet/models.py` — Account (CHECK balance>=0, unique owner/kind/currency tuple, version, tenant_id ghost), Transfer (idempotency_key UNIQUE, metadata JSONB under DB col `metadata`, immutable), Entry (FK transfer/account, direction+amount CHECKs, account index, immutable); `balance` + `amount` are `Mapped[Money]`.
- `backend/alembic/versions/0003_phase3_wallet_ledger.py` — migration: schema + shared immutability trigger/REVOKE on transfers+entries + CHECK + idempotent seed of house_promo (funded) / house_revenue (0).
- `backend/app/wallet/__init__.py` — re-exports the three models for registration.
- `backend/alembic/env.py` — side-effect import of wallet models so autogenerate + tests see the tables.
- `backend/tests/wallet/__init__.py` — package marker (empty).
- `backend/tests/wallet/conftest.py` — `funded_wallet` fixture reusing the parent engine/async_session.
- `backend/tests/wallet/test_models.py` — accounts table shape / tenant_id default + seeded singletons.
- `backend/tests/wallet/test_migration_0003.py` — CHECK, immutability (UPDATE+DELETE on transfers+entries), idempotency UNIQUE.

## Decisions Made
- **Fixed house-account UUIDs in constants.py** (`...00a1` promo, `...00a2` revenue) seeded by the migration so downstream services reference singletons directly. Rationale: avoids a runtime lookup-by-kind and keeps the migration seed + service literal in one place.
- **house_promo funded with 1,000,000,000.0000** so recharge debits never underflow the balance floor in v1 (CONTEXT discretion item).
- **Migration imports the UUIDs from `app/wallet/constants.py`** rather than re-declaring them — single source of truth. (Alembic migrations may import app constants here because `env.py` already imports app modules.)
- **`metadata` column mapped via `mapped_column("metadata", JSONB, ...)`** with the Python attribute named `transfer_metadata` — `metadata` is reserved on SQLAlchemy Declarative classes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] funded_wallet fixture teardown FK violation**
- **Found during:** Task 3 (Wave-0 test scaffold)
- **Issue:** The initial `funded_wallet` fixture cleaned up with `DELETE FROM accounts WHERE id = :id`. Once a test booked an (immutable) `entries` row referencing the wallet, the teardown DELETE violated FK `entries_account_id_fkey` (the entry still references the account and entries cannot be deleted), erroring the test with an IntegrityError.
- **Fix:** Removed the teardown DELETE; the fixture now relies on the parent `async_session`'s session-scoped transaction rollback (its designed cleanup mechanism — "writes are never committed to the real DB"). Documented the rationale in the fixture docstring.
- **Files modified:** backend/tests/wallet/conftest.py
- **Verification:** `pytest tests/wallet/test_models.py tests/wallet/test_migration_0003.py -x -q` → 8 passed.
- **Committed in:** `23b210f` (Task 3 commit)

**2. [Rule 2 - Missing Critical] Savepoint isolation for raise-expecting integration tests**
- **Found during:** Task 3 (writing the immutability/CHECK/idempotency tests)
- **Issue:** The parent `async_session` is session-scoped (one shared transaction across the whole test session). A `DBAPIError` from a trigger/CHECK/UNIQUE violation leaves that transaction in a `current transaction is aborted` state, so the next test that issues SQL fails with `InFailedSQLTransactionError`. (Confirmed empirically: the pre-existing `tests/core/test_audit_immutability.py` actually fails on its 4th test under `-x` for exactly this reason — see Issues Encountered.)
- **Fix:** Every statement expected to raise is wrapped in `async with async_session.begin_nested()` so the abort is scoped to a savepoint and the outer session transaction stays usable. This is correctness-critical for the scaffold to be runnable as a suite, not just one test at a time.
- **Files modified:** backend/tests/wallet/test_migration_0003.py
- **Verification:** All 8 wallet tests pass together (not just individually).
- **Committed in:** `23b210f` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing-critical).
**Impact on plan:** Both fixes are confined to the Wave-0 test scaffold and were necessary for the suite to run correctly under the shared session-scoped fixture. No schema, model, or migration behavior changed; no scope creep.

## Issues Encountered
- **Pre-existing audit-suite fragility (out of scope, NOT fixed):** While validating the error-recovery pattern I ran `tests/core/test_audit_immutability.py -x` and found it fails on the 4th test (`test_audit_log_delete_blocked`) with `InFailedSQLTransactionError` — the 3rd test's expected `DBAPIError` aborts the shared session-scoped transaction and the 4th test's INSERT then can't run. This is a latent issue in a Phase 1/2 test file unrelated to this plan's changes; per the scope boundary I did **not** modify it, but I applied the `begin_nested()` savepoint pattern in the new wallet tests so they don't share the flaw. Recommend a follow-up to retrofit savepoints (or function-scoped savepoint isolation) into the audit suite — logged here for visibility.
- **`alembic` console-script blocked by Windows Application Control (os error 4551):** the bare `alembic` shim could not be spawned in this environment. Worked around by invoking `uv run --directory backend python -m alembic ...`, which runs cleanly. No code impact; noted for downstream plans that shell out to alembic.
- **testcontainers `ResourceWarning: unclosed socket`** prints after the suite completes — a teardown artifact of the testcontainers Docker probe (also present in the audit suite), not a test failure. The suite reports `8 passed`.

## TDD Gate Compliance
Task 3 carried `tdd="true"`. It is, by the plan's own framing, a **Wave-0 test scaffold that proves the DB-level invariants already established by Tasks 1–2** (the migration's CHECK, immutability triggers, and seed are the "implementation"). The tests therefore pass GREEN against the schema committed in Tasks 1–2 rather than following a RED-then-implement cycle — this is the intended scaffold-over-existing-schema pattern, not a skipped RED gate. Note that a genuine bug (the fixture-teardown FK violation, deviation #1) was caught and fixed by these tests during this step, so the scaffold did its job. The plan is `type: execute` (not a plan-level `type: tdd`), so the per-plan RED/GREEN/REFACTOR gate-commit sequence does not apply; the schema-creating commits (Tasks 1–2) are `feat` and the scaffold commit (Task 3) is `test`, consistent with the work performed.

## Next Phase Readiness
- The financial substrate is locked and DB-verified: every later money-touching plan (03-02 WalletService with FOR UPDATE, 03-03 registration hook, 03-04 recharge, 03-05 reads, 03-06 reconciliation, and Phase 5 bets/settlement) rides on these tables.
- `Account` / `Transfer` / `Entry` models, the `funded_wallet` fixture, and the `house_promo` / `house_revenue` constants are ready for 03-02 to build `WalletService` against.
- No blockers. The single-head migration applies via `alembic upgrade head` (exercised by the testcontainers `engine` fixture).

---
*Phase: 03-wallet-double-entry-ledger*
*Completed: 2026-05-27*

## Self-Check: PASSED

All 8 created files verified present on disk; all 3 task commits (`f4e466f`, `97990de`, `23b210f`) verified in git history. The SUMMARY file itself is present. Plan verification gates 1–5 all pass (ruff clean on app/wallet, money-lint exits 0, models import, alembic single head off 0002, `pytest tests/wallet/test_models.py tests/wallet/test_migration_0003.py -x -q` → 8 passed); non-integration regression suite 59 passed / 2 skipped.
