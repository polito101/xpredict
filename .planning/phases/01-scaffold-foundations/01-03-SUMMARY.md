---
phase: 01-scaffold-foundations
plan: 03
subsystem: infra
tags: [docker-compose, alembic, postgres-16, redis-7, audit-immutability, feature-flags, tenant-id-ghost, testcontainers, pytest-asyncio]

# Dependency graph
requires:
  - phase: 01-scaffold-foundations
    plan: 01
    provides: "backend/Dockerfile, app.main /healthz, app.celery_app.sentry_test_task + beat heartbeat thread, AuditLog model, FeatureFlag model, AuditService.record, FeatureFlagService.is_enabled, conftest.py testcontainers Postgres engine fixture skeleton"
  - phase: 01-scaffold-foundations
    plan: 02
    provides: "frontend/Dockerfile (Node 20 + pnpm), /api/healthz Route Handler, /api/sentry-test Route Handler"
provides:
  - "docker-compose.yml — 8-service local stack (db, redis, mailpit, backend, worker, beat, flower, frontend) with healthchecks per D-03, depends_on service_healthy per D-04, named volumes per D-05"
  - "Alembic 0001_phase1_foundations baseline migration — creates audit_log + feature_flags with tenant_id ghost column, audit immutability trigger + REVOKE, 3 seeded feature flags"
  - "backend/alembic.ini + backend/alembic/env.py (sync engine via psycopg2 per D-16, Pattern 2)"
  - "Integration tests against testcontainers Postgres — 4 audit + 5 feature-flag tests prove PLT-01 / PLT-02 / PLT-06 schema acceptance"
  - "Extended conftest.py engine fixture — runs alembic upgrade head against the testcontainer before yielding the async engine; loop_scope=session for cross-fixture loop sharing"
  - ".env.example committed + .env.local gitignored; .gitattributes enforces LF for source/text files (Pitfall 8 Windows CRLF mitigation)"
affects: [01-04-ci-and-acceptance, 02-auth-identity, 03-wallet-ledger]

# Tech tracking
tech-stack:
  added:
    - "Alembic 1.x (baseline 0001 migration shipped)"
    - "(No new top-level deps — all infra deps were installed in 01-01)"
  patterns:
    - "TENANT_DEFAULT constant defined once at migration-module top, reused on both tables (Pitfall 10 mitigation — single source of truth for the v1 default UUID)"
    - "BEFORE UPDATE OR DELETE trigger on audit_log calling raise_audit_immutable() + REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC (D-20, two layers of defense)"
    - "Sync Alembic engine (psycopg2) over DATABASE_URL_SYNC alongside the app's async engine (asyncpg) over DATABASE_URL (D-16, Pattern 2)"
    - "Testcontainers Postgres engine fixture runs alembic upgrade head before yielding the async engine (env vars rewritten + lazy engine cache cleared)"
    - "pytest_asyncio.fixture(loop_scope='session') for session-scoped async fixtures — cross-loop asyncpg connections error with 'Event loop is closed' under pytest-asyncio 0.25 default function-loop scope"
    - "docker-compose YAML anchors (x-backend-env, x-backend-volumes) keep backend/worker/beat/flower DRY"
    - "Beat healthcheck via /tmp/celerybeat.heartbeat mtime + shared beat_heartbeat named volume (Pattern 1, Pitfall 1)"
    - ".env.example committed with placeholders; .env.local gitignored with dev defaults (D-32, PLT-03)"

