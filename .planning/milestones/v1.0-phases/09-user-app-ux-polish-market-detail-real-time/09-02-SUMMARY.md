---
phase: 09-user-app-ux-polish-market-detail-real-time
plan: 02
subsystem: api
tags: [fastapi, sqlalchemy, pydantic, postgres, downsampling, anonymization, market-detail]

# Dependency graph
requires:
  - phase: 09-01
    provides: "app/realtime/publisher.py (format_odds, Numeric(8,6) odds-string idiom); MarketService.update_market returning odds_deltas"
  - phase: 04-markets-domain
    provides: "Market/Outcome/OddsSnapshot models, public_market_router, OutcomeRead.serialize_decimal idiom"
  - phase: 05-bets-settlement
    provides: "Bet model (plain-UUID market_id/outcome_id, stake Money, created_at)"
provides:
  - "GET /api/v1/markets/{slug}/price-history — server-side YES-line series (raw 24h/7d, hourly-downsampled 30d), window allowlist, money/odds as strings"
  - "GET /api/v1/markets/{slug}/activity — last-20 bets fully anonymized server-side (no user identity on the wire)"
  - "PricePoint / PriceHistoryResponse / ActivityItem schemas (Decimal→string serializers)"
  - "MarketService.price_history(slug, window) + MarketService.recent_activity(slug, limit)"
affects: [09-03-frontend-chart-socket, 09-04-order-entry-activity-feed, market-detail-page]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Server-side time-series downsampling via Postgres DISTINCT ON (date_trunc('hour', …)) — latest snapshot per hour bucket"
    - "Window allowlist as a FastAPI Literal[...] query param → automatic 422 before service runs; cutoff derived from the validated value (never interpolated)"
    - "Server-side anonymization: SELECT projects only non-identity columns AND the response schema has no user field (defense in depth, T-09-05)"

key-files:
  created:
    - backend/tests/markets/test_price_history.py
    - backend/tests/markets/test_activity_feed.py
  modified:
    - backend/app/markets/schemas.py
    - backend/app/markets/service.py
    - backend/app/markets/router.py

key-decisions:
  - "30d downsampling uses DISTINCT ON (date_trunc('hour', snapshot_at)) ORDER BY bucket, snapshot_at DESC — keeps the latest snapshot per hour bucket; a Python re-sort restores ascending-by-time for the chart (DISTINCT ON forces the bucket as the leading ORDER BY key)."
  - "Window allowlist enforced via Literal[\"24h\",\"7d\",\"30d\"] on the query param so FastAPI returns 422 BEFORE the slug lookup; the service trusts the validated value and derives the cutoff from _WINDOW_CUTOFFS (T-09-08, no SQL interpolation)."
  - "price_history resolves the market by (id, status) only — no eager relationship load — since it needs just the YES outcome id + a snapshot scan; 404 mirrors get_market_public (OPEN/CLOSED only)."
  - "recent_activity joins outcomes on outcome_id and projects ONLY (stake, created_at, label) — user_id/email/display_name are never selected; the ActivityItem schema additionally has no user field (two independent guards)."

patterns-established:
  - "Decimal-as-string on all new read schemas via @field_serializer returning str(v) (SP-1)"
  - "HTTP-endpoint integration tests seed COMMITTED data via the engine (not the rolled-back async_session) and clean up in finally — mirrors test_public_router.py — because ASGITransport uses the app's own committed session"

requirements-completed: [MKT-03]

# Metrics
duration: 6min
completed: 2026-05-29
---

# Phase 9 Plan 02: Market-Detail Backend Read Surface Summary

**Two public read endpoints for the market detail page: a YES-line price-history endpoint with server-side hourly downsampling beyond 7 days (Postgres DISTINCT ON), and a last-20 recent-activity feed anonymized server-side so no user identity ever reaches the wire (MKT-03).**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-29T16:34:39Z
- **Completed:** 2026-05-29T16:40:37Z
- **Tasks:** 2
- **Files modified:** 5 (3 app, 2 test)

## Accomplishments

- `GET /api/v1/markets/{slug}/price-history?window=24h|7d|30d` — raw 5-min `OddsSnapshot` points for the YES outcome on 24h/7d; **server-side hourly-bucketed** series for 30d (the browser never receives ~8640 raw points, T-09-07). `window` defaults to `7d` and is constrained to the allowlist (422 otherwise, T-09-08). `probability` is a JSON string (SP-1). 404 on unknown/non-public market. A <2-snapshot market returns an empty/low-data payload the frontend renders as the placeholder.
- `GET /api/v1/markets/{slug}/activity` — last 20 bets newest-first, **anonymized server-side** to `{outcome, amount, created_at}`; `user_id`/`email`/`display_name` are never selected in the SQL and the response schema has no user field (T-09-05). `amount` is a JSON string (SP-1).
- Three Pydantic v2 schemas (`PricePoint`, `PriceHistoryResponse`, `ActivityItem`) and two `MarketService` methods (`price_history`, `recent_activity`).
- Verification ran for REAL against testcontainer Postgres: both plan verify commands green; full `tests/markets/` module **86 passed**.

## Task Commits

Each task was committed atomically:

1. **Task 1: Price-history + activity schemas and service methods (downsample + anonymize)** - `f415452` (feat)
2. **Task 2: Public GET endpoints + 30-day-backfill downsampling test** - `e93814c` (feat)

