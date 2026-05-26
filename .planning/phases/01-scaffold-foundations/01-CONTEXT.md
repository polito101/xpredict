# Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations - Context

**Gathered:** 2026-05-26
**Status:** Ready for planning
**Mode:** `--auto` (decisions taken by Claude — recommended options from STACK.md / PITFALLS.md / ARCHITECTURE.md)

<domain>
## Phase Boundary

**One-command local stack + the non-negotiable cross-cutting foundations every later phase inherits for free.** Phase 1 ships zero product features. It ships the scaffolding (Docker compose, FastAPI app skeleton, Next.js hello-world, Postgres 16, Redis 7, Alembic baseline, structlog, Sentry, gitleaks) and the foundations that, if not locked here, cause irreversible damage later (money-column types, `tenant_id` ghost column pattern, audit-log immutability, secrets discipline).

Delivers PLT-01, PLT-02, PLT-03, PLT-04, PLT-06, PLT-08, PLT-10, WAL-05:

- `docker-compose up` brings the full stack (api, worker, beat, db, redis, frontend, mailpit, flower) online with a single command; healthchecks pass for every service (PLT-10)
- Alembic baseline migration `0001_phase1_foundations` exists; tables it creates (`audit_log`, `feature_flags`) include the `tenant_id UUID` nullable ghost column with a fixed default constant (PLT-01)
- `audit_log` table has a Postgres trigger blocking `UPDATE` and `DELETE`; defense in depth via `REVOKE UPDATE,DELETE ON audit_log FROM PUBLIC` (PLT-02)
- A CI lint script fails any new SQLAlchemy `Mapped[]` declaration that violates the money-column standard (`Decimal` + `Numeric(18,4)`); no `Float`/`REAL`/`MONEY` types in the schema (WAL-05)
- All secrets read via Pydantic `BaseSettings` from environment; `.env.example` differs from `.env.local`; `.env.local` gitignored; `gitleaks` runs in CI and blocks a fake-secret test commit (PLT-03, PLT-04)
- Sentry SDK initialized in FastAPI + Celery worker + Celery beat + Next.js; a synthetic error from each surface produces a Sentry event with correct tags (PLT-08)
- `feature_flags` table with minimal v1 shape; `FeatureFlagService.is_enabled(key, tenant_id=None)` works against seeded rows (PLT-06)

**Out of this phase entirely:**
- `users` table → Phase 2 (Demo Identity) — Phase 1 does NOT create it; Phase 2 migration adds it with `tenant_id` per PLT-01 pattern documented here
- `accounts`/`transfers`/`entries` (ledger) → Phase 3 — Phase 1 enforces the money-column standard but does not author any money-bearing table
- `markets`/`outcomes`/`bets` → Phases 4-5
- Real Sentry alert rule tuning (settlement failure thresholds, reconciliation drift) → bound to the features that emit them — Phase 1 only confirms events flow
- Rate limiting (`slowapi`) → Phases that own the limited endpoints (`/auth/*` is deferred to v2 AUTH-FULL; bet placement is Phase 5). Phase 1 may install `slowapi` as a dep but does NOT mount it.
- Mobile responsiveness validation → Phase 11
- Backup / restore tested procedure → bound to deploy work, not Phase 1 (acknowledged as a Phase 11 hardening checklist item in PITFALLS.md "Looks Done But Isn't")

</domain>

<decisions>
## Implementation Decisions

### Repo & service composition (docker-compose)

- **D-01: Repo layout = monorepo `backend/` + `frontend/` under `xpredict/` root.** Already locked by PROJECT.md §Constraints. Phase 1 creates `backend/` and `frontend/` as siblings; root holds `docker-compose.yml`, `.env.local`, `.env.example`, `.gitleaks.toml`, `.pre-commit-config.yaml`, `pyproject.toml` (optional root for shared scripts), and `README.md`.
- **D-02: docker-compose services and ports** (locked):
  - `db` — `postgres:16-alpine` → 5432 (host) → 5432 (container)
  - `redis` — `redis:7-alpine` → 6379 → 6379
  - `mailpit` — `axllent/mailpit:latest` → SMTP 1025, web UI 8025
  - `backend` (api) — build `./backend`, command `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` → 8000 → 8000
  - `worker` — same image as backend, command `celery -A app.celery_app worker -l info -Q default`
  - `beat` — same image, command `celery -A app.celery_app beat -S redbeat.RedBeatScheduler -l info`
  - `flower` — same image, command `celery -A app.celery_app flower --port=5555` → 5555 → 5555
  - `frontend` — build `./frontend`, command `pnpm dev` → 3000 → 3000
