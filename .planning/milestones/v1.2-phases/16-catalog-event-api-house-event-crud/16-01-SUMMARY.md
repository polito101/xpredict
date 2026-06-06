---
phase: 16-catalog-event-api-house-event-crud
plan: 01
subsystem: testing
tags: [catalog, test-scaffold, testcontainers, httpx, asgitransport, pytest, factories, seed]

# Dependency graph
requires:
  - phase: 13-catalog-model
    provides: market_groups table + Market.group_id/group_item_title (event-of-binaries seam)
  - phase: 15-event-settlement
    provides: derive_event_status / ChildStatus projection + EventService resolve/void/reverse (the four states the factories drive children into)
provides:
  - tests/catalog test package with a shared httpx AsyncClient + ASGITransport fixture (Wave-0 infra)
  - seed-factory module (make_market, make_event, place_bet_on_child, resolve_child + per-state event drivers, admin auth helpers)
  - ledger-backed bet seeding (WalletService.recharge) that keeps the spike-004 drift_count==0 invariant valid for later tests
affects: [16-02, 16-03, 16-04, 16-05, catalog-api, event-crud, edit-lock, admin-event-settle]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wave-0 test scaffold: a per-feature tests/<area>/ package whose conftest inherits the heavyweight engine/async_session fixtures from the parent backend/tests/conftest.py (no redefinition) and adds only the api client + autouse testcontainer/override fixtures"
    - "Two-session seed boundary (Pitfall 5): pure ORM writes ride the caller's (possibly rolled-back) session via flush(); the ledger writer (WalletService.recharge, owns its own begin()+commit) runs on a FRESH _get_session_maker() session"
    - "Non-financial event-state setup: drive a group to each derive_event_status state by direct Market.status + winning_outcome_id mutation (case-insensitive YES), no money movement"

key-files:
  created:
    - backend/tests/catalog/__init__.py
    - backend/tests/catalog/conftest.py
    - backend/tests/catalog/_factories.py
  modified: []

key-decisions:
  - "place_bet_on_child funds the wallet via the REAL WalletService.recharge on its own committed session (ledger-backed, drift-clean), then writes the Bet row directly on the caller's session — the edit-lock only needs EXISTS(bets), no market-source view/liability movement required"
  - "Per-state event drivers (drive_event_open/partial/resolved/void) mutate child status + winning_outcome_id directly (the plan's allowed non-financial state path) consistent with event_service._derive_status; resolve_event/void_event remain the financial path tested elsewhere"
  - "make_event children are each exactly YES + NO (binary trigger never trips); every money/odds value is a Decimal"

patterns-established:
  - "tests/catalog package = the import surface every Wave-1+ Phase-16 plan reuses (api client + factories) instead of redefining infra"
  - "ledger-backed seed wallets (INSERT at 0 + recharge) over raw-balance writes, preserving spike-004 reconciliation"

requirements-completed: [BRW-01, BRW-02, BRW-03, BRW-04, BRW-05]

# Metrics
duration: ~12min
completed: 2026-06-05
---

# Phase 16 Plan 01: Catalog Test Scaffold Summary

**Wave-0 `tests/catalog/` package — a shared httpx AsyncClient/ASGITransport fixture plus a seed-factory module that builds standalone markets and ≥2-child events drivable to open/partially_resolved/resolved/void states, with ledger-backed bets via `WalletService.recharge`.**

## Performance

- **Duration:** ~12 min (continuation; Task 1 by a prior executor, Task 2 + tracking here)
- **Completed:** 2026-06-05
- **Tasks:** 2 (Task 1 prior commit `86db7a8`, Task 2 this session)
- **Files created:** 3 (`__init__.py`, `conftest.py`, `_factories.py`)

## Accomplishments

- **`tests/catalog/_factories.py`** (457 lines) — the row-shape synthesizer every Wave-1+ Phase-16 plan imports:
  - `make_market` — standalone binary market (`group_id=None`) + YES/NO outcome pair (mirrors `markets/service.py` create body; never a 3rd outcome).
  - `make_event` — one `MarketGroup` (`slug=generate_slug(title)`) + N binary YES/NO children stamped `group_id`/`group_item_title`; returns `(group, children)`.
  - `place_bet_on_child` — seeds a **ledger-backed** wallet (INSERT at 0 + `WalletService.recharge` on a fresh committed session) then a `Bet` row on the caller's session so `EXISTS(bets)` flips (drives the EVA-02 edit-lock 423).
  - `resolve_child` (+ `resolve_child_yes`/`_no`) and per-state drivers `drive_event_open` / `drive_event_partial` / `drive_event_resolved` / `drive_event_void`, consistent with `event_service._derive_status` (case-insensitive YES).
  - `_Admin` + `admin_override(user_id)` (overrides `current_active_admin`) and `seed_admin(session)` (real superuser via `pwdlib` on a committed session, mirror `test_public_router.py:_seed_admin`).
