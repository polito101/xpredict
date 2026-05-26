---
phase: 01-scaffold-foundations
plan_set: 01-04
status: issues_found
depth: standard
files_reviewed: 54
findings:
  critical: 5
  warning: 8
  info: 4
  total: 17
reviewed_at: 2026-05-26
---

# Code Review: Phase 01 — Project Scaffold, Infra & Cross-Cutting Foundations

**Depth:** standard | **Files Reviewed:** 54 | **Status:** issues_found

The scaffold is structurally sound: money/Decimal enforcement, audit-log immutability trigger, and structlog scrubbing are all correctly implemented. Async SQLAlchemy patterns are clean. Five critical issues need addressing before Phase 2 ships.

---

## Critical

### CR-01: `/_sentry-test` is unauthenticated and unguarded in all environments
**File:** `backend/app/main.py` (sentry_test route)

The `sentry_test()` route unconditionally raises `RuntimeError` with no environment check and no auth gate. Any caller hitting `/_sentry-test` on port 8000 generates a Sentry event — attackers can exhaust Sentry rate limits with a simple loop. The docstring says "Phase 11 may gate" but Phases 2–10 introduce real users before Phase 11.

**Fix:** Add env guard before raising:
```python
if settings.ENVIRONMENT not in ("development", "test"):
    raise HTTPException(status_code=403, detail="not available")
```

---

### CR-02: `async_session` test fixture has wrong scope — integration tests share dirty state
**File:** `backend/tests/conftest.py` (async_session fixture)

`@pytest_asyncio.fixture(loop_scope="session")` has no `scope=` argument, so it defaults to `scope="function"`. The `engine` fixture is `scope="session"`. Each function invocation commits independently — no rollback isolation between tests. `test_is_enabled_toggle` writes `enabled=TRUE` for `stripe_recharge_enabled` and that state persists (flaky-by-design). Additionally, pytest-asyncio 0.25 warns against mixing `scope="function"` with `loop_scope="session"` — asyncpg connections can cross event loops and raise "Event loop is closed".

**Fix:**
```python
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    ...
```
For true per-test isolation, use `begin_nested()` (savepoints) inside the session-scoped connection.

---

### CR-03: Beat healthcheck window too tight — spurious unhealthy under scheduling jitter
**File:** `docker-compose.yml` (beat service healthcheck)

Uses `find /tmp/celerybeat.heartbeat -mmin -1` (60-second window). Heartbeat thread touches every 30 seconds. Any jitter (GC pause, RedBeat lock contention) that delays the heartbeat 31+ seconds fails the check. No `start_period:` means Docker counts failures from time zero.

**Fix:**
```yaml
test: ["CMD-SHELL", "[ $$(find /tmp/celerybeat.heartbeat -mmin -2 2>/dev/null | wc -l) -eq 1 ] || exit 1"]
start_period: 60s
```
Change `-mmin -1` to `-mmin -2` for a 120-second window against the 30-second touch interval.

---

### CR-04: `scrub_secrets` does not scrub nested dict values — undocumented data-exposure gap
**File:** `backend/app/core/logging.py` (scrub_secrets processor)

Only top-level event dict keys are scrubbed. Nested data like `logger.info("user", data={"password": "secret"})` passes through unmasked. CONVENTIONS.md says the scrubber "masks values for keys in SCRUB_KEYS" without qualifying "top-level only". Phase 2 will log auth payloads under this false guarantee.

**Fix:** Document the limitation prominently in the docstring AND in CONVENTIONS.md section 8. Add a test asserting nested secrets pass through (intentional gap, not a silent bug).

---

### CR-05: Dockerfile `uv sync --frozen || uv sync` fallback silently drops frozen-lockfile guarantee
**File:** `backend/Dockerfile`

```dockerfile
RUN uv sync --frozen --no-dev || uv sync --no-dev
```
If `uv sync --frozen` fails, the fallback runs an unfrozen install. The prod container silently diverges from `uv.lock`. CI passes because the build succeeds.

**Fix:** Remove the fallback:
```dockerfile
RUN uv sync --frozen --no-dev
```

---

## Warnings

### WR-01: `Settings()` instantiated on every request/task in three hot paths
**Files:** `backend/app/core/redis.py`, `backend/app/core/audit/service.py`, `backend/app/core/feature_flags/service.py`

`pydantic-settings` parses and validates all env vars on each `Settings()` call. In production these run per-request and per-transactional write. The `@lru_cache(maxsize=1)` pattern already exists in `app/db/session.py`.

**Fix:** Add a cached `get_settings()` factory and use it in these three call sites.

---

### WR-02: `AsyncSession(bind=conn)` uses deprecated keyword removed in SQLAlchemy 2.1
**File:** `backend/tests/conftest.py`

`pyproject.toml` pins `sqlalchemy>=2.0.43,<2.1` so this works today. The first Phase 2 bump to SQLAlchemy 2.1 breaks all integration tests with `TypeError: unexpected keyword argument 'bind'`.

**Fix:** `AsyncSession(conn, expire_on_commit=False)` — positional, not `bind=`.

---

### WR-03: Flower API unauthenticated with no enforcement for staging/prod
**File:** `docker-compose.yml` (flower service)

