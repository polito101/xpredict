---
phase: 14-curated-per-category-gamma-sync
plan: 01
subsystem: api
tags: [pydantic, polymarket, gamma, parser, decimal, structlog, pydantic-settings]

# Dependency graph
requires:
  - phase: 06-polymarket-sync
    provides: "GammaMarket spike-002 parser (stringified-JSON validators, _safe_decimal, _derive_status truth table), _gamma_model_config env-based extra policy, GammaClient"
  - phase: 13-multi-outcome-model
    provides: "market_groups table + partial-unique (source, source_event_id); Market.category / group_id / group_item_title columns (the seam this sync fills)"
provides:
  - "GammaEvent / GammaTag / GammaEventMarket(GammaMarket) Pydantic v2 parsers for the Gamma /events nested shape"
  - "resolve_category(event, allow_list) — first-by-priority category resolver with CAT-03 drift logging (gamma.unmapped_tag)"
  - "POLYMARKET_CATEGORIES — version-controlled 7-entry allow-list (CategoryEntry frozen dataclass) with live-verified tag_ids in priority order"
  - "Phase-14 curation settings: POLYMARKET_EVENTS_TOP_N=10, VOLUME_FLOOR=Decimal(10000), LIMIT_CAP=500, LOCK_TTL=280, POLL_INTERVAL=300"
  - "3 conftest fixtures (gamma_events_multi / gamma_events_single / gamma_tags_categories) wired to the live-captured /events + /tags fixtures"
