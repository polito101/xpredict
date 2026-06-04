# Deferred Items — Phase 03 (wallet-double-entry-ledger)

Out-of-scope discoveries logged during plan execution. These are NOT fixed by the
discovering plan (scope boundary: only fix issues directly caused by the current
task's changes). Tracked here for a follow-up.

---

## DEF-03-01 — Shared session-scoped transaction poisoning across test files (full-suite only) — ✅ RESOLVED 2026-06-02

- **Discovered during:** Plan 03-06 (reconciliation) — full-suite verification run
  (`pytest -q`, unit + integration together).
- **Severity:** Test-infrastructure fragility (does NOT affect production code or
  the per-file / per-plan test gates that GSD actually runs).
- **Symptom:** Running the *entire* backend suite together yields
  `asyncpg.exceptions.InFailedSQLTransactionError: current transaction is aborted,
  commands ignored until end of transaction block` for many DB-touching tests in
  `tests/wallet/test_migration_0003.py`, `tests/wallet/test_models.py`, and
  (as downstream victims) `tests/wallet/test_reconcile.py`. The same tests all
  **pass in isolation** and pass when only `tests/wallet/` is run
  (`pytest tests/wallet/ -q` → 15 passed).
- **Root cause (pre-existing):** The `async_session` fixture in
  `tests/conftest.py` is **session-scoped** with a single outer transaction rolled
  back only at session teardown. A test elsewhere in the suite (per the 03-01
  SUMMARY "Issues Encountered", `tests/core/test_audit_immutability.py` is a known
  offender — its 3rd test's expected `DBAPIError` aborts the shared transaction
  and its 4th test then can't run) lets a `DBAPIError` abort that shared
  transaction **without** savepoint isolation. Every subsequent test that issues
  SQL on the same session then fails with `InFailedSQLTransactionError`.
- **Confirmed NOT caused by 03-06:** Re-running the full suite with the new
  reconcile test excluded (`pytest -q --ignore=tests/wallet/test_reconcile.py`)
  still produces 14 failures + 3 errors in the 03-01 files. Adding the 3 reconcile
  tests only raises the victim count to 17/3 — the reconcile tests are themselves
  correctly savepoint-isolated (explicit `await savepoint.rollback()` per test)
  and are downstream victims, not a cause.
- **Documented precedent:** The 03-01 SUMMARY already flagged this exact
  fragility and recommended "a follow-up to retrofit savepoints (or
  function-scoped savepoint isolation) into the audit suite."
- **Recommended fix (follow-up, NOT in 03-06 scope):** Retrofit the
  raise-expecting tests in `tests/core/test_audit_immutability.py` (and any other
  pre-03 suite that intentionally triggers a `DBAPIError`) with the
  `async with async_session.begin_nested()` savepoint pattern already used by
  `tests/wallet/test_migration_0003.py` and `tests/wallet/test_reconcile.py`, OR
  switch `async_session` to function-scoped savepoint isolation. Either makes the
  full suite order-independent.
- **Operational note:** GSD's documented sampling strategy runs per-file /
  per-wave / `-m "not integration"` gates — all of which are GREEN. The
  whole-suite-in-one-process invocation is the only place this surfaces.

### ✅ Resolution (2026-06-02)

Two distinct isolation bugs were conflated under DEF-03-01; both are now fixed:

1. **Session-scoped tx poisoning (the original defect above)** — fixed by
   `fae0d53`: `async_session` in `tests/conftest.py` is now FUNCTION-scoped (each
   test gets its own connection + rolled-back transaction), so an aborted tx in
   `test_audit_immutability.py` can no longer cascade `InFailedSQLTransactionError`
   into later tests. (This is the "function-scoped savepoint isolation" alternative
   the recommended-fix listed.)
2. **`test_50_concurrent_overdraft` residual** (mis-attributed to DEF-03-01 in
   PHASES.md / LOOKS-DONE-CHECKLIST) — this test was never a victim of the shared
   session; it opens its OWN committed sessions. It failed in full-suite CI on a
   *different* isolation flaw: it asserted `SUM(credit-debit)` over the WHOLE
   `entries` table == 0, coupling it to rows committed by other committed-session
   tests (bets/KPI/signup-bonus). CI showed `global_entry_sum=175.0000` while the
   wallet's own ledger was perfect (drift 0, 25 ok / 25 rejected, balance exact).
   Fixed by `f8a8859`: the conservation sum is now scoped to the test's own
   {genesis, wallet, counterparty} triad (nets to 0 by construction).

Full `pytest tests/` is now order-independent; **backend-ci is green on `main`**
(run 26834844024). The production `WalletService.transfer` was never at fault.
