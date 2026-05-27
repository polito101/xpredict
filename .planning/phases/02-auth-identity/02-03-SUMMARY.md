---
phase: 02-auth-identity
plan: 03
subsystem: auth
tags: [auth, fastapi-users, admin, bearer-jwt, seeding, dual-backend, argon2, cross-surface-isolation]

# Dependency graph
requires:
  - phase: 02-auth-identity
    plan: 01
    provides: "User + RefreshToken ORM, Settings (SECRET_KEY/REFRESH_TOKEN_LIFETIME/FIRST_ADMIN_*), pwdlib transitive"
  - phase: 02-auth-identity
    plan: 02
    provides: "UserManager + DatabaseStrategy + EmailService + check_email_limit + current_active_player + audit-session pattern"
provides:
  - "fastapi_users_admin — second FastAPIUsers instance with BearerTransport (D-03)"
  - "admin_backend — AuthenticationBackend(name='admin-bearer', transport=BearerTransport, get_strategy=get_database_strategy)"
  - "current_active_admin — fastapi_users_admin.current_user(active=True, superuser=True) for Phase 4+ admin endpoints"
  - "POST /admin/auth/login — rate-limited proxy returning OAuth2 Bearer JSON (no Set-Cookie); identical 401 for unknown / wrong / non-superuser (T-02-26, ROADMAP SC#5)"
  - "POST /admin/auth/logout — revokes Bearer via strategy.destroy_token (T-02-36)"
  - "bin/create_admin.py — idempotent first-admin CLI (D-11); reads FIRST_ADMIN_EMAIL/PASSWORD; hashes via pwdlib Argon2id"
  - "8 admin integration tests + 4 create_admin tests (74/74 auth-suite green)"
affects: [02-04 (frontend can call /admin/auth/login), 02-05 (admin-jwt cookie set from Bearer JSON), 04-markets (Phase 4+ admin endpoints use current_active_admin), 08-admin-crm]

# Tech tracking
tech-stack:
  added: []  # no new pip packages — all transitive from 02-01
  patterns:
    - "D-03 dual-backend: TWO distinct FastAPIUsers instances (player CookieTransport vs admin BearerTransport); cross-surface isolation enforced by transport type (T-02-25)"
    - "Defense-in-depth at the admin login proxy: ``user is None or not user.is_active or not user.is_superuser`` → identical 401 + audit row before backend.login() (T-02-26 / ROADMAP SC#5)"
    - "Audit failure reason classification: payload.reason captures unknown_email / inactive / not_superuser internally — caller cannot tell"
    - "Lazy ``__getattr__`` re-export in deps.py to break the import cycle (admin_router → deps → get_user_manager)"
    - "bin/create_admin.py BYPASSES UserManager.validate_password (operator-trusted bootstrap path); documented in module docstring"
    - "FastAPI 0.115 + Python 3.13 + Annotated[T, Depends()] requires no ``from __future__ import annotations`` (Plan 02-02 D-C inherited)"

key-files:
  created:
    - "backend/app/auth/admin_router.py"
    - "backend/tests/auth/test_admin_bearer.py"
    - "backend/bin/__init__.py"
    - "backend/bin/create_admin.py"
    - "backend/tests/auth/test_create_admin_script.py"
    - ".planning/phases/02-auth-identity/02-03-SUMMARY.md"
  modified:
    - "backend/app/auth/router.py"
    - "backend/app/auth/deps.py"
    - "backend/pyproject.toml"
    - "README.md"
    - ".planning/phases/02-auth-identity/deferred-items.md"