key-files:
  created:
    - "docker-compose.yml — 8-service local stack (root)"
    - ".gitattributes — LF enforcement (root, Pitfall 8)"
    - "backend/alembic.ini — Alembic config, sqlalchemy.url empty (env.py reads Settings)"
    - "backend/alembic/env.py — sync engine via psycopg2, imports AuditLog + FeatureFlag for autogenerate"
    - "backend/alembic/script.py.mako — standard Alembic template"
    - "backend/alembic/versions/0001_phase1_foundations.py — baseline migration (audit_log + feature_flags + trigger + REVOKE + 3 seed flags)"
    - "backend/tests/core/__init__.py — pytest package marker"
    - "backend/tests/core/test_audit_immutability.py — 4 integration tests (tenant_id default, AuditService atomicity, UPDATE blocked, DELETE blocked)"
    - "backend/tests/core/test_feature_flags.py — 5 integration tests (seed flags, is_enabled, toggle, unknown key, tenant fallback)"
  modified:
    - ".env.example — Phase 1 env vars (DATABASE_URL, DATABASE_URL_SYNC, REDIS_URL, SENTRY_DSN, NEXT_PUBLIC_*) added"
    - ".env.local — Phase 1 dev-safe values added (still gitignored)"
    - ".gitignore — Python (.pytest_cache, .ruff_cache, .mypy_cache, .uv-cache, htmlcov), Node (.next, node_modules, .pnpm-store), editor patterns"
    - "backend/tests/conftest.py — engine fixture now runs alembic upgrade head against testcontainer; loop_scope=session on async fixtures"
    - "frontend/Dockerfile — pinned pnpm to 9.15.0 (pnpm@latest = pnpm 11+ requires Node ≥22.13; node:20-alpine is locked)"

key-decisions:
  - "Used TENANT_DEFAULT module-top constant in 0001_phase1_foundations.py reused on both audit_log and feature_flags (Pitfall 10 — divergent defaults across tables is the canonical multi-tenant trap)."
  - "feature_flags.tenant_id is NOT NULL with server_default (in Postgres a PK column cannot be NULL even if the model declares Mapped[UUID | None]). The python-side Optional reflects that callers may omit it; SQLAlchemy fills the default."
  - "Used pytest_asyncio.fixture(loop_scope='session') for engine + async_session (rather than function-scoped or rebuilding container per test). The 'Event loop is closed' RuntimeError on cross-loop asyncpg connections (pytest-asyncio 0.25 with default function-loop scope under session-scoped async fixtures) is the canonical pitfall."
  - "Defensive lazy-engine cache clear inside the engine fixture (`_get_engine.cache_clear()` + `_get_session_maker.cache_clear()`). The Wave-0 tests don't request the engine fixture so the cache is never warmed in practice, but the clear ensures correctness if a future Phase 2+ test stack does instantiate app.db.session before the engine fixture."
  - "Frontend Dockerfile pnpm pin (Rule 3 deviation): pnpm@latest = pnpm 11 which requires Node 22.13+; node:20-alpine was the existing pin. Pinned to pnpm 9.15.0 (matches the local host pnpm + the lockfile generator) — minimal change to make `docker compose build frontend` succeed without altering frontend source or pnpm-lock.yaml."
  - "Augmented existing .env.example (Linear-only stub from initial bootstrap) — preserved Linear keys + added Phase 1 backend/frontend env vars. Avoids deleting collaboration-infra placeholders that pre-date Phase 1."

patterns-established:
  - "Alembic env.py reads DATABASE_URL_SYNC from Settings — never hardcodes a URL. Phase 2+ migrations inherit this path."
  - "Integration tests live under tests/core/ with `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope='session')]` — Phase 2-10 tests that touch the DB through testcontainers Postgres inherit this shape."
  - "Audit immutability via Postgres trigger + REVOKE (defense in depth). Phase 5+ uses AuditService.record() inside the caller's session so the audit row commits atomically with the underlying action."
  - "tenant_id ghost column on every table — PLT-01 pattern locked in 0001; Phase 2+ tables inherit (enforced by code review per D-42)."

requirements-completed: [PLT-01, PLT-02, PLT-06, PLT-10]

# Metrics
duration: 13min
completed: 2026-05-26
---

# Phase 01 Plan 01-03: docker-compose stack + Alembic baseline + integration tests Summary

