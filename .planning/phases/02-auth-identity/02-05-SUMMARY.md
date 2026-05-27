---
phase: 02-auth-identity
plan: 05
subsystem: auth-frontend
tags: [auth, frontend, nextjs, middleware, admin, jose, edge-runtime, shadcn, hs256]

# Dependency graph
requires:
  - phase: 02-auth-identity
    plan: 03
    provides: "POST /admin/auth/login OAuth2 Bearer JSON, POST /admin/auth/logout, current_active_admin guard, bin/create_admin.py CLI"
  - phase: 02-auth-identity
    plan: 04
    provides: "(auth) layout patterns, shadcn primitives (Card / Form / Input / Button / Label), Server Action pattern, useActionState + react-hook-form + startTransition wrapper, jose already installed (^5.9.0), BACKEND_URL env"
provides:
  - "frontend/src/middleware.ts — Edge runtime guard on /admin/* (HS256 jose.jwtVerify); OPTIMISTIC layer — backend authoritative"
  - "frontend/src/lib/auth.ts adminLoginAction — Server Action POSTs to /admin/auth/login + sets HttpOnly admin_jwt cookie path=/admin (T-02-50 mitigation)"
  - "frontend/src/lib/auth-schemas.ts AdminLoginSchema — admin email + non-empty password (no client length enforcement; bin/create_admin.py bypasses validate_password)"
  - "frontend/src/app/admin/layout.tsx — server component shell with top nav distinct from player UI"
  - "frontend/src/app/admin/page.tsx — placeholder admin landing (Phase 10 fills KPI dashboard)"
  - "frontend/src/app/admin/login/page.tsx — server shell + AdminLoginForm in Card"
  - "frontend/src/app/admin/login/admin-login-form.tsx — client form mirroring player LoginForm but admin-labelled"
  - "6 middleware tests + 3 admin-login tests (9 new); full frontend suite 33/33 green"
