---
phase: 13-multi-outcome-model-catalog-indexes
plan: 02
subsystem: testing
tags: [pytest, testcontainers, postgres, alembic, pg_trgm, gin-index, selectinload, migration-introspection, sqlalchemy]

# Dependency graph
requires:
  - phase: 13-multi-outcome-model-catalog-indexes (Plan 13-01)
    provides: "Migration 0011_phase13_market_groups (market_groups table, nullable Market.group_id/group_item_title, pg_trgm, 6 indexes) + MarketGroup ORM + Market.group lazy=raise seam"
  - phase: 01-foundations (Plan 01-03)
    provides: "testcontainers PG16 engine fixture (runs alembic upgrade head) + async_session outer-transaction/savepoint fixture in tests/conftest.py"
  - phase: 02-auth / 03-wallet
    provides: "Migration-introspection test analogs (test_migration_0002.py inspect/run_sync + ScriptDirectory chain; test_migration_0003.py raw text() DDL + begin_nested savepoint)"
provides:
  - "tests/markets/test_migration_0011.py — automated SC#1 (apply + reversibility + chain/down_revision/single-head) and SC#3 (pg_trgm + all 6 indexes via pg_indexes.indexdef incl. GIN gin_trgm_ops opclass + partial WHERE) proofs"
  - "tests/markets/test_models.py extension — automated SC#4 (MarketGroup selectinload round-trip >=2 children + Market.group lazy=raise) and SC#2 (group_id IS NULL standalone regression)"
  - "Test-enforcement of threat T-13-01: markets.group_id FK ondelete == SET NULL asserted in CI (CASCADE regression fails the build)"
affects: [14-catalog-sync, 15-event-settlement, 16-catalog-api, 17-catalog-ui, 18-seed-demo]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "First migration-introspection test under tests/markets/ (cloned from tests/auth + tests/wallet analogs)"
    - "GIN gin_trgm_ops opclass + partial WHERE verified via raw pg_indexes.indexdef DDL, not get_indexes() structured fields (RESEARCH A4)"
    - "Reversibility (SC#1) proven via deterministic static downgrade-mirrors-upgrade source parse instead of a live cycle on the session-scoped engine (RESEARCH A5 fallback — avoids cross-test schema disturbance)"
    - "pytest.mark.parametrize over index names to assert each GIN/B-tree index individually"

key-files:
  created:
    - "backend/tests/markets/test_migration_0011.py"
  modified:
    - "backend/tests/markets/test_models.py"

key-decisions:
  - "Reversibility (SC#1) uses a static downgrade-mirrors-upgrade source parse (deterministic, no shared-engine disturbance), not a live command.downgrade/upgrade cycle — the session-scoped engine is at head and a live downgrade would drop market_groups out from under other markets tests"
  - "GIN gin_trgm_ops opclass + partial WHERE asserted via raw pg_indexes.indexdef (get_indexes() does not reliably surface them across dialects; RESEARCH A4)"
  - "No expire() before a selectinload round-trip — calling async_session.expire() triggered MissingGreenlet during attribute refresh; selectinload populates the relationship without it"
  - "The sync reversibility test is declared async def to satisfy the module-level pytestmark asyncio mark (suite runs under filterwarnings=error; an asyncio mark on a sync function would fail)"

patterns-established:
  - "Migration introspection under tests/markets/: inspect()+run_sync for columns/FKs, raw text()/pg_indexes.indexdef for GIN opclass + partial WHERE, ScriptDirectory.get_revision for the chain/single-head guard"
  - "MarketGroup round-trip mirrors TestMarketCreation's selectinload pattern with a _child_market builder carrying the full valid binary Market kwargs"

requirements-completed: [EVT-01]

# Metrics
duration: 10min
completed: 2026-06-05
---

# Phase 13 Plan 02: Multi-outcome Model & Catalog Indexes — Test Layer Summary

**Wave-2 automated Nyquist proof for every Phase 13 SC: a new migration-introspection test (apply + reversibility + chain + pg_trgm + all 6 indexes via raw `pg_indexes.indexdef`) and a `MarketGroup` ORM round-trip extension (selectinload >=2 children + `lazy="raise"` + `group_id IS NULL` regression) — 117 markets tests + 92 bets/settlement tests green, money-lint clean.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-05T10:00:00Z (approx)
- **Completed:** 2026-06-05T10:10:00Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 extended)

