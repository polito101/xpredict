---
phase: 03-wallet-double-entry-ledger
plan: 06
subsystem: testing
tags: [celery, redbeat, reconciliation, sentry, structlog, postgres, sqlalchemy, asyncio, money, observability]

# Dependency graph
requires:
  - phase: 03-wallet-double-entry-ledger
    provides: "03-01 ledger schema (accounts/transfers/entries, NUMERIC(18,4) balance cache + immutable entries, seeded house_promo/house_revenue singletons, funded_wallet fixture, wallet constants)"
  - phase: 01-scaffold-foundations
    provides: "Celery app + RedBeat scheduler + Sentry init signals + structlog config (celery_app.py, core/sentry.py, core/logging.py); testcontainers engine/async_session fixtures"
provides:
  - "reconcile_wallets nightly Celery task (sync body wrapping asyncio.run(_reconcile_async)) — per-account SUM(credit)-SUM(debit) vs accounts.balance drift detector"
  - "RedBeat schedule entry reconcile-wallets-nightly (crontab 03:00 UTC) appended to celery_app.conf.beat_schedule"
  - "Late-import task-registration pattern in celery_app.py so worker/beat register tasks declared in separate modules (Pitfall 5 reachability)"
  - "SC#7 integration test: clean ledger -> INFO reconcile_clean + no Sentry; injected balance drift -> CRITICAL wallet_ledger_drift + sentry capture_message"
  - "house_promo exclusion from reconciliation (deliberate non-ledger-backed seed) to prevent nightly false-positive alerts"
affects: [phase-05, settlement, observability, reconciliation, recharge]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sync Celery task body wrapping asyncio.run(_reconcile_async()) — Celery 5.5 has no native async (RESEARCH Pattern 6 / STACK §1.4); opens a fresh AsyncSession so it never piggybacks on the FastAPI event loop"
    - "Late (bottom-of-module) import of a periodic-task module inside celery_app.py to register a @celery_app.task declared elsewhere, resolving the reconcile<->celery_app circular import (celery_app fully constructed by then)"
    - "_reconcile_async(session=None) accepts an optional injected session so integration tests can reconcile against the rolled-back testcontainer transaction (uncommitted seeded rows a fresh session-maker session cannot see)"
    - "structlog.testing.capture_logs() for asserting log event name + level in tests (bypasses the filtering bound logger so INFO and CRITICAL are both captured)"
    - "Explicit savepoint rollback (begin_nested() + await savepoint.rollback() in finally) + account-specific assertions for tests on the shared session-scoped fixture — order-independent under cross-file row leakage"

key-files:
  created:
    - backend/app/wallet/reconcile.py
    - backend/tests/wallet/test_reconcile.py
  modified:
    - backend/app/celery_app.py

key-decisions:
  - "Nightly schedule = crontab(hour=3, minute=0) UTC (Claude's Discretion — low-traffic window per the plan objective)"
  - "Exclude the seeded house_promo singleton from the drift scan (its 1e9 opening balance is a deliberate non-ledger-backed seed); reconciling it would emit a nightly false CRITICAL + Sentry alert and defeat PLT-09. Every other account (user wallets AND house_revenue) is fully reconciled."
  - "Register the task via a bottom-of-celery_app.py import of app.wallet.reconcile (not autodiscover_tasks, whose default related_name='tasks' would miss a module named reconcile)"
  - "Drift is reported via sentry_sdk.capture_message(level='error') per drifting account (not capture_exception) so the alert carries the account/balances inline without a synthetic stack"

patterns-established:
  - "Reconciliation reads via SQLAlchemy func.coalesce(func.sum(case((Entry.direction=='credit', Entry.amount), else_=-Entry.amount)), 0) grouped by account — the validated harness _measure aggregate shape, LEFT OUTER JOIN so zero-entry accounts still appear"
  - "Decimal end-to-end for money math in the reconciliation (never float) — balance and SUM both wrapped in Decimal() before comparison"
  - "Tests on the session-scoped async_session that must be order-independent: wrap each scenario in a savepoint that is EXPLICITLY rolled back (begin_nested as an implicit CM RELEASES/persists on clean exit) and assert on the test's own seeded account, never on global ledger cleanliness"

