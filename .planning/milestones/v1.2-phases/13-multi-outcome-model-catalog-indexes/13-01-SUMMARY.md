---
phase: 13-multi-outcome-model-catalog-indexes
plan: 01
subsystem: database
tags: [postgres, sqlalchemy, alembic, pg_trgm, gin-index, multi-outcome, market-groups, schema-migration]

# Dependency graph
requires:
  - phase: 12-resolution-and-stake-limits
    provides: "Migration head 0010_phase12_resolution_stakes (the down_revision 0011 chains off)"
  - phase: 04-markets
    provides: "Market/Outcome/OddsSnapshot ORM + markets table + ix_odds_snapshots_outcome_id + trg_binary_outcomes_only trigger"
  - phase: 06-polymarket-sync
    provides: "Partial-unique index precedent (source, source_market_id) + Market.volume_24hr"
provides:
  - "market_groups table (UUID PK, title, source, source_event_id, category, slug, created_at/updated_at, tenant_id ghost)"
  - "Nullable Market.group_id (FK -> market_groups.id ON DELETE SET NULL) + Market.group_item_title"
  - "pg_trgm extension + 6 catalog/search indexes (2 GIN trigram, 1 partial-unique, category x2, status+volume_24hr, odds composite)"
  - "MarketGroup ORM model + bidirectional MarketGroup.markets <-> Market.group relationship (lazy=raise, NO cascade)"
  - "Reversible migration 0011_phase13_market_groups (real downgrade, leaves pg_trgm)"
affects: [14-catalog-sync, 15-event-settlement, 16-catalog-api, 17-catalog-ui, 18-seed-demo]

# Tech tracking
tech-stack:
  added: ["pg_trgm (Postgres-bundled extension — first GIN trigram index in the repo)"]
  patterns:
    - "GIN trigram index via op.create_index(postgresql_using='gin', postgresql_ops={col: 'gin_trgm_ops'})"
    - "Every migration index ALSO declared in the model __table_args__ (byte-identical names) for Base.metadata drift-avoidance"
    - "FK to a soft-grouping parent uses ondelete=SET NULL + relationship WITHOUT cascade (orphan, never delete financial rows)"

key-files:
  created:
    - "backend/alembic/versions/0011_phase13_market_groups.py"
    - ".planning/phases/13-multi-outcome-model-catalog-indexes/deferred-items.md"
  modified:
    - "backend/app/markets/models.py"
    - "backend/app/markets/__init__.py"
    - "backend/alembic/env.py"

key-decisions:
  - "No status/winning_outcome column on market_groups — event status is DERIVED in Phase 15 (EVT-06), never stored"
  - "downgrade() deliberately does NOT drop pg_trgm (DB-global, idempotent, may be shared) — reversibility satisfied by restoring schema objects (RESEARCH A1)"
  - "Market.group_id FK = ON DELETE SET NULL (never CASCADE) + NO relationship cascade — child markets carry bets/odds/ledger and must orphan, never delete"
  - "Composite ix_odds_snapshots_outcome_id_snapshot_at is ADDITIVE alongside the existing single-column ix_odds_snapshots_outcome_id (not dropped)"

patterns-established:
  - "GIN trigram (pg_trgm) infix-search index — the first in the repo; pg_trgm enabled FIRST in upgrade() before any GIN index"
  - "Index declared in BOTH the migration AND the model __table_args__ (drift-avoidance); verified by alembic autogenerate compare_metadata producing zero diff on Phase 13 objects"

requirements-completed: [EVT-01]

# Metrics
duration: 8min
completed: 2026-06-05
---

# Phase 13 Plan 01: Multi-outcome Model & Catalog Indexes Summary

**Event-of-binaries database seam: reversible migration 0011 creates `market_groups` + nullable `Market.group_id`/`group_item_title` + pg_trgm + 6 catalog/search indexes, with a `MarketGroup` ORM model and a `lazy="raise"` no-cascade relationship — pure additive, existing binary markets byte-for-byte unchanged.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-05T09:50:21Z
- **Completed:** 2026-06-05T09:58:31Z
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified) + 1 deferred-items log

