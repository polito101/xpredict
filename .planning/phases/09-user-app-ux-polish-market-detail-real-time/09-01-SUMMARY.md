---
phase: 09-user-app-ux-polish-market-detail-real-time
plan: 01
subsystem: api
tags: [websocket, redis, pubsub, fastapi, real-time, celery, polymarket, odds]

# Dependency graph
requires:
  - phase: 06-polymarket-sync
    provides: "PolymarketAdapter.sync_top25 (sets Outcome.current_odds on poll) + _run_poll_sync holding an AioRedis lock"
  - phase: 08-admin-crm
    provides: "MarketService.update_market admin odds-edit branch (current_odds + OddsSnapshot) + PATCH /api/v1/admin/markets/{id}"
provides:
  - "app/realtime/{manager,subscriber,router,publisher}.py — FastAPI native WS price-broadcast pipeline lifted from validated spike 003"
  - "Public WS endpoint /ws/markets/{market_id} (read-only, ping/pong, per-market isolation)"
  - "redis_subscriber background task wired into app/main.py lifespan (psubscribe prices:*, started/cancelled per worker)"
  - "publish_odds_change (sync) + publish_odds_change_async (held AioRedis) — lean string-odds delta to prices:{market_id}"
  - "Producer hook #1: admin odds edit publishes POST-COMMIT in the router"
  - "Producer hook #2: Polymarket poll publishes POST-COMMIT, per-market, on-change only"
affects: [09-03-frontend-chart-and-socket-hook, phase-11-hardening]

# Tech tracking
tech-stack:
  added: []  # ZERO new backend runtime deps — fastapi[standard]/uvicorn[standard]/redis>=5.0 already pinned; websockets is test-only (bundled by fastapi[standard])
  patterns:
    - "Cross-process fan-out: producers redis.publish(prices:{id}) → uvicorn psubscribe(prices:*) → ConnectionManager.broadcast → WS clients"
    - "Publish-post-commit only at every producer site (clients never render a rolled-back price)"
    - "Publish-on-change only for the poll (compare current_odds != price before recording a delta)"
    - "Lean WS delta: {type, market_id, outcomes:[{outcome_id, odds}], ts} — string odds (Numeric(8,6) at 6dp), NO PII"
    - "Service returns (entity, side-effects) tuple so the router owns the post-commit publish"

key-files:
  created:
    - backend/app/realtime/__init__.py
    - backend/app/realtime/manager.py
    - backend/app/realtime/subscriber.py
    - backend/app/realtime/router.py
    - backend/app/realtime/publisher.py
    - backend/tests/realtime/__init__.py
    - backend/tests/realtime/conftest.py
    - backend/tests/realtime/test_ws_fanout.py
    - backend/tests/realtime/test_ws_isolation.py
    - backend/tests/realtime/test_ws_reconnect.py
    - backend/tests/markets/test_update_market_publishes.py
    - backend/tests/polymarket/test_poll_publishes.py
  modified:
    - backend/app/main.py
    - backend/app/markets/service.py
    - backend/app/markets/router.py
    - backend/app/integrations/polymarket/adapter.py
    - backend/app/integrations/polymarket/tasks.py
    - backend/tests/markets/test_service.py

key-decisions:
  - "WS keyed by market UUID (/ws/markets/{market_id}, channel prices:{market_id}) — producers hold market.id; avoids a slug lookup in the hot path (RESEARCH Claude's-discretion)."
  - "Poll reuses its already-held AioRedis to publish (publish_odds_change_async) rather than opening a second sync connection (RESEARCH Open Q2)."
  - "Admin edit uses a short-lived sync redis client (publish_odds_change) — simplest for the request-context call."
  - "format_odds quantizes to Numeric(8,6) (6dp) so the WS odds string EXACTLY matches what GET /markets/{slug} emits via OutcomeRead after the DB round-trip (SP-1/SP-4)."
  - "MarketService.update_market now returns (market, odds_deltas); the router publishes the deltas post-commit. Service only flush()es, never publishes inside the transaction."

