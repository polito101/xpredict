---
phase: 14-curated-per-category-gamma-sync
verified: 2026-06-05T13:38:40Z
status: human_needed
score: 11/11 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification. The phase code-review (14-REVIEW.md) found 2 critical blockers (CR-01 child SAVEPOINT, CR-02 per-category publish reset) + WR-04 (slug-retry SAVEPOINT); all confirmed FIXED in commit ce5833b with bidirectional regression tests in commit fc18448 — both verified present and green in this codebase check."
human_verification:
  - test: "redbeat schedule reload — restart the beat process after deploy, confirm poll_polymarket_events fires @300s and poll_polymarket_top25 stops firing"
    expected: "Logs show `poll_events.category_synced` entries every ~5min and NO further `poll_complete` (top-25) entries; market_groups rows + grouped children appear in the DB"
    why_human: "redbeat persists the live schedule in Redis (runtime state, not just code). The code swap (celery_app.py: top-25 dropped, events @300s added) is inert until the beat process restarts and re-syncs Redis. No static check can prove the running beat picked up the swap — it requires a live restart + log/DB observation."
  - test: "Live tag_id drift re-verify — run the 7-slug `GET /tags/slug/{slug}` loop against gamma-api.polymarket.com before relying on the pinned POLYMARKET_CATEGORIES constant"
    expected: "All 7 slugs (politics, sports, crypto, pop-culture, economy, tech, world) return HTTP 200 with ids 2 / 1 / 21 / 596 / 100328 / 1401 / 101970 unchanged"
    why_human: "tag_ids were live-pinned 2026-06-05; deploy may run days later. A drifted id would silently mis-route or empty a category. Requires a live external-API call — cannot be verified from the codebase."
---

# Phase 14: Curated Per-Category Gamma Sync Verification Report

**Phase Goal:** A sync cycle ingests Polymarket via Gamma `/events` and lands a curated, per-category catalog (mirrored events grouped into market_groups, children stamped with group_id/category, categories populated) instead of the flat top-25 — resiliently and without ever blanking the catalog.
**Verified:** 2026-06-05T13:38:40Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

All four ROADMAP success criteria and all 11 plan must-haves are **VERIFIED in the actual codebase**. The two code-review blockers the phase context warned about (the documented "begin()-on-open-tx / dangling-tx" defect family) were independently found by the code reviewer, fixed in `ce5833b`, and proven by bidirectional regression tests in `fc18448` — both confirmed present and green here. The phase is functionally complete; status is `human_needed` only because two genuinely-non-programmatic runtime/external verifications remain (redbeat reload + live tag_id drift), per the Step-9 decision tree (human items take priority over an otherwise-clean pass).

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC#1 | After a sync cycle, market_groups rows + grouped children come from Gamma GET /events; poll_polymarket_top25 → poll_polymarket_events @300s (slower than 30s odds poll) | ✓ VERIFIED | `client.py:85` `fetch_events` GETs `/events`; `adapter.py:388` `sync_events` writes 1 group + N children; `tasks.py:179` `_run_poll_events` loop; `celery_app.py:54-57` `poll-polymarket-events`@300.0, top-25 absent. Tests: `test_sync_events_groups_multi_outcome` (n==3, 1 group), `test_beat_schedule_entries` (top25 NOT in schedule, events@300). Adapter module 9/9 green; tasks unit 11/11 green. |
| SC#2 | top-N-per-category vs 7-tag allow-list; dedup by conditionId/event-id BEFORE the volume floor; limit≤500 + short-page stop; unmapped tags logged | ✓ VERIFIED | `config.py:127-135` 7-entry `POLYMARKET_CATEGORIES`; `tasks.py:256-267` dedup (seen_event_ids) → floor → top-N IN THAT ORDER; `client.py:109` `min(limit,500)`; `tasks.py:262` `resolve_category` drift logging; `schemas.py:273-280` `gamma.unmapped_tag` warning. Tests: `test_poll_events_dedup_before_floor`, `test_fetch_events_caps_limit` ("500"). |
| SC#3 | Mirrored markets carry a populated category; empty category never written | ✓ VERIFIED | `adapter.py:219` child `"category": category` stamp; `adapter.py:347` group `"category": category`; `tasks.py:272-274` `if not curated: continue` (never calls sync_events with empty list, CAT-06). Test `test_sync_events_groups_multi_outcome` asserts group + all 3 children `category=="Crypto"`. |
| SC#4 | Gamma fetch failure keeps last-good per-category (never blanks); len==1 event stays standalone (no group) | ✓ VERIFIED | `tasks.py:301-311` per-category `except` → log + rollback + `continue` (other categories still sync; sync only upserts, never deletes); `adapter.py:424-432` `if len(children)==1` → standalone `group_id=None`, no group row (EVT-07). Tests: `test_poll_events_keeps_last_good_per_category` (Politics fails → Sports still syncs, 1 commit, ≥1 rollback), `test_sync_events_single_market_no_group` (no group for 108634; lone market group_id IS NULL, category set). |

