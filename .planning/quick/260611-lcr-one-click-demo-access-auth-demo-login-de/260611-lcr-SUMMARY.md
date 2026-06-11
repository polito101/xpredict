---
phase: quick-260611-lcr
plan: 01
subsystem: auth
tags: [demo, auth, frontend, backend, rate-limit]
requires: [DEMO_MODE setting, UserManager.create demo auto-verify + bonus, player_backend cookie session]
provides: [POST /auth/demo-login route, demoLoginAction Server Action, DemoLoginButton]
affects: [backend/app/auth/router.py, frontend login page]
tech-stack:
  added: []
  patterns: [DEMO_MODE-gated proxy route, slowapi per-IP limit, Server-Action cookie forwarding]
key-files:
  created:
    - backend/tests/auth/test_demo_login.py
    - frontend/src/app/(auth)/login/demo-login-button.tsx
    - frontend/src/app/(auth)/__tests__/demo-login.test.tsx
  modified:
    - backend/app/auth/router.py
    - frontend/src/lib/auth.ts
    - frontend/src/app/(auth)/login/page.tsx
decisions:
  - "Ephemeral demo email uses @demo.example.com (RFC 2606 reserved) instead of the plan's @demo.local — pydantic EmailStr rejects .local as a special-use/reserved name"
  - "Frontend uses a demoLoginAction Server Action (not a raw client fetch to a relative /auth/demo-login) because the codebase has NO Next rewrite for /auth/* and the session cookie is HttpOnly cross-origin — Server Actions forward the cookie via cookies().set(), matching loginAction"
metrics:
  duration: ~25m
  completed: 2026-06-11
  tasks: 3
  files: 6
---

# Phase quick-260611-lcr Plan 01: One-Click Demo Access Summary

One-click demo access: a `DEMO_MODE`-gated `POST /auth/demo-login` backend route that mints an ephemeral verified + bonus-funded player per click, issues the player session cookie, is per-IP rate-limited, and writes an `auth.demo_session_started` audit row — plus a Spanish "Probar la demo" button on the login page (gated behind `NEXT_PUBLIC_DEMO_MODE`) that triggers it and lands the user in `/markets`.

## What Was Built

**Task 1 — Backend route (`backend/app/auth/router.py`, commit `f0520e8`)**
- Added `import secrets` and a `demo_login_proxy` route on `auth_proxy_router`, placed after `login_proxy`.
- Gates FIRST on `get_settings().DEMO_MODE` (read dynamically, not the module-level `settings`) → 404 when off (invisible in white-label/prod, T-demo-02), not 403/500.
- Decorated `@limiter.limit("5/minute", key_func=get_remote_address)` mirroring the other proxy routes (T-demo-01).
- Builds an ephemeral user `demo-<uuid>@demo.example.com` + `secrets.token_urlsafe(24)` password, calls `user_manager.create(..., safe=True, request=request)` — which auto-verifies AND grants the signup bonus in DEMO_MODE (no second grant). Issues the cookie exactly like `login_proxy` (`get_database_strategy()` → `player_backend.login`). Writes the `auth.demo_session_started` audit row in an independent session.

**Task 2 — Backend tests (`backend/tests/auth/test_demo_login.py`, commit `c5e70f2`)**
- 4 integration tests (testcontainers Postgres + `memory://` slowapi), DEMO_MODE toggled via `monkeypatch.setenv` + `get_settings.cache_clear()`, demo rows cleaned by `email LIKE 'demo-%@demo.example.com'`:
  1. `test_demo_login_404_when_flag_off` — flag off → 404.
  2. `test_demo_login_creates_verified_funded_user_when_on` — 200 + `xpredict_session` cookie (HttpOnly, SameSite=lax); `GET /auth/users/me` returns 200 (proves verified) with a `demo-…@demo.example.com` email; no `is_superuser` leak.
  3. `test_demo_login_grants_signup_bonus` — wallet balance equals `SIGNUP_BONUS_AMOUNT` (queried via the `test_signup_bonus_on_verify.py` Account-balance shape).
  4. `test_demo_login_rate_limited` — 5 calls OK, 6th → 429.

