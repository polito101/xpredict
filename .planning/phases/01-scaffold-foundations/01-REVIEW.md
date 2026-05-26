---
phase: 01-scaffold-foundations
reviewed: 2026-05-26T00:00:00Z
depth: standard
files_reviewed: 54
files_reviewed_list:
  - backend/app/core/config.py
  - backend/app/core/logging.py
  - backend/app/core/sentry.py
  - backend/app/core/redis.py
  - backend/app/db/base.py
  - backend/app/db/session.py
  - backend/app/db/types.py
  - backend/app/main.py
  - backend/app/celery_app.py
  - backend/app/routers/health.py
  - backend/app/core/audit/models.py
  - backend/app/core/audit/service.py
  - backend/app/core/feature_flags/models.py
  - backend/app/core/feature_flags/service.py
  - backend/scripts/lint_money_columns.py
  - backend/tests/conftest.py
  - backend/tests/test_settings.py
  - backend/tests/test_money_lint.py
  - backend/tests/test_sentry_init.py
  - backend/tests/test_sentry_test_endpoint.py
  - backend/tests/test_sentry_test_task.py
  - backend/tests/test_health.py
  - backend/tests/core/test_audit_immutability.py
  - backend/tests/core/test_feature_flags.py
  - backend/tests/test_gitleaks_blocks_secret.py
  - backend/alembic/env.py
  - backend/alembic/versions/0001_phase1_foundations.py
  - frontend/next.config.ts
  - frontend/tsconfig.json
  - frontend/eslint.config.mjs
  - frontend/vitest.config.ts
  - frontend/src/instrumentation.ts
  - frontend/src/instrumentation-client.ts
  - frontend/src/app/layout.tsx
  - frontend/src/app/page.tsx
  - frontend/src/app/globals.css
  - frontend/src/app/api/healthz/route.ts
  - frontend/src/app/api/sentry-test/route.ts
  - frontend/src/app/api/healthz/route.test.ts
  - frontend/src/app/api/sentry-test/route.test.ts
  - docker-compose.yml
  - .gitleaks.toml
  - .pre-commit-config.yaml
  - .github/workflows/backend-ci.yml
  - .github/workflows/frontend-ci.yml
  - .github/workflows/security.yml
  - bin/dev
  - bin/dev.ps1
  - Makefile
  - README.md
  - .env.example
  - .gitignore
  - .gitattributes
findings:
  critical: 6
  warning: 7
  info: 4
  total: 17
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-26T00:00:00Z
**Depth:** standard
**Files Reviewed:** 54
**Status:** issues_found

## Summary

Reviewed the full Phase 1 scaffold: FastAPI + SQLAlchemy async + Celery + Redis + Postgres backend, Next.js 15 frontend, Alembic baseline migration, docker-compose 8-service stack, and CI/CD pipeline.

The overall structure is clean and design decisions are consistently applied: async SQLAlchemy patterns, pure-ASGI RequestIdMiddleware, Sentry signal-driven init in Celery, and the Money/Decimal AST lint gate all land correctly. The audit-log immutability trigger pattern is sound.

Six critical issues require fixes before Phase 2 ships — they cover a test-isolation flaw that produces dirty shared state between integration tests, an unauthenticated synthetic-error endpoint exploitable to exhaust Sentry quotas, a money-lint blind spot that lets wrong-precision `Numeric` through via keyword argument form, and a Sentry DSN guard gap on the frontend that causes unconditional SDK init with an empty string.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `/_sentry-test` is unauthenticated and reachable in any environment

**File:** `backend/app/main.py:84-87`
**Issue:** The synthetic Sentry trigger is registered unconditionally with no environment guard, no auth gate, and no rate limiting. Any caller who can reach port 8000 can repeatedly `GET /_sentry-test` to generate unlimited Sentry error events. Phases 2 through 10 introduce real users and traffic before Phase 11 "may gate" this endpoint per the docstring. A simple loop from any network-adjacent attacker can exhaust Sentry's monthly event quota ($0 plan: 5 000 events/month, paid plans vary), effectively disabling error monitoring before it matters.

The route handles both `GET` and `HEAD` methods — `HEAD` returns no body but still raises `RuntimeError`, still produces a Sentry event. The same exploit applies to the frontend `/api/sentry-test` route.

