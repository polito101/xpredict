# Phase 1 Discussion Log

**Phase:** 1 — Project Scaffold, Infra & Cross-Cutting Foundations
**Mode:** `--auto` (autonomous; Claude picked recommended option for every gray area)
**Discussed:** 2026-05-26
**Pol's role:** approved running discuss in auto mode after originally expecting Cuco to plan + implement Phase 1
**Decisions captured:** D-01 through D-47 in `01-CONTEXT.md`

---

## Context Carry-Forward

Read at start of session:
- `.planning/PROJECT.md` — Constraints, Key Decisions
- `.planning/REQUIREMENTS.md` — PLT-* + WAL-05
- `.planning/ROADMAP.md` — Phase 1 success criteria
- `.planning/STATE.md` — Decisions log
- `.planning/phases/02-auth-identity/02-CONTEXT.md` — Phase 2 decisions that depend on Phase 1 contracts (D-25 scrubber list, AuditService API, Settings keys)
- `.planning/research/STACK.md` §§1, 3, 5, 6 — version pins, dev tooling
- `.planning/research/ARCHITECTURE.md` §§1, 2 — modular monolith layout
- `.planning/research/PITFALLS.md` — pitfalls #3, #4, #7, #10 + demo traps

**Carried forward (locked, not re-asked):**
- Stack versions: Python 3.12, FastAPI 0.115.x, SQLAlchemy 2.0, asyncpg, Pydantic 2, Postgres 16, Redis 7, Celery 5.5, Next.js 15, React 19, Tailwind 4, shadcn/ui — STACK.md §§1, 3
- Mono-repo `backend/` + `frontend/` — PROJECT.md §Constraints
- Money-column standard `NUMERIC(18,4)` + `Decimal` — STATE.md decision 2026-05-25, PITFALLS.md #4
- `tenant_id UUID` ghost column on every player/market table — STATE.md decision 2026-05-25
- Audit-log immutability via Postgres trigger — STATE.md decision 2026-05-25
- `gitleaks` in CI — REQUIREMENTS.md PLT-04
- Sentry across FastAPI + Celery + Next.js — REQUIREMENTS.md PLT-08
- Pydantic BaseSettings for secrets — REQUIREMENTS.md PLT-03
- structlog (not loguru) — STACK.md §1.6
- Celery 5.5 + celery-redbeat (not APScheduler, not ARQ) — STACK.md §1.4
- `slowapi` for rate limits — installed but NOT mounted in Phase 1 (deferred to phases that own the limited endpoints)
- testcontainers Postgres for tests (not sqlite) — STACK.md §5

---

## Gray Areas Selected (auto-selected all 8)

`[--auto] Selected all gray areas: A. Service composition, B. Backend project layout, C. Frontend project layout, D. Database & migrations, E. Audit log architecture, F. Observability, G. Secrets & CI, H. Feature flags table.`

---

## Area A — Service composition (docker-compose)

### Q1: What services in compose, what ports?
- **Options considered:**
  - (1) Minimal: db + redis + backend + frontend only
  - (2) Production-realistic: db + redis + backend + worker + beat + flower + mailpit + frontend ✅ recommended
  - (3) Maximalist: add PgBouncer, prometheus, grafana
- `[auto] Selected: (2) Production-realistic` — Phase 1 should mirror prod topology so phases 2-10 don't change compose, just add code. Mailpit is "free" (zero ongoing cost, future-proofs v2 AUTH-FULL email). Skip PgBouncer/prometheus — Phase 11 hardening.
- → **D-02** (services + ports), **D-04** (depends_on with healthchecks), **D-05** (named volumes), **D-06** (dev-only)

### Q2: Healthcheck strategy?
- **Options considered:**
  - (1) Skip healthchecks (let compose `up` "complete" once container starts)
  - (2) Lightweight existence checks (TCP port open) per service
  - (3) Proper liveness probes per service (pg_isready, redis-cli ping, /healthz, celery inspect ping) ✅ recommended