patterns-established:
  - "Realtime module (app/realtime/) is the single home for the WS pipeline — lifted verbatim from spike 003, forensic _latency_ms/_server_ts/event_log stripped for production."
  - "Each producer site swallows Redis publish errors (log.warning) so a Redis hiccup never fails a committed admin edit or poll."

requirements-completed: [MKT-04]

# Metrics
duration: ~30min
completed: 2026-05-29
---

# Phase 9 Plan 01: Real-Time WebSocket Price Broadcasting (backend) Summary

**FastAPI native WebSocket + redis.asyncio pub/sub price-broadcast pipeline lifted from validated spike 003, wired into the app lifespan, with post-commit publish hooks at the admin odds edit and the Polymarket poll (on-change only).**

## Performance

- **Duration:** ~30 min (first task commit 17:58:07 → Task 3 commit 18:28:37, 2026-05-29; spans a mid-Task-3 executor crash + this continuation closeout)
- **Started:** 2026-05-29T17:58:07+02:00 (Task 1 commit)
- **Completed:** 2026-05-29T18:28:37+02:00 (Task 3 commit)
- **Tasks:** 3
- **Files modified:** 18 (12 created, 6 modified)

## Accomplishments

- **WS pipeline (Task 2):** `ConnectionManager` (per-market `set[WebSocket]` + lock-safe broadcast), `redis_subscriber` (`psubscribe("prices:*")` → `broadcast`), and the public `/ws/markets/{market_id}` endpoint — all lifted verbatim from the VALIDATED spike 003, with the dev-only forensic fields stripped. The subscriber is started via `asyncio.create_task` in the existing `app/main.py` lifespan and cancelled in `finally` (one per worker → multi-worker correct).
- **Producer hook #1 — admin odds edit (Task 3):** `MarketService.update_market` now returns `(market, odds_deltas)` and only `flush()`es; `router.update_market` publishes via `publish_odds_change` **AFTER** `session.commit()`, wrapped in try/except so a Redis hiccup never 500s a successful edit. Zero publishes on a no-odds PATCH.
- **Producer hook #2 — Polymarket poll (Task 3):** `adapter.sync_top25` accumulates `changed_markets` only when `existing_outcome.current_odds != price` AND only after a successful per-market flush (a market that hits the IntegrityError rollback+continue never records a delta). `_run_poll_sync` publishes via the already-held `AioRedis` (`publish_odds_change_async`) **AFTER** `session.commit()`, per-market, on-change only.
- **Wave-0 RED scaffolds (Task 1):** `tests/realtime/` fan-out (<2s), per-market isolation, and reconnect (live-only, no replay) integration tests + conftest (WS test client via the `websockets` lib + real-redis fixture). RED on missing `app.realtime` until Tasks 2-3 landed — now GREEN.
- **Constraints honored:** ZERO new backend runtime dependencies; NO new Celery Beat entry; lean string-odds delta with NO PII; channel `prices:{market_id}`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave-0 test scaffolds + realtime conftest** - `d32ee28` (test)
2. **Task 2: Lift spike 003 into app/realtime/ + wire app/main.py lifespan** - `de1f314` (feat)
3. **Task 3: Producer hooks — admin odds edit (post-commit) + Polymarket poll (on-change)** - `6b4079e` (feat)

**Plan metadata:** (this SUMMARY + STATE/ROADMAP commit — see closeout commit)

## Files Created/Modified