**Fix:**
```python
@app.api_route("/_sentry-test", methods=["GET", "HEAD"])
async def sentry_test() -> dict[str, str]:
    if not settings.is_dev:
        raise HTTPException(status_code=403, detail="not available")
    raise RuntimeError("sentry test from api")
```

---

### CR-02: `async_session` fixture missing `scope="session"` — integration tests share dirty state

**File:** `backend/tests/conftest.py:174`
**Issue:** `@pytest_asyncio.fixture(loop_scope="session")` does **not** set `scope=`. The default scope is `"function"`, so a new session (and new transaction) is created for each test. However the fixture opens a transaction on a `session`-scoped engine connection and relies on `trans.rollback()` in the `finally` to clean up. In practice, `pytest-asyncio 0.25` with `loop_scope="session"` and `scope="function"` creates conflicts: the function-scoped fixture is torn down and re-entered within the session loop, and asyncpg raises `"Event loop is closed"` intermittently.

More critically for correctness: `test_is_enabled_toggle` runs an `UPDATE feature_flags SET enabled = TRUE` and then asserts `is_enabled(...) is True`. If that test runs before `test_is_enabled_returns_seeded_value`, the seeded value assertion (`is False`) fails — ordering-dependent test pollution. The `trans.rollback()` only executes when the fixture goes out of scope; with `scope="function"` each test gets a fresh fixture entry that starts a **new** transaction on the **same** underlying session-scoped connection, but the prior write is already visible.

**Fix:**
```python
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                yield session
        finally:
            await trans.rollback()
```
For true per-test isolation with a session-scoped engine, use savepoints (`conn.begin_nested()`) — one per test function — inside the outer session-level transaction.

---

### CR-03: `test_settings_rejects_malformed_url` can silently pass as a false positive

**File:** `backend/tests/test_settings.py:33-40`
**Issue:** `conftest.py` seeds `DATABASE_URL` as a valid URL at **module import time** via `os.environ.setdefault()`. `pydantic-settings` reads env vars with priority over constructor keyword arguments. When `Settings(DATABASE_URL="not-a-url")` is called, `pydantic-settings` v2 silently prefers the env var value (`postgresql+asyncpg://...`) over the constructor kwarg, so no `ValidationError` is raised and the test passes — but it passes because the env var provides a valid URL, not because the validation logic correctly rejects the bad input.

This is a latent false positive: the test appears to verify error handling but actually verifies nothing about it. Any future phase that changes env priority behaviour will reveal this.

**Fix:**
```python
def test_settings_rejects_malformed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "not-a-url")
    monkeypatch.setenv("DATABASE_URL_SYNC", _VALID_URLS["DATABASE_URL_SYNC"])
    monkeypatch.setenv("REDIS_URL", _VALID_URLS["REDIS_URL"])
    with pytest.raises(ValidationError):
        Settings()
```

---

### CR-04: Money linter misses `Numeric` passed as `type_=` keyword arg to `mapped_column`

**File:** `backend/scripts/lint_money_columns.py:99-134`
**Issue:** `_find_numeric_args` iterates only over `call.args` (positional arguments of `mapped_column`). SQLAlchemy also accepts the column type via the `type_=` keyword argument: `mapped_column(type_=Numeric(10, 2))`. In that form the `Numeric(...)` node lives in `call.keywords`, not `call.args`, and `_find_numeric_args` returns `None` — no error is reported. A developer who writes `amount: Mapped[Decimal] = mapped_column(type_=Numeric(10, 2))` gets zero lint failures despite violating R1 (wrong precision/scale).

There is no test case for this form, so the gap is invisible in CI.

**Fix:** Extend `_find_numeric_args` to also scan keyword args of the outer `mapped_column` call:
```python
# After scanning call.args, also check keyword arguments:
for kw in call.keywords:
    if (
        isinstance(kw.value, ast.Call)
        and isinstance(kw.value.func, ast.Name)
        and kw.value.func.id == "Numeric"
    ):
        # parse precision/scale from kw.value exactly as for positional Numeric
        ...
```
Add a test fixture and corresponding `assert lint(tmp_path) == 1` case in `test_money_lint.py`.

---

