---
phase: 02-auth-identity
reviewed: 2026-05-27T00:00:00Z
depth: standard
files_reviewed: 33
files_reviewed_list:
  - backend/alembic.ini
  - backend/alembic/env.py
  - backend/alembic/versions/0002_phase2_auth.py
  - backend/app/auth/admin_router.py
  - backend/app/auth/deps.py
  - backend/app/auth/email.py
  - backend/app/auth/manager.py
  - backend/app/auth/models.py
  - backend/app/auth/rate_limit.py
  - backend/app/auth/router.py
  - backend/app/auth/schemas.py
  - backend/app/auth/strategy.py
  - backend/app/core/config.py
  - backend/app/main.py
  - backend/bin/create_admin.py
  - backend/tests/auth/conftest.py
  - backend/tests/auth/test_admin_bearer.py
  - backend/tests/auth/test_create_admin_script.py
  - backend/tests/auth/test_email_enumeration.py
  - backend/tests/auth/test_login.py
  - backend/tests/auth/test_logout.py
  - backend/tests/auth/test_password_reset.py
  - backend/tests/auth/test_rate_limit.py
  - backend/tests/auth/test_refresh_rotation.py
  - backend/tests/auth/test_register.py
  - frontend/src/middleware.ts
  - frontend/src/lib/auth.ts
  - frontend/src/lib/auth-schemas.ts
  - frontend/src/app/(auth)/login/login-form.tsx
  - frontend/src/app/(auth)/register/register-form.tsx
  - frontend/src/app/(auth)/forgot-password/forgot-form.tsx
  - frontend/src/app/(auth)/reset-password/reset-form.tsx
  - frontend/src/app/admin/login/admin-login-form.tsx
  - frontend/src/app/admin/page.tsx
findings:
  critical: 5
  warning: 6
  info: 3
  total: 14
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-05-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 33
**Status:** issues_found

## Summary

Phase 2 implements the full auth & identity surface: FastAPI-Users dual-backend (Cookie for players, Bearer for admins), DatabaseStrategy with token-rotation and reuse-detection, rate-limiting via slowapi, email verification / password-reset via Resend/Mailpit, and a Next.js 15 frontend with Server Actions and edge middleware. The overall architecture is solid and reflects deliberate security design. However, five critical defects were found — three produce incorrect runtime behaviour that defeats stated security guarantees, and two produce silent failures or crashes in production configurations.

---

## Critical Issues

### CR-01: `on_after_reset_password` commits token_version bump but **does not flush the in-memory User object** — the calling fastapi-users transaction may persist the old version

**File:** `backend/app/auth/manager.py:195-218`

**Issue:**
`on_after_reset_password` opens its **own** session (via `audit_session_factory`) and issues an `UPDATE users SET token_version = token_version + 1`. This is correct for the DB row. The problem is that the `user` object passed into this hook by fastapi-users is already loaded in **the request's session** (the one that also sets the new `hashed_password`). When the request session is committed after the hook returns, SQLAlchemy may **write back the stale `token_version=0` from the in-memory object**, overwriting the just-committed bump, because the object was loaded before the bump and its `token_version` attribute still holds the old value.

This is a classic "lost update" pattern when two sessions race on the same row. In practice, because the request session commits *after* the manager hook, the request session's `UPDATE users SET hashed_password=... WHERE id=...` does not touch `token_version` (fastapi-users only updates `hashed_password`), so the bump survives **today**. But the correctness depends on fastapi-users internals never expanding the UPDATE to include `token_version`. The combination of `expire_on_commit=False` in the session factory and two sessions writing different columns of the same row is fragile. The test `test_reset_invalidates_sessions` passes only because fastapi-users happens not to include `token_version` in its UPDATE.

The belt-and-suspenders `strategy.read_token` version gate checks the **DB value** via a fresh `user_manager.get()` call, which re-queries the row — so even if the bump were lost, the strategy would use the stale version. This means both halves of the "belt-and-suspenders" claim depend on the same precarious ordering.

**Fix:** Perform the token_version bump in the **same** session that fastapi-users uses, not a side session. Override `on_after_reset_password` to accept the session via a context variable or move the bump into a SQLAlchemy event listener that fires after `hashed_password` is committed. Alternatively, reload the user inside the manager's hook session and confirm the row version matches before committing:

```python
async with self.audit_session_factory() as session:
    result = await session.execute(
        update(User)
        .where(User.id == user.id, User.token_version == user.token_version)
        .values(token_version=User.token_version + 1)
        .returning(User.token_version)
    )
    if result.rowcount == 0:
        # Concurrent bump — re-read and continue; log a warning
        ...
```

