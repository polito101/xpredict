---
phase: 03-wallet-double-entry-ledger
plan: 03
subsystem: payments
tags: [wallet, registration, fastapi-users, atomicity, single-transaction, sc1, wal-01, sqlalchemy, asyncio]

# Dependency graph
requires:
  - phase: 03-wallet-double-entry-ledger
    plan: 02
    provides: "WalletService.create_wallet(session, *, user) — the caller-owned-transaction add+flush wallet primitive (never commits) that the registration override calls between the user INSERT and its single commit"
  - phase: 02-auth-identity
    provides: "UserManager (validate_password, on_after_register, audit session machinery), SQLAlchemyUserDatabase adapter (get_user_db), register proxy route, get_async_session (no auto-commit) — the Phase 2 auth surface this plan extends without regressing"
provides:
  - "UserManager.create() override (RESEARCH Option A) — co-inserts the user_wallet on the adapter's own session between the user INSERT (flush) and a SINGLE commit, so user + wallet land atomically (SC#1 / WAL-01)"
  - "SC#1 atomicity proof: register → exactly one user_wallet (PLAY_USD, balance 0); wallet-creation fault rolls the user INSERT back too (no orphan)"
affects: [03-04, 03-05, phase-05, recharge, wallet-reads, bets]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Override fastapi-users UserManager.create() (not on_after_register) to host same-transaction work — the stock SQLAlchemyUserDatabase.create() commits BEFORE the hook fires (verified in installed v15.0.5 source), so the hook can never co-insert in the same tx; the override re-implements the stock flow (validate_password → get_by_email/UserAlreadyExists → create_update_dict → hash) and adds the wallet co-insert before one commit (RESEARCH Pitfall 1 / Option A)"
    - "Caller-owned-transaction contract honored end-to-end: WalletService.create_wallet add+flushes only; the override owns the single commit — the same AuditService.record discipline the codebase already uses"
    - "Integration tests that exercise a real request transaction assert against committed state via their own _get_session_maker() sessions (the register request runs in its OWN request session, not the rollback async_session); rollback proof uses a before/after wallet-count DELTA, not a global scan, so it is immune to the direct-seeded ledger rows sibling tests/wallet modules commit (the 03-02 isolation discipline)"

key-files:
  created:
    - backend/tests/wallet/test_wallet_creation.py
  modified:
    - backend/app/auth/manager.py

key-decisions:
  - "Chose RESEARCH Option A (override UserManager.create) over Option B (custom SQLAlchemyUserDatabase adapter) — minimal blast radius, keeps the change inside the already-customized UserManager and leaves get_user_db wiring untouched; both satisfy SC#1, A is the lighter touch (the planner's A1 locked decision)"
  - "The override grabs the adapter's OWN session (self.user_db.session) rather than opening a new one — that is the exact session FastAPI's get_async_session yields and that get_user_manager does NOT auto-commit, so a single commit here makes user + wallet atomic and a mid-flow raise rolls both back"
  - "Rollback test asserts the user is absent AND the user_wallet count is unchanged (before/after delta) — a global NOT EXISTS orphan scan falsely counted the random-owner_id accounts that test_atomicity/test_idempotency/test_concurrent_transfers seed directly; the delta is the precise, order-independent SC#1 proof"

patterns-established:
  - "Same-transaction provisioning in fastapi-users = override create(), never the post-commit hook — the pattern any future 'create X alongside the user' work (referral row, default settings) must follow"
  - "Request-transaction integration tests: drive the app over httpx ASGITransport (raise_app_exceptions=False so an injected 5xx surfaces as a response), assert via fresh committed _get_session_maker() sessions, clean up by email for idempotent re-runs, autouse _require_testcontainer(engine) for the container side effects"

requirements-completed: [WAL-01]

# Metrics
duration: ~5min
completed: 2026-05-27
---

# Phase 03 Plan 03: Same-Transaction Wallet Creation on Registration Summary

