---
phase: 06-polymarket-sync-catalog-replication
fixed_at: 2026-05-28T19:30:00Z
review_path: .planning/phases/06-polymarket-sync-catalog-replication/06-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 06: Code Review Fix Report

**Fixed at:** 2026-05-28T19:30:00Z
**Source review:** .planning/phases/06-polymarket-sync-catalog-replication/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 11
- Fixed: 11
- Skipped: 0

## Fixed Issues

### CR-01: MarketCard shows 50/50 odds for all real Polymarket markets (case-sensitivity bug)

**Files modified:** `frontend/src/components/market-card.tsx`, `frontend/src/__tests__/market-card.test.tsx`
**Commit:** e144a9c
**Applied fix:** Changed `o.label === "YES"` to `o.label.toUpperCase() === "YES"` for case-insensitive matching. Added fallback to first outcome for non-binary markets (e.g., team names). Renamed `yesPercent`/`noPercent` to `primaryPercent`/`secondaryPercent`. Updated test fixture labels from `"YES"`/`"NO"` to `"Yes"`/`"No"` to match real Gamma API data.

### CR-02: source_url produces broken Polymarket links (numeric ID instead of slug)

**Files modified:** `backend/alembic/versions/0004_phase6_polymarket_sync.py`, `backend/app/markets/models.py`, `backend/app/integrations/polymarket/adapter.py`, `backend/app/markets/schemas.py`, `backend/tests/polymarket/test_home_list.py`
**Commit:** ed1caa9
**Applied fix:** Added `polymarket_slug` column (String(300), nullable) to Market model and migration. Adapter now persists `parsed.slug` from Gamma API during sync. `compute_source_url` in `MarketListItem` uses `polymarket_slug` instead of `source_market_id` for URL construction. Updated test to set `polymarket_slug` and assert against it.

### CR-03: Broad `except Exception` in sync_top25 conflates parse failures with DB errors

**Files modified:** `backend/app/integrations/polymarket/adapter.py`
**Commit:** 6a75dd0
**Applied fix:** Split the single `except Exception` into two separate handlers: `except ValidationError` for parse failures (with `continue`) and `except IntegrityError` for DB errors (with `await session.rollback()` before `continue`). Added imports for `ValidationError` and `IntegrityError`. DB operations now run inside their own try block so a slug collision or other DB error no longer poisons the session for remaining markets.

### WR-01: Slug regeneration on every upsert risks IntegrityError on unique constraint

**Files modified:** `backend/app/integrations/polymarket/adapter.py`
**Commit:** d2c1185
**Applied fix:** Replaced `generate_slug(parsed.question)` (random 6-char hex suffix) with deterministic `f"pm-{parsed.slug}"[:100]` using the stable Gamma API slug. Falls back to `generate_slug()` only when `parsed.slug` is empty. Also added `polymarket_slug` to the ON CONFLICT `set_` dict so it gets backfilled on update.

### WR-02: _run_poll_sync does not rollback session on exception

**Files modified:** `backend/app/integrations/polymarket/tasks.py`
**Commit:** e5fb2bd
**Applied fix:** Added `await session.rollback()` in the except block, guarded by `contextlib.suppress(Exception)` to avoid masking the original error. Added a `session` type annotation initialized to `None` before the try block to safely guard against `NameError` when the exception occurs before session creation.

### WR-03: _run_snapshot_odds swallows exceptions without session rollback

**Files modified:** `backend/app/integrations/polymarket/tasks.py`
**Commit:** 5ddc0eb
**Applied fix:** Added `await session.rollback()` in the except block of `_run_snapshot_odds`, wrapped in `contextlib.suppress(Exception)`. Same pattern as WR-02.

### WR-04: SourceBadge opens blank tab when sourceUrl is null

**Files modified:** `frontend/src/components/source-badge.tsx`
**Commit:** 00fb9e4
**Applied fix:** Split the POLYMARKET branch into two: when `sourceUrl` is truthy, render the anchor-wrapped badge as before; when `sourceUrl` is falsy, render a plain Badge with no link. Removed the `href={sourceUrl ?? "#"}` fallback.

### WR-05: MarketRead schema omits volume and volume_24hr fields

**Files modified:** `backend/app/markets/schemas.py`
**Commit:** d105bcc
**Applied fix:** Added `volume: Decimal = Decimal("0")` and `volume_24hr: Decimal = Decimal("0")` fields to `MarketRead`, plus a `serialize_volume_decimal` field serializer matching the pattern in `MarketListItem`.

### WR-06: list_home_markets has no limit on house markets query

**Files modified:** `backend/app/markets/service.py`
**Commit:** 6a5f33b
**Applied fix:** Added `.limit(50)` to the house markets query in `list_home_markets`, matching the bounded pattern of the Polymarket query (`.limit(25)`).

### IN-01: Odds Numeric(8,6) accepts values > 1.0 without CHECK constraint

**Files modified:** `backend/app/markets/models.py`, `backend/alembic/versions/0004_phase6_polymarket_sync.py`
**Commit:** aa3f502
**Applied fix:** Added CHECK constraints to the `Outcome` model (`ck_outcomes_initial_odds_range`, `ck_outcomes_current_odds_range`) and `OddsSnapshot` model (`ck_odds_snapshots_probability_range`) enforcing `[0, 1]` range. Added corresponding `create_check_constraint` calls in the migration upgrade and `drop_constraint` calls in downgrade.

### IN-02: _gamma_model_config fallback defaults to extra="allow" in dev environments

**Files modified:** `backend/app/integrations/polymarket/schemas.py`
**Commit:** 602e2d5
**Applied fix:** Changed the except-block fallback from `is_dev = False` to `is_dev = True`, so unknown environments (test collection, missing env vars) get the stricter `extra="ignore"` mode instead of the permissive `extra="allow"`.

---

_Fixed: 2026-05-28T19:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