---

### CR-02: `middleware.ts` allows an **undefined `ADMIN_JWT_PUBLIC_SECRET`** to silently pass all admin requests through without verification

**File:** `frontend/src/middleware.ts:41-44`

**Issue:**
The non-null assertion `process.env.ADMIN_JWT_PUBLIC_SECRET!` suppresses TypeScript's check. If `ADMIN_JWT_PUBLIC_SECRET` is missing from the Next.js environment, `new TextEncoder().encode(undefined!)` produces a zero-length key. `jwtVerify` with a zero-length HS256 key will **reject the call** (jose throws `JWTInvalid` or `JOSEError`) — which means the `catch` block fires and the user is redirected to `/admin/login` rather than being let through. This is actually a fail-closed outcome, not a bypass.

However, the real risk is the **inverse configuration mistake**: `ADMIN_JWT_PUBLIC_SECRET` is set in the frontend env but its value does not match the backend `SECRET_KEY`. In that case:
- The middleware verifies the signature against the wrong secret → every admin JWT is rejected → legitimate admins are always redirected to login, creating a permanent lockout.
- There is no observable error — the `catch {}` swallows all `jwtVerify` errors including algorithm mismatches, invalid key errors, and genuine signature failures with an **identical redirect response**. An operator cannot tell from the UI whether the secret is misconfigured or whether the token is actually invalid.

The silent swallow of all errors in the `catch {}` block is a **debuggability blocker** and hides real misconfiguration.

**Fix:** Log the error (at minimum to the server console / Next.js edge runtime logs) before redirecting. Distinguish between `JWTExpired` (normal, redirect silently) and unexpected errors (log a warning). Guard against a missing secret at startup rather than at request time:

```typescript
// At module load — fail loudly if secret is absent
const rawSecret = process.env.ADMIN_JWT_PUBLIC_SECRET;
if (!rawSecret) {
  throw new Error("ADMIN_JWT_PUBLIC_SECRET is not set — admin middleware cannot function");
}
const ADMIN_SECRET = new TextEncoder().encode(rawSecret);

// In the handler
try {
  await jwtVerify(token, ADMIN_SECRET, { algorithms: ["HS256"] });
  return NextResponse.next();
} catch (err) {
  if (!(err instanceof Error && err.name === "JWTExpired")) {
    console.warn("[admin-middleware] jwt verification failed:", (err as Error).message);
  }
  return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url));
}
```

---

### CR-03: `admin_logout_proxy` is **not rate-limited** — unlimited token-lookup requests enable a brute-force timing oracle

**File:** `backend/app/auth/admin_router.py:183-224`

**Issue:**
`admin_login_proxy` is correctly decorated with `@limiter.limit("5/minute")`. `admin_logout_proxy` has **no `@limiter.limit` decorator** at all. Every call to `POST /admin/auth/logout` invokes `strategy.read_token(token, user_manager)`, which performs a DB lookup (`SELECT ... WHERE token_hash = :hash`). An adversary who can observe timing differences between "hash found, user resolved" and "hash not found" can use the unlimited logout endpoint to brute-force 64-character hex token hashes — slowly, but without any per-IP throttle stopping them.

Additionally, the logout endpoint accepts any Bearer token without requiring the caller to be authenticated first. Any unauthenticated party can send arbitrary token strings to `/admin/auth/logout` to probe the `refresh_tokens` table. While the response is 204 in both the "found + revoked" and "not found" cases, DB query timing can leak whether the hash exists.

**Fix:** Add the rate-limit decorator (same cap as login):

```python
@admin_proxy_router.post("/logout")
@limiter.limit("20/minute", key_func=get_remote_address)
async def admin_logout_proxy(
    request: Request,
    token: Annotated[str | None, Depends(_oauth2_bearer_scheme)],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> Response:
```

The same gap exists for `POST /auth/logout` on the player surface — fastapi-users' built-in logout route is mounted without a rate-limit decorator via `fastapi_users_player.get_auth_router(player_backend)`, and `_strip_proxy_owned` only strips `/login` (not `/logout`), so the built-in `/auth/logout` route is live and unthrottled.

---

### CR-04: `forwardSessionCookie` in `auth.ts` uses a **regex that matches partial cookie names** — a Set-Cookie header containing `my_xpredict_session=...` would be forwarded as the session cookie

**File:** `frontend/src/lib/auth.ts:72`