### CR-05: `scrub_secrets` processor only scrubs top-level keys — nested secrets pass through

**File:** `backend/app/core/logging.py:42-51`
**Issue:** `scrub_secrets` iterates `event_dict.keys()` and replaces values for matching keys. Any nested dict — e.g., `logger.info("auth", payload={"password": "hunter2"})` — is not scrubbed; the `payload` key is not in `SCRUB_KEYS`, so its `password` child is emitted in plain text to the JSON log stream.

The module docstring says it "protects log output from accidentally leaking these values" without qualifying that protection as top-level-only. Phase 2's auth and session management will log structured payloads under this false guarantee. The `SCRUB_KEYS` set already pre-emptively includes `session_signing_key` and `admin_token` for Phase 2 values, suggesting the author expects these to appear in log fields — but a nested `{"session_signing_key": "..."}` is invisible to the scrubber.

**Fix — minimal (document the gap explicitly):**
```python
def scrub_secrets(...) -> MutableMapping[str, Any]:
    """structlog processor — replace values for sensitive keys with ``***``.

    WARNING: Only top-level keys in event_dict are scrubbed. Nested dicts
    (e.g. payload={"password": "x"}) are NOT recursively walked.
    Callers must not log sensitive data under nested keys.
    """
```

**Fix — complete (recursive scrub):**
```python
def _scrub_recursive(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: "***" if k.lower() in SCRUB_KEYS else _scrub_recursive(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub_recursive(item) for item in obj]
    return obj

def scrub_secrets(_logger, _name, event_dict):
    return _scrub_recursive(event_dict)
```

---

### CR-06: `gitleaks-action` pinned to mutable `@v2` floating tag in two CI workflows

**File:** `.github/workflows/backend-ci.yml:63`, `.github/workflows/security.yml:26`
**Issue:** Both workflows reference `gitleaks/gitleaks-action@v2` — a mutable floating tag controlled by a third-party author. If that GitHub user account is compromised or the tag is force-pushed, every CI run silently executes adversarial code with `GITHUB_TOKEN` in scope (which, even with `permissions: contents: read`, can read private repository contents). The security workflow is the one responsible for preventing secret leaks — compromising it is the highest-value attack on this pipeline.

The pre-commit hook pins gitleaks itself to `v8.30.1` (immutable), but the CI action does not pin.

**Fix:** Pin to a specific commit SHA (most secure) or a specific version tag:
```yaml
# .github/workflows/backend-ci.yml and security.yml:
uses: gitleaks/gitleaks-action@v2.3.9  # or pin to SHA
```
Check https://github.com/gitleaks/gitleaks-action/releases for the latest stable tag.

---

## Warnings

### WR-01: `Settings()` instantiated per-request/per-task in three hot paths

**Files:** `backend/app/core/redis.py:24`, `backend/app/core/audit/service.py:54`, `backend/app/core/feature_flags/service.py:34`, `backend/app/core/audit/models.py:48`, `backend/app/core/feature_flags/models.py:39`
**Issue:** `pydantic-settings` validates all environment variables on every `Settings()` construction. Five call sites construct a new `Settings()` on each request, on each audit write, and on each feature-flag read. The existing `@lru_cache(maxsize=1)` pattern in `app/db/session.py` is the established project idiom for exactly this case. The per-request model construction is not catastrophic today, but scales poorly under load and is inconsistent with the stated project convention.

**Fix:** Add a cached factory at the module level or in `config.py`:
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```
Then replace every bare `Settings()` call (outside tests) with `get_settings()`.

---

### WR-02: `AsyncSession(bind=conn)` uses deprecated keyword — breaks on SQLAlchemy 2.1+

**File:** `backend/tests/conftest.py:185`
**Issue:** `AsyncSession(bind=conn, expire_on_commit=False)` uses the `bind=` keyword, which was deprecated in SQLAlchemy 2.0 and is removed in SQLAlchemy 2.1. The `pyproject.toml` likely pins `sqlalchemy>=2.0,<2.1` today, but the first minor version bump in any future phase silently breaks all integration tests with `TypeError: __init__() got an unexpected keyword argument 'bind'`.

**Fix:**
```python
async with AsyncSession(conn, expire_on_commit=False) as session:
    yield session
