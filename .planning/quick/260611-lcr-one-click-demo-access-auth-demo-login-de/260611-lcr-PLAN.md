---
phase: quick-260611-lcr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/auth/router.py
  - backend/tests/auth/test_demo_login.py
  - frontend/src/app/(auth)/login/page.tsx
  - frontend/src/app/(auth)/login/demo-login-button.tsx
  - frontend/src/app/(auth)/__tests__/demo-login.test.tsx
autonomous: true
requirements: [DEMO-01]
user_setup:
  - service: env
    why: "Frontend button only renders when demo mode is exposed to the client"
    env_vars:
      - name: NEXT_PUBLIC_DEMO_MODE
        source: "Set to \"true\" in frontend .env.local when demoing; leave unset for white-label/prod"
    dashboard_config:
      - task: "Set DEMO_MODE=true on the backend env for the demo deployment (default False)"
        location: "backend .env / deployment env"

must_haves:
  truths:
    - "With DEMO_MODE on, POST /auth/demo-login returns 200, sets the xpredict_session cookie, and the new user can call /auth/users/me (created already-verified)"
    - "The demo user receives the signup bonus (wallet funded) so it has play money"
    - "With DEMO_MODE off (default), POST /auth/demo-login is hidden/blocked (404)"
    - "POST /auth/demo-login is rate-limited (6th call from same IP -> 429)"
    - "The login page shows a 'Probar la demo' button only when NEXT_PUBLIC_DEMO_MODE is exposed; clicking it POSTs to the endpoint and lands the user in /markets"
  artifacts:
    - path: "backend/app/auth/router.py"
      provides: "demo_login_proxy route on auth_proxy_router gated by DEMO_MODE"
      contains: "demo-login"
    - path: "backend/tests/auth/test_demo_login.py"
      provides: "Integration tests: flag off -> 404, flag on -> 200 + cookie + verified + bonus, rate-limit -> 429"
    - path: "frontend/src/app/(auth)/login/demo-login-button.tsx"
      provides: "Client 'Probar la demo' button that POSTs and redirects to /markets"
    - path: "frontend/src/app/(auth)/__tests__/demo-login.test.tsx"
      provides: "Vitest render/behavior test for the demo button"
  key_links:
    - from: "backend/app/auth/router.py demo_login_proxy"
      to: "UserManager.create + player_backend.login"
      via: "create ephemeral verified user (auto-verify + bonus in DEMO_MODE) then issue cookie via get_database_strategy()"
      pattern: "player_backend\\.login"
    - from: "frontend/src/app/(auth)/login/demo-login-button.tsx"
      to: "/auth/demo-login"
      via: "fetch POST then redirect to /markets"
      pattern: "demo-login"
---

<objective>
Add one-click demo access: a `POST /auth/demo-login` backend endpoint (gated by the existing `DEMO_MODE` setting, default off) that creates an ephemeral verified-and-funded user per click, issues the player session cookie, is rate-limited, and writes an audit row. Add a "Probar la demo" button on the login page that POSTs to it and redirects to `/markets`.

Purpose: Let a prospect try the product in one click without registering, for sales demos — while staying invisible/blocked in white-label/production deployments (DEMO_MODE default False).

Output: A new proxy route in `backend/app/auth/router.py`, a backend integration test file, a frontend client button + wiring on the login page, and a frontend vitest test.