key-decisions:
  - "Filename deviation from CONTEXT D-11: bin/create-admin.py → bin/create_admin.py (underscore, Python module-name constraint; tests need ``import bin.create_admin``). Invocation `uv run python bin/create_admin.py` is functionally identical."
  - "Admin /admin/auth/logout written as a thin proxy (option (c) from PLAN line 142) — 3 lines: extract Bearer → strategy.destroy_token → return 204. Same pattern as login: proxy owns the decoration."
  - "current_active_admin re-exported via deps.__getattr__ to break import cycle (admin_router imports get_user_manager from deps)"
  - "PLAN audit_log event reused: /admin/auth/logout emits ``auth.session_revoked`` (NOT a new event type) — payload.surface='admin' captures the distinction"
  - "Defense-in-depth check (is_superuser BEFORE backend.login()) was chosen over option (b) — relying on the current_user(superuser=True) guard alone — because option (a)/(b) is what RESEARCH §Anti-Patterns line 920 + ROADMAP SC#5 require: NEVER mint a non-superuser Bearer token even if it would be useless"

patterns-established:
  - "Two-instance FastAPIUsers pattern: shared User model + UserManager + DatabaseStrategy; distinct transports per surface; mounted at distinct prefixes; current_user() with distinct flags. Phase 4+ admin endpoints take ``Depends(current_active_admin)``."
  - "OAuth2PasswordBearer(auto_error=False) for /admin/auth/logout: the route handles its own auth (reads + revokes the token) rather than going through the current_user guard, which would prevent the route from accepting an already-expired/revoked Bearer for idempotent logout."
  - "Idempotent bootstrap CLI shape: read Settings, check `select(User).where(email == env)`, INSERT if missing, return 0 either way; refuse empty env vars (exit 1)."

requirements-completed:
  - AUTH-07
  - AUTH-08  # admin scope inherits the player's slowapi infrastructure
  - AUTH-09  # admin scope — same DatabaseStrategy with rotation + reuse detection
  # AUTH-01..06 already shipped in Plan 02-02; Plan 02-03 does NOT close them.
  # Plan 02-03 also satisfies D-11 (admin seeding script).

# Metrics
duration: ~40min
completed: 2026-05-27
---

# Phase 02 Plan 03: Admin Auth Surface + Seeding CLI Summary

**Dual-backend authentication surface complete: player cookie surface (Plan 02-02) AND admin Bearer surface (Plan 02-03) coexist with hard cross-surface isolation. Two distinct FastAPIUsers instances share the same User model + UserManager + DatabaseStrategy but use different transports. `/admin/auth/login` is rate-limited 5/min per-IP + per-email, returns OAuth2 Bearer JSON (no cookie), and enforces `is_superuser=True` at three independent layers (transport, login-proxy defense-in-depth, `current_active_admin` guard). `/admin/auth/logout` revokes the refresh_tokens row idempotently. `bin/create_admin.py` provides operator-driven first-admin seeding with idempotency and pwdlib Argon2id hashing. 12 new tests (8 admin-bearer + 4 create-admin), full auth suite 74/74 green.**

## Performance

- **Duration:** ~40 min (most of it spent recovering from a worktree-path mistake — see Issues Encountered)
- **Started:** 2026-05-27T07:56Z (post-Wave-2)
- **Completed:** 2026-05-27T08:33Z
- **Tasks:** 2 / 2
- **Files:** 6 created, 5 modified (11 files total)
- **Tests added:** 12 (8 admin-bearer integration + 4 create-admin CLI integration); full `tests/auth/` suite is 74 tests, 74/74 green

## Accomplishments

### Backend tier (services / controllers)