**Issue:**
The regex `/xpredict_session=([^;]+)/` has no word-boundary anchor. If the backend ever emits (or an attacker causes it to emit via a response-splitting vector) a cookie named `evil_xpredict_session`, the regex matches and the malicious value is stored as `xpredict_session` in the browser. More practically, a CDN or proxy that injects additional `Set-Cookie` headers could trigger this.

The pattern should match the cookie name at the start of the header value or after a `; ` separator:

```typescript
// Before
const match = setCookieHeader.match(/xpredict_session=([^;]+)/);

// After — anchor to start of value or after "; "
const match = setCookieHeader.match(/(?:^|;\s*)xpredict_session=([^;]+)/);
```

This is a lower-severity issue in isolation but represents a correctness gap that could be exploited via response manipulation.

---

### CR-05: `_mint_reset_token` in tests **re-hashes the already-hashed password** as the `password_fgpt` fingerprint, producing a token that does not match what fastapi-users actually generates

**File:** `backend/tests/auth/test_password_reset.py:63-73`

**Issue:**
The helper constructs the JWT payload as:
```python
"password_fgpt": password_helper.hash(user.hashed_password),
```

`user.hashed_password` is already an Argon2id digest. `password_helper.hash(...)` hashes it **again**, producing `argon2id(argon2id(plaintext))`. The fastapi-users source uses `password_helper.hash(user.hashed_password)` in the same way — so the two hashes **coincidentally agree** because fastapi-users also applies `.hash()` to the stored `hashed_password`. This means the test tokens actually verify correctly against `fastapi-users` `reset_password` endpoint today.

However, if fastapi-users changes the fingerprint algorithm (already done in some 14.x → 15.x migrations), or if the test is read by future developers as documentation of the correct token structure, the double-hash pattern is deeply confusing and incorrect as an explanation. The comment `"password_fgpt": password_helper.hash(user.hashed_password)` implies the fingerprint is a hash of the Argon2id digest, while the real intent is a hash of the stored (already-hashed) value — the naming is a lie.

More critically: `generate_jwt` is imported from `fastapi_users.jwt`, which is a **private / internal API** not guaranteed stable across patch versions. This test will break silently if fastapi-users changes `generate_jwt` internals or removes it. Production token minting is not tested through the legitimate `/auth/forgot-password` → parse email → extract token flow; instead, it fabricates tokens using private internals, making the test a false confidence signal.

**Fix:** Replace `_mint_reset_token` with a Mailpit-integrated flow: call `POST /auth/forgot-password`, read the email from Mailpit, extract the token from the reset URL. Add a `@pytest.mark.skipif(not mailpit_reachable, ...)` guard. For CI without Mailpit, use `UserManager.forgot_password` directly and capture the token from the hook via monkeypatching:

```python
captured_token: list[str] = []

async def mock_send_reset(*, to: str, token: str) -> None:
    captured_token.append(token)

monkeypatch.setattr(email_service, "send_reset_password_email", mock_send_reset)
await manager.forgot_password(user, request=None)
reset_token = captured_token[0]
```

---

## Warnings

### WR-01: `emailservice._send_via_resend` is called in staging/prod even when `RESEND_API_KEY` is `None` (no key → runtime crash)

**File:** `backend/app/auth/email.py:63-73`

**Issue:**
`EmailService.__init__` only sets `resend.api_key` when `not self.settings.is_dev and self.settings.RESEND_API_KEY`. The `send()` method dispatches to `_send_via_resend` when `not self.settings.is_dev` — **regardless of whether `RESEND_API_KEY` was set**. In staging/prod with a missing `RESEND_API_KEY`, `resend.Emails.send_async` will raise because the global `resend.api_key` was never populated. This produces an unhandled exception in the manager hooks (caught by the outer try/except, logged, and swallowed per Pitfall 5), meaning **all transactional emails silently fail in production** with no operator alert beyond a log line.

**Fix:** Add an explicit check in `send()` or raise at init time when not in dev mode and key is absent:

```python
async def send(self, *, to: str, subject: str, html: str) -> None:
    if self.settings.is_dev:
        await self._send_via_mailpit(to=to, subject=subject, html=html)
    elif self.settings.RESEND_API_KEY:
        await self._send_via_resend(to=to, subject=subject, html=html)
    else:
        raise RuntimeError(
            "RESEND_API_KEY is required in non-dev environments but was not set."
        )
```

---

