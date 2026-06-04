---
phase: 01-scaffold-foundations
plan: 01
subsystem: infra
tags: [fastapi, sqlalchemy-async, celery, redis, postgres, structlog, sentry, uv, pydantic-settings, pytest, testcontainers, money-lint, audit-log, feature-flags]

# Dependency graph
requires: []
provides:
  - "Backend Python package (backend/app/) with FastAPI app factory, Celery factory + redbeat, async SQLAlchemy 2.0 session dependency"
  - "Settings(BaseSettings) with extra='ignore' — single source of truth for env-driven config"
  - "Money SQLAlchemy alias enforcing Numeric(18,4) (WAL-05)"
  - "structlog configure_logging() with scrub_secrets processor (D-25 keys preempted)"
  - "init_sentry(service, settings, integrations) helper — tags every event with service=api|worker|beat"
  - "AuditService.record(session, *, actor, event_type, payload, ip, tenant_id) — Phase 2-locked signature"
  - "FeatureFlagService.is_enabled(session, key, tenant_id) with tenant-fallback"
  - "RequestIdMiddleware (pure ASGI, not BaseHTTPMiddleware) binding request_id/path/method/client_ip"
  - "scripts/lint_money_columns.py — AST gate for D-17 / WAL-05"
  - "tests/conftest.py — testcontainers Postgres + fakeredis fixtures (Plan 01-03 reuses)"
  - "30 passing Wave-0 unit tests covering PLT-03, PLT-08, PLT-10, WAL-05"
affects: [01-02-frontend-nextjs, 01-03-alembic-baseline-and-integration-tests, 01-04-compose-and-ops, 02-auth-identity, 03-wallet-ledger]

# Tech tracking
tech-stack:
  added:
    - "uv 0.11.16 (Python dep manager + lockfile)"
    - "fastapi[standard] 0.116.x (Phase 1 dep-pin 0.115.7+)"
    - "uvicorn[standard] 0.35.x"
    - "pydantic 2.13.x + pydantic-settings 2.x"
    - "sqlalchemy 2.0.50 + asyncpg 0.31.x + psycopg2-binary 2.9.10 + alembic 1.x"
    - "celery 5.5.x + redis-py 5.x + celery-redbeat 2.2.x + flower 2.x"
    - "structlog 25.x + sentry-sdk[fastapi,celery,sqlalchemy] 2.18.x"
    - "httpx 0.28.x + tenacity 9.x"
    - "slowapi 0.1.x (installed, NOT mounted — Phase 2 mounts on auth endpoints)"
    - "pytest 8.x + pytest-asyncio 0.25.x + pytest-httpx 0.35.x + testcontainers 4.x + fakeredis 2.x + dirty-equals 0.8.x"
    - "ruff 0.x + mypy 1.x + pre-commit 4.x"
  patterns:
    - "Settings(BaseSettings) singleton — all env reads typed; never os.getenv elsewhere"
    - "Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)] — enforced by AST lint"
    - "Pure-ASGI RequestIdMiddleware (NOT BaseHTTPMiddleware — Pattern 6 anti-pattern documented)"
    - "Celery Sentry init in worker_process_init / beat_init signals only (Pitfall 5)"
    - "task_prerun + task_postrun clear structlog contextvars (Pitfall 7)"
    - "Beat heartbeat thread touching /tmp/celerybeat.heartbeat every 30s (Pattern 1 / Pitfall 1)"
    - "AuditService.record() — single API for inserting audit_log rows; caller owns the AsyncSession"
    - "Tenant-fallback feature-flag lookup with composite PK (key, tenant_id)"
    - "Lazy uv engine factory — async engine instantiated on first use, not at module import (test-friendly)"