**Score:** 4/4 success criteria verified · 11/11 plan must-haves verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `schemas.py` | GammaEvent, GammaTag, GammaEventMarket(GammaMarket), resolve_category | ✓ VERIFIED | All 4 present (lines 184/197/212/247). GammaEventMarket subclasses GammaMarket (inherits validators + `_derive_status`). Event-level volume is `float`→Decimal via `_safe_decimal` property; list validator correctly NOT re-applied. resolve_category first-by-priority + drift logging. |
| `config.py` | POLYMARKET_CATEGORIES + curation settings (frozen CategoryEntry, non-env) | ✓ VERIFIED | `CategoryEntry` `@dataclass(frozen=True)` (line 24); 7 entries in priority order, tag_ids 2/1/21/596/100328/1401/101970; floor Decimal("10000"); top-N 10; limit-cap 500; lock TTL 280; poll interval 300. |
| `client.py` | GammaClient.fetch_events(tag_id, limit, offset) | ✓ VERIFIED | `fetch_events` (line 85) GETs `/events` with active/closed/tag_id/order=volume24hr/ascending/`min(limit,500)`/offset; same tenacity retry. Stale "300 req/10s" docstring corrected (now distinguishes /markets 300 vs /events 500). |
| `adapter.py` | _upsert_one_market (extracted), _upsert_market_group, sync_events | ✓ VERIFIED | `_upsert_one_market` (164) with group_id/category stamp + SAVEPOINT (CR-01 fix); `_upsert_market_group` (317) ON CONFLICT(source,source_event_id) + uuid-suffixed slug retry in fresh SAVEPOINT (WR-04 fix); `sync_events` (388) dedup + EVT-07 branch + grouping. `sync_top25` delegates with nulls (back-compat). |
| `tasks.py` | poll_polymarket_events, _run_poll_events, EVENTS_LOCK_KEY | ✓ VERIFIED | `EVENTS_LOCK_KEY` distinct (46); `_run_poll_events` (179) per-category curation + keep-last-good + CR-02 reset (280); `poll_polymarket_events` task (526); `poll_polymarket_top25` still registered (515). |
| `celery_app.py` | beat_schedule w/ poll-polymarket-events @300s, top-25 removed | ✓ VERIFIED | `poll-polymarket-events`@300.0 (54-57); top-25 absent; snapshot@300, detect@60, reconcile `.update()` intact; redbeat-restart note present (51-53). |
| `conftest.py` / fixtures | gamma_events_multi/single/tags + 3 JSON fixtures | ✓ VERIFIED | 3 fixtures present; ids match asserts exactly (multi 538337 w/ 3 children 64,000/66,000/68,000 distinct conditionIds; single 108634, lone market 958443, dual-tagged World+Politics → first-by-priority Politics). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `schemas.py::GammaEventMarket` | `GammaMarket` | subclass | ✓ WIRED | `class GammaEventMarket(GammaMarket)` (184); adds only `group_item_title`. |
| `schemas.py::resolve_category` | `config.POLYMARKET_CATEGORIES` | priority iteration | ✓ WIRED | `for entry in allow_list` (267), callers pass `settings.POLYMARKET_CATEGORIES`. |
| `client.py::fetch_events` | `GET /events` | `client.get('/events', params)` | ✓ WIRED | line 101. |
| `adapter.py::sync_events` | `market_groups` ON CONFLICT (source, source_event_id) | `_upsert_market_group` | ✓ WIRED | `on_conflict_do_update` index_elements `["source","source_event_id"]` (350-352). |
| `adapter.py::sync_events` | `markets.group_id/category/group_item_title` | `_upsert_one_market` stamps child | ✓ WIRED | 219-221 + 234-236. |
| `celery_app.py::beat_schedule` | `tasks.poll_polymarket_events` | literal entry @300s | ✓ WIRED | 54-57 (in-place edit, not dict reassignment). |
| `tasks.py::_run_poll_events` | `PolymarketAdapter.sync_events` | per-category curate→sync→commit | ✓ WIRED | 281-282. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `sync_events` group/child writes | `MarketGroup.category` / `Market.category` / `group_id` | `_run_poll_events` curated list per category (real Gamma `/events` fetch, dedup, floor) | ✓ Yes — category passed as `entry.name`; `if not curated: continue` guarantees non-empty | ✓ FLOWING |
| `_upsert_one_market` child | `group_id`, `group_item_title` | `GammaEventMarket.group_item_title` (from `/events` `markets[].groupItemTitle`); group_id from `_upsert_market_group` scalar_one() | ✓ Yes — fixture children carry real labels (64,000 etc.); group UUID is a real DB read | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Schemas+resolver parse live fixtures, first-by-priority | `pytest tests/polymarket/test_schemas.py -m unit` | 12 passed | ✓ PASS |
| fetch_events param shape + 500 cap | `pytest tests/polymarket/test_client.py -m unit` | 7 passed | ✓ PASS |
| Curation order, keep-last-good, CR-02 publish reset, beat swap, distinct lock | `pytest tests/polymarket/test_tasks.py -m unit` | 11 passed | ✓ PASS |
| Grouping, EVT-07 standalone, idempotency, CR-01 child-conflict-preserves-group (real Postgres) | `pytest tests/polymarket/test_adapter.py` | 9 passed | ✓ PASS |