### WR-02: `get_user_manager` dependency does not `commit()` after yielding — audit writes from `on_after_register` and `on_after_verify` may lose data on unhandled exceptions

**File:** `backend/app/auth/deps.py:58-63`

**Issue:**
`get_user_manager` yields a `UserManager` without wrapping in a try/finally or exception handler. If the route raises an unhandled exception **after** `on_after_register` has written an audit row (via `_audit` → independent session → `commit()`), the audit row is committed correctly. However, if `on_after_register` itself raises **before** its `await session.commit()` call (e.g. a DB constraint violation inside `AuditService.record`), the partial write is abandoned with no error surfaced to the caller. The `UserManager` also owns no session of its own through this dependency — all mutations go through the request-level session from `get_user_db`. If that session is not committed, writes (e.g. `is_verified=True`) are lost silently.

This is consistent with fastapi-users' own design, but `get_user_manager` does not call `session.commit()` at teardown the way `get_user_db` is expected to, relying entirely on fastapi-users' internal commit logic. The gap: if a future route uses `get_user_manager` for something that does not go through `fastapi_users_player.create_user(...)` but does mutate the DB via `user_manager`, there is no commit at teardown.

**Fix:** Document explicitly that `get_user_manager` is only safe when called from a fastapi-users-managed route. Add a comment to that effect so future phase authors don't use this dependency for custom mutations without adding their own commit.

---

### WR-03: `strategy.read_token` — the session is closed before `user_manager.get()` is called, but the `row` local variable holds references to ORM-mapped columns that are detached

**File:** `backend/app/auth/strategy.py:113-126`

**Issue:**
The session context manager `async with self.sessionmaker() as session:` exits at line 116 (after reading `row_token_version` and `row_user_id`). The explicit copy to local variables is correct for primitive values. However, `row` is a `RefreshToken` ORM instance that is now in a **detached state** — if any code between line 116 and line 121 accidentally accesses `row.user` (the relationship), SQLAlchemy would raise `DetachedInstanceError`. This is not currently triggered because `row` is not accessed after line 116, but the pattern is fragile. Future modifications to the function (e.g. adding a log line with `row.user.email`) will silently break.

**Fix:** Explicitly discard `row` after extracting the needed primitives, or add an `expire_on_commit=False` note:

```python
row_token_version = row.token_version
row_user_id = row.user_id
del row  # prevent accidental access after session close
```

---

### WR-04: `check_email_limit` accesses `limiter._limiter` — a private attribute — which breaks if slowapi changes its internal structure

**File:** `backend/app/auth/rate_limit.py:97`

**Issue:**
`limiter._limiter.hit(limit_item, key)` reaches into slowapi's private `_limiter` attribute (the underlying `limits` strategy instance). This is not part of slowapi's public API. The slowapi 0.5.x → 0.6.x transition renamed several internal attributes. If slowapi is updated, this call fails with `AttributeError` at runtime on the first request to any rate-limited endpoint, crashing authentication entirely.

**Fix:** Use the slowapi public API. The supported pattern is to call `limiter.hit()` or, if per-request manual invocation is needed, use `limits.storage.StorageErrors` directly bound to the storage URI. At minimum, add a startup check that validates the attribute exists:

```python
# In app lifespan or module load:
assert hasattr(limiter, "_limiter") and hasattr(limiter._limiter, "hit"), (
    "slowapi private API changed — update check_email_limit"
)
```

---

### WR-05: `create_admin.py` does not set `token_version` when constructing `User()` — the column defaults to `0` at the Python level but the ORM default is evaluated only when `session.flush()` is called; if `expire_on_commit=False`, the `admin.token_version` attribute may be `None` in the printed output

**File:** `backend/bin/create_admin.py:80-90`

**Issue:**
```python
admin = User(
    id=uuid4(),
    email=email,
    hashed_password=helper.hash(password),
    is_active=True,
    is_verified=True,
    is_superuser=True,
)
```

`token_version` is not supplied. The ORM `default=0` means it will be `0` after `session.flush()`, which is correct. However, `display_name` and `banned_at` are also absent — `display_name` is nullable and defaults to `None`, so that's fine. The concern is that if `expire_on_commit=True` (the session factory default), after `session.commit()` the object's attributes are expired; `print(f"Created admin {email} (id={admin.id})")` re-loads `admin.id` from the DB, which triggers a SELECT. This SELECT will fail with `MissingGreenlet` / `ProgrammingError` because the session is already closed after the `async with` block exits. In practice, `admin.id` was set explicitly so it is not expired — but this is a non-obvious coupling.