key-files:
  created:
    - "backend/pyproject.toml — uv project + pinned deps + ruff + mypy + pytest config"
    - "backend/uv.lock — reproducible deps"
    - "backend/Dockerfile — Python 3.12-slim base, uv sync, EXPOSE 8000"
    - "backend/CONVENTIONS.md — money/tenant_id/audit/SET LOCAL doctrine locked"
    - "backend/app/core/config.py — Settings(BaseSettings) per D-09"
    - "backend/app/core/logging.py — configure_logging + scrub_secrets + SCRUB_KEYS"
    - "backend/app/core/sentry.py — init_sentry(service, settings, integrations)"
    - "backend/app/core/redis.py — get_redis() FastAPI dep"
    - "backend/app/db/base.py — DeclarativeBase"
    - "backend/app/db/session.py — get_async_session() + lazy engine factory"
    - "backend/app/db/types.py — Money Annotated alias"
    - "backend/app/main.py — FastAPI app + RequestIdMiddleware + lifespan"
    - "backend/app/celery_app.py — Celery factory + redbeat + heartbeat + Sentry signals + task contextvars"
    - "backend/app/routers/health.py — /healthz + /readyz"
    - "backend/app/core/audit/{models.py,service.py} — AuditLog + AuditService"
    - "backend/app/core/feature_flags/{models.py,service.py} — FeatureFlag + FeatureFlagService"
    - "backend/scripts/lint_money_columns.py — AST linter, 200 LOC"
    - "backend/tests/conftest.py — env seed + 5 fixtures (lightweight + Postgres)"
    - "backend/tests/test_settings.py, test_money_lint.py, test_sentry_init.py, test_sentry_test_endpoint.py, test_sentry_test_task.py, test_health.py — 30 tests total"
    - "backend/app/{auth,wallet,markets,bets,admin,integrations}/__init__.py — Phase ownership stubs"
  modified: []

key-decisions:
  - "Broadened requires-python from STACK.md's >=3.12,<3.13 to >=3.12,<3.14 — Pol's host machine has Python 3.13.7 only; uv auto-fetches 3.12 if pyproject demands it. 3.13 is FFI-compatible with every locked dep."
  - "Added _annotation_kind classifier to money-lint — suppresses R2 false-positive on legitimate JSONB/Text/Boolean columns whose names match MONEY_NAMES (D-17 lists `value` which collides with feature_flags.value JSONB)."
  - "ASGITransport(raise_app_exceptions=False) in test client — required so /_sentry-test exercises FastAPI's ServerErrorMiddleware → 500 path (matches production behavior)."
  - "Module-level env seeding in conftest.py (not session-fixture) — app.celery_app instantiates Settings() at import, which happens during test collection before any fixture runs."
  - "Lazy engine factory in app/db/session.py (`@lru_cache _get_engine`) — avoids constructing the asyncpg pool at module import; makes Settings()-required tests trivial."

patterns-established:
  - "Pure ASGI middleware for contextvar binding (FastAPI discussion #8632 — BaseHTTPMiddleware would copy context out)"
  - "Sentry init INSIDE Celery worker_process_init/beat_init signals — never module-level (Pitfall 5)"
  - "structlog contextvars cleared on Celery task_prerun + task_postrun (Pitfall 7)"
  - "Beat heartbeat daemon thread for docker-compose healthcheck via mtime (Pattern 1)"
  - "AuditService.record(session, *, ...) — caller-owned transaction, atomic with underlying action"
  - "FeatureFlagService tenant-fallback ordering (prefer tenant-specific row over default-tenant row)"
  - "Money column AST lint with annotation-kind classifier (R2 only fires when column's type annotation is numeric or unclear — not when clearly non-money like JSONB)"

requirements-completed: [PLT-03, PLT-08, WAL-05]

# Metrics
duration: 26min
completed: 2026-05-26
---

# Phase 01 Plan 01-01: Backend Python Scaffold + Cross-Cutting Foundations Summary

**FastAPI app factory + Celery factory + Settings(BaseSettings) + Money/Numeric(18,4) AST lint + structlog/Sentry config + AuditService/FeatureFlagService + 30-test Wave-0 suite — the contract surface every Phase 2-10 plan plugs into.**

## Performance

- **Duration:** ~26 minutes
- **Started:** 2026-05-26T05:50:00Z
- **Completed:** 2026-05-26T06:16:07Z
- **Tasks:** 3 (executed atomically as separate commits)
- **Files modified:** 38 created (backend/ from scratch), 0 modified

## Accomplishments