## Accomplishments
- `tests/markets/test_migration_0011.py` (NEW, 349 lines, first migration test under `tests/markets/`) — 14 tests automating SC#1 + SC#3:
  - SC#1 apply: `market_groups` columns + `markets.group_id`/`group_item_title` present (`inspect`/`run_sync`).
  - SC#1 financial safety (T-13-01): `markets.group_id` FK is `ON DELETE SET NULL` — a CASCADE regression now fails CI.
  - SC#1 chain: `down_revision == "0010_phase12_resolution_stakes"` (revision id, not filename stem) AND exactly one head named `0011_phase13_market_groups` (Pitfall-2 guard).
  - SC#1 reversibility: `downgrade()` mirrors every `create_table`/`add_column`/`create_index`/`create_foreign_key` with a matching drop, and does NOT drop `pg_trgm` (RESEARCH A1).
  - SC#3: `pg_trgm` enabled; both GIN trigram indexes carry `gin_trgm_ops`; the partial-unique index has `WHERE source_event_id`; the 4 B-tree catalog indexes exist; the pre-existing single-column `ix_odds_snapshots_outcome_id` is retained alongside the new composite (additive).
- `tests/markets/test_models.py` (EXTENDED, +137 net) — 8 new tests automating SC#4 + SC#2:
  - SC#4: a `MarketGroup` round-trips a parent + 2 children via `selectinload(MarketGroup.markets)`, with the expected `group_item_title` set and every child's `group_id` pointing back to the parent.
  - SC#4: `Market.group` access without eager-load raises `InvalidRequestError` matching `lazy='raise'`.
  - SC#2: the standalone `sample_market` has `group_id`/`group_item_title` NULL and still round-trips its 2 YES/NO outcomes unchanged — the additive columns did not alter the binary path.
