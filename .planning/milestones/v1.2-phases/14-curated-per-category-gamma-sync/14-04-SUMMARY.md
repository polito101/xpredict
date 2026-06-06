---
phase: 14-curated-per-category-gamma-sync
plan: 04
subsystem: integration
tags: [polymarket, gamma, celery, redbeat, beat-schedule, redis-lock, curation, keep-last-good, dedup]

# Dependency graph
requires:
  - phase: 06-polymarket-sync
    provides: "_run_poll_sync template (Redis SETNX owner-token lock acquire/release WR-05, GammaClient lifecycle, session-maker, post-commit changed_markets publish); beat_schedule literal; acquire_poll_lock/release_poll_lock + _RELEASE_LOCK_LUA"
  - phase: 14-curated-per-category-gamma-sync
    plan: 01
    provides: "GammaEvent parser (float volume24hr -> Decimal), resolve_category drift logging, POLYMARKET_CATEGORIES allow-list + POLYMARKET_EVENTS_TOP_N/POLYMARKET_VOLUME_FLOOR/POLYMARKET_EVENTS_LOCK_TTL_SECONDS settings"
  - phase: 14-curated-per-category-gamma-sync
    plan: 02
    provides: "GammaClient.fetch_events(*, tag_id, limit, offset) — the curated /events HTTP boundary (500-cap, volume24hr-ranked)"
  - phase: 14-curated-per-category-gamma-sync
    plan: 03
    provides: "PolymarketAdapter.sync_events(session, events, *, category) -> int — idempotent group+children writer, safe to call per-category with a commit between categories; adapter.changed_markets realtime bookkeeping"
provides:
  - "tasks.EVENTS_LOCK_KEY = 'xpredict:poll:events:lock' — distinct from LOCK_KEY/DETECT_LOCK_KEY (T-14-13)"
  - "tasks.acquire_events_lock / release_events_lock — SETNX owner-token + Lua compare-and-delete on EVENTS_LOCK_KEY, TTL=POLYMARKET_EVENTS_LOCK_TTL_SECONDS (280s < 300s tick)"
  - "tasks._run_poll_events — the per-category curation loop: fetch -> cross-cycle event-id dedup (first-by-priority) -> volume24hr floor AFTER dedup -> top-N -> sync_events -> commit-per-category, with per-category try/except keep-last-good (CAT-05)"
  - "tasks.poll_polymarket_events — the @celery_app.task wrapping asyncio.run(_run_poll_events())"
  - "celery_app beat_schedule: poll-polymarket-events @300s (poll-polymarket-top25 dropped; snapshot-odds/detect/reconcile untouched)"
  - "poll_polymarket_top25 stays an importable, registered task (back-compat)"
affects: [15-event-settlement, 16-catalog-api, deploy-beat-restart]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_run_poll_events mirrors _run_poll_sync verbatim (override-resolved redis, lock-held early-return, GammaClient + session-maker lifecycle, post-commit changed_markets publish, single release/close in finally) — generalized to a per-category loop"
    - "Commit-per-category keep-last-good: each category fetch+sync+commit is wrapped in its own try/except; a failure logs + rolls back + continues so one poisoned category never aborts the cycle or blanks the catalog (sync only upserts)"
    - "Cross-cycle event-id dedup via a loop-level seen_event_ids set, applied BEFORE the volume floor — gives first-by-priority for free (a higher-priority category claims a dual-tagged event) AND prevents Polymarket cross-category volume double-count from inflating a borderline event over the floor"
    - "Distinct WR-05 lock per task family: a new EVENTS_LOCK_KEY + dedicated acquire/release helpers reusing the shared _RELEASE_LOCK_LUA, never the poll/detect keys"
    - "Beat-schedule swap as an in-place literal edit (remove one key, add another) — NOT a dict reassignment; the reconcile .update() block stays separate"

key-files:
  created: []
  modified:
    - "backend/app/integrations/polymarket/tasks.py — +EVENTS_LOCK_KEY, +acquire_events_lock/release_events_lock, +_run_poll_events (curation loop), +poll_polymarket_events task; +imports GammaEvent/resolve_category; poll_polymarket_top25 docstring notes its back-compat status"
    - "backend/app/celery_app.py — beat_schedule literal: removed poll-polymarket-top25@30s, added poll-polymarket-events@300s + a redbeat-restart deploy comment"
    - "backend/tests/polymarket/test_tasks.py — inverted test_beat_schedule_entries; +test_acquire_events_lock_uses_distinct_key, +test_poll_events_skipped_when_lock_held, +test_poll_events_keeps_last_good_per_category, +test_poll_events_dedup_before_floor; +_event_payload helper; +httpx import"