- All money/odds values are `Decimal` (never float); each child is exactly YES + NO so `trg_binary_outcomes_only` never trips.
- Task 1's `conftest.py` (shared `api` client + autouse `_require_testcontainer`/`_clear_overrides`) inherited unchanged; this plan added no production code (`backend/app/` untouched).

## Task Commits

1. **Task 1: tests/catalog package + shared AsyncClient fixture** — `86db7a8` (test) — *prior executor; not redone*
2. **Task 2: seed-factory module** — `863c08a` (test)

**Plan metadata:** this commit (docs).

## Files Created/Modified

- `backend/tests/catalog/__init__.py` — catalog test package marker (Task 1).
- `backend/tests/catalog/conftest.py` — `api` AsyncClient (`ASGITransport`, `raise_app_exceptions=False`) + autouse testcontainer/override fixtures; reuses parent `engine`/`async_session` (Task 1).
- `backend/tests/catalog/_factories.py` — seed factories: `make_market`, `make_event`, `place_bet_on_child`, `resolve_child` + per-state event drivers, `_Admin`/`admin_override`/`seed_admin` (Task 2).

## Verification

- **`cd backend && uv run pytest tests/catalog --co -q` → exit 5 ("no tests collected").** This is the **correct** Wave-0 state: the scaffold intentionally ships zero test functions (only `__init__.py`/`conftest.py`/`_factories.py`). The `conftest.py` imports with no collection error.
- **`_factories.py` imports cleanly → verified exit 0.** Because pytest collection only imports `conftest.py`/`test_*.py` (never a `_`-prefixed helper), import-cleanliness was proven by a throwaway `test_zzz_import_smoke.py` that `import`ed `_factories` and asserted all 10 required exports — it collected at exit 0 (proving the full import chain — `app.main`, `WalletService`, models — resolves), and was then **deleted** (not part of the shipped scaffold).
- `git diff --stat` for the task commit shows only `backend/tests/catalog/_factories.py` (+457); no `backend/app/` change, no deletions.

> Note: the Windows-worktree pytest flake (testcontainers contention) is irrelevant here — the check is collection-only (`--co`), which spawns no Postgres container. Trust Linux CI for the full suite.

## Decisions Made

See frontmatter `key-decisions`. In short: ledger-backed wallet via real `recharge` on a fresh committed session (drift-clean); direct status-mutation per-state drivers for the non-financial state setup the plan allows; binary-only YES/NO children with all-`Decimal` money/odds.

## Deviations from Plan

None — plan executed exactly as written. Task 2 implements the `_factories.py` spec verbatim (all named helpers present, ledger-backed bets via `WalletService.recharge`, binary-trigger-safe, `Decimal`-only).

## Issues Encountered

- A bare `python -c "import tests.catalog._factories"` fails (`Settings` missing `DATABASE_URL` etc.) because the env vars are seeded by `tests/conftest.py` at import time, which a non-pytest process bypasses. **Not a code issue** — the module imports cleanly under pytest (proven above). Resolved by verifying import via a pytest-collected smoke test rather than a bare interpreter.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Waves 1–3 of Phase 16 (catalog list/detail API, event CRUD, edit-lock, admin event settle) can now `from tests.catalog._factories import ...` and `from tests.catalog.conftest` (the `api` client) instead of redefining infrastructure.
- The four `derive_event_status` states and ledger-backed bets are seedable, so later plans write behavior tests, not boilerplate.

## Self-Check: PASSED

- `backend/tests/catalog/__init__.py` — FOUND
- `backend/tests/catalog/conftest.py` — FOUND
- `backend/tests/catalog/_factories.py` — FOUND
- Commit `86db7a8` (Task 1) — FOUND in git history
- Commit `863c08a` (Task 2) — FOUND in git history
- `_factories.py` import-cleanliness — VERIFIED (smoke collection exit 0)
- `backend/app/` unmodified by this plan — VERIFIED (task commit touches only `tests/catalog/`)

---
*Phase: 16-catalog-event-api-house-event-crud*
*Completed: 2026-06-05*
