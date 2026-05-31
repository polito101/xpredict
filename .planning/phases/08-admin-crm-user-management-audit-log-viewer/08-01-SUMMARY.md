---
phase: 08-admin-crm-user-management-audit-log-viewer
plan: 01
subsystem: api
tags: [fastapi, sqlalchemy, admin, crm, ban, pydantic, alembic, pagination]

# Dependency graph
requires:
  - phase: 02-auth-identity
    provides: User model (banned_at, is_superuser), current_active_admin Bearer gate, login proxies, UserManager
  - phase: 03-wallet-double-entry-ledger
    provides: accounts/transfers/entries ledger, MoneyStr money-string contract, recharge primitive
  - phase: 04-markets (0003 migration)
    provides: markets/outcomes tables, MarketService pagination pattern, PaginatedResponse envelope
  - phase: 05-bets
    provides: bets table, current_betting_player ban gate, payout/portfolio P&L math
provides:
  - Admin CRM backend module (app/admin): schemas + AdminUserService + admin_crm_router with 6 endpoints
  - Paginated user list with ILIKE search, status/signup-date filters, balance via LEFT JOIN (no N+1)
  - User detail aggregation (profile + balance + transaction_count + bet_count) + paginated transactions/bets
  - Ban/unban state machine (banned_at flag) with mandatory ban reason + audit events
  - Ban enforcement at 3 paths: login (403), bet placement (403, pre-existing gate), admin recharge (403)
  - users.created_at column (migration 0007) — signup timestamp for CRM sort/filter