- `[auto] Selected: (3) Proper liveness probes` — required for `depends_on: condition: service_healthy` to prevent backend booting before Postgres accepts queries. Phase 1 acceptance criterion #1 in ROADMAP says "healthcheck passes for each service" — explicit.
- → **D-03**

---

## Area B — Backend project layout

### Q3: Module structure inside `backend/app/`?
- **Options considered:**
  - (1) Flat (`models.py`, `routes.py`, `services.py`)
  - (2) Layered (`controllers/`, `services/`, `repositories/`, `models/`)
  - (3) Feature folders + shared infrastructure (modular monolith) ✅ recommended
- `[auto] Selected: (3) Modular monolith` — per ARCHITECTURE.md §1 executive recommendation. Pol's "modular monolith with strict boundaries" guideline; each feature folder is a candidate for v2 service extraction. Phase 1 creates the skeleton + placeholder directories.
- → **D-07**

### Q4: Dependency management?
- **Options considered:**
  - (1) `requirements.txt` + pip (oldschool)
  - (2) Poetry (popular, slower)
  - (3) `pyproject.toml` + `pip-tools` (lockfile, conservative)
  - (4) `pyproject.toml` + `uv` (modern, fastest, won the ecosystem) ✅ recommended
- `[auto] Selected: (4) uv` — STACK.md §6 implicitly endorses; uv is now the default tool astral built around. 10-100x speed advantage in CI. Reproducible lockfile.
- → **D-08**

### Q5: Pydantic Settings shape?
- **Options considered:**
  - (1) Single `Settings` class (start simple) ✅ recommended
  - (2) Nested submodels per concern (`DatabaseSettings`, `RedisSettings`, etc.)
- `[auto] Selected: (1) Single class` — start simple; refactor when it gets unwieldy (>40 fields). Phase 1's set is small (~7 fields).
- → **D-09**, **D-10** (`is_dev`/`is_prod` properties)

---

## Area C — Frontend project layout

### Q6: Package manager?
- **Options considered:**
  - (1) npm (default, slow, sometimes wrong hoisting)
  - (2) yarn (older alt)
  - (3) pnpm (fastest, correct hoisting, de-facto standard 2026) ✅ recommended
- `[auto] Selected: (3) pnpm`.
- → **D-11**

### Q7: Monorepo tooling (Turbo/Nx)?
- **Options considered:**
  - (1) No monorepo tooling ✅ recommended
  - (2) Turbo
  - (3) Nx
- `[auto] Selected: (1) None` — backend and frontend are deployed independently and don't share TypeScript code. Turbo/Nx add overhead with no payoff for two unrelated subprojects.
- → **D-12**

### Q8: Sentry init pattern for Next.js 15?
- **Options considered:**
  - (1) Manual `Sentry.init()` in `_app.tsx` (deprecated)
  - (2) `@sentry/nextjs` with `instrumentation.ts` + `instrumentation-client.ts` (Next.js 15 standard) ✅ recommended
- `[auto] Selected: (2) instrumentation files` — per Sentry's Next.js 15 docs.
- → **D-14**

---

## Area D — Database & migrations

### Q9: Alembic baseline scope?
- **Options considered:**
  - (1) Empty baseline (just `alembic_version` table); each phase adds its own
  - (2) Baseline creates only Phase 1's tables (`audit_log`, `feature_flags`); subsequent phases add migrations ✅ recommended
  - (3) Baseline creates ALL v1 tables (`users`, `accounts`, `markets`, `bets`, etc.) up front
- `[auto] Selected: (2) Baseline = Phase 1 tables only` — phases own their schema. Option 3 would couple all phases to one migration, violating the per-phase shipping discipline.
- → **D-15**

### Q10: Alembic env.py engine choice?
- **Options considered:**
  - (1) Sync psycopg2 (standard) ✅ recommended
  - (2) Async asyncpg (newer pattern, more complex env.py)