Full `pytest tests/` suite NOT run locally (Windows-worktree testcontainers flake — documented policy); Linux CI is the full-suite + ruff + mypy gate.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CAT-01 | 14-02, 14-04 | Sync via Gamma `GET /events`, replacing top-25 `/markets` poll | ✓ SATISFIED | `fetch_events` + `_run_poll_events` + beat swap; SC#1 |
| CAT-02 | 14-04 | top-N per category + volume floor; dedup by conditionId/event-id BEFORE floor | ✓ SATISFIED | `tasks.py:256-267` dedup→floor→top-N; SC#2; `test_poll_events_dedup_before_floor` |
| CAT-03 | 14-01, 14-04 | 7 `tag_id` allow-list (version-controlled); unmapped tags logged, never auto-added | ✓ SATISFIED | `POLYMARKET_CATEGORIES`; `resolve_category` first-by-priority + `gamma.unmapped_tag` |
| CAT-04 | 14-03 | Mirrored markets get `category` populated (today always NULL) | ✓ SATISFIED | child + group category stamps; SC#3; integration asserts `category=="Crypto"` |
| CAT-05 | 14-02, 14-04 | Resilient keep-last-good; cap limit=500 + short-page stop; slower cadence | ✓ SATISFIED | per-category try/except keep-last-good; `min(limit,500)`; @300s; SC#4 |
| CAT-06 | 14-03 | Empty category suppressed at data layer (never written) | ✓ SATISFIED | `if not curated: continue` (never persists empty category); SC#3 |
| EVT-07 | 14-01, 14-03 | `len==1` event stays standalone, no group; grouping only ≥2 outcomes | ✓ SATISFIED | `adapter.py:424` len==1 branch; `test_sync_events_single_market_no_group` |