**Fix:** Access `admin.id` **before** the `async with` block exits, or capture it in a local variable:

```python
admin_id = admin.id
await session.commit()
print(f"Created admin {email} (id={admin_id})")
```

---

### WR-06: `conftest.py` fixture cleanup uses `delete(User).where(User.id == user.id)` but does **not** commit — relies on `async_session.flush()` to propagate

**File:** `backend/tests/auth/conftest.py:92-93`, `116-117`, `140-141`

**Issue:**
The `finally` blocks in `verified_user`, `unverified_user`, and `admin_user` call `await async_session.flush()` after the DELETE, not `await async_session.commit()`. Because these fixtures are `loop_scope="session"` and share the same `async_session` that is wrapped in an outer transaction (the session-scoped rollback pattern), flushing sends the DELETE to the DB but does not commit it. This is intentional for rollback-based test isolation. However, if the `async_session` transaction is never rolled back (e.g. test runner terminates abnormally), the user rows are left in the DB, causing unique-email violations on the next test run.

More critically, if any test in the session uses `engine` directly (which operates outside the `async_session` transaction) and queries the user rows, the session-scoped fixture rows are visible to those tests because the flush propagated them. Tests that clean up via `engine` (e.g. `test_refresh_rotation.py`) will silently interfere with fixtures from `conftest.py` if the emails collide.

**Fix:** Document that `conftest.py` fixture users must use email addresses that cannot collide with emails used in direct-engine tests. Add email prefixes like `fixture-verified@example.com` (distinct from `verified@example.com`). Alternatively, use `await async_session.commit()` in the finally block and explicitly re-open a transaction.

---

## Info

### IN-01: `main.py` constructs `Settings()` at module level bypassing `get_settings()` cache

**File:** `backend/app/main.py:46`

**Issue:**
`settings = Settings()` creates a fresh `Settings` instance unconditionally at module import. `get_settings()` in `config.py` uses `@lru_cache(maxsize=1)` to return a singleton. The two instances will read the same environment variables and produce equal values, but they are separate objects. Tests that call `get_settings.cache_clear()` and `monkeypatch` env vars will correctly invalidate the `get_settings` singleton — but `main.settings` is captured at import time and will not reflect the new env vars. This can cause subtle test failures where `settings.is_dev` in `main.py` returns `True` (dev default) while a monkeypatched `get_settings()` returns a staging/prod instance.

**Fix:** Replace `settings = Settings()` with `settings = get_settings()` at line 46, importing `get_settings` from `app.core.config`:

```python
from app.core.config import get_settings
settings = get_settings()
```

---

### IN-02: HTML email templates use raw f-string `.format()` — tokens containing `{` or `}` would produce `KeyError` / corrupt HTML

**File:** `backend/app/auth/email.py:103-113`

**Issue:**
```python
html=VERIFY_HTML.format(verify_url=verify_url),
```

fastapi-users JWTs are base64url-encoded and do not contain `{` or `}`, so this is not exploitable today. However, if the token generation ever changes to include curly braces (unlikely but not impossible), or if `FRONTEND_BASE_URL` is misconfigured to include a `{`, the `.format()` call raises `KeyError` rather than sending an email. This is an unnecessarily fragile pattern given the templates are static except for the URL.

**Fix:** Use `VERIFY_HTML.replace("{verify_url}", verify_url)` or switch to a proper template engine.

---

### IN-03: `admin_router.py` comment says "Note on `from __future__ import annotations`: Removed intentionally" — but `manager.py` and `deps.py` both have `from __future__ import annotations` and are also used in FastAPI route resolution

**File:** `backend/app/auth/admin_router.py:44-47`

**Issue:**
The comment warns that `from __future__ import annotations` breaks FastAPI's `inspect.signature` resolution in Python 3.13+. `manager.py` (line 1) and `deps.py` (line 1) both import it. `admin_router.py` imports from both modules and uses their types in `Annotated[UserManager, Depends(get_user_manager)]`. If the Python 3.13 breakage is real, the issue exists in the transitive imports regardless of `admin_router.py` not having the import itself.

This is a documentation inconsistency rather than a runtime bug (the current stack uses Python 3.12 per CLAUDE.md), but the comment creates false confidence.

**Fix:** Either remove the comment (it documents a guard that does not fully protect) or document that the restriction applies only to files that use `Annotated[T, Depends(...)]` with forward-reference types in the function signature itself — not to module-level type annotations.

---

_Reviewed: 2026-05-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
