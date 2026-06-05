---
phase: 13-multi-outcome-model-catalog-indexes
verified: 2026-06-05T11:30:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 13: Multi-outcome Model & Catalog Indexes — Verification Report

**Phase Goal:** The database can represent a multi-outcome event as a group of N independent binary markets, with every catalog/search index in place — and existing binary markets behave exactly as before. PURE ADDITIVE schema + ORM + indexes (one reversible Alembic migration `0011`). The gate that unblocks v1.2 Phases 14-18.
**Verified:** 2026-06-05T11:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Migration `0011_phase13_market_groups` applies cleanly AND is reversible (real `downgrade()`), creating `market_groups` + nullable `Market.group_id`/`group_item_title` — no backfill, no downtime. | VERIFIED | `test_market_groups_table_columns`, `test_markets_has_group_columns`, `test_downgrade_mirrors_upgrade` — 15/15 migration tests pass against real postgres:16-alpine (testcontainers). Downgrade body confirmed non-empty, drops exactly what upgrade creates, does NOT drop pg_trgm. |
| 2 | An existing standalone (`group_id IS NULL`) binary market is read, bet on, and settled EXACTLY as before — zero behavior change. | VERIFIED | `tests/bets/ tests/settlement/` — 92 passed. `TestStandaloneMarketRegression` (2 tests): `sample_market.group_id is None`, outcomes still load 2 YES/NO unchanged. `trg_binary_outcomes_only` trigger still fires (TestBinaryOnlyTrigger passes). |
| 3 | The migration enables `pg_trgm` and creates all 6 indexes (GIN trigram on `market_groups.title` + `markets.question` with `gin_trgm_ops`; partial-unique on `market_groups(source, source_event_id) WHERE source_event_id IS NOT NULL`; `markets(category)`; `markets(status, volume_24hr)`; composite `odds_snapshots(outcome_id, snapshot_at)`). | VERIFIED | `test_pg_trgm_enabled`, `test_gin_trgm_indexes_have_opclass` (parametrized x2 — opclass tied to column, not just substring), `test_partial_unique_has_where_clause` (asserts IS NOT NULL polarity), `test_btree_catalog_indexes_exist` (4 B-tree indexes), `test_composite_index_column_order` (leading-column order pinned), `test_existing_odds_outcome_id_index_retained` (additive, 0003 index preserved). All pass. |
| 4 | The `MarketGroup` ORM model + `MarketGroup ↔ Market` relationship load via the async session and round-trip a parent group with ≥2 children. | VERIFIED | `TestMarketGroup.test_group_round_trips_two_children`: parent + 2 children flush, selectinload returns `len(loaded.markets) == 2`, group_item_titles correct, group_id FK back-pointer verified. `TestMarketGroupLazyRaise`: `Market.group` access without eager-load raises `InvalidRequestError` matching `lazy='raise'`. `TestMarketGroup.test_deleting_group_orphans_children_not_cascade` (WR-02 fix): DELETE FROM market_groups confirms child is NOT deleted and `group_id` is set to NULL (T-13-01 behavioral proof). |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/alembic/versions/0011_phase13_market_groups.py` | Reversible Alembic migration — `market_groups` table, 2 nullable `markets` columns, `pg_trgm`, 6 indexes | VERIFIED | 206 lines. `upgrade()` creates table + 2 columns + FK + 8 indexes. `downgrade()` drops all in reverse order, leaves pg_trgm. `down_revision = "0010_phase12_resolution_stakes"`, `revision = "0011_phase13_market_groups"`. No debt markers. |
| `backend/app/markets/models.py` | `MarketGroup` ORM class + `Market.group_id`/`group_item_title`/`group` seam + 6 indexes in `__table_args__` | VERIFIED | 363 lines. `MarketGroup` class present with correct `__tablename__ = "market_groups"`, `lazy="raise"` relationship, no cascade. `Market.group_id` FK `ondelete="SET NULL"`, `Market.group` relationship `lazy="raise"`. All 6 indexes declared in `__table_args__` with byte-identical names to migration. No debt markers. |
| `backend/app/markets/__init__.py` | `MarketGroup` exported | VERIFIED | `MarketGroup` imported from `.models` and present in `__all__`. |
| `backend/alembic/env.py` | `MarketGroup` registered for autogenerate | VERIFIED | `from app.markets.models import (... MarketGroup, ...)` with `# noqa: F401` at line 32-34. |
| `backend/tests/markets/test_migration_0011.py` | 14+ migration-introspection tests for SC#1 + SC#3 | VERIFIED | 15 tests collected and passed. Covers: column presence, FK SET NULL metadata, pg_trgm extension, GIN opclass tied to column, partial-unique IS NOT NULL polarity, 4 B-tree indexes, composite column order, additive odds index, chain/single-head, static reversibility parse. |
| `backend/tests/markets/test_models.py` | Extended with MarketGroup SC#4 + SC#2 regression | VERIFIED | 24 tests total (8 new Phase 13 tests). `TestMarketGroup` (3), `TestMarketGroupLazyRaise` (1), `TestStandaloneMarketRegression` (2) + `TestMarketColumns` updated with `group_id`/`group_item_title`. T-13-01 behavioral orphan test included. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `Market.group_id` | `market_groups.id` | FK `ondelete="SET NULL"` in migration + ORM `ForeignKey("market_groups.id", ondelete="SET NULL")` | WIRED | Verified by `test_markets_group_id_fk_set_null` (catalog metadata) AND `test_deleting_group_orphans_children_not_cascade` (behavioral DELETE test) — both pass. |
| `MarketGroup.markets` | `Market.group` | `relationship(back_populates=..., lazy="raise")` bidirectional | WIRED | `test_group_round_trips_two_children` confirms round-trip in both directions; `test_group_relationship_lazy_raise` confirms lazy="raise" is enforced. |
| `migration 0011` | `alembic` revision chain | `down_revision = "0010_phase12_resolution_stakes"`, single head | WIRED | `test_chain_down_revision_and_single_head` passes: `rev.down_revision == "0010_phase12_resolution_stakes"` and exactly one head. |
| `MarketGroup` ORM | `alembic` autogenerate | `env.py` import with `noqa: F401` | WIRED | Grep confirms import at env.py:32-34; autogenerate drift confirmed zero by 13-01-SUMMARY. |