`FLOWER_UNAUTHENTICATED_API: "true"` with no `FLOWER_BASIC_AUTH` means anyone reaching port 5555 can cancel tasks, terminate workers, and inspect task arguments (which will contain sensitive data from Phase 2+). No startup check validates the operator assumption.

**Fix:** Remove `ports:` from flower in base compose (accessible only via `exec`), or add a guard in `bin/dev`/`bin/dev.ps1` that warns when `FLOWER_BASIC_AUTH` is unset and `ENVIRONMENT != dev`.

---

### WR-04: `AuditLog.id` has no Python-side default — `row.id` is `None` before RETURNING completes
**File:** `backend/app/core/audit/models.py`

`server_default=func.gen_random_uuid()` means the DB generates the UUID. No test asserts `row.id is not None` after `AuditService.record()`, so a regression goes undetected.

**Fix:** Add `default=uuid4` as Python-side default alongside `server_default`. Add `assert row.id is not None` to `test_audit_service_record`.

---

### WR-05: Money linter misses `Numeric` passed via `type_=` keyword to `mapped_column`
**File:** `backend/scripts/lint_money_columns.py`

`_find_numeric_args` only scans positional `call.args`. A column declared as `mapped_column(type_=Numeric(10, 2))` produces zero errors from R1 — wrong precision passes silently.

**Fix:** Extend `_find_numeric_args` to also check `call.keywords` for `Numeric(...)` values. Add a test case to `test_money_lint.py`.

---

### WR-06: `test_settings_rejects_malformed_url` may pass for the wrong reason
**File:** `backend/tests/test_settings.py`

Module-level env seed in `conftest.py` sets `DATABASE_URL` to a valid URL. `pydantic-settings` env vars take priority over constructor kwargs. `Settings(DATABASE_URL="not-a-url")` may silently use the env var's valid URL — `ValidationError` never fires, making the test a false pass.

**Fix:** Use `monkeypatch.setenv("DATABASE_URL", "not-a-url")` to unambiguously force the invalid value.

---

### WR-07: Frontend `instrumentation-client.ts` initialises Sentry with empty-string DSN in dev
**Files:** `frontend/instrumentation-client.ts`, `frontend/instrumentation.ts`

`Sentry.init({ dsn: process.env.NEXT_PUBLIC_SENTRY_DSN })` runs unconditionally. With `.env.example` defaults `NEXT_PUBLIC_SENTRY_DSN=""`, Sentry SDK 10.x emits a console warning and may attempt invalid connections on every page load.

**Fix:** Guard: `if (dsn) { Sentry.init({ dsn, ... }); }`

---

### WR-08: `downgrade()` will fail when Phase 2+ adds FK constraints referencing `audit_log`
**File:** `backend/alembic/versions/0001_phase1_foundations.py`

`op.drop_table("audit_log")` without `cascade=True` will fail with FK constraint errors once Phase 2+ migrations reference `audit_log`.

**Fix:** `op.drop_table("audit_log", cascade=True)`. Document in migration comment.

---

## Info

### IN-01: `.gitleaks.toml` allowlists entire `.planning/` tree
An accidentally-pasted real Sentry DSN or signing key in any planning doc would be invisible to gitleaks.

**Suggestion:** Narrow to specific file patterns or add a comment that the allowlist is for documentation snippets only, never real secrets.

---

### IN-02: `mailpit` healthcheck missing `start_period`
No `start_period` means Docker counts failures from cold start. With `retries: 3` and `interval: 30s`, mailpit has only 90 seconds to become healthy.

**Suggestion:** Add `start_period: 10s`.

---

### IN-03: `test_gitleaks_blocks_secret.py` discards `_run_gitleaks` exit code
`_run_gitleaks()` returns `(exit_code, stdout, stderr)` but the return value is discarded.

**Suggestion:** Capture and assert `exit_code != 0` for the negative test.

---

### IN-04: `gitleaks/gitleaks-action@v2` pinned to mutable tag in CI
**Files:** `.github/workflows/backend-ci.yml`, `.github/workflows/security.yml`

Mutable tag from third-party author — supply-chain attack risk.

**Suggestion:** Pin to specific release: `gitleaks/gitleaks-action@v2.3.9`

---

## Summary

| Severity | Count | Key files |
|----------|-------|-----------|
| Critical | 5 | main.py, conftest.py, docker-compose.yml, logging.py, Dockerfile |
| Warning  | 8 | conftest.py, redis.py, audit/service.py, feature_flags/service.py, audit/models.py, lint_money_columns.py, test_settings.py, instrumentation-client.ts, 0001_phase1_foundations.py |
| Info     | 4 | .gitleaks.toml, docker-compose.yml, test_gitleaks_blocks_secret.py, CI workflows |
| **Total**| **17** | |

**Recommended fix order before Phase 2:**
1. **CR-05** (Dockerfile fallback) — 1-line fix, prevents silent prod divergence
2. **CR-02** (async_session scope) — prevents flaky CI blocking Phase 2
3. **CR-01** (`/_sentry-test` auth gate) — add env guard before real deployment
4. **CR-03** (beat healthcheck window) — prevents phantom unhealthy restarts
5. **CR-04** (scrub_secrets doc) — document limitation before Phase 2 auth logging