**8-service docker-compose stack (db, redis, mailpit, backend, worker, beat, flower, frontend) with per-service healthchecks + named volumes; Alembic baseline migration `0001_phase1_foundations` ships `audit_log` (with BEFORE UPDATE OR DELETE trigger raising the exact D-44 message + `REVOKE UPDATE, DELETE FROM PUBLIC`) and `feature_flags` (composite PK on `(key, tenant_id)` with 3 seeded rows) — both carrying the `tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'` ghost column; 9 integration tests against testcontainers Postgres prove PLT-01 + PLT-02 + PLT-06; .gitattributes enforces LF for Windows-CRLF mitigation; .env.example committed and .env.local gitignored.**

## Performance

- **Duration:** ~13 minutes
- **Started:** 2026-05-26T06:41:57Z
- **Completed:** 2026-05-26T06:55:35Z
- **Tasks:** 3 (executed atomically as separate commits; Task 3 partial — runtime acceptance gated by host port conflict, manual-verify documented below)
- **Files modified:** 9 created, 5 modified

## Accomplishments

- **`docker compose config --quiet` exits 0** with exactly 8 services (`backend, beat, db, flower, frontend, mailpit, redis, worker`). 8 healthcheck blocks, 4 named volumes (`pg_data, redis_data, mailpit_data, beat_heartbeat`), `postgres:16-alpine` confirmed (not 17), `redbeat.RedBeatScheduler` confirmed in the beat command (not `PersistentScheduler`).
- **`alembic heads` returns `0001_phase1_foundations (head)`** — env.py loads, target_metadata sees both models, the migration is registered.
- **9/9 integration tests pass in 4.74s** against a real Postgres 16 via testcontainers:
  - PLT-01: `test_tenant_id_default` proves the ghost column defaults to `UUID('00000000-0000-0000-0000-000000000001')` (matches `Settings.TENANT_ID_DEFAULT`)
  - PLT-02: `test_audit_service_record` (caller-owned transaction atomicity), `test_audit_log_update_blocked` (raises with "append-only"), `test_audit_log_delete_blocked` (raises with "append-only")
  - PLT-06: `test_seed_flags` (3 rows, all FALSE), `test_is_enabled_returns_seeded_value`, `test_is_enabled_toggle` (UPDATE flips it), `test_is_enabled_unknown_key_defaults_false` (default-deny), `test_tenant_fallback` (unknown tenant uses default-tenant row)
- **Full test suite (Wave-0 + new integration) = 39/39 passing in ~7s.** ruff + mypy clean.
- **frontend image builds successfully** after pinning pnpm to 9.15.0 (Rule 3 deviation — pre-existing Dockerfile issue surfaced during compose build).
- **backend image builds successfully** (`docker compose build backend` exits 0).
- **`.env.local` is matched by a `.gitignore` rule** (`git check-ignore .env.local` exits 0); `.env.example` is committed.
- **`.gitattributes` enforces LF** for Dockerfile, docker-compose.yml, `*.py`, `*.ts`, `*.tsx`, `*.sh`, `*.toml`, `*.yml`, etc. (Pitfall 8).

## Task Commits

Each task committed atomically:

1. **Task 1: docker-compose.yml + .env.example + .gitignore + .gitattributes** — `bc5690f` (feat)
2. **Task 2: Alembic 0001 baseline + audit immutability + feature-flag integration tests + conftest.py extension** — `30d7e21` (feat)
3. **Task 3 (prerequisite fix): frontend Dockerfile pnpm pin for Node-20 compatibility** — `dd76dac` (fix). Runtime acceptance itself documented as manual-verify below.

**Plan metadata commit:** _added below after this summary is staged_

## Files Created/Modified

**Created (9):**

