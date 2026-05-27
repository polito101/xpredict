# Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations — Research

**Researched:** 2026-05-26
**Domain:** Python 3.12 + FastAPI + Postgres 16 + Redis 7 + Celery + Next.js 15 — one-command Docker scaffold with money-column, audit-immutability, secrets, and observability foundations
**Confidence:** HIGH overall (Phase 1 has zero novel territory — every decision is sourced from CONTEXT.md, STACK.md, ARCHITECTURE.md, PITFALLS.md, all dated 2026-05-25 and cross-verified)

## Summary

Phase 1 ships **scaffolding only** — no product features, no business logic. It locks the non-negotiable foundations every later phase inherits: docker-compose stack (8 services), Alembic baseline migration with `tenant_id` ghost column, `audit_log` immutability via Postgres trigger + REVOKE, money-column standard enforced by a custom AST lint, secrets discipline (Pydantic BaseSettings + gitleaks in CI), and Sentry initialised across 4 surfaces (FastAPI / Celery worker / Celery beat / Next.js).

Every architectural decision is already locked in `01-CONTEXT.md` (47 decisions D-01..D-47) and traced to `.planning/research/STACK.md`, `ARCHITECTURE.md`, and `PITFALLS.md`. This research file's job is to **make those decisions executable by the planner**: surface exact version pins, the docker-compose healthcheck patterns (especially the redbeat filesystem heartbeat), the Alembic async/sync env.py shape, the Sentry init code for each of the 4 surfaces, and the validation architecture so `/gsd:plan-phase` step 5.5 can produce VALIDATION.md without re-research.

**Primary recommendation:** The planner can author tasks straight from CONTEXT.md — no architectural choices remain open. The only Claude's-discretion items are (D-44) the audit trigger error message wording, (D-45) the exact ruff/mypy rule selections, (D-46) extra gitleaks rules, and (D-47) the dev `bin/dev` / Makefile command names. Everything else is locked.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Copied verbatim from `01-CONTEXT.md` (`<decisions>` block) — 47 decisions across 11 groups. These are **non-negotiable** for the planner.

#### Repo & docker-compose
- **D-01:** Monorepo `backend/` + `frontend/` under `xpredict/` root. Phase 1 creates the directories. Root holds `docker-compose.yml`, `.env.local`, `.env.example`, `.gitleaks.toml`, `.pre-commit-config.yaml`, optional `pyproject.toml`, `README.md`.
- **D-02:** docker-compose services and host ports:
  - `db` — `postgres:16-alpine` → 5432
  - `redis` — `redis:7-alpine` → 6379
  - `mailpit` — `axllent/mailpit:latest` → SMTP 1025, web UI 8025
  - `backend` (api) — `./backend` Dockerfile, `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` → 8000
  - `worker` — same image as backend, `celery -A app.celery_app worker -l info -Q default`
  - `beat` — same image, `celery -A app.celery_app beat -S redbeat.RedBeatScheduler -l info`
  - `flower` — same image, `celery -A app.celery_app flower --port=5555` → 5555
  - `frontend` — `./frontend` Dockerfile, `pnpm dev` → 3000