key-decisions:
  - "Dedicated acquire_events_lock/release_events_lock (mirroring the poll helpers) rather than parameterizing acquire_poll_lock by key — keeps the legacy poll-lock signature byte-stable (its existing unit tests assert the exact call shape) while the events lock reuses the same owner-token + _RELEASE_LOCK_LUA pattern on its own key + TTL"
  - "CAT-06 guard at the task layer: when the floor empties a category (curated == []), log poll_events.category_empty and continue WITHOUT calling sync_events — honors sync_events' own contract ('only ever called with a non-empty curated list per category') so an empty category never opens a no-op transaction"
  - "seen_event_ids.add happens at dedup time (before floor/top-N), so a duplicate event id is claimed by the FIRST (highest-priority) category that surfaces it even if that event is later floored out of the curated slice — first-by-priority is decided at the event grain, exactly as Pattern 3 specifies"
  - "resolve_category is called per kept event purely for its drift-logging side effect (gamma.unmapped_tag); the category written to the DB is entry.name (the allow-list category being iterated), matching sync_events' category= kwarg — resolve_category's return is not used to re-route, avoiding a category flip on dual-tagged events"
  - "Lock released + client closed + session closed + redis aclosed exactly once in a single finally (WR-04/WR-05); the lock-held early-return aclosed redis before returning (no client/session created on that path)"

patterns-established:
  - "Pattern: a periodic curated-sync task loops a version-controlled allow-list in priority order, dedups across the cycle before a credibility floor, and commits per allow-list entry with per-entry keep-last-good"
  - "Pattern: the existing single-batch poll task (_run_poll_sync) is the verbatim structural template for a multi-batch per-category loop — same lock/lifecycle/publish scaffolding, only the body becomes a for-loop"

requirements-completed: [CAT-01, CAT-02, CAT-03, CAT-05]

# Metrics
duration: ~5min
completed: 2026-06-05
---

# Phase 14 Plan 04: poll_polymarket_events Curation Loop + Beat Swap Summary

**Wired the curated sync end-to-end: `_run_poll_events` loops the 7 `POLYMARKET_CATEGORIES` in priority order (fetch `/events` -> cross-cycle event-id dedup -> `$10k` volume24hr floor AFTER dedup -> top-N -> `sync_events` -> commit-per-category with per-category keep-last-good), behind a distinct `EVENTS_LOCK_KEY` WR-05 lock; swapped the beat schedule from `poll-polymarket-top25`@30s to `poll-polymarket-events`@300s (legacy task kept importable); inverted the existing beat-schedule test and proved the distinct lock + keep-last-good + dedup-before-floor with mocked Redis/Gamma.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-05T13:02:33Z
- **Completed:** 2026-06-05T13:07:37Z
- **Tasks:** 3 (Task 1 `tdd="true"`, Tasks 2-3 `auto`)
- **Files modified:** 3 (tasks.py, celery_app.py, test_tasks.py)

## Accomplishments

