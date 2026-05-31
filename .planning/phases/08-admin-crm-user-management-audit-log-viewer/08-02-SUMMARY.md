---
phase: 08-admin-crm-user-management-audit-log-viewer
plan: 02
subsystem: api
tags: [fastapi, sqlalchemy, csv, export, audit-log, security, pydantic, pagination]

# Dependency graph
requires:
  - phase: 08-01
    provides: AdminUserService (list filters + _escape_like), admin schemas (PaginatedResponse + MoneyStr reuse), admin_crm_router, tests/admin/_helpers.py
  - phase: 02-auth-identity
    provides: current_active_admin Bearer gate, User model, admin login proxy
  - phase: 03-wallet-double-entry-ledger
    provides: accounts/transfers/entries ledger, MoneyStr money-string contract
  - phase: 01-scaffold-foundations
    provides: AuditLog model + AuditService.record (single writer), append-only trigger + REVOKE (immutability)
provides:
  - CSV export utility (app/admin/csv_export.py): sanitize_csv_cell + build_users/transactions/bets_csv with formula-injection protection (D-09), money-as-string, ISO 8601 UTC, MAX_EXPORT_ROWS cap
  - CSV export endpoints (app/admin/export_router.py): GET /api/v1/admin/export/{users,transactions,bets}, admin-Bearer-gated, text/csv attachment
  - AdminUserService.export_users/transactions/bets — filtered reads joining user_email, DB-capped
  - Read-only audit-log viewer (app/core/audit/router.py): GET /api/v1/admin/audit-log (paginated, filterable) + GET /event-types; strictly GET-only (no mutation endpoints)
  - AuditLogItem schema (payload as raw JSON object) + KNOWN_EVENT_TYPES (19, D-13) for the frontend dropdown
