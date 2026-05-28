# Deferred / Out-of-Scope Items — Phase 8

Discovered during execution of plans in this phase. NOT fixed (out of scope per
the executor SCOPE BOUNDARY); logged for the PM / a future hardening pass.

## 08-01

- **`ruff format` baseline drift (pre-existing).** With the pinned `ruff 0.8.6`,
  `uv run ruff format --check` flags MANY already-committed backend files
  (`app/markets/service.py`, `app/markets/schemas.py`, `app/wallet/service.py`,
  `tests/markets/test_admin_router.py`, …). The committed code uses a compact
  "magic-trailing-comma collapsed" style; ruff 0.8.6 wants to explode those
  call sites. This means the repo's committed format baseline predates / differs
  from the pinned formatter. New Phase 8 code was written to MATCH the committed
  style (so it stays consistent with its neighbours) and passes `ruff check`
  (lint) + `mypy --strict`. A repo-wide `ruff format` normalization is a separate
  chore (touches dozens of unrelated files) and was deliberately NOT done here.

- **pre-commit framework not installed in this clone.** `.git/hooks/` only has
  `pre-commit.sample`; `pre-commit install` was never run. The gitleaks / ruff /
  ruff-format / mypy / money-lint hooks in `.pre-commit-config.yaml` therefore do
  not fire on commit in this environment. Equivalent checks were run manually for
  08-01 (`ruff check`, `mypy app/admin`, full pytest) and pass.

- **Pre-existing mypy errors in `app/auth/manager.py` (7, NOT introduced here).**
  `uv run mypy app/auth/manager.py` reports 7 strict-mode errors at the committed
  baseline `ad1578d` (the `create()` override: `create_update_dict*` untyped
  calls, `user_db.session`/`user_table` attr-defined, Any return; and
  `on_after_reset_password`: an unused `type: ignore` + `Result.rowcount`). They
  exist BEFORE the Phase 8 edits — confirmed by running mypy on the file at HEAD.
  The Phase 8 addition (`UserManager.assert_not_banned`) is mypy-clean. Not fixed
  (out of scope: pre-existing errors in a file this plan only appends to).

- **Full-suite test isolation collapse on Windows (pre-existing / environmental).**
  Running the ENTIRE backend suite at once (`uv run pytest`) yields ~28 failed +
  ~25 errored, but the SAME failures occur with `--ignore=tests/admin` (i.e. with
  zero Phase 8 tests) and the implicated tests PASS in isolation or in smaller
  groups (`tests/markets tests/wallet` together = 98 passed; `tests/admin` = 25
  passed; affected-scope `admin+auth+bets+wallet+markets` = 233 passed). The
  errors are "at setup/teardown of" fixture failures of the session-scoped
  testcontainer `engine`/`async_session` under full-suite async load — matching
  the documented note that this stack's integration tests are CI-Linux-only and
  "won't true-green on Windows". Two additional pre-existing, code-unrelated
  failures: `tests/auth/test_password_reset.py` (its own mock `_mock_send_reset`
  has an arg-count `TypeError` + no mailpit DNS in this env) and
  `tests/test_gitleaks_blocks_secret.py::test_gitleaks_clean_scan_of_full_repo`
  (full-repo scan). None are caused by Phase 8 changes.

## 08-02

- **`tests/core/test_audit_immutability.py::test_audit_log_delete_blocked` fails
  ONLY in-file-order (pre-existing savepoint flaw, NOT introduced here).** Running
  the file as a group fails the 4th test with an `InFailedSQLTransactionError`
  on its `INSERT INTO audit_log` — the prior `test_audit_log_update_blocked`
  raises a `DBAPIError` WITHOUT wrapping it in `session.begin_nested()`, so the
  abort poisons the shared session-scoped transaction and the next statement
  fails. The SAME test PASSES in isolation
  (`pytest tests/core/test_audit_immutability.py::test_audit_log_delete_blocked`
  -> 1 passed). This is the EXACT latent flaw already logged in
  `STATE.md` (2026-05-27, Plan 03-01: "the pre-existing
  `tests/core/test_audit_immutability.py` has this latent flaw — fails on its 4th
  test under `-x` … logged for a follow-up retrofit"). It is entirely independent
  of the 08-02 read-only audit viewer (which never UPDATEs/DELETEs audit rows).
  Fix is a one-line savepoint wrap in that test file — out of scope here
  (pre-existing test-infra bug in a file this plan does not touch).

- **`tests/wallet/test_concurrent_transfers.py::test_50_concurrent_overdraft`
  fails ONLY under multi-group async load (pre-existing Windows isolation flake,
  NOT introduced here).** When run alongside other suites
  (`tests/admin tests/wallet tests/bets` together) the 50-concurrent-overdraft
  SELECT-FOR-UPDATE test fails; run in isolation
  (`pytest tests/wallet/test_concurrent_transfers.py`) it PASSES (1 passed). This
  is the documented session-scoped-testcontainer-engine collapse under full/large
  async load that makes this stack "CI-Linux-only, won't true-green on Windows"
  (see 08-01 note above + STATE.md). 08-02 changes are read-only (export queries +
  audit viewer) and touch NONE of the wallet concurrency write path.