- **`_run_poll_events` curation loop** — resolves redis (override or `AioRedis.from_url`), acquires the events lock (early-return + `poll_events_skipped` on lock-held), creates the `GammaClient` + session, then loops `POLYMARKET_CATEGORIES` in priority order. Per category: `fetch_events(tag_id=entry.tag_id, limit=top_n)` -> parse to `GammaEvent` (skipping `ValidationError` elements) -> **dedup** by event id against a cycle-level `seen_event_ids` set (this skip IS first-by-priority) -> **volume floor** `volume_24hr_decimal >= POLYMARKET_VOLUME_FLOOR` AFTER dedup -> **top-N** `[:top_n]` -> `sync_events(session, curated, category=entry.name)` -> `session.commit()` (PER CATEGORY) -> post-commit `changed_markets` publish (swallow publish errors). Each category is wrapped in its own `try/except` that logs `poll_events.category_failed` + `sentry_sdk.capture_exception` + `session.rollback()` + `continue` (CAT-05 keep-last-good — one category's Gamma 5xx never aborts the others or blanks the catalog).
- **Distinct `EVENTS_LOCK_KEY = "xpredict:poll:events:lock"`** + `acquire_events_lock` / `release_events_lock` mirroring `acquire_poll_lock`/`release_poll_lock` (SETNX owner-token + shared `_RELEASE_LOCK_LUA` compare-and-delete, WR-05) with `TTL = POLYMARKET_EVENTS_LOCK_TTL_SECONDS` (280s < the 300s tick so a crash auto-releases).
- **`poll_polymarket_events`** registered `@celery_app.task` wrapping `asyncio.run(_run_poll_events())`; **`poll_polymarket_top25` kept** defined + registered (back-compat) with a docstring noting its dropped-from-schedule status.
- **Beat-schedule swap** — removed `poll-polymarket-top25`@30s from the `beat_schedule` literal and added `poll-polymarket-events`@300s in place (NOT a dict reassignment); `snapshot-odds`@300s, `detect-polymarket-resolutions`@60s, and the `reconcile-wallets-nightly` `.update()` block untouched. Added an inline **redbeat-restart deploy note** (Pitfall 5).
- **Tests** — inverted `test_beat_schedule_entries` (now asserts `poll-polymarket-top25 not in schedule` + `poll-polymarket-events`@300s + the untouched neighbours), and added 4 `@pytest.mark.unit` tests: distinct-lock-key, skipped-when-lock-held, keep-last-good-per-category (Politics fetch raises, Sports still syncs, rollback for the failing cat), and dedup-before-floor (same event id in two categories -> synced once under higher-priority Politics). **10/10 unit tests pass** via the per-module run.

## Task Commits

Each task was committed atomically (only the task's file staged; `.planning/config.json`'s pre-existing `use_worktrees` change never staged):

1. **Task 1: EVENTS_LOCK_KEY + events lock + `_run_poll_events` curation loop + `poll_polymarket_events` task** - `0ed3d5e` (feat)
2. **Task 2: Swap the beat-schedule entry (drop top25@30s, add events@300s) + redbeat-restart note** - `06f25ad` (feat)
3. **Task 3: Invert the beat-schedule test + add poll_events lock/curation/keep-last-good unit tests** - `420ce2a` (test)

**Plan metadata:** committed separately with this SUMMARY + STATE/ROADMAP.

_No separate REFACTOR commit: Task 1 is `tdd="true"` but its RED gate is the existing unit suite as a regression guard (the genuinely new behavior tests are added in Task 3 per the plan's own task split); the GREEN implementation matched the `_run_poll_sync` template verbatim, nothing to clean up._

## Files Created/Modified

- `backend/app/integrations/polymarket/tasks.py` — Added `EVENTS_LOCK_KEY`; `acquire_events_lock`/`release_events_lock` (mirroring the poll-lock helpers on the new key + events TTL); `_run_poll_events` (the per-category curation loop, ~110 lines); the `poll_polymarket_events` task. Imports extended: `GammaEvent`, `resolve_category` (was `GammaMarket` only). `poll_polymarket_top25` kept + docstring updated. `snapshot_odds`, `detect_polymarket_resolutions`, `_run_poll_sync`, `_run_snapshot_odds`, `_run_detect_resolutions` untouched.
- `backend/app/celery_app.py` — `beat_schedule` literal: `poll-polymarket-top25`@30s removed, `poll-polymarket-events`@300s added with a redbeat-restart comment. `snapshot-odds`/`detect-polymarket-resolutions`/the `reconcile-wallets-nightly` `.update()` block all unchanged.
- `backend/tests/polymarket/test_tasks.py` — `test_beat_schedule_entries` inverted; 4 new unit tests + an `_event_payload` helper (a floor-clearing Gamma `/events` element with a float `volume24hr`); `httpx` import added. The integration tests (`test_poll_upserts_markets`, `test_snapshot_odds_writes_rows`) untouched.

## Decisions Made

- **Dedicated events-lock helpers, not a parameterized poll-lock:** `acquire_poll_lock` is hardcoded to `LOCK_KEY` and its existing unit tests assert the exact `redis.set`/`eval` call shape. Adding `acquire_events_lock`/`release_events_lock` (same owner-token + `_RELEASE_LOCK_LUA` pattern, new key, events TTL) keeps the legacy signature byte-stable while satisfying CONTEXT's "distinct lock key + reuse the WR-05 pattern".
- **CAT-06 empty-category guard at the task layer:** when the floor empties a category, the loop logs `poll_events.category_empty` and `continue`s WITHOUT calling `sync_events` — honoring `sync_events`' documented contract ("only ever called with a non-empty curated list per category") and avoiding a no-op open transaction.
- **`seen_event_ids` claimed at dedup time (before floor/top-N):** a duplicate event id is owned by the FIRST (highest-priority) category that surfaces it even if that event is later floored out — first-by-priority is decided at the event grain (Pattern 3), not at the persisted-slice grain.
- **`resolve_category` used only for drift logging:** the DB category is `entry.name` (the allow-list category being iterated, matching the `category=` kwarg `sync_events` stamps). `resolve_category` is called per kept event purely for its `gamma.unmapped_tag` side effect — its return is NOT used to re-route, so a dual-tagged event keeps the category of the loop that claimed it (no last-writer category flip; consistent with the dedup-skip first-by-priority).
- **Single release/close in one `finally` (WR-04/WR-05):** lock released + client closed + session closed (when not overridden) + redis aclosed (when not overridden) exactly once; the lock-held early-return aclosed redis without creating a client/session.

## Deviations from Plan

None - plan executed exactly as written.

The plan's `<action>` for Task 1 lists the post-commit `changed_markets` publish as "optional"; I included it (mirroring `_run_poll_sync`) so curated-event odds changes propagate to the realtime layer exactly like the top-25 path did — additive, behind the same swallow-publish-errors guard, no scope change.

## Issues Encountered

- **Module-level `Settings()` blocks a bare `python -c` import of `tasks.py`/`celery_app.py`** (the import chain constructs `Settings()` which requires `DATABASE_URL`/`REDIS_URL`/`SECRET_KEY`). This is an environment artifact, not a code problem — pytest imports the modules cleanly via its conftest env, and the symbol/registry/one-liner cross-checks pass when run with dummy env vars exported. No code change needed.
- **`ruff` flagged two `E501` on the `fake_fetch` test signatures + a format diff:** `uv run ruff format` auto-wrapped them; `ruff check` + `format --check` + `mypy` are all clean on the three changed files afterward. Per the Windows-worktree policy, ruff was run only on the files I touched (the worktree file set flip-flops on a full-repo run).

## Verification Performed

- `cd backend && uv run pytest tests/polymarket/test_tasks.py -m unit -x` -> **10 passed, 2 deselected** (4 pre-existing poll-lock + the inverted `test_beat_schedule_entries` + 4 new poll_events tests). Run PER-MODULE per the Windows-worktree policy.
- Task 2 one-liner (`from app.celery_app import celery_app ...`, run with dummy env) -> printed **`ok`**: `poll-polymarket-top25` absent; `poll-polymarket-events`@300.0 -> the events task; `snapshot-odds`@300.0, `detect-polymarket-resolutions`@60.0, `reconcile-wallets-nightly` all intact.
- Celery task-registry cross-check (dummy env): both `app.integrations.polymarket.tasks.poll_polymarket_top25` (back-compat) and `...poll_polymarket_events` are registered.
- `uv run ruff check` + `ruff format --check` + `mypy` on `tasks.py`, `celery_app.py`, `test_tasks.py` -> all green (files-touched only).
- **Phase gate (full `pytest tests/` + ruff + mypy across the repo) deferred to Linux CI** per the Windows-worktree policy ([[xprediction-backend-fullsuite-testcontainers-flake]]) — the local full suite flakes on testcontainers contention across unrelated modules.

## Deploy Note (REQUIRED — redbeat schedule reload, Pitfall 5)

**redbeat persists the beat schedule in Redis** (`celery_app.conf.beat_scheduler = "redbeat.RedBeatScheduler"`, `redbeat_redis_url`), and the running beat loads it on start. The code swap (dropping `poll-polymarket-top25`, adding `poll-polymarket-events`) is **inert until the beat process is RESTARTED**:

- **Until restart:** the running beat keeps firing `poll-polymarket-top25` @30s from the Redis-persisted schedule, and `poll-polymarket-events` never starts. No `market_groups` rows / curated catalog will appear.
- **On deploy:** restart the beat service so redbeat reloads the new schedule. Local dev: `docker compose restart` the beat service (see [[xprediction-local-runtime-recipe]]).
- **Harmlessness of the lingering key:** the dropped `poll-polymarket-top25` redbeat key may linger in Redis until restart; because the `poll_polymarket_top25` task stays importable + registered, a stray fire is a benign no-op (it just re-upserts top-25 markets, which CONTEXT leaves intact) — never an unregistered-task crash.
- **Post-restart manual verification (deploy-time, not a local gate):** confirm `poll_events.category_synced` logs appear and `poll_complete` (top-25) logs stop.

## Next Phase Readiness

- The curated sync is fully wired and unit-proven. After a beat restart, `poll_polymarket_events` @300s will populate `market_groups` + stamp `Market.category` from live Gamma `/events` — the real data **Phase 15 (Event Settlement)** uses for mirrored-children verification and **Phase 16 (Catalog API)** reads for category browse.
- The cross-category first-by-priority dedup (CAT-02) lives in this task layer (`seen_event_ids`); `sync_events` continues to do only within-event `conditionId` dedup — the contract boundary noted in 14-03's readiness holds.
- No blockers. Zero new dependencies. The only operational requirement is the beat restart documented above.

---
*Phase: 14-curated-per-category-gamma-sync*
*Completed: 2026-06-05*

## Self-Check: PASSED

- Files: `14-04-SUMMARY.md`, `backend/app/integrations/polymarket/tasks.py`, `backend/app/celery_app.py`, `backend/tests/polymarket/test_tasks.py` all present on disk.
- Commits: `0ed3d5e` (Task 1 feat), `06f25ad` (Task 2 feat), `420ce2a` (Task 3 test) all present in git history.
- Tests: `uv run pytest tests/polymarket/test_tasks.py -m unit -x` -> 10 passed, 2 deselected.
- Ruff check + format + mypy: clean on the three changed files (files-touched only, per Windows-worktree policy).
- `.planning/config.json` (`use_worktrees`) NOT staged/committed — confirmed via `git status --short`.
