# Phase 1 — Foundation (close-out)

Status: **complete, stable, local.** Branch `gsd/phase-1-foundation` (not pushed).
Scope: project scaffold, infra, and cross-cutting foundations only — **no business
logic** (auth, users, wallet, markets, settlement are Phase 2+).

## What exists

```
backend/            FastAPI modular monolith (uv-managed)
  app/
    main.py         app factory: CORS, structlog, exception handlers, router mounts
    config.py       pydantic-settings (async asyncpg + sync psycopg URLs)
    celery_app.py   Celery instance (Redis broker) + health.ping task
    core/           logging (structlog), exceptions (XPredictError hierarchy)
    db/             SQLAlchemy 2 async engine/session + declarative Base
    api/health.py   GET /health (liveness), GET /health/ready (2s-bounded DB probe)
  alembic/          migrations wired to settings + Base.metadata (no migrations yet)
  tests/            pytest (health endpoint)
  Dockerfile        uv-based, slim
frontend/           Next.js 15 + React 19 + Tailwind 4 (src/ layout)
  src/app/          layout (Sora/Inter/JetBrains, metadata, branding) + page + globals
  src/components/   dark-premium UI integrated from xprediction-demo (18 components)
  src/lib/          api.ts (typed backend client) · mock-data · theme · motion hooks
docker-compose.yml  postgres:16 + redis:7 + backend (API) + celery worker + beat
README.md           quickstart + conventions
```

## Verification (at close)

- Backend: `ruff` clean · `mypy --strict` clean · `pytest` 2/2 green · uvicorn boots, `/health` 200.
- Frontend: `next build` green · lint + types clean · console clean · renders desktop + mobile.
- Infra: `docker compose config` valid (5 services). Not run live (Docker Desktop was off).
- Git: working tree clean; 6 semantic commits on the phase branch; `main` untouched.

## Conventions (locked, per `.planning/research/`)

- **Money:** `NUMERIC(18,4)` + Python `Decimal` from strings. Never floats / Postgres MONEY.
- **DB access:** SQLAlchemy 2.0 async (`select()` + `session.execute()`); Alembic runs sync (psycopg).
- **Config:** single source of truth is `app/config.py` (env-driven). Both DB URLs derive from it.
- **Line endings:** LF (`.gitattributes`). UI theming via CSS variables (`--accent` is white-label swappable).

## Ready for Phase 2 (extension points — NOT implemented here)

- **Backend modules** go in `backend/app/modules/<context>/` (`models.py`, `schemas.py`,
  `repository.py`, `service.py`, `router.py`) per `.planning/research/ARCHITECTURE.md §3`.
  Mount each router in `app/main.py` (`app.include_router(...)`).
- **First migration:** add models inheriting `app.db.base.Base`, import them in `alembic/env.py`,
  then `alembic revision --autogenerate`.
- **Frontend ↔ backend:** wire real data through `src/lib/api.ts` (`apiFetch` / `NEXT_PUBLIC_API_URL`),
  replacing `src/lib/mock-data.ts` consumers incrementally.
- **Auth (Phase 2):** fastapi-users v14 (Argon2) per STACK.md — not added yet.

## Explicitly NOT done

- No `docker compose up` run (no live backend↔Postgres proof yet).
- No `.planning/` edits (STATE/ROADMAP owned by the GSD flow).
- No `PLAN.md` / `VERIFICATION.md`, no push, no PR (ship/merge is a separate, deliberate step).
- UI uses mock data only — not yet connected to the backend.