- **D-03: Healthcheck strategy (docker-compose `healthcheck:` block per service):**
  - `db`: `pg_isready -U xpredict -d xpredict` every 5s, retries 5
  - `redis`: `redis-cli ping` every 5s, retries 5
  - `backend`: `curl -fsS http://localhost:8000/healthz` every 10s, retries 5
  - `worker`: `celery -A app.celery_app inspect ping -d celery@$$HOSTNAME` every 30s, retries 5
  - `beat`: filesystem heartbeat — beat writes `/tmp/celerybeat.heartbeat` every tick; healthcheck checks mtime < 60s old (redbeat doesn't expose a port)
  - `flower`: `curl -fsS http://localhost:5555/api/workers` every 30s
  - `frontend`: `curl -fsS http://localhost:3000/api/healthz` every 10s
  - `mailpit`: `curl -fsS http://localhost:8025` (web UI) every 30s
- **D-04: Service dependencies (compose `depends_on` with `condition: service_healthy`):** `backend` → `db` + `redis`; `worker` → `db` + `redis`; `beat` → `db` + `redis`; `flower` → `redis`; `frontend` → `backend` (soft — frontend can hot-reload while backend restarts).
- **D-05: Named volumes for stateful services** — `pg_data` for Postgres, `redis_data` for Redis (AOF persistence enabled), `mailpit_data`. No bind mounts for DB (slow on Windows/macOS). Code is bind-mounted for hot-reload.
- **D-06: docker-compose is dev-only.** Staging/prod deploys via Railway/Fly.io using the same Dockerfiles (per STACK.md §7). docker-compose is not a deployment tool — keeps Phase 1 scope tight.

### Backend project layout (modular monolith)

- **D-07: Module structure inside `backend/app/`** — feature folders + shared infrastructure (per ARCHITECTURE.md §1):
  ```
  backend/app/
    main.py                  # FastAPI app factory + middleware wiring
    celery_app.py            # Celery app factory + beat schedule
    core/                    # cross-cutting (settings, logging, audit, feature flags, healthchecks)
      config.py              # Settings(BaseSettings)
      logging.py             # structlog config
      audit/
        service.py           # AuditService.record(...)
        models.py            # AuditLog SQLAlchemy model
      feature_flags/
        service.py           # FeatureFlagService.is_enabled(key, tenant_id=None)
        models.py            # FeatureFlag SQLAlchemy model
      health.py              # /healthz, /readyz handlers
      sentry.py              # Sentry init helpers
    db/
      base.py                # DeclarativeBase, engine, sessionmaker
      session.py             # get_async_session dependency
      types.py               # Money = Annotated[Decimal, mapped_column(Numeric(18,4))] alias
    integrations/            # external adapters (Phase 6+ — placeholder dir in Phase 1)
    auth/                    # Phase 2 lives here
    wallet/                  # Phase 3 lives here
    markets/                 # Phase 4 lives here
    bets/                    # Phase 5 lives here
    admin/                   # Phase 8 lives here
    routers/                 # FastAPI APIRouters mounted in main.py
      health.py              # mounts /healthz, /readyz
  alembic/
    versions/0001_phase1_foundations.py
    env.py
    script.py.mako
  scripts/
    lint_money_columns.py    # AST-based money-column enforcer
  tests/
    conftest.py              # pytest fixtures (testcontainers Postgres, fakeredis)
    core/
      test_audit_immutability.py
      test_feature_flags.py
    test_health.py
    test_money_lint.py
  ```
  Phase 1 creates `core/`, `db/`, `routers/health.py`, and the placeholder directories `integrations/`, `auth/`, `wallet/`, `markets/`, `bets/`, `admin/` (each with a `__init__.py` and a `# Phase N owns this` comment).
- **D-08: Dependency management = `pyproject.toml` + `uv` (lockfile `uv.lock`).** `uv` is the modern fast installer that has clearly won the ecosystem in 2026 (10-100x faster than pip, single tool replaces pip+venv+pip-tools+pyenv). Generates lockfile that's reproducible and CI-cacheable. Falls back gracefully to `pip install -e .` for users who don't have uv. Dependencies are version-pinned exactly per STACK.md §1.1-1.7.
- **D-09: Single `Settings` class in `app/core/config.py`** extending `BaseSettings`, all env vars typed and documented inline. No nested submodels in Phase 1 (start simple). `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`. Phase 1 settings:
  ```python
  ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
  DATABASE_URL: PostgresDsn
  DATABASE_URL_SYNC: PostgresDsn          # for Alembic (psycopg2)
  REDIS_URL: RedisDsn
  SENTRY_DSN: str | None = None           # None disables Sentry init
  SENTRY_TRACES_SAMPLE_RATE: float = 0.1
  LOG_LEVEL: Literal["DEBUG","INFO","WARNING","ERROR"] = "INFO"
  TENANT_ID_DEFAULT: UUID = UUID("00000000-0000-0000-0000-000000000001")  # v1 fixed default
  ```
  Phase 2+ adds `SESSION_SIGNING_KEY`, `ADMIN_TOKEN`, etc.; planner just appends.
- **D-10: `is_dev` / `is_prod` properties** on Settings (`@property def is_dev(self) -> bool: return self.ENVIRONMENT == "dev"`) — used by structlog renderer choice (D-19), Sentry init (skip in dev unless DSN explicitly set), cookie `secure` flag (Phase 2 reads this).

### Frontend project layout

- **D-11: Package manager = `pnpm`.** Faster than npm, correct hoisting (avoids "phantom dependencies" bugs), good lockfile. Already the de-facto standard for Next.js projects in 2026. `package.json` + `pnpm-lock.yaml`.
- **D-12: No monorepo tooling (no Turbo/Nx).** Backend and frontend are deployed independently and don't share TypeScript code. Adding Turbo for two unrelated subprojects is overhead with no payoff. Each subproject builds standalone via its own Dockerfile.
- **D-13: Frontend tech versions (per STACK.md §3):** Next.js 15 (App Router), React 19, TypeScript 5.5+, Tailwind 4, shadcn/ui (CLI-installed components), `npm-run-all` not needed. Phase 1 scaffolds `pnpm create next-app@latest` output, configures Tailwind, installs `@sentry/nextjs`, and adds one `/api/healthz` route handler.
- **D-14: Frontend Sentry init** uses `@sentry/nextjs` with `instrumentation-client.ts` + `instrumentation.ts` (Next.js 15 pattern). DSN from `NEXT_PUBLIC_SENTRY_DSN` (must be `NEXT_PUBLIC_*` so it's available client-side). Synthetic trigger: `/api/sentry-test` route that throws.

### Database & migrations

- **D-15: Alembic baseline `0001_phase1_foundations`** creates only the tables Phase 1 owns: `audit_log`, `feature_flags`. Both include the `tenant_id UUID NULL DEFAULT '00000000-0000-0000-0000-000000000001'` ghost column per PLT-01. Subsequent migrations (Phase 2+) add their tables and MUST include the ghost column on player/market tables — enforced by code review + planner discipline (no automated check in v1; documented in `backend/CONVENTIONS.md`).
- **D-16: Alembic configured with sync engine (psycopg2-binary)** even though app runs asyncpg. Standard Alembic pattern. `env.py` reads `DATABASE_URL_SYNC` from Settings.
- **D-17: Money-column lint** = custom Python script `scripts/lint_money_columns.py` that:
  1. AST-walks `backend/app/**/models.py` and any `*models*.py`
  2. Finds every `mapped_column(...)` call
  3. If the type is `Numeric`, asserts precision=18, scale=4
  4. If the column name matches a money-suggesting pattern (`amount`, `balance`, `price`, `stake`, `payout`, `fee`, `volume`, `liquidity`, `credit`, `debit`, `cost`, `value`) AND the type is `Float`/`Real`/`Integer` (or anything other than the Money alias) → fail with line+file
  5. If `Numeric(18,4)` is used on a field NOT in the money-suggesting list → warn (not fail) — catches typos
  Script runs in pre-commit and in CI via `uv run python scripts/lint_money_columns.py`. Exit code non-zero fails CI. **Rationale**: a ruff custom rule would be cleaner but requires writing a ruff plugin in Rust or maintaining a regex-based linter; an AST script is ~80 lines, testable, and lives in the repo. Phase 1 ships the lint with unit tests in `tests/test_money_lint.py` covering: pass case, missing-precision fail, wrong-type fail, unknown-column warn.
- **D-18: SQLAlchemy `Money` type alias** in `app/db/types.py`:
  ```python
  from decimal import Decimal
  from typing import Annotated
  from sqlalchemy.orm import mapped_column
  from sqlalchemy import Numeric

  Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]
  ```
  All money columns use `amount: Mapped[Money]` syntax. Audit-log payload column is JSONB (not Money) — money values inside JSONB payloads are serialized as strings.

### Audit log architecture

- **D-19: `audit_log` table schema** (Phase 1 creates):
  ```sql
  CREATE TABLE audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor        TEXT NOT NULL,        -- "user:<uuid>" | "admin" | "system" | "celery:<task_name>"
    event_type   TEXT NOT NULL,        -- e.g. "auth.guest_created", "wallet.transfer", "market.resolved"
    payload      JSONB NOT NULL,       -- arbitrary structured data
    ip           INET NULL,            -- caller IP if available (NULL for system/celery)
    tenant_id    UUID NULL DEFAULT '00000000-0000-0000-0000-000000000001'
  );
  CREATE INDEX ix_audit_log_occurred_at ON audit_log (occurred_at DESC);
  CREATE INDEX ix_audit_log_event_type  ON audit_log (event_type);
  CREATE INDEX ix_audit_log_actor       ON audit_log (actor);
  ```
- **D-20: Immutability — defense in depth (two mechanisms):**
  1. Postgres trigger `audit_log_immutability_trigger BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION raise_audit_immutable()` — function raises `EXCEPTION 'audit_log is append-only'`. Works even for superuser/owner.
  2. `REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC` — second layer; only the migration runner ever needs these grants (and even it should fail because of the trigger).
  Integration test (`tests/core/test_audit_immutability.py`) inserts a row, then asserts both `UPDATE` and `DELETE` raise `IntegrityError` / `DataError` from the trigger.
- **D-21: `AuditService.record(...)` API** in `app/core/audit/service.py`:
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
  Caller passes its own `AsyncSession` (the audit insert happens in the caller's transaction — audit and the underlying action commit atomically together). No async event bus, no background queue. Trade-off: synchronous insert adds ~1ms to every audited action; acceptable in exchange for the atomicity guarantee. Phases 2-10 all use this single API.
- **D-22: `tenant_id` populated automatically.** If caller doesn't pass `tenant_id`, `AuditService` reads `Settings.TENANT_ID_DEFAULT`. Forward-compat: in v2 multi-tenant, replaces this with `current_tenant_var.get()` (contextvar set by tenant middleware). The API doesn't change.

### Observability — logging & error tracking

- **D-23: structlog** as the logging library, NOT loguru (per STACK.md §1.6 — loguru fights stdlib + FastAPI internals and has no first-party OpenTelemetry interop).
- **D-24: structlog renderer** = `ConsoleRenderer(colors=True)` when `Settings.is_dev`; `JSONRenderer()` otherwise. Configured once in `app/core/logging.py`, called from FastAPI lifespan and Celery `worker_init` signal.
- **D-25: structlog processors (in order):** `add_log_level`, `TimeStamper(fmt="iso", utc=True)`, `StackInfoRenderer`, `format_exc_info`, custom `scrub_secrets` (drops keys named `password`, `password_hash`, `session_signing_key`, `admin_token`, `sentry_dsn`, `api_key`, `secret`, `xp_session` — Phase 2's auth keys are already listed proactively here), renderer.
- **D-26: Standard log binding pattern** — FastAPI middleware binds `request_id` (UUID per request), `path`, `method`, `client_ip` (if present) to a contextvar so every log line inside the request automatically carries them. Celery task body binds `task_id`, `task_name`.
- **D-27: Sentry — single project per environment with tags.** `xpredict-dev`, `xpredict-staging`, `xpredict-prod` Sentry projects. NOT a separate project per service. Every event tagged `service=api|worker|beat|frontend`. Free tier (5k events/month) is enough for the demo. `release` tag = `XPREDICT_VERSION` env var (set by deploy pipeline; defaults to `dev-{git-sha}` locally).
- **D-28: Sentry init points:**
  - FastAPI: `sentry_sdk.init(dsn, integrations=[FastApiIntegration(), SqlalchemyIntegration()])` in `app/main.py` startup
  - Celery worker + beat: `sentry_sdk.init(dsn, integrations=[CeleryIntegration(), SqlalchemyIntegration()])` in Celery `worker_process_init` signal
  - Next.js: `@sentry/nextjs` with `instrumentation.ts` + `instrumentation-client.ts`
- **D-29: Sentry triple-trigger test endpoints (Phase 1 ships these temporarily; Phase 11 may remove or gate them):**
  - `GET /_sentry-test` on FastAPI → raises `RuntimeError("sentry test from api")`
  - Celery task `app.core.sentry.sentry_test_task` → raises inside the worker; triggered manually via `flower` UI or `celery -A app.celery_app call app.core.sentry.sentry_test_task`
  - `GET /api/sentry-test` on Next.js → throws in the route handler
  Each must produce a distinct Sentry event with the correct `service` tag during Phase 1 acceptance.

### Healthchecks

- **D-30: Two endpoints — `/healthz` (liveness) and `/readyz` (readiness)** on FastAPI:
  - `/healthz` returns `{"status":"ok"}` 200 — no dependency checks
  - `/readyz` checks DB (`SELECT 1`) + Redis (`PING`); returns 200 if both respond, 503 with which-failed payload otherwise. Used by docker-compose healthcheck (D-03).
  Frontend `/api/healthz` Next.js route handler returns `{"status":"ok"}` 200.
- **D-31: No metrics endpoint in Phase 1.** Prometheus scraping is a Phase 11 hardening item (PITFALLS.md "Looks Done But Isn't" mentions Postgres metrics + slow query log under deploy/infra). Phase 1 keeps Sentry as the only observability surface.

### Secrets & CI

- **D-32: `.env.example` committed, `.env.local` gitignored, no `.env` plaintext file used.** `.env.example` contains every required key with placeholder values (`DATABASE_URL=postgresql+asyncpg://xpredict:xpredict@localhost:5432/xpredict`, `SENTRY_DSN=` etc.). `.env.local` is the dev secrets file each developer creates from the example.
- **D-33: `gitleaks` config** in `.gitleaks.toml` at repo root — extends the default ruleset with custom rules for the keys Phase 1+ introduces:
  ```toml
  [[rules]]
  id = "xpredict-session-signing-key"
  regex = '''SESSION_SIGNING_KEY\s*=\s*['""]?[A-Za-z0-9+/=]{32,}'''

  [[rules]]
  id = "xpredict-admin-token"
  regex = '''ADMIN_TOKEN\s*=\s*['""]?[A-Za-z0-9_-]{16,}'''
  ```
  Plus default rules catch Sentry DSN, generic API keys, Postgres URLs with embedded passwords, etc.
- **D-34: gitleaks runs in (a) pre-commit hook, (b) CI on every PR — block (exit 1) on detect.** Phase 1 acceptance: commit a file containing `ADMIN_TOKEN=this-is-a-test-secret-1234567890abcd` → CI fails. Then revert. The synthetic-secret test commit lives in a separate branch never merged.
- **D-35: pre-commit hooks** (`.pre-commit-config.yaml`): `ruff check --fix`, `ruff format`, `mypy app/` (backend only), `gitleaks protect --staged`, `python scripts/lint_money_columns.py`, frontend `pnpm lint && pnpm typecheck`. Pre-commit is mandatory for Pol; Cuco-equivalent contributors must install before first commit (README documents).
- **D-36: CI = GitHub Actions** (already part of repo bootstrap per `.claude/` collaboration infra). Workflows:
  - `.github/workflows/backend-ci.yml`: matrix on Python 3.12, `uv sync`, ruff, mypy, money-lint, pytest with testcontainers Postgres + fakeredis, gitleaks
  - `.github/workflows/frontend-ci.yml`: Node 20, `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm typecheck`, `pnpm build`, `pnpm test` (Vitest)
  - `.github/workflows/security.yml`: gitleaks full-history scan weekly

### Feature flags table

- **D-37: `feature_flags` table schema** (Phase 1 creates):
  ```sql
  CREATE TABLE feature_flags (
    key         TEXT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    value       JSONB NULL,                    -- optional structured value (e.g., bet limits)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id   UUID NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    PRIMARY KEY (key, tenant_id)
  );
  ```
  Per-tenant composite PK allows v2 multi-tenant overrides without schema change. In v1, all rows have the default `tenant_id`.
- **D-38: `FeatureFlagService.is_enabled(key, tenant_id=None) -> bool`** in `app/core/feature_flags/service.py`. Queries the table with tenant-fallback (`WHERE key = :key AND (tenant_id = :tenant OR tenant_id = :default) ORDER BY tenant_id = :tenant DESC LIMIT 1`). In-memory LRU cache (`functools.lru_cache` is wrong for async — use `aiocache` or a 60-second dict cache invalidated on `feature_flags` write). Phase 1 ships the simplest version: query every call (no cache); add cache when something hot path needs it.
- **D-39: No admin UI for feature flags in v1.** Admin sets flags via SQL or via a one-off seed script. Phase 8 (Admin CRM) may add a UI; Phase 1 just exposes the service. Seed migration `0001` inserts these default flags:
  - `stripe_recharge_enabled` = `false` (used by Phase 3 to keep the Add-funds button disabled per PLT-05)
  - `polymarket_sync_enabled` = `false` (used by Phase 6 to gate the polling beat task)
  - `admin_2fa_required` = `false` (schema-prep for v2 AUTH-FULL-11)

### Cross-cutting

- **D-40: Audit-event naming convention** = dotted lowercase `domain.action` (e.g., `auth.guest_created`, `wallet.transfer.completed`, `market.resolved`, `cleanup.guest_purge`). Documented in `backend/CONVENTIONS.md`; planners and executors use the same prefix per phase domain.
- **D-41: Database connection pooling** — asyncpg via SQLAlchemy `create_async_engine(..., pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=3600)`. No PgBouncer in v1 (deployment concern — staging may add it; Phase 1 docker-compose runs without it). Per PITFALLS.md #7: `SET LOCAL` ONLY (no session-level state); since no multi-tenant runtime yet, no `app.tenant_id` setting is needed in v1.
- **D-42: `tenant_id` ghost-column policy (locked, documented in `backend/CONVENTIONS.md`):** Every player-owned and market table in v1 declares `tenant_id: Mapped[UUID | None] = mapped_column(default=Settings().TENANT_ID_DEFAULT)`. Code review enforces. Phase 1 does NOT add this to `audit_log` and `feature_flags` reflexively — it does (D-19, D-37) precisely to model the pattern that Phases 2+ inherit.
- **D-43: README structure** — `README.md` at root with: prerequisites (Docker, uv, pnpm, Node 20+), one-command setup (`make dev` or `./bin/dev` script wrapping `docker compose up -d && cd backend && uv run alembic upgrade head`), service URLs (frontend :3000, backend :8000, flower :5555, mailpit :8025), how to run tests, contribution checklist (pre-commit install). `README-SETUP.md` (already exists in repo from initial bootstrap) is kept as the detailed deeper reference.

### Claude's Discretion

- **D-44: Exact wording of `audit_log_immutability_trigger` error message** — planner picks; suggested: `'audit_log is append-only — UPDATE and DELETE are forbidden'`.
- **D-45: Exact `pyproject.toml` `[tool.ruff]` / `[tool.mypy]` rule sets** — planner picks sensible production defaults (ruff `E,F,I,UP,B,C4,SIM,RUF`; mypy `strict = true` on `app/`, lax on `tests/`).
- **D-46: Initial `.gitleaks.toml` extension rules beyond D-33** — planner can add more rules if Phase 1 introduces other secrets; the structure is documented.
- **D-47: Exact dev `Makefile` / `bin/dev` script entries** — planner picks; suggested top-level commands: `dev` (compose up + alembic upgrade), `down`, `test` (run backend + frontend tests), `lint`, `format`, `db.shell`, `db.reset`, `seed`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level (locked requirements)
- `.planning/PROJECT.md` — Core value, Constraints (mono-repo, Python 3.12, FastAPI, Postgres 16, Next.js 15, Tailwind, shadcn/ui), Key Decisions table (especially row "Auth self-hosted (FastAPI-users)" → deferred v2)
- `.planning/REQUIREMENTS.md` §"Platform — Cross-cutting (PLT)" — PLT-01 through PLT-10 are the v1 contract for Phase 1
- `.planning/REQUIREMENTS.md` §"Wallet & Ledger (WAL)" — WAL-05 (money-column standard) lives in Phase 1
- `.planning/ROADMAP.md` §"Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations" — success criteria (5 enumerated)
- `.planning/STATE.md` — Decisions log, especially money-column lock (2026-05-25), tenant_id ghost column lock, audit-log immutability lock

### Phase 2 reference (already planned)
- `.planning/phases/02-auth-identity/02-CONTEXT.md` — Phase 2 decisions that depend on Phase 1 outputs (Settings keys, AuditService API, structlog scrubber list, Redis client provider, async session dependency). Phase 1 plan MUST surface these contracts so Phase 2 doesn't drift.

### Research (all under `.planning/research/`)
- `STACK.md` §1 "Backend — Core (Python 3.12)" — pinned versions for FastAPI, SQLAlchemy, asyncpg, Alembic, Pydantic, pydantic-settings (D-08 sources every Phase 1 dep here)
- `STACK.md` §1.2 "Database — SQLAlchemy 2.0 async + asyncpg + Alembic" — Postgres 16 lock, money-column rationale, never-FLOAT rule
- `STACK.md` §1.4 "Background tasks — Celery 5.5 + Beat" — Celery 5.5 pin (not 5.6), `celery-redbeat` for HA scheduler, Flower for monitoring, asyncio gotcha
- `STACK.md` §1.6 "Observability — structlog (NOT loguru)" — rationale for structlog choice + Sentry SDK pins
- `STACK.md` §1.7 "Security & hardening extras" — slowapi info (not mounted in Phase 1)
- `STACK.md` §3 "Frontend" (Next.js 15, React 19, TS, Tailwind, shadcn/ui, pnpm) — D-11 through D-14 source from here
- `STACK.md` §5 "Testing stack" — testcontainers Postgres (NOT sqlite), pytest-httpx, dirty-equals; informs Phase 1 CI workflow
- `STACK.md` §6 "Dev tools & code quality" — ruff + mypy + pre-commit pins
- `STACK.md` §6.x "Docker / docker-compose sketch" — basis for D-02 service composition
- `STACK.md` §7 "Deployment — staging" — Railway > Fly.io recommendation (Phase 1 doesn't deploy but acknowledges the target)
- `ARCHITECTURE.md` §1 "Executive Recommendation" + §2 "System Overview" — modular monolith layout (D-07)
- `PITFALLS.md` "Pitfall #3 (regulatory — secrets posture)" + "Demo trap: hardcoded config" + "Demo trap: branding hardcoded" — directly applied in D-32 through D-36 (secrets discipline) and informs frontend layout (Phase 10 will revisit branding)
- `PITFALLS.md` "Pitfall #4 (Decimal/NUMERIC)" — D-17, D-18 implementation
- `PITFALLS.md` "Pitfall #7 (Connection pool contamination)" — D-41 (SET LOCAL discipline established as pattern; not actively used until v2 multi-tenant)
- `PITFALLS.md` "Pitfall #10 (single-transaction discipline)" — informs Phase 1 by laying the AsyncSession dependency pattern Phases 3+ inherit
- `SUMMARY.md` — research synthesis (read for high-level orientation if unfamiliar)
- `FEATURES.md` — domain feature inventory (low priority for Phase 1, no product features here)

### External library docs (for researcher to fetch live during plan-phase)
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- Alembic env.py async pattern: https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- `uv` lockfile + workspace: https://docs.astral.sh/uv/concepts/projects/
- Sentry FastAPI integration: https://docs.sentry.io/platforms/python/integrations/fastapi/
- Sentry Celery integration: https://docs.sentry.io/platforms/python/integrations/celery/
- Sentry Next.js 15 instrumentation: https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/
- structlog config recipes: https://www.structlog.org/en/stable/configuration.html
- gitleaks custom rules: https://github.com/gitleaks/gitleaks#configuration
- testcontainers Postgres in pytest: https://testcontainers-python.readthedocs.io/en/latest/database/postgres/
- celery-redbeat README: https://github.com/sibson/redbeat
- Mailpit Docker image: https://github.com/axllent/mailpit

### Repo siblings (allowed as inspiration, NOT for code import)
- `live-bets/` — Pol's production Python+FastAPI+Postgres+Redis+Docker repo. Planner MAY reference its `docker-compose.yml`, `pyproject.toml`, structlog config, and Alembic baseline as reasonableness checks. MUST NOT copy code — different repo, different scope. live-bets is currently `v3.0` shipped (per memory).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **None inside `xpredict/`.** Repo currently contains only docs, `.planning/`, `.claude/`, `.env.local`, `.env.example`, `.mcp.json`, `CLAUDE.md`, `README-SETUP.md`, `docs/`. Backend and frontend trees do not exist yet — Phase 1 creates them from scratch.
- **`README-SETUP.md` already exists** at root from initial bootstrap. Phase 1 SHOULD NOT delete it; instead, the new `README.md` links to it for deeper setup detail. Planner may re-read it to align dev-workflow language.

### Established Patterns (from prior decisions / sibling repos)
- **`live-bets/` mono-repo layout** (sibling, separate git): `backend/` + `frontend/` + `docker-compose.yml` at root with services {api, worker, beat, db, redis, flower}. Same target topology as D-02 — proven in Pol's production. Validates the choice without forcing import.
- **Phase 2 CONTEXT.md** locks downstream contracts from Phase 1:
  - `AuditService.record(actor, event_type, payload, ip, *, session)` — exact signature in D-21
  - `Settings` exposes `SESSION_SIGNING_KEY` and `ADMIN_TOKEN` (Phase 2 adds these — Phase 1 must leave room in `config.py` per D-09)
  - structlog scrubber drops `X-Admin-Token` header value and `xp_session` cookie value — D-25 preempts both keys
  - Redis client provider available as a FastAPI dependency — Phase 1 ships `get_redis()` dependency
  - Async session dependency `get_async_session` — Phase 1 ships in `app/db/session.py`
  - Celery beat schedule editable — celery-redbeat (D-02 beat service) supports this

### Integration Points (Phase 1 = the seam every later phase plugs into)
- **`get_async_session` (FastAPI Depends)** — all DB-touching routes use this; Phase 1 ships, Phases 2+ depend on it
- **`get_redis` (FastAPI Depends)** — Redis client; Phase 1 ships, Phase 2 uses for `last_seen_at` debounce, Phase 6 uses for Polymarket polling lock
- **`AuditService.record(...)`** — Phase 1 ships, Phases 2-10 are forbidden from raw INSERT into `audit_log`
- **`Settings()` singleton (via `@lru_cache`)** — Phase 1 ships, all phases read configuration through it
- **`structlog.get_logger()`** — Phase 1 configures, all phases bind their own context
- **`Money` SQLAlchemy alias (`app/db/types.py`)** — Phase 1 ships, every money-bearing column in Phases 3+ uses it
- **`FeatureFlagService.is_enabled(...)`** — Phase 1 ships, Phase 3 uses for Stripe gate, Phase 6 for Polymarket sync gate, Phase 8 (v2) for admin 2FA gate
- **Celery `celery_app` factory + `app.celery_app.beat_schedule`** — Phase 1 ships empty beat schedule + worker config; Phase 2 adds `cleanup_inactive_guest_users` task, Phase 6 adds Polymarket poll, Phase 7 adds resolution detect, Phase 9 adds reconciliation
- **`/healthz` + `/readyz`** — Phase 1 ships; deploy infra (Railway/Fly.io) probes these

</code_context>

<specifics>
## Specific Ideas

- **`uv` over `poetry`/`pip-tools` (D-08):** `uv` install of all backend deps from scratch in a fresh venv is ~5-10 seconds; poetry takes 60-90 seconds. CI runtime delta over a project's lifetime is hours saved. Astral has clearly won.
- **Custom money-lint script over ruff plugin (D-17):** A ruff plugin requires either a Rust-side rule (high friction) or maintaining a separate `ruff_plugin_xpredict_money` Python package (Ruff has no Python plugin API as of 2026.05). An AST script in `scripts/` is ~80 lines, lives with the code it lints, easy for Pol to understand and modify.
- **Two-mechanism audit immutability (D-20):** The Postgres trigger is the load-bearing defense. The GRANT revoke is documentation-as-code — anyone reading the schema sees "this table is special". Belt and suspenders for a money-critical surface.
- **`is_dev` Settings property (D-10) drives 3 behaviors:** structlog console vs JSON renderer, Sentry init skip-unless-explicit-DSN, cookie `secure` flag (Phase 2 reads). Avoids three independent `if ENVIRONMENT == "dev"` checks scattered across the codebase.
- **Frontend Sentry uses `NEXT_PUBLIC_SENTRY_DSN`:** The `NEXT_PUBLIC_` prefix is required by Next.js for client-bundle exposure. The DSN is not a secret in the security sense (it's a write-only public token), but it should still be a different DSN from the backend's Sentry project tag (or just the same DSN with a `service=frontend` tag — D-27 picks the latter for simplicity).
- **No PgBouncer in Phase 1 (D-41):** Adds operational complexity for zero v1 benefit (single dev environment, low concurrency). When staging needs it, the planner of that work documents pooling-mode discipline per PITFALLS.md #7. Phase 1 lays the doctrine ("`SET LOCAL` only, never `SET`") so the future addition doesn't break tenant scoping.
- **Mailpit over MailHog:** MailHog is unmaintained (last release 2020); Mailpit is the active fork. STACK.md §6 confirms. Phase 2 doesn't actually send email (guest mode), but Phase 1 includes Mailpit for v2 AUTH-FULL readiness and because zero ongoing cost.
- **Sentry triple-trigger endpoints kept short-term (D-29):** They live in code through Phase 11 acceptance, then Phase 11 either removes them or gates behind a `?key=…` query param matching `Settings.SENTRY_TEST_KEY`. Phase 1 ships them naked because no real users exist yet.

</specifics>

<deferred>
## Deferred Ideas

Captured during this discussion but out of Phase 1 scope.

- **PgBouncer / advanced connection pooling** — staging/prod deploy work; not docker-compose dev environment.
- **Prometheus metrics endpoint + Grafana dashboards** — Phase 11 hardening (PITFALLS.md "Looks Done But Isn't" lists Postgres metrics + slow query log under deploy/infra).
- **Database backup + restore tested procedure** — Phase 11 hardening; not Phase 1 because there's no production data to back up.
- **OpenTelemetry distributed tracing** — Sentry's tracing is enough for v1. OTel comes when staging needs cross-service traces.
- **Admin UI for feature flags** — Phase 8 (Admin CRM) decision; v1 admin sets via SQL.
- **`tenant_id` runtime population via middleware (PITFALLS.md #7 RLS pattern)** — v2 multi-tenant. v1 just uses the default constant.
- **Row-Level Security policies on tables** — v2 multi-tenant.
- **Custom Ruff plugin for money-column enforcement** — current AST script is sufficient; revisit if Ruff ships a Python plugin API.
- **Async audit-event bus / Kafka / event-sourcing** — synchronous insert in caller's transaction is correct for v1. Async event bus adds infra cost (Kafka/Redpanda) with no v1 payoff. Revisit only if audit-log writes become a hot path.
- **Pinned Python version manager (mise/asdf) in repo** — assume devs have Python 3.12 installed; document in README. Not a Phase 1 deliverable.
- **`pre-commit.ci` hosted runner** — local pre-commit + GitHub Actions covers it; revisit if Cuco-equivalent contributors keep skipping local pre-commit.
- **Sentry source-map upload for frontend** — Phase 11 polish; staging-only concern.
- **Devcontainer / Codespaces config** — nice-to-have; not blocking. Add when team grows.

</deferred>

---

*Phase: 1 — Project Scaffold, Infra & Cross-Cutting Foundations*
*Context gathered: 2026-05-26 (Pol, --auto)*