- `[auto] Selected: (1) Sync psycopg2` — Alembic is synchronous by design; per STACK.md §1.2. Keeps env.py simple. App still uses asyncpg.
- → **D-16**

### Q11: Money-column lint enforcement mechanism?
- **Options considered:**
  - (1) Grep for `Float|REAL|MONEY` in models (fragile, false positives)
  - (2) Custom ruff plugin (hard — no Ruff Python plugin API as of 2026.05)
  - (3) Custom Python AST script in `scripts/` ✅ recommended
- `[auto] Selected: (3) AST script` — ~80 lines, lives with code, testable, easy to understand. Per PITFALLS.md #4.
- → **D-17** (script), **D-18** (`Money` SQLAlchemy alias)

---

## Area E — Audit log architecture

### Q12: Audit-log table schema?
- **Options considered:**
  - (1) Flat columns for everything (actor, event, payload columns × N)
  - (2) Structured: `actor`, `event_type`, `payload JSONB`, `ip`, `tenant_id` ✅ recommended
- `[auto] Selected: (2) Structured` — JSONB payload is the standard pattern, flexible across all audit types Phases 2-10 will produce.
- → **D-19**

### Q13: Immutability mechanism?
- **Options considered:**
  - (1) Postgres trigger only
  - (2) GRANT revoke only
  - (3) Both (defense in depth) ✅ recommended
- `[auto] Selected: (3) Both` — trigger is load-bearing (works even for superuser); GRANT revoke is documentation-as-code. Money-critical surface deserves belt and suspenders. Per PITFALLS.md "Looks Done But Isn't" → audit log is non-negotiable.
- → **D-20**

### Q14: Writer interface (sync vs async event bus)?
- **Options considered:**
  - (1) Synchronous insert in caller's transaction ✅ recommended
  - (2) Async fire-and-forget (Celery task)
  - (3) Event bus (Kafka/Redpanda)
- `[auto] Selected: (1) Sync insert` — atomicity: audit must commit with the action. Async loses this guarantee. ~1ms latency cost is acceptable. Event bus is over-engineering for v1.
- → **D-21**, **D-22** (tenant_id auto-population)

---

## Area F — Observability

### Q15: structlog renderer dev vs prod?
- **Options considered:**
  - (1) JSON everywhere (consistent but ugly in dev)
  - (2) Pretty console in dev, JSON otherwise ✅ recommended
- `[auto] Selected: (2)` — readable dev output, machine-readable prod output. Cheap ergonomic win.
- → **D-23**, **D-24**, **D-25** (processor stack incl. secret scrubber preempting Phase 2 keys), **D-26** (request_id binding pattern)

### Q16: Sentry project layout?
- **Options considered:**
  - (1) Separate Sentry project per service (api, worker, beat, frontend)
  - (2) One project per environment with `service=*` tag ✅ recommended
- `[auto] Selected: (2)` — easier cross-service correlation; free tier (5k events/month) is a single project's allowance, not per-service. Tags allow filtering and alert routing.
- → **D-27**, **D-28** (init points), **D-29** (triple-trigger test endpoints)

### Q17: Healthcheck endpoint shape?
- **Options considered:**
  - (1) `/healthz` only (liveness)
  - (2) `/healthz` (liveness) + `/readyz` (readiness checks DB + Redis) ✅ recommended
- `[auto] Selected: (2)` — k8s-standard pattern. docker-compose healthcheck uses `/healthz` (liveness); Railway/Fly.io probes can use either. Frontend ships `/api/healthz`.
- → **D-30**, **D-31** (no Prometheus in Phase 1 — Phase 11)

---

## Area G — Secrets & CI

### Q18: Secrets file convention?
- **Options considered:**
  - (1) `.env` committed with empty values (risky — easy to commit real value)
  - (2) `.env.example` committed (placeholders), `.env.local` gitignored (real values) ✅ recommended