**`UserManager.create()` now co-inserts the `user_wallet` account on the adapter's own session between the user INSERT and a single commit (RESEARCH Option A) — so every new player atomically owns exactly one wallet (PLAY_USD, balance 0), and a wallet-creation fault rolls the user INSERT back too (SC#1 / WAL-01), proven by fault injection on the real request transaction.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-27T15:50:26Z
- **Completed:** 2026-05-27T15:55:11Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- **`UserManager.create()` override (`app/auth/manager.py`, +67 lines)** — the one genuinely non-obvious wiring decision in the phase, resolved per RESEARCH Option A:
  - Re-implements the stock `BaseUserManager.create()` flow faithfully: `await self.validate_password(...)` first → `get_by_email` → `raise exceptions.UserAlreadyExists()` on a duplicate → `create_update_dict()` (safe) / `create_update_dict_superuser()` → `pop("password")` → `hashed_password = self.password_helper.hash(password)`.
  - Grabs the adapter's OWN session (`session = self.user_db.session`), builds the user via `self.user_db.user_table(**user_dict)`, `session.add(user)`, `await session.flush()` (user.id available, NOT committed).
  - `await WalletService.create_wallet(session, user=user)` — co-inserts the wallet on the SAME session (the 03-02 add+flush primitive that never commits).
  - `await session.commit()` — the SINGLE commit → user + wallet land in ONE transaction (SC#1 / WAL-01). Then `session.refresh(user)`, `on_after_register(user, request)`, `return user`.
  - Added `from app.wallet.service import WalletService` and the fastapi-users `exceptions` import (no import cycle — `wallet.service` imports only models/constants/exceptions/db, never auth). A docstring records WHY the override exists (stock adapter commits before the hook — RESEARCH Pitfall 1) and that `create_wallet` must never commit.
- **`on_after_register`, `validate_password`, and the audit session machinery are unchanged** — verification email + `auth.guest_created` audit still fire AFTER the single commit, exactly as in Phase 2 (no regression; the 27 auth unit tests stay green).
- **SC#1 proven on the real request transaction** (`tests/wallet/test_wallet_creation.py`, 3 integration tests against testcontainers Postgres 16):
  - `test_wallet_created_on_registration` — `POST /auth/register` 201 → exactly one `user_wallet` (kind `user_wallet`, currency `PLAY_USD`, `balance == Decimal("0")`) owned by the new user.
  - `test_wallet_creation_failure_rolls_back_user` — monkeypatch `WalletService.create_wallet` to raise mid-create → register returns 5xx, the user does NOT exist, and the `user_wallet` count is unchanged (the single-tx atomicity proof; RESEARCH Pitfall 1 warning sign). T-03-11 mitigated.
  - `test_no_duplicate_wallet` — a register yields a single wallet for the user (the `(owner_type, owner_id, kind, currency)` unique-constraint shape).
- **Verification all green:** `pytest tests/wallet/test_wallet_creation.py -x` → 3 passed; `pytest tests/wallet` (whole directory, order-independent) → 18 passed; `pytest -m "not integration" tests/auth` → 27 passed (no Phase 2 regression); `pytest -m "not integration"` (whole backend) → 59 passed / 2 skipped; `ruff check app/auth/manager.py` + the test file → clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: UserManager.create override co-inserting the wallet in one transaction** — `cce0af4` (feat)
2. **Task 2: SC#1 integration test — wallet exists in same tx + fault rolls back the user** — `0e4e028` (test)

**Plan metadata:** _(this SUMMARY + STATE + ROADMAP + REQUIREMENTS — final docs commit)_

_Note: both tasks carried `tdd="true"`. The plan splits the feature so Task 1 is the implementation (the override) and Task 2 is the behavioral proof (SC#1 + the fault-injection rollback). The genuine RED→GREEN signal lives in Task 2: `test_wallet_created_on_registration` only goes green because the override creates the wallet (pre-override, `on_after_register` never did, so the wallet count would be 0). See "TDD Gate Compliance" below._

## Files Created/Modified
- `backend/app/auth/manager.py` — added the `UserManager.create()` override (the same-transaction user+wallet co-insert, RESEARCH Option A) + the `WalletService` and fastapi-users `exceptions` imports. `validate_password`, all four lifecycle hooks, and the audit session machinery are byte-for-byte unchanged.
- `backend/tests/wallet/test_wallet_creation.py` — the SC#1 / WAL-01 integration suite (3 tests) driving `POST /auth/register` over httpx ASGITransport and asserting against committed state via fresh `_get_session_maker()` sessions; autouse `_require_testcontainer(engine)`; before/after wallet-count delta as the order-independent rollback proof.

## Decisions Made
- **RESEARCH Option A over Option B.** The planner's A1 decision locked Option A (override `UserManager.create`) — minimal blast radius, stays inside the already-customized `UserManager`, leaves the `get_user_db` dependency wiring untouched. Option B (a custom `SQLAlchemyUserDatabase` subclass) is "cleaner layering" but spreads the change across the dep graph; both satisfy SC#1, A is the lighter touch.
- **Grab the adapter's own session, own the single commit.** `self.user_db.session` is exactly the session FastAPI's `get_async_session` yields and that `get_user_manager` deliberately does NOT auto-commit at teardown (confirmed in `deps.py` + `session.py`). Committing once here makes user + wallet atomic; any raise before that commit (e.g. a failing `create_wallet`) lets the `async with session` context in `get_async_session` roll the whole transaction back.
- **Rollback proof = user-absent + wallet-count delta, not a global orphan scan.** See Deviations below — the global `NOT EXISTS` scan I first wrote falsely counted the direct-seeded accounts sibling `tests/wallet` modules commit. The before/after delta is the precise, isolation-safe SC#1 atomicity assertion (the 03-02 discipline: scope assertions to this scenario, never the whole ledger).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Rollback test's global orphan-wallet scan produced a false positive**
- **Found during:** Task 2 (running `pytest tests/wallet` as a full directory — the test passed in isolation but failed at `assert 4 == 0` when run alongside the other wallet modules)
- **Issue:** My first version of `test_wallet_creation_failure_rolls_back_user` proved "no wallet committed" with a global `SELECT count(*) FROM accounts WHERE kind='user_wallet' AND NOT EXISTS (matching users row)`. But `test_atomicity.py` / `test_idempotency.py` / `test_concurrent_transfers.py` seed `user_wallet` accounts directly via raw SQL with random `uuid4()` `owner_id`s that have no matching `users` row (legitimately — they isolate the immutable ledger without teardown, per 03-02). Those committed rows made the global scan return 4, a false positive: the production rollback genuinely works (the injected-fault user does NOT leak — `_user_exists` confirmed false), but my assertion was scoped to the whole ledger instead of this scenario. This is a bug in my own Task 2 test artifact, not a production bug.
- **Fix:** Replaced the global `NOT EXISTS` scan with a before/after `user_wallet` count DELTA (`_user_wallet_count()` snapshot before the register attempt, asserted unchanged after) plus the existing user-absent assertion. The delta is immune to unrelated seeded rows and is the exact, order-independent proof that no new wallet committed when the user rolled back.
- **Files modified:** backend/tests/wallet/test_wallet_creation.py
- **Verification:** `pytest tests/wallet` (full directory) → 18 passed; the rollback test run BEFORE `test_idempotency.py` → 3 passed (order-independent).
- **Committed in:** `0e4e028` (Task 2 commit — the fix was applied before the test was first committed)

**2. [Rule 1 - Lint] `UP037` removable type-annotation quotes**
- **Found during:** Task 2 (ruff on the new test file)
- **Issue:** The autouse fixture signature `def _require_testcontainer(engine: "AsyncEngine") -> "AsyncEngine"` quoted the type; with `from __future__ import annotations` present, ruff `UP037` flags the quotes as removable (the `if TYPE_CHECKING` import makes the name resolvable in annotation context).
- **Fix:** Removed the quotes → `def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine`.
- **Files modified:** backend/tests/wallet/test_wallet_creation.py
- **Verification:** `ruff check tests/wallet/test_wallet_creation.py` → clean.
- **Committed in:** `0e4e028` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both in my own Task 2 test artifact: 1 test-isolation bug, 1 lint). **Zero changes to the plan's prescribed production code** — `UserManager.create` is exactly the RESEARCH Option A skeleton; `WalletService.create_wallet` and the auth surface are untouched beyond the override + its two imports.

## Issues Encountered
- **The plan's Task 1 verify one-liner needs env vars seeded.** `uv run --directory backend python -c "...import UserManager..."` fails with a `Settings` `ValidationError` (DATABASE_URL/SECRET_KEY missing) because `UserManager` instantiates `Settings()` at class-definition time (`reset_password_token_secret = get_settings().SECRET_KEY`). This is a pre-existing characteristic of the module, NOT a regression — the conftest seeds those env vars via `os.environ.setdefault`, so the assertion passes cleanly under pytest and when the same four vars are exported. I ran the override-source assertion with the conftest's exact env defaults to confirm "override OK" + no import cycle; the load-bearing acceptance gate (`pytest -m "not integration" tests/auth` → 27 passed) ran normally.
- **`ResourceWarning: unclosed socket`** prints after each integration run — the known testcontainers Docker-probe teardown artifact (also documented in the 03-01/03-02/audit suites), not a test failure; every run reported all green.
- **Pre-existing DEF-03-01 (not touched):** the whole-suite single-process `pytest -q` cascade-fail caused by `tests/core/test_audit_immutability.py` poisoning the session-scoped tx is a Phase 1 issue out of scope here. Verified my work with per-file / per-directory runs + `pytest -m "not integration"`, exactly as the brief instructed.

## TDD Gate Compliance
Both tasks carried `tdd="true"`. The plan splits the feature so **Task 1 is the implementation** (the `UserManager.create` override) and **Task 2 is the behavioral proof** (the SC#1 happy path + the fault-injection rollback + the no-duplicate shape). The genuine behavioral signal lives in Task 2 and it did its job: `test_wallet_created_on_registration` is green only because the override actually creates the wallet (pre-override, `on_after_register` ran after the commit and never co-inserted, so a wallet query would find zero rows — a clean RED→GREEN), and `test_wallet_creation_failure_rolls_back_user` is the load-bearing atomicity assertion that surfaced (and forced the fix of) the test-isolation bug above. The plan is `type: execute` (not a plan-level `type: tdd`), so the per-plan RED/GREEN/REFACTOR gate-commit sequence does not apply; commits are `feat` (Task 1) and `test` (Task 2), consistent with the work. No test passed without first exercising the production override.

## Known Stubs
- None. The override is complete production code; no placeholder/empty-data paths were introduced. (`WalletService.recharge`'s `stripe` v2 stub is owned by 03-02 and untouched here.)

## Next Phase Readiness
- **SC#1 / WAL-01 is locked and DB-verified:** every new player atomically owns exactly one `user_wallet` (PLAY_USD, balance 0), and a wallet-creation fault rolls the user back too. The downstream surfaces can now assume the wallet exists:
  - **03-04 (recharge endpoint):** wraps `WalletService.recharge(...)` to credit the wallet this plan guarantees exists for every registered user.
  - **03-05 (wallet reads):** `get_balance` / `get_transactions` shaping reads the wallet provisioned here.
  - **Phase 5 (bets/settlement):** stake debits / payout credits move value on the per-user wallet created at registration.
- **No backfill in scope:** SC#1 creates wallets only for NEW registrations (RESEARCH §Stored data). Pre-existing Phase 2 dev/test users do not retroactively get wallets; a one-off backfill is a separate task only if Pol requests it.
- No blockers.

---
*Phase: 03-wallet-double-entry-ledger*
*Completed: 2026-05-27*

## Self-Check: PASSED

Both touched files verified present on disk (`backend/app/auth/manager.py`, `backend/tests/wallet/test_wallet_creation.py`) plus this SUMMARY; both task commits (`cce0af4` feat, `0e4e028` test) verified in git history. Plan verification gates all pass: `pytest tests/wallet/test_wallet_creation.py -x` → 3 passed, `pytest tests/wallet` (order-independent) → 18 passed, `pytest -m "not integration" tests/auth` → 27 passed (no Phase 2 regression), `pytest -m "not integration"` → 59 passed / 2 skipped, `ruff check app/auth/manager.py` + the test file → clean.
