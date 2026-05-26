---
phase: 02
slug: auth-identity
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-26
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3 + pytest-asyncio 0.25 (asyncio_mode="auto", loop_scope="session") |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/auth/ -x` |
| **Full suite command** | `uv run pytest -x` + `pnpm --filter frontend test` |
| **Estimated runtime** | ~30s (auth-only, testcontainer-warm) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/auth/ -x`
- **After every plan wave:** Run `uv run pytest -x` + `pnpm --filter frontend test`
- **Before `/gsd-verify-work`:** Full suite green; coverage ≥ 80% on `app/auth/*`
- **Max feedback latency:** 30 seconds (auth suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| AUTH-01a | 01 | 1 | AUTH-01 | T-register-01 | Argon2id hash stored (never plaintext) | integration | `uv run pytest tests/auth/test_register.py -x` | ❌ W0 | ⬜ pending |
| AUTH-01b | 01 | 1 | AUTH-01 | T-register-02 | Weak password rejected (InvalidPasswordException) | unit | `uv run pytest tests/auth/test_register.py::test_weak_password_rejected -x` | ❌ W0 | ⬜ pending |
| AUTH-02 | 01 | 1 | AUTH-02 | — | Registration triggers email in Mailpit | integration | `uv run pytest tests/auth/test_email_verification.py::test_register_sends_email -x` | ❌ W0 | ⬜ pending |
| AUTH-03 | 01 | 1 | AUTH-03 | T-verify-01 | Single-use token: second use → 400 | integration | `uv run pytest tests/auth/test_email_verification.py::test_verify_single_use -x` | ❌ W0 | ⬜ pending |
| AUTH-04 | 02 | 1 | AUTH-04 | T-session-01 | Cookie set on login; subsequent request authenticated | integration | `uv run pytest tests/auth/test_login.py::test_cookie_set_and_persists -x` | ❌ W0 | ⬜ pending |
| AUTH-05 | 02 | 1 | AUTH-05 | T-session-02 | Logout revokes token in DB; next call → 401 | integration | `uv run pytest tests/auth/test_logout.py::test_logout_revokes_token -x` | ❌ W0 | ⬜ pending |
| AUTH-06 | 02 | 1 | AUTH-06 | T-reset-01 | Password reset bumps token_version; old cookie → 401 | integration | `uv run pytest tests/auth/test_password_reset.py::test_reset_invalidates_sessions -x` | ❌ W0 | ⬜ pending |
| AUTH-07a | 03 | 2 | AUTH-07 | T-admin-01 | Player cookie on /admin/* → 403 | integration | `uv run pytest tests/auth/test_admin_bearer.py -x` | ❌ W0 | ⬜ pending |
| AUTH-07b | 03 | 2 | AUTH-07 | T-admin-02 | Non-admin Bearer on /admin/* → 403 | integration | `uv run pytest tests/auth/test_admin_bearer.py::test_non_admin_bearer_forbidden -x` | ❌ W0 | ⬜ pending |
| AUTH-08a | 01 | 1 | AUTH-08 | T-ratelimit-01 | 6th login attempt per-IP → 429 | integration | `uv run pytest tests/auth/test_rate_limit.py -x` | ❌ W0 | ⬜ pending |
| AUTH-08b | 01 | 1 | AUTH-08 | T-enumerate-01 | 429 message reveals no email existence info | integration | `uv run pytest tests/auth/test_email_enumeration.py -x` | ❌ W0 | ⬜ pending |
| AUTH-09a | 02 | 1 | AUTH-09 | T-refresh-01 | Reuse detection: revoked token → revoke ALL user tokens | integration | `uv run pytest tests/auth/test_refresh_rotation.py::test_reuse_detection_revokes_all -x` | ❌ W0 | ⬜ pending |
| AUTH-09b | 02 | 1 | AUTH-09 | T-refresh-02 | refresh_tokens.token_hash is SHA256 (raw token never stored) | unit | `uv run pytest tests/auth/test_refresh_rotation.py::test_token_hash_is_sha256 -x` | ❌ W0 | ⬜ pending |
| FE-AUTH-04 | 04 | 2 | AUTH-04 | — | /login page renders + posts to FastAPI | unit | `pnpm --filter frontend test src/app/__tests__/login.test.tsx` | ❌ W0 | ⬜ pending |
| FE-AUTH-07 | 04 | 2 | AUTH-07 | — | /admin/* redirected to /admin/login without admin_jwt cookie | unit | `pnpm --filter frontend test src/__tests__/middleware.test.ts` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/auth/__init__.py` — empty file (test package marker)
- [ ] `backend/tests/auth/conftest.py` — shared auth fixtures: `verified_user`, `admin_user`, `unverified_user`, `mailpit_messages` (clears Mailpit between tests via its HTTP API)
- [ ] `backend/tests/auth/test_register.py` — AUTH-01 (4 tests)
- [ ] `backend/tests/auth/test_login.py` — AUTH-04 (3 tests)
- [ ] `backend/tests/auth/test_logout.py` — AUTH-05 (2 tests)
- [ ] `backend/tests/auth/test_email_verification.py` — AUTH-02, AUTH-03 (4 tests)
- [ ] `backend/tests/auth/test_password_reset.py` — AUTH-06 (3 tests)
- [ ] `backend/tests/auth/test_refresh_rotation.py` — AUTH-09 (3 tests including reuse-detection critical test)
- [ ] `backend/tests/auth/test_admin_bearer.py` — AUTH-07 (3 tests)
- [ ] `backend/tests/auth/test_rate_limit.py` — AUTH-08 (3 tests; uses fakeredis or per-test Redis flush)
- [ ] `backend/tests/auth/test_email_enumeration.py` — AUTH-08 (2 tests: forgot-password 202 either way; login 401 timing within 50ms)
- [ ] `frontend/src/__tests__/middleware.test.ts` — Edge runtime middleware tests
- [ ] `frontend/src/app/__tests__/login.test.tsx` — Login page rendering + Server Action form submission

*Framework install: none — pytest, pytest-asyncio, httpx, testcontainers already in `[dependency-groups].dev`. Frontend has Vitest 2.1 from Phase 1.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Email link works in browser (click redirects + sets cookie) | AUTH-03, AUTH-04 | Requires real browser cookie handling | Open Mailpit at localhost:8025, click verify link, confirm redirect to home with active session |
| Password reset flow end-to-end in browser | AUTH-06 | Requires email client + real cookie behavior | Request reset, open Mailpit, click link, set new password, confirm old cookie → 401 |
| Admin Bearer JWT works in browser admin panel | AUTH-07 | Requires Next.js middleware to run | Log into /admin/login, confirm dashboard loads; confirm /admin/* redirects to login when Bearer absent |
| Rate-limit 429 UI display | AUTH-08 | Requires triggering rate limit in real browser | Attempt 6 logins in 60s, confirm friendly error message visible, no email existence leak |

---

*Phase: 02-auth-identity*
*Validation strategy created: 2026-05-26*