- Verification gates all green against a real `postgres:16-alpine` (testcontainers): markets module **117 passed**, bets+settlement **92 passed** (SC#2 zero-behavior-change), money-lint exit 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create test_migration_0011.py (apply + reversibility + chain + pg_trgm + 6 indexes)** — `9b41148` (test)
2. **Task 2: Extend test_models.py — MarketGroup round-trip + lazy=raise + group_id IS NULL regression** — `fb4cf60` (test)

**Plan metadata:** (final docs commit — this SUMMARY.md, STATE.md, ROADMAP.md)

## Files Created/Modified
- `backend/tests/markets/test_migration_0011.py` (created) — 14 migration-introspection tests: column/FK presence via `inspect`+`run_sync`; `pg_trgm` + GIN `gin_trgm_ops` + partial `WHERE` + B-tree indexes via raw `pg_indexes.indexdef`; chain/single-head via `ScriptDirectory`; static downgrade-mirrors-upgrade reversibility parse.
- `backend/tests/markets/test_models.py` (modified) — added `MarketGroup` import, a `_child_market` builder, and three test classes (`TestMarketGroup`, `TestMarketGroupLazyRaise`, `TestStandaloneMarketRegression`); no existing test modified or removed.

## Decisions Made
- **Reversibility harness = static source parse, not a live downgrade/upgrade cycle.** RESEARCH A5 authorized either; the session-scoped `engine` fixture is already at head and shared across all markets tests, so a live `command.downgrade("-1")` would briefly drop `market_groups` out from under other tests and, if it failed mid-cycle, break the whole session (`InFailedSQLTransactionError` cascade). The static parse asserts the contract that matters — `downgrade()` is non-empty and drops exactly what `upgrade()` creates, and deliberately does NOT drop `pg_trgm` — deterministically and side-effect-free. (The live upgrade→downgrade→upgrade round-trip was already exercised against a real PG16 while authoring 13-01; see 13-01-SUMMARY "Decisions Made".)
- **GIN opclass + partial WHERE via raw `pg_indexes.indexdef`** (RESEARCH A4) — `inspect(...).get_indexes()` does not reliably surface the `gin_trgm_ops` opclass or the partial predicate; the raw DDL string is the source of truth.
- **Parametrized per-index assertions** so a single missing/renamed index fails with a precise name rather than a blanket "indexes mismatch".

## Deviations from Plan

None — plan executed exactly as written. Both test artifacts were delivered with the assertions specified in the plan `<action>` blocks, and the optional reversibility fallback was selected per the plan's explicit guidance (Task 1 `<action>` step 9 + RESEARCH A5). No production code was touched (test-only plan), and no production bug was found in the migration or ORM under test.

## Issues Encountered

Two self-inflicted test-authoring bugs, both caught by running the suite for real and fixed inline before either task commit landed (no broken commit ever recorded):

1. **`pytest.PytestWarning` on the sync reversibility test → failure under `filterwarnings=error`.** The module-level `pytestmark` applies `@pytest.mark.asyncio` to every test; the initially-synchronous `test_downgrade_mirrors_upgrade` tripped "asyncio mark on a non-async function", which the suite's `filterwarnings=error` turns into a failure. **Fix:** declared the test `async def` (its body is pure source-text parsing — no I/O), with a docstring explaining why. Re-ran: 14/14 green.
2. **`MissingGreenlet` in the `MarketGroup` round-trip.** I had added `async_session.expire(grp)` / `expire(child)` before the `selectinload` query; the subsequent implicit attribute refresh attempted lazy I/O outside the async greenlet context. **Fix:** removed the unnecessary `expire()` calls — `selectinload` populates `.markets` directly, and the un-loaded `.group` still raises `lazy='raise'` on access without a re-expire. Re-ran `-k "group or lazy"`: 5/5 green, then full `test_models.py`: 23/23 green.

Also (environment noise, not a failure): pytest emits `ResourceWarning: unclosed <socket/asyncpg connection>` lines on Windows during testcontainer teardown. These are pre-existing teardown artifacts, not test failures — the pass/fail summary lines confirm all green.

## Verification (real output)

- `cd backend && uv run pytest tests/markets/test_migration_0011.py -x` → **14 passed in 3.53s**
- `cd backend && uv run pytest tests/markets/test_migration_0011.py -k chain -x` → **1 passed, 13 deselected**
- `cd backend && uv run pytest tests/markets/test_migration_0011.py -k index -x` → **7 passed, 7 deselected**
- `cd backend && uv run pytest tests/markets/test_models.py -x` → **23 passed in 3.68s**
- `cd backend && uv run pytest tests/markets/` → **117 passed in 14.38s**
- `cd backend && uv run pytest tests/bets/ tests/settlement/` → **92 passed in 6.06s** (SC#2 zero-behavior-change proof)
- `cd backend && uv run python scripts/lint_money_columns.py` → **OK: 7 files checked, 2 warnings** (exit 0; the 2 warnings are the pre-existing BET-06 `min_stake`/`max_stake` NULLABLE-money exception on `Market`, not Phase 13)

## User Setup Required
None — no external service configuration required. Tests run against the existing testcontainers PG16 fixture; no new env vars, no new dependencies.

## Next Phase Readiness
- Every Phase 13 SC (1, 2, 3, 4) and EVT-01 now has a committed, automated `uv run pytest` proof — the phase is ready for `/gsd-verify-work`.
- Phase 14 (Gamma `/events` sync) can write `market_groups` rows and stamp `Market.group_id` against a schema whose shape, FK safety (`SET NULL`), and partial-unique upsert index are all test-locked.
- Forward constraint (T-13-02, owned by Phase 16): never f-string a search term into the `ix_*_trgm` GIN-backed `ilike` — use bound params. Not exercised here (no query written in Phase 13).

## Self-Check: PASSED

- FOUND: backend/tests/markets/test_migration_0011.py (349 lines; contains `ix_markets_question_trgm`, `pg_indexes` x6)
- FOUND: backend/tests/markets/test_models.py (contains `MarketGroup` x12, `selectinload(MarketGroup.markets)`)
- FOUND commit: 9b41148 (Task 1, test)
- FOUND commit: fb4cf60 (Task 2, test)

---
*Phase: 13-multi-outcome-model-catalog-indexes*
*Completed: 2026-06-05*