```
Pass the connection positionally, not via `bind=`.

---

### WR-03: Beat service healthcheck window is half the interval — one jitter event fails it

**File:** `docker-compose.yml:138`
**Issue:** `find /tmp/celerybeat.heartbeat -mmin -1` checks for a file touched within the last 60 seconds. The heartbeat thread touches the file every 30 seconds (`_HEARTBEAT_INTERVAL_SECONDS = 30`). Any pause longer than 31 seconds — GC, RedBeat lock contention, resource starvation — causes the mtime to exceed 60 seconds and triggers a health failure. Docker then counts this toward `retries: 5` and may restart the beat process.

The beat service also lacks a `start_period`, meaning Docker counts failures from container start. The heartbeat thread is only started *after* the beat process initialises (inside `_init_beat`), which includes acquiring RedBeat's distributed lock — this can take tens of seconds on first boot.

**Fix:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "[ $$(find /tmp/celerybeat.heartbeat -mmin -2 2>/dev/null | wc -l) -eq 1 ] || exit 1"]
  interval: 30s
  timeout: 5s
  retries: 5
  start_period: 60s
```

---

### WR-04: Frontend Sentry initialised with empty-string DSN — SDK emits errors, may attempt invalid connections

**Files:** `frontend/src/instrumentation.ts:19`, `frontend/src/instrumentation-client.ts:14`
**Issue:** Both files pass `dsn: process.env.NEXT_PUBLIC_SENTRY_DSN` directly to `Sentry.init()`. With the `.env.example` default of `NEXT_PUBLIC_SENTRY_DSN=`, this evaluates to `dsn: ""`. Sentry SDK 10.x does not treat an empty string the same as `undefined`/`null`: it attempts to parse the DSN, fails with an internal warning, and may establish a Sentry hub in an error state. Every browser page load in dev emits spurious console output; every server start produces a Node.js warning.

The backend `init_sentry()` explicitly guards `if not settings.SENTRY_DSN: return` — the frontend has no equivalent guard.

**Fix:** Add explicit guard in both instrumentation files:
```typescript
// instrumentation-client.ts
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) {
  Sentry.init({ dsn, tracesSampleRate: 0.1, ... });
}

// instrumentation.ts (inside the nodejs guard)
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) {
  Sentry.init({ dsn, tracesSampleRate: 0.1, ... });
}
```

---

### WR-05: `AuditLog.id` has no Python-side default — `row.id` is `None` until DB flush returns

**File:** `backend/app/core/audit/models.py:27-31`
**Issue:** `id` is declared with only `server_default=func.gen_random_uuid()`. SQLAlchemy populates `row.id` only after a `RETURNING id` round-trip (i.e., after `session.flush()`). `AuditService.record()` calls `session.flush()`, so `row.id` is populated by the time `record()` returns — that is the happy path. However, if a caller creates an `AuditLog` directly (bypassing `AuditService`) and accesses `row.id` before flushing, `row.id` is `None` — silently, without error. The test `test_audit_service_record` does not assert `row.id is not None`, so this regression path has no coverage.

Adding a Python-side `default=uuid4` makes the field immediately assigned on construction, removes the pre-flush `None` window, and is the standard SQLAlchemy pattern when `server_default` is also present.

**Fix:**
```python
from uuid import uuid4

id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    default=uuid4,
    server_default=func.gen_random_uuid(),
)
```
Add `assert row.id is not None` to `test_audit_service_record`.

---

### WR-06: `downgrade()` will fail with FK constraint errors once Phase 2+ references `audit_log`

**File:** `backend/alembic/versions/0001_phase1_foundations.py:144-154`
**Issue:** `op.drop_table("feature_flags")` followed by `op.drop_table("audit_log")` will fail once any Phase 2+ migration adds a foreign key referencing `audit_log`. The drop order also matters: if Phase 2 adds a table that references `feature_flags`, the current downgrade sequence drops `feature_flags` before dropping its dependents.

Standard Alembic practice is to add `sa.text("CASCADE")` or use `postgresql_cascade=True` when the dependency graph is expected to grow, or to at minimum document that downgrade requires manual intervention.

**Fix:**
```python
def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutability_trigger ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS raise_audit_immutable();")
    op.drop_table("feature_flags")
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE;")
```