- `docker-compose.yml` (root) — 8 services + healthchecks + depends_on + 4 named volumes
- `.gitattributes` (root) — LF enforcement (Pitfall 8)
- `backend/alembic.ini` — Alembic config with empty `sqlalchemy.url` (env.py reads Settings)
- `backend/alembic/env.py` — sync engine via psycopg2 / DATABASE_URL_SYNC (Pattern 2)
- `backend/alembic/script.py.mako` — standard Alembic template
- `backend/alembic/versions/0001_phase1_foundations.py` — baseline migration
- `backend/tests/core/__init__.py` — pytest package marker
- `backend/tests/core/test_audit_immutability.py` — 4 PLT-01 + PLT-02 tests
- `backend/tests/core/test_feature_flags.py` — 5 PLT-06 tests

**Modified (5):**

- `.env.example` — Phase 1 env vars appended; Linear placeholder preserved
- `.env.local` — Phase 1 dev-safe values appended; Linear values preserved
- `.gitignore` — added .pytest_cache, .ruff_cache, .mypy_cache, .uv-cache, .next-related, editor patterns
- `backend/tests/conftest.py` — engine fixture now runs `alembic upgrade head`; `loop_scope=session` on async fixtures
- `frontend/Dockerfile` — pinned pnpm to 9.15.0 for Node-20 compat (Rule 3 deviation; surgical 1-line fix)

## Decisions Made

1. **`TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"` defined once in `0001_phase1_foundations.py` and reused on both `audit_log` and `feature_flags`** — Pitfall 10 mitigation. The canonical multi-tenant trap is divergent default UUIDs across tables; a module-top constant + grep verification (returns exactly one definition) blocks it.
2. **`feature_flags.tenant_id` set NOT NULL in the migration** despite the model declaring `Mapped[PyUUID | None]`. Postgres requires PK columns to be NOT NULL; the Optional in the model is python-side syntactic sugar (SQLAlchemy fills `default=lambda: Settings().TENANT_ID_DEFAULT` on insert). The `server_default` at the SQL layer means an explicit `INSERT INTO feature_flags (key, enabled)` works.
3. **`pytest_asyncio.fixture(loop_scope="session")` for `engine` + `async_session`** — pytest-asyncio 0.25 defaults async fixtures to function-loop, but the session-scoped engine fixture creates asyncpg connections under a different loop than the test function uses → "Event loop is closed" RuntimeError on first test that touches the engine. The fix is `loop_scope="session"` on both the fixture decorator and the `pytestmark` (each test file gets `pytest.mark.asyncio(loop_scope="session")`).
4. **Frontend Dockerfile pnpm pin to 9.15.0** (Rule 3 deviation) — Plan 01-02 committed `pnpm-lock.yaml` against pnpm 9.15.0 on Pol's host, but the Dockerfile said `corepack prepare pnpm@latest --activate` which resolves to pnpm 11+ requiring Node ≥22.13. node:20-alpine is the locked image. The 1-line fix pins to 9.15.0 (matches host + lockfile). No frontend source code touched.
5. **Augmented `.env.example` rather than replaced** — the existing file was the Linear-only stub from initial repo bootstrap; appended Phase 1 backend/frontend vars (DATABASE_URL, DATABASE_URL_SYNC, REDIS_URL, SENTRY_DSN, NEXT_PUBLIC_SENTRY_DSN, NEXT_PUBLIC_API_URL, ENVIRONMENT, LOG_LEVEL) above the Linear placeholder. Avoids deleting collaboration infra that pre-dates Phase 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] pytest-asyncio cross-loop "Event loop is closed" on session-scoped engine fixture**
- **Found during:** Task 2 (first integration-test run — 1 test passed, second errored on asyncpg connection teardown)
- **Issue:** With `@pytest.fixture(scope="session") async def engine(...)` and default function-loop scope on test functions, the engine's asyncpg pool was created under one event loop and the second test's connection close happened under a different loop, raising `RuntimeError: Event loop is closed`.
- **Fix:**
  1. Changed `@pytest.fixture(scope="session")` to `@pytest_asyncio.fixture(scope="session", loop_scope="session")` on the `engine` fixture (and matching `loop_scope="session"` on `async_session` and `client`).
  2. Added `pytest.mark.asyncio(loop_scope="session")` to the `pytestmark` of each `tests/core/` test file.