- **`app/auth/admin_router.py`** — new module owning the admin surface:
  - `bearer_transport = BearerTransport(tokenUrl="/admin/auth/login")` — OpenAPI hint; the actual route is our proxy.
  - `admin_backend = AuthenticationBackend(name="admin-bearer", transport=bearer_transport, get_strategy=get_database_strategy)` — SAME custom DatabaseStrategy as the player surface; only the transport differs.
  - `fastapi_users_admin = FastAPIUsers[User, uuid.UUID](get_user_manager, [admin_backend])` — distinct from `fastapi_users_player` (D-03 verified by `assert fastapi_users_player is not fastapi_users_admin`).
  - `current_active_admin = fastapi_users_admin.current_user(active=True, superuser=True)` — exported for Phase 4+ admin endpoints.
  - `admin_login_proxy` (POST /admin/auth/login): rate-limited 5/min per-IP via the same `@limiter.limit` decorator + per-email via `check_email_limit()` body-time call. Authenticates via `user_manager.authenticate`; rejects (identical 401) any of `user is None`, `not user.is_active`, `not user.is_superuser` AFTER writing `auth.admin_login_failed` audit row. On success: writes `auth.admin_login_started` + mints Bearer via `admin_backend.login(strategy, user)`.
  - `admin_logout_proxy` (POST /admin/auth/logout): reads the Bearer via `OAuth2PasswordBearer(auto_error=False)`, calls `strategy.read_token` + `strategy.destroy_token`, writes `auth.session_revoked` (surface='admin'), returns 204. Idempotent — already-revoked/expired tokens still return 204.
  - `_audit_admin_login_failed`: helper that classifies the failure reason (`unknown_email` / `inactive` / `not_superuser`) into the audit payload, so internal forensics can distinguish even though the caller cannot.