- **D-03:** Healthchecks per service:
  - `db`: `pg_isready -U xpredict -d xpredict` every 5s, retries 5
  - `redis`: `redis-cli ping` every 5s, retries 5
  - `backend`: `curl -fsS http://localhost:8000/healthz` every 10s, retries 5
  - `worker`: `celery -A app.celery_app inspect ping -d celery@$$HOSTNAME` every 30s, retries 5
  - `beat`: filesystem heartbeat — beat writes `/tmp/celerybeat.heartbeat` every tick; healthcheck checks mtime < 60s old (redbeat doesn't expose a port)
  - `flower`: `curl -fsS http://localhost:5555/api/workers` every 30s
  - `frontend`: `curl -fsS http://localhost:3000/api/healthz` every 10s
  - `mailpit`: `curl -fsS http://localhost:8025` every 30s
- **D-04:** `depends_on` with `condition: service_healthy`: backend → db + redis; worker → db + redis; beat → db + redis; flower → redis; frontend → backend (soft).
- **D-05:** Named volumes — `pg_data`, `redis_data` (AOF), `mailpit_data`. No bind mounts for DB on Windows/macOS. Code is bind-mounted for hot-reload.
- **D-06:** docker-compose is dev-only. Staging/prod via Railway/Fly.io using same Dockerfiles.

#### Backend layout
- **D-07:** Module structure inside `backend/app/` — feature folders + shared infrastructure:
  ```
  backend/app/
    main.py                  # FastAPI app factory + middleware
    celery_app.py            # Celery factory + beat schedule
    core/                    # cross-cutting
      config.py              # Settings(BaseSettings)
      logging.py             # structlog config
      audit/{service.py,models.py}     # AuditService + AuditLog
      feature_flags/{service.py,models.py}
      health.py              # /healthz, /readyz
      sentry.py              # Sentry init helpers
    db/
      base.py                # DeclarativeBase, engine, sessionmaker
      session.py             # get_async_session dependency
      types.py               # Money = Annotated[Decimal, mapped_column(Numeric(18,4))]
    integrations/            # placeholder for Phase 6+
    auth/                    # Phase 2
    wallet/                  # Phase 3
    markets/                 # Phase 4
    bets/                    # Phase 5
    admin/                   # Phase 8
    routers/health.py        # mounts /healthz, /readyz
  alembic/versions/0001_phase1_foundations.py
  alembic/{env.py, script.py.mako}
  scripts/lint_money_columns.py
  tests/
    conftest.py
    core/{test_audit_immutability.py, test_feature_flags.py}
    test_health.py
    test_money_lint.py
  ```
  Phase 1 creates `core/`, `db/`, `routers/health.py`, and **placeholder directories** `integrations/`, `auth/`, `wallet/`, `markets/`, `bets/`, `admin/` (each with `__init__.py` and a `# Phase N owns this` comment).
- **D-08:** Dependency management = `pyproject.toml` + `uv` (lockfile `uv.lock`). Falls back to `pip install -e .`.
- **D-09:** Single `Settings` class in `app/core/config.py` extending `BaseSettings`, all env vars typed. `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`. Phase 1 settings:
  ```python
  ENVIRONMENT: Literal["dev","staging","prod"] = "dev"
  DATABASE_URL: PostgresDsn
  DATABASE_URL_SYNC: PostgresDsn         # Alembic
  REDIS_URL: RedisDsn
  SENTRY_DSN: str | None = None
  SENTRY_TRACES_SAMPLE_RATE: float = 0.1
  LOG_LEVEL: Literal["DEBUG","INFO","WARNING","ERROR"] = "INFO"
  TENANT_ID_DEFAULT: UUID = UUID("00000000-0000-0000-0000-000000000001")
  ```
  Phase 2+ appends `SESSION_SIGNING_KEY`, `ADMIN_TOKEN`, etc.
- **D-10:** `is_dev` / `is_prod` properties on `Settings` drive: structlog renderer, Sentry skip-unless-explicit, cookie Secure flag (Phase 2).

#### Frontend
- **D-11:** Package manager = `pnpm`. `package.json` + `pnpm-lock.yaml`.
- **D-12:** No monorepo tooling (no Turbo/Nx). Each subproject builds standalone.
- **D-13:** Next.js 15 (App Router), React 19, TS 5.5+, Tailwind 4, shadcn/ui via CLI. Phase 1 scaffolds `pnpm create next-app@latest`, installs `@sentry/nextjs`, adds `/api/healthz` route.
- **D-14:** Frontend Sentry uses `@sentry/nextjs` with `instrumentation-client.ts` + `instrumentation.ts` (Next.js 15 pattern). DSN from `NEXT_PUBLIC_SENTRY_DSN`. Synthetic trigger: `/api/sentry-test` route.

#### Database & migrations
- **D-15:** Alembic baseline `0001_phase1_foundations` creates only `audit_log` + `feature_flags`. Both include `tenant_id UUID NULL DEFAULT '00000000-0000-0000-0000-000000000001'`. Phases 2+ MUST include ghost column on player/market tables — enforced by code review + documented in `backend/CONVENTIONS.md`.
- **D-16:** Alembic configured with sync engine (psycopg2-binary) even though app uses asyncpg. `env.py` reads `DATABASE_URL_SYNC` from `Settings`.
- **D-17:** Money-column lint = custom Python script `scripts/lint_money_columns.py`. AST-walks `backend/app/**/models.py` + any `*models*.py`. For each `mapped_column(...)`: (1) if type is `Numeric`, assert precision=18 scale=4; (2) if column name matches money-suggesting pattern (`amount`, `balance`, `price`, `stake`, `payout`, `fee`, `volume`, `liquidity`, `credit`, `debit`, `cost`, `value`) AND type ≠ Money alias → fail with file+line; (3) if `Numeric(18,4)` used on non-money-named column → warn (not fail). Runs in pre-commit and CI via `uv run python scripts/lint_money_columns.py`.
- **D-18:** `Money` SQLAlchemy alias in `app/db/types.py`:
  ```python
  from decimal import Decimal
  from typing import Annotated
  from sqlalchemy.orm import mapped_column
  from sqlalchemy import Numeric
  Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]
  ```
  All money columns use `amount: Mapped[Money]`. Audit-log JSONB payload stores money as strings inside payloads.

#### Audit log
- **D-19:** `audit_log` schema (creates in 0001):
  ```sql
  CREATE TABLE audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor        TEXT NOT NULL,         -- "user:<uuid>" | "admin" | "system" | "celery:<task>"
    event_type   TEXT NOT NULL,         -- "auth.guest_created", "wallet.transfer", ...
    payload      JSONB NOT NULL,
    ip           INET NULL,
    tenant_id    UUID NULL DEFAULT '00000000-0000-0000-0000-000000000001'
  );
  CREATE INDEX ix_audit_log_occurred_at ON audit_log (occurred_at DESC);
  CREATE INDEX ix_audit_log_event_type  ON audit_log (event_type);
  CREATE INDEX ix_audit_log_actor       ON audit_log (actor);
  ```
- **D-20:** Immutability — two mechanisms:
  1. `BEFORE UPDATE OR DELETE` trigger calls `raise_audit_immutable()` which `RAISE EXCEPTION 'audit_log is append-only'`.
  2. `REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC`.
  Integration test asserts both `UPDATE` and `DELETE` raise `IntegrityError`/`DataError`.
- **D-21:** `AuditService.record(...)` API in `app/core/audit/service.py`:
  ```python
  class AuditService:
      @staticmethod
      async def record(
          session: AsyncSession,
          *,
          actor: str,
          event_type: str,
          payload: dict,
          ip: str | None = None,
          tenant_id: UUID | None = None,
      ) -> AuditLog:
          ...
  ```
  Caller passes own `AsyncSession` → audit insert in caller's transaction → atomic with underlying action. **Synchronous** ~1ms overhead is accepted in exchange for atomicity guarantee.
- **D-22:** If caller doesn't pass `tenant_id`, `AuditService` reads `Settings.TENANT_ID_DEFAULT`. v2 swaps to `current_tenant_var.get()`; API unchanged.

#### Observability
- **D-23:** structlog (not loguru — STACK.md §1.6).
- **D-24:** structlog renderer = `ConsoleRenderer(colors=True)` when `Settings.is_dev`; else `JSONRenderer()`. Configured once in `app/core/logging.py`, called from FastAPI lifespan and Celery `worker_init` signal.
- **D-25:** structlog processors in order: `add_log_level`, `TimeStamper(fmt="iso", utc=True)`, `StackInfoRenderer`, `format_exc_info`, custom `scrub_secrets` (drops keys named `password`, `password_hash`, `session_signing_key`, `admin_token`, `sentry_dsn`, `api_key`, `secret`, `xp_session`), renderer.
- **D-26:** FastAPI middleware binds `request_id` (UUID per request), `path`, `method`, `client_ip` to contextvar. Celery task body binds `task_id`, `task_name`.
- **D-27:** Sentry — one project per environment with tags. `xpredict-dev`, `xpredict-staging`, `xpredict-prod`. Every event tagged `service=api|worker|beat|frontend`. Free tier (5k events/month) is enough. `release` = `XPREDICT_VERSION` env (defaults to `dev-{git-sha}`).
- **D-28:** Sentry init points:
  - FastAPI: `sentry_sdk.init(dsn, integrations=[FastApiIntegration(), SqlalchemyIntegration()])` in `app/main.py` startup
  - Celery worker + beat: `sentry_sdk.init(dsn, integrations=[CeleryIntegration(), SqlalchemyIntegration()])` in Celery `worker_process_init` signal
  - Next.js: `@sentry/nextjs` with `instrumentation.ts` + `instrumentation-client.ts`
- **D-29:** Triple-trigger test endpoints (Phase 11 may remove or gate):
  - `GET /_sentry-test` (FastAPI) → `raise RuntimeError("sentry test from api")`
  - Celery task `app.core.sentry.sentry_test_task` → raises in worker; triggered via flower UI or `celery -A app.celery_app call app.core.sentry.sentry_test_task`
  - `GET /api/sentry-test` (Next.js) → throws in route handler

#### Healthchecks
- **D-30:** Two endpoints — `/healthz` (liveness, returns 200) and `/readyz` (readiness — checks DB SELECT 1 + Redis PING; 503 if either fails). Frontend `/api/healthz` returns `{"status":"ok"}` 200.
- **D-31:** No metrics endpoint in Phase 1. Prometheus deferred to Phase 11.

#### Secrets & CI
- **D-32:** `.env.example` committed, `.env.local` gitignored, no `.env` plaintext used.
- **D-33:** `.gitleaks.toml` extends default ruleset with custom rules (xpredict-session-signing-key, xpredict-admin-token). Default rules catch Sentry DSN, generic API keys, Postgres URLs with embedded passwords.
- **D-34:** gitleaks runs in (a) pre-commit hook, (b) CI on every PR — block on detect. Synthetic-secret commit test on separate branch never merged.
- **D-35:** pre-commit hooks: `ruff check --fix`, `ruff format`, `mypy app/`, `gitleaks protect --staged`, `python scripts/lint_money_columns.py`, frontend `pnpm lint && pnpm typecheck`. Mandatory for Pol; README documents install.
- **D-36:** CI = GitHub Actions. Workflows: `backend-ci.yml` (Python 3.12, uv sync, ruff, mypy, money-lint, pytest with testcontainers + fakeredis, gitleaks), `frontend-ci.yml` (Node 20, pnpm install --frozen-lockfile, lint, typecheck, build, Vitest), `security.yml` (gitleaks full-history weekly).

#### Feature flags
- **D-37:** `feature_flags` schema (creates in 0001):
  ```sql
  CREATE TABLE feature_flags (
    key         TEXT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    value       JSONB NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id   UUID NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    PRIMARY KEY (key, tenant_id)
  );
  ```
- **D-38:** `FeatureFlagService.is_enabled(key, tenant_id=None) -> bool`. Tenant-fallback query: `WHERE key=:key AND (tenant_id=:tenant OR tenant_id=:default) ORDER BY tenant_id=:tenant DESC LIMIT 1`. **Phase 1 ships simplest version — no cache; add cache when hot path needs it.**
- **D-39:** No admin UI for flags in v1. Seed migration `0001` inserts:
  - `stripe_recharge_enabled` = `false` (Phase 3)
  - `polymarket_sync_enabled` = `false` (Phase 6)
  - `admin_2fa_required` = `false` (v2 prep)

#### Cross-cutting
- **D-40:** Audit-event naming = dotted lowercase `domain.action` (e.g. `auth.guest_created`, `wallet.transfer.completed`). Documented in `backend/CONVENTIONS.md`.
- **D-41:** DB connection pool — asyncpg via SQLAlchemy `create_async_engine(pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=3600)`. No PgBouncer v1. Per PITFALLS.md #7: `SET LOCAL` ONLY, never session-level. No multi-tenant runtime → no `app.tenant_id` setting needed.
- **D-42:** `tenant_id` ghost column policy locked in `backend/CONVENTIONS.md`. Every player-owned + market table in v1 declares `tenant_id: Mapped[UUID | None] = mapped_column(default=Settings().TENANT_ID_DEFAULT)`. Code review enforces.
- **D-43:** README structure — prerequisites, one-command setup (`make dev` or `./bin/dev` wrapping `docker compose up -d && cd backend && uv run alembic upgrade head`), service URLs, how to run tests, contribution checklist. `README-SETUP.md` kept as deeper reference.

### Claude's Discretion

The planner picks:
- **D-44:** Exact wording of `audit_log_immutability_trigger` error message (suggested: `'audit_log is append-only — UPDATE and DELETE are forbidden'`).
- **D-45:** Exact `[tool.ruff]` / `[tool.mypy]` rule sets (suggested ruff `E,F,I,UP,B,C4,SIM,RUF`; mypy `strict = true` on `app/`, lax on `tests/`).
- **D-46:** Additional `.gitleaks.toml` rules beyond D-33 if Phase 1 introduces other secrets.
- **D-47:** Exact dev `Makefile` / `bin/dev` script entries (suggested: `dev`, `down`, `test`, `lint`, `format`, `db.shell`, `db.reset`, `seed`).

### Deferred Ideas (OUT OF SCOPE for Phase 1)

Captured during discussion — DO NOT plan these:
- PgBouncer / advanced connection pooling
- Prometheus metrics endpoint + Grafana dashboards (Phase 11)
- Database backup + restore tested procedure (Phase 11)
- OpenTelemetry distributed tracing
- Admin UI for feature flags (Phase 8)
- `tenant_id` runtime population via middleware (v2 multi-tenant)
- Postgres Row-Level Security policies (v2)
- Custom Ruff plugin for money-column (AST script sufficient)
- Async audit-event bus / Kafka / event-sourcing
- Pinned Python version manager (mise/asdf) in repo
- `pre-commit.ci` hosted runner
- Sentry source-map upload for frontend (Phase 11)
- Devcontainer / Codespaces config

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **PLT-01** | All tenant-scoped tables include nullable `tenant_id UUID` column with default constant for v1 (multi-tenant migration prep — flipping to NOT NULL + RLS is mechanical in v2). | `audit_log` (D-19) and `feature_flags` (D-37) both ship with the ghost column. Convention documented in `backend/CONVENTIONS.md` (D-42). Phases 2+ inherit pattern; enforced by code review. |
| **PLT-02** | All money mutations and admin actions go through the audit log — append-only enforced by Postgres trigger. | `AuditService.record()` API (D-21) + Postgres BEFORE UPDATE/DELETE trigger + REVOKE UPDATE,DELETE (D-20). Integration test `tests/core/test_audit_immutability.py` verifies both raise. |
| **PLT-03** | All secrets via Pydantic BaseSettings reading from environment; never hardcoded. | `Settings` class in `app/core/config.py` (D-09) with `SettingsConfigDict`. `.env.example` committed, `.env.local` gitignored, no `.env` plaintext (D-32). |
| **PLT-04** | `gitleaks` runs in CI to block accidental secret commits. | `.gitleaks.toml` extending default ruleset (D-33). gitleaks in pre-commit (D-34) + GitHub Actions `security.yml` (D-36). Synthetic secret commit test on throwaway branch validates CI block. |
| **PLT-06** | Feature flags table exists with prep for per-tenant config in v2 (single-row default for v1). | `feature_flags` table (D-37) with composite PK `(key, tenant_id)`. `FeatureFlagService.is_enabled(key, tenant_id=None)` (D-38) with tenant-fallback. Seed flags `stripe_recharge_enabled`, `polymarket_sync_enabled`, `admin_2fa_required` all default `false` (D-39). |
| **PLT-08** | Sentry receives errors from FastAPI + Celery + Next.js. | Sentry init in FastAPI (`FastApiIntegration + SqlalchemyIntegration`), Celery worker + beat (`CeleryIntegration`), Next.js (`@sentry/nextjs`) — all D-28. Triple-trigger test endpoints D-29. Single Sentry project per env, tagged `service=api|worker|beat|frontend` (D-27). |
| **PLT-10** | `docker-compose up` brings up full stack locally (api, worker, beat, db, redis, frontend, mailpit) with one command. | 8-service docker-compose (D-02), per-service healthchecks (D-03), `depends_on: condition: service_healthy` (D-04), named volumes for stateful services (D-05). `flower` is the 8th service (added by D-02; not strictly listed in PLT-10 but no harm). |
| **WAL-05** | All money columns use `NUMERIC(18,4)`; all Python money values use `Decimal` from strings — never float, never Postgres `MONEY`. | `Money` SQLAlchemy alias `Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]` (D-18). CI lint script `scripts/lint_money_columns.py` (D-17) blocks any new column that violates the standard. Negative tests `tests/test_money_lint.py` verify the linter fires correctly. |

**Phase 1 ships zero product features.** Every requirement above is foundational — Phases 2-10 inherit the contracts.

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP request routing | API / Backend (FastAPI) | — | FastAPI is the API tier; the frontend never talks to Postgres directly. |
| Server-side rendering (Phase 1: hello-world only) | Frontend Server (Next.js SSR) | — | Next.js 15 App Router; Phase 1 ships a hello-world page + `/api/healthz` route handler. |
| Persistence — audit_log, feature_flags | Database / Storage (Postgres 16) | — | SQL is the source of truth; SQLAlchemy is the access layer. |
| Background job orchestration | API / Backend (Celery worker + beat) | — | Phase 1 ships an empty beat schedule + a synthetic Sentry test task. Phase 2+ adds real periodic jobs. |
| Caching / broker | API / Backend (Redis 7) | — | Celery broker + result backend. Phase 2+ uses Redis for rate-limit, dedupe locks, etc. |
| Email catcher (dev only) | Infrastructure (Mailpit) | — | SMTP receiver for Phase 2+ email flows. Phase 1 just stands it up. |
| Worker monitoring | Infrastructure (Flower) | — | Celery UI; dev-only in Phase 1. |
| Settings & secrets | API / Backend (Pydantic BaseSettings) | — | Single `Settings()` class; never read env vars directly elsewhere. |
| Audit recording | API / Backend (AuditService) | Database (trigger + REVOKE) | Service writes; trigger is defense-in-depth for immutability. |
| Money-column enforcement | CI / build tier (AST lint) | Database (NUMERIC schema) | Lint catches at PR; DB schema is the runtime guarantee. |
| Error tracking | Cross-tier (Sentry SDK in FastAPI / Celery / Next.js) | — | One Sentry project per env, tagged per service. |
| Structured logging | API / Backend (structlog) | — | JSON in staging/prod, console in dev. FastAPI + Celery both call same init. |

**Why this matters for the planner:** every capability above has an unambiguous owner. Tasks should not put Sentry init logic in `db/`, money-column lint in `tests/` (it lives in `scripts/`), or feature-flag service in `routers/` (it lives in `core/feature_flags/`).

## Standard Stack

All versions sourced from `.planning/research/STACK.md` (HIGH confidence; verified via Context7 + PyPI mid-2026 at research time). slopcheck scan run 2026-05-26 — every package below returned status `OK` (no SLOP, no SUS).

### Core (backend)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | `>=3.12,<3.13` | Runtime | 3.12 long-stable, 3.13 GIL-free still experimental for C-ext deps. STACK.md §1.1. `[CITED: STACK.md §1.1]` |
| FastAPI | `>=0.115.7,<0.116.0` | HTTP framework | 0.115 is the long-stable line; minor-pinned because FastAPI is 0.x and minor bumps can break. `[CITED: STACK.md §1.1]` |
| Uvicorn | `>=0.32,<0.36` (use `[standard]`) | ASGI server | Bundles uvloop + httptools. `[CITED: STACK.md §1.1]` |
| Gunicorn | `>=23.0,<24.0` | Process manager (prod only — not in Phase 1 dev) | Wraps uvicorn workers; pinned for staging/prod readiness. `[CITED: STACK.md §1.1]` |
| Pydantic | `>=2.10,<3.0` | Models | v2 current; v1 EOL. `[CITED: STACK.md §1.1]` |
| pydantic-settings | `>=2.6,<3.0` | BaseSettings | Mandatory for D-09 / PLT-03. `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`. `[CITED: STACK.md §1.1]` |
| python-dotenv | `>=1.0,<2.0` | `.env` loader | Required by pydantic-settings. `[CITED: STACK.md §1.1]` |
| SQLAlchemy | `>=2.0.43,<2.1` | ORM/Core | 2.0 async API (`AsyncSession`, `Mapped[]`, `mapped_column`). **Never use 1.4-style `query(Model).filter(...)`.** `[CITED: STACK.md §1.2]` |
| asyncpg | `>=0.30,<0.32` | Async Postgres driver | High-perf; returns `Decimal` natively for `NUMERIC` — exactly what `Money` (D-18) needs. `[CITED: STACK.md §1.2]` |
| psycopg2-binary | `>=2.9.10,<3.0` | Sync Postgres driver for Alembic | Alembic env.py is sync-only by design (D-16). `[CITED: STACK.md §1.2]` |
| Alembic | `>=1.14,<2.0` | Migrations | Standard. `[CITED: STACK.md §1.2]` |
| greenlet | `>=3.1` (transitive) | SQLAlchemy async dependency | Auto-pulled; pin only if Docker build flakes. `[CITED: STACK.md §1.2]` |
| Celery | `>=5.5,<5.6` | Task queue | **Pin to 5.5, NOT 5.6**. 5.6 (Mar 2026) too fresh for prod. `[CITED: STACK.md §1.4]` |
| redis (py client) | `>=5.0,<6.0` | Broker + cache client | `[CITED: STACK.md §1.4]` |
| celery-redbeat | `>=2.2,<3.0` | Beat scheduler | Stores schedules in Redis; survives Beat restarts; HA-capable. `[CITED: STACK.md §1.4]` |
| flower | `>=2.0,<3.0` | Celery monitoring UI | `[CITED: STACK.md §1.4]` |
| httpx | `>=0.28,<0.29` | Async HTTP client | One shared `AsyncClient` per app (lifespan-managed). Phase 1 ships no outbound calls; Phase 6 uses for Polymarket. `[CITED: STACK.md §1.5]` |
| tenacity | `>=9.0,<10.0` | Retry policies | Used in Phase 6 Gamma client; Phase 1 installs but doesn't use. `[CITED: STACK.md §1.5]` |
| structlog | `>=24.4,<26.0` | Structured logging | `[CITED: STACK.md §1.6]` |
| sentry-sdk[fastapi,celery,sqlalchemy] | `>=2.18,<3.0` | Error tracking | Auto-instruments FastAPI, Celery, SQLAlchemy. `[CITED: STACK.md §1.6]` |
| slowapi | `>=0.1.9,<0.2` | Rate limiting | **Installed as dep in Phase 1, NOT mounted.** Phase 2 mounts on auth endpoints; Phase 5 on bet placement. `[CITED: STACK.md §1.7]` |

### Core (frontend)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | `>=15.1,<16.0` | App framework | App Router, async `cookies()/headers()`. **Stay on 15** — Next 16 removes sync access. `[CITED: STACK.md §4.1]` |
| React | `>=19.0,<20.0` | UI library | Required by Next 15 App Router. **Match `react-is` to same minor** (recharts needs it). `[CITED: STACK.md §4.1]` |
| TypeScript | `>=5.5,<5.8` | Static typing | `[CITED: STACK.md §4.1]` |
| Tailwind CSS | `>=4.0,<5.0` | Styling | v4 CSS-first config (`@theme`); new default in shadcn templates. `[CITED: STACK.md §4.1]` |
| shadcn/ui (CLI) | `>=3.0` | Component scaffolding (copy-paste, not npm dep) | Phase 1 may run `pnpm dlx shadcn@latest init` but doesn't need any components yet. `[CITED: STACK.md §4.1]` |
| @sentry/nextjs | latest 2.x | Sentry SDK for Next 15 | Auto-instruments App Router; uses `instrumentation.ts` + `instrumentation-client.ts`. `[CITED: STACK.md §1.6 + Sentry docs 2026]` |
| lucide-react | `>=0.460` | Icons (pulled in by shadcn) | `[CITED: STACK.md §4.1]` |

### Testing (Phase 1 acceptance)

| Library | Version | Purpose |
|---------|---------|---------|
| pytest | `>=8.3,<9.0` | Test runner | `[CITED: STACK.md §5.1]` |
| pytest-asyncio | `>=0.24,<0.26` | Async tests; `asyncio_mode = "auto"` | `[CITED: STACK.md §5.1]` |
| pytest-httpx | `>=0.32,<0.36` | Mock outbound httpx; Phase 1 has no outbound but install for Phase 6 prep | `[CITED: STACK.md §5.1]` |
| testcontainers | `>=4.8` (testcontainers-python) | Real Postgres in tests — NOT sqlite (audit trigger + NUMERIC + gen_random_uuid() all require PG) | `[CITED: STACK.md §5.1]` |
| dirty-equals | `>=0.8` | Better test assertions | `[CITED: STACK.md §5.1]` |
| fakeredis | `>=2.20` | In-memory Redis for unit tests | Common companion to testcontainers when Redis logic is light. `[ASSUMED]` (not explicitly pinned in STACK.md but mentioned in CONTEXT.md "tests" section under D-36) |
| factory-boy | `>=3.3` (optional) | Test factories | Optional; pleasant for Phase 2+. `[CITED: STACK.md §5.1]` |

### Dev tools

| Tool | Version | Purpose |
|------|---------|---------|
| uv | latest stable | Python deps + lockfile (D-08) | `[CITED: STACK.md §6.1 + CONTEXT.md D-08]` |
| ruff | `>=0.7,<0.9` | Lint + format. target-version = py312 | `[CITED: STACK.md §6.1]` |
| mypy | `>=1.13,<2.0` | Static types. Strict on `app/`, lax on `tests/` | `[CITED: STACK.md §6.1]` |
| pre-commit | `>=4.0,<5.0` | Pre-commit hooks | `[CITED: STACK.md §6.1]` |
| gitleaks | latest stable (binary action) | Secret scanning | `[CITED: STACK.md §6 + gitleaks docs 2026]` |
| pnpm | latest stable | Frontend deps | `[CITED: STACK.md §4.1 + CONTEXT.md D-11]` |

### Alternatives Considered (DO NOT use)

| Instead of | Could use | Why we picked the locked option |
|------------|-----------|-------|
| Celery 5.5 | Celery 5.6, ARQ, APScheduler, RQ | 5.6 too fresh; ARQ has no Beat; APScheduler breaks with >1 worker; RQ lacks Beat. `[CITED: STACK.md §1.4]` |
| structlog | loguru | loguru fights stdlib + has no OTel interop. `[CITED: STACK.md §1.6]` |
| uv | poetry, pip-tools | uv is 10-100x faster; single tool replaces pip+venv+pip-tools+pyenv. `[CITED: STACK.md §6.1 + CONTEXT.md D-08 specifics]` |
| pnpm | npm, yarn | Faster + correct hoisting; de-facto standard for Next.js 2026. `[CITED: STACK.md §4.1 + CONTEXT.md D-11]` |
| postgres:16-alpine | postgres:17-alpine | PG 17 GA but ~17% extension ecosystem still has issues. `[CITED: STACK.md §1.2]` |
| Mailpit | MailHog | MailHog unmaintained since 2020. `[CITED: STACK.md §6.3]` |
| Custom money-column AST lint | Ruff plugin | Ruff has no Python plugin API as of 2026.05. `[CITED: CONTEXT.md D-17 + STACK.md confirmed]` |
| Postgres MONEY type | NUMERIC(18,4) | MONEY is locale-dependent, returns strings, has decimal-math problems. `[CITED: STACK.md §9 + PITFALLS.md #4]` |
| FLOAT/REAL for money columns | NUMERIC(18,4) | Floating-point drift compounds invisibly — guaranteed audit failure. `[CITED: PITFALLS.md #4]` |

### Installation (planner builds the exact `pyproject.toml`)

```bash
# Backend — Phase 1 deps
uv add "fastapi[standard]@~0.115.7" "uvicorn[standard]>=0.32,<0.36" \
       "pydantic>=2.10,<3" "pydantic-settings>=2.6,<3" "python-dotenv>=1,<2" \
       "sqlalchemy>=2.0.43,<2.1" "asyncpg>=0.30,<0.32" "psycopg2-binary>=2.9.10,<3" "alembic>=1.14,<2" \
       "celery>=5.5,<5.6" "redis>=5,<6" "celery-redbeat>=2.2,<3" "flower>=2,<3" \
       "httpx>=0.28,<0.29" "tenacity>=9,<10" \
       "structlog>=24.4,<26" "sentry-sdk[fastapi,celery,sqlalchemy]>=2.18,<3" \
       "slowapi>=0.1.9,<0.2"

uv add --dev "pytest>=8.3,<9" "pytest-asyncio>=0.24,<0.26" "pytest-httpx>=0.32,<0.36" \
              "testcontainers>=4.8" "fakeredis>=2.20" "dirty-equals>=0.8" \
              "ruff>=0.7,<0.9" "mypy>=1.13,<2" "pre-commit>=4,<5"
```

```bash
# Frontend — Phase 1 deps
pnpm create next-app@latest frontend --typescript --tailwind --app --eslint --src-dir
cd frontend
pnpm add @sentry/nextjs
# (Phase 1 doesn't need shadcn yet, but the planner can run `pnpm dlx shadcn@latest init` to prep)
```

**Version verification (slopcheck run 2026-05-26):** All 31 Python packages + 7 npm packages above passed `slopcheck scan` with status `OK`. No slop, no suspicious flags.

## Package Legitimacy Audit

slopcheck installed and executable at `~/AppData/Roaming/Python/Python313/Scripts/slopcheck` on this machine. Ran against every package in the Standard Stack table on 2026-05-26.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| fastapi | PyPI | ~7 yr | >70M/wk | github.com/fastapi/fastapi | OK | Approved |
| uvicorn | PyPI | ~7 yr | >25M/wk | github.com/encode/uvicorn | OK | Approved |
| gunicorn | PyPI | ~15 yr | >30M/wk | github.com/benoitc/gunicorn | OK | Approved |
| pydantic | PyPI | ~8 yr | >180M/wk | github.com/pydantic/pydantic | OK | Approved |
| pydantic-settings | PyPI | ~3 yr | >30M/wk | github.com/pydantic/pydantic-settings | OK | Approved |
| python-dotenv | PyPI | ~12 yr | >50M/wk | github.com/theskumar/python-dotenv | OK | Approved |
| sqlalchemy | PyPI | ~18 yr | >70M/wk | github.com/sqlalchemy/sqlalchemy | OK | Approved |
| asyncpg | PyPI | ~9 yr | >10M/wk | github.com/MagicStack/asyncpg | OK | Approved |
| psycopg2-binary | PyPI | ~10 yr | >25M/wk | github.com/psycopg/psycopg2 | OK | Approved |
| alembic | PyPI | ~15 yr | >25M/wk | github.com/sqlalchemy/alembic | OK | Approved |
| celery | PyPI | ~15 yr | >12M/wk | github.com/celery/celery | OK | Approved |
| redis | PyPI | ~15 yr | >30M/wk | github.com/redis/redis-py | OK | Approved |
| celery-redbeat | PyPI | ~9 yr | >300k/wk | github.com/sibson/redbeat | OK | Approved |
| flower | PyPI | ~13 yr | >700k/wk | github.com/mher/flower | OK | Approved |
| httpx | PyPI | ~7 yr | >50M/wk | github.com/encode/httpx | OK | Approved |
| tenacity | PyPI | ~12 yr | >70M/wk | github.com/jd/tenacity | OK | Approved |
| structlog | PyPI | ~12 yr | >15M/wk | github.com/hynek/structlog | OK | Approved |
| sentry-sdk | PyPI | ~7 yr | >40M/wk | github.com/getsentry/sentry-python | OK | Approved |
| slowapi | PyPI | ~5 yr | >5M/wk | github.com/laurents/slowapi | OK | Approved |
| pytest | PyPI | ~15 yr | >70M/wk | github.com/pytest-dev/pytest | OK | Approved |
| pytest-asyncio | PyPI | ~10 yr | >15M/wk | github.com/pytest-dev/pytest-asyncio | OK | Approved |
| pytest-httpx | PyPI | ~5 yr | >5M/wk | github.com/Colin-b/pytest_httpx | OK | Approved |
| testcontainers | PyPI | ~8 yr | >5M/wk | github.com/testcontainers/testcontainers-python | OK | Approved |
| dirty-equals | PyPI | ~3 yr | >2M/wk | github.com/samuelcolvin/dirty-equals | OK | Approved |
| factory-boy | PyPI | ~13 yr | >12M/wk | github.com/FactoryBoy/factory_boy | OK | Approved |
| fakeredis | PyPI | ~9 yr | >3M/wk | github.com/cunla/fakeredis-py | OK | Approved |
| ruff | PyPI | ~3 yr | >30M/wk | github.com/astral-sh/ruff | OK | Approved |
| mypy | PyPI | ~12 yr | >30M/wk | github.com/python/mypy | OK | Approved |
| pre-commit | PyPI | ~11 yr | >15M/wk | github.com/pre-commit/pre-commit | OK | Approved |
| greenlet | PyPI | ~17 yr | >100M/wk | github.com/python-greenlet/greenlet | OK | Approved |
| aiocache | PyPI | ~8 yr | >2M/wk | github.com/aio-libs/aiocache | OK | Approved (Phase 1 doesn't install, but planner may add if simple cache becomes needed; D-38 explicitly defers) |
| next | npm | ~7 yr | >7M/wk | github.com/vercel/next.js | OK | Approved |
| react | npm | ~12 yr | >30M/wk | github.com/facebook/react | OK | Approved |
| react-dom | npm | ~12 yr | >30M/wk | github.com/facebook/react | OK | Approved |
| react-is | npm | ~7 yr | >25M/wk | github.com/facebook/react | OK | Approved |
| @sentry/nextjs | npm | ~5 yr | >2M/wk | github.com/getsentry/sentry-javascript | OK | Approved |
| typescript | npm | ~13 yr | >50M/wk | github.com/microsoft/TypeScript | OK | Approved |
| tailwindcss | npm | ~7 yr | >12M/wk | github.com/tailwindlabs/tailwindcss | OK | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

slopcheck was successfully installed and executed for this audit — no `[ASSUMED]` fallback was needed. All packages above are verified clean (downloads + age estimates are rough indicators sourced from training knowledge; the load-bearing claim is the slopcheck OK status returned 2026-05-26).

## Architecture Patterns

### System Architecture Diagram

```
                ┌─────────────────────────────────────────────────┐
                │                  DEVELOPER MACHINE              │
                │   docker compose up   ─►  one command, 8 svcs   │
                └────────────┬────────────────────────────────────┘
                             │
       ┌─────────────────────┼─────────────────────────────────────────┐
       │                     │                                         │
       ▼                     ▼                                         ▼
  ┌─────────┐          ┌─────────┐                              ┌──────────────┐
  │ frontend│ ◄───────►│ backend │ ◄────── HTTP /healthz ──────►│  curl probes │
  │ Next 15 │   8000   │ FastAPI │    healthcheck every 10s     │ (compose hc) │
  │   :3000 │          │  :8000  │                              └──────────────┘
  └────┬────┘          └────┬────┘
       │                    │ ── awaits db + redis healthy
       │                    ├──► AuditService (sync write inside caller's tx)
       │                    ├──► FeatureFlagService (DB lookup, no cache v1)
       │                    └──► Sentry SDK (FastApi + Sqlalchemy integrations)
       │
       │       ┌──────────────────────────────────────┐
       │       │                                      │
       ▼       ▼                                      ▼
 ┌──────────┐ ┌──────────┐    ┌──────────┐    ┌──────────┐
 │ frontend │ │ backend  │    │ worker   │    │   beat   │
 │ Sentry @ │ │ Sentry @ │    │ Sentry @ │    │ Sentry @ │
 │ instrument│ │ startup  │    │worker_init│   │worker_init│
 │   .ts    │ │ tagged    │   │  tagged   │   │  tagged   │
 │  service=│ │service=api│   │ service=  │   │ service=  │
 │ frontend │ └────┬─────┘    │  worker   │   │   beat    │
 └──────────┘      │          └─────┬─────┘   └─────┬─────┘
                   │                │ ── celery ──► │
                   │                │   ► broker    │
                   │                ▼               │
                   │           ┌──────────┐         │
                   │           │  redis 7 │ ◄───────┘ (RedBeat schedules)
                   │           │   :6379  │
                   │           │  AOF on  │
                   │           └────┬─────┘
                   │                │
                   │                │  healthcheck: redis-cli ping
                   │                │
                   ▼                ▼
              ┌──────────────────────────┐         ┌──────────────┐
              │     postgres 16-alpine   │         │   mailpit    │
              │           :5432          │         │  SMTP :1025  │
              │  ─ audit_log (immutable) │         │   web :8025  │
              │  ─ feature_flags         │         │  (Phase 2+)  │
              │  ─ alembic_version       │         └──────────────┘
              │  named volume pg_data    │
              │  healthcheck: pg_isready │
              └──────────────────────────┘                ▲
                                                          │
                                                  ┌───────┴────────┐
                                                  │     flower     │
                                                  │     :5555      │
                                                  │  Celery UI     │
                                                  └────────────────┘
```

**Data flow for Phase 1 acceptance:**
1. `docker compose up` brings all 8 services online.
2. `pg_isready` / `redis-cli ping` / `curl /healthz` / `find /tmp/celerybeat.heartbeat -mmin -1` all pass → every service has `healthy` status.
3. Backend runs `alembic upgrade head` → migration `0001` creates `audit_log` + `feature_flags` with `tenant_id` ghost column + immutability trigger.
4. Triple-trigger Sentry test: `GET /_sentry-test` (api), `celery call sentry_test_task` (worker), `GET /api/sentry-test` (frontend) → 3 distinct events in Sentry with `service` tag.
5. CI run: ruff + mypy + money-column lint + pytest + gitleaks all green.

### Recommended Project Structure

```
xpredict/
├── docker-compose.yml
├── .env.example
├── .env.local              # gitignored
├── .gitleaks.toml
├── .pre-commit-config.yaml
├── README.md
├── README-SETUP.md          # already exists — keep
├── bin/dev                   # or Makefile (D-47)
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py            # sync engine via psycopg2-binary, reads DATABASE_URL_SYNC
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_phase1_foundations.py
│   ├── scripts/
│   │   └── lint_money_columns.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── celery_app.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── sentry.py
│   │   │   ├── health.py
│   │   │   ├── audit/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── service.py
│   │   │   │   └── models.py
│   │   │   └── feature_flags/
│   │   │       ├── __init__.py
│   │   │       ├── service.py
│   │   │       └── models.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── types.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── health.py
│   │   ├── integrations/__init__.py        # placeholder, comment "# Phase 6 owns this"
│   │   ├── auth/__init__.py                # placeholder, "# Phase 2 owns this"
│   │   ├── wallet/__init__.py              # placeholder, "# Phase 3 owns this"
│   │   ├── markets/__init__.py             # placeholder, "# Phase 4 owns this"
│   │   ├── bets/__init__.py                # placeholder, "# Phase 5 owns this"
│   │   └── admin/__init__.py               # placeholder, "# Phase 8 owns this"
│   ├── CONVENTIONS.md         # tenant_id ghost column policy, audit-event naming
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py        # testcontainers Postgres + fakeredis fixtures
│       ├── test_health.py
│       ├── test_money_lint.py
│       └── core/
│           ├── __init__.py
│           ├── test_audit_immutability.py
│           └── test_feature_flags.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── pnpm-lock.yaml
    ├── next.config.ts          # withSentryConfig wrapper
    ├── instrumentation.ts      # server-side Sentry init
    ├── instrumentation-client.ts  # browser Sentry init
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx
    │   │   ├── page.tsx        # hello-world
    │   │   └── api/
    │   │       ├── healthz/route.ts
    │   │       └── sentry-test/route.ts
    │   └── ...
    └── tsconfig.json

.github/workflows/
├── backend-ci.yml
├── frontend-ci.yml
└── security.yml
```

### Pattern 1: docker-compose healthcheck contract

**What:** Every service in `docker-compose.yml` ships a `healthcheck:` block; downstream services wait via `depends_on: { condition: service_healthy }`.

**When to use:** Always in Phase 1 — PLT-10 demands `docker-compose up` works as one command.

**Pattern (sketch — planner authors the full file):**

```yaml
# docker-compose.yml — Phase 1 skeleton
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: xpredict
      POSTGRES_PASSWORD: xpredict
      POSTGRES_DB: xpredict
    ports: ["5432:5432"]
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U xpredict -d xpredict"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    ports: ["6379:6379"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"  # SMTP
      - "8025:8025"  # web UI
    volumes:
      - mailpit_data:/data
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8025"]
      interval: 30s
      timeout: 5s
      retries: 3

  backend:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports: ["8000:8000"]
    volumes:
      - ./backend:/app
    environment:
      DATABASE_URL: postgresql+asyncpg://xpredict:xpredict@db:5432/xpredict
      DATABASE_URL_SYNC: postgresql+psycopg2://xpredict:xpredict@db:5432/xpredict
      REDIS_URL: redis://redis:6379/0
      SENTRY_DSN: ${SENTRY_DSN:-}
      ENVIRONMENT: dev
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  worker:
    build: ./backend
    command: celery -A app.celery_app worker -l info -Q default
    volumes: [./backend:/app]
    environment: <same as backend>
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "celery -A app.celery_app inspect ping -d celery@$$HOSTNAME || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s

  beat:
    build: ./backend
    command: celery -A app.celery_app beat -S redbeat.RedBeatScheduler -l info
    volumes:
      - ./backend:/app
      - beat_heartbeat:/tmp        # so the heartbeat file persists between checks
    environment: <same as backend>
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      # filesystem heartbeat — find returns the file iff modified in <1 min
      test: ["CMD-SHELL", "[ $$(find /tmp/celerybeat.heartbeat -mmin -1 2>/dev/null | wc -l) -eq 1 ] || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 60s

  flower:
    build: ./backend
    command: celery -A app.celery_app flower --port=5555
    ports: ["5555:5555"]
    environment: <same as backend>
    depends_on:
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:5555/api/workers"]
      interval: 30s
      timeout: 5s
      retries: 5

  frontend:
    build: ./frontend
    command: pnpm dev
    ports: ["3000:3000"]
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next
    environment:
      NEXT_PUBLIC_SENTRY_DSN: ${NEXT_PUBLIC_SENTRY_DSN:-}
      NEXT_PUBLIC_API_URL: http://backend:8000
    depends_on:
      backend: { condition: service_started }     # soft — frontend hot-reload survives backend restarts
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:3000/api/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

volumes:
  pg_data:
  redis_data:
  mailpit_data:
  beat_heartbeat:
```

**Source:** `D-02, D-03, D-04, D-05` (CONTEXT.md). Pattern verified against Nautobot's `CELERY_BEAT_HEARTBEAT_FILE` pattern (Sources: see [Celery beat healthcheck file](https://github.com/nautobot/nautobot/pull/5434), [Celery School heartbeat post](https://celery.school/posts/docker-healthcheck-for-celery-workers/)). **The beat scheduler must `touch /tmp/celerybeat.heartbeat` on every tick** — this is implemented inside `app/celery_app.py` via a `beat_init` signal handler or by patching `RedBeatScheduler.tick`. Planner picks the cleanest implementation.

**Windows-specific gotcha:** `volumes: - ./backend:/app` is a bind mount; on Windows it's slow but acceptable for dev. The DB and Redis use **named volumes** (D-05) precisely to avoid bind-mount slowness on Windows/macOS. The `beat_heartbeat` named volume is shared with the beat container so the healthcheck can find the file.

### Pattern 2: Alembic env.py with sync engine + async app

**What:** Alembic is sync-only by design. App uses asyncpg; Alembic uses psycopg2-binary. Two `DATABASE_URL` env vars — `DATABASE_URL` (app, asyncpg) + `DATABASE_URL_SYNC` (Alembic, psycopg2).

**When to use:** D-16 (Phase 1) — every later phase's migration runs through this env.py.

**Pattern:**

```python
# backend/alembic/env.py — Phase 1 baseline
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Import metadata so autogenerate works
from app.db.base import Base                # DeclarativeBase
from app.core.audit.models import AuditLog  # noqa: F401 - register table
from app.core.feature_flags.models import FeatureFlag  # noqa: F401
from app.core.config import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL_SYNC))

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    context.configure(
        url=str(settings.DATABASE_URL_SYNC),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Baseline migration shape (`0001_phase1_foundations.py`):**

```python
"""phase1 foundations: audit_log + feature_flags + ghost column

Revision ID: 0001_phase1_foundations
Revises:
Create Date: 2026-XX-XX
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0001_phase1_foundations"
down_revision = None
branch_labels = None
depends_on = None

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"

def upgrade() -> None:
    # ---- audit_log ----
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("ip", postgresql.INET, nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True,
                  server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid")),
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", [sa.text("occurred_at DESC")])
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])

    # ---- audit_log immutability ----
    op.execute("""
        CREATE OR REPLACE FUNCTION raise_audit_immutable() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only -- UPDATE and DELETE are forbidden';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_log_immutability_trigger
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION raise_audit_immutable();
    """)
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;")

    # ---- feature_flags ----
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("value", postgresql.JSONB, nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True,
                  server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid")),
        sa.PrimaryKeyConstraint("key", "tenant_id"),
    )

    # ---- seed default flags (D-39) ----
    op.execute(f"""
        INSERT INTO feature_flags (key, enabled, tenant_id) VALUES
          ('stripe_recharge_enabled', FALSE, '{TENANT_DEFAULT}'),
          ('polymarket_sync_enabled', FALSE, '{TENANT_DEFAULT}'),
          ('admin_2fa_required',     FALSE, '{TENANT_DEFAULT}');
    """)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutability_trigger ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS raise_audit_immutable()")
    op.drop_table("feature_flags")
    op.drop_table("audit_log")
```

**Source:** [Alembic cookbook async](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic). Pattern verified against [Berk Karaal — FastAPI + Async SQLAlchemy 2 + Alembic](https://berkkaraal.com/blog/2024/09/19/setup-fastapi-project-with-async-sqlalchemy-2-alembic-postgresql-and-docker/) and [Alembic with Async SQLAlchemy](https://www.brandonwie.dev/posts/alembic-async-sqlalchemy). The sync-engine-with-async-app pattern is the established idiom.

### Pattern 3: Audit-log immutability — Postgres trigger + REVOKE

**What:** Two layers of defense — (1) a `BEFORE UPDATE OR DELETE` trigger that raises an exception (works even for superuser), (2) `REVOKE UPDATE, DELETE` so the GRANT level rejects first.

**When to use:** D-20 (PLT-02) — every later phase's audit row touches this table via `AuditService.record()`.

**Pattern (already encoded in the baseline migration above):**

```sql
CREATE OR REPLACE FUNCTION raise_audit_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only -- UPDATE and DELETE are forbidden';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_immutability_trigger
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION raise_audit_immutable();

REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
```

**Test pattern (planner authors `tests/core/test_audit_immutability.py`):**

```python
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError, IntegrityError

@pytest.mark.asyncio
async def test_audit_log_update_blocked(async_session):
    """A direct UPDATE must raise — both REVOKE and the trigger should fire."""
    # Insert a row first (allowed)
    await async_session.execute(text("""
        INSERT INTO audit_log (actor, event_type, payload)
        VALUES ('system', 'test.row', '{}'::jsonb)
    """))
    await async_session.commit()

    with pytest.raises(DBAPIError) as exc_info:
        await async_session.execute(text("""
            UPDATE audit_log SET actor = 'mutated' WHERE actor = 'system'
        """))
        await async_session.commit()
    # Match either the REVOKE error or the trigger message
    assert "append-only" in str(exc_info.value).lower() or "permission denied" in str(exc_info.value).lower()

@pytest.mark.asyncio
async def test_audit_log_delete_blocked(async_session):
    await async_session.execute(text("""
        INSERT INTO audit_log (actor, event_type, payload)
        VALUES ('system', 'test.delete', '{}'::jsonb)
    """))
    await async_session.commit()

    with pytest.raises(DBAPIError) as exc_info:
        await async_session.execute(text("DELETE FROM audit_log WHERE actor = 'system'"))
        await async_session.commit()
    assert "append-only" in str(exc_info.value).lower() or "permission denied" in str(exc_info.value).lower()
```

**Source:** D-20 (CONTEXT.md), [Modern Treasury — Immutability & Double-Entry](https://www.moderntreasury.com/journal/enforcing-immutability-in-your-double-entry-ledger). Live-bets sibling repo (per `01-CONTEXT.md`) uses the same trigger pattern for its `round_events` table.

### Pattern 4: Money-column AST lint

**What:** A Python script that walks the AST of every `*models.py` and `*models*.py` file, finds `mapped_column(...)` calls, and enforces three rules (D-17):
1. If type is `Numeric`, precision must = 18 and scale must = 4.
2. If column name matches money-suggesting pattern AND type is anything other than `Money` (or `Numeric(18,4)`) → fail.
3. If `Numeric(18,4)` used on column NOT in money-suggesting list → warn.

**When to use:** D-17 (WAL-05) — every PR runs the lint; CI fails on exit-code non-zero.

**Pattern (skeleton — planner writes the full ~80 LOC):**

```python
# backend/scripts/lint_money_columns.py
"""
Enforces money-column standard (WAL-05) — runs as pre-commit hook + CI gate.

Rules (per CONTEXT.md D-17):
  R1. Numeric(p,s) must have precision=18 AND scale=4
  R2. Column name matching money-suggesting pattern must use `Money` alias
      (or equivalent Numeric(18,4))
  R3. Numeric(18,4) on non-money-named column → warning (typo detector)

Exit code: 0 on pass; 1 on any R1 or R2 failure (R3 warnings printed but don't fail).
"""
import ast
import sys
from pathlib import Path

MONEY_NAMES = {
    "amount", "balance", "price", "stake", "payout", "fee", "volume",
    "liquidity", "credit", "debit", "cost", "value",
}

class MoneyColumnLinter(ast.NodeVisitor):
    def __init__(self, file: Path) -> None:
        self.file = file
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # Looking for `name: Mapped[T] = mapped_column(...)` patterns
        if not isinstance(node.target, ast.Name):
            return self.generic_visit(node)
        col_name = node.target.id
        if not isinstance(node.value, ast.Call):
            return self.generic_visit(node)
        # mapped_column(...) - check args for Numeric(...)
        call = node.value
        if not (isinstance(call.func, ast.Name) and call.func.id == "mapped_column"):
            return self.generic_visit(node)

        numeric_args = self._find_numeric_args(call)
        is_money_name = col_name.lower() in MONEY_NAMES
        uses_money_alias = self._uses_money_alias(node)

        if numeric_args is not None:
            precision, scale = numeric_args
            # R1
            if precision != 18 or scale != 4:
                self.errors.append(
                    f"{self.file}:{node.lineno}: '{col_name}' uses Numeric({precision},{scale}); "
                    f"must be Numeric(18,4) [WAL-05]"
                )
            # R3 (warning)
            if not is_money_name:
                self.warnings.append(
                    f"{self.file}:{node.lineno}: '{col_name}' uses Numeric(18,4) but name is "
                    f"not in money-list — typo or unintentional Money type?"
                )
        else:
            # R2 — column is named like money but doesn't use Numeric(18,4) or Money alias
            if is_money_name and not uses_money_alias:
                self.errors.append(
                    f"{self.file}:{node.lineno}: '{col_name}' has money-suggesting name but "
                    f"is not Money / Numeric(18,4) [WAL-05]"
                )
        self.generic_visit(node)

    def _find_numeric_args(self, call: ast.Call) -> tuple[int, int] | None:
        for arg in call.args:
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "Numeric":
                precision = arg.args[0].value if arg.args else None
                scale = arg.args[1].value if len(arg.args) > 1 else None
                # Also check keyword args
                for kw in arg.keywords:
                    if kw.arg == "precision":
                        precision = kw.value.value
                    elif kw.arg == "scale":
                        scale = kw.value.value
                if precision is not None and scale is not None:
                    return precision, scale
        return None

    def _uses_money_alias(self, node: ast.AnnAssign) -> bool:
        # crude: Mapped[Money] or Mapped[Annotated[Decimal, ...]]
        if not isinstance(node.annotation, ast.Subscript):
            return False
        inner = node.annotation.slice
        if isinstance(inner, ast.Name) and inner.id == "Money":
            return True
        return False


def lint(root: Path) -> int:
    files = list(root.rglob("**/models.py")) + list(root.rglob("**/*models*.py"))
    total_errors, total_warnings = 0, 0
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        linter = MoneyColumnLinter(f)
        linter.visit(tree)
        for e in linter.errors:
            print(f"ERROR: {e}")
            total_errors += 1
        for w in linter.warnings:
            print(f"WARN:  {w}")
            total_warnings += 1
    if total_errors:
        print(f"\nFAIL: {total_errors} money-column violations", file=sys.stderr)
        return 1
    print(f"OK: {len(files)} files checked, {total_warnings} warnings.")
    return 0


if __name__ == "__main__":
    sys.exit(lint(Path("app")))
```

**Test pattern (`tests/test_money_lint.py`):** Use `tmp_path` to write small Python files exhibiting (a) pass case, (b) Numeric without precision/scale → fail, (c) Float for `balance` → fail, (d) Numeric(18,4) for `radius` → warn-only-pass, then invoke `lint(tmp_path)` and assert return code.

**Source:** D-17 (CONTEXT.md), PITFALLS.md #4. There's no published OSS example of this exact lint (the pattern is too project-specific) — the AST-walk pattern is standard Python; SQLAlchemy's `mapped_column` API is documented at [SQLAlchemy 2.0 type basics](https://docs.sqlalchemy.org/en/20/core/type_basics.html). Confidence: HIGH on rule shape (verified against PITFALLS.md), MEDIUM on AST node-matching robustness — recommend extra test coverage for edge cases.

### Pattern 5: Sentry init — 4 surfaces

**What:** Sentry SDK initialised in 4 distinct entry points. Single Sentry project per env; events tagged `service=` for filtering.

**When to use:** D-28 (PLT-08).

#### 5a. FastAPI (`app/main.py`)

```python
# app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import Settings
from app.core.logging import configure_logging
from app.routers import health

settings = Settings()

def init_sentry_api() -> None:
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", "api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings)
    init_sentry_api()
    yield

app = FastAPI(lifespan=lifespan, title="XPredict API")
app.include_router(health.router)

# Sentry triple-trigger test endpoint (D-29)
@app.get("/_sentry-test")
async def sentry_test() -> dict:
    raise RuntimeError("sentry test from api")
```

#### 5b. Celery worker + beat (`app/celery_app.py`)

```python
# app/celery_app.py
import sentry_sdk
from celery import Celery
from celery.signals import worker_process_init, beat_init
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from app.core.config import Settings
from app.core.logging import configure_logging

settings = Settings()
celery_app = Celery("xpredict", broker=str(settings.REDIS_URL), backend=str(settings.REDIS_URL))

@worker_process_init.connect
def _init_worker(**_kwargs) -> None:
    configure_logging(settings)
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[CeleryIntegration(), SqlalchemyIntegration()],
        )
        sentry_sdk.set_tag("service", "worker")

@beat_init.connect
def _init_beat(**_kwargs) -> None:
    configure_logging(settings)
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[CeleryIntegration(), SqlalchemyIntegration()],
        )
        sentry_sdk.set_tag("service", "beat")
    # Heartbeat file for healthcheck (D-03 beat)
    from pathlib import Path
    import threading
    def _heartbeat() -> None:
        while True:
            Path("/tmp/celerybeat.heartbeat").touch()
            threading.Event().wait(30)  # touch every 30s
    threading.Thread(target=_heartbeat, daemon=True).start()

# Sentry test task (D-29)
@celery_app.task(name="app.core.sentry.sentry_test_task")
def sentry_test_task() -> None:
    raise RuntimeError("sentry test from worker")

# Empty beat schedule — phases 2-7 will add tasks
celery_app.conf.beat_schedule = {}
celery_app.conf.beat_scheduler = "redbeat.RedBeatScheduler"
celery_app.conf.redbeat_redis_url = str(settings.REDIS_URL)
```

#### 5c. Next.js (`instrumentation.ts` + `instrumentation-client.ts`)

```typescript
// frontend/instrumentation.ts (server-side)
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    Sentry.init({
      dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
      tracesSampleRate: 0.1,
      environment: process.env.NODE_ENV,
      initialScope: { tags: { service: "frontend" } },
    });
  }
}

export const onRequestError = Sentry.captureRequestError;  // Next.js 15 hook
```

```typescript
// frontend/instrumentation-client.ts (browser)
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: 0.1,
  environment: process.env.NODE_ENV,
  initialScope: { tags: { service: "frontend" } },
});
```

```typescript
// frontend/next.config.ts — wrap with Sentry config
import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  // standard Next config
};

export default withSentryConfig(nextConfig, {
  silent: !process.env.CI,
  org: "xpredict",
  project: "xpredict-dev",  // or staging/prod per env
});
```

```typescript
// frontend/src/app/api/sentry-test/route.ts (D-29)
export async function GET(): Promise<Response> {
  throw new Error("sentry test from frontend");
}
```

**Source:** D-28, D-29 (CONTEXT.md), [Sentry Next.js manual setup](https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/), [Sentry FastAPI integration](https://docs.sentry.io/platforms/python/integrations/fastapi/), [Sentry Celery integration](https://docs.sentry.io/platforms/python/integrations/celery/). Pattern verified: `onRequestError = Sentry.captureRequestError` is the Next.js 15 server-error hook (requires `@sentry/nextjs >= 8.28.0`).

### Pattern 6: structlog setup + request_id contextvar binding

**What:** Configure structlog once at startup (FastAPI lifespan + Celery worker_init). Bind `request_id` via FastAPI middleware using `structlog.contextvars`.

**When to use:** D-23 through D-26 — every Phase 2+ logs through structlog.

**Pattern:**

```python
# app/core/logging.py
import logging
import sys
import structlog
from app.core.config import Settings

SCRUB_KEYS = {
    "password", "password_hash", "session_signing_key",
    "admin_token", "sentry_dsn", "api_key", "secret", "xp_session",
}

def scrub_secrets(_logger, _name, event_dict: dict) -> dict:
    for k in list(event_dict.keys()):
        if k.lower() in SCRUB_KEYS:
            event_dict[k] = "***"
    return event_dict

def configure_logging(settings: Settings) -> None:
    # Stdlib root logger captures everything (FastAPI, Uvicorn, Celery)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.LOG_LEVEL,
    )
    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if settings.is_dev
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,         # binds request_id, etc.
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            scrub_secrets,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(settings.LOG_LEVEL),
        cache_logger_on_first_use=True,
    )
```

```python
# app/main.py — request_id middleware (use pure ASGI, not BaseHTTPMiddleware)
import uuid
import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

class RequestIdMiddleware:
    """Bind request_id, path, method, client_ip into structlog context per request.
    Use pure ASGI middleware (not BaseHTTPMiddleware) because contextvars set in
    endpoints must remain visible in the finally block.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid.uuid4()),
            path=scope["path"],
            method=scope["method"],
            client_ip=(scope.get("client") or ["unknown"])[0],
        )
        try:
            await self.app(scope, receive, send)
        finally:
            structlog.contextvars.clear_contextvars()

app.add_middleware(RequestIdMiddleware)
```

**Source:** [structlog Context Variables](https://www.structlog.org/en/latest/contextvars.html), [Logging setup for FastAPI, Uvicorn and Structlog (nymous gist)](https://gist.github.com/nymous/f138c7f06062b7c43c060bf03759c29e), [Apitally — FastAPI logging guide](https://apitally.io/blog/fastapi-logging-guide). The pure-ASGI middleware caveat is from the [FastAPI discussion 8632](https://github.com/fastapi/fastapi/discussions/8632) — `BaseHTTPMiddleware` runs endpoints in a task group that creates a copy of the context.

### Pattern 7: gitleaks CI + pre-commit

**What:** gitleaks in (a) pre-commit (`gitleaks protect --staged` — fast, scans only staged diff), (b) GitHub Actions on every PR (full HEAD scan), (c) weekly full-history scan.

**When to use:** D-33, D-34, D-36.

**`.gitleaks.toml` skeleton:**

```toml
# .gitleaks.toml — extends gitleaks defaults
title = "XPredict gitleaks config"
[extend]
useDefault = true

# Custom rules for keys Phase 1+ introduces
[[rules]]
id = "xpredict-session-signing-key"
description = "XPredict session signing key (Phase 2)"
regex = '''SESSION_SIGNING_KEY\s*=\s*['"]?[A-Za-z0-9+/=]{32,}'''
tags = ["secret", "key"]

[[rules]]
id = "xpredict-admin-token"
description = "XPredict admin token (Phase 2)"
regex = '''ADMIN_TOKEN\s*=\s*['"]?[A-Za-z0-9_-]{16,}'''
tags = ["secret", "key"]

[allowlist]
description = "Test fixtures and docs"
paths = [
  '''\.gitleaks\.toml$''',
  '''README.*\.md$''',
  '''docs/.*\.md$''',
  '''tests/.*fixtures.*''',
]
```

**`.pre-commit-config.yaml` (Phase 1 minimum):**

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2     # planner verifies latest stable at execution time
    hooks:
      - id: gitleaks
        args: ["protect", "--staged", "--config=.gitleaks.toml"]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.4      # planner verifies latest stable
    hooks:
      - id: ruff
        args: ["--fix", "--exit-non-zero-on-fix"]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        files: ^backend/app/
        additional_dependencies: [pydantic, sqlalchemy, types-redis]

  - repo: local
    hooks:
      - id: lint-money-columns
        name: Money column standard (WAL-05)
        entry: bash -c 'cd backend && uv run python scripts/lint_money_columns.py'
        language: system
        pass_filenames: false
        files: ^backend/.*models.*\.py$
```

**`.github/workflows/security.yml`:**

```yaml
name: security
on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"   # weekly full-history scan, Monday 06:00 UTC

permissions:
  contents: read

jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_CONFIG: .gitleaks.toml
```

**Source:** D-33-D-36 (CONTEXT.md), [gitleaks GitHub Actions docs](https://github.com/gitleaks/gitleaks#configuration), [d4b — Local Gitleaks pre-commit hook](https://www.d4b.dev/blog/2026-02-01-gitleaks-pre-commit-hook/), [gitleaks repo](https://github.com/gitleaks/gitleaks).

### Pattern 8: FeatureFlagService — minimal v1

**What:** DB-backed lookup with tenant-fallback. **No cache** in Phase 1 — query every call. Phase 2+ may add `aiocache`-backed cache when a hot path needs it (deferred per D-38).

**When to use:** D-38 (PLT-06).

**Pattern:**

```python
# app/core/feature_flags/models.py
from sqlalchemy import Text, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from uuid import UUID as PyUUID
from app.db.base import Base
from app.core.config import Settings

class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    key:        Mapped[str] = mapped_column(Text, primary_key=True)
    enabled:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    value:      Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(),
                                                 onupdate=func.now())
    tenant_id:  Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: Settings().TENANT_ID_DEFAULT,
    )
```

```python
# app/core/feature_flags/service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.core.feature_flags.models import FeatureFlag
from app.core.config import Settings

class FeatureFlagService:
    @staticmethod
    async def is_enabled(
        session: AsyncSession,
        key: str,
        tenant_id: UUID | None = None,
    ) -> bool:
        """Return whether a feature flag is enabled for the given tenant.

        Tenant-fallback: prefer a tenant-specific row over the default-tenant row.
        Phase 1 has no per-tenant overrides yet, so it always finds the default row.
        """
        settings = Settings()
        target_tenant = tenant_id or settings.TENANT_ID_DEFAULT
        stmt = (
            select(FeatureFlag)
            .where(
                FeatureFlag.key == key,
                FeatureFlag.tenant_id.in_([target_tenant, settings.TENANT_ID_DEFAULT]),
            )
            # Prefer the tenant-specific row
            .order_by(FeatureFlag.tenant_id == target_tenant.bytes.hex(), )
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        return bool(row and row.enabled)
```

**Test pattern (`tests/core/test_feature_flags.py`):** Seed `stripe_recharge_enabled=false`, assert `is_enabled` returns `False`. Toggle to `true`, assert `True`. Try a non-existent key, assert `False` (default-deny). Try with a custom tenant_id that has no row, assert it falls back to default-tenant row.

**Source:** D-37, D-38, D-39 (CONTEXT.md).

### Anti-Patterns to Avoid

- **❌ Loguru / print() / Python logging without structlog config** — fights stdlib, breaks Sentry/structlog correlation. `[PITFALLS.md §1.6]`
- **❌ Using `SET app.tenant_id` (session-level) instead of `SET LOCAL`** — connection-pool contamination across tenants. v1 isn't multi-tenant yet but D-41 establishes the doctrine. `[PITFALLS.md #7]`
- **❌ `Numeric()` without precision/scale** — defaults are DB-dependent; could silently store as `numeric` with unbounded precision (waste) or 0 scale (rounding). Always `Numeric(18, 4)`. `[PITFALLS.md #4]`
- **❌ `Decimal(0.1)` instead of `Decimal("0.1")`** — passing float to Decimal retains the binary error. `[PITFALLS.md #4]`
- **❌ Editing or deleting from `audit_log` from app code** — the trigger will raise; even attempts indicate a bug. Always insert. `[D-20]`
- **❌ Reading env vars directly with `os.getenv(...)`** — bypasses `Settings`, leaks secrets into logs, no typing. Always read through `Settings()`. `[D-09, PLT-03]`
- **❌ `BaseHTTPMiddleware` for context-var binding** — runs endpoints in a task group that copies the context; bound values won't be visible in the finally block. Use pure ASGI middleware. `[structlog contextvars docs + FastAPI discussion #8632]`
- **❌ `tenant_id NOT NULL` in v1** — the ghost column is **nullable** (D-15, D-19, D-37); v2 will flip it. Code that assumes NOT NULL breaks. `[D-15]`
- **❌ Running Alembic with asyncpg** — Alembic is sync-only; use psycopg2 + `DATABASE_URL_SYNC`. `[D-16]`
- **❌ sqlite in tests for anything wallet/audit-touching** — sqlite lacks `gen_random_uuid()`, triggers, `NUMERIC` semantics, row-level locking. Use testcontainers Postgres. `[STACK.md §5.1]`

## Don't Hand-Roll

| Problem | Don't build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async Postgres driver | Custom asyncio over libpq | `asyncpg` | Returns `Decimal` natively, decade of edge cases handled. |
| Settings management | `os.getenv()` + manual casting | `pydantic-settings.BaseSettings` | Typed env validation, `.env` loading, secret introspection. |
| Structured logging | `logging.LoggerAdapter` + json formatter | `structlog` | Threadsafe + async contextvars; Sentry integration is automatic. |
| Error tracking | Custom exception capture | `sentry-sdk` with FastAPI/Celery integrations | Auto-instruments request lifecycle; transactions; releases. |
| Beat scheduling | cron + `celery worker` | `celery-redbeat` | HA-ready (Redis-stored schedules), runtime mutation. |
| Secret scanning | Regex-grep in pre-commit | `gitleaks` | Default ruleset covers most providers; allowlist for fixtures. |
| Money type | Float, int (cents), Postgres MONEY | `Numeric(18,4)` + Python `Decimal` from strings | Exact arithmetic; asyncpg ↔ Decimal seamless. |
| Decimal SQLAlchemy mapping | Hand-roll `Numeric(18,4)` on every column | `Money = Annotated[Decimal, mapped_column(Numeric(18,4), nullable=False)]` (D-18) | DRY + lint-checkable + planner-friendly. |
| Audit immutability | Application-level "don't update" rule | Postgres trigger + REVOKE (D-20) | Two layers of defense; works even when raw SQL is used. |
| Healthcheck for Celery beat | Bash script polling Redis for the scheduler row | filesystem heartbeat file (`/tmp/celerybeat.heartbeat` mtime check) | Pattern is battle-tested in Nautobot; doesn't require Redis introspection. |
| Test DB | sqlite-in-memory | testcontainers Postgres (session-scoped) | Real PG semantics; trigger + NUMERIC + UUID all work natively. |

**Key insight:** Phase 1's whole job is to install correct foundations so Phases 2-10 inherit them. Hand-rolling any of these would mean each later phase pays the cost again — for zero v1 benefit. The hand-rolling we DO accept is the money-column AST lint (D-17), and that's only because Ruff has no Python plugin API as of 2026.05.

## Common Pitfalls

### Pitfall 1: Beat heartbeat file not actually written
**What goes wrong:** docker-compose `beat` service is `healthy` for the first 60s (start_period) then permanently `unhealthy` because nothing is touching `/tmp/celerybeat.heartbeat`.
**Why it happens:** Developers wire up the `healthcheck:` block but forget to add the `beat_init`-signal-triggered thread that touches the file every tick. The signal fires once at startup; you need a recurring task.
**How to avoid:** Implement a daemon thread in `app/celery_app.py` triggered by `beat_init` that touches the file every 30s. Alternative: subclass `RedBeatScheduler.tick` and add the touch there.
**Warning signs:** `docker compose ps` shows `beat (unhealthy)` after 90s of running; flower shows beat is alive.

### Pitfall 2: Alembic migrations fail in Docker because the network alias differs
**What goes wrong:** Local Alembic from the host uses `DATABASE_URL_SYNC=postgresql+psycopg2://xpredict:xpredict@localhost:5432/xpredict`; running inside the backend container `localhost` is the container itself, not the `db` service.
**Why it happens:** `.env.example` shows one URL; Docker compose passes through; the engineer doesn't notice.
**How to avoid:** **Always** run `alembic upgrade head` via `docker compose exec backend uv run alembic upgrade head` OR via a host-side env file that uses `localhost`. The `bin/dev` script (D-47) should default to compose-exec.
**Warning signs:** `psycopg2.OperationalError: connection refused`.

### Pitfall 3: Pydantic v2 `BaseSettings` rejects unknown env vars by default
**What goes wrong:** Adding a new env var in `.env.local` for a future phase causes the app to fail on startup with `ValidationError`.
**Why it happens:** `pydantic-settings` v2 defaults to `extra="forbid"`.
**How to avoid:** D-09 explicitly sets `SettingsConfigDict(extra="ignore")`. Verify in the actual `config.py`.
**Warning signs:** `ValidationError: extra fields not permitted` on startup.

### Pitfall 4: `Annotated[Decimal, mapped_column(...)]` chain breaks on `nullable=True`
**What goes wrong:** The `Money` alias declares `nullable=False`. If a column is intended to be nullable (e.g., a refund amount), naively using `Money` breaks.
**Why it happens:** `Annotated`-baked mapped_column kwargs are fixed; the column must override them.
**How to avoid:** For nullable money, use `amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)` directly. The lint (D-17) still validates the type. Document in `CONVENTIONS.md`.
**Warning signs:** Schema migration errors; "cannot override Annotated metadata".

### Pitfall 5: Sentry events arrive without `service` tag (or wrong tag)
**What goes wrong:** All 4 surfaces send events to the same Sentry project, but filtering by `service=worker` returns events from `api` too because the worker process inherited the API's process-level Sentry init.
**Why it happens:** Sentry SDK uses process-global state. If `init_sentry_api()` is called somewhere that gets imported by the Celery worker (because `app.main` is imported), both inits race.
**How to avoid:** Sentry init must happen in the `worker_process_init` / `beat_init` signals — **not** at module-level. Set `set_tag("service", "worker")` immediately after init.
**Warning signs:** Two Sentry events for one error (one tagged api, one tagged worker); same `release` value with mixed `service` tags.

### Pitfall 6: gitleaks pre-commit blocks legitimate test fixtures
**What goes wrong:** The synthetic-secret CI test commit (D-34) needs a fake secret in a known file; pre-commit blocks the developer from committing it locally.
**Why it happens:** No allowlist for test fixtures.
**How to avoid:** `.gitleaks.toml` `[allowlist]` includes `tests/.*fixtures.*` and `docs/.*\.md$`. The synthetic-secret test lives on a throwaway branch and is `commit --no-verify`'d intentionally to validate that CI catches it.
**Warning signs:** Developer cannot commit; CI passes when the same file is forced.

### Pitfall 7: structlog contextvars leak across tasks
**What goes wrong:** Celery worker processes 2 tasks; the second task's logs show the first task's `task_id` because contextvars weren't cleared.
**Why it happens:** Celery's worker reuses the thread; structlog contextvars persist across task invocations.
**How to avoid:** Use `task_prerun` / `task_postrun` signals to `structlog.contextvars.clear_contextvars()` and re-bind with the new `task_id`.
**Warning signs:** Logs from task B show `task_id=<A>`.

### Pitfall 8: Windows-specific line endings break shell heredocs in docker-compose
**What goes wrong:** docker-compose `command:` arrays with multi-line shell snippets get CRLF line endings on Windows, breaking inside Linux containers.
**Why it happens:** Git config `core.autocrlf=true` on Windows.
**How to avoid:** Add `.gitattributes` with `* text=auto eol=lf` for `Dockerfile`, `docker-compose.yml`, `*.sh`. Keep all multi-line commands in scripts checked-in with LF endings.
**Warning signs:** `bash: invalid character '$\r'` or `command not found` inside container.

### Pitfall 9: Named-volume permissions break when host UID ≠ container UID
**What goes wrong:** Postgres in alpine runs as user `postgres` (UID 70); the named volume created on Linux has different permissions. Restarting after `down -v` re-creates and works, but in-place permission changes break.
**Why it happens:** Default volume mode + alpine UID handling.
**How to avoid:** Use `postgres:16-alpine`'s recommended `PGDATA=/var/lib/postgresql/data/pgdata` subdir pattern; do **not** mount over the entire `/var/lib/postgresql/data` — use the subdir. Or accept that `docker compose down -v && up` is the dev workflow when permissions get weird.
**Warning signs:** `permission denied` in Postgres init logs.

### Pitfall 10: The `tenant_id` default UUID is wrong on one table but right on others
**What goes wrong:** `audit_log` uses `'00000000-0000-0000-0000-000000000001'`; `feature_flags` is also supposed to but a typo on one column inserts NULL or a different default.
**Why it happens:** UUID constants typed by hand.
**How to avoid:** Define `TENANT_ID_DEFAULT` once in `Settings` (D-09) AND in the migration as a top-level constant. Migration test asserts `SELECT tenant_id FROM feature_flags` returns the same UUID for every seeded row.
**Warning signs:** Lookups silently miss rows because the WHERE clause doesn't match.

## Runtime State Inventory

> Phase 1 is greenfield — there is no pre-existing runtime state to rename or migrate. Section omitted per instructions ("Include this section for rename/refactor/migration phases only").

## Code Examples

### `app/core/config.py` (D-09)

```python
# app/core/config.py
from typing import Literal
from uuid import UUID
from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    DATABASE_URL: PostgresDsn
    DATABASE_URL_SYNC: PostgresDsn
    REDIS_URL: RedisDsn
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    TENANT_ID_DEFAULT: UUID = UUID("00000000-0000-0000-0000-000000000001")

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT == "dev"

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "prod"
```

### `app/db/types.py` (D-18)

```python
# app/db/types.py
from decimal import Decimal
from typing import Annotated
from sqlalchemy import Numeric
from sqlalchemy.orm import mapped_column

Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]
"""All money columns MUST be typed as `Mapped[Money]` per WAL-05.
The `scripts/lint_money_columns.py` CI gate enforces this at every PR."""
```

### `app/db/session.py` (D-07)

```python
# app/db/session.py
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import Settings

settings = Settings()

engine = create_async_engine(
    str(settings.DATABASE_URL),
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.is_dev,
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

### `app/routers/health.py` (D-30)

```python
# app/routers/health.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.session import get_async_session
# Phase 1 also ships app/core/redis.py exposing get_redis() — used in Phase 2+

router = APIRouter(tags=["health"])

@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@router.get("/readyz")
async def readyz(
    session: AsyncSession = Depends(get_async_session),
    # redis: Redis = Depends(get_redis),  # Phase 1 ships get_redis() as a stub
) -> dict:
    failures: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        failures["db"] = str(exc)
    # try:
    #     await redis.ping()
    # except Exception as exc:
    #     failures["redis"] = str(exc)
    if failures:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "failures": failures})
    return {"status": "ready"}