- **Files modified:** `backend/tests/conftest.py`, `backend/tests/core/test_audit_immutability.py`, `backend/tests/core/test_feature_flags.py`
- **Verification:** 9/9 integration tests pass in 4.74s; full suite 39/39 in ~7s
- **Committed in:** `30d7e21` (Task 2 commit)

**2. [Rule 3 — Blocking] frontend Dockerfile pnpm pin to 9.15.0**
- **Found during:** Task 3 (first `docker compose build frontend`)
- **Issue:** `RUN corepack enable && corepack prepare pnpm@latest --activate` resolved to pnpm 11.3.0 which requires Node ≥22.13. The Dockerfile uses `node:20-alpine` (locked by STACK.md §4.1 + the host pnpm-lock.yaml committed by Plan 01-02). Build failed with `ERR_UNKNOWN_BUILTIN_MODULE` from pnpm 11 trying to use Node 22+ stdlib features.
- **Fix:** Pinned `corepack prepare pnpm@9.15.0 --activate` (matches the host's pnpm version + the lockfile generator).
- **Files modified:** `frontend/Dockerfile` (1-line change)
- **Verification:** `docker compose build frontend` exits 0; `docker compose build backend` exits 0
- **Committed in:** `dd76dac` (separate commit per the spirit of "Zero modifications to frontend/" — explicit, minimal, audit-friendly)

**3. [Rule 3 — Blocking] ruff import-sort nits in conftest.py and alembic/env.py**
- **Found during:** Task 2 (post-test `ruff check`)
- **Issue:** `ruff` flagged 2 `I001` (import organization) issues — `alembic` and `app.db.session` deferred imports + `pytest_asyncio` insertion order.
- **Fix:** `uv run ruff check --fix` (auto-organized). No behavioral change.
- **Files modified:** `backend/tests/conftest.py`, `backend/alembic/env.py`
- **Committed in:** `30d7e21` (Task 2 commit, before the final `git commit`)

---

**Total deviations:** 3 auto-fixed (all Rule 3 — blocking environmental/lint issues). Zero behavioural deviations. No Rule 4 architectural decisions needed.

**Impact on plan:** All deviations are infrastructure-level — none change the schema, the trigger error string, the seed values, the tenant_id default, or any of the interface contracts Phase 2+ depends on.

## Issues Encountered

- **Host port conflicts during Task 3 runtime acceptance** (see "Task 3 manual-verify" below). Pol's `crypto-casino` project has `cc_redis` and `cc_postgres` containers running and bound to host ports 6379 and 5432, which blocks `docker compose up -d --wait` from binding the xpredict `redis` and `db` services to the same host ports.
- **First `docker compose build frontend` failed on pnpm/Node version mismatch** (Rule 3 deviation #2 above). Surfaced a pre-existing frontend Dockerfile issue from Plan 01-02; fixed surgically.
- **First integration-test run failed on "Event loop is closed" RuntimeError** (Rule 3 deviation #1 above). Resolved via `loop_scope="session"`.

## Task 3 — Runtime Acceptance (Manual-Verify)

`docker compose up -d --wait` was attempted but blocked by host port conflicts (Pol's `crypto-casino` `cc_redis` and `cc_postgres` containers occupy host ports 6379 and 5432 — `cc_redis` UP 18h, `cc_postgres` UP 22h). Stopping them automatically risked disrupting Pol's other active work, so the runtime gate is deferred to a manual session.

**What WAS verified automatically:**

- `docker compose config --quiet` exits 0 (compose file syntactically valid)
- `docker compose config --services` returns 8 services
- `docker compose build backend` exits 0
- `docker compose build frontend` exits 0 (after pnpm pin)
- `docker compose up -d mailpit` brought mailpit up healthy in ~4s (smoke test that healthcheck blocks parse + run correctly)
- `alembic heads` returns `0001_phase1_foundations (head)` from the host (env.py + migration register cleanly)
- 9/9 integration tests against testcontainers Postgres pass — proves the migration applies cleanly and the trigger + REVOKE + seed flags all work against a real PG 16

**Manual verification steps for Pol (~5 minutes):**

```powershell
# 1. Free host ports 5432 and 6379 (stop crypto-casino's containers).
#    Capture their IDs first so you can restart them after.
docker ps --filter "name=cc_redis" --filter "name=cc_postgres" --format "{{.Names}}"
docker stop cc_redis cc_postgres

# 2. Bring up the xpredict stack.
cd C:\Users\pobom\xpredict
docker compose up -d --wait

# Expected: exits 0 after ~30-90 seconds with all 8 services healthy.
docker compose ps --format "table {{.Service}}\t{{.Status}}"
# Expected output:
#   SERVICE    STATUS
#   backend    Up X minutes (healthy)
#   beat       Up X minutes (healthy)
#   db         Up X minutes (healthy)
#   flower     Up X minutes (healthy)
#   frontend   Up X minutes (healthy)
#   mailpit    Up X minutes (healthy)
#   redis      Up X minutes (healthy)
#   worker     Up X minutes (healthy)

# 3. Verify alembic upgrade head + table creation.
docker compose exec backend uv run alembic upgrade head
docker compose exec db psql -U xpredict -d xpredict -c "\dt"
# Expected: audit_log and feature_flags listed

docker compose exec db psql -U xpredict -d xpredict -c "SELECT key, enabled FROM feature_flags ORDER BY key;"
# Expected:
#            key            | enabled
#   ------------------------+---------
#   admin_2fa_required      | f
#   polymarket_sync_enabled | f
#   stripe_recharge_enabled | f
#   (3 rows)

# 4. Sentry triple-trigger HTTP smoke (independent of SENTRY_DSN — these
#    return HTTP status codes regardless of whether the DSN is configured).
curl.exe -fsS -o NUL -w "%{http_code}\n" http://localhost:8000/healthz       # expect 200
curl.exe -fsS -o NUL -w "%{http_code}\n" http://localhost:3000/api/healthz   # expect 200
curl.exe -fsSI http://localhost:8000/_sentry-test 2>&1 | findstr HTTP        # expect HTTP/1.1 500
curl.exe -fsSI http://localhost:3000/api/sentry-test 2>&1 | findstr HTTP     # expect HTTP/1.1 500
docker compose exec backend celery -A app.celery_app call app.core.sentry.sentry_test_task
docker compose logs worker --tail 20 | findstr "sentry test from worker"     # expect log line

# 5. If SENTRY_DSN is configured (set in .env.local and re-run `docker compose
#    up -d --wait` to propagate), confirm 3 distinct Sentry events with
#    service tags (api, worker, frontend) land in the Sentry project.

# 6. Tear down + restart crypto-casino containers.
docker compose down
docker start cc_redis cc_postgres
```

**Recovery path** if any healthcheck fails:
- `docker compose logs <service>` to read the failure
- `docker compose ps` to see which service is `unhealthy`
- For the beat heartbeat specifically: `docker compose exec beat ls -la /tmp/celerybeat.heartbeat` — if missing, the heartbeat thread didn't start (check `docker compose logs beat` for the `_init_beat` signal log)

## User Setup Required

**Pol must complete the Task 3 runtime acceptance manually** (5-min checklist above). Until then:
- `docker compose up -d --wait` is **not yet end-to-end verified** on this host.
- The compose file itself + the Alembic migration + the integration tests ARE fully verified (see "What WAS verified automatically" above).

End-to-end Sentry round-trip verification (PLT-08 manual gate) needs a real `SENTRY_DSN` and `NEXT_PUBLIC_SENTRY_DSN` in `.env.local`. The HTTP-level triple-trigger (steps 4 above) verifies the wiring; the Sentry event landing is the manual-verify gate that 01-04 (or the phase verifier) will close.

## Next Phase Readiness

**Plan 01-04 (CI + gitleaks + bin/dev + README + acceptance gate)** prerequisites all in place:

- `docker-compose.yml` ready for `bin/dev` to wrap (`docker compose up -d && cd backend && uv run alembic upgrade head`).
- `.env.example` enumerates every Phase 1 env var — `bin/dev` can fail-fast if `.env.local` doesn't exist or is missing required keys.
- `.gitattributes` already ships with LF enforcement; 01-04's CI workflows can assume Unix line endings on all source.
- `backend/tests/core/` integration tests are the green baseline `backend-ci.yml` runs.
- `backend/alembic/versions/0001_phase1_foundations.py` is the migration `prod-migration-dry-run` (Phase 11) will replay against staging.

**Phase 2+ contracts honored:**

- `AuditService.record(session, *, actor, event_type, payload, ip, tenant_id)` is now backed by a real, immutable `audit_log` table — Phases 3-10's audit calls land in the same trigger-protected destination.
- `FeatureFlagService.is_enabled(session, key, tenant_id)` works against seeded rows; Phase 3 (`stripe_recharge_enabled`), Phase 6 (`polymarket_sync_enabled`), and v2 (`admin_2fa_required`) gates are already populated.
- `tenant_id` ghost column pattern is locked at the schema layer (D-19, D-37) and demonstrated to be the v1 default; Phase 2+ tables inherit the pattern documented in `backend/CONVENTIONS.md`.

**Known stubs / deferred items:**

- **Task 3 runtime acceptance** (manual-verify checklist above) — gated by host port conflicts with Pol's `crypto-casino` containers.
- **End-to-end Sentry round-trip** with a real DSN — Phase 1 acceptance gate, deferred to 01-04 or phase verifier.
- **`.env.local` is augmented but the Linear key remains in the committed value** — kept as-is (existing convention; the file is gitignored, only re-committed when the user updates the example, which I avoided).

## Self-Check: PASSED

Verified 9/9 created files exist on disk:
- `docker-compose.yml`, `.gitattributes` (root)
- `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_phase1_foundations.py`
- `backend/tests/core/__init__.py`, `backend/tests/core/test_audit_immutability.py`, `backend/tests/core/test_feature_flags.py`

Verified 3/3 task commits exist in `git log --oneline`:
- `bc5690f` — `feat(01-03): docker-compose 8-service stack + Phase 1 env templates`
- `30d7e21` — `feat(01-03): Alembic 0001 baseline + audit immutability + feature flag integration tests`
- `dd76dac` — `fix(01-03): pin pnpm 9.15.0 in frontend Dockerfile for Node-20 compatibility`

Final re-runs after summary draft:
- `cd backend && uv run pytest tests/` → 39/39 passing in ~7s
- `cd backend && uv run ruff check app/ scripts/ tests/ alembic/` → All checks passed
- `cd backend && uv run mypy app/` → Success: no issues found in 27 source files
- `cd backend && uv run alembic heads` → `0001_phase1_foundations (head)`
- `cd .. && docker compose config --quiet && docker compose config --services | wc -l` → exits 0, returns 8

Trigger error message D-44 verbatim in migration file:
- `grep -F "audit_log is append-only -- UPDATE and DELETE are forbidden" backend/alembic/versions/0001_phase1_foundations.py` → 1 match

`TENANT_DEFAULT` defined exactly once in the migration:
- `grep -c '^TENANT_DEFAULT = ' backend/alembic/versions/0001_phase1_foundations.py` → 1

---
*Phase: 01-scaffold-foundations*
*Plan: 03*
*Completed: 2026-05-26*