- `backend/app/realtime/manager.py` - `ConnectionManager` (per-market socket set, lock-safe broadcast, dead-socket pruning) + module-level `manager` singleton.
- `backend/app/realtime/subscriber.py` - `redis_subscriber(manager, redis_url)` — `psubscribe("prices:*")`, decode channel → market_id, broadcast; CancelledError-safe cleanup.
- `backend/app/realtime/router.py` - `realtime_router` with public `@websocket("/ws/markets/{market_id}")` (ping→pong, disconnect cleanup in finally).
- `backend/app/realtime/publisher.py` - `publish_odds_change` (sync), `publish_odds_change_async` (held AioRedis), `format_odds` (Numeric(8,6) string), `build_price_update_payload` (lean delta).
- `backend/app/main.py` - lifespan starts/cancels `redis_subscriber`; includes `realtime_router`.
- `backend/app/markets/service.py` - `update_market` returns `(market, odds_deltas)`; builds the delta list in the odds branch, flush-only (no publish inside tx).
- `backend/app/markets/router.py` - `update_market` publishes `odds_deltas` post-commit in a try/except (log+swallow).
- `backend/app/integrations/polymarket/adapter.py` - `sync_top25` accumulates `self.changed_markets` (on-change, post-flush only).
- `backend/app/integrations/polymarket/tasks.py` - `_run_poll_sync` publishes `adapter.changed_markets` post-commit via the held AioRedis, per-market, log+swallow.
- `backend/tests/realtime/{__init__,conftest}.py` + `test_ws_{fanout,isolation,reconnect}.py` - WS integration scaffolds (real Redis).
- `backend/tests/markets/test_update_market_publishes.py` - producer hook #1: publish-once-post-commit + no-publish-on-no-odds.
- `backend/tests/polymarket/test_poll_publishes.py` - producer hook #2: publish-on-change + no-publish-on-unchanged-tick.
- `backend/tests/markets/test_service.py` - updated for the new `(market, odds_deltas)` tuple return (criteria-only → `[]`; odds edit → string deltas).

## Verification Results

Run in this continuation against a real Redis container (`romantic-poincare-09eaf1-redis-1`, healthy on :6379) + ephemeral testcontainer Postgres. All results are genuine — nothing faked.

| Check | Command | Result |
|-------|---------|--------|
| Task 3 producer tests | `uv run pytest tests/markets/test_update_market_publishes.py tests/polymarket/test_poll_publishes.py -x` | **4 passed** (4.77s) |
| Quick non-integration suite | `uv run pytest -m "not integration"` | **127 passed, 2 skipped** (Stripe stubs), 9.48s |
| realtime + markets + polymarket modules (incl. Task 1's 3 WS tests now GREEN) | `uv run pytest tests/realtime/ tests/markets/ tests/polymarket/` | **100 passed** (20.79s) |
| ruff check | `uv run ruff check` (8 changed files) | **All checks passed** |
| ruff format | `uv run ruff format --check` (8 changed files) | **8 files already formatted** (after applying format to router.py — see Deviations) |
| mypy strict | `uv run mypy` (5 changed app files) | **Success: no issues found** |
| money-column lint (WAL-05) | `uv run python scripts/lint_money_columns.py` | **OK: 6 files checked, 0 warnings** |

> The two `ResourceWarning: unclosed socket` lines on testcontainer teardown are a harmless cleanup artifact of testcontainers' HTTP probe, not a test failure.

## TDD Gate Compliance

- **Task 1 (RED) → `d32ee28` `test(...)`** and **Task 2 (GREEN) → `de1f314` `feat(...)`** form a clean RED→GREEN gate for the three WS pipeline tests (`test_ws_fanout`/`isolation`/`reconnect`).
- **Task 3** combined its two RED producer test files (`test_update_market_publishes.py`, `test_poll_publishes.py`) **and** the implementation in a single `feat(...)` commit (`6b4079e`), rather than a separate `test(...)` RED commit followed by a `feat(...)` GREEN commit. This is because the prior executor authored the Task-3 tests + implementation as one uncommitted unit and crashed before committing; this continuation was instructed to commit the existing work atomically as one commit. The tests are nonetheless genuine RED→GREEN signals — they assert the producer-hook behavior and pass only because the hooks exist (verified: 4/4 green). No production behavior was lost; only the per-gate commit granularity differs for Task 3.

## Decisions Made

See `key-decisions` in frontmatter. Highlights:
- WS keyed by market UUID (producers hold `market.id`; channel `prices:{market_id}`).
- Poll reuses its held `AioRedis` (`publish_odds_change_async`); admin edit uses a short-lived sync client.
- `format_odds` quantizes to 6dp so the socket odds string matches the REST `OutcomeRead` string exactly.
- Service returns `(market, odds_deltas)`; the router owns the post-commit publish.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Applied `ruff format` to `app/markets/router.py`**
- **Found during:** Task 3 closeout (pre-commit readiness)
- **Issue:** `ruff format --check` flagged `app/markets/router.py` for reformatting (the post-commit publish block, incl. a long `log.warning(...)` line). The pre-commit `ruff-format` hook would have reformatted-and-failed the commit otherwise.
- **Fix:** Ran `uv run ruff format app/markets/router.py` (formatting only — no logic change).
- **Files modified:** backend/app/markets/router.py
- **Verification:** `ruff format --check` → "8 files already formatted"; commit hooks passed clean.
- **Committed in:** `6b4079e` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking/style). **Impact on plan:** Formatting-only; the implementation matches the plan and RESEARCH (Pitfall 3 post-commit publish, Pitfall 4 on-change poll, lean string-odds delta, channel `prices:{market_id}`) exactly. No scope creep, no behavior change.

