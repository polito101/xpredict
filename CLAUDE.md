# XPredict

Prediction market white-label, production-grade, construido fase a fase con GSD. Navegar/apostar en mercados de Polymarket (proxy) + mercados propios de la casa + CRM/admin para operar. Demo para vender → luego SaaS white-label.

## Equipo & regla única
- **Pol** — PM/Tech Lead: crea el roadmap, aprueba y mergea los PRs.
- **Cuco** — Dev (nombre real Agustin; commits como `Agustin <predictionmarkets.solutions@gmail.com>`).
- **Lo único que se le pide a un dev:** trabajar en una **rama por phase** (`gsd/phase-{N}-{slug}`), **nunca en `main`**, y abrir **1 PR por phase**. Nada más. Solo Pol mergea.

## Flujo por phase
`/gsd-autonomous` cubre el flujo en un comando (plan → execute → verify → code-review → ship). Gates de calidad activos (`plan_check`, `verifier`, `code_review`). Modo `yolo`, branching por phase. Estado y fases en `.planning/`. PRs con `gh pr create` o el GitHub MCP.

## Stack
- **Backend:** Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Postgres 16 · Redis · Celery + redbeat · FastAPI-users (Argon2id) · ledger double-entry propio.
- **Frontend:** Next.js 15 · React 19 · Tailwind 4 · shadcn/ui. Usa el **standalone pnpm 9.15.0**, NUNCA `corepack pnpm` (resuelve a 11.x destructivo: borra node_modules, reescribe lockfile).

## Entorno
- Python 3.12 + uv + Docker para fases backend. Tests: backend `cd backend && uv run pytest` (testcontainers + Docker); frontend `cd frontend && pnpm vitest run`.
- GitHub MCP en `.mcp.json` (PAT vía `GITHUB_PERSONAL_ACCESS_TOKEN`). `.env.local` (gitignored) solo secretos.

## Spike findings
Patrones, constraints y gotchas de implementación → `Skill("spike-findings-xpredict")`.