### Data-Flow Trace (Level 4)

Not applicable — Phase 13 is a pure schema/ORM phase with no API endpoints, no service layer, and no UI rendering dynamic data. All artifacts are database/ORM primitives. No data-flow trace required.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SC#1 + SC#3: migration apply + all 6 indexes + pg_trgm + chain + reversibility | `cd backend && uv run pytest tests/markets/test_migration_0011.py -q` | 15 passed in 3.34s | PASS |
| SC#4 + SC#2: MarketGroup ORM round-trip + lazy=raise + standalone regression + T-13-01 orphan | `cd backend && uv run pytest tests/markets/test_models.py -q` | 24 passed in 4.84s | PASS |
| SC#1 + SC#3 + SC#4 combined | `cd backend && uv run pytest tests/markets/test_migration_0011.py tests/markets/test_models.py -q` | 39 passed in 4.84s | PASS |
| SC#2: standalone bet/settle path unchanged | `cd backend && uv run pytest tests/bets/ tests/settlement/ -q` | 92 passed in 5.53s | PASS |
| No money columns added | `cd backend && uv run python scripts/lint_money_columns.py` | OK: 7 files checked, 2 warnings (exit 0; 2 warnings are pre-existing BET-06 documented exceptions) | PASS |

### Probe Execution

No probes declared in this phase. Behavioral spot-checks above cover all SCs.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| EVT-01 | 13-01-PLAN, 13-02-PLAN | A multi-outcome event groups N independent binary (YES/NO) markets under one event entity (`market_groups` + nullable `Market.group_id`), without changing the binary market or settlement model. | SATISFIED | Migration 0011 creates `market_groups` table + nullable FK seam. ORM model + relationship. 92 bets/settlement tests pass unchanged. `trg_binary_outcomes_only` trigger intact. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No TBD/FIXME/XXX/PLACEHOLDER/stub patterns found in any Phase 13 key file. Money-lint clean. `downgrade()` is a real implementation (not a pass/no-op). |

**Code review findings from 13-REVIEW.md (already addressed):**

- **WR-01** (column-order not asserted in composite index tests) — FIXED in committed code. `test_composite_index_column_order` (lines 239-270 of `test_migration_0011.py`) asserts `outcome_id` precedes `snapshot_at` and `status` precedes `volume_24hr`. `test_partial_unique_has_where_clause` asserts `"is not null"` polarity. `test_gin_trgm_indexes_have_opclass` ties opclass to the intended column via paren-clause search. All pass.
- **WR-02** (FK SET NULL behavior only metadata-checked, not behaviorally tested) — FIXED in committed code. `test_deleting_group_orphans_children_not_cascade` in `TestMarketGroup` performs a real `DELETE FROM market_groups`, flushes, expires the child, reloads from DB, and asserts `reloaded is not None` (not cascade-deleted) and `reloaded.group_id is None` (nulled). Passes.
- **IN-01** (test_market_has_expected_columns not extended) — FIXED. `TestMarketColumns.test_market_has_expected_columns` now includes `"group_id"` and `"group_item_title"` in the expected set (lines 75-76 of `test_models.py`).
- **IN-02, IN-03, IN-04** — INFO-level items, no blocker. Noted in 13-REVIEW.md as pre-existing or acceptable-as-is.

### Human Verification Required

None. This is a pure schema/ORM/test phase. All observable behaviors (migration apply, index existence, ORM round-trip, standalone market behavior) are verifiable programmatically and were verified against a real postgres:16-alpine via testcontainers.

---

## Gaps Summary

No gaps. All 4 success criteria verified against real test output:

- **39 tests** covering SC#1 + SC#3 + SC#4 pass in `tests/markets/`
- **92 tests** covering SC#2 (bet/settle path unchanged) pass in `tests/bets/ tests/settlement/`
- **Money-lint** exits 0 (clean, no new money-named columns)
- All code review warnings (WR-01, WR-02, IN-01) were addressed in the committed test code before this verification ran

Phase 13 is the schema gate for v1.2. The `market_groups` table, the nullable `Market.group_id`/`group_item_title` seam, all 6 catalog indexes, the `MarketGroup` ORM model, and the `lazy="raise"` no-cascade relationship all exist, are substantive, are wired, and are test-locked against real Postgres 16. Phase 14 (Curated Per-Category Gamma Sync) is unblocked.

---

_Verified: 2026-06-05T11:30:00Z_
_Verifier: Claude (gsd-verifier)_