affects: [08-03 admin-frontend (consumes export + audit-log endpoints), phase-10 admin-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CSV formula-injection defuse: prefix a single quote to any cell starting with = + - @ TAB CR (D-09/T-08-05/OWASP)"
    - "Batch CSV via stdlib csv.DictWriter + io.StringIO(newline='') (D-10), no streaming in v1"
    - "Money in CSV = str(Decimal) (no symbol, no float); timestamps = ISO 8601 UTC; both mirror the MoneyStr/API contract"
    - "MAX_EXPORT_ROWS=10000 DoS cap at BOTH the DB query (.limit) and the builder (defensive re-cap) with structlog warning (T-08-09)"
    - "Read-only resource = GET-only APIRouter; mutation methods return 405 by routing, immutability also enforced at DB layer (T-08-07)"
    - "Audit actor ILIKE reuses AdminUserService._escape_like wildcard guard (T-08-08), no duplication"
    - "INET column normalised to str when building the JSON response (asyncpg may hand back an ipaddress object)"

key-files:
  created:
    - backend/app/admin/csv_export.py
    - backend/app/admin/export_router.py
    - backend/app/core/audit/router.py
    - backend/app/core/audit/schemas.py
    - backend/tests/admin/test_csv_export.py
    - backend/tests/admin/test_audit_log.py
  modified:
    - backend/app/admin/service.py
    - backend/app/main.py
    - backend/tests/admin/_helpers.py

key-decisions:
  - "Export query methods live on AdminUserService (export_users reuses _apply_user_filters; export_transactions/bets join user_email + accept optional user_id scope) rather than a separate service — keeps the admin read surface in one place"
  - "CSV unit tests + integration tests share one file (test_csv_export.py per the plan); module-level pytestmark with @asyncio was DROPPED in favour of per-async-test marks so the SYNC unit tests don't trip pytest-asyncio's 'not an async function' warning (which filterwarnings=['error'] turns into a failure)"
  - "seed_audit test helper drives the real AuditService.record (the single audit writer, D-20/D-21) via the app session-maker, not a raw INSERT — audit_log is append-only so tests scope assertions to a unique event_type/actor marker per test"
  - "Audit endpoints use prefix path '' (GET '') matching the markets-router list pattern; the route is /api/v1/admin/audit-log (trailing-slash-free) and /event-types"

requirements-completed: [ADU-06, ADD-04]

# Metrics
duration: 12min
completed: 2026-05-28
---

# Phase 8 Plan 02: CSV Export & Read-Only Audit Log Viewer Summary

**CSV export endpoints (users/transactions/bets) with OWASP formula-injection protection, money-as-string + ISO-8601-UTC, and a 10k DoS cap; plus a strictly read-only, paginated, filterable audit-log viewer API exposing the JSONB payload as a raw JSON object — 35 new tests green (16 unit + 19 integration), 60/60 in the full tests/admin group.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-28T21:27Z
- **Completed:** 2026-05-28T21:39Z
- **Tasks:** 2
- **Files:** 9 (6 created, 3 modified)

## Accomplishments

### Task 1 — CSV export with injection protection (ADU-06, D-08..D-10)
- `app/admin/csv_export.py`: `sanitize_csv_cell` prefixes a single quote `'` to any cell beginning with a formula-trigger (`FORMULA_TRIGGERS = {"=", "+", "-", "@", "\t", "\r"}`, D-09/T-08-05). Three builders (`build_users_csv`, `build_transactions_csv`, `build_bets_csv`) use stdlib `csv.DictWriter` + `io.StringIO` (batch, D-10), render money via `str(Decimal)` (no symbol, no float) and timestamps via ISO 8601 UTC, sanitize every cell, and truncate to `MAX_EXPORT_ROWS = 10000` with a structlog warning (T-08-09).
- `app/admin/export_router.py`: `admin_export_router` (prefix `/api/v1/admin/export`, no `from __future__ import annotations`) with three admin-Bearer-gated GET endpoints returning `Response(media_type="text/csv", headers={Content-Disposition: attachment})`. `/users` accepts the same filters as the user list (D-08 "export the current filtered view"); `/transactions` + `/bets` accept an optional `user_id` scope.
- `AdminUserService.export_users/export_transactions/export_bets`: filtered reads. `export_users` reuses `_apply_user_filters` for filter parity; transactions/bets LEFT-JOIN `user_email` and compute realized P&L exactly like the detail reads. All DB-capped at `MAX_EXPORT_ROWS`.

### Task 2 — Read-only audit-log viewer (ADD-04, D-11..D-13)
- `app/core/audit/schemas.py`: `AuditLogItem` (`from_attributes=True`) with `payload: dict[str, Any]` (raw JSON object, D-12) + nullable `ip`. `KNOWN_EVENT_TYPES` — the 19-entry D-13 list for the frontend filter dropdown.
- `app/core/audit/router.py`: `audit_admin_router` (prefix `/api/v1/admin/audit-log`, no `from __future__ import annotations`), **GET-only** (T-08-07). `GET ""` → `PaginatedResponse[AuditLogItem]` (default `page_size=50`, D-11) filterable by `event_type` (exact), `actor` (wildcard-escaped ILIKE, T-08-08), `date_from`/`date_to` (`occurred_at` range), ordered `occurred_at DESC`. `GET /event-types` → `list[str]`. INET `ip` normalised to `str`.
- `app/main.py`: both `admin_export_router` and `audit_admin_router` wired (after `admin_crm_router`).

## Task Commits

1. **Task 1: CSV export endpoints with formula-injection protection (ADU-06)** — `dd61fc0` (feat)
2. **Task 2: read-only audit log viewer API with filters (ADD-04)** — `278d02e` (feat)

_TDD note: both tasks are `tdd="true"`. The pure CSV logic (`sanitize_csv_cell` + builders) was driven RED→GREEN by 16 standalone `@pytest.mark.unit` tests (no app/DB). The HTTP/DB layers are integration-test-driven via ASGITransport (the proven 08-01 approach — a failing-RED commit can't import until the router is mounted), so each task's router/queries and its integration tests were committed together. RED→GREEN was exercised iteratively in the loop (the first unit run RED-failed on a pytest-asyncio marker collision before the module mark was restructured; see Deviation 1)._

## Files Created/Modified
- `backend/app/admin/csv_export.py` — formula-injection sanitizer + 3 CSV builders + DoS cap (new).
- `backend/app/admin/export_router.py` — `admin_export_router`, 3 GET export endpoints (new).
- `backend/app/core/audit/router.py` — `audit_admin_router`, read-only viewer + event-types (new).
- `backend/app/core/audit/schemas.py` — `AuditLogItem` + `KNOWN_EVENT_TYPES` (new).
- `backend/app/admin/service.py` — added `export_users`/`export_transactions`/`export_bets` (modified).
- `backend/app/main.py` — wired both new routers (modified).
- `backend/tests/admin/_helpers.py` — added `seed_audit` helper (modified).
- `backend/tests/admin/test_csv_export.py` — 16 unit + 8 integration tests (new).
- `backend/tests/admin/test_audit_log.py` — 11 integration tests (new).

## Decisions Made
- **Export queries belong on `AdminUserService`.** The plan allowed "reuse query patterns from AdminUserService OR build direct queries". Putting `export_users/transactions/bets` on the existing service keeps the admin read surface in one module and lets `export_users` reuse `_apply_user_filters` verbatim — guaranteeing the CSV honours exactly the same filters as `GET /api/v1/admin/users` (D-08). Transactions/bets are direct joins (they need `user_email`, which the per-user detail reads don't include) with an optional `user_id` scope.
- **One CSV test file, per-test marks (not module `pytestmark`).** `test_csv_export.py` mixes SYNC unit tests with ASYNC integration tests. The established admin test files use a module-level `pytestmark = [integration, asyncio(...)]`, but those files have no sync tests. Applying that module mark here marked the sync unit tests with `@asyncio`, tripping pytest-asyncio's "marked with asyncio but not an async function" warning — which `filterwarnings=["error"]` escalates to a failure. Fix: drop the module mark; decorate each async integration test with `@pytest.mark.integration` + `@pytest.mark.asyncio(loop_scope="session")` explicitly. Unit tests carry `@pytest.mark.unit`.
- **`seed_audit` drives the real `AuditService.record`.** Rather than a raw `INSERT INTO audit_log`, the test helper calls the single allowed audit writer (D-20/D-21) through the app session-maker (which the `engine` fixture points at the testcontainer). `audit_log` is append-only (no cleanup), so each test seeds rows under a UNIQUE `event_type`/`actor` marker (uuid suffix) and scopes its assertions to those rows — the same fresh-marker discipline `_helpers.cleanup_user` documents for users.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest-asyncio marker collision on the mixed unit+integration CSV test file**
- **Found during:** Task 1 (first `pytest -m unit` run).
- **Issue:** A module-level `pytestmark` including `pytest.mark.asyncio(...)` (the pattern copied from the existing admin test files) applied the asyncio mark to the SYNC `sanitize_csv_cell`/builder unit tests, emitting `PytestWarning: ... marked with '@pytest.mark.asyncio' but it is not an async function`. With `filterwarnings = ["error"]` in `pyproject.toml`, all 16 unit tests errored.
- **Fix:** Removed the module-level `pytestmark` from `test_csv_export.py`; applied `@pytest.mark.integration` + `@pytest.mark.asyncio(loop_scope="session")` to each async integration test individually, and `@pytest.mark.unit` to the sync tests.
- **Files modified:** `backend/tests/admin/test_csv_export.py`
- **Verification:** `uv run pytest tests/admin/test_csv_export.py -m unit -q` → 16 passed; full file → 24 passed.
- **Committed in:** `dd61fc0`

**2. [Rule 3 - Blocking] mypy attr-defined / arg-type on fastapi-users base-table columns in export queries**
- **Found during:** Task 1 (mypy on `service.py`).
- **Issue:** `User.email.label(...)` and `User.id == <fk>` inside the new export joins raise `[attr-defined]` / `[arg-type]` under `mypy --strict` — fastapi-users' `SQLAlchemyBaseUserTableUUID` types `email`/`id` as plain `str`/`UUID`, not `InstrumentedAttribute`.
- **Fix:** Added the same `# type: ignore[attr-defined]` / `# type: ignore[arg-type]` annotations the EXISTING `service.py` code already uses for these exact columns (lines 165/204/466) — established convention, not a new suppression.
- **Files modified:** `backend/app/admin/service.py`
- **Verification:** `uv run mypy app/admin/service.py` → Success.
- **Committed in:** `dd61fc0`

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking test/type-checker issues). No bugs, no missing-critical functionality, no scope creep, no architectural changes.

## Threat Flags

None — no security surface beyond the plan's `<threat_model>` was introduced. All six dispositions are implemented + tested:
- **T-08-05** (CSV formula injection) → `sanitize_csv_cell` + negative test with `=SUM` cell AND an end-to-end `=cmd@evil.com` email sanitized on the wire.
- **T-08-06** (export endpoints auth) → `current_active_admin` on all 3 endpoints + 401/403 tests.
- **T-08-07** (audit log mutation) → GET-only router + a test asserting POST/PUT/PATCH/DELETE → 405; DB trigger + REVOKE still the backstop.
- **T-08-08** (ILIKE wildcard in actor search) → `_escape_like` + a test that a literal `%` does not act as a wildcard.
- **T-08-09** (unbounded CSV export) → `MAX_EXPORT_ROWS=10000` cap at the query and the builder + a unit test.
- **T-08-SC** (package installs) → none; Python stdlib `csv` + `io` only.

## Known Stubs

None — every endpoint is wired to real queries and returns real data. The audit `payload` is the raw JSONB object as stored (D-12, no v1 prettifying — intentional, not a stub). `KNOWN_EVENT_TYPES` is a deliberately hardcoded list per D-13 ("New event types added in future phases extend this list").

## Issues Encountered
- **Two PRE-EXISTING test failures under multi-group async load on Windows (NOT caused by 08-02), logged in `deferred-items.md`:**
  1. `tests/core/test_audit_immutability.py::test_audit_log_delete_blocked` fails as the 4th test in its file (a prior test raises a `DBAPIError` without a `begin_nested()` savepoint, poisoning the shared session) — PASSES in isolation. This is the EXACT latent flaw already logged in STATE.md (2026-05-27, Plan 03-01). The 08-02 audit viewer is read-only and never writes/updates/deletes audit rows.
  2. `tests/wallet/test_concurrent_transfers.py::test_50_concurrent_overdraft` fails when run alongside `tests/admin tests/wallet tests/bets` — PASSES in isolation. The documented session-scoped-testcontainer collapse under large async load ("CI-Linux-only, won't true-green on Windows"). 08-02 touches none of the wallet concurrency write path.
- **ResourceWarning teardown noise on Windows.** After a green run, testcontainer/asyncpg socket GC prints `ResourceWarning: unclosed ...` lines AFTER the passed summary — post-session interpreter-shutdown noise, not a test failure (same as 08-01).

## Verification Evidence
- `uv run pytest tests/admin/test_csv_export.py -m unit -q` → **16 passed** (pure logic, no container).
- `uv run pytest tests/admin/test_csv_export.py -x -q` → **24 passed** (Task 1 acceptance).
- `uv run pytest tests/admin/test_audit_log.py -x -q` → **11 passed** (Task 2 acceptance).
- `uv run pytest tests/admin -q` → **60 passed** (full admin group: 25 from 08-01 + 35 new; no regressions).
- `uv run ruff check app/admin/csv_export.py app/admin/export_router.py app/core/audit/router.py app/core/audit/schemas.py` → All checks passed.
- `uv run mypy app/admin/csv_export.py app/admin/export_router.py app/core/audit/router.py app/core/audit/schemas.py app/admin/service.py` → Success, no issues.
- `uv run python scripts/lint_money_columns.py` → OK, 6 files checked, 0 warnings.
- Both task commits passed the gitleaks + money-lint pre-commit hooks (no `--no-verify`).
- Adjacent-suite isolation confirmed: `tests/core/test_audit_immutability.py::test_audit_log_delete_blocked` and `tests/wallet/test_concurrent_transfers.py` both → passed in isolation (the two multi-group failures above are pre-existing environmental flakes).

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- The export endpoints (`/api/v1/admin/export/{users,transactions,bets}`) and the audit-log viewer (`GET /api/v1/admin/audit-log` + `/event-types`) are ready for the **Plan 08-03 frontend** to consume — the audit dropdown reads `GET /event-types` (the D-13 list).
- The audit-log viewer is strictly read-only at the API level (GET-only, 405 on mutation) on top of the Phase 1 DB-level immutability (trigger + REVOKE) — the PITFALL #6 trust signal is complete.
- No blockers from this plan.

## Self-Check: PASSED
- All 6 created files + 3 modified files verified present on disk.
- The SUMMARY (`08-02-SUMMARY.md`) verified present.
- Both task commits (`dd61fc0`, `278d02e`) verified present in git history.

---
*Phase: 08-admin-crm-user-management-audit-log-viewer*
*Completed: 2026-05-28*
