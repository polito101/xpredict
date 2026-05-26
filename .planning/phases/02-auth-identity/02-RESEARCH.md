# Phase 2: Auth & Identity - Research

**Researched:** 2026-05-26
**Domain:** Self-hosted authentication (FastAPI + Next.js 15 App Router) with dual-backend pattern (player cookie + admin Bearer), email verification, password reset, refresh-token rotation with DB-backed reuse detection, and per-IP + per-email rate limiting.
**Confidence:** HIGH on stack, architecture, and pitfalls; MEDIUM on exact OWASP Argon2 tuning (numbers vary by host RAM); LOW on no items.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Auth Library**
- **D-01: fastapi-users v14** — battle-tested, dual-backend pattern (cookie player + Bearer admin), Argon2id built-in, email verify + password reset out of the box. Saves ~400 lines of boilerplate vs hand-rolling.
- **D-02: Herencia múltiple `User(SQLAlchemyBaseUserTableUUID, Base)`** — patrón oficial de fastapi-users. Nuestro `User` hereda de su base (`SQLAlchemyBaseUserTableUUID`) y de nuestro `DeclarativeBase` (`app.db.base.Base`). `tenant_id` ghost column se añade normalmente como columna adicional.
- **D-03: Dos instancias FastAPIUsers separadas** — una con `CookieTransport + JWTStrategy` para players (prefijo `/auth/`), otra con `BearerTransport + JWTStrategy` para admin (prefijo `/admin/auth/`). El guard `is_superuser` se aplica en todos los routers `/admin/*`.
- **D-04: `DatabaseStrategy` custom con tabla `refresh_tokens`** — en lugar de `JWTStrategy` puro. Tabla: `(id, token_hash, user_id, expires_at, revoked_at, reuse_count)`. Reuse detection: si llega un token ya rotado, se revocan TODOS los tokens del usuario. Cumple AUTH-09 (revocación verificable en DB + éxito criteria #3 y #4 de ROADMAP).

> **Researcher note on D-01 — version drift detected.** CONTEXT.md says "v14" but PyPI's latest is **fastapi-users 15.0.5** (released 2024-10-25, security patches through 2025-03-27). v15 dropped Python 3.9 + Pydantic v1 — both already required by our stack (Python 3.12 + Pydantic 2). The dual-backend, custom strategy, and email-hook APIs are unchanged v14→v15. **Recommendation:** install `fastapi-users[sqlalchemy] >=15.0.5,<16.0.0` instead of v14. Library is officially in maintenance mode (no new features, only security + dep updates) — v14 will not get back-ports. This is the same code path D-01 chose; only the version pin changes. Surface to Pol in discuss-checker or accept as a minor planning correction. `[ASSUMED]` until Pol confirms.

**Email SMTP**
- **D-05: Resend como proveedor** para staging y producción (free tier 3000/mes, SDK Python oficial, excelente deliverability). Mailpit para dev (ya operativo desde Phase 1 en docker-compose).
- **D-06: `ResendEmailSender` custom** — implementa el protocolo `BaseEmailSender` de fastapi-users. Switch por `ENVIRONMENT` env var: `dev` → Mailpit SMTP, `staging`/`prod` → Resend API. Un solo punto de configuración.
- **D-07: HTML simple inline** para templates de email (sin Jinja2 ni ficheros separados). Branding básico (nombre del proyecto + link prominente). Phase 10 añade branding configurable si es necesario.

> **Researcher correction on D-06 — fastapi-users does not expose a `BaseEmailSender` protocol.** Verified against the v15 source: email dispatch lives in **`UserManager` lifecycle hooks** (`on_after_register`, `on_after_request_verify`, `on_after_forgot_password`). The "custom sender" is a regular Python class injected into `UserManager.__init__` and called from those hooks. No fastapi-users protocol to satisfy. The intent of D-06 is preserved — a single switchable email service — only the implementation shape changes. See §"Code Examples" below for the exact pattern. `[VERIFIED: github.com/fastapi-users/fastapi-users/blob/master/docs/configuration/user-manager.md]`

**Users Table Schema**
- **D-08: Schema completo en Phase 2** — la migración `0002_phase2_auth` crea la tabla `users` con todos los campos necesarios para las fases actuales y futuras:
  - Campos fastapi-users built-in: `id UUID PK`, `email TEXT UNIQUE`, `hashed_password TEXT`, `is_active BOOLEAN DEFAULT TRUE`, `is_superuser BOOLEAN DEFAULT FALSE`, `is_verified BOOLEAN DEFAULT FALSE`
  - Campos adicionales: `display_name TEXT nullable`, `banned_at TIMESTAMPTZ nullable` (Phase 8 lo usa), `token_version INT DEFAULT 0` (para invalidar sesiones en password reset), `tenant_id UUID nullable DEFAULT TENANT_DEFAULT`
  - Tabla `refresh_tokens`: `(id, token_hash TEXT UNIQUE, user_id UUID FK users, expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ nullable, reuse_count INT DEFAULT 0, created_at TIMESTAMPTZ)`
- **D-09: `is_superuser` internamente, `is_admin` en la API** — fastapi-users usa `is_superuser` en su lógica interna. Los Pydantic schemas de respuesta exponen `is_admin: bool` mapeando desde `is_superuser`. No se parchea fastapi-users.
- **D-10: `display_name` nullable** — incluido ahora para que Phase 3 (wallet) y Phase 8 (CRM) no necesiten ALTER TABLE.

**Admin Bootstrapping**
- **D-11: Script de seeding `bin/create-admin.py`** — lee `FIRST_ADMIN_EMAIL` y `FIRST_ADMIN_PASSWORD` del entorno, hashea con Argon2id, inserta en `users` con `is_superuser=True`. Idempotente (no falla si ya existe). Se documenta en README. Añadir `FIRST_ADMIN_EMAIL` + `FIRST_ADMIN_PASSWORD` a `.env.example`.

**Frontend Auth**
- **D-12: Rutas Next.js dedicadas** — páginas full-page con App Router: `/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email`. URLs compartibles + linkables desde emails de verify/reset. shadcn/ui `Form` + `Input` + `Button`.
- **D-13: Panel admin en `/admin/*`** — mismo Next.js, layout separado `app/admin/` con su propia navbar. Next.js middleware protege las rutas `/admin/*` comprobando el Bearer JWT. Un solo deploy.

**Rate Limiting**
- **D-14: slowapi + Redis ya instalado** (Phase 1). Montar `SlowAPIMiddleware` en `main.py` en Phase 2. Límites AUTH-08: 5 intentos/minuto por IP + 5 intentos/minuto por email en `/auth/login`, `/auth/register`, `/auth/forgot-password`, `/auth/verify-email`. El 6º intento → 429 sin información leak sobre si el email existe.

### Claude's Discretion

CONTEXT.md does not enumerate explicit discretion items — every architectural choice is locked above. The researcher's discretion areas (recommendations the planner can refine) are:

- Exact Argon2id `memory_cost` / `time_cost` (OWASP gives two equally-valid options; this RESEARCH recommends one — planner may pick the other).
- Token lifetimes (access 15 min, refresh 30 days are common; planner may tune).
- Redis key prefix conventions for slowapi storage.
- Whether to use Next.js Server Actions (recommended by Next 15 docs) or pure client-side fetch for the login form.
- Email subject lines and HTML body wording.

### Deferred Ideas (OUT OF SCOPE)

- **Wallet creation on registration** — Phase 3 crea la tabla `accounts`; el hook post-register que crea el wallet se implementa allí.
- **Sign-up bonus (1000 PLAY_USD)** — WAL-02, Phase 5 (triggered on email verify, debits ledger).
- **Ban/unban UI y lógica** — ADU-04/05, Phase 8. Los campos `is_active` y `banned_at` se crean ahora (nullable) para evitar ALTER TABLE en Phase 8.
- **Branding configurable en emails** — Phase 10 añade TenantConfig; el HTML inline de Phase 2 es suficiente para la demo.
- **OAuth / social login** — out of scope v1.
- **Passkeys / WebAuthn** — out of scope v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Player can register with email + password (Argon2id hashed, server-side validation, password strength enforced) | fastapi-users v15 + pwdlib 0.3.0 Argon2Hasher (default type=ID); see §"Standard Stack" + §"Password Strength Validation" |
| AUTH-02 | Player receives email verification message after signup (Mailpit dev; real SMTP staging) | `UserManager.on_after_register` → `request_verify(user)`; SMTP via `aiosmtplib` to Mailpit (dev), Resend SDK (staging/prod); see §"Email Architecture" |
| AUTH-03 | Player can verify email by clicking single-use, time-limited link | fastapi-users built-in `POST /auth/verify` route + `verification_token_lifetime_seconds`; see §"fastapi-users Routes" |
| AUTH-04 | Player can log in with email + password; session persists across browser refresh | Cookie backend with `CookieTransport(cookie_max_age=N, cookie_httponly=True, cookie_secure=...)` + custom `DatabaseStrategy`; see §"Dual Backend Setup" |
| AUTH-05 | Player can log out from any page (server-side session/token revoked) | `POST /auth/logout` → `DatabaseStrategy.destroy_token` writes `revoked_at`; see §"Custom DatabaseStrategy" |
| AUTH-06 | Player can reset password via email link (single-use token; bumps token_version, invalidates prior sessions) | `UserManager.on_after_forgot_password` → email; `on_after_reset_password` → increment `token_version`; `DatabaseStrategy.read_token` rejects tokens where stored `token_version` < user's current; see §"Password Reset Flow" |
| AUTH-07 | Admin uses separate login route and `is_admin` flag; admin auth surface is distinct from player auth surface | Second `FastAPIUsers` instance with `BearerTransport` mounted at `/admin/auth/*`; `current_user(superuser=True)` guard on `/admin/*`; see §"Dual Backend Setup" |
| AUTH-08 | All auth endpoints rate-limited per IP and per email via slowapi + Redis | Two stacked `@limiter.limit("5/minute", key_func=...)` decorators on each endpoint (per-IP + per-email key funcs); `storage_uri="redis://..."`; see §"Rate Limiting" |
| AUTH-09 | Refresh token rotation with reuse detection; HTTP-only Secure cookies for player session, Bearer JWT for admin API access | Custom `DatabaseStrategy` writes `refresh_tokens` row on issue; on `read_token` if `revoked_at IS NOT NULL` → revoke ALL user's tokens (reuse attack pattern); see §"Custom DatabaseStrategy" |
</phase_requirements>

## Summary

Phase 2 ships a production-grade, self-hosted auth surface for **XPredict** by adopting **fastapi-users v15** (CONTEXT.md locks v14 — see version-drift note: 15.0.5 is current, 14→15 is backward-compatible for our usage) with two cleanly separated `FastAPIUsers` instances: a **player surface** at `/auth/*` using `CookieTransport` + a custom `DatabaseStrategy` (refresh-token rotation + reuse detection in Postgres), and an **admin surface** at `/admin/auth/*` using `BearerTransport` + the same custom `DatabaseStrategy`. Both share a single `User` SQLAlchemy model that inherits from `SQLAlchemyBaseUserTableUUID` plus our `Base`, gaining the standard fastapi-users columns (`id UUID`, `email`, `hashed_password`, `is_active`, `is_superuser`, `is_verified`) and adding XPredict-specific columns (`display_name nullable`, `banned_at nullable`, `token_version int DEFAULT 0`, `tenant_id` ghost). Password hashing uses **pwdlib 0.3.0** (which fastapi-users pins exactly) with Argon2id as the default and bcrypt as a backwards-compat verifier — no custom hasher needed. Email verification + password reset use the four built-in `UserManager` lifecycle hooks (`on_after_register`, `on_after_request_verify`, `on_after_forgot_password`, `on_after_reset_password`); a single `EmailService` switches by `ENVIRONMENT` (Mailpit SMTP in dev via `aiosmtplib`; Resend SDK `send_async` in staging/prod). Rate limiting stacks two `@limiter.limit("5/minute", key_func=...)` decorators per endpoint (one keyed on IP via `get_remote_address`, one on the request body's email field) with `storage_uri="redis://redis:6379/1"` so the limits survive across worker processes. The frontend (Next.js 15 App Router) talks to the backend via `fetch` with `credentials: "include"` (cookie auto-flows from the FastAPI `Set-Cookie` header); the admin surface stores the Bearer token in a separate HTTP-only cookie set by a Next.js Server Action (so middleware can read it on every `/admin/*` route).

**Primary recommendation:** Pin `fastapi-users[sqlalchemy] >=15.0.5,<16.0.0` (one minor adjustment from CONTEXT D-01's "v14"), use pwdlib's defaults via `PasswordHash.recommended()` (already Argon2id), and implement the custom `DatabaseStrategy` exactly as documented in §"Custom DatabaseStrategy" — it's ~80 lines and fully self-contained.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Password hashing (Argon2id) | API / Backend | — | Hashing must happen server-side; password never leaves the server unhashed. pwdlib is FastAPI-side. |
| Email verification token issue + verify | API / Backend | — | Tokens are signed/verified with `SECRET` env var; only backend holds it. |
| Email delivery (Mailpit / Resend) | API / Backend | External SMTP service | Backend builds + sends; SMTP is the transport. |
| Cookie session (player) | API / Backend | Browser | FastAPI sets `Set-Cookie`; browser stores and re-sends. Next.js does NOT need to touch the cookie if proxying via `credentials: "include"`. |
| Bearer session (admin) | API / Backend + Frontend Server (SSR) | Browser | Admin Bearer token must travel via `Authorization: Bearer` header. Stored in an HTTP-only cookie set by Next.js Server Action; Next.js middleware reads cookie + injects header on backend fetches. |
| Refresh-token rotation + reuse detection | API / Backend | Database (Postgres) | DB row is the source of truth; backend writes/revokes. |
| Rate limiting (per IP + per email) | API / Backend | Redis | slowapi runs in FastAPI; Redis stores counters across worker processes. |
| Password strength validation | API / Backend | Frontend (UX hint) | Server is the gatekeeper (UI may pre-validate for UX, but backend MUST re-validate). |
| Login UI / form rendering | Frontend Server (SSR) | Browser | Next.js Server Components render `/login`, `/register`, etc.; Server Actions handle form POSTs and forward to FastAPI. |
| Admin route protection | Frontend Server (SSR) | API / Backend | Next.js middleware does **optimistic** Bearer JWT check (signature + exp via `jose`); FastAPI enforces with `current_user(superuser=True)` on every `/admin/*` endpoint (defense-in-depth). |
| `is_superuser → is_admin` mapping | API / Backend | — | Pydantic schemas at the API edge; ORM keeps `is_superuser` per fastapi-users convention. |
| First-admin bootstrap | API / Backend (CLI) | — | `bin/create-admin.py` reads env vars and writes a single row; runs once at deploy. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi-users[sqlalchemy]` | `>=15.0.5,<16.0.0` | Auth scaffolding: User model base, JWT/cookie/bearer transports, routers, hooks, password hashing wrapper | Battle-tested, dual-backend supported, maintenance mode but actively patched. Saves ~400 LOC. CONTEXT D-01 says "v14"; v15 is current and API-compatible for our needs. `[VERIFIED: pypi.org/project/fastapi-users + github.com/fastapi-users/fastapi-users/releases]` |
| `pwdlib[argon2,bcrypt]` | `==0.3.0` | Argon2id + bcrypt password hashing | Bundled transitively by fastapi-users (exact pin); defaults to Argon2id (`argon2.Type.ID`); has built-in bcrypt fallback for any rare legacy hash. `[VERIFIED: github.com/frankie567/pwdlib/blob/main/pwdlib/hashers/argon2.py]` |
| `argon2-cffi` | `>=23.1.0` (transitive) | Native Argon2id implementation | Underlying lib for pwdlib's Argon2 hasher; current PyPI is 25.1.0. `[VERIFIED: pypi.org]` |
| `PyJWT[crypto]` | `>=2.12.0,<3.0.0` (transitive) | JWT signing/verification | fastapi-users v15 requires it; current PyPI is 2.13.0. HS256 is the default algorithm; cryptography backend is included via `[crypto]` extra. `[VERIFIED: pypi.org + github.com/fastapi-users/fastapi-users/blob/master/pyproject.toml]` |
| `slowapi` | `>=0.1.9,<0.2` | Rate limiting middleware + decorators with Redis backend | Already installed in Phase 1 `pyproject.toml` (not yet mounted). Supports stacked decorators (per-IP + per-email), custom `key_func` per decorator, Redis via `storage_uri`. `[VERIFIED: pypi.org + raw.githubusercontent.com/laurentS/slowapi/master/slowapi/extension.py]` |
| `resend` | `>=2.30.0,<3.0` | Resend.com Python SDK for staging/prod email | Has async support via `[async]` extra; `await resend.Emails.send_async(params)`. Current PyPI 2.30.1. `[VERIFIED: pypi.org + github.com/resend/resend-python]` |
| `aiosmtplib` | `>=4.0,<5.0` | Async SMTP client for dev → Mailpit | Standard async SMTP; lightweight; Mailpit speaks plain SMTP on port 1025 (no auth, no TLS in dev). `[VERIFIED: pypi.org/project/aiosmtplib]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `email-validator` | `>=2.2,<3` (transitive) | RFC 5322 email validation used by pydantic's `EmailStr` | Already pulled in by `pydantic[email]` if we use `EmailStr`. Explicit pin avoids surprises. `[VERIFIED: pypi.org]` |
| `password-strength` | (not used) | — | Don't add — pwdlib does not validate strength, only hashes. Strength is enforced via pydantic validator on the schema (see §"Password Strength Validation"). |

### Frontend

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `next` | `^15.5.18` | App Router framework | Already pinned in Phase 1. `[VERIFIED: frontend/package.json]` |
| `jose` | `^5.9.0` | JWT verification in Next.js middleware (Edge runtime) | Standard library Next.js docs recommend for middleware. Pure Web Crypto, works in both Edge and Node runtimes. `[CITED: nextjs.org/docs/app/guides/authentication#stateless-sessions]` |
| `zod` | `^3.23.0` | Form schema validation in Server Actions | Recommended by Next 15 auth docs for `safeParse` in signup/login forms. `[CITED: nextjs.org/docs/app/guides/authentication#validate-form-fields-on-the-server]` |
| `@hookform/resolvers` + `react-hook-form` | latest | Form state management with `useActionState` integration | Standard pairing with zod + shadcn `Form`. shadcn's `Form` primitives are built on react-hook-form. `[CITED: ui.shadcn.com/docs/components/form]` |
| `shadcn/ui` Form, Input, Button | latest (manual copy-in) | Existing UI primitives | CONTEXT D-12 specifies shadcn; install via `pnpm dlx shadcn@latest add form input button label`. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| fastapi-users | Hand-rolled FastAPI auth (raw PyJWT + sqlalchemy) | -400 LOC saved by fastapi-users; +complete control. Verdict: fastapi-users wins given Phase 2's tight scope. |
| pwdlib | `passlib[argon2]` | passlib is legacy/abandoned; pwdlib is the modern successor (same author, maintained alongside fastapi-users). Verdict: pwdlib. `[VERIFIED: frankie567.github.io/pwdlib]` |
| slowapi | `fastapi-limiter` | fastapi-limiter is async-native but lacks per-route shared limits + multiple-decorator stacking. slowapi already installed in Phase 1. Verdict: slowapi. |
| Resend | SendGrid, Postmark | Resend has the simplest free tier (3000/mo) and best DX. Postmark is great for transactional but $$$. CONTEXT D-05 locked. |
| Next.js middleware with `jose` | NextAuth.js | NextAuth would replace fastapi-users on the frontend; double-storage of identity. CONTEXT D-12/D-13 prefer Next.js owning only UI + middleware. |
| Two `FastAPIUsers` instances | One instance with two backends in a list | Single instance with `[cookie_backend, bearer_backend]` makes `current_user` accept either token type on the same route — wrong for our model (admin Bearer must NOT authenticate against player endpoints). Two separate instances enforce a hard boundary. `[VERIFIED: github.com/fastapi-users/fastapi-users/discussions/989]` |

**Installation:**

```bash
# Backend — add to backend/pyproject.toml [project.dependencies]:
"fastapi-users[sqlalchemy] >=15.0.5,<16.0.0",
"resend[async] >=2.30.0,<3.0",
"aiosmtplib >=4.0,<5.0",
# argon2-cffi, pwdlib, PyJWT, email-validator come transitively

# Then:
uv lock && uv sync
```

```bash
# Frontend — add to frontend/package.json [dependencies]:
"jose": "^5.9.0",
"zod": "^3.23.0",
"react-hook-form": "^7.53.0",
"@hookform/resolvers": "^3.9.0"

# Then:
pnpm install
pnpm dlx shadcn@latest add form input button label card
```

**Version verification (run before locking):**

```bash
# Verified 2026-05-26 via pip:
fastapi-users: 15.0.5 (latest)
slowapi: 0.1.9 (latest)
argon2-cffi: 25.1.0 (latest; satisfies pwdlib transitive >=23.1.0)
resend: 2.30.1 (latest)
pwdlib: 0.3.0 (exact pin from fastapi-users v15)
pyjwt: 2.13.0 (latest; in [2.12, 3.0) range)
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `fastapi-users` | PyPI | 6 yrs (since 2019) | 700K+/mo | github.com/fastapi-users/fastapi-users | [OK] | Approved |
| `pwdlib` | PyPI | ~2 yrs (since 2023) | 600K+/mo (pulled by fastapi-users) | github.com/frankie567/pwdlib | [OK] (transitive) | Approved |
| `argon2-cffi` | PyPI | 8 yrs (since 2017) | 50M+/mo | github.com/hynek/argon2-cffi | [OK] | Approved |
| `PyJWT` | PyPI | 13 yrs (since 2012) | 100M+/mo | github.com/jpadilla/pyjwt | [OK] (transitive) | Approved |
| `slowapi` | PyPI | 5 yrs (since 2020) | 500K+/mo | github.com/laurentS/slowapi | [OK] | Approved (already in Phase 1) |
| `resend` | PyPI | 2 yrs (since 2023) | 800K+/mo | github.com/resend/resend-python | [OK] | Approved |
| `aiosmtplib` | PyPI | 9 yrs (since 2016) | 5M+/mo | github.com/cole/aiosmtplib | [OK] | Approved |
| `email-validator` | PyPI | 9 yrs (since 2016) | 100M+/mo (pulled by pydantic) | github.com/JoshData/python-email-validator | [OK] (transitive) | Approved |
| `jose` (Node) | npm | 8 yrs (since 2018) | 10M+/wk | github.com/panva/jose | [OK] (assumed — slopcheck is PyPI; verified via npm view) | Approved |
| `zod` (Node) | npm | 5 yrs (since 2020) | 30M+/wk | github.com/colinhacks/zod | [OK] | Approved |
| `react-hook-form` (Node) | npm | 6 yrs (since 2019) | 12M+/wk | github.com/react-hook-form/react-hook-form | [OK] | Approved |
| `@hookform/resolvers` (Node) | npm | 5 yrs (since 2020) | 7M+/wk | github.com/react-hook-form/resolvers | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

*slopcheck CLI ran clean against `fastapi-users argon2-cffi slowapi resend` and `fastapi-users-db-sqlalchemy`: all [OK]. Node packages were verified via known authoritative documentation (Next.js docs recommend jose + zod; shadcn docs recommend react-hook-form).*

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Browser (Player)                                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                          GET /login (Next.js page)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│         Next.js 15 App Router (Server Components + Server Actions)       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ Routes (D-12):  /login  /register  /forgot-password           │   │
│  │                 /reset-password  /verify-email                 │   │
│  │ Server Actions: signup(formData) → fetch FastAPI               │   │
│  │ Middleware:     middleware.ts → guards /admin/* (jose verify)  │   │
│  │ Cookie store:   cookies().get('session') / .set('admin_jwt')   │   │
│  └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
            HTTP (fetch with credentials: "include")
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend (app/auth/*)                       │
│  ┌──────────────────────────────────┐  ┌────────────────────────────┐ │
│  │ SlowAPIMiddleware (Redis)        │  │ RequestIdMiddleware (P1)   │ │
│  │  - per-IP + per-email decorators │  │  - request_id contextvar   │ │
│  └────────────────┬─────────────────┘  └────────────────────────────┘ │
│                   │                                                      │
│                   ▼                                                      │
│  ┌──────────────────────────────────┐  ┌────────────────────────────┐ │
│  │ FastAPIUsers[User, UUID]         │  │ FastAPIUsers[User, UUID]   │ │
│  │  (PLAYER, prefix=/auth)          │  │ (ADMIN, prefix=/admin/auth)│ │
│  │                                  │  │                            │ │
│  │  CookieTransport(httponly,       │  │  BearerTransport           │ │
│  │   secure=is_prod, samesite=lax)  │  │   (tokenUrl=admin/auth/    │ │
│  │   + DatabaseStrategy (custom)    │  │      login)                │ │
│  │                                  │  │   + DatabaseStrategy       │ │
│  │  Routes:                         │  │     (custom)               │ │
│  │   POST /auth/register            │  │                            │ │
│  │   POST /auth/login               │  │  Routes:                   │ │
│  │   POST /auth/logout              │  │   POST /admin/auth/login   │ │
│  │   POST /auth/verify              │  │   POST /admin/auth/logout  │ │
│  │   POST /auth/request-verify-tok  │  │                            │ │
│  │   POST /auth/forgot-password     │  │  Guard:                    │ │
│  │   POST /auth/reset-password      │  │   current_user(            │ │
│  │   GET  /auth/users/me            │  │     superuser=True)        │ │
│  │   PATCH /auth/users/me           │  │   on every /admin/*        │ │
│  └────────────┬─────────────────────┘  └────────────────────────────┘ │
│               │                                                          │
│               ▼                                                          │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ UserManager(SQLAlchemyUserDatabase, UUIDIDMixin)                │   │
│  │  - validate_password (length, complexity, dictionary)           │   │
│  │  - on_after_register(user, request)                             │   │
│  │      → request_verify(user) → schedules email                  │   │
│  │  - on_after_request_verify(user, token, request) → email       │   │
│  │  - on_after_forgot_password(user, token, request) → email      │   │
│  │  - on_after_reset_password(user, request) → ++token_version,  │   │
│  │      revoke all refresh_tokens for user                        │   │
│  └────────────┬───────────────────────────────────┬───────────────┘   │
│               │                                   │                     │
│               ▼                                   ▼                     │
│  ┌──────────────────────────┐    ┌──────────────────────────────┐   │
│  │ EmailService (env switch) │    │ DatabaseStrategy (custom)    │   │
│  │  if ENVIRONMENT=='dev':   │    │  read_token(t)               │   │
│  │    aiosmtplib → Mailpit   │    │   → SELECT * WHERE           │   │
│  │  else:                    │    │     token_hash=sha256(t)     │   │
│  │    resend.send_async()    │    │   → if revoked_at IS NOT NULL│   │
│  └──────────┬───────────────┘    │     → REVOKE ALL user tokens │   │
│             │                    │     (reuse attack mitigation)│   │
│             ▼                    │   → check user.token_version │   │
│  ┌──────────────────────────┐    │  write_token(user)           │   │
│  │ External (Resend / Mail- │    │   → INSERT row, hash 64 char │   │
│  │ pit) — outside boundary  │    │  destroy_token(t, user)      │   │
│  └──────────────────────────┘    │   → UPDATE revoked_at=NOW()  │   │
│                                  └──────────────┬───────────────┘   │
│                                                 │                    │
│  ┌──────────────────────────────────────────────▼────────────────┐ │
│  │ AuditService.record(session, actor=user:<id>, event_type=     │ │
│  │   auth.*) → audit_log INSERT (atomic with action)             │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                Postgres 16 (xpredict)                                    │
│  Tables added by 0002_phase2_auth:                                       │
│   - users (fastapi-users schema + display_name, banned_at,               │
│            token_version, tenant_id)                                     │
│   - refresh_tokens (id, token_hash, user_id FK, expires_at,              │
│                     revoked_at, reuse_count, created_at)                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          Redis 7                                         │
│   slowapi storage (DB index /1) — rate-limit counters                    │
│   key shape:    LIMITER/<key_func_result>/<endpoint>/<window>            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component / File | Responsibility | Notes |
|------------------|---------------|-------|
| `backend/app/auth/models.py` | `User` ORM class (`SQLAlchemyBaseUserTableUUID + Base`), `RefreshToken` ORM class | Module follows Phase 1's `app/core/audit/models.py` pattern; UUID PK with Python + server default |
| `backend/app/auth/schemas.py` | Pydantic schemas: `UserRead`, `UserCreate`, `UserUpdate` (extend `schemas.BaseUser*` from fastapi-users); `UserRead` maps `is_superuser → is_admin` | Per D-09: API exposes `is_admin`, ORM keeps `is_superuser` |
| `backend/app/auth/manager.py` | `UserManager(SQLAlchemyUserDatabase, UUIDIDMixin)` with email hooks + password validation | Single manager class used by BOTH player and admin instances |
| `backend/app/auth/strategy.py` | Custom `DatabaseStrategy` implementing `Strategy[User, UUID]` Protocol: `read_token`, `write_token`, `destroy_token` | ~80 LOC; see §"Custom DatabaseStrategy" |
| `backend/app/auth/email.py` | `EmailService` with `send_verification_email`, `send_reset_password_email`; env-switched Mailpit vs Resend | Single class; one source of truth for `from` address |
| `backend/app/auth/router.py` | Wires up both `FastAPIUsers` instances + includes their routers under `/auth/*` and `/admin/auth/*` | Mounted in `app/main.py` |
| `backend/app/auth/rate_limit.py` | `limiter = Limiter(...)`, key functions `key_func_remote` + `key_func_email`, exports `auth_limits` decorator factory | Used by router.py |
| `backend/app/auth/deps.py` | Re-exports `current_active_player`, `current_active_admin`, `get_user_db` | Convenience for downstream phases (Phase 3+ imports `current_active_player`) |
| `backend/alembic/versions/0002_phase2_auth.py` | Creates `users` + `refresh_tokens` tables; `down_revision = "0001_phase1_foundations"` | Sql layer; hand-authored (no autogenerate in Phase 1 baseline) |
| `backend/bin/create-admin.py` | CLI: reads `FIRST_ADMIN_EMAIL/PASSWORD`, hashes via pwdlib, INSERTs idempotently | Run via `uv run python bin/create-admin.py` |
| `frontend/src/app/(auth)/login/page.tsx` | Login form (Server Component shell + Client Component for form) | Posts to FastAPI via Server Action |
| `frontend/src/app/(auth)/register/page.tsx` | Register form | |
| `frontend/src/app/(auth)/forgot-password/page.tsx` | Forgot password form | |
| `frontend/src/app/(auth)/reset-password/page.tsx` | Reset form (reads `?token=…` from query) | |
| `frontend/src/app/(auth)/verify-email/page.tsx` | Verification landing (reads `?token=…`, POSTs once on mount, shows result) | |
| `frontend/src/app/admin/layout.tsx` | Admin layout (separate nav, calls `verifySession()` at the top) | |
| `frontend/src/middleware.ts` | Reads `admin_jwt` cookie, verifies with `jose.jwtVerify`, redirects to `/admin/login` if invalid | Optimistic check; FastAPI is the authoritative gate |
| `frontend/src/lib/auth.ts` | `loginAction`, `logoutAction`, `getSession()`, `verifyAdminSession()` Server Actions / helpers | Centralizes all backend fetch calls |

### Recommended Project Structure

```
backend/app/auth/
├── __init__.py
├── models.py        # User, RefreshToken (SQLAlchemy)
├── schemas.py       # UserRead, UserCreate, UserUpdate (Pydantic)
├── manager.py       # UserManager with email hooks + password validation
├── strategy.py      # Custom DatabaseStrategy (~80 LOC)
├── email.py         # EmailService (Mailpit ↔ Resend switch)
├── rate_limit.py    # Limiter instance + key_func variants + decorators
├── deps.py          # Re-exported current_active_player / current_active_admin
└── router.py        # Wires both FastAPIUsers instances; includes routers

backend/alembic/versions/
└── 0002_phase2_auth.py   # users + refresh_tokens (depends on 0001)

backend/bin/
└── create-admin.py       # First-admin seeding CLI

backend/tests/
├── auth/
│   ├── __init__.py
│   ├── test_register.py
│   ├── test_login.py
│   ├── test_logout.py
│   ├── test_email_verification.py
│   ├── test_password_reset.py
│   ├── test_refresh_rotation.py    # reuse-detection critical test
│   ├── test_admin_bearer.py
│   ├── test_rate_limit.py          # 6th attempt → 429
│   └── test_email_enumeration.py   # forgot-password returns 202 either way

frontend/src/app/
├── (auth)/
│   ├── login/page.tsx
│   ├── register/page.tsx
│   ├── forgot-password/page.tsx
│   ├── reset-password/page.tsx
│   └── verify-email/page.tsx
├── admin/
│   ├── login/page.tsx
│   ├── layout.tsx               # Admin layout; verifySession at top
│   └── page.tsx                 # Placeholder; Phase 8 fills in
├── middleware.ts                # Edge runtime; jose JWT verify on /admin/*
└── lib/
    ├── session.ts               # cookies(), encrypt/decrypt
    ├── auth.ts                  # loginAction, logoutAction
    └── api.ts                   # Shared fetch with credentials: "include"
```

### Pattern 1: Dual `FastAPIUsers` Instances (D-03)

**What:** Two cleanly-separated `FastAPIUsers` objects — one for players (cookie), one for admin (bearer). They share the `User` model and `UserManager` class but mount distinct routers under distinct prefixes.

**When to use:** Whenever player and admin auth surfaces must NOT cross-authenticate (a player cookie must never grant admin access; an admin Bearer must never satisfy a player endpoint check).

**Example:**

```python
# backend/app/auth/router.py
# Source: github.com/fastapi-users/fastapi-users/discussions/989 (maintainer-endorsed pattern)
import uuid

from fastapi import APIRouter
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
)

from app.auth.deps import get_user_manager
from app.auth.models import User
from app.auth.strategy import get_database_strategy
from app.core.config import get_settings

settings = get_settings()

# ── Player surface (cookie) ────────────────────────────────────────
cookie_transport = CookieTransport(
    cookie_name="xpredict_session",
    cookie_max_age=60 * 60 * 24 * 30,          # 30 days
    cookie_httponly=True,
    cookie_secure=not settings.is_dev,         # False in dev, True in staging/prod
    cookie_samesite="lax",
    cookie_path="/",
)

player_backend = AuthenticationBackend(
    name="player-cookie",
    transport=cookie_transport,
    get_strategy=get_database_strategy,        # custom — see strategy.py
)

fastapi_users_player = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [player_backend],
)

# ── Admin surface (bearer) ─────────────────────────────────────────
bearer_transport = BearerTransport(tokenUrl="/admin/auth/login")

admin_backend = AuthenticationBackend(
    name="admin-bearer",
    transport=bearer_transport,
    get_strategy=get_database_strategy,        # same strategy; different transport
)

fastapi_users_admin = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [admin_backend],
)

# ── Convenience deps re-exported from app.auth.deps ─────────────────
current_active_player = fastapi_users_player.current_user(active=True, verified=True)
current_active_admin = fastapi_users_admin.current_user(active=True, superuser=True)

# ── Router includes (called from main.py) ──────────────────────────
def build_auth_routers() -> APIRouter:
    """Return a parent router containing all auth + admin-auth routes."""
    parent = APIRouter()

    # Player
    parent.include_router(
        fastapi_users_player.get_auth_router(player_backend),
        prefix="/auth", tags=["auth"],
    )
    parent.include_router(
        fastapi_users_player.get_register_router(UserRead, UserCreate),
        prefix="/auth", tags=["auth"],
    )
    parent.include_router(
        fastapi_users_player.get_verify_router(UserRead),
        prefix="/auth", tags=["auth"],
    )
    parent.include_router(
        fastapi_users_player.get_reset_password_router(),
        prefix="/auth", tags=["auth"],
    )
    parent.include_router(
        fastapi_users_player.get_users_router(UserRead, UserUpdate),
        prefix="/auth/users", tags=["auth"],
    )

    # Admin (no register / no verify / no reset for the demo — admins are seeded)
    parent.include_router(
        fastapi_users_admin.get_auth_router(admin_backend),
        prefix="/admin/auth", tags=["admin-auth"],
    )
    return parent
```

**Why this works:** Each instance has its own backend list; `current_user(...)` only succeeds when the request carries a token in the format the backend's transport understands. A player browser sends `Cookie: xpredict_session=…` — only `fastapi_users_player.current_user(...)` parses it. An admin API client sends `Authorization: Bearer …` — only `fastapi_users_admin.current_user(...)` parses it. No cross-auth.

### Pattern 2: Custom `DatabaseStrategy` with Reuse Detection (D-04, AUTH-05, AUTH-09)

**What:** Replace fastapi-users' built-in `JWTStrategy` (stateless, no revocation) with a database-backed strategy that writes a row per token issued. Logout revokes the row; reuse of a revoked token triggers a "scorched-earth" revocation of all the user's tokens.

**When to use:** Whenever the requirement says "session revoked on logout, verifiable in DB" or "refresh-token rotation with reuse detection" — which is exactly AUTH-05 + AUTH-09 + ROADMAP success criteria #3.

**Strategy Protocol** (verified from fastapi-users source, `fastapi_users/authentication/strategy/base.py`):

```python
class Strategy(Protocol):
    async def read_token(self, token: str | None, user_manager: BaseUserManager) -> User | None: ...
    async def write_token(self, user: User) -> str: ...
    async def destroy_token(self, token: str, user: User) -> None: ...
```

**Example:**

```python
# backend/app/auth/strategy.py
# Source: verified against github.com/fastapi-users/fastapi-users/blob/master/fastapi_users/authentication/strategy/base.py
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends
from fastapi_users.authentication.strategy import Strategy, StrategyDestroyNotSupportedError
from fastapi_users.manager import BaseUserManager
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken, User
from app.core.config import get_settings
from app.db.session import get_async_session


def _hash(token: str) -> str:
    """Store SHA256 of token, never the raw value — DB breach must not leak tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DatabaseStrategy(Strategy[User, UUID]):
    """Persistent token store with rotation + reuse detection (AUTH-09)."""

    def __init__(self, session: AsyncSession, lifetime_seconds: int) -> None:
        self.session = session
        self.lifetime_seconds = lifetime_seconds

    async def read_token(
        self,
        token: str | None,
        user_manager: BaseUserManager[User, UUID],
    ) -> User | None:
        if token is None:
            return None

        stmt = select(RefreshToken).where(RefreshToken.token_hash == _hash(token))
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None

        # ── REUSE DETECTION ────────────────────────────────────────────────
        # If a revoked token is presented, treat it as an attack: nuke ALL
        # tokens for this user. This is the OWASP-recommended response.
        if row.revoked_at is not None:
            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC), reuse_count=RefreshToken.reuse_count + 1)
            )
            await self.session.commit()
            return None

        if row.expires_at < datetime.now(UTC):
            return None

        # ── token_version GATE (AUTH-06: invalidate on password reset) ────
        try:
            user = await user_manager.get(row.user_id)
        except Exception:
            return None
        if user.token_version > row.token_version:
            return None

        return user

    async def write_token(self, user: User) -> str:
        # 64 chars of url-safe randomness = 384 bits of entropy
        token = secrets.token_urlsafe(48)
        row = RefreshToken(
            token_hash=_hash(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.lifetime_seconds),
            token_version=user.token_version,
        )
        self.session.add(row)
        await self.session.commit()
        return token

    async def destroy_token(self, token: str, user: User) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == _hash(token), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.session.commit()


def get_database_strategy(
    session: AsyncSession = Depends(get_async_session),
) -> DatabaseStrategy:
    """FastAPI dependency producing a per-request strategy bound to the session."""
    settings = get_settings()
    return DatabaseStrategy(session, lifetime_seconds=settings.REFRESH_TOKEN_LIFETIME_SECONDS)
```

**Why this is correct:** The `Strategy` Protocol is exactly three methods. Storing `sha256(token)` means a DB breach doesn't leak active tokens. The reuse-detection branch is the OWASP-recommended pattern (every legitimate client only sees a fresh token; if the old one comes back, something stole it). Mounting `token_version` in `read_token` means a password-reset bump (in `on_after_reset_password`) instantly invalidates every cookie issued before the reset.

### Pattern 3: Email Service (D-05, D-06, AUTH-02)

**What:** A single `EmailService` class that decides Mailpit vs Resend by `ENVIRONMENT`. Called from `UserManager` hooks; produces a fire-and-forget email send.

**When to use:** Anywhere the backend needs to send a transactional email (verification + password reset in Phase 2; future phases may add settlement notifications etc.).

**Example:**

```python
# backend/app/auth/email.py
import aiosmtplib
import resend
from email.message import EmailMessage

from app.core.config import get_settings


VERIFY_HTML = """
<!doctype html>
<html><body style="font-family:system-ui,sans-serif">
  <h2>Verify your XPredict account</h2>
  <p>Click the link below to verify your email address. The link is single-use and expires in 1 hour.</p>
  <p><a href="{verify_url}" style="background:#000;color:#fff;padding:10px 16px;text-decoration:none">Verify email</a></p>
  <p style="color:#666;font-size:12px">If the button does not work, paste this URL into your browser: {verify_url}</p>
</body></html>
"""


class EmailService:
    """One sender to rule them all — env-switched."""

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.is_dev:
            resend.api_key = self.settings.RESEND_API_KEY

    async def send(self, *, to: str, subject: str, html: str) -> None:
        if self.settings.is_dev:
            await self._send_via_mailpit(to=to, subject=subject, html=html)
        else:
            await self._send_via_resend(to=to, subject=subject, html=html)

    async def _send_via_mailpit(self, *, to: str, subject: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"] = "XPredict <noreply@xpredict.local>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content("HTML email — view in a modern client.")
        msg.add_alternative(html, subtype="html")
        await aiosmtplib.send(
            msg,
            hostname=self.settings.SMTP_HOST,    # "mailpit" in docker
            port=self.settings.SMTP_PORT,        # 1025
            use_tls=False,
            start_tls=False,
        )

    async def _send_via_resend(self, *, to: str, subject: str, html: str) -> None:
        params: resend.Emails.SendParams = {
            "from": self.settings.RESEND_FROM_ADDRESS,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        await resend.Emails.send_async(params)


    async def send_verification_email(self, *, to: str, token: str) -> None:
        verify_url = f"{self.settings.FRONTEND_BASE_URL}/verify-email?token={token}"
        await self.send(
            to=to,
            subject="Verify your XPredict email",
            html=VERIFY_HTML.format(verify_url=verify_url),
        )

    async def send_reset_password_email(self, *, to: str, token: str) -> None:
        reset_url = f"{self.settings.FRONTEND_BASE_URL}/reset-password?token={token}"
        # ... similar HTML template
```

**Plumbing into `UserManager`:**

```python
# backend/app/auth/manager.py — relevant excerpt
class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = get_settings().SECRET_KEY
    verification_token_secret = get_settings().SECRET_KEY

    def __init__(self, user_db, password_helper, email_service: EmailService) -> None:
        super().__init__(user_db, password_helper)
        self.email_service = email_service

    async def on_after_register(self, user: User, request=None) -> None:
        await self.request_verify(user, request)   # triggers on_after_request_verify

    async def on_after_request_verify(self, user: User, token: str, request=None) -> None:
        await self.email_service.send_verification_email(to=user.email, token=token)

    async def on_after_forgot_password(self, user: User, token: str, request=None) -> None:
        await self.email_service.send_reset_password_email(to=user.email, token=token)

    async def on_after_reset_password(self, user: User, request=None) -> None:
        # AUTH-06 + ROADMAP success criteria #4: bump token_version → invalidates
        # all prior refresh tokens. The DatabaseStrategy.read_token checks
        # user.token_version > row.token_version.
        await self._increment_token_version(user)
        # Then revoke all currently active rows for clean book-keeping:
        from sqlalchemy import update
        from app.auth.models import RefreshToken
        await self.user_db.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.user_db.session.commit()
```

### Pattern 4: Stacked Rate-Limit Decorators (D-14, AUTH-08)

**What:** Two `@limiter.limit(...)` decorators on the same endpoint — one keyed on IP, one keyed on email — both enforced per request.

**When to use:** Any endpoint that needs simultaneous protection against both IP-based brute force AND targeted single-account credential stuffing.

**Example:**

```python
# backend/app/auth/rate_limit.py
# Source: github.com/laurentS/slowapi/blob/master/slowapi/extension.py (limit method signature + stacking)
import json

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


_settings = get_settings()
limiter = Limiter(
    key_func=get_remote_address,                        # default = per-IP
    storage_uri=str(_settings.REDIS_URL) + "/1",        # use Redis DB 1, dedicated
    default_limits=[],                                  # no global default
    headers_enabled=True,                               # X-RateLimit-* headers
)


async def _email_from_form(request: Request) -> str:
    """Extract email from form body for per-email limiting on login/forgot.

    Reads the BODY without consuming the underlying stream (request.body() is
    cached). Returns a deterministic placeholder when the field is missing so
    the limit still applies to malformed requests.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = (body.get("email") or body.get("username") or "").strip().lower()
    return f"email:{email or 'unknown'}"


def email_key_func(request: Request) -> str:
    # NOTE: slowapi's key_func is sync; we read the cached body inline.
    # For form-encoded requests we'd parse differently. The router function
    # that wraps this hands us the email explicitly to avoid double-parsing.
    return getattr(request.state, "rate_limit_email_key", "email:unknown")
```

**Applying to endpoints** (using a small router wrapper because fastapi-users mounts routers we don't control — see Pitfall §"Rate-limiting fastapi-users routers"):

```python
# backend/app/auth/router.py — apply limits via dependency, not decorator,
# because we don't author the fastapi-users routes.
from fastapi import Depends, Request

from app.auth.rate_limit import limiter


async def auth_rate_limit_dependency(request: Request) -> None:
    """Per-IP + per-email limit applied as a route dependency.

    fastapi-users provides the route functions — we cannot decorate them
    directly. Instead, we attach a Depends() that runs the limiter check
    via Limiter._check_request_limit_inner (the same private method the
    decorator uses) — OR we mount our own wrapper routes.

    Recommendation: wrap the four critical fastapi-users endpoints
    (login, register, forgot-password, request-verify) with thin proxy
    routes WE author, so the @limiter.limit decorator stack works
    directly. The proxy routes delegate to fastapi-users via call().
    """
    ...


# Cleaner alternative: thin wrapper routes that delegate to fastapi-users.
auth_router = APIRouter(prefix="/auth", tags=["auth"])

@auth_router.post("/login")
@limiter.limit("5/minute", key_func=get_remote_address)
@limiter.limit("5/minute", key_func=lambda r: r.state.email_key)
async def login(request: Request, credentials: OAuth2PasswordRequestForm = Depends()):
    # Pre-extract email for the second key_func to read
    request.state.email_key = f"email:{credentials.username.strip().lower()}"
    # Delegate to fastapi-users' actual login route via internal call
    ...
```

**The cleaner production pattern** — wrap fastapi-users' router with a single thin proxy router that owns the decorators. Planner should pick between (a) thin proxy routes vs (b) running `Limiter._check_request_limit_inner` from a dependency. Both work; (a) is more readable.

### Pattern 5: Next.js Auth UI (D-12, D-13)

**What:** Next.js 15 App Router pages with Server Actions that POST to FastAPI, then Server Components that gate via a `verifySession` data-access-layer helper.

**Example login flow:**

```typescript
// frontend/src/lib/auth.ts
// Source: nextjs.org/docs/app/guides/authentication (canonical pattern)
'use server'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { z } from 'zod'

const LoginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
})

export async function loginAction(prev: unknown, formData: FormData) {
  const parsed = LoginSchema.safeParse({
    email: formData.get('email'),
    password: formData.get('password'),
  })
  if (!parsed.success) return { errors: parsed.error.flatten().fieldErrors }

  // FastAPI returns Set-Cookie: xpredict_session=...; the browser does NOT
  // see it (HTTP-only). For the Next.js Server Action to participate in
  // the cookie flow, we use fetch with `credentials: "include"` and let
  // Next.js forward the Set-Cookie via the response headers. The simpler
  // path: have the BROWSER submit the form directly to FastAPI via a
  // CORS-allowed cross-origin request. Server Actions are still useful
  // for validation + redirect.

  const res = await fetch(`${process.env.BACKEND_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      username: parsed.data.email,     // OAuth2 form field name
      password: parsed.data.password,
    }),
    credentials: 'include',
  })
  if (!res.ok) return { errors: { _form: ['Invalid credentials'] } }

  // Forward the cookie from the FastAPI response to the browser
  const setCookie = res.headers.get('set-cookie')
  if (setCookie) {
    // Parse and re-set via next/headers cookies() so the browser receives it
    // (Next.js Server Actions automatically forward cookies set this way)
    const match = setCookie.match(/xpredict_session=([^;]+)/)
    if (match) {
      const store = await cookies()
      store.set('xpredict_session', match[1], {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        path: '/',
        maxAge: 60 * 60 * 24 * 30,
      })
    }
  }
  redirect('/')
}
```

**Admin middleware** (Edge runtime, fast cookie check):

```typescript
// frontend/src/middleware.ts
// Source: nextjs.org/docs/app/guides/authentication#optimistic-checks-with-proxy
import { NextRequest, NextResponse } from 'next/server'
import { jwtVerify } from 'jose'

const ADMIN_PROTECTED = /^\/admin(\/|$)/
const ADMIN_LOGIN = '/admin/login'

export async function middleware(req: NextRequest) {
  if (!ADMIN_PROTECTED.test(req.nextUrl.pathname)) return NextResponse.next()
  if (req.nextUrl.pathname === ADMIN_LOGIN) return NextResponse.next()

  const token = req.cookies.get('admin_jwt')?.value
  if (!token) return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url))

  try {
    const secret = new TextEncoder().encode(process.env.ADMIN_JWT_PUBLIC_SECRET!)
    await jwtVerify(token, secret, { algorithms: ['HS256'] })
    return NextResponse.next()
  } catch {
    return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url))
  }
}

export const config = {
  matcher: ['/admin/:path*'],
}
```

**Why middleware is OPTIMISTIC, not the gate:** Per Next.js 15 docs, middleware runs on every request including prefetches and should not hit the DB. The authoritative `is_superuser` check happens at the **FastAPI** layer on every `/admin/*` request via the `current_active_admin` dependency. The middleware just keeps unauthenticated browsers out of the admin UI eagerly.

### Anti-Patterns to Avoid

- **Reusing one `FastAPIUsers` instance with `[cookie, bearer]`** — makes a player cookie satisfy the admin's `current_user`, defeating AUTH-07. Use two instances. `[VERIFIED via fastapi-users discussion #989]`
- **Trusting the Bearer JWT alone for `/admin/*` enforcement** — middleware in Next.js is optimistic. A request that bypasses the frontend (curl direct to backend) must still be rejected by FastAPI's `current_active_admin` guard. `[CITED: nextjs.org/docs/app/guides/authentication]`
- **Storing the raw token in `refresh_tokens.token_hash`** — store SHA256 only. A DB read attack must not leak live tokens.
- **Returning different status codes / messages for "email exists" vs "email does not exist" on `/auth/forgot-password`** — fastapi-users defaults to 202 for both, which is correct. Do not "fix" this; it's the email-enumeration mitigation. `[VERIFIED: fastapi-users.github.io/fastapi-users/latest/usage/routes/]`
- **Decorating fastapi-users-provided routes with `@limiter.limit(...)`** — you don't own those functions. Wrap them with proxy routes or use a `Depends(...)` that calls `Limiter._check_request_limit_inner`. See §"Common Pitfalls".
- **Letting `aiosmtplib` retry on every send error blocking the request thread** — wrap the email send in a try/except, log on failure, but never let an SMTP outage block the `POST /auth/register` response. Email is best-effort from the user's POV.
- **Letting middleware do DB queries** — middleware runs on every prefetch in Next.js 15. DB calls there are a perf catastrophe. Verify JWT signature only, hit DB inside route handlers / Server Components via the DAL.
- **Skipping `AuditService.record(...)` in auth hooks** — Phase 1 mandates audit on every state mutation. Every successful register/login/logout/verify/reset MUST `await AuditService.record(...)` in the same transaction as the underlying mutation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom Argon2 wrapper | `pwdlib` (transitive via fastapi-users) | Parameter tuning, salt generation, constant-time compare, version upgrade — all already correct in pwdlib. Custom code is where CVEs live. |
| JWT signing / verification | Manual `jwt.encode` + claim validation | `PyJWT[crypto]` (transitive) + fastapi-users' built-in token generator | Header confusion attacks, algorithm confusion (`alg: none`), expiration edge cases — all already handled. |
| Email verification token generation | Custom `secrets.token_urlsafe` + signing | fastapi-users `request_verify` + built-in `verify` route | Token includes `aud`, `exp`, `email` (so it survives email change between request and verify); validated atomically. |
| Password reset token generation | Custom one-time-use token table | fastapi-users `forgot_password` + `reset_password` routes | Same — proper exp + aud + atomic verify. |
| Refresh-token rotation logic | Custom `/auth/refresh` endpoint | Custom `DatabaseStrategy.read_token` returning fresh row + writing new (rotation on every read) | Putting rotation in the Strategy means EVERY backend request rotates the token; no separate `/refresh` endpoint needed. |
| Rate limiting | Custom Redis counters | `slowapi` with `storage_uri="redis://..."` + stacked decorators | Race conditions in counter increments, expiry windows, per-route storage keys, header emission — all already correct. |
| Email enumeration prevention on forgot-password | Conditional response branching | fastapi-users default 202 Accepted | Built in — DO NOT override. |
| First-admin bootstrapping | Magic on first request | `bin/create-admin.py` CLI run once at deploy | Avoids the "self-promotion via first registration" footgun. |
| Email templating | Jinja2 + template files | Inline f-strings in Python (per CONTEXT D-07) | Phase 2 has 2 emails. Adding Jinja2 is overkill; Phase 10 adds branding properly. |
| `is_admin` boolean separate from `is_superuser` | Custom column | Reuse `is_superuser`, expose as `is_admin` in Pydantic schema mapping | Per CONTEXT D-09. Avoids parallel-state bug. |
| Password strength rules | Custom regex chain | pydantic validator on `UserCreate` + override `UserManager.validate_password` | fastapi-users calls `validate_password` automatically; throw `InvalidPasswordException` for failure. |

**Key insight:** fastapi-users does ~80% of this for us. The 20% we own — the custom `DatabaseStrategy`, the EmailService, the rate-limit wiring, and the admin/player route separation — has exactly one well-shaped extension point each. Don't push hand-rolled code into the other 80%.

## Runtime State Inventory

Phase 2 is a **greenfield additive phase** — it creates new tables (`users`, `refresh_tokens`) and new code modules. No rename, refactor, or migration affecting existing runtime state. This section is intentionally minimal.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — both `users` and `refresh_tokens` are new tables created in `0002_phase2_auth.py` | None |
| Live service config | None — Mailpit is already running (Phase 1); Resend is new but configured via env vars only (no live runtime state) | None |
| OS-registered state | None — no scheduled tasks or registered services touched | None |
| Secrets/env vars | NEW env vars added to `.env.example` and `Settings`: `SECRET_KEY` (JWT signing + token secrets), `RESEND_API_KEY`, `RESEND_FROM_ADDRESS`, `FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD`, `FRONTEND_BASE_URL`, `SMTP_HOST` (default `mailpit`), `SMTP_PORT` (default `1025`), `ACCESS_TOKEN_LIFETIME_SECONDS` (default `900` = 15 min), `REFRESH_TOKEN_LIFETIME_SECONDS` (default `2592000` = 30 d), `ADMIN_JWT_PUBLIC_SECRET` (Next.js env, mirrors backend's SECRET_KEY but exposed to middleware) | Add to `Settings(BaseSettings)` (preserving Phase 1's `extra="ignore"`); add to `.env.example` with placeholder values; ensure `.gitleaks.toml` allowlist still passes |
| Build artifacts | None — no compiled artifacts touched | None |

**The canonical question:** *After every Phase 2 file lands, what runtime systems still have stale state?*

**Answer:** Only the Postgres schema needs the new migration applied (`alembic upgrade head`); the first admin needs `bin/create-admin.py` run once; the dev `.env.local` needs the new vars populated. No legacy systems hold names we are renaming.

## Common Pitfalls

### Pitfall 1: Rate-limiting routes you don't own (fastapi-users routers)

**What goes wrong:** You try to slap `@limiter.limit("5/minute")` on `fastapi_users_player.get_auth_router(...).routes[0].endpoint`. The decorator wraps the function, but the wrapped function loses its FastAPI dependency-injection metadata and the route stops accepting requests. Alternatively, the decorator is silently ignored because slowapi inspects the function signature and doesn't see `request: Request`.

**Why it happens:** `slowapi.Limiter.limit` is a function decorator; fastapi-users routers are mounted with their own route functions that don't expose a `request` param at the top level. You can't retroactively decorate them.

**How to avoid:**
- **Option A (recommended)**: write four thin proxy routes in `app/auth/router.py` that explicitly declare `request: Request, ...` parameters, decorate them with `@limiter.limit(...)`, and call the underlying fastapi-users route function or call the manager's methods directly. This keeps the limiter decorator-style and readable.
- **Option B**: write an async dependency that calls `Limiter._check_request_limit_inner(request, "5/minute", key_func=...)` and add it via `dependencies=[Depends(...)]` on the include_router call. Slightly less idiomatic but doesn't require duplicating routes.

**Warning signs:** Tests pass but the rate limit never triggers. Or routes silently 422 with "missing field: request".

### Pitfall 2: `Session.expire_on_commit` not False under async (data loss on commit)

**What goes wrong:** After `await session.commit()`, accessing any attribute on the ORM object you just committed re-triggers an auto-refresh. Under sync SQLAlchemy this is fine; under async it raises `MissingGreenlet` or `DetachedInstanceError` because the implicit re-fetch is sync IO inside an async context.

**Why it happens:** SQLAlchemy 2.0's async docs explicitly call this out — `expire_on_commit=True` (the default) breaks async patterns.

**How to avoid:** Already done in `app/db/session.py` (`expire_on_commit=False` on the `async_sessionmaker`). Just don't regress it when wiring fastapi-users' `SQLAlchemyUserDatabase` — it uses the same sessionmaker. `[VERIFIED: backend/app/db/session.py line 47]`

**Warning signs:** Tests that touch a user's attributes right after `session.commit()` raise `sqlalchemy.exc.MissingGreenlet`.

### Pitfall 3: Cookie `Secure` flag wrong in dev (cookie discarded)

**What goes wrong:** You set `cookie_secure=True` unconditionally; in dev the browser silently drops the Set-Cookie because the request was on `http://localhost`. You debug for an hour wondering why login "works" but the next request is unauthenticated.

**How to avoid:** Tie `cookie_secure` to `settings.is_dev` (the `is_dev` property already exists in `app/core/config.py` line 47): `cookie_secure=not settings.is_dev`. In staging/prod the flag is True; in dev it's False.

**Warning signs:** Browser DevTools → Application → Cookies shows the cookie absent after a 200 OK login; or `set-cookie` header present in response but cookie missing from next request.

### Pitfall 4: Argon2id parameters too aggressive (10s login)

**What goes wrong:** You configure Argon2id with `memory_cost=2GiB` (RFC 9106 high-memory profile) without realizing each login eats 2 GiB. Concurrent logins OOM the API container.

**How to avoid:** Use OWASP's "balanced" recommendation — `memory_cost=19456` (19 MiB), `time_cost=2`, `parallelism=1`. pwdlib's `PasswordHash.recommended()` already gives sensible defaults; only override if benchmarking shows you need to. Document the chosen values in CONVENTIONS.md so a future operator deploying with bigger hardware doesn't accidentally downgrade them. `[CITED: cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html]`

**Warning signs:** `htop` shows API container RSS climbing per login; p99 login latency > 500 ms; tests time out.

### Pitfall 5: Email failures blocking registration

**What goes wrong:** Resend has a 500 outage. Your `on_after_register` awaits the email send. The `POST /auth/register` response never returns. Users see "registration failed" toasts and try again, creating duplicate-email errors.

**How to avoid:** Wrap email sends in try/except inside hooks. Log the failure (and emit a Sentry event) but DO NOT raise. From the API consumer's POV, registration succeeds; verification can be retried via `POST /auth/request-verify-token` later.

```python
async def on_after_register(self, user: User, request=None) -> None:
    try:
        await self.request_verify(user, request)
    except Exception:
        logger.exception("verification email send failed", extra={"user_id": str(user.id)})
        # do NOT raise — Phase 2 success criteria #1 only requires the email
        # "lands in Mailpit"; under SMTP outage we degrade gracefully.
```

**Warning signs:** Sentry shows `aiosmtplib.SMTPException` correlated with registration timeouts.

### Pitfall 6: `token_version` bump without revoking active rows

**What goes wrong:** Password reset bumps `users.token_version` but doesn't revoke `refresh_tokens` rows. The cookie still parses (signature OK), the row still exists (revoked_at IS NULL), and `read_token` would return the user — except for the `token_version > row.token_version` check.

**How to avoid:** Do BOTH in `on_after_reset_password`: increment `token_version` AND `UPDATE refresh_tokens SET revoked_at = NOW() WHERE user_id = ? AND revoked_at IS NULL`. Belt-and-suspenders. The `token_version` check in `read_token` is the suspenders (it catches reuse of an "old generation" token); the bulk revoke is the belt (it gives clean DB state and a verifiable "revoked at" timestamp per row).

**Warning signs:** Manual test: login (cookie A), reset password (bumps version), refresh page — cookie A should NOT authenticate. If it does, one of the two mechanisms is missing.

### Pitfall 7: CORS + cookie credentials misconfigured

**What goes wrong:** Browser sends `OPTIONS` preflight, backend's CORSMiddleware allows `*` origins, but the cookie still doesn't flow because `allow_credentials=True` requires an explicit origin (cannot be `*`).

**How to avoid:** In `app/main.py` add `CORSMiddleware` with explicit `allow_origins=["http://localhost:3000"]` (dev) / `[settings.FRONTEND_BASE_URL]` (prod), `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`. Don't use `["*"]` for origins. `[CITED: fastapi.tiangolo.com/tutorial/cors/]`

**Warning signs:** Browser shows "Cross-Origin Request Blocked: cookies not sent" in DevTools Network tab; login succeeds (200) but next API call returns 401.

### Pitfall 8: Email-enumeration via timing on `/auth/login`

**What goes wrong:** Server returns 401 in 50 ms for unknown emails (no hash compare) but 200+ ms for known emails (full Argon2 compare). An attacker enumerates valid emails by request timing.

**How to avoid:** fastapi-users already mitigates: it performs a dummy Argon2 hash compare against a placeholder when the email doesn't exist. **Verify** this is still the case in v15 by checking `fastapi_users/manager.py::authenticate`. The same applies to forgot-password: fastapi-users returns 202 either way (already correct — see anti-patterns above). `[VERIFIED via maintainer behaviour, but planner should add an explicit test that timing variance < 50 ms between known/unknown email]`

**Warning signs:** Test that measures `POST /auth/login` p99 with an unknown email vs known email — gap > 50 ms is suspicious.

### Pitfall 9: Custom `DatabaseStrategy` committing inside a request transaction

**What goes wrong:** Our `DatabaseStrategy.write_token` calls `await self.session.commit()`. If the route handler is in the middle of a larger transaction (e.g., register also writes a row + audit), the strategy's commit ends the whole transaction prematurely.

**How to avoid:** Either (a) use a separate session inside the strategy via a fresh `async_sessionmaker()` (own transaction lifetime), or (b) just `await self.session.flush()` and let the caller commit. Decision for the planner: **(a) is safer** because the cookie-issued-but-user-not-committed race is impossible. Document explicitly in `strategy.py`.

**Warning signs:** Tests that expect a register failure to rollback (no user row left over) see a half-committed state where the user exists but no audit entry.

### Pitfall 10: Forgetting `is_verified` gate on `/auth/login`

**What goes wrong:** Player registers, doesn't verify email, can still log in and bet. That violates BET-02 (Phase 5) and possibly AUTH-04's "verified" requirement.

**How to avoid:** Use `fastapi_users_player.current_user(active=True, verified=True)` as the player dependency. fastapi-users' `auth_router` itself lets unverified users authenticate (`requires_verification=False` by default on `get_auth_router`), but the `current_user(verified=True)` gate on protected routes is the enforcement point. `[VERIFIED: fastapi-users.github.io/fastapi-users/latest/configuration/routers/auth/]`

**Warning signs:** Test that registers a user, logs in, accesses `/me` — should succeed. Accesses any `verified=True`-gated route — should 403.

## Code Examples

### Common Operation 1: User model (D-02, D-08)

```python
# backend/app/auth/models.py
# Source: fastapi-users.github.io/fastapi-users/latest/configuration/full-example/
#         + verified columns in github.com/fastapi-users/fastapi-users-db-sqlalchemy
from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """XPredict user — extends fastapi-users base with our tenant_id ghost,
    display_name, banned_at, token_version."""

    __tablename__ = "users"

    # SQLAlchemyBaseUserTableUUID brings: id (UUID PK, default=uuid4),
    # email (String 320 unique indexed), hashed_password (String 1024),
    # is_active (Bool default True), is_superuser (Bool default False),
    # is_verified (Bool default False).

    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0,
    )
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )


class RefreshToken(Base):
    """One row per refresh token issued. Hash-only storage."""

    __tablename__ = "refresh_tokens"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    reuse_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0,
    )
    # Snapshot of user.token_version at issue time — invalidated on bump.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
```

### Common Operation 2: User schemas with `is_superuser → is_admin` (D-09)

```python
# backend/app/auth/schemas.py
import uuid
from datetime import datetime

from fastapi_users import schemas
from pydantic import EmailStr, computed_field


class UserRead(schemas.BaseUser[uuid.UUID]):
    """API representation — exposes is_admin, hides is_superuser."""

    display_name: str | None = None

    # Hide fastapi-users' is_superuser from the wire
    is_superuser: bool = False

    @computed_field
    @property
    def is_admin(self) -> bool:
        return self.is_superuser

    model_config = {
        # Exclude is_superuser from JSON output; admins read is_admin instead.
        "json_schema_extra": {
            "examples": [{
                "id": "...", "email": "p@x.com", "is_active": True,
                "is_verified": True, "is_admin": False, "display_name": "Pol",
            }],
        },
    }


class UserCreate(schemas.BaseUserCreate):
    """Register payload."""
    display_name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    """PATCH /auth/users/me payload."""
    display_name: str | None = None
```

> **Note on serialization:** The cleanest "hide `is_superuser` from API" is to override `model_dump`'s exclude list or set `is_superuser` as an excluded field via `Field(exclude=True)`. Planner should verify the exact pydantic v2 incantation; the `computed_field` approach above maps the bool but doesn't hide the original.

### Common Operation 3: Password validation in `UserManager` (AUTH-01)

```python
# backend/app/auth/manager.py — excerpt
import re

from fastapi_users.exceptions import InvalidPasswordException


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    async def validate_password(self, password: str, user: User | UserCreate) -> None:
        """Enforce server-side strength rules (AUTH-01).

        Called automatically by fastapi-users before hashing on register
        and password reset. Throw InvalidPasswordException with a message
        the API will surface verbatim.
        """
        if len(password) < 12:
            raise InvalidPasswordException(reason="Password must be at least 12 characters.")
        if not re.search(r"[A-Z]", password):
            raise InvalidPasswordException(reason="Password must contain an uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise InvalidPasswordException(reason="Password must contain a lowercase letter.")
        if not re.search(r"\d", password):
            raise InvalidPasswordException(reason="Password must contain a digit.")
        if user is not None and isinstance(user, UserCreate) and user.email.lower() in password.lower():
            raise InvalidPasswordException(reason="Password must not contain your email.")
```

### Common Operation 4: Alembic migration `0002_phase2_auth.py` (D-08)

```python
"""Phase 2: users + refresh_tokens.

Revision ID: 0002_phase2_auth
Revises: 0001_phase1_foundations
Create Date: 2026-05-XX
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "0002_phase2_auth"
down_revision: str | None = "0001_phase1_foundations"
branch_labels: str | None = None
depends_on: str | None = None


TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("is_superuser", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("banned_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("token_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_hash", sa.Text, nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reuse_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("token_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
```

### Common Operation 5: First-admin seeding script (D-11)

```python
# backend/bin/create-admin.py
"""Seed the first admin user idempotently.

Read FIRST_ADMIN_EMAIL + FIRST_ADMIN_PASSWORD from env, hash with Argon2id
(via pwdlib — same hasher fastapi-users uses), INSERT one user with
is_superuser=True is_verified=True. Re-run is a no-op.
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

from pwdlib import PasswordHash
from sqlalchemy import select

from app.auth.models import User
from app.core.config import get_settings
from app.db.session import _get_session_maker


async def main() -> int:
    settings = get_settings()
    email = settings.FIRST_ADMIN_EMAIL
    password = settings.FIRST_ADMIN_PASSWORD
    if not email or not password:
        print("FIRST_ADMIN_EMAIL and FIRST_ADMIN_PASSWORD must be set", file=sys.stderr)
        return 1

    session_maker = _get_session_maker()
    async with session_maker() as session:
        existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            print(f"Admin {email} already exists (id={existing.id}). No-op.")
            return 0

        helper = PasswordHash.recommended()
        admin = User(
            id=uuid4(),
            email=email,
            hashed_password=helper.hash(password),
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.commit()
        print(f"Created admin {email} (id={admin.id})")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `passlib[bcrypt]` for hashing | `pwdlib[argon2,bcrypt]` (default Argon2id) | pwdlib 0.1 released 2023; fastapi-users switched in v14 | passlib is in maintenance mode; pwdlib is the modern replacement by the same author of fastapi-users. Don't go back to passlib. |
| `python-jose` for JWT | `PyJWT[crypto]` | fastapi-users v13+ moved to PyJWT; python-jose has been unmaintained since 2021 | python-jose has known CVE for algorithm-confusion attacks; PyJWT is the maintained choice. Don't reintroduce python-jose. |
| `JWTStrategy` (stateless) for refresh | `DatabaseStrategy` for refresh | OWASP refresh-token rotation recommendation | Stateless JWT cannot be revoked. Modern apps use a DB-backed refresh token + short-lived access token. |
| Next.js Pages Router auth (next-auth v4) | App Router + Server Actions + DAL + `jose` middleware | Next.js 13.4+ App Router stable, Next 15 official docs published in 2024-2025 | App Router is the canonical path; the Auth doc page on nextjs.org now recommends `iron-session` or `jose` over next-auth for hand-rolled flows. |
| Cookies via `response.set_cookie(...)` in every route | `CookieTransport` from fastapi-users | fastapi-users v8+ | Cookie attributes (HttpOnly, Secure, SameSite, Path, Max-Age) all centralized; one source of truth. |
| Single auth backend with role flag | Two `FastAPIUsers` instances (player + admin) | Multiple GitHub discussions converging on this pattern (e.g., #989, #960) | Hard boundary between surfaces; player cookies can't authenticate `/admin/*`. |

**Deprecated/outdated:**
- **fastapi-users v14** — superseded by v15 (October 2024); same API for our usage. CONTEXT D-01 should be updated.
- **passlib** — superseded by pwdlib; do not reintroduce.
- **python-jose** — unmaintained since 2021; do not introduce.
- **NextAuth.js v4 pages router** — not relevant; we are App Router.
- **`SQLAlchemyBaseUserTable` (non-UUID variant)** — we use UUID per ROADMAP / PROJECT consistency; integer PK variant exists but we never want it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | fastapi-users v15 is API-compatible with v14 for our usage (dual backend, custom strategy, email hooks) | Standard Stack | LOW — v15 changelog only mentions dep drops (Python 3.9, Pydantic v1) — both already required by our stack. Worst case: we keep v14 explicitly. Surface to Pol. |
| A2 | `cookie_samesite="lax"` is correct given the frontend and backend are on different ports in dev | Pattern 1 + Pattern 5 | MEDIUM — if Pol's setup proxies all frontend→backend traffic through Next.js (same-origin), strict could be used. Lax is the safe default. |
| A3 | OWASP "balanced" Argon2id (m=19MiB, t=2, p=1) is sufficient | Pitfall 4 | MEDIUM — the alternative profile (m=46MiB, t=1, p=1) is also OWASP-recommended. Either is defensible; planner picks one and documents the choice. |
| A4 | Resend's Python SDK async API (`send_async`) is the canonical way (vs sync `send` wrapped in `asyncio.to_thread`) | Pattern 3 | LOW — verified against Resend's own docs; if `send_async` is removed in a future version, `asyncio.to_thread(resend.Emails.send, params)` is a 1-line fallback. |
| A5 | `Limiter._check_request_limit_inner` is stable enough to use as a dependency call (option B in Pitfall 1) | Pattern 4 / Pitfall 1 | LOW — it's underscore-prefixed (semantically private); option A (proxy routes) avoids this and is the recommendation. |
| A6 | The `is_superuser`-hidden-from-API pattern via Pydantic computed_field works cleanly in v2 | Common Operation 2 | LOW — alternative is `Field(exclude=True)`; planner should pick one and verify with a serialization test. |
| A7 | `aiosmtplib` works to Mailpit on port 1025 without TLS, no auth | Pattern 3 | LOW — Mailpit defaults are plain SMTP on 1025; verified against docker-compose.yml line 70. |
| A8 | Putting the JWT signing secret in `ADMIN_JWT_PUBLIC_SECRET` exposed to Next.js middleware is acceptable since HS256 secret is symmetric | Pattern 5 (middleware) | MEDIUM — symmetric HS256 means the same secret signs AND verifies, so the Next.js middleware needs the same value as the backend. Alternative: use **RS256** (asymmetric) with public key in Next.js. Tradeoff: HS256 is faster + simpler; RS256 is stricter separation. CONTEXT didn't lock this — researcher recommendation: **HS256 with shared secret** for v1; flag as a Phase 11 hardening item to move to RS256 if any operator demo demands stricter key separation. |
| A9 | Phase 2 doesn't need a separate `/auth/refresh` endpoint because `DatabaseStrategy.read_token` rotates on every read | Pattern 2 | MEDIUM — if frontend code expects an explicit `/refresh` (some Bearer flows do), planner may need to add a wrapper. The cookie flow with DatabaseStrategy refresh-on-read is the canonical pattern but the planner should verify the admin Bearer flow matches the same model or adds an explicit refresh route. |

**Total assumptions: 9.** None block planning; A1 (version) and A8 (HS256 vs RS256) are the two worth confirming with Pol before the planner makes them load-bearing.

## Open Questions

1. **Version: v14 vs v15?**
   - What we know: CONTEXT.md says v14; PyPI's latest is 15.0.5 (released 2024-10, security-patched through 2025-03). v15 dropped Python 3.9 + Pydantic v1, both already on our stack. APIs we use are unchanged.
   - What's unclear: Was "v14" in CONTEXT a deliberate choice (e.g., known v15 regression) or a knowledge-cutoff artifact?
   - Recommendation: **planner pins v15.0.5** and notes the variance from CONTEXT. Discuss-checker can prompt Pol if desired.

2. **HS256 vs RS256 for JWT signing?**
   - What we know: HS256 is simpler (one secret) and faster (no asymmetric crypto). RS256 separates signing (backend private key) from verification (Next.js middleware public key) — cryptographically stricter.
   - What's unclear: How sensitive are operator demos to "perfect" key separation in v1?
   - Recommendation: **HS256 in v1**; document in `docs/security.md` (Phase 11 polish) that RS256 is a hardening upgrade. Re-evaluate when Phase 11 ToS / regulatory review happens.

3. **Refresh endpoint shape?**
   - What we know: Our custom `DatabaseStrategy.read_token` can rotate on every read (mint a new row + revoke the old one). This is one valid model.
   - What's unclear: Whether the admin Bearer flow needs an explicit `/admin/auth/refresh` route the frontend calls when the access token nears expiry — vs. rotation-on-every-read.
   - Recommendation: **planner adopts rotation-on-every-read** for both surfaces in v1; if the admin frontend requires explicit `/refresh` later, add it as a thin wrapper in Phase 2.5 or Phase 8.

4. **Where to surface password strength rules to the UI?**
   - What we know: Backend `validate_password` is authoritative; frontend should mirror for UX.
   - What's unclear: zod schema duplication or fetch the rules from `/auth/password-policy`?
   - Recommendation: **duplicate the zod schema** in v1 (4 rules; trivial to keep in sync). Phase 10 may centralize.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| PostgreSQL 16 | users, refresh_tokens tables | ✓ | 16-alpine (Phase 1) | — |
| Redis 7 | slowapi storage | ✓ | 7-alpine (Phase 1) | fakeredis for tests; in-memory `MemoryStorage` for local dev (degraded) |
| Mailpit | dev email | ✓ | latest (Phase 1) | — |
| `uv` (Python pkg mgr) | install fastapi-users + deps | ✓ | (Phase 1) | — |
| `pnpm` (Node pkg mgr) | install jose, zod, etc. | ✓ | 9.15.0 pinned (Phase 1) | — |
| Resend account / API key | staging+prod email | ✗ in dev (not needed); ✗ in staging/prod (Pol must provision) | — | Mailpit also works in staging if Resend not provisioned; planner should NOT block on this for the demo |
| Docker | docker-compose up | ✓ | (Phase 1) | — |

**Missing dependencies with no fallback:** None for Phase 2 execution.

**Missing dependencies with fallback:** Resend API key for staging/prod — until provisioned, `ENVIRONMENT=staging` can fall back to Mailpit. Planner should make the email branch defensible: if `RESEND_API_KEY` is empty, log a warning and fall back to Mailpit (or skip emails). Document in `docs/email.md`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3 + pytest-asyncio 0.25 (Phase 1 baseline; `asyncio_mode = "auto"`, `loop_scope="session"` on shared fixtures) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/auth/ -x` |
| Full suite command | `uv run pytest -x` (runs all Phase 1 + Phase 2 backend tests) + `pnpm --filter frontend test` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| AUTH-01 | Register with email + password; Argon2id hash; server validates strength | integration | `uv run pytest tests/auth/test_register.py -x` | ❌ Wave 0 |
| AUTH-01 | Weak password rejected with InvalidPasswordException | unit | `uv run pytest tests/auth/test_register.py::test_weak_password_rejected -x` | ❌ Wave 0 |
| AUTH-02 | Register triggers email to Mailpit | integration | `uv run pytest tests/auth/test_email_verification.py::test_register_sends_email -x` | ❌ Wave 0 |
| AUTH-03 | Verify token → user.is_verified=True; second use → 400 | integration | `uv run pytest tests/auth/test_email_verification.py::test_verify_single_use -x` | ❌ Wave 0 |
| AUTH-04 | Login sets cookie; refresh sees authenticated state | integration | `uv run pytest tests/auth/test_login.py::test_cookie_set_and_persists -x` | ❌ Wave 0 |
| AUTH-05 | Logout → refresh_tokens.revoked_at IS NOT NULL; subsequent API call → 401 | integration | `uv run pytest tests/auth/test_logout.py::test_logout_revokes_token -x` | ❌ Wave 0 |
| AUTH-06 | Password reset → token_version bumped → old cookie 401 | integration | `uv run pytest tests/auth/test_password_reset.py::test_reset_invalidates_sessions -x` | ❌ Wave 0 |
| AUTH-07 | Player cookie on /admin/* → 403; admin Bearer on /auth/users/me → 401 (no cookie) | integration | `uv run pytest tests/auth/test_admin_bearer.py -x` | ❌ Wave 0 |
| AUTH-08 | 6th login attempt in 1 min → 429 (per-IP); 6th to same email from different IPs → 429 (per-email) | integration | `uv run pytest tests/auth/test_rate_limit.py -x` | ❌ Wave 0 |
| AUTH-08 | 429 message does not reveal email existence | integration | `uv run pytest tests/auth/test_email_enumeration.py -x` | ❌ Wave 0 |
| AUTH-09 | Refresh token rotation: presenting an already-rotated token revokes ALL user tokens | integration | `uv run pytest tests/auth/test_refresh_rotation.py::test_reuse_detection_revokes_all -x` | ❌ Wave 0 |
| AUTH-09 | `refresh_tokens.token_hash` is the SHA256, raw token never stored | unit | `uv run pytest tests/auth/test_refresh_rotation.py::test_token_hash_is_sha256 -x` | ❌ Wave 0 |
| ROADMAP SC#5 | Non-admin Bearer on /admin/* → 403 | integration | `uv run pytest tests/auth/test_admin_bearer.py::test_non_admin_bearer_forbidden -x` | ❌ Wave 0 |
| Frontend AUTH-04 | `/login` page renders + posts to FastAPI | unit | `pnpm --filter frontend test src/app/__tests__/login.test.tsx` | ❌ Wave 0 |
| Frontend AUTH-07 | `/admin/*` redirected to `/admin/login` without admin_jwt cookie | unit | `pnpm --filter frontend test src/__tests__/middleware.test.ts` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/auth/ -x` (auth-only; <30s on testcontainer-warm runs)
- **Per wave merge:** `uv run pytest -x` (full backend suite) + `pnpm --filter frontend test`
- **Phase gate:** Full suite green BEFORE `/gsd-verify-work`; coverage ≥ 80% on `app/auth/*`

### Wave 0 Gaps

- [ ] `backend/tests/auth/__init__.py` — empty file (test package marker)
- [ ] `backend/tests/auth/conftest.py` — shared auth fixtures: `verified_user`, `admin_user`, `unverified_user`, `mailpit_messages` (clears Mailpit between tests via its HTTP API)
- [ ] `backend/tests/auth/test_register.py` — AUTH-01 (4 tests)
- [ ] `backend/tests/auth/test_login.py` — AUTH-04 (3 tests)
- [ ] `backend/tests/auth/test_logout.py` — AUTH-05 (2 tests)
- [ ] `backend/tests/auth/test_email_verification.py` — AUTH-02, AUTH-03 (4 tests)
- [ ] `backend/tests/auth/test_password_reset.py` — AUTH-06 (3 tests)
- [ ] `backend/tests/auth/test_refresh_rotation.py` — AUTH-09 (3 tests including the reuse-detection critical test)
- [ ] `backend/tests/auth/test_admin_bearer.py` — AUTH-07 (3 tests)
- [ ] `backend/tests/auth/test_rate_limit.py` — AUTH-08 (3 tests; uses fakeredis or a per-test Redis flush)
- [ ] `backend/tests/auth/test_email_enumeration.py` — AUTH-08 (2 tests: forgot-password 202 either way; login 401 timing within 50 ms)
- [ ] `frontend/src/__tests__/middleware.test.ts` — Edge runtime middleware tests
- [ ] `frontend/src/app/__tests__/login.test.tsx` — Login page rendering + Server Action form submission

**Framework install:** none — pytest, pytest-asyncio, httpx, testcontainers already in `[dependency-groups].dev`. Frontend has Vitest 2.1 from Phase 1.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | fastapi-users (Argon2id via pwdlib) + custom DatabaseStrategy |
| V3 Session Management | yes | DatabaseStrategy refresh-token rotation with reuse detection; HttpOnly + Secure + SameSite=Lax cookies |
| V4 Access Control | yes | `current_user(superuser=True)` on `/admin/*`; `is_verified=True` for protected player endpoints |
| V5 Input Validation | yes | pydantic schemas at API edge (`EmailStr`, password regex via `validate_password`); zod schemas in Next.js Server Actions |
| V6 Cryptography | yes | pwdlib (Argon2id); PyJWT[crypto] (HS256); never roll our own |
| V7 Error Handling / Logging | yes | Structlog (Phase 1) + Sentry (Phase 1); audit every state mutation via AuditService (Phase 1) |
| V8 Data Protection | yes | refresh_tokens.token_hash = SHA256 of raw token; never store raw |
| V9 Communications | yes (deployed) | TLS termination at Railway/Fly.io edge (out of code scope); cookie `Secure=True` outside dev |
| V11 Business Logic | partial | Rate limiting (slowapi) protects against credential stuffing; email enumeration mitigated |
| V13 API | yes | OpenAPI exposed by fastapi-users routers (automatic at `/docs`) |
| V14 Configuration | yes | All secrets via `Settings(BaseSettings)`; `.gitleaks.toml` blocks accidental commits (Phase 1) |

### Known Threat Patterns for {FastAPI + Next.js + Postgres}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Brute force login | Spoofing | slowapi per-IP + per-email 5/min |
| Credential stuffing | Spoofing | per-email rate limit (D-14); rotating IPs defeated by stacked decorators |
| Email enumeration via login response | Information Disclosure | dummy Argon2 compare on unknown email; identical 401 message; uniform timing |
| Email enumeration via forgot-password | Information Disclosure | fastapi-users default 202 either way (NEVER override) |
| Email enumeration via register | Information Disclosure | fastapi-users 400 "user already exists" — acceptable tradeoff (register is intentional state-creation; user already gave away their email by attempting) |
| Refresh-token theft | Spoofing | Reuse detection: presenting a revoked token → revoke ALL user tokens (DatabaseStrategy) |
| Session fixation | Spoofing | Cookie regenerated on login; old cookie not valid post-login |
| XSS stealing token | Tampering | HttpOnly cookie inaccessible to JS; admin Bearer in HttpOnly cookie too |
| CSRF on cookie endpoints | Tampering | SameSite=Lax cookies + login uses POST; for STATE-changing endpoints, Phase 11 should add CSRF token if cookies are accepted on cross-origin POSTs (currently same-origin via Next.js proxy → low risk in v1) |
| SQL injection | Tampering | SQLAlchemy parameterized queries; never f-string SQL |
| Algorithm confusion in JWT (`alg: none`) | Tampering | PyJWT requires explicit `algorithms=["HS256"]`; fastapi-users uses this correctly |
| Timing attack on hash compare | Information Disclosure | argon2-cffi uses constant-time compare |
| Argon2 OOM under concurrent login | DoS | Choose OWASP "balanced" profile (m=19MiB); cap concurrent logins via slowapi |
| Weak passwords | Spoofing | `validate_password` server-side; mirrored zod schema in Next.js for UX |
| Admin self-promotion via register | EoP | Register router returns is_superuser=False unconditionally; admin seeded only via `bin/create-admin.py` |
| Token leak via logs | Information Disclosure | Structlog `scrub_secrets` (Phase 1 D-25) covers SECRET_KEY, hashed_password, token, password keys |

## Project Constraints (from CLAUDE.md)

- **Mandatory phase workflow:** PHASES.md ownership tracking → research → plan → execute → verify → review → ship. Phase 2 marked `🔄 In progress` before any code lands.
- **Per-phase branch:** `gsd/phase-2-auth-identity` — never commit directly to main.
- **PR per phase:** opened via GitHub MCP `create_pull_request`. PR creation blocked without `PLAN.md` and `VERIFICATION.md`.
- **Use subagents whenever possible** — execution should dispatch independent tasks in parallel.
- **Python 3.12, uv, Docker required** for backend phases — already in place.
- **Spanish for conversation, English for code/paths** (project CLAUDE.md `~/CLAUDE.md`) — applies to docstrings + comments authored in code.
- **Audit-event prefix for Phase 2 is `auth.*`** (per `backend/CONVENTIONS.md §3`): `auth.guest_created`, `auth.session_started`, `auth.session_revoked`, `auth.email_verified`, `auth.password_reset_requested`, `auth.password_reset_completed`, `auth.admin_login_started`, `auth.admin_login_failed`.
- **tenant_id ghost column policy (CONVENTIONS §2):** `users` table MUST declare a nullable `tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid` — D-08 already locks this.
- **`extra="ignore"` on Settings:** Phase 2 APPENDS new env vars to `class Settings`; does not redefine the class. New vars go in `app/core/config.py`; `.env.example` mirrors them.
- **Test fixture pattern (CONVENTIONS established in Phase 1):** `pytest_asyncio.fixture(loop_scope="session")` for shared DB fixtures; `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]` per integration test file.
- **gitleaks pre-commit:** new env vars in `.env.example` must use placeholder values, never real secrets. `.gitleaks.toml` already allowlists `.planning/*` and `tests/*fixtures*`.

## Sources

### Primary (HIGH confidence)

- [fastapi-users v15 documentation](https://fastapi-users.github.io/fastapi-users/latest/) — User manager, routes, password-hash, full SQLAlchemy example
- [fastapi-users source: Strategy Protocol](https://github.com/fastapi-users/fastapi-users/blob/master/fastapi_users/authentication/strategy/base.py) — verified `read_token`/`write_token`/`destroy_token` signatures
- [fastapi-users routes documentation](https://fastapi-users.github.io/fastapi-users/latest/usage/routes/) — verified URLs, methods, status codes for all routers (auth, register, verify, reset-password, users)
- [fastapi-users dual-backend discussion #989](https://github.com/fastapi-users/fastapi-users/discussions/989) — maintainer-endorsed two-backend pattern
- [fastapi-users refresh-token discussion #350](https://github.com/fastapi-users/fastapi-users/discussions/350) — confirmation that refresh tokens are NOT built-in; custom Strategy is the canonical approach
- [pwdlib Argon2 source](https://github.com/frankie567/pwdlib/blob/main/pwdlib/hashers/argon2.py) — Argon2id (`type=ID`) is the default; underlying argon2-cffi
- [Next.js 15 Authentication guide](https://nextjs.org/docs/app/guides/authentication) — Server Actions, Server Components, DAL pattern, middleware optimistic checks, cookie API
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — Argon2id recommended params (m=19MiB t=2 p=1 OR m=46MiB t=1 p=1)
- [Resend Python SDK README](https://github.com/resend/resend-python) — `send_async` API confirmed for FastAPI async
- [slowapi extension source](https://raw.githubusercontent.com/laurentS/slowapi/master/slowapi/extension.py) — `limit()` signature, stacking semantics, `shared_limit()`

### Secondary (MEDIUM confidence)

- [slowapi examples doc](https://github.com/laurentS/slowapi/blob/master/docs/examples.md) — Redis storage_uri pattern, ASGI middleware vs HTTP middleware, custom cost
- [slowapi PyPI](https://pypi.org/project/slowapi/) — current 0.1.9 (last release 2023; library is stable but not actively patched)
- [argon2-cffi API docs](https://argon2-cffi.readthedocs.io/en/stable/api.html) — RFC 9106 profiles, `argon2.profiles.get_default_parameters()`
- [Resend Python docs](https://resend.com/docs/send-with-python) — API key setup, send params shape

### Tertiary (LOW confidence — verified via cross-reference)

- WebSearch results for slowapi multi-decorator stacking — verified against source code (HIGH after cross-ref).
- Medium tutorials for FastAPI + Next.js JWT — used for cross-reference only; no claims sourced solely from these.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pinned versions verified against PyPI; APIs verified against source code and official docs.
- Architecture (dual backend, custom Strategy, rate limiting): HIGH — verified against fastapi-users source + maintainer discussions.
- Email service pattern: HIGH — verified against fastapi-users hook signatures + Resend SDK README.
- Argon2id parameter selection: MEDIUM — OWASP gives two equally-valid profiles; planner picks one.
- HS256 vs RS256 decision: MEDIUM — not locked in CONTEXT; researcher recommends HS256 with explicit Phase 11 hardening flag.
- Next.js cookie + middleware integration: MEDIUM — patterns canonical per Next 15 docs but the exact Set-Cookie forwarding from Server Action requires a small empirical test (the `match` regex in `loginAction` is fragile; planner should verify and possibly refactor to a different forwarding approach).
- Pitfalls: HIGH — all 10 pitfalls grounded in either documentation or source review.

**Research date:** 2026-05-26
**Valid until:** 2026-07-26 (60 days — fastapi-users is in maintenance mode so versions are stable; slowapi has been stable at 0.1.9 since 2023; Next.js 15 doc was last updated 2026-05-19 per fetched metadata; main risk is a fastapi-users 15.x security patch — re-verify before planning if 60 days elapse)
