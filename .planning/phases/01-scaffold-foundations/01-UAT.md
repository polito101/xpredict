---
status: complete
phase: 01-scaffold-foundations
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md]
started: 2026-05-26T10:00:00Z
updated: 2026-05-26T10:45:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: |
  Stop cc_redis + cc_postgres (crypto-casino containers occupying ports 5432/6379).
  Run .\bin\dev.ps1 (Windows) or ./bin/dev (POSIX) from xpredict/.
  All 8 services come up healthy:

    docker compose ps
    SERVICE    STATUS
    backend    Up X minutes (healthy)
    beat       Up X minutes (healthy)
    db         Up X minutes (healthy)
    flower     Up X minutes (healthy)
    frontend   Up X minutes (healthy)
    mailpit    Up X minutes (healthy)
    redis      Up X minutes (healthy)
    worker     Up X minutes (healthy)

  Followed by: alembic upgrade head exits 0, no migration errors.
result: issue
reported: "container xpredict-worker-1 is unhealthy"
severity: major
fix_applied: |
  Root cause 1 — beat heartbeat thread never started on restart:
  `-S redbeat.RedBeatScheduler` on CLI caused RedBeat's beat_init receiver
  (acquire_distributed_beat_lock) to register before _init_beat. On restart,
  the lock was held from the previous run, so acquire_distributed_beat_lock
  blocked indefinitely, preventing _init_beat and the heartbeat thread from running.
  Fix: removed -S flag from docker-compose.yml beat command (scheduler is in
  celery_app.conf); moved thread.start() to first line of _init_beat; deleted
  stale Redis lock. All 8 services now healthy after restart.
  Root cause 2 — worker healthcheck timeout on startup:
  start_period: 30s insufficient for celery inspect ping during worker init.
  Fix: raised to 60s.

### 2. Backend test suite (41/41)
expected: |
  cd backend && uv run pytest tests/ -x --tb=short
  All 41 tests pass in ~15s: 32 unit + 9 integration (testcontainers Postgres).
  No failures, no errors.
result: pass

### 3. Frontend Vitest tests (2/2)
expected: |
  cd frontend && pnpm test
  Both tests pass: healthz route (200 + {status:'ok'}) and sentry-test route (throws expected Error).
  Output: 2/2 passed.
result: pass

### 4. gitleaks detects synthetic secret
expected: |
  cd backend && uv run pytest tests/test_gitleaks_blocks_secret.py -v
  Both tests pass:
  - test_gitleaks_fires_on_synthetic_fixture: gitleaks finds 2 leaks against .env.fake
  - test_gitleaks_clean_scan: full-repo scan returns 0 findings
result: pass

### 5. Money-column lint gate
expected: |
  cd backend && uv run python scripts/lint_money_columns.py
  Output: "OK: 2 files checked, 0 warnings"
  Exit code 0. No Float/REAL/MONEY annotations found.
result: pass

### 6. Backend health endpoint
expected: |
  With the stack running (Test 1 complete):
  curl.exe http://localhost:8000/healthz
  Response: {"status":"ok"} with HTTP 200.
result: pass

### 7. Frontend health endpoint
expected: |
  With the stack running (Test 1 complete):
  curl.exe http://localhost:3000/api/healthz
  Response: {"status":"ok"} with HTTP 200.
result: pass

### 8. Sentry test endpoints return 500
expected: |
  With the stack running (Test 1 complete):
  curl.exe -sI http://localhost:8000/_sentry-test   → HTTP/1.1 500
  curl.exe -sI http://localhost:3000/api/sentry-test → HTTP/1.1 500
  Both endpoints deliberately throw errors. No 404 or 200.
result: issue
reported: "/_sentry-test returns HTTP/1.1 405 Method Not Allowed (HEAD); /api/sentry-test returns 500 OK"
severity: minor
note: |
  405 is a test-command issue, not a code bug. -sI sends HEAD; FastAPI/Starlette
  does not propagate exceptions to HEAD responses on GET-only routes.
  GET returns 500 as expected (verified: curl.exe -s -o NUL -w "%{http_code}"
  http://localhost:8000/_sentry-test → 500). Sentry wiring is correct.

### 9. Alembic migration tables + feature flag seeds
expected: |
  With the stack running (Test 1 complete):
  docker compose exec db psql -U xpredict -d xpredict -c "\dt"
  Tables: audit_log, feature_flags (at minimum)

  docker compose exec db psql -U xpredict -d xpredict -c "SELECT key, enabled FROM feature_flags ORDER BY key;"
  Exactly 3 rows:
    admin_2fa_required      | f
    polymarket_sync_enabled | f
    stripe_recharge_enabled | f
result: pass

## Summary

total: 9
passed: 7
issues: 2
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "docker compose up -d --wait brings all 8 services healthy in one command"
  status: failed
  reason: "User reported: container xpredict-worker-1 is unhealthy (beat also stuck in health:starting)"
  severity: major
  test: 1
  root_cause: |
    Two bugs: (1) beat heartbeat thread never starts on crash-restart because
    -S redbeat.RedBeatScheduler CLI flag causes RedBeat's beat_init receiver
    (acquire_distributed_beat_lock) to register before _init_beat, blocking it
    indefinitely while awaiting stale Redis lock. (2) Worker start_period: 30s
    insufficient for celery inspect ping during cold start.
  artifacts:
    - path: "docker-compose.yml"
      issue: "-S redbeat.RedBeatScheduler on beat command; worker start_period: 30s"
    - path: "backend/app/celery_app.py"
      issue: "thread.start() after configure_logging/init_sentry in _init_beat"
  missing:
    - "Remove -S flag, move thread.start() first, raise worker start_period to 60s"
  fix_status: APPLIED (verified all 8 services healthy after fix)

- truth: "/_sentry-test returns HTTP 500 to curl -sI (HEAD)"
  status: failed
  reason: "User reported: HTTP/1.1 405 Method Not Allowed on HEAD"
  severity: minor
  test: 8
  root_cause: |
    Test command issue, not a code bug. -sI sends HEAD; FastAPI/Starlette
    does not auto-propagate exceptions to HEAD responses. GET → 500 confirmed.
    The Sentry endpoint is wired correctly.
  artifacts:
    - path: "backend/app/routers/health.py"
      issue: "/_sentry-test route does not explicitly handle HEAD"
  missing:
    - "Optional: add HEAD method support to /_sentry-test, or update test docs to use GET"
  fix_status: NO ACTION REQUIRED (functionality correct, test command was wrong)