```

### `app/core/audit/models.py` + `service.py` (D-19, D-21)

```python
# app/core/audit/models.py
from datetime import datetime
from uuid import UUID as PyUUID
from sqlalchemy import Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.core.config import Settings

class AuditLog(Base):
    __tablename__ = "audit_log"
    id:          Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                                server_default=func.gen_random_uuid())
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now(),
                                                  nullable=False)
    actor:       Mapped[str] = mapped_column(Text, nullable=False)
    event_type:  Mapped[str] = mapped_column(Text, nullable=False)
    payload:     Mapped[dict] = mapped_column(JSONB, nullable=False)
    ip:          Mapped[str | None] = mapped_column(INET, nullable=True)
    tenant_id:   Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        default=lambda: Settings().TENANT_ID_DEFAULT,
    )
```

```python
# app/core/audit/service.py
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.audit.models import AuditLog
from app.core.config import Settings

class AuditService:
    @staticmethod
    async def record(
        session: AsyncSession,
        *,
        actor: str,
        event_type: str,
        payload: dict,
        ip: str | None = None,
        tenant_id: UUID | None = None,
    ) -> AuditLog:
        """Record an audit event in the caller's transaction. Caller must commit.

        Phases 2-10 MUST NOT do raw INSERTs into audit_log — use this method.
        """
        row = AuditLog(
            actor=actor,
            event_type=event_type,
            payload=payload,
            ip=ip,
            tenant_id=tenant_id or Settings().TENANT_ID_DEFAULT,
        )
        session.add(row)
        await session.flush()
        return row