affects: [08-02 audit-log-viewer, 08-03 admin-frontend, phase-10 admin-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Admin CRM service mirrors MarketService (static methods, offset-limit pagination, count+items)"
    - "ILIKE wildcard escaping (\\\\ % _) before %...% wrap with escape='\\\\' (T-08-03)"
    - "Ban = nullable banned_at timestamp doubling as state + audit trail (D-01)"
    - "Ban enforcement via UserManager.assert_not_banned called from login proxy (no on_after_login hook)"
    - "Admin schemas REUSE PaginatedResponse + MoneyStr (no duplication)"

key-files:
  created:
    - backend/app/admin/schemas.py
    - backend/app/admin/service.py
    - backend/app/admin/router.py
    - backend/alembic/versions/0008_phase8_user_created_at.py
    - backend/tests/admin/_helpers.py
    - backend/tests/admin/conftest.py
    - backend/tests/admin/test_user_list.py
    - backend/tests/admin/test_user_detail.py
    - backend/tests/admin/test_auth_negative.py
    - backend/tests/admin/test_ban_unban.py
  modified:
    - backend/app/main.py
    - backend/app/auth/models.py
    - backend/app/auth/manager.py
    - backend/app/auth/router.py
    - backend/app/wallet/admin_router.py

key-decisions:
  - "Added users.created_at (migration 0007) — fastapi-users base table has no signup timestamp, required by ADU-01/D-05"
  - "Login ban check lives in the login proxy via UserManager.assert_not_banned (fastapi-users has no on_after_login hook)"
  - "Audit events use admin.user_banned / admin.user_unbanned (PLAN/CONTEXT D-04/D-13), not CONVENTIONS' admin.user.banned"
  - "cleanup_user does not delete entries/transfers/accounts (append-only WAL-06) — tests use fresh user UUIDs"

patterns-established:
  - "ILIKE wildcard escape helper (_escape_like) for any admin free-text search"
  - "Inline target-user banned_at check in money endpoints (recharge), distinct from the admin auth dependency"

requirements-completed: [ADU-01, ADU-02, ADU-04, ADU-05]

# Metrics
duration: 27min
completed: 2026-05-28
---

# Phase 8 Plan 01: Admin CRM (User Management & Ban Enforcement) Summary

**Admin CRM backend with 6 Bearer-gated endpoints — paginated user list (ILIKE search, status/date filters, no-N+1 balance), user detail aggregation, paginated transactions/bets, and a banned_at state machine enforced at login, bet, and recharge — 25 integration tests green.**

## Performance

- **Duration:** ~27 min
- **Started:** 2026-05-28T18:45Z
- **Completed:** 2026-05-28T19:12Z
- **Tasks:** 2
- **Files modified:** 17 (10 created, 5 modified, 2 `__init__.py` touched)

## Accomplishments
- `app/admin/` module: `schemas.py` (UserListItem/UserDetail/BanRequest/UnbanRequest/UserTransactionItem/UserBetItem), `service.py` (`AdminUserService`), `router.py` (`admin_crm_router`, 6 endpoints), wired into `main.py`.
- `GET /api/v1/admin/users`: offset-limit pagination, ILIKE search on email+display_name (wildcard-escaped, T-08-03), `status`/`signup_after`/`signup_before` filters, whitelisted sort, wallet balance via a single LEFT JOIN to `accounts` (no N+1), `last_activity` = most-recent bet via grouped LEFT JOIN.
- `GET /api/v1/admin/users/{id}`: profile + balance + `transaction_count` (entries) + `bet_count`; 404 for a missing user. Plus paginated `/transactions` and `/bets` (with LEFT-JOINed market question + outcome label and realized P&L).
- Ban/unban state machine (`banned_at`): mandatory ban reason, 409 on already-banned/already-active, `admin.user_banned`/`admin.user_unbanned` audit rows. Frozen-balance verified (balance unchanged across a full ban→unban cycle, D-03).
- Ban enforcement at **all 3 D-02 paths**: login (403 "Account suspended"), bet placement (403 via the pre-existing `current_betting_player` gate), admin recharge of a banned user (403, inline target check).

## Task Commits

1. **Task 1: Admin CRM schemas, service, router + user list/detail/auth tests** — `ad1578d` (feat)
2. **Task 2: Ban/unban enforcement at login, bet, recharge + ban integration tests** — `1a9185e` (feat)

_TDD note: both tasks are `tdd="true"`. The feature is integration-test-driven (tests import the live FastAPI app via ASGITransport), so each task's tests and implementation were committed together (a separate failing-RED commit would not import without the router mounted). RED→GREEN was exercised iteratively in the loop (the first `list_users` run failed on the missing `users.created_at` column before the migration was added)._

## Files Created/Modified
- `backend/app/admin/schemas.py` — Admin CRM Pydantic schemas (reuse PaginatedResponse + MoneyStr).
- `backend/app/admin/service.py` — `AdminUserService`: list/detail/transactions/bets reads + ban/unban writes; `_escape_like` ILIKE guard.
- `backend/app/admin/router.py` — `admin_crm_router` with the 6 endpoints (no `from __future__ import annotations`).
- `backend/app/main.py` — include `admin_crm_router`.
- `backend/app/auth/models.py` — add `User.created_at` (signup timestamp).
- `backend/alembic/versions/0008_phase8_user_created_at.py` — additive migration for `users.created_at` (server_default now()).
- `backend/app/auth/manager.py` — `UserManager.assert_not_banned` (login ban check).
- `backend/app/auth/router.py` — call `assert_not_banned` in the player login proxy (403).
- `backend/app/wallet/admin_router.py` — inline `banned_at` check on the recharge TARGET user (403).
- `backend/tests/admin/*` — `_helpers.py`, `conftest.py`, and 4 test modules (25 tests).

## Decisions Made
- **`users.created_at` added (migration 0007).** The fastapi-users `SQLAlchemyBaseUserTableUUID` table ships no signup timestamp, and the `id` is a random UUIDv4 (not time-ordered). ADU-01 / D-05 require sorting + filtering users by signup date, so a non-null `TIMESTAMPTZ created_at` (server_default `now()`, backfilling existing rows) was added. Additive + backward-compatible; CONTEXT's "may not need a new migration" was a possibility, not a prohibition.
- **Login ban check via `UserManager.assert_not_banned`.** `app/auth/manager.py`'s own docstring states fastapi-users has no `on_after_login` hook. The check is a small static helper on `UserManager` (touches `manager.py` as the plan's `files_modified` lists) and is invoked from the player login proxy in `router.py` right after `authenticate()` — the actual login decision point. Returns 403 (valid credentials, suspended account), not 401.
- **Audit event names `admin.user_banned` / `admin.user_unbanned`.** The PLAN must_haves, key_links, and CONTEXT D-04/D-13 lock these (underscore form, and D-13 lists them in the audit-viewer dropdown). `backend/CONVENTIONS.md` §3 shows `admin.user.banned` (dot form) as an example — the phase-specific PLAN/CONTEXT take precedence, and the viewer (Plan 08-02) will filter on the D-13 list.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `users.created_at` column + migration 0007**
- **Found during:** Task 1 (user list service) — first test run failed with `AttributeError: type object 'User' has no attribute 'created_at'`.
- **Issue:** The plan's `UserListItem.created_at`, the `signup_after`/`signup_before` filters, and `sort_by=created_at` (all from D-05) require a per-user signup timestamp that did not exist on the `users` table.
- **Fix:** Added `User.created_at` (`Mapped[datetime]`, server_default `now()`, Python default `datetime.now(UTC)`) and Alembic migration `0008_phase8_user_created_at` (additive, backfills existing rows). Single alembic head preserved.
- **Files modified:** `backend/app/auth/models.py`, `backend/alembic/versions/0008_phase8_user_created_at.py`
- **Verification:** `uv run alembic heads` → single head; admin list/sort/filter tests pass.
- **Committed in:** `ad1578d`

**2. [Rule 3 - Blocking] Login ban enforcement placed in the login proxy (no `on_after_login` hook)**
- **Found during:** Task 2 (login enforcement).
- **Issue:** The plan suggested checking `banned_at` in `on_after_login`, but fastapi-users provides no such hook (documented in `manager.py`).
- **Fix:** Added `UserManager.assert_not_banned` and called it from the player login proxy in `auth/router.py` after `authenticate()`. Same net behaviour (403 for a banned user at login) at the correct architectural seam.
- **Files modified:** `backend/app/auth/manager.py`, `backend/app/auth/router.py`
- **Verification:** `test_banned_user_login_returns_403` passes (403 + "suspended").
- **Committed in:** `1a9185e`

