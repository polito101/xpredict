# XPredict

White-label, production-grade prediction market platform (play money in v1). Users bet
on real-world events (politics, sports, crypto, culture); operators get a turnkey product
under their brand.

**Backend:** FastAPI · SQLAlchemy 2 (async) · Postgres 16 · Redis · Celery
**Frontend:** Next.js 15 · React 19 · Tailwind v4 · shadcn/ui

> Built phase by phase via GSD. See [`README-SETUP.md`](README-SETUP.md) for the
> collaborative workflow and [`.planning/`](.planning/) for the roadmap and requirements.

## Layout

```
backend/     FastAPI app (modular monolith), Celery worker/beat, Alembic migrations
frontend/    Next.js 15 App Router UI (mobile-first)
docker-compose.yml   Local backend stack: Postgres + Redis + API + worker + beat
```

## Prerequisites

- **Docker** + Docker Compose — backend stack
- **Node 20+** — frontend
- **Python 3.12 + [uv](https://docs.astral.sh/uv/)** — backend dev/tests outside Docker

## Quickstart

### 1. Backend stack (Docker)

```bash
docker compose up --build     # API at http://localhost:8000  (try /health and /docs)
```

This starts `db`, `redis`, the `backend` API, and the Celery `worker` + `beat`.
Dev credentials default to `xpredict` / `xpredict`; override with `POSTGRES_*` env vars
(or a root `.env`) if needed. (The root `.env.example` is for optional Linear hooks only.)

### 2. Frontend (local dev — best HMR)

```bash
cd frontend
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:3000
```

### Backend without Docker (fast iteration / tests)

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload      # http://localhost:8000
uv run pytest
uv run ruff check . && uv run mypy app
```

> Database migrations (Phase 2+): `uv run alembic upgrade head` (or
> `docker compose run --rm backend alembic upgrade head`).

## Conventions

- **Money** is `NUMERIC(18,4)` + Python `Decimal` — never floats (enforced once models land).
- **Migrations:** Alembic uses the sync psycopg URL; the app uses async asyncpg. Single
  source of truth for both URLs is `backend/app/config.py`.
- **Line endings:** LF everywhere (see `.gitattributes`) for clean Linux/Docker builds.

## Status

Phase 1 of 11 — **Project Scaffold, Infra & Cross-Cutting Foundations**. Business modules
(auth, wallet, markets, bets, settlement) arrive in later phases per `.planning/ROADMAP.md`.