requirements-completed: [PLT-09]

# Metrics
duration: ~26min
completed: 2026-05-27
---

# Phase 03 Plan 06: Wallet Reconciliation Safety Net Summary

**A nightly `reconcile_wallets` Celery task (RedBeat, 03:00 UTC) computes `SUM(credit) - SUM(debit)` per account and compares it to the denormalized `accounts.balance` cache — clean ledgers log INFO, any drift logs CRITICAL via structlog and fires a Sentry alert — proving the double-entry truth holds over time (WAL-06 / SC#7 / PLT-09).**

## Performance

- **Duration:** ~26 min
- **Started:** 2026-05-27T15:16:25Z
- **Completed:** 2026-05-27T15:42:22Z
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- `reconcile_wallets` nightly task: a SYNC Celery task body wrapping `asyncio.run(_reconcile_async())` (Celery 5.5 has no native async), opening a fresh `AsyncSession` so the reconciliation never shares the FastAPI event loop. Returns `{"accounts_checked": N, "drift_count": M}` for flower/observability.
- Per-account drift detection: `func.coalesce(func.sum(case((Entry.direction=='credit', Entry.amount), else_=-Entry.amount)), 0)` grouped by account (the validated harness `_measure` shape), LEFT OUTER JOIN so zero-entry accounts still appear; `Decimal` end-to-end. Clean → single INFO `reconcile_clean`; each drifting account → CRITICAL `wallet_ledger_drift` (account_id, balance, ledger_sum, drift) + `sentry_sdk.capture_message(level="error")`.
- Registered + scheduled: `reconcile-wallets-nightly` (`crontab(hour=3, minute=0)`) appended to the shared `celery_app.conf.beat_schedule` (never reassigned — Phases 2-9 share it); the task module is imported at the bottom of `celery_app.py` so the worker/beat register it (Pitfall 5 reachability), with the existing signals/heartbeat untouched.
- SC#7 proven by integration test: a properly opening-booked wallet reconciles clean (INFO, no Sentry); a raw `UPDATE accounts SET balance = balance + 1` on the mutable cache (entries stay immutable) produces a CRITICAL line for that account AND a Sentry alert — the synthetic-drift alert path that satisfies PLT-09.

## Task Commits

Each task was committed atomically:

1. **Task 1: reconcile_wallets Celery task + async reconciliation + RedBeat schedule entry** — `2555e7b` (feat)
2. **Task 2: SC#7 reconciliation test — clean logs INFO; injected drift logs CRITICAL + Sentry** — `6eedb42` (test; also carries the Rule 2 `house_promo` exclusion fix to `reconcile.py`)

**Plan metadata:** _(this SUMMARY + STATE + ROADMAP — final docs commit)_

_Note: Both tasks carried `tdd="true"`. As in 03-01, the plan is `type: execute` (not plan-level `type: tdd`): Task 1 is the implementation (`feat`) and Task 2 is the SC#7 test scaffold (`test`) that proves the Task-1 behavior GREEN — the dedicated RED→GREEN gate-commit sequence does not apply. See "TDD Gate Compliance" below._

## Files Created/Modified
- `backend/app/wallet/reconcile.py` (created) — `reconcile_wallets` sync task + `_reconcile_async(session=None)` + `_reconcile_with_session()`; `_RECONCILE_EXCLUDED_ACCOUNT_IDS = {HOUSE_PROMO_ACCOUNT_ID}`; per-account signed-sum drift query, Decimal math, structlog INFO/CRITICAL, Sentry capture on drift.
- `backend/tests/wallet/test_reconcile.py` (created) — 3 integration tests (clean→INFO/no-Sentry, injected-drift→CRITICAL+Sentry, summary shape); `_book_clean_wallet()` helper booking a balanced opening transfer; savepoint-isolated, account-specific assertions.
- `backend/app/celery_app.py` (modified) — added `from celery.schedules import crontab`; appended `reconcile-wallets-nightly` to `beat_schedule` via `.update()`; bottom-of-module `import app.wallet.reconcile` for task registration. All existing config (RedBeat scheduler, default queue, worker/beat Sentry signals, heartbeat thread, contextvar clearing, `sentry_test_task`) preserved verbatim.

## Decisions Made
- **Nightly at 03:00 UTC** via `crontab(hour=3, minute=0)` — the plan's Claude's-Discretion low-traffic window.
- **Exclude `house_promo` from reconciliation** (Rule 2 deviation, below) — its seeded 1e9 opening balance is intentionally not ledger-backed; scanning it would alert every night.
- **Register via explicit bottom-of-module import**, not `autodiscover_tasks(["app.wallet"])`: autodiscover's default `related_name="tasks"` looks for an `app.wallet.tasks` module, which does not exist; the task lives in `app.wallet.reconcile`. The late import (after `celery_app` is fully constructed) also resolves the `reconcile.py` → `celery_app` circular import cleanly.
- **`capture_message(level="error")` per drifting account** rather than `capture_exception` — the alert carries the account id + balances inline; no synthetic exception/stack needed.
- **Test `_reconcile_async()` directly with the injected test session** (not the sync `reconcile_wallets()`): the sync task uses `asyncio.run` (would nest loops under pytest-asyncio) and opens a fresh session that cannot see the test's uncommitted rolled-back rows. `_reconcile_async(async_session)` reconciles inside the same transaction (the path the plan prescribes).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Exclude the seeded `house_promo` singleton from the drift scan**
- **Found during:** Task 2 (writing the SC#7 clean test against the testcontainer DB).
- **Issue:** Migration 0003 (03-01) seeds `house_promo` with a `1,000,000,000.0000` opening balance and **no** offsetting `entries` — it is the recharge SOURCE, funded so admin recharges never hit the `balance >= 0` floor. The reconciliation as literally specified ("SUM(entries) per account vs balance for every account") would compute `drift = 1e9 - 0` for `house_promo` on **every** run, emitting a CRITICAL log + Sentry alert nightly. That permanent false positive would bury any real drift under alert fatigue — directly defeating the purpose of PLT-09. It also made the "clean → INFO, no Sentry" path impossible to ever observe.
- **Fix:** Added `_RECONCILE_EXCLUDED_ACCOUNT_IDS = frozenset({HOUSE_PROMO_ACCOUNT_ID})` and a `.where(Account.id.notin_(...))` clause. Every other account — all user wallets AND `house_revenue` — remains fully reconciled, so no real drift surface is hidden; only the one deliberate non-ledger-backed seed is excluded, with a thorough code comment explaining why.
- **Files modified:** `backend/app/wallet/reconcile.py`.
- **Verification:** `pytest tests/wallet/test_reconcile.py -x -q` → 3 passed; `pytest tests/wallet/ -q` → 15 passed; ruff clean; Task-1 registration assertion still passes.
- **Committed in:** `6eedb42` (Task 2 commit).

---

**Total deviations:** 1 auto-fixed (1 missing-critical).
**Impact on plan:** The exclusion is required for the alert path to be meaningful (no nightly false positives) and for the clean path to be observable at all. It narrows the scan by exactly one intentional seed account and is fully documented in code; no schema/architecture change, no scope creep. A cleaner long-term alternative (seed `house_promo`'s opening balance as a real opening transfer in the migration) would touch 03-01's already-committed migration and is left to a future plan if desired.

## Issues Encountered
- **Pre-existing full-suite session-poisoning (out of scope, NOT fixed) — logged to `deferred-items.md` as DEF-03-01.** Running the *entire* backend suite in one process (`pytest -q`, unit + integration) yields `InFailedSQLTransactionError: current transaction is aborted` for many DB-touching tests in the 03-01 files (`test_migration_0003.py`, `test_models.py`) and, as downstream victims, the new `test_reconcile.py`. **Confirmed NOT caused by 03-06:** re-running the full suite with the reconcile test excluded (`pytest -q --ignore=tests/wallet/test_reconcile.py`) still produces 14 failures + 3 errors in the 03-01 files; my tests only raise the victim count. Root cause is the **session-scoped** `async_session` fixture combined with a pre-03 test (per 03-01's own SUMMARY, `tests/core/test_audit_immutability.py`) that lets an expected `DBAPIError` abort the shared transaction without savepoint isolation. **All gates GSD actually runs are GREEN:** `pytest tests/wallet/ -q` → 15 passed; `pytest tests/wallet/test_reconcile.py -q` → 3 passed; `pytest -m "not integration" -q` → 59 passed / 2 skipped; ruff clean. The new reconcile tests are themselves correctly savepoint-isolated (explicit `await savepoint.rollback()` per test) and pass both in isolation and in the wallet suite. Recommended follow-up (NOT in 03-06 scope): retrofit savepoints into the audit suite, or switch `async_session` to function-scoped isolation.
- **`alembic` console-script blocked by Windows Application Control (os error 4551)** — carried-forward 03-01 learning; not encountered here (no alembic shell-out in this plan), noted for continuity. The testcontainer `engine` fixture runs `alembic upgrade head` via the Python `command` API, which works.
- **testcontainers `ResourceWarning: unclosed socket`** prints after the suite completes — the same teardown artifact 03-01 noted, not a failure; the wallet suite reports `15 passed`.

## TDD Gate Compliance
Both tasks carried `tdd="true"`. The plan is `type: execute` (not plan-level `type: tdd`), so the per-plan RED/GREEN/REFACTOR gate-commit sequence does not apply (same posture as 03-01). Task 1 is the implementation, committed as `feat`; Task 2 is the SC#7 integration test scaffold, committed as `test`, and passes GREEN against the Task-1 behavior. The scaffold did real work: writing the clean test surfaced the `house_promo` false-positive (the Rule 2 deviation) and the shared-fixture leakage that drove the savepoint-rollback + account-specific assertion design. No RED gate was skipped — there is no plan-level TDD gate to satisfy here.

## User Setup Required
None — no new external service configuration or env vars. The only runtime action at deploy time (per RESEARCH "Runtime State Inventory") is restarting the Celery **beat** process so RedBeat loads the new `reconcile-wallets-nightly` schedule from the updated config (RedBeat stores the live schedule in Redis). No new secret; `DATABASE_URL` / `REDIS_URL` / `SENTRY_DSN` already exist in `Settings`.

## Next Phase Readiness
- The reconciliation safety net closes Phase 3's SC#7 / PLT-09: user-wallet and house_revenue balances are now nightly-verified against the immutable ledger, with a loud CRITICAL + Sentry alert on any divergence.
- Phase 5 (bets/settlement) will add new account kinds + transfers; all of them are automatically covered by this reconciliation (only the one `house_promo` seed is excluded). If a future settlement records `house_revenue` movements, they remain reconciled as written.
- No blockers from this plan. Note the deferred full-suite test-isolation item (DEF-03-01) for a future test-infra cleanup — it does not affect production code or any per-file/per-wave gate.

---
*Phase: 03-wallet-double-entry-ledger*
*Completed: 2026-05-27*

## Self-Check: PASSED

Both created files (`backend/app/wallet/reconcile.py`, `backend/tests/wallet/test_reconcile.py`) and the supporting `deferred-items.md` + this SUMMARY are present on disk. Both task commits (`2555e7b` feat, `6eedb42` test) verified in git history. Plan verification gates all pass: `pytest tests/wallet/test_reconcile.py -q` → 3 passed; `pytest tests/wallet/ -q` → 15 passed; `pytest -m "not integration" -q` → 59 passed / 2 skipped; `ruff check app/wallet/reconcile.py app/celery_app.py` → clean; `reconcile-wallets-nightly` present in `beat_schedule` with `crontab(hour=3,minute=0)` and `app.wallet.reconcile.reconcile_wallets` registered in `celery_app.tasks`. The pre-existing full-suite session-poisoning (DEF-03-01) is documented and confirmed not caused by this plan.