```

## State of the Art

| Old approach | Current approach | When changed | Impact |
|--------------|------------------|--------------|--------|
| pip + venv + requirements.txt | uv + pyproject.toml + uv.lock | 2025 (uv 0.4) | 10-100x faster installs; single tool replaces 4. `[CITED: STACK.md §6.1]` |
| SQLAlchemy 1.4 `Query` API | SQLAlchemy 2.0 `select() + session.execute()` | 2.0 GA Jan 2023 | Async-native; type-checked. **Never use 1.4 style.** `[CITED: STACK.md §1.2]` |
| `passlib` for hashing | `pwdlib[argon2]` | 2024 (fastapi-users v14) | passlib effectively unmaintained. (Phase 1 doesn't hash, but Phase 2 will.) `[CITED: STACK.md §1.3]` |
| MailHog | Mailpit | 2020+ (MailHog unmaintained) | Active fork; same protocol. `[CITED: STACK.md §6.3]` |
| Loguru for "ergonomic" logging | structlog | OpenTelemetry interop needs | structlog wins for FastAPI/Sentry/OTel. `[CITED: STACK.md §1.6]` |
| Next.js Pages Router | Next.js 15 App Router | Next 13+ stable, defaults in 14+ | RSC, Server Actions, streaming. **App Router only** for new code. `[CITED: STACK.md §4.1]` |
| sync `cookies()` / `headers()` in Next | `await cookies()` / `await headers()` | Next 15 | Next 16 removes sync access entirely. **Use async in Phase 1.** `[CITED: STACK.md §4.2]` |
| `useFormState` | `useActionState` | React 19 | Renamed. `[CITED: STACK.md §9]` |
| Tailwind 3 `tailwind.config.js` | Tailwind 4 CSS-first `@theme` | Tailwind 4 (2025) | Different mental model; ~30min onboarding. `[CITED: STACK.md §4.1]` |
| `db.session.query(...)` | `select(...).where(...)` + `await session.execute(...)` | SQLAlchemy 2.0 | Mandatory for async. `[CITED: STACK.md §1.2]` |
| `BaseHTTPMiddleware` for context binding | Pure ASGI middleware classes | FastAPI/Starlette discussion #8632 | contextvars survive into finally block. `[CITED: structlog docs]` |

**Deprecated / outdated (do NOT use):**
- `passlib`, `bcrypt`-direct, `psycopg2` for async, `pages/` router, `sync` request APIs in Next 15, `useFormState`, Recharts <2.15 on React 19, `moment.js`, `requests` library (use httpx), MailHog, APScheduler in multi-worker apps, Celery 5.6 (too fresh), Pydantic v1, SQLModel for this scope.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `fakeredis>=2.20` is the right version pin for in-memory Redis in tests | Testing table | LOW — fakeredis is widely used and stable; STACK.md §5.1 doesn't explicitly pin it but CONTEXT.md D-36 mentions it. Worst case: planner pins a different version. |
| A2 | The exact gitleaks pre-commit rev (`v8.21.2`) is the latest stable | Pattern 7 | LOW — planner verifies at execution time and pins what's actually current. |
| A3 | `aiocache` is the natural choice if a feature-flag cache becomes needed (D-38 explicitly defers, but planner may want to know what to use later) | Package audit | LOW — D-38 defers the cache decision; this is a forward-looking note only. |
| A4 | Sentry's `@sentry/nextjs` v8.28.0+ exports `Sentry.captureRequestError` for the `onRequestError` Next.js 15 hook | Pattern 5c | LOW — verified against [Sentry Next.js manual setup docs](https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/); planner re-verifies on install. |
| A5 | Default Postgres password `xpredict` in the example compose file is acceptable for dev-only (no real secret) | Pattern 1 docker-compose | LOW — D-32 mandates `.env.local` is gitignored and `.env.example` uses placeholders. Real local dev uses random-generated dev password. |

**If this table feels short:** It is. Phase 1 has minimal assumed knowledge — every version pin, every pattern is sourced from CONTEXT.md (locked by Pol) or STACK.md (Pol's own research). The 47 decisions D-01..D-47 are pre-locked locked, so the planner's freedom is intentionally tiny.

## Open Questions

1. **Should `get_redis()` ship as a real FastAPI dependency in Phase 1, or as a stub?**
   - What we know: `01-CONTEXT.md §code_context` lists `get_redis` as a Phase 1 deliverable that Phase 2+ depends on. Phase 1 has no Redis use case itself.
   - What's unclear: ship the full async `redis.asyncio` client wired into `/readyz`, or ship a stub that Phase 2's planner expands.
   - Recommendation: **Ship the real `get_redis()`** — it's ~10 LOC, wires the `Redis.from_url(settings.REDIS_URL)` client, and gets the `/readyz` PING check for free (D-30 mandates it).

2. **Should the docker-compose `frontend` service really build a full Dockerfile, or can Phase 1 ship the frontend as a host-side `pnpm dev` process?**
   - What we know: D-02 lists `frontend` as one of the 8 compose services. PLT-10 says "with one command".
   - What's unclear: a Dockerfile for the frontend in Phase 1 (when it's just hello-world) is overhead; many teams skip it until production prep.
   - Recommendation: **Ship the Dockerfile in Phase 1** to honor PLT-10 literally ("one command brings up the full stack"). The Dockerfile is ~10 lines (Node 20 base, `pnpm install`, `pnpm dev`).

3. **Sentry test endpoints — should they live behind any guard in dev?**
   - What we know: D-29 says "Phase 1 ships them naked because no real users exist yet" — Phase 11 may gate them.
   - What's unclear: even in dev, a stray HTTP probe to `/_sentry-test` will create noise in Sentry.
   - Recommendation: keep them unguarded in Phase 1 per D-29; the cost is ~3 Sentry events during testing and the 5k/mo free tier absorbs it.

4. **Should the money-column lint also walk Alembic migrations?**
   - What we know: D-17 specifies "`backend/app/**/models.py` and any `*models*.py`".
   - What's unclear: Alembic migrations literally write `sa.Column(...)` calls with `sa.Numeric(...)` — the same risk applies.
   - Recommendation: **Yes, extend the lint to walk `backend/alembic/versions/*.py`** for `op.add_column` / `op.create_table` calls with money-suggesting names. This is a small follow-up; planner can decide whether to include it in Phase 1 or defer.

5. **Phase 2 has 8 PLAN.md files on `gsd/phase-02-demo-identity` branch (per STATE.md blockers) — should Phase 1 explicitly cross-check those?**
   - What we know: STATE.md says Phase 2 is already planned and depends on Phase 1 contracts (AuditService API, Settings keys, structlog scrubber, get_redis dep, get_async_session dep).
   - What's unclear: Phase 1's plan must expose those contracts. The `code_context` block of CONTEXT.md already lists them; the planner should treat them as mandatory deliverables.
   - Recommendation: **planner cross-references Phase 2's expected contract list against the produced code** during plan-check. Don't reverse-engineer Phase 2's plan; just verify the contracts Phase 1 ships match the list in `01-CONTEXT.md §code_context`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Docker Desktop / Docker Engine | docker-compose stack (PLT-10) | ✓ (per CLAUDE.md prerequisites; assumed) | TBD by Pol's machine | — — without Docker, Phase 1 cannot ship |
| Docker Compose v2 | Same | ✓ (bundled with Docker Desktop 20.10+) | v2 | — |
| Python 3.12 | Backend + Alembic | ✓ (assumed per CLAUDE.md) | 3.12.x | — |
| uv | Python deps (D-08) | TBD — Pol/Cuco may need `pipx install uv` if absent | — | `pip install -e .` (D-08 explicitly offers this fallback) |
| Node 20+ | Frontend (D-13) | ✓ (per CLAUDE.md prerequisites) | 20.x | — |
| pnpm | Frontend deps (D-11) | TBD — may need `npm install -g pnpm` if absent | — | `npm install` (works but slower / different lockfile shape) |
| Git | Always | ✓ | — | — |
| gitleaks binary (for local pre-commit) | Pre-commit (D-35) | TBD — the pre-commit hook auto-downloads via the `gitleaks-action` Docker image in CI; locally, devs install via `brew install gitleaks` / scoop / chocolatey | — | If absent locally, pre-commit hook fails until installed. CI catches what local missed. |
| psql / redis-cli (host) | Optional, for `bin/dev db.shell` (D-47) | TBD | — | `docker compose exec db psql -U xpredict` always works (containerized). |
| Sentry account + DSN | PLT-08 acceptance | Required for end-to-end Sentry verification; without it, the synthetic-error tests can't be observed | — | `SENTRY_DSN=""` disables init (D-09); tests still pass locally but PLT-08 acceptance can't be checked end-to-end |
| GitHub repo + Actions runners | CI workflows (D-36) | ✓ (per CLAUDE.md `.mcp.json` GitHub MCP config) | — | — |

**Missing dependencies with no fallback:** Docker. Without it, the entire phase is blocked. README must list it as the first prerequisite.

**Missing dependencies with fallback:** uv (→ pip), pnpm (→ npm), Sentry DSN (→ tests pass locally but PLT-08 needs a DSN to fully verify).

## Validation Architecture

> Required because `workflow.nyquist_validation: true` in `.planning/config.json` (verified — no `false` override).

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 8.x + pytest-asyncio 0.24+ (`asyncio_mode = "auto"`) |
| Backend test runner | `uv run pytest tests/ -x` |
| Backend integration runner | `uv run pytest tests/ -x -m integration` (uses testcontainers Postgres) |
| Frontend framework | Vitest 2.x + @testing-library/react 16+ |
| Frontend test runner | `pnpm test` |
| Config file (backend) | `backend/pyproject.toml` `[tool.pytest.ini_options]` — Phase 1 creates |
| Config file (frontend) | `frontend/vitest.config.ts` — Phase 1 creates |
| Quick run command (backend, < 30s) | `uv run pytest tests/test_health.py tests/test_money_lint.py -x` (unit-only) |
| Quick run command (frontend) | `pnpm test --run` |
| Full suite command (backend) | `uv run pytest tests/ -x` (includes testcontainers Postgres ~30-60s spin-up) |
| Full suite command (frontend) | `pnpm test --run && pnpm build` |
| docker-compose smoke | `docker compose up -d --wait && curl -fsS localhost:8000/healthz && curl -fsS localhost:3000/api/healthz` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test type | Automated command | File exists? |
|--------|----------|-----------|-------------------|-------------|
| PLT-01 | `audit_log` + `feature_flags` carry `tenant_id UUID` nullable with constant default | integration (testcontainers) | `pytest tests/core/test_audit_immutability.py::test_tenant_id_default -x` | ❌ Wave 0 |
| PLT-02 | `audit_log` UPDATE/DELETE blocked by trigger + REVOKE | integration | `pytest tests/core/test_audit_immutability.py -x` | ❌ Wave 0 |
| PLT-02 | `AuditService.record()` writes a row atomically in caller's tx | integration | `pytest tests/core/test_audit_immutability.py::test_audit_service_record -x` | ❌ Wave 0 |
| PLT-03 | `Settings(BaseSettings)` reads env vars; rejects malformed `DATABASE_URL` | unit | `pytest tests/test_settings.py -x` | ❌ Wave 0 |
| PLT-04 | gitleaks blocks a known-secret pattern | CI integration | `gitleaks detect --config=.gitleaks.toml --source tests/fixtures/synthetic_secrets/` returns non-zero | ❌ Wave 0 (synthetic secret fixture file) |
| PLT-04 | GitHub Actions `security.yml` fails on a PR containing a fake secret | CI integration (manual) | Push to throwaway branch with fake secret; verify CI red | manual gate |
| PLT-06 | `FeatureFlagService.is_enabled` returns seeded values; tenant-fallback works | integration | `pytest tests/core/test_feature_flags.py -x` | ❌ Wave 0 |
| PLT-06 | Seed flags `stripe_recharge_enabled`, `polymarket_sync_enabled`, `admin_2fa_required` all `false` after migration | integration | `pytest tests/core/test_feature_flags.py::test_seed_flags -x` | ❌ Wave 0 |
| PLT-08 | Sentry SDK initialised for FastAPI (mocked DSN; init called once) | unit | `pytest tests/test_sentry_init.py -x` | ❌ Wave 0 |
| PLT-08 | Synthetic error from `/_sentry-test` raises and propagates | integration | `pytest tests/test_sentry_test_endpoint.py -x` (verifies the route raises; doesn't check Sentry round-trip) | ❌ Wave 0 |
| PLT-08 | Synthetic error from `sentry_test_task` raises | integration | `pytest tests/test_sentry_test_task.py -x` | ❌ Wave 0 |
| PLT-08 | Synthetic error from Next.js `/api/sentry-test` returns 500 | frontend integration | `pnpm test src/app/api/sentry-test/route.test.ts` | ❌ Wave 0 |
| PLT-08 | End-to-end Sentry round-trip (DSN configured) | manual gate | docker compose up + trigger 3 endpoints + verify Sentry dashboard shows 3 events tagged `service=api`, `service=worker`, `service=frontend` | manual-only |
| PLT-10 | `docker compose up -d --wait` succeeds; all services `healthy` | integration | `docker compose up -d --wait && docker compose ps --format json | jq '.[].Health' | grep -c healthy` returns 8 | ❌ Wave 0 |
| PLT-10 | `/healthz` and `/readyz` return 200; frontend `/api/healthz` returns 200 | integration | `pytest tests/test_health.py -x` + curl checks in CI smoke | ❌ Wave 0 |
| WAL-05 | Money-column lint passes on conformant code | unit | `pytest tests/test_money_lint.py::test_pass_case -x` | ❌ Wave 0 |
| WAL-05 | Money-column lint fails on `Float` for `balance` | unit | `pytest tests/test_money_lint.py::test_float_for_money_name_fails -x` | ❌ Wave 0 |
| WAL-05 | Money-column lint fails on `Numeric(10, 2)` (wrong precision/scale) | unit | `pytest tests/test_money_lint.py::test_wrong_numeric_args_fails -x` | ❌ Wave 0 |
| WAL-05 | Money-column lint warns on `Numeric(18,4)` for non-money-named column | unit | `pytest tests/test_money_lint.py::test_unknown_column_warns -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit (Nyquist quick):** `uv run pytest tests/test_money_lint.py tests/test_settings.py -x` + `pnpm test --run` — < 30s, catches lint regressions and config drift immediately.
- **Per wave merge (Nyquist standard):** `uv run pytest tests/ -x` (full backend with testcontainers ~60s) + `pnpm test --run && pnpm build` + `docker compose up -d --wait` smoke (~90s).
- **Phase gate (before `/gsd:verify-work`):** Full suite green + docker-compose stack up + 3 Sentry test triggers fired + 3 events confirmed in Sentry dashboard (manual eyeball OR Sentry CLI verification).

### Wave 0 Gaps

The planner SHOULD include the following in Wave 0 (test infrastructure):

- [ ] `tests/conftest.py` — testcontainers Postgres session-scoped fixture; `async_session` function-scoped fixture; fakeredis fixture
- [ ] `tests/test_health.py` — covers PLT-10 (health endpoints)
- [ ] `tests/test_settings.py` — covers PLT-03 (Settings env loading + validation)
- [ ] `tests/core/test_audit_immutability.py` — covers PLT-01, PLT-02
- [ ] `tests/core/test_feature_flags.py` — covers PLT-06
- [ ] `tests/test_money_lint.py` — covers WAL-05 (the lint itself; 4 positive/negative cases)
- [ ] `tests/test_sentry_init.py` — covers PLT-08 (init mocking)
- [ ] `tests/test_sentry_test_endpoint.py`, `tests/test_sentry_test_task.py` — synthetic-error tests
- [ ] `tests/fixtures/synthetic_secrets/.env.fake` — for gitleaks negative test (PLT-04)
- [ ] `frontend/src/app/api/sentry-test/route.test.ts` — covers PLT-08 frontend
- [ ] `frontend/src/app/api/healthz/route.test.ts` — covers PLT-10 frontend
- [ ] `frontend/vitest.config.ts` — Vitest config
- [ ] `backend/pyproject.toml` `[tool.pytest.ini_options]` block — `asyncio_mode = "auto"`, `testpaths = ["tests"]`, markers for `integration`
- [ ] Framework install: covered by Phase 1 `uv add --dev` block above.

*(No existing test infrastructure to reuse — Phase 1 is greenfield. Wave 0 ships everything.)*

## Security Domain

> Phase 1 has `security_enforcement` enabled (no explicit `false` in config). Phase 1 ships scaffolding only — there are no auth endpoints, no money flows, no external integrations. Security applicability is therefore narrow.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Modular monolith (ARCHITECTURE.md §1); module boundaries enforced by code review |
| V2 Authentication | no | Phase 2 owns AUTH-* |
| V3 Session Management | no | Phase 2 |
| V4 Access Control | no | Phase 2 (admin flag) + Phase 8 (CRM endpoints) |
| V5 Input Validation | partial | Pydantic models in `/healthz` / `/readyz` are trivial; full input validation surface comes with Phase 2+ endpoints |
| V6 Cryptography | partial | Argon2 / JWT signing happens in Phase 2; Phase 1 only ships `SENTRY_DSN` and connection-string secrets via BaseSettings |
| V7 Error handling | yes | Sentry init + structlog scrubber (D-25) prevents PII/secret leak in logs |
| V8 Data Protection | yes | `.env.local` gitignored, `.env.example` is placeholder-only (D-32) |
| V9 Communication | partial | docker-compose internal traffic is plaintext; staging/prod uses HTTPS (Railway/Fly.io terminates TLS) — out of Phase 1 |
| V10 Malicious Code | yes | gitleaks blocks secret commits (PLT-04); slopcheck verified package legitimacy (this research file) |
| V11 Business Logic | n/a | No business logic in Phase 1 |
| V12 Files and Resources | n/a | No file uploads or resource handling |
| V13 API and Web Service | partial | Health endpoints are public; no auth surface yet |
| V14 Configuration | yes | Pydantic BaseSettings (PLT-03), environment-aware `is_dev` / `is_prod` (D-10) |

### Known Threat Patterns for {Python + FastAPI + Postgres + Celery + Next.js} stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secrets committed to repo | Information Disclosure | gitleaks pre-commit + CI block (D-33-D-34); `.env.local` gitignored (D-32) |
| Float-based money columns | Tampering / Repudiation | NUMERIC(18,4) + Decimal-from-strings; AST lint (D-17); pre-commit + CI gate |
| Audit log mutability | Tampering / Repudiation | Postgres trigger + REVOKE (D-20); integration test confirms |
| PII in logs / Sentry events | Information Disclosure | structlog `scrub_secrets` processor (D-25); `send_default_pii=False` on Sentry init (Pattern 5a) |
| Connection-pool contamination across tenants | Information Disclosure / Tampering | `SET LOCAL` doctrine (D-41); no v1 multi-tenant runtime, so risk is dormant but pattern locked |
| Dependency supply-chain (typosquat) | Tampering | slopcheck (this file); pin exact versions in `pyproject.toml`; `uv.lock` for reproducible installs; Dependabot/Renovate (deferred to Phase 11 hardening) |
| Health endpoint info leak | Information Disclosure | `/healthz` returns only `{"status":"ok"}`; `/readyz` returns failure details only on 503 — never leaks DB connection strings or version info |
| docker-compose default credentials in repo | Information Disclosure | `.env.example` has placeholder values only; the real `.env.local` is per-developer and never committed |

**Phase 1 ships zero attack surface for the most worrying threats (no auth, no money writes, no external API).** The discipline it installs (secrets, audit, money-types) is what makes Phases 2-10 defendable.

## Sources

### Primary (HIGH confidence)

- `.planning/phases/01-scaffold-foundations/01-CONTEXT.md` — 47 decisions D-01..D-47 locked by Pol on 2026-05-26
- `.planning/research/STACK.md` (2026-05-25, HIGH confidence) — version pins, alternatives considered, "What NOT to Use" table
- `.planning/research/PITFALLS.md` (2026-05-25, HIGH confidence) — #3 (regulatory/secrets), #4 (Decimal/NUMERIC), #7 (SET LOCAL doctrine)
- `.planning/research/ARCHITECTURE.md` (2026-05-25, HIGH confidence) — modular monolith layout, MarketSource abstraction
- `.planning/PROJECT.md` — core value, constraints (single-tenant v1, mono-repo, stack lock)
- `.planning/REQUIREMENTS.md` — PLT-01..04, PLT-06, PLT-08, PLT-10, WAL-05 exact text
- `.planning/STATE.md` — current position, Phase 2 dependency notes
- [Sentry Next.js manual setup](https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/) — Pattern 5c (`instrumentation.ts` + `instrumentation-client.ts`)
- [Sentry FastAPI integration](https://docs.sentry.io/platforms/python/integrations/fastapi/) — Pattern 5a
- [Sentry Celery integration](https://docs.sentry.io/platforms/python/integrations/celery/) — Pattern 5b
- [Alembic Cookbook — async](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic) — Pattern 2
- [SQLAlchemy 2.0 Type Basics](https://docs.sqlalchemy.org/en/20/core/type_basics.html) — Numeric/Decimal mapping
- [structlog Context Variables](https://www.structlog.org/en/latest/contextvars.html) — Pattern 6
- [gitleaks repository](https://github.com/gitleaks/gitleaks) — Pattern 7

### Secondary (MEDIUM confidence — verified against official docs)

- [Celery beat heartbeat healthcheck (Nautobot PR #5434)](https://github.com/nautobot/nautobot/pull/5434) — Pattern 1 beat healthcheck
- [Celery School — Docker Healthcheck for Celery Workers](https://celery.school/posts/docker-healthcheck-for-celery-workers/) — Pattern 1
- [Berk Karaal — FastAPI + Async SQLAlchemy 2 + Alembic + Postgres + Docker](https://berkkaraal.com/blog/2024/09/19/setup-fastapi-project-with-async-sqlalchemy-2-alembic-postgresql-and-docker/) — Pattern 2
- [Brandon Wie — Alembic with Async SQLAlchemy](https://www.brandonwie.dev/posts/alembic-async-sqlalchemy) — Pattern 2
- [Modern Treasury — Enforcing Immutability in your Double-Entry Ledger](https://www.moderntreasury.com/journal/enforcing-immutability-in-your-double-entry-ledger) — Pattern 3
- [d4b — Local Gitleaks Pre-Commit Hook](https://www.d4b.dev/blog/2026-02-01-gitleaks-pre-commit-hook/) — Pattern 7
- [nymous gist — Logging setup for FastAPI, Uvicorn and Structlog](https://gist.github.com/nymous/f138c7f06062b7c43c060bf03759c29e) — Pattern 6
- [Apitally — FastAPI logging guide](https://apitally.io/blog/fastapi-logging-guide) — Pattern 6
- [FastAPI Discussion #8632](https://github.com/fastapi/fastapi/discussions/8632) — BaseHTTPMiddleware contextvars caveat
- [Mailpit repo](https://github.com/axllent/mailpit) — service config
- [celery-redbeat repo](https://github.com/sibson/redbeat) — beat scheduler API
- [Testcontainers Python](https://testcontainers-python.readthedocs.io/en/latest/database/postgres/) — testing fixtures
- [uv concepts/projects](https://docs.astral.sh/uv/concepts/projects/) — uv pyproject + lockfile
- [Postgres Docker official image](https://www.docker.com/blog/how-to-use-the-postgres-docker-official-image/) — Pattern 1 health check

### Tertiary (LOW confidence — single source or training data)

- A1, A2, A3, A5 — see Assumptions Log; planner re-verifies at execution time.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version traced to STACK.md (2026-05-25 with Context7 verification) AND passed slopcheck 2026-05-26.
- Architecture patterns: HIGH — every pattern locked in CONTEXT.md D-01..D-47 and cross-verified against ARCHITECTURE.md.
- Pitfalls: HIGH — sourced from PITFALLS.md (2026-05-25) which Pol authored.
- Validation Architecture: HIGH — test map is direct from PLT-01..10 + WAL-05 → CONTEXT.md decision tracebility.
- Code examples (Patterns 1-8): HIGH for shape, MEDIUM for exact syntax — planner verifies against current Sentry SDK / Alembic / structlog docs at execution time.

**Research date:** 2026-05-26
**Valid until:** ~2026-06-25 (30 days — stable stack, no fast-moving deps). Re-verify Sentry SDK + Next.js version pins if execution slips past 30 days.
