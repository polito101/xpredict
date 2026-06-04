# Phase 2: Auth & Identity - Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

**Players and admins can authenticate against a production-grade auth surface with verified email, persistent sessions, password reset, and rate-limited endpoints — distinct surfaces for player (cookie) and admin (Bearer).**

Phase 2 delivers all 9 AUTH requirements (AUTH-01..09):
- Player register + Argon2id password hashing + server-side strength validation
- Email verification (single-use time-limited link via Resend/Mailpit)
- Persistent cookie session (HTTP-only Secure SameSite) + refresh token rotation with DB-backed reuse detection
- Password reset via email (bumps token_version, invalidates all prior sessions)
- Admin distinct login route (`/admin/auth/login`) — Bearer JWT (not cookie)
- `is_superuser` flag enforced on every `/admin/*` endpoint
- Rate limiting per-IP and per-email (slowapi + Redis) on all auth endpoints

**Out of this phase entirely:**
- Wallet creation on registration → Phase 3 (needs `accounts` table)
- Sign-up bonus → Phase 5 (triggered on email verify but debits ledger)
- Ban/unban state machine UI → Phase 8 (column `is_active` + `banned_at` shipped NOW as nullable, logic in Phase 8)
- Branding configurable emails → Phase 10 (HTML inline in Phase 2 is sufficient)
- Admin user list / CRM → Phase 8

</domain>

<decisions>
## Implementation Decisions

### Auth Library

