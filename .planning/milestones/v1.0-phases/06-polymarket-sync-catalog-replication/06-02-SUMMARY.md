---
phase: 06-polymarket-sync-catalog-replication
plan: 02
subsystem: polymarket-sync-tasks
tags: [celery, redis-lock, beat-schedule, home-api, sorting, polymarket]
dependency_graph:
  requires: [06-01]
  provides: [celery-poll-task, celery-snapshot-task, home-market-list-api]
  affects: [celery-beat-schedule, public-markets-endpoint, market-schemas]
tech_stack:
  added: []
  patterns: [redis-setnx-lock, asyncio-run-wrapper, house-first-sorting, computed-model-field]
key_files:
  created:
    - backend/app/integrations/polymarket/tasks.py
    - backend/tests/polymarket/test_tasks.py
    - backend/tests/polymarket/test_home_list.py
  modified:
    - backend/app/celery_app.py
    - backend/app/markets/schemas.py
    - backend/app/markets/service.py
    - backend/app/markets/router.py
    - backend/tests/markets/test_public_router.py
decisions:
  - "Used asyncio.run() inside sync Celery tasks to wrap async logic -- Celery tasks are sync by design, asyncio.run creates a fresh event loop per task invocation"
  - "Dependency injection via _override params on _run_poll_sync/_run_snapshot_odds for testability -- avoids global state mutation in tests"
  - "Public GET /api/v1/markets changed from PaginatedResponse to flat list -- D-01 requires house-first + PM-by-volume sorting, pagination not needed for max ~50 items"
metrics:
  duration: ~14m
  completed: 2026-05-28T09:51:00Z
---

# Phase 06 Plan 02: Celery Tasks + Home Market List API Summary

Celery Beat poll (30s) and snapshot (300s) tasks with Redis SETNX dedupe lock, plus house-first public market list API with volume and computed source_url fields -- 11 new tests green.

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Celery tasks, Redis lock, and Beat schedule | 2846c52 | tasks.py, celery_app.py, test_tasks.py |
| 2 | Service, router, schema for house-first market list (D-01) | d50ff32 | schemas.py, service.py, router.py, test_home_list.py, test_public_router.py |

## What Was Built

### Celery Tasks (tasks.py)
- `poll_polymarket_top25`: sync Celery task wrapping async `_run_poll_sync` via `asyncio.run()`
- `_run_poll_sync`: acquires Redis SETNX lock (TTL=25s), fetches top-25 via GammaClient, upserts via `PolymarketAdapter.sync_top25()`, releases lock in finally block
- `snapshot_odds`: sync Celery task wrapping async `_run_snapshot_odds`
- `_run_snapshot_odds`: queries all OPEN markets (both HOUSE and POLYMARKET) with selectinload(outcomes), writes OddsSnapshot row per outcome
- Both tasks accept `session_override` and `redis_override` kwargs for test injection
- Error handling: catches all exceptions, logs via structlog, reports to Sentry

### Redis SETNX Lock (T-06-05)
- `acquire_poll_lock`: `redis.set(LOCK_KEY, "1", nx=True, ex=ttl)` with TTL from settings (25s)
- `release_poll_lock`: `redis.delete(LOCK_KEY)` in finally block
- Lock key: `xpredict:poll:polymarket:lock` (fixed pattern per T-06-06)
- TTL < poll interval (25s < 30s) ensures crashed tasks auto-release before next poll

### Beat Schedule (celery_app.py)
- `poll-polymarket-top25`: task at 30.0s interval
- `snapshot-odds`: task at 300.0s interval

### MarketListItem Schema (schemas.py)
- Added fields: `volume` (Decimal, serialized to str), `volume_24hr` (Decimal, serialized to str), `source_market_id` (str | None), `source_url` (str | None)
- `source_url` computed via `model_validator(mode="after")`: Polymarket markets get `https://polymarket.com/event/{source_market_id}`, house markets get None (T-06-07)

