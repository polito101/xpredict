---
phase: 14-curated-per-category-gamma-sync
plan: 03
subsystem: integration
tags: [polymarket, gamma, adapter, sqlalchemy, pg-insert, on-conflict, market-groups, idempotency]

# Dependency graph
requires:
  - phase: 06-polymarket-sync
    provides: "PolymarketAdapter.sync_top25 pg_insert ON CONFLICT (source, source_market_id) upsert body + changed_markets realtime bookkeeping; GammaMarket._derive_status"
  - phase: 13-multi-outcome-model
    provides: "market_groups table + partial-unique ix_market_groups_source_source_event_id (source, source_event_id); Market.group_id / category / group_item_title columns; MarketGroup ORM"
  - phase: 14-curated-per-category-gamma-sync
    plan: 01
    provides: "GammaEvent / GammaEventMarket(GammaMarket) parsers (the curated /events shape this writer consumes)"
provides:
  - "PolymarketAdapter._upsert_one_market(session, parsed, *, group_id, category) -> bool — the shared per-market upsert (extracted from sync_top25), now stamping category + group_id + group_item_title on INSERT and ON CONFLICT"
  - "PolymarketAdapter._upsert_market_group(session, ev, category) -> UUID — first writer of market_groups; pg_insert ON CONFLICT (source, source_event_id) + SAVEPOINT-guarded uuid-suffixed slug-collision retry (Pitfall 6)"
  - "PolymarketAdapter.sync_events(session, events, *, category) -> int — per-event conditionId dedup, EVT-07 len==1 standalone branch, 1 group + N stamped children for multi-outcome events; idempotent"
  - "sync_top25 back-compat: delegates to _upsert_one_market(group_id=None, category=None) — legacy top-25 path unchanged"