**Task 3 — Frontend (commit `bde21b1`)**
- `frontend/src/lib/auth.ts`: added `demoLoginAction` Server Action — POSTs server-side to the backend `/auth/demo-login`, forwards the session cookie via `forwardSessionCookie`, returns `ActionState` (`{success}` / `{errors}`); maps 429 → "too many", any non-ok (incl. 404 when DEMO_MODE off) → inline Spanish error.
- `frontend/src/app/(auth)/login/demo-login-button.tsx`: `"use client"` `DemoLoginButton` — `useActionState` + `startTransition`, "Probar la demo" / "Cargando…" pending label, `useRouter().push("/markets")` on success (via effect), inline `data-testid="demo-error"` on failure.
- `frontend/src/app/(auth)/login/page.tsx`: imports + renders `<DemoLoginButton />` (with a small "o" divider) only when `process.env.NEXT_PUBLIC_DEMO_MODE === "true"` (gate in the server component → button fully absent in prod).
- `frontend/src/app/(auth)/__tests__/demo-login.test.tsx`: 3 vitest tests (renders button; pushes to `/markets` on success; shows inline error + no navigation on failure).

## Verification

- Backend: `cd backend && uv run pytest tests/auth/test_demo_login.py -q` → **4 passed**.
- Backend regression: `uv run pytest tests/auth/test_login.py tests/auth/test_rate_limit.py -q` → **6 passed**.
- Backend lint/format: `ruff check` + `ruff format --check` on changed files → clean.
- Frontend: `pnpm vitest run "src/app/(auth)/__tests__/demo-login.test.tsx"` → **3 passed**.
- Frontend lint: `pnpm lint` → **0 errors** (warnings are all pre-existing, in untouched files).
- Frontend typecheck: `pnpm typecheck` → clean.
- No `backend/app/bets/*`, `backend/tests/bets/*`, or `frontend/src/app/portfolio/*` files touched; no file deletions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ephemeral demo email domain `.local` rejected by `EmailStr`**
- **Found during:** Task 1 (first backend test run returned 500).
- **Issue:** The plan specified `demo-<uuid>@demo.local`, but `UserCreate.email` is a pydantic `EmailStr` whose deliverability validator rejects `.local` as a "special-use or reserved name" → `ValidationError` → 500 instead of 200.
- **Fix:** Switched to `demo-<uuid>@demo.example.com` (RFC 2606 reserved `example.com` sub-domain — can never be a real mailbox AND passes `EmailStr`). Verified empirically which reserved domains `EmailStr` accepts. The `demo-` local-part prefix is preserved so cleanup/identification via `email LIKE 'demo-%'` still works; test assertions + cleanup updated to match.
- **Files modified:** `backend/app/auth/router.py`, `backend/tests/auth/test_demo_login.py`.
- **Commit:** `f0520e8` (route) / `c5e70f2` (tests).

### Architectural-pattern choice (within plan's explicit guidance)

**2. [Rule 3 - Blocking] Frontend reaches the backend via a Server Action, not a raw client `fetch`**
- **Found during:** Task 3 context review.
- **Issue:** The plan's primary suggestion was a client-side `fetch("/auth/demo-login")` to a relative path "if a dev proxy/rewrite routes /auth/*". There is **no** Next rewrite for `/auth/*` in `next.config.ts`, and the session cookie is `HttpOnly` + cross-origin — a browser `fetch` could neither reach the backend nor persist the cookie. Every existing auth call (`loginAction`, `registerAction`, …) goes through a Server Action that fetches `BACKEND_URL` server-side and re-sets the cookie via `cookies().set()`.
- **Fix:** Added `demoLoginAction` mirroring `loginAction` (the plan explicitly allowed this: "follow whatever the existing client-side auth calls do — match it"). The button invokes the action; success returns `{success}` and the client `router.push("/markets")` (testable, matches the plan's stated client-navigation contract), failure returns inline errors.
- **Files modified:** `frontend/src/lib/auth.ts`, `frontend/src/app/(auth)/login/demo-login-button.tsx`.
- **Commit:** `bde21b1`.

## Known Stubs

None. The demo flow is fully wired end-to-end (button → Server Action → backend route → verified+funded user → session cookie → `/markets`).

## User Setup (from plan frontmatter — operator action, not code)

- Backend: set `DEMO_MODE=true` in the demo deployment env (default `False`).
- Frontend: set `NEXT_PUBLIC_DEMO_MODE=true` in `.env.local` when demoing (leave unset for white-label/prod) so the button renders AND `demoLoginAction`'s error copy / register relaxed rules align.

## Threat Flags

None. The endpoint stays within the plan's `<threat_model>`: DEMO_MODE-gated (404 in prod), per-IP rate-limited, `safe=True` user creation (no superuser escalation), idempotent bonus grant.

## Self-Check: PASSED

All 6 implementation files + the SUMMARY exist on disk; all 3 task commits (`f0520e8`, `c5e70f2`, `bde21b1`) are present in git history.