## Issues Encountered

- **Prior executor crash (API socket error) at end of Task 3.** Task 3 was fully implemented but uncommitted. This continuation verified the work against the plan spec + 09-RESEARCH/09-VALIDATION, ran the full verification honestly, and committed Task 3 atomically. No rework of Tasks 1-2.

## Manual-Verify / Could-Not-Run-Here

All automated checks for this plan ran and passed **here** (real Redis + testcontainer Postgres were available). The remaining item is the cross-tier browser round-trip, which is manual by design (per 09-VALIDATION.md "Manual-Only Verifications"):

| Behavior | Why manual | How to verify |
|----------|------------|---------------|
| Full MKT-04 round-trip on a live page (admin odds edit / Polymarket poll → YES % animates on `/markets/{slug}` within 2s + Live dot pulses) | Requires the full stack running (uvicorn + Celery beat + Redis + Next dev) + a browser. The automated WS tests cover the producer→Redis→subscriber→WS-client pipeline in isolation but not the end-to-end browser render. The frontend slice (Plan 09-03) is not built yet. | Run `bin/dev` (or `docker compose up`); open `/markets/{slug}`; in another tab PATCH the market's `odds_yes` via the admin API; confirm the YES % updates in place + the Live dot pulses within 2s. (Deferred until Plan 09-03 ships the `use-market-socket` hook + chart.) |

> Note: the WS subscriber's clean start/cancel with the app lifespan ("no Event-loop-is-closed on shutdown", Pitfall 4) is exercised structurally by the lifespan wiring + the realtime conftest's test app; a full uvicorn reload observation is part of the same live-stack manual check above.

## Next Phase Readiness

- **Backend half of MKT-04 is complete and green.** The producer→Redis→subscriber→WS-client pipeline is end-to-end ready; Plan 09-03 (frontend) can now connect a `"use client"` socket to `/ws/markets/{market_id}` and consume the `{type:"price_update", market_id, outcomes, ts}` delta.
- **Contract for the frontend:** WS URL must be `NEXT_PUBLIC_WS_URL`-prefixed (e.g. `ws://localhost:8000`); odds arrive as strings (6dp), already matching the SSR `OutcomeRead` payload — patch in place, no float math.
- **No blockers.** Plan 09-02 (price-history + activity endpoints) and 09-03/09-04 (frontend) remain for the phase.

## Self-Check: PASSED

- Created files verified on disk: `app/realtime/{publisher,manager,subscriber,router}.py`, `tests/markets/test_update_market_publishes.py`, `tests/polymarket/test_poll_publishes.py`, `09-01-SUMMARY.md` — all FOUND.
- Task commits verified in git history: `d32ee28` (Task 1), `de1f314` (Task 2), `6b4079e` (Task 3) — all FOUND.

---
*Phase: 09-user-app-ux-polish-market-detail-real-time*
*Completed: 2026-05-29*