---

### WR-07: `test_gitleaks_fires_on_synthetic_fixture` does not assert exit code of the gitleaks run

**File:** `backend/tests/test_gitleaks_blocks_secret.py:94-105`
**Issue:** `_run_gitleaks(...)` returns `(exit_code, stdout, stderr)` but the return value is discarded. The test then checks that `report_path.exists()` and that `len(findings) == 2`. If gitleaks exits 0 (unexpected — no detections) or crashes with exit code 2, the report file may not be written or may be empty/`null`, and the `assert report_path.exists()` check catches it — but only partially. A gitleaks version that changes its JSON report schema could silently write an empty list or a different structure, and the test would not detect the failure mode.

**Fix:**
```python
exit_code, stdout, stderr = _run_gitleaks([...], cwd=REPO_ROOT)
assert exit_code == 1, (
    f"expected gitleaks to exit 1 (findings detected); got {exit_code}. "
    f"stdout={stdout!r} stderr={stderr!r}"
)
assert report_path.exists(), ...
```

---

## Info

### IN-01: `.gitleaks.toml` allowlist covers entire `.planning/` directory

**File:** `.gitleaks.toml:43`
**Issue:** `'''\.planning/.*'''` allowlists every file under `.planning/` from secret scanning. Planning documents written by agents may inadvertently contain real Sentry DSNs, database connection strings, or signing keys copy-pasted from local environments. The allowlist was presumably added to allow example env-var snippets in planning docs, but it has no narrower scope.

**Suggestion:** Narrow the allowlist to specific file patterns within `.planning/`:
```toml
paths = [
  '''\.planning/.*-RESEARCH\.md$''',
  '''\.planning/.*-PLAN\.md$''',
  # ... etc.
]
```
Or add a comment documenting that planning docs must never contain real secrets.

---

### IN-02: `pytestmark = pytest.mark.skipif(GITLEAKS is None, ...)` has inverted condition

**File:** `backend/tests/test_gitleaks_blocks_secret.py:42`
**Issue:** The condition is `skipif(GITLEAKS is None, reason=_SKIP_REASON)`. Read literally: "skip if gitleaks is NOT found". This is the correct intent — skip when the binary is absent. However the `_SKIP_REASON` string says "gitleaks not installed on PATH ... required for PLT-04 verification". The logic is correct but the naming of `_SKIP_REASON` is misleading — it reads like it's the reason the test is being kept, not the reason it's being skipped. Minor, but can confuse a reader who sees the skip in CI output.

**Suggestion:** Rename to `_MISSING_GITLEAKS_REASON` or adjust wording to clearly indicate it's the skip justification.

---

### IN-03: Flower admin UI exposed on host port 5555 with no auth and `FLOWER_UNAUTHENTICATED_API: "true"`

**File:** `docker-compose.yml:144-161`
**Issue:** Flower is published on `localhost:5555` and `FLOWER_UNAUTHENTICATED_API: "true"` is set unconditionally. The comment says "Dev-only; staging/prod sets FLOWER_BASIC_AUTH" but nothing in the startup scripts or CI enforces that `FLOWER_BASIC_AUTH` is present in non-dev environments. Flower 2.0+ allows task cancellation, worker termination, and full task argument inspection via `/api/*` when unauthenticated — once Phase 2+ adds real task payloads (user data, payment events), unauthenticated Flower in staging/prod is a data exposure risk.

**Suggestion:** Ensure `FLOWER_BASIC_AUTH` is in the `.env.example` (commented, but present), and add a startup check in `bin/dev.ps1`/`bin/dev` that warns when running non-dev without `FLOWER_BASIC_AUTH`.

---

### IN-04: `mailpit` healthcheck has no `start_period`

**File:** `docker-compose.yml:75-79`
**Issue:** The mailpit service defines `retries: 3` and `interval: 30s` but no `start_period`. Docker counts failures from container creation — if mailpit takes more than 90 seconds to come up (slow disk, image pull), it is marked unhealthy before it has a chance to become ready. No other service depends on mailpit in Phase 1, so the impact today is limited to a confusing `docker compose ps` output.

**Suggestion:** Add `start_period: 10s` to match the other services.

---

_Reviewed: 2026-05-26T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
