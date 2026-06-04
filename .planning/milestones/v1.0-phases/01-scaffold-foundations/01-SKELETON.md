# Walking Skeleton — XPredict

**Phase:** 1 (Project Scaffold, Infra & Cross-Cutting Foundations)
**Generated:** 2026-05-26

## Capability Proven End-to-End

> One sentence: the smallest user-visible capability that exercises the full stack.

**`docker compose up -d --wait` brings 8 services healthy; `curl http://localhost:8000/healthz` and `curl http://localhost:3000/api/healthz` both return 200; `alembic upgrade head` creates `audit_log` + `feature_flags` (with `tenant_id` ghost column and immutability trigger) inside Postgres; and a synthetic Sentry event from each of FastAPI, Celery worker/beat, and Next.js arrives in the configured Sentry project tagged `service={api|worker|beat|frontend}`.**

Phase 1 ships zero product features. The "user" of this walking skeleton is the next developer (Pol) and every later phase, who can rely on these foundations existing without renegotiating them.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI 0.115 + Uvicorn 0.32+ (per STACK.md §1.1) | Async-native, type-safe, well-understood, sibling repo (`live-bets`) proves the pattern in Pol's production. |
| Frontend framework | Next.js 15 App Router + React 19 + TypeScript 5.5+ (per STACK.md §3, D-13) | App Router only (Next 16 removes sync `cookies()`/`headers()`); RSC ready; pnpm de-facto standard. |
| Data layer | Postgres 16 + SQLAlchemy 2.0 async + asyncpg + Alembic + psycopg2-binary (for migrations) (D-15, D-16, D-41) | PG 16 stable (17 ecosystem ~17% not ready); SQLAlchemy 2.0 async API mandatory; sync engine for Alembic env.py is the established idiom. |
| Money types | `Money = Annotated[Decimal, mapped_column(Numeric(18,4), nullable=False)]` (D-18) + AST lint (D-17) | WAL-05 — never Float/MONEY; lint enforces at PR time; Pattern 4 in 01-RESEARCH. |
| Audit immutability | Postgres `BEFORE UPDATE OR DELETE` trigger + `REVOKE UPDATE,DELETE ON audit_log FROM PUBLIC` (D-20) | Defense in depth; trigger wins even for superuser; PLT-02. |
| Tenant seam | Nullable `tenant_id UUID` ghost column on every player/market table; constant default `'00000000-0000-0000-0000-000000000001'`; v2 flips to NOT NULL + RLS (D-15, D-42, PLT-01) | Schema-level prep for multi-tenant runtime without renegotiating tables in v2. |
| Background tasks | Celery 5.5 + celery-redbeat + Flower (D-02, STACK.md §1.4) | 5.5 is long-stable (5.6 too fresh); redbeat survives restarts and is HA-ready; Flower for dev observability. |
| Logging | structlog 24.4+ with `ConsoleRenderer` in dev and `JSONRenderer` in staging/prod (D-23, D-24, D-25) | loguru fights stdlib + no OTel interop; structlog is the 2026 standard. |
| Error tracking | Sentry SDK on 4 surfaces (FastAPI / Celery worker / Celery beat / Next.js) — one Sentry project per env, tagged `service=` (D-27, D-28) | Free tier (5k events/month) is enough for the demo; single project + tags is simpler than per-service projects. |
| Settings | Single `Settings(BaseSettings)` class via `pydantic-settings`; `.env.local` gitignored; `.env.example` committed (D-09, D-32, PLT-03) | One source of truth; never `os.getenv()`; secrets discipline locked Phase 1. |
| Secrets discipline | gitleaks in pre-commit + GitHub Actions CI; weekly full-history scan; custom rules for XPredict keys (D-33, D-34, D-36, PLT-04) | Blocks accidental commit before push and on PR; weekly scan catches history regressions. |
| Feature flags | `feature_flags` table with composite PK `(key, tenant_id)`; `FeatureFlagService.is_enabled(key, tenant_id=None)` (D-37, D-38, PLT-06) | DB-backed (queryable, auditable); per-tenant overrides ready for v2 without schema change; no cache in v1 — query every call. |
| Dependency management | `pyproject.toml` + `uv` (Python); `package.json` + `pnpm` (frontend) — no Turbo/Nx monorepo tooling (D-08, D-11, D-12) | uv 10-100x faster than pip; pnpm correct hoisting; the two subprojects deploy independently — no monorepo build tool needed. |
| Deployment target | docker-compose for dev; Railway/Fly.io for staging/prod (D-06, STACK.md §7) | docker-compose is NOT a deploy tool — same Dockerfiles target managed platforms. |
| Directory layout | Modular monolith under `backend/app/`: `core/` (cross-cutting) + feature folders (`auth/`, `wallet/`, `markets/`, `bets/`, `admin/`, `integrations/`) + `db/` + `routers/` (D-07, ARCHITECTURE.md §1) | Vertical slices in feature folders; cross-cutting infra in `core/`; placeholders carry "# Phase N owns this" comments so executors don't accidentally touch them. |