- Backend Python package builds and imports cleanly via `uv sync`; ruff + mypy strict + money-lint all green
- **Settings, Money, get_async_session, get_redis, init_sentry, AuditService.record, FeatureFlagService.is_enabled** all exported with the exact signatures Phase 2 CONTEXT.md depends on
- FastAPI app factory mounts pure-ASGI RequestIdMiddleware (NOT BaseHTTPMiddleware) + lifespan-driven Sentry/structlog init + /healthz + /readyz + /_sentry-test
- Celery factory wires redbeat scheduler, `app.core.sentry.sentry_test_task`, beat heartbeat daemon thread, Sentry init via `worker_process_init`+`beat_init` signals, contextvars clearing on `task_prerun`/`task_postrun` (Pitfall 7)
- Money-column AST lint implements D-17 rules R1/R2/R3 with annotation-kind classifier suppressing false positives on legitimate non-money columns (JSONB `value`, etc.)
- pytest infrastructure (testcontainers Postgres + fakeredis fixtures + ASGI client) lives in `conftest.py` and is ready for Plan 01-03 to add DB-touching integration tests
- **30/30 unit tests pass in 1.21 seconds** — 4 Settings + 12 money-lint + 3 Sentry init + 1 Sentry endpoint + 1 Sentry task + 4 health (acceptance threshold was ≥12)

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend Python scaffold — pyproject.toml, Dockerfile, Settings, db base/session/types, Money alias, structlog, Sentry helper, redis dep, placeholder feature folders** — `e305a5a` (feat)
2. **Task 2: FastAPI app factory + health router + Celery factory + audit/feature-flag models & services + money-column AST lint script** — `6db7c46` (feat)
3. **Task 3: pytest test infrastructure — conftest (testcontainers Postgres + fakeredis), Settings/money-lint/Sentry-init/Sentry-task/health unit tests** — `9d08305` (test)

**Plan metadata commit:** _added below after this summary is staged_

## Files Created/Modified

Wave 0 (Tasks 1-3) created 38 files under `backend/`:

