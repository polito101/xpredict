# XPredict

White-label, production-grade prediction market platform. Operators sell prediction
markets under their own brand; XPredict supplies the backend (FastAPI + Postgres +
Celery), the Polymarket sync, the wallet/ledger, and a Next.js player and admin UI.
Built phase by phase via the [GSD workflow](README-SETUP.md).

## Prerequisites

- **Docker Desktop** (or Docker Engine + Docker Compose v2)
- **Python 3.12** plus **[uv](https://docs.astral.sh/uv/)** — `pip install uv` or `pipx install uv`
- **Node 20+** plus **pnpm 9.15.x** — `npm install -g pnpm@9.15.0` or `corepack enable && corepack prepare pnpm@9.15.0 --activate`
- **gitleaks** (CI parity) — `scoop install gitleaks` (Windows), `brew install gitleaks` (macOS), or download from [releases](https://github.com/gitleaks/gitleaks/releases)

> Pol's machine is Windows; the dev loop is dual-supported. POSIX uses `bin/dev`; Windows uses `bin\dev.ps1` (see "One-command setup" below).

## One-command setup

1. Clone the repo and copy the env template:

   ```bash
   cp .env.example .env.local
   # edit .env.local: set SENTRY_DSN / NEXT_PUBLIC_SENTRY_DSN if you have one
   ```

2. Bring the stack up (8 services + Alembic migrations) with one command:

   - **POSIX (Linux/macOS):** `./bin/dev`
   - **Windows PowerShell:** `.\bin\dev.ps1`
   - **Make (POSIX only):** `make dev`

   Both scripts run `docker compose up -d --wait` (waits for all healthchecks)
   followed by `docker compose exec backend uv run alembic upgrade head`.
   Expected runtime on a warm cache: 30-60 seconds.

## Services

| Service  | URL / Port                       | Notes                                    |
| -------- | -------------------------------- | ---------------------------------------- |
| Frontend | http://localhost:3000            | Next.js 15 + Tailwind 4 player UI        |
| Backend  | http://localhost:8000            | FastAPI; `/healthz`, `/readyz`, `/_sentry-test` |
| Flower   | http://localhost:5555            | Celery worker + beat dashboard           |
| Mailpit  | http://localhost:8025            | Dev SMTP catcher (Phase 2+ emails)       |
| Postgres | `localhost:5432` (xpredict user) | Persistent volume `pg_data`              |
| Redis    | `localhost:6379`                 | Persistent AOF volume `redis_data`       |

If host ports 5432 or 6379 are occupied (e.g., by other Docker projects), stop
those containers first; `docker compose up` cannot rebind a bound host port.

## First-time setup

### Seed the first admin

Phase 2 ships a separate admin authentication surface at `/admin/auth/*`
(AUTH-07). Admins are seeded from the environment — there is no self-
registration route. Set `FIRST_ADMIN_EMAIL` and `FIRST_ADMIN_PASSWORD`
in your `.env.local`, then:

```bash
cd backend
uv run python bin/create_admin.py
```

The script is idempotent — re-running it after the admin row already
exists prints "already exists" and returns 0 (no-op). It hashes the
password with Argon2id via `pwdlib` (same hasher the player surface
uses), so the seeded admin can log in at `POST /admin/auth/login` and
receive a Bearer JWT token (D-11, AUTH-07).

## Running tests

| Surface  | Command                                                      |
| -------- | ------------------------------------------------------------ |
| Backend  | `cd backend && uv run pytest tests/ -x`                      |
| Frontend | `cd frontend && pnpm test`                                   |
| Lint     | `make lint` (or invoke the individual ruff/mypy/pnpm tools)  |
| Format   | `make format`                                                |

The backend suite uses [testcontainers](https://testcontainers.com) to spin up
a real Postgres 16 — Docker must be running. Tests that need DB are marked
`@pytest.mark.integration`; the lightweight unit subset (Wave-0) runs without
Docker.

## Contribution checklist

- Install pre-commit hooks once per clone:

  ```bash
  pip install pre-commit
  pre-commit install
  ```

  The hooks run gitleaks (`--config=.gitleaks.toml`), ruff (lint + format),
  mypy strict on `backend/app/`, the WAL-05 money-column AST lint, and a
  frontend `pnpm lint && pnpm typecheck` block. Same shape as
  `.github/workflows/backend-ci.yml` and `frontend-ci.yml`, so green local
  pre-commit ≈ green CI.

- All work happens on **per-phase branches**, never on `main`. See
  `CLAUDE.md` for the branching policy.

- One PR per phase, opened via the GitHub MCP (`create_pull_request`).
  See `README-SETUP.md` and `CLAUDE.md` for the full workflow.

## Phase status

The roadmap lives in `.planning/ROADMAP.md` (11 phases; Phase 1 in progress at
the time of writing). Each phase ships under `.planning/phases/XX-{slug}/`
with a `PLAN.md`, per-plan `SUMMARY.md`, and (after `/gsd-verify-work`) a
`VERIFICATION.md`.

For the deeper onboarding/workflow guide (GitHub MCP setup, Linear, Slack,
GSD conventions), see [`README-SETUP.md`](README-SETUP.md).