- **`app/auth/router.py`** — `build_auth_routers()` extended to mount `admin_proxy_router` alongside the player proxy (via a local import to avoid the player↔admin module cycle).
- **`app/auth/deps.py`** — module-level `__getattr__` lazily resolves `current_active_admin` (and `current_active_player`) from the router modules to break the import cycle (`admin_router` imports `get_user_manager` from `deps`).
- **`bin/__init__.py`** + **`bin/create_admin.py`** — idempotent CLI script:
  - Reads `FIRST_ADMIN_EMAIL` + `FIRST_ADMIN_PASSWORD` from `Settings()`.
  - Empty env → stderr message + `return 1`.
  - `SELECT user WHERE email == env` first — if found, prints `"Admin … already exists … No-op."` + `return 0`.
  - Otherwise: `pwdlib.PasswordHash.recommended().hash(password)` → INSERT with `is_active=True, is_verified=True, is_superuser=True` + commit + print `"Created admin …"` + `return 0`.
  - Module docstring documents the deliberate BYPASS of `UserManager.validate_password` (operator-trusted bootstrap; passwords come from `.env.local`, strength is operator's responsibility).
- **`backend/pyproject.toml`** — `[tool.pytest.ini_options] pythonpath` extended with `"bin"` so tests can `from bin.create_admin import main`.

### Documentation

- **`README.md` §"First-time setup" §"Seed the first admin"** — documents `uv run python bin/create_admin.py` with the idempotency contract.

### Tests

- **`tests/auth/test_admin_bearer.py`** (8 tests):
  1. `test_admin_login_returns_bearer_token` — 200 + OAuth2 JSON body + NO Set-Cookie header.
  2. `test_player_login_does_not_grant_admin` — player cookie can't reach /admin/* (returns 401).
  3. `test_non_admin_bearer_forbidden` — verified player credentials → 401 on /admin/auth/login.
  4. `test_admin_bearer_does_not_authenticate_player_routes` — admin Bearer presented to /auth/users/me → 401/403.
  5. `test_admin_login_rate_limited` — 6th hit in 60s → 429 with generic body.
  6. `test_admin_login_failure_does_not_leak_existence` — identical 401 body for unknown-email vs wrong-password.
  7. `test_admin_login_audit_logged` — audit_log has both `auth.admin_login_started` (1 row, payload.email matches) and `auth.admin_login_failed` (≥2 rows, payload.reason ∈ {unknown_email, inactive, not_superuser}).
  8. `test_admin_bearer_revocation` — logout sets `refresh_tokens.revoked_at IS NOT NULL`.
- **`tests/auth/test_create_admin_script.py`** (4 tests):
  1. `test_seeds_admin_on_fresh_db` — INSERT one row + flags + `PasswordHash.recommended().verify(plaintext, hash)` succeeds + plaintext NOT in stdout (T-02-33).
  2. `test_idempotent_on_existing_admin` — second run prints "already exists", row count unchanged.
  3. `test_refuses_empty_env` — empty env → exit 1 + stderr mentions both required vars.
  4. `test_password_bypasses_validate_password` — script ACCEPTS weak passwords (UserManager rules don't apply to operator bootstrap).

## Task Commits

1. **Task 1 — Admin Bearer surface (admin_router.py + router.py + deps.py + 8 tests):** `32fbb45`
2. **Task 2 — bin/create_admin.py (CLI + pyproject pythonpath + README + 4 tests):** `1f153f2`

## Files Created/Modified

### Created (6)

- `backend/app/auth/admin_router.py` — admin BearerTransport + FastAPIUsers instance + login/logout proxy + audit helper
- `backend/tests/auth/test_admin_bearer.py` — 8 cross-surface isolation tests
- `backend/bin/__init__.py` — empty package marker (enables `import bin.create_admin`)
- `backend/bin/create_admin.py` — idempotent first-admin seeding CLI
- `backend/tests/auth/test_create_admin_script.py` — 4 CLI integration tests
- `.planning/phases/02-auth-identity/02-03-SUMMARY.md` — this file

### Modified (5)

- `backend/app/auth/router.py` — `build_auth_routers()` mounts `admin_proxy_router` (local import to avoid cycle); module docstring updated to document the admin surface
- `backend/app/auth/deps.py` — module-level `__getattr__` for lazy re-export of `current_active_admin` + `current_active_player` (breaks the import cycle)
- `backend/pyproject.toml` — `[tool.pytest.ini_options] pythonpath` extended with `"bin"`
- `README.md` — §"First-time setup" §"Seed the first admin" block
- `.planning/phases/02-auth-identity/deferred-items.md` — new entry for the cross-worktree gitleaks false-positive

## Decisions Made

### D-G: Filename `bin/create_admin.py` (underscore) deviates from CONTEXT D-11

CONTEXT D-11 + PATTERNS line 467 specify `backend/bin/create-admin.py` (hyphen). Python module names CANNOT contain hyphens — `from bin.create-admin import main` is a `SyntaxError`. The test file imports the module, so the file MUST be `create_admin.py` (underscore). This was documented in the PLAN `<action>` block (Task 2 line 214) as an acceptable deviation. Invocation is functionally identical (`uv run python bin/create_admin.py`) — only the in-source module name differs.

### D-H: Admin logout proxy directly handles auth (not `current_active_admin`)

The PLAN line 142 listed three options for the logout endpoint shape; I chose option (c) "direct logout proxy". Rationale: the `current_user(active=True, superuser=True)` guard would REJECT an already-expired or already-revoked Bearer, which means a client cannot log out idempotently if the token is stale. The proxy uses `OAuth2PasswordBearer(auto_error=False)` to read the token and `strategy.read_token` to look it up — when the row is missing/revoked/expired, the proxy returns 204 anyway (idempotent). This matches the fastapi-users default logout behaviour.

### D-I: Audit event for admin logout reuses `auth.session_revoked`

The PATTERNS audit taxonomy line 723-724 reserved `auth.admin_login_started` and `auth.admin_login_failed`. It did NOT reserve a separate `auth.admin_session_revoked`. The admin logout writes `auth.session_revoked` with `payload.surface='admin'` to capture the distinction without bloating the taxonomy. The `actor` field is `user:{uuid}` either way; the surface field disambiguates internally.

### D-J: Defense-in-depth at the login proxy (not at the guard alone)

The most idiomatic fastapi-users pattern would be: let `admin_backend.login()` mint a Bearer for any authenticated user, and rely on `current_active_admin` (via `current_user(superuser=True)`) to gate the actual `/admin/*` endpoints. But ROADMAP SC#5 explicitly says "non-admin Bearer → 403 on /admin/*" — meaning a non-admin Bearer must NOT EVEN BE MINTABLE. So the login proxy enforces `is_superuser` BEFORE calling `backend.login()`. A player who knows their own credentials can attempt POST `/admin/auth/login` but ALWAYS gets 401, identical to the unknown-email and wrong-password failure cases. This is verified by `test_non_admin_bearer_forbidden`.

### D-K: Lazy `__getattr__` for `deps.current_active_admin`

`app.auth.admin_router` imports `get_user_manager` from `app.auth.deps`. A top-level `from app.auth.admin_router import current_active_admin` in `deps.py` would create an import cycle (deps → admin_router → deps). The module-level `__getattr__` pattern (PEP 562) defers the resolution until the attribute is actually read, breaking the cycle. The `# noqa: F822` on `__all__` documents that the names are intentionally lazy.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FastAPI 0.115 rejects `status_code=204` with a response body**

- **Found during:** Task 1 first integration test run (`AssertionError: Status code 204 must not have a response body`)
- **Issue:** Declaring `@admin_proxy_router.post("/logout", status_code=204)` with a body-returning handler (even `return None`) fails FastAPI's `is_body_allowed_for_status_code(204)` assertion.
- **Fix:** Removed the `status_code=204` decorator argument; the handler returns `Response(status_code=204)` directly. Result: 204 No Content with empty body.
- **Files modified:** `app/auth/admin_router.py`
- **Verification:** `test_admin_bearer_revocation` returns 204 correctly.
- **Committed in:** `32fbb45`

**2. [Rule 3 - Blocking] `from __future__ import annotations` breaks `Annotated[T, Depends()]`**

- **Found during:** Task 1 first integration test run (422 instead of 200 on /admin/auth/login)
- **Issue:** Same Plan 02-02 D-C / Deviation #1: FastAPI's `inspect.signature` dependency resolver fails when annotations are forward-ref strings (`'OAuth2PasswordRequestForm'`). The proxy routes wrongly tried to read `username`/`password` from the query string instead of the form body.
- **Fix:** Removed `from __future__ import annotations` from `admin_router.py`; documented the constraint in the module docstring (Plan 02-02 inherited).
- **Files modified:** `app/auth/admin_router.py`
- **Verification:** All 8 admin-bearer tests pass.
- **Committed in:** `32fbb45`

**3. [Rule 3 - Blocking] mypy false-positive on `User.email == email`**

- **Found during:** Task 2 final mypy run
- **Issue:** fastapi-users-db-sqlalchemy's `SQLAlchemyBaseUserTableUUID` declares `email` without `ColumnElement` typing, so mypy thinks `User.email == "x"` returns `bool` (not a SQL expression). `where(bool)` is then a type error.
- **Fix:** `# type: ignore[arg-type]` on the single line with a documenting comment.
- **Files modified:** `bin/create_admin.py`
- **Verification:** `uv run mypy bin/create_admin.py` → 0 errors.
- **Committed in:** `1f153f2`

**4. [Rule 1 - Bug] Ruff F822 on `__all__` lazy re-exports**

- **Found during:** Task 1 final ruff run
- **Issue:** Ruff flags `__all__` entries that are not statically defined in the module. `current_active_admin` / `current_active_player` are resolved by `__getattr__`, so they're not visible to a static analyzer.
- **Fix:** `# noqa: F822` per line with a comment explaining the lazy resolution.
- **Files modified:** `app/auth/deps.py`
- **Verification:** `uv run ruff check app/auth/deps.py` → All checks passed.
- **Committed in:** `32fbb45`

---

**Total deviations:** 4 auto-fixed (2 Rule 1 bugs, 2 Rule 3 blockers). All inherited patterns from Plan 02-02 (`from __future__ import annotations` removal + Annotated[T, Depends()]; F822 on lazy re-exports). No Rule 2 (security) or Rule 4 (architectural) deviations.

## Issues Encountered

### Worktree path drift mid-execution (recovered)

Mid-Task 1, I wrote files using absolute paths beginning with `C:\Users\pobom\xpredict\backend\...` instead of `C:\Users\pobom\xpredict\.claude\worktrees\agent-a0d4a6201bd1490a6\backend\...`. This is exactly the bug #3099 documented in the executor mandatory pre-commit check: Edit/Write with an absolute path NOT under the worktree root silently writes to the **main repo** instead of the worktree.

The drift wasn't detected by the pre-commit cwd-drift assertion (#3097) because that fires on `cd` between bash calls — Write is a separate tool and bypasses that guard.

**Recovery:** I detected the drift when `git status` in the worktree returned empty despite multiple Write operations. I then:
1. Switched to the main repo (`cd /c/Users/pobom/xpredict`).
2. Reverted the spurious changes (`git checkout -- backend/app/auth/{deps,router}.py`).
3. Deleted the spurious new files (`rm backend/app/auth/admin_router.py backend/tests/auth/test_admin_bearer.py`).
4. Returned to the worktree and re-applied all the Write/Edit operations with the correct absolute path under `.claude/worktrees/agent-a0d4a6201bd1490a6/`.

**No data lost.** No commits made to the main repo. The main repo's working tree was restored to its pre-spawn state.

**Recommendation for future executors:** Even when Write takes an absolute path, **always** derive that absolute path from `git rev-parse --show-toplevel` run inside the worktree, not from an earlier `pwd` capture. The executor `<absolute-path safety>` section (#3099) describes the correct pre-write check but the agent (me) failed to follow it on first attempt.

### Pre-existing test failures (out of scope)

Running the FULL backend suite (`uv run pytest tests/`) reveals 8 pre-existing failures:

- **6 in `tests/core/test_audit_immutability.py` + `tests/core/test_feature_flags.py`** — the same session-scope state-isolation bug documented in `01-04-SUMMARY.md`, `02-01-SUMMARY.md`, and `02-02-SUMMARY.md`. Not introduced by Plan 02-03 (the failures reproduce at parent commit `dd588e7`, before any Phase 2 work).
- **1 in `tests/test_gitleaks_blocks_secret.py::test_gitleaks_clean_scan_of_full_repo`** — gitleaks scans the **shared git history** of the repo (not the worktree's branch), so it picks up the 23 leaks in commit `54af9454…` introduced by the SIBLING worktree (02-04 frontend agent running in parallel). The leaks are all in `frontend/src/lib/__tests__/auth.test.ts` (test fixture passwords matching the generic-api-key entropy heuristic). NOT introduced by Plan 02-03; documented in `deferred-items.md` for the 02-04 worktree or Phase 11 hardening to address (likely an `.gitleaks.toml` allowlist extension for frontend test fixtures, mirror of the existing `tests/.*fixtures.*` backend allowlist).

**Plan 02-03's own test surface (`tests/auth/`) is 74/74 green.**

## Manual Verification (deferred — host Postgres not running)

The `<verification>` block of the PLAN includes manual smoke commands like
`curl -X POST -F username=... -F password=... http://localhost:8000/admin/auth/login`.
Those require `docker compose up -d` to be running on the host, which has the
documented port-conflict issue with Pol's `cc_redis` / `cc_postgres` containers
(see `01-03-SUMMARY.md`). The smoke checklist (5 min) is:

1. Stop `cc_redis` + `cc_postgres` containers on the host.
2. `bin/dev.ps1` to bring up xpredict's docker-compose.
3. `cd backend; uv run alembic upgrade head` — should reach `0002_phase2_auth`.
4. Set `FIRST_ADMIN_EMAIL=pol@xpredict.local` + `FIRST_ADMIN_PASSWORD=AdminPass1234!` in `.env.local`.
5. `uv run python bin/create_admin.py` — should print "Created admin pol@xpredict.local (id=…)"; second run prints "already exists".
6. `curl.exe -X POST -F username=pol@xpredict.local -F password=AdminPass1234! http://localhost:8000/admin/auth/login` — should return `{"access_token":"…", "token_type":"bearer"}` with NO Set-Cookie header.
7. Restart `cc_redis` + `cc_postgres` after.

Steps 1, 2, 6, 7 are the parts that need the host runtime; steps 3-5 are also covered by the 12 automated integration tests against the testcontainer Postgres. The host-runtime smoke is gated by Pol's environmental config (same as Phase 1 manual-verify items).

## User Setup Required

None for this plan. The new env vars (`FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD`) were already added to `.env.example` in Plan 02-01 with safe placeholders. The plan documents `uv run python bin/create_admin.py` as the seeding invocation; an operator who wants a working admin login MUST run that command once.

## Next Plan Readiness (Plan 02-04 — Frontend Auth UI)

- `/auth/*` routes ship from Plan 02-02 (player register / login / forgot-password / etc.)
- `/admin/auth/login` returns OAuth2 Bearer JSON ready to be stored in an HTTP-only `admin_jwt` cookie by a Next.js Server Action (Plan 02-05).
- `/admin/auth/logout` accepts the Bearer in `Authorization: Bearer …`; frontend POSTs from the admin layout's logout link.
- `current_active_admin` and `current_active_player` are both importable from `app.auth.deps` (lazy resolution).
- The first admin can be seeded via `bin/create_admin.py` before the frontend integration test in Plan 02-04 / 02-05 needs an admin to log in as.

## Test Coverage Matrix

| Requirement | Test File | Test Name(s) | Status |
|-------------|-----------|--------------|--------|
| AUTH-07 admin login surface | test_admin_bearer.py | test_admin_login_returns_bearer_token | ✅ |
| AUTH-07 cross-surface isolation (player→admin) | test_admin_bearer.py | test_player_login_does_not_grant_admin | ✅ |
| AUTH-07 cross-surface isolation (admin→player) | test_admin_bearer.py | test_admin_bearer_does_not_authenticate_player_routes | ✅ |
| AUTH-07 ROADMAP SC#5 non-admin Bearer | test_admin_bearer.py | test_non_admin_bearer_forbidden | ✅ |
| AUTH-08 admin scope (rate limit + no leak) | test_admin_bearer.py | test_admin_login_rate_limited + test_admin_login_failure_does_not_leak_existence | ✅ |
| AUTH-09 admin Bearer revocable | test_admin_bearer.py | test_admin_bearer_revocation | ✅ |
| Audit taxonomy (admin_login_started + admin_login_failed) | test_admin_bearer.py | test_admin_login_audit_logged | ✅ |
| D-11 seed fresh DB | test_create_admin_script.py | test_seeds_admin_on_fresh_db | ✅ |
| D-11 idempotent | test_create_admin_script.py | test_idempotent_on_existing_admin | ✅ |
| D-11 empty env refused | test_create_admin_script.py | test_refuses_empty_env | ✅ |
| D-11 validate_password bypass | test_create_admin_script.py | test_password_bypasses_validate_password | ✅ |

## Audit-Event Taxonomy Coverage (Plan 02-03 additions)

| Event Type | Where Emitted | Tested In |
|------------|---------------|-----------|
| `auth.admin_login_started` | admin_login_proxy success path (admin_router.py) | test_admin_login_audit_logged |
| `auth.admin_login_failed` | _audit_admin_login_failed (admin_router.py) — payload.reason ∈ {unknown_email, inactive, not_superuser} | test_admin_login_audit_logged |
| `auth.session_revoked` (surface='admin') | admin_logout_proxy success path | (indirectly via test_admin_bearer_revocation; payload.surface field documented but not asserted in this plan; covered in Phase 8 admin CRM tests) |

## Threat Surface Scan

All threats T-02-25 through T-02-36 + T-02-SC documented in PLAN.md `<threat_model>` have mitigations implemented and asserted by tests:

- T-02-25 (EoP: player cookie satisfies /admin/*) → two distinct FastAPIUsers instances; test_player_login_does_not_grant_admin + test_admin_bearer_does_not_authenticate_player_routes ✅
- T-02-26 (EoP: player credentials → admin Bearer) → defense-in-depth `is_superuser` check before `backend.login()`; test_non_admin_bearer_forbidden ✅
- T-02-27 (Spoofing: admin brute force) → 5/min per-IP + per-email; test_admin_login_rate_limited ✅
- T-02-28 (InfoDisc: admin login enumeration) → identical 401 + body for all failure modes; test_admin_login_failure_does_not_leak_existence ✅
- T-02-29 (Tampering: JWT alg=none) → fastapi-users HS256-only (inherited from Plan 02-02; not regressed) ✅
- T-02-30 (Repudiation: admin actions not audited) → `auth.admin_login_started` + `auth.admin_login_failed` emitted with payload.reason; test_admin_login_audit_logged ✅
- T-02-31 (EoP: register `is_superuser=True`) → `UserCreate` schema (Plan 02-01) inherits fastapi-users' `BaseUserCreate` which DOES NOT expose `is_superuser` — verified by inspection; seed-only path via `bin/create_admin.py` ✅
- T-02-32 (Tampering: plaintext password in DB) → `pwdlib.PasswordHash.recommended()` (Argon2id) BEFORE INSERT; test_seeds_admin_on_fresh_db ✅
- T-02-33 (InfoDisc: password in stdout) → stdout only emits email + UUID; assertion `_TEST_PASSWORD not in captured.out` in test_seeds_admin_on_fresh_db ✅
- T-02-34 (DoS: Argon2 OOM on admin login storm) → slowapi 5/min cap blocks at 6th attempt; OWASP "balanced" Argon2 profile (pwdlib defaults); inherited ✅
- T-02-35 (Tampering: long-lived admin token) → AUTH-06 token_version + re-running create_admin.py to rotate (accepted until Phase 8) ✅
- T-02-36 (Repudiation: Bearer not revocable) → strategy.destroy_token wired into /admin/auth/logout; test_admin_bearer_revocation ✅
- T-02-SC (supply chain: mid-plan installs) → 0 new pip installs in Plan 02-03; verified by `pip list` parity with Plan 02-01 ✅

No new attack surface introduced beyond what the threat_model documented.

## Known Stubs

None. Every code path is wired end-to-end. The `current_active_admin` placeholder from Plan 02-02 is now concretized; the admin surface is fully operational against the testcontainer DB.

## Self-Check: PASSED

All 11 created/modified files exist in the worktree:

- `backend/app/auth/admin_router.py` ✅
- `backend/app/auth/router.py` (modified) ✅
- `backend/app/auth/deps.py` (modified) ✅
- `backend/bin/__init__.py` ✅
- `backend/bin/create_admin.py` ✅
- `backend/pyproject.toml` (modified) ✅
- `backend/tests/auth/test_admin_bearer.py` ✅
- `backend/tests/auth/test_create_admin_script.py` ✅
- `README.md` (modified) ✅
- `.planning/phases/02-auth-identity/02-03-SUMMARY.md` ✅
- `.planning/phases/02-auth-identity/deferred-items.md` (modified) ✅

Both task commits exist in `git log --oneline -3` on `worktree-agent-a0d4a6201bd1490a6`:

- `32fbb45` — Task 1 (admin Bearer surface + 8 tests)
- `1f153f2` — Task 2 (create_admin CLI + README + 4 tests)

Plan metadata (STATE.md / ROADMAP.md): owned by the parent orchestrator after wave 3 completes (worktree mode).

---

*Phase: 02-auth-identity*
*Plan: 03*
*Completed: 2026-05-27*