## Stack Touched in Phase 1

- [x] Project scaffold (backend `pyproject.toml` + uv lock; frontend `package.json` + pnpm lock; pytest 8 + Vitest 2 test runners)
- [x] Routing — `GET /healthz`, `GET /readyz`, `GET /_sentry-test` (backend); `GET /api/healthz`, `GET /api/sentry-test` (frontend)
- [x] Database — Alembic migration `0001_phase1_foundations` creates `audit_log` + `feature_flags`; **real write** via `AuditService.record()` from the immutability test fixture; **real read** via `FeatureFlagService.is_enabled()` against the 3 seeded flags
- [x] UI — Next.js 15 hello-world page at `/` rendering server-side; `/api/healthz` route handler wired
- [x] Deployment — `docker compose up -d --wait` brings 8 services healthy in one command; `bin/dev` script wraps `compose up + alembic upgrade head` for the canonical local boot

## Out of Scope (Deferred to Later Slices)

> Anything that is *not* in the skeleton. Be explicit — this list prevents future phases from re-litigating Phase 1's minimalism.

- **Users / accounts / authentication** — Phase 2 (Auth & Identity) creates `users` table and Argon2id flows
- **Wallets / ledger / money flows** — Phase 3 creates `accounts`/`transfers`/`entries` (Phase 1 only ships the Money type + lint that Phase 3 inherits)
- **Markets / bets / settlements** — Phases 4-7
- **Rate limiting (slowapi)** — installed as a dep in Phase 1 (per STACK.md §1.7) but **not mounted**; Phases 2 + 5 mount on their endpoints
- **Real Sentry alert rule tuning** — Phase 11 (alerts are bound to features that emit them)
- **Mobile responsiveness validation** — Phase 11
- **Backup / restore tested procedure** — Phase 11
- **Prometheus metrics endpoint + Grafana dashboards** — Phase 11
- **OpenTelemetry distributed tracing** — Phase 11 if needed; Sentry's tracing is enough for v1
- **Admin UI for feature flags** — Phase 8 (Admin CRM); v1 admin sets via SQL or seed migration
- **`tenant_id` runtime population via middleware (RLS)** — v2 multi-tenant; v1 uses the constant default
- **Email sending (real SMTP)** — Phase 2 uses Mailpit for dev; staging picks provider then
- **Stripe / real-money** — `WalletService.recharge(payment_provider="stripe")` stub lands in Phase 3 (PLT-05) but is feature-flagged off

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2: Auth & Identity** — `users` table (with `tenant_id` ghost column per the Phase 1 pattern); fastapi-users v14 dual cookie/JWT backends; Argon2id; email verification via Mailpit; rate-limited auth endpoints (mounts slowapi on `/auth/*`).
- **Phase 3: Wallet & Double-Entry Ledger** — `accounts`/`transfers`/`entries` schema; `SELECT ... FOR UPDATE` discipline; nightly reconciliation Celery task; Stripe stub (PLT-05). Every money column uses `Mapped[Money]` — Phase 1's lint catches violations at PR.
- **Phase 4: Markets Domain & HouseAdapter** — `markets`/`outcomes`/`odds_snapshots` (with `tenant_id` ghost column); `MarketSource` Protocol; admin CRUD for house markets.
- **Phase 5: Bets, Settlement & First End-to-End Demo** — first user-visible vertical slice; reuses every Phase 1 foundation.
- **Phase 6: Polymarket Sync** — adds Celery Beat task to Phase 1's empty beat schedule; uses Phase 1's `httpx` + `tenacity` + Redis dedupe lock.
- **Phase 7: Polymarket Auto-Resolution & Admin Override** — adds another Celery Beat task; reuses Phase 5's `SettlementService`.
- **Phase 8: Admin CRM** — admin UI for users, transactions, bets, audit log viewer (Phase 1's `audit_log` is the source).
- **Phase 9: User App UX Polish** — market detail, WebSocket real-time updates, price-history chart (uses Phase 6's `odds_snapshots`).
- **Phase 10: Admin KPI Dashboard & Configurable Branding** — TenantConfig table joins Phase 1's tenant seam.
- **Phase 11: Hardening & Operator-Demo Gate** — mobile QA, Sentry alert tuning, gitleaks full-history, OWASP ZAP, ToS gate. First time anyone demos to a real operator.