## Accomplishments
- Reversible Alembic migration `0011_phase13_market_groups` chaining off `0010_phase12_resolution_stakes` as the single head — verified upgrade → downgrade -1 → upgrade round-trip against a real `postgres:16-alpine`.
- `market_groups` table (UUID PK, `tenant_id` ghost column, no money/status column, no seed row) + two nullable `markets` columns (`group_id` FK SET NULL, `group_item_title`) with no backfill.
- `pg_trgm` extension (enabled first) + all 6 catalog/search indexes: 2 GIN trigram (`gin_trgm_ops`), partial-unique `(source, source_event_id) WHERE source_event_id IS NOT NULL`, `category` on both tables, `(status, volume_24hr)`, and the composite `(outcome_id, snapshot_at)` on `odds_snapshots`.
- `MarketGroup` ORM model + bidirectional `MarketGroup.markets` ↔ `Market.group` relationship (`lazy="raise"`, NO cascade), exported from `markets/__init__.py` and registered in `alembic/env.py`.
- Every index declared in both the migration and the model `__table_args__` (byte-identical names) — verified zero `alembic` autogenerate drift on Phase 13 objects.
- 98 existing markets tests pass against the new schema (SC#2 / EVT-01: binary read/bet/settle path + `trg_binary_outcomes_only` trigger unchanged).

## Task Commits

Each task was committed atomically:

1. **Task 1: Author reversible migration 0011_phase13_market_groups** — `fd2aab8` (feat)
2. **Task 2: Add MarketGroup ORM + Market.group seam; wire __init__ and env** — `810090c` (feat)

**Plan metadata:** (final docs commit — SUMMARY.md, STATE.md, ROADMAP.md)

## Files Created/Modified
- `backend/alembic/versions/0011_phase13_market_groups.py` (created) - Reversible additive migration: `market_groups` table, 2 nullable `Market` columns, `pg_trgm`, all 6 indexes; `downgrade()` reverses exactly and leaves `pg_trgm`.
- `backend/app/markets/models.py` (modified) - `MarketGroup` class + `Market.group_id`/`group_item_title`/`group` relationship + the 6 indexes in `__table_args__` (incl. the odds composite on `OddsSnapshot`); added `Index`/`text` imports.
- `backend/app/markets/__init__.py` (modified) - Export `MarketGroup` in the import + `__all__`.
- `backend/alembic/env.py` (modified) - Register `MarketGroup` against `Base.metadata` for autogenerate.
- `.planning/phases/13-multi-outcome-model-catalog-indexes/deferred-items.md` (created) - Logs pre-existing (non-Phase-13) ORM↔migration autogenerate drift, out of scope.

## Decisions Made
- **No `status` column on `market_groups`** — although the RESEARCH Pattern 1 example showed one (with an explicit Note A flagging it for removal), the plan `<action>`, RESEARCH A3, PATTERNS, and EVT-06 all require event status be DERIVED in Phase 15, never stored. Followed the plan (no `status`).
- **`downgrade()` leaves `pg_trgm`** — extensions are DB-global/idempotent and may be shared; reversibility (SC#1) is satisfied by restoring the schema objects (RESEARCH A1). Documented in the migration docstring.
- **FK `ON DELETE SET NULL` + relationship with NO cascade** — the one real threat (T-13-01): child markets carry bets/odds/ledger state, so deleting a group must orphan children back to standalone, never delete financial rows.
- **Verification harnesses were throwaway** — the committed introspection + ORM round-trip tests are Plan 13-02's deliverable (Wave 2). For immediate proof this plan used two temporary `postgres:16-alpine` harnesses (deleted after use), so no uncommitted test files remain.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking / drift-avoidance] Declared the odds composite index on `OddsSnapshot.__table_args__`**
- **Found during:** Task 2 (MarketGroup ORM + verification)
- **Issue:** The plan `<action>` for Task 2 listed the indexes to add to `MarketGroup` and `Market.__table_args__` but did not mention the 6th index (`ix_odds_snapshots_outcome_id_snapshot_at`, on `odds_snapshots`). The migration (Task 1) creates it, so `Base.metadata` was missing it — `alembic` autogenerate `compare_metadata` reported a `remove_index` drift, meaning a future `--autogenerate` would try to DROP the production index. The plan's own acceptance criterion ("all index names match the migration byte-for-byte") and `must_haves.truths` (no drift) require the model to declare every migration index.
- **Fix:** Added `Index("ix_odds_snapshots_outcome_id_snapshot_at", "outcome_id", "snapshot_at")` to `OddsSnapshot.__table_args__` (byte-identical to the migration; additive alongside the existing `index=True` single-column index on `outcome_id`).
- **Files modified:** `backend/app/markets/models.py`
- **Verification:** `alembic` autogenerate `compare_metadata(MigrationContext, Base.metadata)` now reports zero diff on all Phase 13 objects; 98 markets tests pass.
- **Committed in:** `810090c` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking / drift-avoidance).
**Impact on plan:** Necessary to satisfy the plan's own byte-identical-index acceptance criterion and the no-drift `must_have`. No scope creep — the index itself was already specified in Task 1; the fix only mirrors it into the ORM as the repo convention requires.

## Issues Encountered
- The dev `docker compose` stack was not running and is missing `SECRET_KEY`/`ADMIN_JWT_PUBLIC_SECRET` env vars, so the plan's `docker compose exec backend uv run alembic ...` verify form was not directly usable. Resolved by using the repo's testcontainers path (the same `postgres:16-alpine` the test suite spins up) with the conftest `_DEFAULT_TEST_ENV` vars — a strictly more reliable Postgres-16 proof. All acceptance criteria were verified this way.

## Deferred / Not Verified Here (lands in Plan 13-02, Wave 2)
- The committed automated tests for SC#1 (apply + reversibility + chain), SC#3 (pg_trgm + all 6 indexes via `pg_indexes.indexdef` introspection), and SC#4 (ORM round-trip ≥2 children + `lazy="raise"` + `group_id IS NULL` regression) are authored in Plan 13-02 (`tests/markets/test_migration_0011.py` + additions to `tests/markets/test_models.py`). They did not exist in this plan's scope; this plan proved the same criteria with throwaway harnesses + the existing 98-test markets regression suite. Reported as **deferred-to-13-02** rather than claimed as committed-test-passing.

## User Setup Required
None - no external service configuration required. `pg_trgm` is enabled inside the migration; no new env vars, no new dependencies.

## Next Phase Readiness
- The additive schema seam is complete and reversible: Phase 14 (Gamma `/events` sync) can write `market_groups` rows and stamp `Market.group_id`, using the `(source, source_event_id)` partial-unique index for `ON CONFLICT` upserts.
- Phase 16 catalog search can use the `ix_markets_question_trgm` / `ix_market_groups_title_trgm` GIN indexes via parameterized `ilike` (forward constraint T-13-02: never f-string the term).
- Plan 13-02 (Wave 2) must add the committed migration-introspection + ORM round-trip tests to lock SC#1/SC#3/SC#4 automatically.

## Self-Check: PASSED

---
*Phase: 13-multi-outcome-model-catalog-indexes*
*Completed: 2026-06-05*