Note for the executor: `DEMO_MODE` already exists in `app/core/config.py` (default `False`), and `UserManager.create()` / `on_after_register()` already auto-verify the user AND grant the signup bonus when `DEMO_MODE` is on (see `backend/app/auth/manager.py` lines 110-113 and 202-221). So the demo-login route only needs to (a) gate on the flag, (b) build a `UserCreate` with the ephemeral email + strong random password, (c) call `user_manager.create(...)` — which produces an already-verified, bonus-funded user — and (d) reuse the exact session-issuance path of `login_proxy`. Do NOT add a second bonus grant; the manager already grants it on register in demo mode.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@backend/app/auth/router.py
@backend/app/auth/manager.py
@backend/app/auth/schemas.py
@backend/app/auth/rate_limit.py
@backend/app/core/config.py
@backend/tests/auth/test_login.py
@backend/tests/auth/test_rate_limit.py
@backend/tests/auth/conftest.py
@frontend/src/lib/auth.ts
@frontend/src/app/(auth)/login/page.tsx
@frontend/src/app/(auth)/login/login-form.tsx
@frontend/src/app/(auth)/__tests__/login.test.tsx
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add DEMO_MODE-gated POST /auth/demo-login route</name>
  <files>backend/app/auth/router.py</files>
  <behavior>
    - DEMO_MODE off (default): POST /auth/demo-login returns 404 (route hidden/blocked, not 500).
    - DEMO_MODE on: returns 200 with a Set-Cookie: xpredict_session=...; HttpOnly; SameSite=lax header.
    - DEMO_MODE on: a NEW user is created each call with email matching demo-<uuid>@demo.local, is_verified=True, is_active=True.
    - DEMO_MODE on: the new user's wallet is funded with the signup bonus (granted by manager.on_after_register in demo mode — NOT a second grant in the route).
    - DEMO_MODE on: an audit row auth.demo_session_started (or auth.session_started) is written for the new user.
    - The route is rate-limited 5/minute per IP via @limiter.limit (6th call from same IP -> 429).
  </behavior>
  <action>
Add `import secrets` and a `demo_login_proxy` route to `auth_proxy_router` in `backend/app/auth/router.py`, placed after `login_proxy` (per locked user decisions).

Gate FIRST: at the top of the body call `if not get_settings().DEMO_MODE: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")`. Read the flag dynamically via `get_settings().DEMO_MODE` (NOT the module-level `settings` captured at import) so tests can toggle it via env + `get_settings.cache_clear()`. Use 404 (not 403) so the endpoint is invisible in white-label/prod.

Decorate with `@limiter.limit("5/minute", key_func=get_remote_address)` exactly mirroring the other proxy routes (per locked decision: reuse existing slowapi pattern). The signature takes `request: Request` first (slowapi requires it) plus `user_manager: Annotated[UserManager, Depends(get_user_manager)]`.