**Project setup** — `pyproject.toml`, `uv.lock`, `Dockerfile`, `CONVENTIONS.md`
**Cross-cutting** — `app/core/{config,logging,sentry,redis,health}.py`; `app/core/audit/{models,service}.py`; `app/core/feature_flags/{models,service}.py`
**DB layer** — `app/db/{base,session,types}.py` (Money alias is the WAL-05 source of truth)
**HTTP surface** — `app/main.py` (FastAPI factory + RequestIdMiddleware + lifespan + /_sentry-test); `app/routers/health.py` (/healthz + /readyz with dep mocks support)
**Celery surface** — `app/celery_app.py` (factory + redbeat + heartbeat + 4 signal handlers + sentry_test_task)
**Phase ownership stubs** — `app/{auth,wallet,markets,bets,admin,integrations}/__init__.py`
**Lint gate** — `scripts/lint_money_columns.py` (200 LOC, AST-walks app/**/models.py + alembic/versions/*.py)
**Tests** — `tests/{__init__,conftest,test_settings,test_money_lint,test_sentry_init,test_sentry_test_endpoint,test_sentry_test_task,test_health}.py` — 30 tests, 1.21s

## Decisions Made

1. **Python pin broadened to `>=3.12,<3.14`** — STACK.md fixed `<3.13` but Pol's machine has only 3.13.7. uv handles auto-downloading 3.12 on demand; 3.13 is FFI-compatible with every locked dep (asyncpg, psycopg2-binary, sqlalchemy, etc.).
2. **Money-lint annotation-kind classifier** — D-17 lists `value` in `MONEY_NAMES`, but `feature_flags.value` is a legitimate JSONB column. Added `_annotation_kind` (numeric / non-money / unknown) and `_NON_MONEY_ANNOTATION_NAMES` set ({bool, str, bytes, dict, list, tuple, set, datetime, date, time, timedelta, UUID, PyUUID}). R2 now only fires when the column's `Mapped[T]` annotation is numeric or unclear — not when clearly non-money like JSONB dict.
3. **Lazy engine + lazy session-maker via `@lru_cache`** — Avoids constructing an asyncpg pool at module import time. Tests can import `app.db.session` without env vars and only pay the pool cost when a test actually requests a session.
4. **Module-level env seeding in conftest.py** — Originally planned as a session-scoped autouse fixture, but `app.celery_app` instantiates `Settings()` at module load (which happens during test collection, before fixtures run). Moved env defaults to top-of-conftest module load; tests that exercise validation pass explicit constructor args.
5. **`ASGITransport(raise_app_exceptions=False)` in test client** — Default `raise_app_exceptions=True` propagates `/_sentry-test`'s RuntimeError to the test runner. Setting `False` exercises Starlette's `ServerErrorMiddleware` → 500 path, which is what Sentry's FastAPI integration relies on.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Broadened `requires-python` to `>=3.12,<3.14`**
- **Found during:** Task 1 (pyproject.toml creation)
- **Issue:** STACK.md pins Python `>=3.12,<3.13`; Pol's machine has only 3.13.7 installed at `C:\Program Files\Python313\python.exe`. Strict `<3.13` would force `uv sync` to download Python 3.12 every time and would block running tests against the host interpreter.
- **Fix:** Set `requires-python = ">=3.12,<3.14"`. uv still auto-fetches 3.12 if explicitly requested via `uv python install 3.12`; the codebase is 3.13-compatible (no use of `typing.Self` or other 3.13-specific features that 3.12 lacks; all deps are FFI-compatible).
- **Files modified:** `backend/pyproject.toml`
- **Verification:** `uv sync` resolves 105 packages cleanly on 3.13.7
- **Committed in:** `e305a5a` (Task 1 commit)

**2. [Rule 3 — Blocking] Removed `readme = "../README.md"` from pyproject.toml**
- **Found during:** Task 1 (first `uv sync`)
- **Issue:** hatchling build failed with `OSError: Readme file does not exist: ../README.md` — root README.md is Plan 01-04's responsibility (compose & ops), not Plan 01-01's.
- **Fix:** Dropped the `readme` field; backend package now builds standalone.
- **Files modified:** `backend/pyproject.toml`
- **Verification:** `uv sync` succeeds
- **Committed in:** `e305a5a` (Task 1 commit)

**3. [Rule 1 — Bug fix in linter] Added annotation-kind classifier to money-lint**
- **Found during:** Task 2 (first run of `lint_money_columns.py` against scaffold)
- **Issue:** D-17 lists `value` in `MONEY_NAMES`, but `feature_flags.value` is a legitimate JSONB column. The linter false-positived on this row and would block any legitimate `value: Mapped[dict | None] = mapped_column(JSONB, ...)` declaration. D-17's intent is a money-column safety net, not a universal name ban.
- **Fix:** Added `_annotation_kind` classifier — when `Mapped[T]` is clearly non-numeric (`dict`, `bool`, `str`, `bytes`, `list`, `tuple`, `set`, `datetime`, `date`, `time`, `timedelta`, `UUID`, `PyUUID`), R2 is suppressed. Numeric annotations (`Decimal`, `int`, `float`) still trigger R2; `unknown` annotations still trigger R2 (conservative default).
- **Files modified:** `backend/scripts/lint_money_columns.py`
- **Verification:** `test_jsonb_value_passes` test asserts feature_flags-style `value` columns pass; 12 money-lint tests all pass
- **Committed in:** `6db7c46` (Task 2 commit)

**4. [Rule 3 — Blocking] Added mypy override for `app.celery_app` to disable `[misc, untyped-decorator]`**
- **Found during:** Task 2 (first `uv run mypy app/`)
- **Issue:** Celery's `@worker_process_init.connect`, `@beat_init.connect`, `@task_prerun.connect`, `@task_postrun.connect`, and `@celery_app.task` decorators return untyped callables under mypy strict; the wrapped functions are fully typed but the decorators trigger `untyped-decorator` errors.
- **Fix:** Added `[[tool.mypy.overrides]] module = "app.celery_app"` block with `disable_error_code = ["misc", "untyped-decorator"]`. The rest of mypy strict mode still applies; only Celery decorator type-erasure is suppressed.
- **Files modified:** `backend/pyproject.toml`
- **Verification:** `uv run mypy app/` → Success: no issues found in 27 source files
- **Committed in:** `6db7c46` (Task 2 commit)

**5. [Rule 1 — Bug fix in test infra] `ASGITransport(raise_app_exceptions=False)`**
- **Found during:** Task 3 (first test run, `test_sentry_test_endpoint_raises_500` failed)
- **Issue:** Default `raise_app_exceptions=True` propagates the route's `RuntimeError` to the test runner instead of letting Starlette's `ServerErrorMiddleware` convert it to a 500. In production, the client sees a 500 response (Sentry's integration relies on this path).
- **Fix:** Set `raise_app_exceptions=False` in the `client` fixture.
- **Files modified:** `backend/tests/conftest.py`
- **Verification:** `test_sentry_test_endpoint_raises_500` passes (asserts status 500)
- **Committed in:** `9d08305` (Task 3 commit)

**6. [Rule 1 — Bug fix in test infra] Moved env seeding from session-fixture to conftest module load**
- **Found during:** Task 3 (first test collection — `test_sentry_test_task.py` failed to import)
- **Issue:** `app.celery_app` instantiates `Settings()` at module load. Pytest collection imports this module before any fixture runs, including the session-scoped autouse env fixture. Result: `ValidationError` during collection for `DATABASE_URL`/`DATABASE_URL_SYNC`/`REDIS_URL`.
- **Fix:** Moved `_DEFAULT_TEST_ENV` seeding to top-of-conftest module load (runs at import, before collection). Tests that need to verify Settings validation pass explicit constructor args, so they don't rely on the defaults.
- **Files modified:** `backend/tests/conftest.py`
- **Verification:** Full Wave-0 suite collects and passes (30/30)
- **Committed in:** `9d08305` (Task 3 commit)

**7. [Rule 3 — Blocking] Auto-fix lint nits (`SIM103`, `SIM105`)**
- **Found during:** Tasks 2 and 3 (ruff runs)
- **Issue:** Ruff's `SIM103` flagged a returnable conditional; `SIM105` flagged a `try/except OSError: pass` in the beat heartbeat loop.
- **Fix:** Inlined the conditional via `return isinstance(...) and ...`; replaced `try/except pass` with `contextlib.suppress(OSError)`.
- **Files modified:** `backend/scripts/lint_money_columns.py`, `backend/app/celery_app.py`
- **Verification:** `uv run ruff check app/ scripts/ tests/` → All checks passed
- **Committed in:** `6db7c46` (Task 2) and applied in `9d08305` (Task 3 ruff sweep)

---

**Total deviations:** 7 auto-fixed (3 Rule 3 blocking, 3 Rule 1 bug fixes in linter/test infra, 1 Rule 3 lint nits)
**Impact on plan:** All deviations are infrastructure-level — none change the interface contracts Phase 2+ depends on. The money-lint annotation-kind classifier is the only behavior-affecting change; it strengthens the lint (lower false-positive rate) without weakening it (numeric and unknown annotations still trigger R2 on money-named columns).

## Issues Encountered

- **No `uv` and no Python 3.12 on host at start.** Resolved by installing `uv` via `python -m pip install --user uv` (uv is the official Astral installer tool, listed in RESEARCH §slopcheck-clean with status `OK`). Python 3.13.7 is sufficient given the pin broadening above; uv can auto-fetch 3.12 on demand for any consumer that needs strict 3.12-only.
- **CRLF line-ending warnings on every `git add`** (Windows default). Not blocking; Plan 01-04 will add `.gitattributes` with `* text=auto eol=lf` for compose/Dockerfile/shell scripts (per Pitfall 8).

## User Setup Required

None for this plan. `SENTRY_DSN` is optional (Settings defaults to None; init_sentry no-ops when unset). `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL` will be wired into `.env.example` by Plan 01-04. End-to-end Sentry round-trip verification (PLT-08 manual gate) needs a real DSN, but that's part of the phase verifier step, not this plan.

## Next Phase Readiness

**Wave 1 sibling 01-02 (frontend Next.js scaffold) is ready to start** — no shared files; 01-02 owns `frontend/` exclusively. Sequential execution proceeds to 01-02 immediately.

**Wave 2 (Plans 01-03, 01-04) prerequisites all in place:**
- 01-03 (Alembic baseline + integration tests) inherits `app/db/base.py` (Base), `app/db/types.py` (Money), the `AuditLog` + `FeatureFlag` ORM models, the `AuditService` + `FeatureFlagService` contracts, and the testcontainers Postgres + `async_session` fixtures in `conftest.py`. 01-03 only needs to author `alembic/env.py`, the baseline migration, and the DB-touching integration tests.
- 01-04 (compose + ops) inherits the `Dockerfile`, the Settings env var list (DATABASE_URL/DATABASE_URL_SYNC/REDIS_URL/SENTRY_DSN/etc.), and the beat heartbeat file path (`/tmp/celerybeat.heartbeat`) for the docker-compose healthcheck.

**Phase 2 contracts honored:** `SESSION_SIGNING_KEY` and `ADMIN_TOKEN` are NOT defined in `Settings` (only mentioned in the docstring); Phase 2 will APPEND them per D-09's locked pattern. structlog scrubber already preempts `session_signing_key`, `admin_token`, and `xp_session` per D-25.

**Known stubs / deferred items:**
- `/readyz` integration with real DB + Redis lives in Plan 01-03's testcontainers suite (this plan exercises the route with `dependency_overrides` to stay under 30 seconds).
- Audit immutability tests (PLT-02) and feature-flag DB integration tests (PLT-06) live in Plan 01-03 — this plan ships the ORM models + service signatures, not the live DB exercises.
- `.env.example` update with Phase 1 keys (DATABASE_URL/REDIS_URL/SENTRY_DSN) lives in Plan 01-04.

## Self-Check: PASSED

Verified 29/29 files exist on disk; verified 3/3 task commits exist in `git log --all`. Wave-0 test suite re-run after summary draft: 30/30 passing in 1.21s.

---
*Phase: 01-scaffold-foundations*
*Plan: 01*
*Completed: 2026-05-26*