### MarketService.list_home_markets (service.py)
- Two separate queries concatenated per D-01:
  - Query 1: HOUSE + OPEN, selectinload(outcomes), ORDER BY created_at DESC
  - Query 2: POLYMARKET + OPEN, selectinload(outcomes), ORDER BY volume_24hr DESC, LIMIT 25
- Returns `list[Market]` (no pagination needed for max ~50 items)

### Public Router (router.py)
- `GET /api/v1/markets` changed from `PaginatedResponse[MarketListItem]` to `list[MarketListItem]`
- Calls `MarketService.list_home_markets()` instead of `list_markets()`
- Slug-based get and bet-check endpoints unchanged

## Test Results

11 new tests (5 unit + 6 integration):

**Task 1 - test_tasks.py (4 unit + 3 integration):**
- test_acquire_poll_lock_calls_setnx: SETNX with nx=True
- test_release_poll_lock_deletes_key: deletes lock key
- test_poll_skipped_when_lock_held: GammaClient NOT called when lock held
- test_poll_acquires_and_releases_lock: lock acquired and released around sync
- test_beat_schedule_entries: both task names in beat_schedule with correct intervals
- test_poll_upserts_markets: 2 mocked Gamma markets upserted to DB
- test_snapshot_odds_writes_rows: 2 OddsSnapshot rows created for 1 market with 2 outcomes

**Task 2 - test_home_list.py (4 integration):**
- test_house_first_ordering: house market at index 0, PM at index 1
- test_polymarket_sorted_by_volume: higher volume PM first in PM section
- test_only_open_markets_shown: closed markets excluded
- test_public_endpoint_returns_mixed_list: flat list, house first, volume + source_url present

**Updated existing tests (test_public_router.py):**
- test_public_list_returns_open_markets: updated assertions for flat list response
- test_public_list_excludes_closed_markets: updated assertions for flat list response

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated existing public_router tests for new response format**
- Found during: Task 2
- Issue: Existing tests in test_public_router.py checked for `"items" in body` and `body["total"]` (paginated format), but the endpoint now returns a flat list
- Fix: Changed assertions to `isinstance(body, list)` and `len(body) >= 1`, items accessed directly from `body` instead of `body["items"]`
- Files modified: backend/tests/markets/test_public_router.py
- Commit: d50ff32

**2. [Rule 1 - Bug] Fixed ruff violations in schemas and test files**
- Found during: Task 2
- Issue: Import line too long (E501), unsorted imports (I001), unused import (F401), nested with statements (SIM117)
- Fix: Split pydantic imports to multi-line, removed unused `select` import, combined nested async with blocks
- Files modified: backend/app/markets/schemas.py, backend/tests/polymarket/test_home_list.py
- Commit: d50ff32

## Known Issues (Pre-existing, Out of Scope)

**test_service.py::TestMarketServiceList::test_list_markets_with_pagination** fails when run in the same session as polymarket integration tests that use `engine.connect()` + `commit()`. This is a pre-existing session-scoped fixture isolation issue: the `sample_market` conftest fixture uses the shared `async_session` (session scope), and cross-test commits via the engine create permanent data that invalidates the identity map. The `list_markets` method itself is unchanged. This issue exists on the base commit when running polymarket + markets test suites together.

## Verification Results

- `uv run pytest tests/polymarket/test_tasks.py -x -q`: 7 passed
- `uv run pytest tests/polymarket/test_home_list.py -x -q`: 4 passed
- `uv run pytest tests/polymarket/test_home_list.py tests/markets/test_public_router.py -x -q`: 10 passed
- `uv run ruff check app/integrations/polymarket/ app/markets/`: All checks passed
- Beat schedule contains both task entries with correct intervals (30.0, 300.0)
- GET /api/v1/markets returns house-first list with volume and source_url

## Self-Check: PASSED

All created files verified present. Both task commits (2846c52, d50ff32) verified in git log.