Build the ephemeral user: `email = f"demo-{uuid.uuid4().hex}@demo.local"` (uuid is already imported at module top) and `password = secrets.token_urlsafe(24)` (strong random; >= 6 chars so it passes DEMO_MODE's relaxed validate_password, and >= 12 so it would pass even if the flag flipped). Construct `user_create = UserCreate(email=email, password=password)` (UserCreate is already imported). Then `user = await user_manager.create(user_create, safe=True, request=request)`. This single call auto-verifies the user and grants the signup bonus because DEMO_MODE is on (see manager.py create() line 112 and on_after_register() lines 202-221) — do NOT call WalletService.grant_signup_bonus again.

Issue the session cookie EXACTLY like login_proxy (locked decision): `strategy = get_database_strategy()` then `response = await player_backend.login(strategy, user)`.

Write the audit row mirroring login_proxy's independent-session pattern (lines 170-181): open `_get_audit_session_factory()`, `AuditService.record(session, actor=f"user:{user.id}", event_type="auth.demo_session_started", payload={"email": user.email}, ip=client_ip)`, then `await session.commit()`. Use event_type `auth.demo_session_started` to keep demo sessions distinguishable in the audit log (consistent with existing audit usage).

Return `response`. Do NOT call `check_email_limit` (each email is unique per click, so per-email limiting is meaningless here — the per-IP @limiter decorator is the anti-farming guard the locked decision asks for).

Do NOT add the path to `_PROXY_OWNED_PATHS` (that set only strips fastapi-users duplicate routes; /demo-login has no fastapi-users equivalent).
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/auth/test_demo_login.py -x -q</automated>
  </verify>
  <done>POST /auth/demo-login: 404 when DEMO_MODE off; 200 + xpredict_session cookie when on; creates a demo-&lt;uuid&gt;@demo.local verified+active user with a funded wallet; writes an auth.demo_session_started audit row; rate-limited (6th call -> 429). Test file from Task 2 passes.</done>
</task>

<task type="auto">
  <name>Task 2: Backend integration tests for demo-login</name>
  <files>backend/tests/auth/test_demo_login.py</files>
  <action>
Create `backend/tests/auth/test_demo_login.py` mirroring the structure of `backend/tests/auth/test_login.py` and `test_rate_limit.py` (same `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]`, same `_client_for_engine()` / ASGITransport helper, same `engine` fixture, same `_cleanup_user` style cleanup by email prefix).

Toggle DEMO_MODE per test using the codebase pattern (see test_create_admin_script.py: `get_settings.cache_clear()`): a helper or fixture that does `monkeypatch.setenv("DEMO_MODE", "true")` then `from app.core.config import get_settings; get_settings.cache_clear()`, and restores by clearing the env + cache_clear() on teardown. Because `get_settings()` is lru_cached and both the route and the UserManager read `get_settings().DEMO_MODE` dynamically at request time, clearing the cache after setting the env is what makes the flag take effect. Clean up created `demo-%@demo.local` rows after each test (DELETE FROM users WHERE email LIKE 'demo-%@demo.local').

Cover (per locked decision — backend tests MUST cover flag off hidden/blocked, flag on 200+cookie+verified+bonus):
1. test_demo_login_404_when_flag_off — with DEMO_MODE off (default), POST /auth/demo-login returns 404.
2. test_demo_login_creates_verified_funded_user_when_on — with DEMO_MODE on: response is 200; Set-Cookie contains `xpredict_session=`, `HttpOnly`, SameSite=lax; a subsequent GET /auth/users/me using the same client returns 200 (proves the user is verified — the verified=True gate passes) with an email matching `demo-...@demo.local`.
3. test_demo_login_grants_signup_bonus — with DEMO_MODE on, after demo-login, assert the new user's wallet balance equals SIGNUP_BONUS_AMOUNT. Find the user id by querying `SELECT id FROM users WHERE email LIKE 'demo-%@demo.local' ORDER BY created_at DESC LIMIT 1` (or read it from GET /auth/users/me), then assert the wallet/ledger reflects the bonus. Reuse whatever balance-assertion approach exists in the wallet or signup-bonus tests (see backend/tests/auth/test_signup_bonus_on_verify.py for the established query/balance pattern) — match that, do not invent a new ledger query shape.
4. test_demo_login_rate_limited — with DEMO_MODE on, 5 calls do NOT 429, the 6th returns 429 (mirror test_rate_limit.py's 5-then-6th assertion). Note the autouse `_reset_rate_limit_storage` fixture in conftest.py resets the limiter between tests.

Do NOT touch any files under backend/tests/bets/.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/auth/test_demo_login.py -q</automated>
  </verify>
  <done>All four tests pass against testcontainers Postgres + memory:// slowapi storage. Tests prove: flag off -> 404; flag on -> 200 + cookie + verified user; bonus funded; rate-limited.</done>
</task>

<task type="auto">
  <name>Task 3: Frontend "Probar la demo" button + login-page wiring + test</name>
  <files>frontend/src/app/(auth)/login/demo-login-button.tsx, frontend/src/app/(auth)/login/page.tsx, frontend/src/app/(auth)/__tests__/demo-login.test.tsx</files>
  <action>
Create `frontend/src/app/(auth)/login/demo-login-button.tsx` as a `"use client"` component named `DemoLoginButton`. Follow the existing client-component + Button conventions used by login-form.tsx (import `Button` from `@/components/ui/button`). The button label is the Spanish copy "Probar la demo" (UI copy is Spanish per project convention; identifiers stay English).

Behavior: on click, set a local `pending` state, `await fetch("/auth/demo-login", { method: "POST", credentials: "include" })`. The frontend talks to the backend through the same origin/proxy the existing actions assume; do NOT hardcode a backend host in the client — POST to the relative `/auth/demo-login` path (the dev proxy / rewrite that already routes /auth/* to the backend handles it; if the project instead routes through a Next route handler, follow whatever the existing client-side auth calls do — check how the app reaches /auth/* from the browser and match it). On a successful response (`res.ok`), navigate to `/markets` using `useRouter().push("/markets")` from `next/navigation`. On failure, show a small inline error (reuse the red text style from login-form.tsx's `data-testid="form-error"` block, e.g. data-testid="demo-error"). Disable the button while pending and show a pending label ("Cargando…").

Gate rendering: the button must only render when demo mode is exposed to the client. Use the existing `NEXT_PUBLIC_DEMO_MODE` env flag (already used by registerAction in frontend/src/lib/auth.ts line 211): render the button only when `process.env.NEXT_PUBLIC_DEMO_MODE === "true"`. Implement the gate in the SERVER component (page.tsx) — read the env var there and conditionally render `<DemoLoginButton />` — so the env check is evaluated at the right boundary and the button is fully absent (not just hidden) when the flag is off.

Edit `frontend/src/app/(auth)/login/page.tsx`: import `DemoLoginButton`, and after `<LoginForm />` add `{process.env.NEXT_PUBLIC_DEMO_MODE === "true" && <DemoLoginButton />}`. Keep the existing layout/spacing classes consistent (it sits inside the same `space-y-6` container). Optionally add a small "or" divider above it to match the page's visual rhythm, but keep it minimal.

Create `frontend/src/app/(auth)/__tests__/demo-login.test.tsx` mirroring login.test.tsx (vitest + @testing-library/react + jsdom, mock `next/navigation`'s `useRouter`/`redirect`, mock `global.fetch`). Cover: (1) renders a button with the text /probar la demo/i; (2) clicking it POSTs to /auth/demo-login and, on a mocked ok response, calls router.push("/markets"); (3) on a mocked non-ok response, shows the demo-error inline message. Test the DemoLoginButton component directly (the env-gate lives in page.tsx, so the component test does not need the env flag).

Do NOT touch any files under frontend/src/app/portfolio/.
  </action>
  <verify>
    <automated>cd frontend && pnpm vitest run src/app/(auth)/__tests__/demo-login.test.tsx</automated>
  </verify>
  <done>DemoLoginButton renders "Probar la demo", POSTs to /auth/demo-login on click, pushes to /markets on success, shows an inline error on failure; the button is gated behind NEXT_PUBLIC_DEMO_MODE in page.tsx. Vitest test passes.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser -> POST /auth/demo-login | Unauthenticated public request that mints a verified, bonus-funded account |
| /auth/demo-login -> ledger | Each call credits the signup bonus to a fresh wallet (house_promo -> user_wallet) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-demo-01 | Denial of Service / abuse | POST /auth/demo-login | mitigate | Endpoint gated by DEMO_MODE (default False) — invisible (404) in white-label/prod; @limiter.limit("5/minute", key_func=get_remote_address) caps farming of bonus-funded users per IP (locked decision) |
| T-demo-02 | Information disclosure | DEMO_MODE off response | mitigate | Return 404 (not 403/500) so the endpoint's existence is not revealed in production deployments |
| T-demo-03 | Elevation of privilege | Ephemeral user creation | mitigate | UserCreate via user_manager.create(..., safe=True) — safe flag prevents setting is_superuser; user is a plain verified player only |
| T-demo-04 | Tampering | Ledger / bonus grant | accept | Bonus is granted via the existing idempotent grant_signup_bonus (key bonus:{user_id}); per-click unique user means no double-credit. Demo users accumulate in DB by design (locked decision: no cleanup task) |
</threat_model>

<verification>
- Backend: `cd backend && uv run pytest tests/auth/test_demo_login.py -q` — all pass.
- Backend regression (no breakage to existing auth routes): `cd backend && uv run pytest tests/auth/test_login.py tests/auth/test_rate_limit.py -q`.
- Frontend: `cd frontend && pnpm vitest run src/app/(auth)/__tests__/demo-login.test.tsx` — passes.
- Manual sanity (optional): with DEMO_MODE=true backend + NEXT_PUBLIC_DEMO_MODE=true frontend, the login page shows "Probar la demo"; clicking it lands you in /markets with a funded wallet.
- No files under backend/app/bets/*, backend/tests/bets/*, or frontend/src/app/portfolio/* were modified.
</verification>

<success_criteria>
- POST /auth/demo-login returns 404 when DEMO_MODE is off (default) and 200 + xpredict_session cookie when on.
- Each demo-login creates a unique demo-<uuid>@demo.local user that is verified, active, and has a wallet funded with the signup bonus.
- The endpoint is rate-limited (6th call from one IP -> 429) and writes an auth.demo_session_started audit row.
- The login page renders a "Probar la demo" button only when NEXT_PUBLIC_DEMO_MODE is "true"; clicking it POSTs to the endpoint and redirects to /markets on success.
- Both backend and frontend tests pass; no migrations, no JWT changes, no bets/portfolio files touched.
</success_criteria>

<output>
Create `.planning/quick/260611-lcr-one-click-demo-access-auth-demo-login-de/260611-lcr-01-SUMMARY.md` when done.
</output>