affects: [14-02, 14-03, 14-04, polymarket-adapter, poll-polymarket-events, browse-api, settlement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Subclass-the-validated-parser: GammaEventMarket(GammaMarket) inherits spike-002 validators + _derive_status + Decimal discipline verbatim, adds only group_item_title"
    - "Mixed-encoding awareness: event-level volume is FLOAT -> Decimal via _safe_decimal property; nested children stay stringified-JSON (the validator stays only on GammaMarket)"
    - "Version-controlled allow-list as a frozen-dataclass Python constant on Settings (NOT env/DB); priority-order list is the first-wins tie-break"
    - "Drift logging over auto-add: unmapped tags emit log.warning('gamma.unmapped_tag', ...), never mutate the allow-list (CAT-03)"

key-files:
  created: []
  modified:
    - "backend/app/integrations/polymarket/schemas.py — +GammaEventMarket, +GammaTag, +GammaEvent, +resolve_category, +structlog log"
    - "backend/app/core/config.py — +CategoryEntry frozen dataclass, +POLYMARKET_CATEGORIES, +5 Phase-14 curation settings"
    - "backend/tests/polymarket/conftest.py — +gamma_events_multi / gamma_events_single / gamma_tags_categories fixtures"
    - "backend/tests/polymarket/test_schemas.py — +TestGammaEventParser (5 tests: float->Decimal, inherited status, subclass label, first-by-priority, GammaTag)"

key-decisions:
  - "GammaEventMarket subclasses GammaMarket (vs adding group_item_title to GammaMarket directly) — keeps the legacy /markets model untouched; verified to parse live data"
  - "Event-level volume24hr/volume typed float|None with *_decimal properties; the stringified-JSON list validator is NOT re-declared for event volume (Pitfall 1)"
  - "POLYMARKET_CATEGORIES lives as an instance field on Settings; tests read it via get_settings().POLYMARKET_CATEGORIES (there is no module-level constant to import)"
  - "resolve_category types its allow_list param loosely (Sequence[CategoryEntry] under TYPE_CHECKING) to avoid a config<->schemas circular import at module load"

patterns-established:
  - "Pattern: inherit-not-reimplement for API-shape variants (subclass the spike-002-validated model)"
  - "Pattern: FLOAT-vs-stringified divergence handled at the field-type + property layer, never by re-applying the list validator"
  - "Pattern: live tag_id re-verify loop run at execute start before trusting the pin (all 7 confirmed unchanged 2026-06-05)"

requirements-completed: [CAT-03, EVT-07]

# Metrics
duration: ~14min
completed: 2026-06-05
---

# Phase 14 Plan 01: Gamma /events Data-Contract Foundation Summary

**GammaEvent/GammaTag/GammaEventMarket Pydantic parsers + first-by-priority `resolve_category` + the version-controlled 7-entry `POLYMARKET_CATEGORIES` allow-list, with the event-level FLOAT-volume→Decimal divergence proven by unit tests against live-captured fixtures.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-06-05 (execute start)
- **Completed:** 2026-06-05
- **Tasks:** 3
- **Files modified:** 4 (235 insertions, 1 deletion)

## Accomplishments
- Added `GammaEventMarket(GammaMarket)` — a subclass that inherits the spike-002 stringified-JSON validators, `_derive_status` truth table, and Decimal discipline verbatim, adding only `group_item_title` (alias `groupItemTitle`).
- Added `GammaEvent` + `GammaTag` parsers; event-level `volume24hr`/`volume` are typed `float | None` and converted via `_safe_decimal` `*_decimal` properties — the critical divergence from `GammaMarket` (where those fields are stringified JSON).
- Added `resolve_category(event, allow_list)` — first-by-priority over `POLYMARKET_CATEGORIES`; the dual-tagged (World+Politics) fixture resolves to "Politics". Unmapped tags emit `gamma.unmapped_tag` drift warnings (CAT-03, "logged, never auto-added").
- Added `CategoryEntry` (frozen dataclass) + `POLYMARKET_CATEGORIES` (7 entries, priority order, live-verified tag_ids) + 5 curation settings to `config.py` as a version-controlled, non-env constant.
- Re-verified all 7 Gamma `tag_id`s live at execute start (`GET /tags/slug/{slug}`, HTTP 200 each) — no drift from the pin.
- 12 schema unit tests green via per-module run (7 pre-existing + 5 new).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add GammaEvent / GammaTag / GammaEventMarket parsers + resolve_category** - `6199feb` (feat)
2. **Task 2: Add POLYMARKET_CATEGORIES constant + Phase-14 curation settings to config.py** - `45a8ee3` (feat)
3. **Task 3: Add conftest fixtures + GammaEvent/priority unit tests** - `f4a4b3a` (test)

_Note: Task 1 carried `tdd="true"`, but the plan sequences the assertions into Task 3 (Task 1's own verify is satisfied by the unchanged existing 7 tests). The RED/GREEN landing point is Task 3's `TestGammaEventParser`._

## Files Created/Modified
- `backend/app/integrations/polymarket/schemas.py` - Added `structlog` import + `log`; appended `GammaEventMarket`, `GammaTag`, `GammaEvent`, and `resolve_category` below `GammaMarket`. Event-level float volume → Decimal via properties; `parse_stringified_json_list` count unchanged at 1.
- `backend/app/core/config.py` - Added `from dataclasses import dataclass`; module-scope `CategoryEntry` frozen dataclass; Phase-14 block with `POLYMARKET_CATEGORIES` (7 entries) + 5 curation settings.
- `backend/tests/polymarket/conftest.py` - Added `gamma_events_multi` / `gamma_events_single` / `gamma_tags_categories` fixtures (each returns a list).
- `backend/tests/polymarket/test_schemas.py` - Added `TestGammaEventParser` with 5 tests + imports for the new symbols and `get_settings`.

## Decisions Made
- **Subclass over field-add:** `GammaEventMarket(GammaMarket)` keeps the legacy `/markets` model untouched (research-recommended; verified live).
- **Float volume at the type+property layer:** event `volume_24hr`/`volume_total` are `float | None`; the stringified-JSON list validator stays only on `GammaMarket`. This is the explicit Pitfall-1 guard.
- **Allow-list as a Settings field:** `POLYMARKET_CATEGORIES` is an instance field on `Settings` (per the research's "Config additions"), so tests reference it via `get_settings().POLYMARKET_CATEGORIES`. There is no module-level constant to import — the plan offered both forms; `get_settings()` is the one that matches the actual config shape.
- **Circular-import avoidance:** `resolve_category` types its `allow_list` parameter as `Sequence[CategoryEntry]` under `TYPE_CHECKING` only, so `schemas.py` does not import `config.py` at module load.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test import path corrected to the real config shape**
- **Found during:** Task 3 (test imports)
- **Issue:** The plan suggested `from app.core.config import POLYMARKET_CATEGORIES`, but `POLYMARKET_CATEGORIES` is an *instance field on `Settings`*, not a module-level name — that import would raise `ImportError`. (The plan explicitly offered the alternative `get_settings().POLYMARKET_CATEGORIES`.)
- **Fix:** Imported `get_settings` and call `get_settings().POLYMARKET_CATEGORIES` in the two resolver tests.
- **Files modified:** backend/tests/polymarket/test_schemas.py
- **Verification:** `uv run pytest tests/polymarket/test_schemas.py -m unit -x` → 12 passed.
- **Committed in:** f4a4b3a (Task 3 commit)

**2. [Rule 1 - Bug] Shortened an over-long test docstring (E501)**
- **Found during:** Task 3 (ruff check on changed files)
- **Issue:** `test_gamma_event_multi_outcome`'s docstring was 101 chars (> 100 limit) → ruff E501.
- **Fix:** Trimmed the docstring to one line under 100 chars.
- **Files modified:** backend/tests/polymarket/test_schemas.py
- **Verification:** `uv run ruff check` on the 4 changed files → "All checks passed!"; tests still 12 passed.
- **Committed in:** f4a4b3a (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both were trivial mechanical corrections (a wrong import name the plan itself flagged an alternative for, and a one-line length fix). No scope creep; the data contract matches the plan exactly.

## Issues Encountered
- The Task 2 verification one-liner failed on a *raw* `uv run python -c` because `Settings()` requires `DATABASE_URL`/`REDIS_URL`/`SECRET_KEY` env vars (pre-existing, unrelated to this plan). These are seeded under pytest by the session-autouse `_test_env_setup` fixture in `tests/conftest.py`. Re-ran the one-liner with those vars set inline (mirroring the conftest placeholders) → printed `ok`. Not a code change — purely how `Settings` is exercised outside the test harness.

## User Setup Required
None - no external service configuration required. (Zero new dependencies; `POLYMARKET_CATEGORIES` and the curation settings are code constants, not secrets — no `.env` change.)

## Next Phase Readiness
- The data-contract layer is complete and unit-proven: 14-03 (adapter `sync_events` / `_upsert_one_market`) and 14-04 (`poll_polymarket_events` task) can build against `GammaEvent` / `GammaEventMarket` / `resolve_category` / `POLYMARKET_CATEGORIES` as a known contract.
- `resolve_category` is callable with `get_settings().POLYMARKET_CATEGORIES`; the cross-category first-by-priority cycle dedup (CAT-02) is a *task-layer* concern (14-04), not the resolver's.
- No blockers. The full backend suite (testcontainers + ruff + mypy) is gated on Linux CI, not this Windows worktree — only the per-module `test_schemas.py` unit run was used here (green).

---
*Phase: 14-curated-per-category-gamma-sync*
*Completed: 2026-06-05*

## Self-Check: PASSED

- Files: all 4 modified backend files + 14-01-SUMMARY.md present on disk.
- Commits: 6199feb (Task 1), 45a8ee3 (Task 2), f4a4b3a (Task 3) all present in git history.
- Tests: `uv run pytest tests/polymarket/test_schemas.py -m unit -x` → 12 passed.
- Ruff: clean on the 4 changed files (check + format).