- **D-01: fastapi-users v14** — battle-tested, dual-backend pattern (cookie player + Bearer admin), Argon2id built-in, email verify + password reset out of the box. Saves ~400 lines of boilerplate vs hand-rolling.
- **D-02: Herencia múltiple `User(SQLAlchemyBaseUserTableUUID, Base)`** — patrón oficial de fastapi-users. Nuestro `User` hereda de su base (`SQLAlchemyBaseUserTableUUID`) y de nuestro `DeclarativeBase` (`app.db.base.Base`). `tenant_id` ghost column se añade normalmente como columna adicional.
- **D-03: Dos instancias FastAPIUsers separadas** — una con `CookieTransport + JWTStrategy` para players (prefijo `/auth/`), otra con `BearerTransport + JWTStrategy` para admin (prefijo `/admin/auth/`). El guard `is_superuser` se aplica en todos los routers `/admin/*`.
- **D-04: `DatabaseStrategy` custom con tabla `refresh_tokens`** — en lugar de `JWTStrategy` puro. Tabla: `(id, token_hash, user_id, expires_at, revoked_at, reuse_count)`. Reuse detection: si llega un token ya rotado, se revocan TODOS los tokens del usuario. Cumple AUTH-09 (revocación verificable en DB + éxito criteria #3 y #4 de ROADMAP).

### Email SMTP

- **D-05: Resend como proveedor** para staging y producción (free tier 3000/mes, SDK Python oficial, excelente deliverability). Mailpit para dev (ya operativo desde Phase 1 en docker-compose).
- **D-06: `ResendEmailSender` custom** — implementa el protocolo `BaseEmailSender` de fastapi-users. Switch por `ENVIRONMENT` env var: `dev` → Mailpit SMTP, `staging`/`prod` → Resend API. Un solo punto de configuración.
- **D-07: HTML simple inline** para templates de email (sin Jinja2 ni ficheros separados). Branding básico (nombre del proyecto + link prominente). Phase 10 añade branding configurable si es necesario.

### Users Table Schema

- **D-08: Schema completo en Phase 2** — la migración `0002_phase2_auth` crea la tabla `users` con todos los campos necesarios para las fases actuales y futuras:
  - Campos fastapi-users built-in: `id UUID PK`, `email TEXT UNIQUE`, `hashed_password TEXT`, `is_active BOOLEAN DEFAULT TRUE`, `is_superuser BOOLEAN DEFAULT FALSE`, `is_verified BOOLEAN DEFAULT FALSE`
  - Campos adicionales: `display_name TEXT nullable`, `banned_at TIMESTAMPTZ nullable` (Phase 8 lo usa), `token_version INT DEFAULT 0` (para invalidar sesiones en password reset), `tenant_id UUID nullable DEFAULT TENANT_DEFAULT`
  - Tabla `refresh_tokens`: `(id, token_hash TEXT UNIQUE, user_id UUID FK users, expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ nullable, reuse_count INT DEFAULT 0, created_at TIMESTAMPTZ)`
- **D-09: `is_superuser` internamente, `is_admin` en la API** — fastapi-users usa `is_superuser` en su lógica interna. Los Pydantic schemas de respuesta exponen `is_admin: bool` mapeando desde `is_superuser`. No se parchea fastapi-users.
- **D-10: `display_name` nullable** — incluido ahora para que Phase 3 (wallet) y Phase 8 (CRM) no necesiten ALTER TABLE.

### Admin Bootstrapping

- **D-11: Script de seeding `bin/create-admin.py`** — lee `FIRST_ADMIN_EMAIL` y `FIRST_ADMIN_PASSWORD` del entorno, hashea con Argon2id, inserta en `users` con `is_superuser=True`. Idempotente (no falla si ya existe). Se documenta en README. Añadir `FIRST_ADMIN_EMAIL` + `FIRST_ADMIN_PASSWORD` a `.env.example`.

### Frontend Auth

- **D-12: Rutas Next.js dedicadas** — páginas full-page con App Router: `/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email`. URLs compartibles + linkables desde emails de verify/reset. shadcn/ui `Form` + `Input` + `Button`.
- **D-13: Panel admin en `/admin/*`** — mismo Next.js, layout separado `app/admin/` con su propia navbar. Next.js middleware protege las rutas `/admin/*` comprobando el Bearer JWT. Un solo deploy.

### Rate Limiting

- **D-14: slowapi + Redis ya instalado** (Phase 1). Montar `SlowAPIMiddleware` en `main.py` en Phase 2. Límites AUTH-08: 5 intentos/minuto por IP + 5 intentos/minuto por email en `/auth/login`, `/auth/register`, `/auth/forgot-password`, `/auth/verify-email`. El 6º intento → 429 sin información leak sobre si el email existe.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` §Authentication & Identity (AUTH-01..09) — todos los requisitos locked
- `.planning/ROADMAP.md` §Phase 2 — goal, success criteria, pitfalls cubiertos

### Project Decisions
- `.planning/PROJECT.md` §Constraints — stack constraints (FastAPI, Next.js 15, Argon2, self-hosted auth)
- `.planning/PROJECT.md` §Key Decisions — "Auth self-hosted (FastAPI-users o equivalente)" + "Stack" decisions

### Phase 1 Context (inherited patterns)
- `.planning/phases/01-scaffold-foundations/01-CONTEXT.md` — D-07 (modular monolith structure), D-09 (Settings pattern), D-18 (Money alias), D-24 (structlog), D-26 (RequestIdMiddleware), D-28 (Sentry)

### Existing Code Patterns
- `backend/app/db/base.py` — `DeclarativeBase` que User debe extender
- `backend/app/core/config.py` — patrón `Settings(BaseSettings)` con `extra="ignore"`; Phase 2 añade `SESSION_SECRET_KEY`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `RESEND_API_KEY`, `FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD`
- `backend/app/core/audit/models.py` — patrón SQLAlchemy model (herencia de Base, UUID PK con python+server default, tenant_id)
- `backend/app/main.py` — factory pattern + lifespan; Phase 2 añade `SlowAPIMiddleware` aquí

### PITFALLS Reference
- `.planning/ROADMAP.md` §Phase 2 → "Critical pitfalls covered: PITFALL #8" — leer descripción completa de PITFALL #8 (refresh-token rotation, Argon2id, rate-limit, email enumeration prevention, HTTP-only Secure SameSite cookies)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/core/config.py` `Settings(BaseSettings)` — Phase 2 añade nuevos env vars aquí (no redefine la clase)
- `app/core/audit/service.py` `AuditService.record()` — llamar en register, login, logout, password reset, email verify
- `app/core/redis.py` — cliente Redis ya configurado; slowapi lo usa para rate limiting
- `app/db/session.py` — `AsyncSession` lazy factory + sessionmaker; fastapi-users necesita el get_async_session dependency
- `app/db/base.py` `Base` — User hereda de aquí además de `SQLAlchemyBaseUserTableUUID`
- `app/db/types.py` `Money` alias — no aplica a Phase 2 (no hay columnas de dinero)

### Established Patterns
- **Module layout**: `backend/app/auth/` con subcarpetas `models.py`, `service.py`, `router.py`, `schemas.py` — siguiendo el patrón de `app/core/audit/` y `app/core/feature_flags/`
- **Settings**: añadir nuevas vars a `class Settings` en `config.py`, no crear nuevos archivos de config
- **SQLAlchemy models**: UUID PK con `default=uuid4` + `server_default=func.gen_random_uuid()`, `tenant_id` con `default=lambda: get_settings().TENANT_ID_DEFAULT`
- **Test fixtures**: `pytest_asyncio.fixture(loop_scope="session")` para engine + async_session (patrón de Phase 1 tests de integración)
- **Pre-commit + gitleaks**: los nuevos env vars de Phase 2 deben ir a `.env.example` (no `.env.local`)

### Integration Points
- `app/main.py` — añadir `SlowAPIMiddleware` + incluir routers `/auth/*` y `/admin/auth/*`
- `backend/migrations/versions/` — nueva migración `0002_phase2_auth.py` (tabla `users` + `refresh_tokens`)
- `frontend/app/` — nuevas rutas `(auth)/login`, `(auth)/register`, `(auth)/forgot-password`, `(auth)/reset-password`, `(auth)/verify-email` + `admin/` layout
- `docker-compose.yml` — ya incluye `mailpit` service en SMTP 1025; no cambios necesarios para dev

</code_context>

<specifics>
## Specific Ideas

- El success criteria #3 del ROADMAP exige verificar que el refresh token esté revocado en la tabla `refresh_tokens` después de logout — la `DatabaseStrategy` custom hace esto verificable.
- El success criteria #4 exige que password reset bump `token_version` e invalide sesiones previas — `token_version` en la tabla `users` es el mecanismo.
- El success criteria #6 exige que el 6º intento de login en la ventana configurada retorne 429 sin leak de info sobre si el email existe — el error message debe ser genérico ("Too many attempts") tanto si el email existe como si no.
- `bin/create-admin.py` debe documentarse en README §"First-time setup" junto con los otros scripts de Phase 1 (`bin/dev`, `bin/dev.ps1`).

</specifics>

<deferred>
## Deferred Ideas

- **Wallet creation on registration** — Phase 3 crea la tabla `accounts`; el hook post-register que crea el wallet se implementa allí.
- **Sign-up bonus (1000 PLAY_USD)** — WAL-02, Phase 5 (triggered on email verify, debits ledger).
- **Ban/unban UI y lógica** — ADU-04/05, Phase 8. Los campos `is_active` y `banned_at` se crean ahora (nullable) para evitar ALTER TABLE en Phase 8.
- **Branding configurable en emails** — Phase 10 añade TenantConfig; el HTML inline de Phase 2 es suficiente para la demo.
- **OAuth / social login** — out of scope v1.
- **Passkeys / WebAuthn** — out of scope v1.

</deferred>

---

*Phase: 2-Auth & Identity*
*Context gathered: 2026-05-26*