**3. [Rule 1 - Bug] Test cleanup respected append-only ledger**
- **Found during:** Task 1 (user detail test) — cleanup raised `transfers/entries are append-only -- UPDATE and DELETE are forbidden`.
- **Issue:** The initial `cleanup_user` helper tried to `DELETE FROM entries`, blocked by the WAL-06 deny-trigger; accounts referenced by entries are then FK-pinned.
- **Fix:** `cleanup_user` now deletes only the user row + its bets and leaves ledger/accounts in place (harmless — every test seeds a fresh user UUID, so no collision).
- **Files modified:** `backend/tests/admin/_helpers.py`
- **Verification:** Full `tests/admin/` group passes (25).
- **Committed in:** `ad1578d`

---

**Total deviations:** 3 auto-fixed (1 missing-critical, 1 blocking, 1 test bug)
**Impact on plan:** All necessary for correctness; no scope creep. The only schema change (users.created_at) is additive and required by the plan's own acceptance criteria.

## Threat Flags

None — no security surface beyond the plan's `<threat_model>` was introduced. T-08-01 (admin gate on every endpoint), T-08-03 (ILIKE escape), T-08-02 (ban at 3 paths), T-08-04 (401/403) are all implemented and tested. No new packages (T-08-SC).

## Known Stubs

None — all endpoints are wired to real queries. `UserDetail.email_verified_at` is exposed as `None` (the `users` table tracks verification via the boolean `is_verified`, not a timestamp; `is_verified` IS populated). `last_activity` on the detail endpoint is `None` (the list endpoint computes it from bets; detail omits the join for simplicity) — both are nullable contract fields, not blocking stubs.

## Issues Encountered
- **Full-suite test isolation collapse on Windows (pre-existing, NOT this plan).** `uv run pytest` (entire suite) yields ~28 failed + ~25 errored, but the SAME failures occur with `--ignore=tests/admin` (zero Phase 8 tests), and the implicated tests pass in isolation / smaller groups: `tests/admin/` = **25 passed**, `tests/markets tests/wallet` together = **98 passed**, affected-scope `admin+auth+bets+wallet+markets` = **233 passed**. Failures are "at setup/teardown of" fixture errors of the session-scoped testcontainer engine under full-suite async load — matching the known constraint that this stack's integration tests are CI-Linux-only and won't true-green on Windows. Two code-unrelated extras: `tests/auth/test_password_reset.py` (its own mock `_mock_send_reset` has an arg-count `TypeError` + no mailpit DNS) and `test_gitleaks_clean_scan_of_full_repo`. Logged in `deferred-items.md`.
- **Pre-existing mypy errors in `app/auth/manager.py` (7).** Present at the committed baseline before any Phase 8 edit; the new `assert_not_banned` is mypy-clean. Logged in `deferred-items.md`.
- **`ruff format` baseline drift + pre-commit not installed.** `ruff 0.8.6` would reformat many already-committed files (compact magic-trailing-comma style vs. exploded). New code matches the committed neighbour style and passes `ruff check` (lint) + `mypy --strict` on the admin module; `ruff format` was intentionally not mass-run (would touch dozens of unrelated files). Equivalent hooks (ruff check, mypy, money-lint, gitleaks) were run manually and pass. Logged in `deferred-items.md`.

## Verification Evidence
- `uv run pytest tests/admin/ -q` → **25 passed**.
- `uv run pytest tests/admin/test_user_list.py tests/admin/test_user_detail.py tests/admin/test_auth_negative.py -x -q` → **16 passed** (Task 1 acceptance).
- `uv run pytest tests/admin/test_ban_unban.py -x -q` → **9 passed** (Task 2 acceptance).
- `uv run ruff check app/admin/` → clean. `uv run mypy app/admin/` → clean.
- `uv run python scripts/lint_money_columns.py` → OK, 0 warnings.
- `gitleaks protect --staged` (both commits) → no leaks.
- `uv run alembic heads` → single head `0008_phase8_user_created_at`.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- The admin CRM backend surface (user list/detail/transactions/bets + ban/unban) is ready for the **Plan 08-03 frontend** to consume.
- The `admin.user_banned` / `admin.user_unbanned` audit events are now being written and will appear in the **Plan 08-02 audit-log viewer** (whose D-13 dropdown already lists them).
- Ban enforcement is complete at all 3 D-02 paths; no follow-up enforcement work needed.
- No blockers.

## Self-Check: PASSED
- All 10 key created/modified files verified present on disk.
- Both task commits (`ad1578d`, `1a9185e`) verified present in git history.

---
*Phase: 08-admin-crm-user-management-audit-log-viewer*
*Completed: 2026-05-28*