affects: [14-04, poll-polymarket-events, browse-api, settlement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Extract-and-delegate: lift the proven sync_top25 per-market body into _upsert_one_market; both the legacy top-25 path and the new event path share one idempotent upsert (DRY + back-compat)"
    - "Idempotent parent upsert on the Phase-13 partial-unique: pg_insert(MarketGroup).on_conflict_do_update(index_elements=[source, source_event_id], index_where=source_event_id IS NOT NULL) — replay updates, never duplicates"
    - "SAVEPOINT-guarded slug-collision retry (begin_nested + nested.rollback, mirroring markets/service.py): a cross-event MarketGroup.slug UNIQUE clash retries once with a uuid6 suffix without aborting siblings (Pitfall 6 / T-14-09)"
    - "EVT-07 standalone branch: a len==1 event (after conditionId dedup) upserts its lone child with group_id=None and writes NO market_groups row — many Polymarket events wrap a single binary"
    - "Status always via the inherited GammaMarket._derive_status (children are GammaEventMarket); this writer sets status only, never settles on closed/price alone (spike-002 / T-14-10)"

key-files:
  created: []
  modified:
    - "backend/app/integrations/polymarket/adapter.py — extracted _upsert_one_market (+3 stamps: category/group_id/group_item_title on values AND on_conflict set_); added _upsert_market_group + sync_events; sync_top25 now delegates; +imports GammaEvent, MarketGroup, _slugify, uuid4"
    - "backend/tests/polymarket/test_adapter.py — added TestSyncEventsIntegration (groups_multi_outcome, single_market_no_group, idempotent) against the live-captured fixtures"

key-decisions:
  - "Extracted _upsert_one_market keeps the EXACT sync_top25 body; the only behavioral delta is the 3 new stamps. IntegrityError path returns False after rollback (was `continue`); sync_top25's loop translates False->skip so legacy counts are byte-equivalent (verified: test_upsert_idempotent still == 2)"
  - "Slug-collision retry uses session.begin_nested() SAVEPOINT (the established markets/service.py idiom) instead of a full session.rollback() — a clash on one event's slug must not discard children already upserted for sibling events in the same sync_events session"
  - "group_item_title written via getattr(parsed, 'group_item_title', None) so the legacy GammaMarket (no such attr) path stays valid; only GammaEventMarket children carry the label"
  - "MarketGroup gets ONLY source/source_event_id/title/slug/category written — the table deliberately has no volume/status column (EVT-06); no columns invented (Open Question 2 resolved)"
  - "children typed list[GammaMarket] (GammaEventMarket is a subclass) to satisfy mypy --strict (type-arg) while accepting the deduped /events children"

patterns-established:
  - "Pattern: one shared idempotent child upsert feeds both the global top-25 path and the curated per-category event path"
  - "Pattern: parent-group ON CONFLICT on (source, source_event_id) is the market_groups idempotency seam; slug UNIQUE clashes are absorbed by a SAVEPOINT retry, NOT by the ON CONFLICT target"
  - "Pattern: EVT-07 len==1 stays standalone (no degenerate single-child group)"

requirements-completed: [CAT-04, EVT-07, CAT-06]

# Metrics
duration: ~16min
completed: 2026-06-05
---

# Phase 14 Plan 03: Adapter sync_events — First Writer of market_groups Summary

**Extracted `_upsert_one_market` (now stamping `category` + `group_id` + `group_item_title`) from `sync_top25`, then built `sync_events` + `_upsert_market_group` on top — the first writer of the Phase-13 `market_groups` seam: 1 group + N stamped children for multi-outcome events, a standalone child (no group) for `len==1` events (EVT-07), idempotent on `ON CONFLICT (source, source_event_id)`, with a SAVEPOINT-guarded slug-collision retry.**

## Performance

- **Duration:** ~16 min
- **Started:** 2026-06-05 (execute start)
- **Completed:** 2026-06-05
- **Tasks:** 3 (all `type="auto"`)
- **Files modified:** 2 (adapter.py, test_adapter.py)

## Accomplishments

- **Extracted `_upsert_one_market(session, parsed, *, group_id, category) -> bool`** — the verbatim per-market body from `sync_top25` (deadline parse, `pm-{slug}` rule, description fallback, the `pg_insert(Market)` ON CONFLICT upsert, the post-upsert market select, the YES/NO outcome loop with `current_odds` change tracking, `flush()` + `changed_markets` realtime bookkeeping). Added **3 writes** — `category` (CAT-04), `group_id` (EVT-01 child stamp), `group_item_title` (`getattr` — children only) — to BOTH the INSERT `market_values` AND the `on_conflict_do_update` `set_` (`stmt.excluded.*`). Returns `True` after flush, `False` after the `IntegrityError` rollback.
- **`sync_top25` now delegates** to `_upsert_one_market(group_id=None, category=None)` — the legacy top-25 path is byte-equivalent (the 2 pre-existing integration tests, `test_upsert_idempotent` and `test_fetch_active_markets`, still pass; counts unchanged).
- **Added `_upsert_market_group(session, ev, category) -> UUID`** — the first writer of `market_groups`. `pg_insert(MarketGroup).on_conflict_do_update(index_elements=["source","source_event_id"], index_where=source_event_id IS NOT NULL, set_={title, category, updated_at})` on the Phase-13 partial-unique. Writes ONLY the columns the table has (`source`, `source_event_id` = Gamma event id, `title`, `slug`, `category`) — no volume/status (EVT-06). Slug = `pm-evt-{slugify(title, max_length=80)}[:100]`; on a cross-event slug `IntegrityError` (the ON CONFLICT target is `source_event_id`, not `slug`), a SAVEPOINT retry with a `-{uuid4().hex[:6]}` suffix (Pitfall 6 / T-14-09).
- **Added `sync_events(session, events, *, category) -> int`** — per event: dedup children by `condition_id` (drop falsy/dupes); `len==1` → `_upsert_one_market(group_id=None)` + `continue` (EVT-07, NO group row); else `_upsert_market_group` once, then stamp every child with the resulting `group_id`. Status always flows through the inherited `GammaMarket._derive_status` (no settlement; T-14-10).
- **Added `TestSyncEventsIntegration`** (3 testcontainers tests) proving grouping (1 group + 3 children, category=Crypto, group_item_titles {64,000/66,000/68,000}), the EVT-07 standalone path (event 108634 → no group, lone market 958443 standalone with category=Politics), and idempotent replay (exactly 1 group).
- **All 8 `test_adapter.py` tests pass via the per-module run** (5 back-compat + 3 new); ruff check + format + mypy clean on both files.

## Task Commits

Each task was committed atomically (per-task, only the task's file staged; `.planning/config.json`'s pre-existing `use_worktrees` change never staged):

1. **Task 1: Extract `_upsert_one_market` from `sync_top25` (with group_id + category stamp)** — `d6e7854` (refactor)
2. **Task 2: Add `_upsert_market_group` + `sync_events` (grouping, EVT-07, conditionId dedup, slug-collision fallback)** — `eea7aff` (feat)
3. **Task 3: Add `sync_events` integration tests (grouping, EVT-07, category, dedup, idempotency)** — `45969a2` (test)

## Files Created/Modified

- `backend/app/integrations/polymarket/adapter.py` — Imports: `uuid4`, `slugify as _slugify`, `GammaEvent`, `MarketGroup` added. `_upsert_one_market` extracted (152-line refactor) with the 3 new stamps on values + `set_`. `_upsert_market_group` + `sync_events` added (134 lines). `sync_top25` slimmed to parse + delegate. `detect_resolution`, `fetch_active_markets`, `fetch_market`, `_map_winning_outcome_id` untouched.
- `backend/tests/polymarket/test_adapter.py` — `TestSyncEventsIntegration` added (113 lines): `test_sync_events_groups_multi_outcome`, `test_sync_events_single_market_no_group`, `test_sync_events_idempotent`, using the existing `gamma_events_multi`/`gamma_events_single` conftest fixtures. Asserted against the real on-disk fixture ids (538337, 108634, 958443) — all matched the research sample exactly (no fixture-id divergence).

## Decisions Made

- **Extract-and-delegate, byte-equivalent legacy path:** `_upsert_one_market` is the literal `sync_top25` body plus the 3 stamps; `sync_top25` keeps only the parse + ValidationError-skip and translates the helper's `False` return to a skip. The pre-existing `test_upsert_idempotent` (== 2) and `test_fetch_active_markets` confirm back-compat.
- **SAVEPOINT for the slug-collision retry (not a full rollback):** `_upsert_market_group` wraps the group insert in `session.begin_nested()` (the established `markets/service.py:62` idiom). A `MarketGroup.slug` UNIQUE clash across a *different* event rolls back only that SAVEPOINT and retries once with a uuid6-suffixed slug — sibling children already upserted in the same `sync_events` session are preserved (T-14-09: one event's clash can't abort the cycle).
- **`getattr` for `group_item_title`:** keeps the legacy `GammaMarket` (no such attribute) path valid; only `GammaEventMarket` children carry the per-outcome label. Stamped into `Market.group_item_title`.
- **Write only existing `MarketGroup` columns:** `source`, `source_event_id`, `title`, `slug`, `category` — the table has no volume/status column by design (EVT-06; Research Open Question 2 resolved "write only what exists, never add columns").
- **`children: list[GammaMarket]`:** typed at the supertype (`GammaEventMarket` is a subclass) to satisfy `mypy --strict` `type-arg` while holding the deduped `/events` children.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `mypy --strict` `type-arg` on the deduped-children list**
- **Found during:** Task 2 (mypy on the new `sync_events` loop)
- **Issue:** `children: list = []` raised `mypy error: Missing type arguments for generic type "list" [type-arg]` — the repo's mypy is strict and the Linux-CI `backend` job runs mypy as part of the phase gate.
- **Fix:** Annotated `children: list[GammaMarket] = []` (`GammaEventMarket` is a subclass of `GammaMarket`, so the deduped `/events` children are accepted covariantly; `_upsert_one_market` already accepts `GammaMarket`).
- **Files modified:** backend/app/integrations/polymarket/adapter.py
- **Verification:** `uv run mypy app/integrations/polymarket/adapter.py` → "Success: no issues found".
- **Committed in:** `eea7aff` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (blocking, type-annotation). No scope creep — the implementation follows 14-RESEARCH.md Pattern 2 + Pitfall 6 exactly. No architectural changes; no `checkpoint` reached (the plan is fully autonomous, no checkpoints, no auth gates, zero new dependencies).

## Known Stubs

None. `sync_events` performs real DB writes (market_groups + stamped children) and the tests assert against real persisted rows via testcontainers Postgres — no hardcoded/mock data flowing to assertions. `Market.category` and `market_groups` are genuinely populated for the first time.

## Issues Encountered

- **Windows-worktree testcontainers `ResourceWarning` (cosmetic):** each per-module run prints `ResourceWarning: unclosed <socket.socket ...>` during testcontainers teardown. This is a harmless socket-cleanup artifact on Windows (the container DB stops fine; all assertions pass) — NOT a test failure or a logic error. Per the Windows-worktree policy I used PER-MODULE runs (`pytest tests/polymarket/test_adapter.py`); the full `pytest tests/` suite was NOT run locally (it flakes here on testcontainers contention across unrelated modules — Linux CI is the full-suite gate). No real assertion failures occurred — every `sync_events` run was a clean pass, so no environmental-flake deferral was needed for the logic itself.
- **Branch/worktree note:** this is a Windows git-worktree (`.git` is a file) but the operator pre-created the phase branch `gsd/phase-14-curated-per-category-gamma-sync` here and the orchestrator runs SEQUENTIALLY on it (not a Claude-Code auto worktree). Commits were made normally WITH hooks on the phase branch (never `main`, never `--no-verify`). The pre-existing `.planning/config.json` (`use_worktrees`) working-tree change was never staged or committed.

## Verification Performed

- `cd backend && uv run pytest tests/polymarket/test_adapter.py -x` → **8 passed** (5 back-compat: protocol/registry/detect_resolution/upsert_idempotent/fetch_active_markets + 3 new sync_events).
- `cd backend && uv run pytest tests/polymarket/test_adapter.py -k sync_events -x` → **3 passed, 5 deselected** (grouping/EVT-07/idempotency).
- `uv run ruff check` + `uv run ruff format --check` on adapter.py + test_adapter.py → all green.
- `uv run mypy app/integrations/polymarket/adapter.py` → Success, no issues.
- Phase gate (full `pytest tests/` + ruff + mypy) deferred to Linux CI per the Windows-worktree policy.

## Next Phase Readiness

- The write path is complete and integration-proven. **14-04** (`poll_polymarket_events` task + `_run_poll_events` curation loop + beat-schedule swap) can call `adapter.sync_events(session, curated_events, category=entry.name)` as a known contract: it returns the child-upsert count, writes the group + children idempotently, and is safe to call per-category with a commit between categories (CAT-05 keep-last-good).
- The cross-category event-id dedup (CAT-02 first-by-priority) is a **task-layer** concern for 14-04 (a cycle-level `seen_event_ids` set), NOT inside `sync_events` (which only does within-event conditionId dedup).
- No blockers.

---
*Phase: 14-curated-per-category-gamma-sync*
*Completed: 2026-06-05*

## Self-Check: PASSED

- Files: `14-03-SUMMARY.md`, `backend/app/integrations/polymarket/adapter.py`, `backend/tests/polymarket/test_adapter.py` all present on disk.
- Commits: `d6e7854` (Task 1 refactor), `eea7aff` (Task 2 feat), `45969a2` (Task 3 test) all present in git history.
- Tests: `uv run pytest tests/polymarket/test_adapter.py -x` → 8 passed; `-k sync_events` → 3 passed.
- Ruff + mypy: clean on both changed files.
- `.planning/config.json` (`use_worktrees`) NOT staged/committed — confirmed via `git status --short`.