**Plan metadata:** (final docs commit — STATE/ROADMAP + this SUMMARY)

_TDD note: Task 1 was RED→GREEN within a single feat commit — the schema unit tests (the plan's `-m "not integration"` gate) were written first and verified failing on `ImportError` (7 failed), then the schemas + service methods turned them green (7 passed). Task 2 was likewise RED (endpoint returned 404 before the route existed) → GREEN (24 passed incl. integration). The integration tests that Task 2 turns green ship in the Task 1 commit (deselected by the Task 1 gate)._

## Files Created/Modified

- `backend/app/markets/schemas.py` - Added `PricePoint` (probability→string), `PriceHistoryResponse` (window + points), `ActivityItem` (outcome/amount→string/created_at, no user field).
- `backend/app/markets/service.py` - Added `MarketService.price_history` (raw 24h/7d; 30d DISTINCT ON hourly bucket) and `MarketService.recent_activity` (Bet JOIN Outcome, last-20, no identity). Added `_WINDOW_CUTOFFS`/`_RAW_WINDOWS` allowlist constants and the `Bet` + new-schema imports.
- `backend/app/markets/router.py` - Added `GET /{slug}/price-history` (Literal window, 422 allowlist) and `GET /{slug}/activity` (list[ActivityItem]) on `public_market_router`, placed as siblings of `/{slug}/bet-check` so they do not shadow the bare `/{slug}` route.
- `backend/tests/markets/test_price_history.py` - 4 unit (schema serialization) + 9 integration (service downsampling, 404, low-data; live HTTP 30d-backfill count assertion, 7d default, bare-slug no-shadow regression).
- `backend/tests/markets/test_activity_feed.py` - 3 unit (no user field, amount-as-string) + 8 integration (service last-20/anonymized/empty/404; live HTTP raw-JSON no-user-identity negative assertion).

## Decisions Made

- **DISTINCT ON for the 30d downsample.** Postgres `DISTINCT ON (date_trunc('hour', snapshot_at))` with `ORDER BY bucket, snapshot_at DESC` returns the latest snapshot per hour bucket in one query (09-RESEARCH Pattern 5). Because DISTINCT ON forces the bucket as the leading ORDER BY key, the result is bucket-ordered; a small Python `sorted(..., key=lambda p: p.ts)` restores ascending-by-time for the chart. 24h/7d skip bucketing entirely (raw rows).
- **Window allowlist as a typed query param.** `window: Literal["24h","7d","30d"]` makes FastAPI reject out-of-allowlist values with 422 BEFORE the handler/service runs (validated this fires before the slug lookup). The service derives the cutoff from `_WINDOW_CUTOFFS[window]` — no raw interval string ever reaches SQL (T-09-08).
- **Two independent anonymization guards.** The `recent_activity` SELECT projects only `(stake, created_at, label)`, and `ActivityItem` has no `user_id`/`email`/`display_name` field. Either alone would suffice; both together are defense-in-depth for the privacy requirement (T-09-05, CONTEXT Area 1). Tests assert both the schema field set AND the raw HTTP JSON body.
- **HTTP-endpoint tests seed committed data via the engine.** The `ASGITransport` client uses the app's own committed DB session, not the rolled-back `async_session` fixture, so the live-endpoint tests INSERT via `engine.connect()` + `commit()` and delete in `finally` (mirroring the existing `test_public_router.py` convention). Service-level tests use the transactional `async_session` fixture.

## Deviations from Plan

None - plan executed exactly as written. No bugs, missing-critical functionality, blocking issues, or architectural changes were encountered (Rules 1-4 not triggered). No package installs (read-only endpoints over existing models — T-09-SC confirmed no install gate). No auth gates (public reads).

## Issues Encountered

- **Interpreter-shutdown `ResourceWarning` noise.** After the integration runs reported `passed`, the process emitted `ResourceWarning: unclosed connection/transport/socket` from asyncpg + the Windows Proactor event loop during garbage collection at exit. These appear AFTER the green summary line, are not test failures, and are a known Windows+asyncpg teardown artifact (the suite already ignores analogous asyncio/websockets transitional warnings in `pyproject.toml filterwarnings`). No action taken — exit was clean and all assertions passed.

## User Setup Required

None - no external service configuration required. Both endpoints are public reads over existing tables; no new env vars, secrets, or dashboard config.

## Next Phase Readiness

- **09-03 (frontend chart + socket)** can now SSR-fetch `GET /{slug}/price-history?window=7d` and feed `points[].probability` (strings) into the Recharts YES line; the 30d window is already downsampled server-side so the chart renders without a perf regression.
- **09-04 (order-entry + activity feed)** can SSR-fetch `GET /{slug}/activity` and render the anonymized rows ("Someone backed YES · $X · Nm ago") with no client-side stripping needed.
- No blockers. The `MarketRead` detail payload already returns `resolution_criteria` + `outcomes[].current_odds`, so the two new endpoints complete the MKT-03 backend data surface.

## Self-Check: PASSED

- All 5 source files (3 app modified, 2 tests created) verified on disk.
- Both task commits verified in git history: `f415452`, `e93814c`.
- Both plan verify commands ran for real against testcontainer Postgres and passed (Task 1 gate: 7 unit passed; Task 2 full: 24 passed; full `tests/markets/`: 86 passed).

---
*Phase: 09-user-app-ux-polish-market-detail-real-time*
*Completed: 2026-05-29*
