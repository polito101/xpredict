---
phase: 01-scaffold-foundations
fixed_at: 2026-05-26T20:55:00Z
review_path: .planning/phases/01-scaffold-foundations/01-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-05-26T20:55:00Z
**Source review:** `.planning/phases/01-scaffold-foundations/01-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 13 (6 Critical + 7 Warning; Info excluded per fix_scope=critical_warning)
- Fixed: 13
- Skipped: 0

## Fixed Issues

### CR-01: `/_sentry-test` is unauthenticated and reachable in any environment

**Files modified:** `backend/app/main.py`
**Commit:** `1cdd6b8`
**Applied fix:** Added `from fastapi import FastAPI, HTTPException` import and a guard `if not settings.is_dev: raise HTTPException(status_code=403, detail="not available")` at the top of `sentry_test()`. The route now returns 403 in staging/prod and only raises the synthetic RuntimeError in dev.

---

### CR-02: `async_session` fixture missing `scope="session"` — integration tests share dirty state

**Files modified:** `backend/tests/conftest.py`
**Commit:** `149187f`
**Applied fix:** Changed `@pytest_asyncio.fixture(loop_scope="session")` to `@pytest_asyncio.fixture(scope="session", loop_scope="session")` so the fixture is created once per test session. Also fixed the `AsyncSession(bind=conn, ...)` deprecated keyword to positional form `AsyncSession(conn, ...)` (combining CR-02 and WR-02 in one atomic commit). Added explanatory docstring about the scope rationale.

---

### CR-03: `test_settings_rejects_malformed_url` can silently pass as a false positive

**Files modified:** `backend/tests/test_settings.py`
**Commit:** `33b4889`
**Applied fix:** Rewrote `test_settings_rejects_malformed_url` to use `monkeypatch.setenv("DATABASE_URL", "not-a-url")` (plus valid values for the other required URLs) so pydantic-settings reads the invalid value via its highest-priority env-var path rather than the constructor kwargs that env vars silently shadow. The test now exercises the actual validation path.

---

### CR-04: Money linter misses `Numeric` passed as `type_=` keyword arg to `mapped_column`

**Files modified:** `backend/scripts/lint_money_columns.py`, `backend/tests/test_money_lint.py`
**Commit:** `4749920`
**Applied fix:** Refactored `_find_numeric_args` (now a `@classmethod`) into two parts: a `_parse_numeric_call` helper that extracts `(precision, scale)` from a `Numeric(...)` AST node, and an updated `_find_numeric_args` that scans both `call.args` (positional) and `call.keywords` (keyword args like `type_=Numeric(...)`) of `mapped_column`. Added two new test fixtures (`TYPE_KW_WRONG_FIXTURE` and `TYPE_KW_CORRECT_FIXTURE`) and corresponding tests `test_type_kw_wrong_numeric_fails` and `test_type_kw_correct_numeric_passes`.

---

### CR-05: `scrub_secrets` processor only scrubs top-level keys — nested secrets pass through

**Files modified:** `backend/app/core/logging.py`
**Commit:** `60a4842`
**Applied fix:** Implemented `_scrub_recursive(obj)` helper that walks dicts (any depth), lists, and scalars, replacing values for keys matching `SCRUB_KEYS`. `scrub_secrets` now calls `_scrub_recursive(dict(event_dict))`, clears the original mapping, and updates it with the scrubbed copy — preserving the `MutableMapping` contract required by structlog.

---

### CR-06: `gitleaks-action` pinned to mutable `@v2` floating tag in two CI workflows

**Files modified:** `.github/workflows/backend-ci.yml`, `.github/workflows/security.yml`
**Commit:** `18d9a8b`
**Applied fix:** Updated `gitleaks/gitleaks-action@v2` to `gitleaks/gitleaks-action@v2.3.9` in both CI workflow files. This pins to an immutable version tag, preventing supply-chain compromise via a force-pushed mutable tag.

---

### WR-01: `Settings()` instantiated per-request/per-task in five hot paths

**Files modified:** `backend/app/core/config.py`, `backend/app/core/redis.py`, `backend/app/core/audit/service.py`, `backend/app/core/audit/models.py`, `backend/app/core/feature_flags/service.py`, `backend/app/core/feature_flags/models.py`
**Commit:** `17af91d`
**Applied fix:** Added `get_settings()` with `@lru_cache(maxsize=1)` to `config.py`. Replaced all five bare `Settings()` call sites in hot paths with `get_settings()`, updating imports accordingly. The cache is transparent to tests (which call `Settings()` directly or use `monkeypatch`).

---

### WR-02: `AsyncSession(bind=conn)` uses deprecated keyword — breaks on SQLAlchemy 2.1+

**Files modified:** `backend/tests/conftest.py`
**Commit:** `149187f` (combined with CR-02)
**Applied fix:** Changed `AsyncSession(bind=conn, expire_on_commit=False)` to `AsyncSession(conn, expire_on_commit=False)` — connection passed positionally per SQLAlchemy 2.x documentation.

---

### WR-03: Beat service healthcheck window is half the interval — one jitter event fails it

**Files modified:** `docker-compose.yml`
**Commit:** `f04952e`
**Applied fix:** Changed `-mmin -1` to `-mmin -2` in the beat healthcheck `test` command. This gives a 90-second window (3x the 30-second heartbeat interval), surviving a single delayed heartbeat without triggering a false health failure. The `start_period: 60s` was already present in the file.

---

### WR-04: Frontend Sentry initialised with empty-string DSN

**Files modified:** `frontend/src/instrumentation.ts`, `frontend/src/instrumentation-client.ts`
**Commit:** `d066c96`
**Applied fix:** In both files, extracted `const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN` and wrapped `Sentry.init(...)` in `if (dsn) { ... }`. This mirrors the backend's `if not settings.SENTRY_DSN: return` guard and prevents the SDK from entering an error state when `NEXT_PUBLIC_SENTRY_DSN` is empty or unset.

---

### WR-05: `AuditLog.id` has no Python-side default — `row.id` is `None` until DB flush returns

**Files modified:** `backend/app/core/audit/models.py`, `backend/tests/core/test_audit_immutability.py`
**Commit:** `bc0214a`
**Applied fix:** Added `from uuid import UUID as PyUUID, uuid4` import and `default=uuid4` to `AuditLog.id`'s `mapped_column`. The `server_default=func.gen_random_uuid()` is preserved for raw SQL inserts. Added `assert row.id is not None` assertion to `test_audit_service_record` to cover this regression path.

---

### WR-06: `downgrade()` will fail with FK constraint errors once Phase 2+ references `audit_log`

**Files modified:** `backend/alembic/versions/0001_phase1_foundations.py`
**Commit:** `37729b1`
**Applied fix:** Replaced `op.drop_table("audit_log")` with `op.execute("DROP TABLE IF EXISTS audit_log CASCADE;")` in `downgrade()`. Added a docstring explaining the cascade behaviour and noting that `feature_flags` drop order may need adjustment in future phases if downstream FKs reference it.

---

### WR-07: `test_gitleaks_fires_on_synthetic_fixture` does not assert exit code

**Files modified:** `backend/tests/test_gitleaks_blocks_secret.py`
**Commit:** `62a01de`
**Applied fix:** Changed `_run_gitleaks(...)` call from discarding the return value to destructuring it as `exit_code, stdout, stderr = _run_gitleaks(...)`. Added `assert exit_code == 1` with a descriptive message including both stdout and stderr to aid debugging when gitleaks exits with an unexpected code.

---

_Fixed: 2026-05-26T20:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