- `[auto] Selected: (2)` — per PITFALLS.md "Hardcoded secrets in code" and Phase 2 CONTEXT.md (D-09 carryover). Sentry/Stack also recommends this.
- → **D-32**

### Q19: gitleaks custom rules?
- **Options considered:**
  - (1) Default rules only
  - (2) Default + custom rules for project-specific secret names (SESSION_SIGNING_KEY, ADMIN_TOKEN) ✅ recommended
- `[auto] Selected: (2)` — defense in depth. Cheap to add.
- → **D-33**, **D-34** (CI + pre-commit), **D-35** (full pre-commit stack)

### Q20: CI provider?
- **Options considered:**
  - (1) GitHub Actions ✅ recommended (already part of repo bootstrap per `.claude/`)
  - (2) CircleCI / GitLab CI
- `[auto] Selected: (1) GHA` — repo already on GitHub, no additional vendor to introduce.
- → **D-36**

---

## Area H — Feature flags table

### Q21: Feature flags table shape + service?
- **Options considered:**
  - (1) Minimal: `(key TEXT PK, enabled BOOLEAN, value JSONB)` ✅ recommended
  - (2) Production-grade: rules engine, percentage rollouts, user targeting, audit on changes (over-engineering)
- `[auto] Selected: (1) Minimal` — v1 needs a flip-switch, not a feature flag SaaS. Composite PK `(key, tenant_id)` is v2-ready.
- → **D-37** (schema), **D-38** (service API + no-cache initially), **D-39** (no admin UI v1, seed default flags)

---

## Cross-Cutting Decisions

- **D-40** Audit-event naming convention `domain.action` (e.g., `auth.guest_created`) — documented in `backend/CONVENTIONS.md` so Phases 2-10 align.
- **D-41** asyncpg pool config without PgBouncer in v1; `SET LOCAL` doctrine documented for v2 multi-tenant prep.
- **D-42** `tenant_id` ghost column policy is enforced by code review + documented convention (no automated check in v1; planner discipline).
- **D-43** Root `README.md` lists prerequisites + one-command setup + service URLs.

## Claude's Discretion (planner picks)

- **D-44** audit_log trigger error message text
- **D-45** ruff / mypy rule sets
- **D-46** additional `.gitleaks.toml` rules
- **D-47** dev Makefile / `bin/dev` script entries

---

## Scope Creep Avoided / Deferred

Captured in CONTEXT.md `<deferred>`:
- PgBouncer (staging/prod, not v1 dev)
- Prometheus + Grafana (Phase 11 hardening)
- Backup/restore tested procedure (Phase 11)
- OpenTelemetry distributed tracing (v2)
- Admin UI for feature flags (Phase 8)
- `tenant_id` middleware (v2 multi-tenant)
- Row-Level Security (v2 multi-tenant)
- Custom Ruff plugin (if Ruff ships Python API)
- Async audit event bus / Kafka (over-engineering)
- Python version manager pinning (mise/asdf) in repo
- `pre-commit.ci` hosted runner
- Sentry source-map upload for frontend (Phase 11)
- Devcontainer / Codespaces config

---

## Why `--auto` was the right call here

Phase 1 is the most "STACK.md-locked" phase of the project — version pins, structlog vs loguru, Celery vs ARQ, Postgres 16 vs 17, money-column standards, etc. are all already decided by research. The remaining gray areas (module layout, healthcheck format, lint enforcement mechanism, audit writer API, etc.) all have clear recommended defaults from STACK.md / ARCHITECTURE.md / PITFALLS.md. Asking Pol question by question would have produced the same answers with more friction.

The trade-off: Pol skipped the opportunity to assert preferences he might hold but hasn't documented. The escape hatch is reviewing `01-CONTEXT.md` before `/gsd:plan-phase 1` runs — any decision can be edited in place.

---

*Discussion completed: 2026-05-26*
*Next step: `/gsd:plan-phase 1`*