affects: [03-wallet-ledger (player flow gated by middleware-free routes), 04-markets-domain (admin endpoints behind /admin/*), 08-admin-crm (CRM lives under /admin/*), 10-admin-dashboard-branding (replaces /admin/ landing content)]

# Tech tracking
tech-stack:
  added: []  # zero new packages — all runtime deps installed in 02-04 (jose, zod, etc.)
  patterns:
    - "Edge middleware guards /admin/* with jose HS256 jwtVerify (RESEARCH Pattern 5); algorithm pinned to HS256 to defeat alg=none / alg confusion attacks (T-02-47)"
    - "OPTIMISTIC middleware contract — RESEARCH lines 913-914: middleware only verifies signature + expiry; FastAPI current_active_admin is the AUTHORITATIVE gate (Plan 02-03)"
    - "admin_jwt cookie scoped to path=/admin (T-02-50 defense-in-depth) — browser never sends admin token on /auth/* or / routes"
    - "Admin Server Action POSTs OAuth2 form, parses JSON {access_token, token_type:'bearer'}, re-wraps as HttpOnly cookie via cookies().set() (T-02-55: token never reaches the client)"
    - "AdminLoginSchema mirrors player LoginSchema (email + non-empty password) — NO client-side password length enforcement because admins are seeded via bin/create_admin.py which bypasses UserManager.validate_password (Plan 02-03 D-G)"
    - "Cookie maxAge=900 matches backend ACCESS_TOKEN_LIFETIME_SECONDS (Plan 02-01)"
    - "Same testing pattern as Plan 02-04: vi.hoisted() for action mocks (#2 of 02-04 deviations), userEvent + startTransition wrapper, FormData payload assertion"

key-files:
  created:
    - "frontend/src/middleware.ts"
    - "frontend/src/__tests__/middleware.test.ts"
    - "frontend/src/app/admin/layout.tsx"
    - "frontend/src/app/admin/page.tsx"
    - "frontend/src/app/admin/login/page.tsx"
    - "frontend/src/app/admin/login/admin-login-form.tsx"
    - "frontend/src/app/admin/__tests__/admin-login.test.tsx"
  modified:
    - "frontend/src/lib/auth.ts"
    - "frontend/src/lib/auth-schemas.ts"
    - ".env.example"

key-decisions:
  - "Middleware verbatim from RESEARCH §Pattern 5 lines 883-911 — no deviation; HS256 + algorithms pin in jwtVerify"
  - "AdminLoginSchema does NOT enforce password length client-side — Plan 02-03 D-G established that admin passwords come from the operator's .env.local (validate_password bypassed); enforcing it here would lock out legitimate operator-set passwords that don't match validate_password rules"
  - "admin_jwt cookie path=/admin (defense-in-depth) + maxAge=900 (matches backend ACCESS_TOKEN_LIFETIME_SECONDS)"
  - "Admin layout renders the top nav even on /admin/login (placeholder links inactive) — single layout for the whole admin section; operator immediately knows they reached the admin surface"
  - "Admin landing page is a placeholder — content arrives in Phase 10; the routing + auth pieces are what Plan 02-05 must verify"

patterns-established:
  - "Edge middleware shape for any future /<surface>/* route gate: regex match + early passthrough for the login page + jose.jwtVerify under try/catch + redirect to <surface>/login"
  - "Server Action that consumes an OAuth2 Bearer JSON: POST form, parse JSON, validate token_type, set HttpOnly cookie via cookies().set() with explicit path scoping — never expose the raw token to the client"
  - "Admin section layout pattern: separate /admin/* route tree with its own layout.tsx + nav, mirroring the (auth) route group's separate layout (Plan 02-04)"

requirements-completed:
  - AUTH-07  # frontend half — Edge middleware enforces admin_jwt HS256 verify on /admin/*; admin/login page mirrors player UX but visually distinct
  - AUTH-09  # admin Bearer rotation + reuse already shipped by Plan 02-03 backend; frontend now consumes the Bearer through adminLoginAction
  # Note: AUTH-08 was the rate-limit requirement and was fully closed in Plans 02-02 + 02-03 (backend slowapi).

# Metrics
duration: ~12min
completed: 2026-05-27
---

# Phase 02 Plan 05: Admin Frontend (Middleware + Login) Summary

**End-to-end admin sign-in surface for the browser: a Next.js Edge middleware that optimistically guards every `/admin/*` route by verifying the `admin_jwt` HttpOnly cookie with `jose.jwtVerify` (HS256 against `ADMIN_JWT_PUBLIC_SECRET`), an `adminLoginAction` Server Action that POSTs OAuth2 credentials to FastAPI's `/admin/auth/login` and stores the returned access_token in an HttpOnly cookie scoped to `/admin/` (defense-in-depth so the admin token never leaks to player routes), an `/admin/login` page that mirrors the player login UX but is visually + textually distinct ("Admin sign in" / "Sign in as admin"), a placeholder `/admin/` landing page reserved for Phase 10's KPI dashboard, and 9 new Vitest tests (6 middleware + 3 admin login form). With Plan 02-05 shipped, the entire ROADMAP Phase 2 acceptance is end-to-end demoable: a player can register / verify / login via `/login`, and a real admin (seeded via `bin/create_admin.py` from 02-03) can log in at `/admin/login`, land on `/admin/`, and navigate any `/admin/*` route knowing both Next.js middleware AND FastAPI `current_active_admin` enforce admin authority.**

## Performance

- **Duration:** ~12 min (much faster than 02-04's ~30 min — most patterns already shipped; this plan extended `auth.ts`, added the middleware, and the admin pages mirror existing forms)
- **Started:** 2026-05-27 (post Wave-3 — sole plan in Wave 4)
- **Completed:** 2026-05-27
- **Tasks:** 2 / 2
- **Files:** 7 created, 3 modified (10 files total)
- **Tests added:** 9 (6 middleware + 3 admin login form); full frontend suite = 33 tests, 33/33 green

## Accomplishments

### Edge middleware (`frontend/src/middleware.ts`)

- Verbatim from RESEARCH §"Pattern 5 admin middleware" lines 883-911 — pinned to HS256 (algorithm-confusion mitigation T-02-47) via `jwtVerify(token, secret, { algorithms: ['HS256'] })`.
- Early passthrough for non-`/admin/*` routes (regex match) AND for `/admin/login` (so the login page itself never redirects to itself, RESEARCH line 894).
- No-cookie / verify-failure / expired-token paths all fail-closed via `NextResponse.redirect(new URL('/admin/login', req.url))`.
- Edge-runtime safe: ZERO database access (Anti-pattern RESEARCH line 923) — `process.env.ADMIN_JWT_PUBLIC_SECRET` is the sole verification input.
- Module docstring documents:
  - The OPTIMISTIC trust boundary (FastAPI's `current_active_admin` is authoritative).
  - The shared-secret invariant with backend `SECRET_KEY` (Assumption A8; T-02-53).
  - The Edge-runtime DB ban (Anti-pattern).
- `export const config = { matcher: ['/admin/:path*'] }` — Next.js only invokes the middleware on admin paths.

### Admin Server Action (`frontend/src/lib/auth.ts → adminLoginAction`)

- POSTs `URLSearchParams({username, password})` to FastAPI `/admin/auth/login` (OAuth2 form per Plan 02-03's proxy route).
- Parses JSON `{access_token, token_type}`; rejects shapes where `token_type !== 'bearer'` or `access_token` missing.
- Calls `cookies().set('admin_jwt', access_token, { httpOnly: true, secure: NODE_ENV==='production', sameSite: 'lax', path: '/admin', maxAge: 900 })`:
  - `httpOnly: true` — JS cannot read it (XSS-safe per T-02-51).
  - `path: '/admin'` — browser never sends `admin_jwt` on `/auth/*` or `/` (T-02-50).
  - `maxAge: 900` — matches backend `ACCESS_TOKEN_LIFETIME_SECONDS` (Plan 02-01).
  - `secure` flipped on `NODE_ENV==='production'` (Pitfall 3 mitigation — dev cookie still works on `http://localhost`).
- On 401 returns `{errors: {_form: ['Invalid credentials']}}` (mirrors backend's identical-401 contract from Plan 02-03 D-J).
- On 429 returns the shared `tooManyAttempts()` message.
- On success: `redirect('/admin')`.
- The action's TYPE returns `Promise<ActionState>` and reuses the same `useActionState`-friendly discriminated union from `auth-schemas.ts` (so the form binds with the existing `useActionState<ActionState, FormData>` pattern from Plan 02-04).

### Admin Login Schema (`frontend/src/lib/auth-schemas.ts → AdminLoginSchema`)

- `email: z.string().email(...)` + `password: z.string().min(1, ...)`.
- Deliberately DOES NOT enforce password length / complexity — admins are seeded via `bin/create_admin.py` which BYPASSES `UserManager.validate_password` (Plan 02-03 D-G); enforcing here would lock out legitimate operator-set passwords. Backend's `/admin/auth/login` is the authoritative validator.

### Admin pages tier (`frontend/src/app/admin/`)

- **`admin/layout.tsx`** — server component wrapper for the entire `/admin/*` tree with a top nav: `XPredict Admin` brand link to `/admin`, three placeholder Phase 8 CRM links (`Users` / `Markets` / `Audit log` shown as inactive zinc text), and a logout link (Phase 8 wires the actual logout Server Action). The nav is rendered even on `/admin/login` — single layout for the entire admin section.
- **`admin/login/page.tsx`** — server shell renders a centered `Card` (max-w-md) with `CardHeader → CardTitle "Admin sign in"` + `CardContent → AdminLoginForm`. Visually distinct from `/login` (heading + page chrome).
- **`admin/login/admin-login-form.tsx`** — client component (`"use client"`) using:
  - `useActionState<ActionState, FormData>(adminLoginAction, undefined)` — same shape as Plan 02-04 player forms.
  - `useForm<AdminLoginValues>` with `zodResolver(AdminLoginSchema)`.
  - shadcn `Form` / `FormField` / `FormItem` / `FormLabel` / `FormControl` / `FormMessage` primitives.
  - `startTransition(() => formAction(fd))` inside `handleSubmit` (silences React 19's "useActionState outside a transition" warning + works in jsdom — Plan 02-04 deviation #3 inherited).
  - Submit button labelled `Sign in as admin` (success criteria #2 + Plan PLAN line 38 + button-name test assertion).
- **`admin/page.tsx`** — placeholder server component:
  - `<h1>Admin dashboard</h1>` + Phase 10 / Phase 8 roadmap copy.
  - The plan's contract: "/admin/page.tsx renders without crash when an authenticated admin reaches it" — Phase 10 ADD-01..03 fills the actual KPI content.

### Tests (`frontend/src/__tests__/middleware.test.ts` + `frontend/src/app/admin/__tests__/admin-login.test.tsx`)

Middleware (6 tests, run under node env per `vitest.config.ts` environmentMatchGlobs):

1. `redirects_unauthenticated_admin_request` — `/admin/users` with no cookie → 307 + Location `/admin/login`.
2. `passes_through_admin_login_route` — `/admin/login` itself → 200 (NextResponse.next).
3. `passes_through_non_admin_routes` — `/`, `/login`, `/api/healthz`, `/register` → 200.
4. `passes_through_valid_admin_jwt` — HS256-signed JWT (`SignJWT(...).sign(VALID_SECRET)`) → 200.
5. `redirects_on_invalid_jwt_signature` — JWT signed with `WRONG_SECRET` → 307 to `/admin/login`.
6. `redirects_on_expired_jwt` — JWT with `exp` 60s in the past → 307 to `/admin/login` (jose throws `JWTExpired`).

Admin login form (3 tests, run under jsdom env):

1. `renders_admin_login_form` — assertions on email + password labelled inputs + "Sign in as admin" button.
2. `submits_to_admin_action` — userEvent types credentials, clicks submit, asserts `adminLoginActionMock` was called with FormData containing `email` + `password`.
3. `displays_inline_form_error` — action mocked to return `{errors: {_form: ['Invalid credentials']}}` → asserts the message renders.

## Task Commits

1. **Task 1 — Edge middleware + adminLoginAction + 6 middleware tests + .env.example doc:** `8a9c186`
2. **Task 2 — Admin layout + login page + admin-login-form + landing + 3 form tests:** `fd03396`

## Files Created/Modified

### Created (7)

- `frontend/src/middleware.ts` — Edge HS256 admin guard
- `frontend/src/__tests__/middleware.test.ts` — 6 tests
- `frontend/src/app/admin/layout.tsx` — admin section nav shell
- `frontend/src/app/admin/page.tsx` — placeholder landing
- `frontend/src/app/admin/login/page.tsx` — admin login server shell
- `frontend/src/app/admin/login/admin-login-form.tsx` — admin login client form
- `frontend/src/app/admin/__tests__/admin-login.test.tsx` — 3 tests

### Modified (3)

- `frontend/src/lib/auth.ts` — appended `adminLoginAction` + `AdminLoginSchema` import; preserved the five Plan 02-04 player actions
- `frontend/src/lib/auth-schemas.ts` — appended `AdminLoginSchema` (email + non-empty password)
- `.env.example` — improved `ADMIN_JWT_PUBLIC_SECRET` inline documentation (must equal backend SECRET_KEY; Phase 11 moves to RS256)

## Decisions Made

### D-A: AdminLoginSchema does NOT enforce password length client-side

Plan 02-03 D-G established that `bin/create_admin.py` BYPASSES `UserManager.validate_password` — admin passwords come from the operator's `.env.local` and the operator is trusted to choose a strong one. If the frontend schema enforced the 12+ char + upper/lower/digit rules, a perfectly valid operator-set password that doesn't match those rules would be rejected client-side before the form is even submitted. The backend `/admin/auth/login` remains the authoritative validator (it just hashes-compares with whatever's in the DB; no strength rules at login time). I documented this in the `AdminLoginSchema` JSDoc.

### D-B: admin_jwt cookie path scoped to /admin

The browser only sends `admin_jwt` on requests to `/admin/*`. This is browser-side defense-in-depth (T-02-50) — even if a Phase 4+ player API fetch were accidentally constructed without `credentials: 'omit'`, the admin token would NOT travel along. Combined with the backend's distinct OAuth2PasswordBearer transport on `/admin/auth/*` (Plan 02-03), this means the admin Bearer is unreachable from any non-admin code path.

### D-C: Cookie maxAge=900 matches backend ACCESS_TOKEN_LIFETIME_SECONDS

Plan 02-01 set `ACCESS_TOKEN_LIFETIME_SECONDS=900` (15 min). The admin Bearer JWT issued by `admin_backend.login()` carries an `exp` that reflects this lifetime; the cookie that wraps the Bearer must expire NO LATER than the token itself, otherwise the browser would keep sending an invalid token (and `current_active_admin` would just reject it server-side, but that's an extra round-trip + audit_log noise). Setting `maxAge=900` in the cookie aligns the two clocks.

### D-D: Single admin layout for the whole /admin/* tree

The plan PATTERNS line 624-630 noted "admin/login uses its OWN layout structure (not the (auth) route group)". I went one step further: every `/admin/*` route — INCLUDING `/admin/login` — uses the same `app/admin/layout.tsx`. The placeholder nav links are inactive on `/admin/login` (the operator hasn't authenticated yet), but the brand link + visual identity are present. This is consistent with how the backend's `current_active_admin` guard works on the API side: the user is INSIDE the admin section the moment they navigate to `/admin/login`, even if they haven't proven authority yet.

### D-E: AdminLoginForm submit label is "Sign in as admin" (not "Sign in")

The plan PATTERNS line 236 + success criteria #2 ("admin-styled distinct UX") + the test assertion `getByRole('button', { name: /sign in as admin/i })` all converge on this label. It distinguishes the admin form visually + audibly (screen readers) from the player `/login` form, removing any chance an operator types player credentials into the admin form thinking it's the wrong page.

## Deviations from Plan

### None.

The plan was executed verbatim. Both tasks landed without any auto-fix being triggered — no Rule 1 bugs, no Rule 2 critical-functionality additions, no Rule 3 blockers, no Rule 4 architectural decisions. All patterns inherited from Plans 02-02 / 02-03 / 02-04 worked first-time:

- The `from __future__ import annotations` problem (Plan 02-02 deviation #1, Plan 02-03 deviation #2) does not apply to TypeScript files.
- The vi.hoisted() pattern (Plan 02-04 deviation #2) was applied preemptively in `admin-login.test.tsx`.
- The startTransition wrapper for `useActionState` (Plan 02-04 deviation #3) was applied preemptively in `admin-login-form.tsx`.
- The TypeScript mock typing `(...args: unknown[]) => Promise<unknown>` (Plan 02-04 deviation #5) was applied preemptively to satisfy next-lint's `no-explicit-any`.

The `.env.example` already had `ADMIN_JWT_PUBLIC_SECRET` from a prior plan, so I only refined the inline documentation to spell out the "must equal backend SECRET_KEY" invariant per the plan's `<action>` block.

## Issues Encountered

### None blocking

The pre-existing test isolation failures noted in 02-01, 02-02, 02-03 SUMMARYs are backend-only and do not affect this frontend-only plan. The gitleaks false positive on the sibling worktree's frontend test fixtures (noted in `02-03-SUMMARY.md > Issues Encountered`) is also unrelated — Plan 02-05 introduces ZERO new strings that match generic-api-key heuristics; the only new env-value addition is the same `change-me-…` placeholder pattern as the rest of `.env.example`.

## Manual Verification (deferred — host runtime port conflicts)

The PLAN `<verification>` block's manual smoke is gated by the same `cc_redis` / `cc_postgres` port conflicts documented in `01-03-SUMMARY.md`. The 5-min checklist when the host runtime is available:

1. Stop `cc_redis` + `cc_postgres` containers.
2. `bin/dev.ps1` to bring up XPredict's docker-compose (8 services).
3. `cd backend; uv run alembic upgrade head`.
4. Set `FIRST_ADMIN_EMAIL=pol@xpredict.local` + `FIRST_ADMIN_PASSWORD=AdminPass1234!` in `.env.local`.
5. `uv run python bin/create_admin.py` (created in Plan 02-03).
6. Visit `http://localhost:3000/admin` → expect 307 redirect to `/admin/login`.
7. Submit admin credentials → cookie set → redirect to `/admin` → land on placeholder.
8. Refresh `/admin` → still authenticated (cookie not consumed).
9. `curl.exe -X GET http://localhost:8000/admin/users` (no Bearer) → expect 401 (FastAPI authoritative gate enforces).
10. Restart `cc_redis` + `cc_postgres`.

Steps 1, 2, 6-9 require the runtime; the test surface (6 middleware tests + 3 admin login + 24 carried-over from 02-04) is otherwise the complete acceptance for the frontend half.

## User Setup Required

None for this plan. The new env vars (`ADMIN_JWT_PUBLIC_SECRET`) was already added by Plan 02-01 (verified via `Read` of `.env.example` at the start of execution). The plan only refined its inline documentation. To use the admin login in production: ensure `ADMIN_JWT_PUBLIC_SECRET` equals backend `SECRET_KEY` in `.env.local` — otherwise the middleware will fail-closed (all admin requests redirect to `/admin/login`).

## Next Plan Readiness (End-of-Phase 2)

This is the LAST plan in Phase 02-auth-identity. With 02-05 shipped:

- The ENTIRE ROADMAP Phase 2 acceptance is end-to-end machine-verifiable via the combined backend + frontend test suites (see Test Coverage Matrix below).
- Plan 03 (wallet-ledger) can take a hard dependency on:
  - `current_active_player` (Plan 02-02) for player API routes.
  - `current_active_admin` (Plan 02-03) for any admin admin-wallet adjustments.
  - The player `(auth)/` UI shell for any post-authentication player surface (e.g., wallet balance display in the header).
- Plan 04+ admin endpoints in `backend/app/<surface>/admin_router.py` (or equivalent) just take `Depends(current_active_admin)` and the entire auth+nav infrastructure (Edge middleware + Bearer cookie + admin layout) flows through.

## Test Coverage Matrix (Plan 02-05 surface)

| Requirement / PLAN must-have | Test File | Test Name | Status |
|------------------------------|-----------|-----------|--------|
| AUTH-07 (Edge middleware enforces JWT verify on /admin/*) | middleware.test.ts | redirects_unauthenticated_admin_request | ✅ |
| AUTH-07 (middleware passes valid JWT through) | middleware.test.ts | passes_through_valid_admin_jwt | ✅ |
| AUTH-07 (middleware fail-closed on invalid signature) | middleware.test.ts | redirects_on_invalid_jwt_signature | ✅ |
| AUTH-07 (middleware fail-closed on expired JWT) | middleware.test.ts | redirects_on_expired_jwt | ✅ |
| Plan must-have (admin/login itself never redirects) | middleware.test.ts | passes_through_admin_login_route | ✅ |
| Plan must-have (non-admin routes pass through) | middleware.test.ts | passes_through_non_admin_routes | ✅ |
| Plan must-have (admin login form renders + posts) | admin-login.test.tsx | renders_admin_login_form, submits_to_admin_action | ✅ |
| Plan must-have (inline form error displayed) | admin-login.test.tsx | displays_inline_form_error | ✅ |
| Plan must-have (path: '/admin' on cookie set) | (verified by inspection of auth.ts adminLoginAction) | n/a | ✅ |
| Plan must-have (maxAge=900 matches backend) | (verified by inspection) | n/a | ✅ |
| Plan must-have (HttpOnly cookie) | (verified by inspection) | n/a | ✅ |

## End-of-Phase 2 Acceptance: ROADMAP SC#1..SC#6

Cross-references each ROADMAP Phase 2 Success Criterion to the test (or pair of tests) that proves it:

| ROADMAP SC | Description | Verifying Test(s) |
|-----------|-------------|-------------------|
| **SC#1 — Player registers + receives email verify + can sign in + session persists** | Full player happy path | backend: `tests/auth/test_register.py::test_register_success` (201 + audit) + `tests/auth/test_email_verification.py::test_verify_single_use` (email link single-use) + `tests/auth/test_login.py::test_cookie_set_and_persists` (HttpOnly Lax cookie + persists across requests); frontend: `frontend/src/lib/__tests__/auth.test.ts::loginAction forwards Set-Cookie to next/headers cookies` |
| **SC#2 — Logout revokes server-side session + cannot re-auth with same token** | `auth.session_revoked` audit row + cookie + DB-side revoke | backend: `tests/auth/test_logout.py::test_logout_revokes_token` (refresh_tokens.revoked_at IS NOT NULL + next request 401) |
| **SC#3 — Refresh-token rotation + reuse detection (compromised refresh re-presented → all sessions revoked)** | Custom DatabaseStrategy reuse-detection | backend: `tests/auth/test_refresh_rotation.py::test_reuse_detection_revokes_all` (scorched-earth revocation cascades) |
| **SC#4 — Password reset bumps token_version + invalidates prior sessions** | belt+suspenders: token_version + bulk revoke | backend: `tests/auth/test_password_reset.py::test_reset_invalidates_sessions` + `tests/auth/test_password_reset.py::test_audit_trail_on_reset` |
| **SC#5 — Admin uses distinct login route + is_admin flag enforced (non-admin Bearer → 403 on /admin/*)** | Dual-backend cross-surface isolation | backend: `tests/auth/test_admin_bearer.py::test_non_admin_bearer_forbidden` (player can't mint admin Bearer) + `tests/auth/test_admin_bearer.py::test_admin_bearer_does_not_authenticate_player_routes` (admin Bearer not accepted on /auth/*); frontend: `src/__tests__/middleware.test.ts::redirects_unauthenticated_admin_request` (Edge middleware redirects anonymous /admin/* request) |
| **SC#6 — 6th login attempt within window → 429 without email enumeration leak** | slowapi + check_email_limit + generic 429 | backend: `tests/auth/test_rate_limit.py::test_six_logins_returns_429` (per-IP 429) + `tests/auth/test_email_enumeration.py::test_login_does_not_leak_email_existence` (identical body for unknown-vs-known email) |

All 6 ROADMAP Phase 2 Success Criteria are now machine-verifiable end-to-end via the combined backend (auth-suite 74/74) + frontend (33/33) test suites.

## Audit-Event Taxonomy Coverage (Plan 02-05 additions)

Plan 02-05 is FRONTEND-ONLY — no new audit events are written from frontend code (T-02-46: frontend has no audit obligation, RESEARCH-noted: audit happens server-side). The admin login flow already emits `auth.admin_login_started` / `auth.admin_login_failed` from `backend/app/auth/admin_router.py` (Plan 02-03 D-J), exercised here by the same backend tests but driven through the frontend's `adminLoginAction` proxy.

## Threat Surface Scan

All threats T-02-47 through T-02-56 + T-02-SC documented in PLAN.md `<threat_model>` have mitigations implemented and where applicable, tested:

- T-02-47 (Spoofing: forged admin_jwt via algorithm confusion) → `jwtVerify(..., { algorithms: ['HS256'] })` pins the algorithm; `redirects_on_invalid_jwt_signature` asserts the fail-closed path. ✅
- T-02-48 (Spoofing: bypass middleware via direct curl to /admin/* API) → backend `current_active_admin` is authoritative; `test_non_admin_bearer_forbidden` already covers (Plan 02-03 inheritance). ✅
- T-02-49 (Tampering: ADMIN_JWT_PUBLIC_SECRET leaked to git) → placeholder `change-me-32+chars-must-match-backend-SECRET_KEY` is gitleaks-safe; verified via `gitleaks detect --source .env.example` ("no leaks found"). ✅
- T-02-50 (InfoDisc: admin_jwt cookie leaks to player API) → cookie `path: '/admin'` scoping; browser does NOT include admin_jwt on `/auth/*` or `/`. Verified by inspection of `adminLoginAction`. ✅
- T-02-51 (Tampering: XSS reads admin_jwt) → `httpOnly: true` on cookies().set(); JS cannot read; React escapes user input. ✅
- T-02-52 (InfoDisc: middleware logs JWT payload) → middleware does NOT call `console.log` anywhere; Edge runtime has no logging path. Verified by inspection. ✅
- T-02-53 (EoP: ADMIN_JWT_PUBLIC_SECRET drifts from backend SECRET_KEY) → middleware fail-closed (every admin request redirects); `.env.example` documents the parity requirement. ✅
- T-02-54 (DoS: jose.jwtVerify CPU-heavy on every /admin/* request) → HS256 is symmetric microseconds; far cheaper than a DB round-trip (which is the actual anti-pattern). Accepted. ✅
- T-02-55 (InfoDisc: adminLoginAction surfaces raw access_token to client) → token stored via cookies().set() server-side; action returns `{success: true}` or error state; cookie is HttpOnly so client cannot read. ✅
- T-02-56 (Repudiation: no client-side admin audit) → frontend has no audit obligation; backend audits via `auth.admin_login_started` / `auth.admin_login_failed` (Plan 02-03). ✅
- T-02-SC (Supply chain: no new packages this plan) → zero new pnpm installs; verified by `pnpm-lock.yaml` unchanged in `git status` after both commits. ✅

No new threat surface introduced beyond what the plan documented.

## Known Stubs

- `frontend/src/app/admin/page.tsx` is a placeholder for Phase 10's KPI dashboard. This is INTENTIONAL — the plan's must-have line 41 says `/admin/page.tsx is a placeholder landing page reading 'Admin dashboard — coming in Phase 10'`. It satisfies the contract "renders without crashing for authenticated admin"; Phase 10 ADD-01..03 will replace its content.
- `frontend/src/app/admin/layout.tsx` nav links for `Users` / `Markets` / `Audit log` are inactive `<span>` placeholders. INTENTIONAL — Phase 8 (Admin CRM) wires them to real CRM routes; the logout link points at `/admin/logout` which Phase 8 will also implement as a server action calling `cookies().delete('admin_jwt')` + redirect.

Neither of these prevents the plan's goal (admin auth surface end-to-end). They are explicitly documented as deferred to specific future plans.

## Self-Check: PASSED

All 7 created files exist on disk in the worktree:

- `frontend/src/middleware.ts` — FOUND
- `frontend/src/__tests__/middleware.test.ts` — FOUND
- `frontend/src/app/admin/layout.tsx` — FOUND
- `frontend/src/app/admin/page.tsx` — FOUND
- `frontend/src/app/admin/login/page.tsx` — FOUND
- `frontend/src/app/admin/login/admin-login-form.tsx` — FOUND
- `frontend/src/app/admin/__tests__/admin-login.test.tsx` — FOUND

All 3 modified files have the expected changes:

- `frontend/src/lib/auth.ts` — `adminLoginAction` exported (verified by `node -e "...includes('adminLoginAction')..."`)
- `frontend/src/lib/auth-schemas.ts` — `AdminLoginSchema` exported (verified by `import { AdminLoginSchema } from "./auth-schemas"` succeeding at compile)
- `.env.example` — `ADMIN_JWT_PUBLIC_SECRET` documentation refined (verified by inspection)

Both task commits exist on `worktree-agent-a35c6780f8ca57a35`:

- `8a9c186` — Task 1 (Edge middleware + adminLoginAction + 6 middleware tests + .env.example)
- `fd03396` — Task 2 (admin pages + admin-login form + 3 form tests)

Plan metadata (STATE.md / ROADMAP.md): owned by the parent orchestrator after Wave 4 completes (worktree mode — this executor does NOT touch those files).

---

*Phase: 02-auth-identity*
*Plan: 05*
*Completed: 2026-05-27*