All 7 IDs map to Phase 14 in REQUIREMENTS.md (lines 103-109), all marked Complete. No ORPHANED requirements (REQUIREMENTS.md "Phase 14 (Sync): 7 — CAT-01..06, EVT-07" matches the union of plan `requirements` fields).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX/HACK/PLACEHOLDER in any phase-14 source | ℹ️ Info | Clean — completion is auditable |
| `adapter.py` | 127-156 | `return None` ×5 | ℹ️ Info (not a stub) | All in Phase-7 `detect_resolution` guard clauses (unchanged by Phase 14); legitimate not-found/not-resolved returns, not in the Phase-14 write path |

### Known Non-Blocking Items (deferred to Pol per 14-REVIEW.md)

These were flagged in the code review as WARNING/INFO, explicitly NOT blocking, and are tracked for Pol's review — they do not affect goal achievement:

- **WR-01** (warning): `sync_events` dedups children by `condition_id`; a Gamma child with a blank `conditionId` (legit for not-yet-deployed markets) is skipped, which could collapse a genuine 2-child event onto the EVT-07 standalone path. Happy path is sound (the multi-outcome fixture children all carry non-blank conditionIds). Edge-case data-quality concern, not a goal-blocker.
- **WR-02** (warning): event-level `volume24hr` is float-derived Decimal (Gamma returns it as a JSON number) for the soft $10k floor — contradicts the strict string→Decimal money rule but acceptable for a curation threshold; flagged for an explicit decision/comment.
- **WR-03/WR-05, IN-01..04** (warning/info): lock-acquire structure fragility, per-candidate GammaClient in the pre-existing detect loop, hand-inlined detect lock, magic slug-truncation numbers, stale module docstrings. All cosmetic/pre-existing; none touch the Phase-14 goal path.

### Human Verification Required

Two runtime/external-service behaviors cannot be verified from the codebase (carried from 14-VALIDATION.md "Manual-Only Verifications"):

#### 1. redbeat schedule reload

**Test:** After deploy (or local `docker compose restart` of the beat service), observe the beat logs and DB.
**Expected:** `poll_events.category_synced` log entries appear every ~5min; NO further `poll_complete` (top-25) entries; `market_groups` rows + grouped children appear in the DB.
**Why human:** redbeat persists the live schedule in Redis (runtime state). The code swap in `celery_app.py` is inert until the beat process restarts and re-syncs from Redis — no static check can prove the running scheduler adopted the swap. The code-side swap IS verified (`test_beat_schedule_entries` green); only the live reload is manual.

#### 2. Live tag_id drift re-verify

**Test:** Run the 7-slug loop: `for slug in politics sports crypto pop-culture economy tech world; do curl -s "https://gamma-api.polymarket.com/tags/slug/$slug"; done`
**Expected:** All 7 return HTTP 200 with ids 2 / 1 / 21 / 596 / 100328 / 1401 / 101970 unchanged.
**Why human:** tag_ids were live-pinned 2026-06-05; a deploy days later could hit drifted ids that silently mis-route or empty a category. Requires a live external-API call.

### Gaps Summary

**No gaps.** All four success criteria, all 11 plan must-haves, and all 7 requirement IDs are verified against the actual code with fresh green per-module test evidence (schemas 12 · client 7 · tasks 11 unit · adapter 9 integration). The two code-review blockers (CR-01 child SAVEPOINT, CR-02 per-category publish reset) plus WR-04 (slug-retry SAVEPOINT) are confirmed FIXED in `adapter.py`/`tasks.py` (commit ce5833b) and locked by bidirectional regression tests (commit fc18448) — `test_sync_events_child_conflict_preserves_group` exercises the exact mid-batch child IntegrityError against real Postgres and passes, and `test_poll_events_publishes_per_category_not_cumulative` proves the accumulator reset.

Status is `human_needed` (not `passed`) solely because two genuinely-non-programmatic verifications remain — a live redbeat beat-restart and a live Gamma tag_id drift check — which the validation strategy itself classified as manual-only. The implementation is otherwise complete and the phase goal is achieved in code.

---

_Verified: 2026-06-05T13:38:40Z_
_Verifier: Claude (gsd-verifier)_
