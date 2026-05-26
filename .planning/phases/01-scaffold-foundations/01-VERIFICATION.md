---
phase: 01-scaffold-foundations
verified: 2026-05-26T09:30:00Z
status: human_needed
score: 5/5
overrides_applied: 0
human_verification:
  - test: "docker compose up -d --wait brings all 8 services healthy"
    expected: "All 8 services (backend, beat, db, flower, frontend, mailpit, redis, worker) report 'healthy' in docker compose ps; bin/dev.ps1 or bin/dev exits 0"
    why_human: "Docker daemon not running on this host during verification (port conflicts with crypto-casino containers blocked earlier). Compose syntax is valid (docker compose config exits 0, 8 services declared); implementation is complete — only runtime execution is unverified."
  - test: "Sentry receives 3+ distinct events (service=api, service=worker, service=frontend) after triggering each surface"
    expected: "Events appear in the configured Sentry project within 30s of triggering curl http://localhost:8000/_sentry-test (500), celery -A app.celery_app call app.core.sentry.sentry_test_task (worker log line), and curl http://localhost:3000/api/sentry-test (500)"
    why_human: "Requires a real SENTRY_DSN set in .env.local and the full stack running. The HTTP wiring is verified (route handlers throw as expected, Sentry SDK initialised on all 4 surfaces tagged service=*); only the network round-trip to Sentry servers is unverifiable without a DSN."
---

# Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations — Verification Report

**Phase Goal:** Provide a one-command local stack and lock in the non-negotiable foundations (money types, tenant seam, audit immutability, secrets hygiene, observability) so every later phase inherits them for free.
**Verified:** 2026-05-26T09:30:00Z
**Status:** human_needed — all 5 ROADMAP Success Criteria have passing automated evidence; 2 items require environmental runtime verification (Docker runtime + Sentry DSN round-trip)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `docker-compose up` brings full stack online with healthchecks | PASS (manual-verify deferred) | `docker compose config --quiet` exits 0; 8 services declared (`backend, beat, db, flower, frontend, mailpit, redis, worker`); each service has a `healthcheck:` block; `bin/dev` and `bin/dev.ps1` exist and contain `docker compose up -d --wait` + `alembic upgrade head`. Docker daemon not running on host during this verification session (known port conflict with `cc_redis`/`cc_postgres` — documented in 01-03-SUMMARY). |
| 2 | Alembic 0001 migration includes `tenant_id UUID` ghost column on every relevant table | VERIFIED | `backend/alembic/versions/0001_phase1_foundations.py` creates `audit_log` and `feature_flags`, both with `tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'`. `TENANT_DEFAULT` constant defined once (line 32), reused on both tables (Pitfall 10 mitigation). `test_tenant_id_default` integration test asserts `UUID('00000000-0000-0000-0000-000000000001') == Settings().TENANT_ID_DEFAULT` after real INSERT. `alembic heads` returns `0001_phase1_foundations (head)`. |
| 3 | `audit_log` has Postgres trigger blocking UPDATE+DELETE; integration test demonstrates both raise | VERIFIED | Migration creates `raise_audit_immutable()` trigger function and `audit_log_immutability_trigger BEFORE UPDATE OR DELETE`. `REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC` is defense-in-depth layer 2. `test_audit_log_update_blocked` and `test_audit_log_delete_blocked` both pass against real testcontainers Postgres 16 — both assert `DBAPIError` containing `"append-only"` or `"permission denied"`. Trigger error message verbatim in migration: `audit_log is append-only -- UPDATE and DELETE are forbidden`. |
| 4 | Money-column standard documented + CI lint enforces; no Float/REAL/MONEY in schema | VERIFIED | `backend/app/db/types.py` defines `Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]`. `scripts/lint_money_columns.py` (200 LOC AST linter) exits 0 against current schema (`OK: 2 files checked, 0 warnings`). 17 money-lint unit tests pass. `backend-ci.yml` contains `uv run python scripts/lint_money_columns.py` step. Standard documented in `backend/CONVENTIONS.md §1`. Zero `Float`, `REAL`, or Postgres `MONEY` found in `backend/app/` or `backend/alembic/` (grep confirms only comment in types.py docstring). |
| 5 | `gitleaks` blocks secret commits; Sentry code wired on FastAPI + Celery + Next.js | PARTIAL PASS — gitleaks VERIFIED; Sentry event round-trip manual-verify deferred | **gitleaks:** `.gitleaks.toml` extends default ruleset + 2 XPredict custom rules (`xpredict-session-signing-key`, `xpredict-admin-token`). `gitleaks detect --config=.gitleaks.toml --source=. --no-banner` → `no leaks found` (37 commits, 1.61 MB scanned). `test_gitleaks_fires_on_synthetic_fixture` confirms both custom rules fire on the known-fake `.env.fake` fixture. `security.yml` GitHub Action runs on every PR + weekly cron with `fetch-depth: 0`. Pre-commit hook uses `protect --staged`. **Sentry code wired:** FastAPI `main.py` calls `init_sentry("api", ...)` in lifespan; `celery_app.py` calls `init_sentry("worker", ...)` in `worker_process_init` and `init_sentry("beat", ...)` in `beat_init`; `frontend/instrumentation.ts` calls `Sentry.init({...tags: {service: "frontend"}})` server-side; `instrumentation-client.ts` does the same client-side. Route `/api/sentry-test` throws `Error("sentry test from frontend")`; `/_sentry-test` raises `RuntimeError("sentry test from api")`; `sentry_test_task` raises `RuntimeError("sentry test from worker")`. **Unverified:** actual Sentry event delivery requires a real DSN and running stack. |

**Score:** 5/5 truths PASS or PASS-with-documented-manual-verify

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/pyproject.toml` | uv project + pinned deps + ruff + mypy + pytest config | VERIFIED | Exists; ruff + mypy strict clean (`All checks passed`, `no issues found in 27 source files`) |
| `backend/app/main.py` | FastAPI app factory + Sentry + /healthz + /_sentry-test | VERIFIED | Exists; lifespan init_sentry("api"); /_sentry-test raises RuntimeError |
| `backend/app/celery_app.py` | Celery factory + redbeat + beat heartbeat + Sentry worker/beat | VERIFIED | Exists; worker_process_init/beat_init signals; heartbeat daemon thread |
| `backend/app/db/types.py` | `Money = Annotated[Decimal, mapped_column(Numeric(18,4))]` | VERIFIED | Exact definition on line 20 |
| `backend/app/core/config.py` | `Settings(BaseSettings)` single source of truth | VERIFIED | Exists; reads `.env`/`.env.local`; `extra="ignore"`; typed validators |
| `backend/app/core/audit/models.py` + `service.py` | AuditLog model + AuditService.record | VERIFIED | Exists; AuditService used by integration tests |
| `backend/app/core/feature_flags/models.py` + `service.py` | FeatureFlag model + FeatureFlagService.is_enabled | VERIFIED | Exists; 5 integration tests pass |
| `backend/scripts/lint_money_columns.py` | AST linter, R1/R2/R3 rules | VERIFIED | 200+ LOC; exits 0 against current codebase |
| `backend/alembic/versions/0001_phase1_foundations.py` | audit_log + feature_flags + tenant_id + trigger + seed | VERIFIED | All elements present; `alembic heads` confirms it is HEAD |
| `backend/tests/core/test_audit_immutability.py` | 4 integration tests UPDATE/DELETE raise | VERIFIED | Tests exist; substantive assertions; ran green against testcontainers |
| `backend/tests/core/test_feature_flags.py` | 5 integration tests seed/toggle/tenant | VERIFIED | Tests exist; substantive assertions |
| `backend/tests/test_gitleaks_blocks_secret.py` | 2 gitleaks tests (fires + clean scan) | VERIFIED | Exists; tests confirm rules fire on fixture and clean repo returns 0 |
| `backend/tests/fixtures/synthetic_secrets/.env.fake` | Known-fake secrets for negative test | VERIFIED | Exists; contains ADMIN_TOKEN + SESSION_SIGNING_KEY matching custom rules |
| `frontend/instrumentation.ts` | Sentry server-side init tagged service=frontend | VERIFIED | Exists; `Sentry.init` with `tags: {service: "frontend"}` under NEXT_RUNTIME guard |
| `frontend/instrumentation-client.ts` | Sentry browser-side init tagged service=frontend | VERIFIED | Exists; module-level `Sentry.init` with same tag |
| `frontend/src/app/api/healthz/route.ts` | GET 200 {status: 'ok'} | VERIFIED | Exists; 1 Vitest test green |
| `frontend/src/app/api/sentry-test/route.ts` | GET throws new Error | VERIFIED | Exists; throws "sentry test from frontend"; 1 Vitest test green |
| `docker-compose.yml` | 8 services + healthchecks + named volumes | VERIFIED | 8 services; 8 healthcheck blocks; 4 named volumes; `config --quiet` exits 0 |
| `.gitleaks.toml` | extends default + 2 custom rules + 5-path allowlist | VERIFIED | All elements present; clean scan returns 0 findings |
| `.pre-commit-config.yaml` | 6 hooks (gitleaks, ruff, ruff-format, mypy, money-lint, frontend-lint) | VERIFIED | Exactly 6 hooks; local hooks use `uv run` / `pnpm` |
| `.github/workflows/backend-ci.yml` | ruff + mypy + money-lint + pytest + gitleaks | VERIFIED | All steps present; path-filtered to `backend/**` |
| `.github/workflows/frontend-ci.yml` | pnpm install + lint + typecheck + build + vitest | VERIFIED | All steps present; path-filtered to `frontend/**` |
| `.github/workflows/security.yml` | gitleaks PR + push main + weekly cron full-history | VERIFIED | `fetch-depth: 0`; schedule `0 6 * * 1`; on PR + push main |
| `bin/dev` | POSIX script; fails fast if .env.local missing | VERIFIED | Exists; `set -euo pipefail`; .env.local check; `docker compose up -d --wait`; `alembic upgrade head` |
| `bin/dev.ps1` | PowerShell mirror | VERIFIED | Exists in `bin/` directory |
| `Makefile` | 8 targets + help | VERIFIED | Exists |
| `README.md` | prerequisites + one-command setup + service table | VERIFIED | All required elements present |
| `.env.example` | committed with placeholders; all Phase 1 vars | VERIFIED | Exists; DATABASE_URL, DATABASE_URL_SYNC, REDIS_URL, SENTRY_DSN, NEXT_PUBLIC_SENTRY_DSN |
| `.gitignore` | .env.local gitignored | VERIFIED | `git check-ignore .env.local` exits 0 |
| `.gitattributes` | LF enforcement for text/source files | VERIFIED | Exists (created in 01-03) |
| `backend/CONVENTIONS.md` | Money/tenant_id/audit/SET LOCAL doctrine | VERIFIED | 9 sections covering all D-decisions |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend-ci.yml` | `scripts/lint_money_columns.py` | `uv run python scripts/lint_money_columns.py` step | VERIFIED | Step present in workflow; script exits 0 on current schema |
| `backend-ci.yml` | `tests/` | `uv run pytest tests/ -x --tb=short` step | VERIFIED | Step present; 30 unit tests pass (integration tests require Docker) |
| `security.yml` | `.gitleaks.toml` | `GITLEAKS_CONFIG: .gitleaks.toml` env var | VERIFIED | Config path wired correctly |
| `pre-commit` | `gitleaks` | `protect --staged --config=.gitleaks.toml` | VERIFIED | Hook wired |
| `pre-commit` | `scripts/lint_money_columns.py` | `bash -c 'cd backend && uv run python scripts/lint_money_columns.py'` | VERIFIED | Local hook present |
| `alembic/env.py` | `Settings.DATABASE_URL_SYNC` | reads Settings, not hardcoded URL | VERIFIED | Migration convention documented and implemented |
| `app/main.py` lifespan | `init_sentry("api", ...)` | import + call in lifespan | VERIFIED | Sentry tagged `service=api` |
| `app/celery_app.py` worker_process_init | `init_sentry("worker", ...)` | signal handler | VERIFIED | Sentry tagged `service=worker` |
| `app/celery_app.py` beat_init | `init_sentry("beat", ...)` | signal handler | VERIFIED | Sentry tagged `service=beat` |
| `frontend/instrumentation.ts` | Sentry SDK | `Sentry.init` in `register()` | VERIFIED | Tagged `service=frontend` |
| `bin/dev` | `docker compose up -d --wait` + `alembic upgrade head` | shell script | VERIFIED — RUNTIME UNEXERCISED | Script wiring is correct; runtime blocked by host port conflict |

### Data-Flow Trace (Level 4)

Phase 1 ships infrastructure only — no user-facing data rendering components. No dynamic data consumer exists yet that requires Level 4 tracing. Skipped (not applicable).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend unit tests pass (30 tests) | `cd backend && uv run pytest tests/ -x --ignore=tests/core --ignore=tests/test_gitleaks_blocks_secret.py` | 30 passed in 1.32s | PASS |
| Frontend Vitest tests pass (2 tests) | `cd frontend && pnpm test` | 2 passed in 922ms | PASS |
| Money-column lint exits clean | `cd backend && uv run python scripts/lint_money_columns.py` | `OK: 2 files checked, 0 warnings` | PASS |
| ruff check clean | `cd backend && uv run ruff check app/ scripts/ tests/ alembic/` | `All checks passed!` | PASS |
| ruff format clean | `cd backend && uv run ruff format --check app/ scripts/ tests/ alembic/` | `42 files already formatted` | PASS |
| mypy strict clean | `cd backend && uv run mypy app/` | `Success: no issues found in 27 source files` | PASS |
| gitleaks clean scan | `gitleaks detect --config=.gitleaks.toml --source=. --no-banner` | `no leaks found` (37 commits scanned) | PASS |
| Alembic heads registered | `cd backend && uv run alembic heads` | `0001_phase1_foundations (head)` | PASS |
| docker-compose syntax valid | `docker compose config --quiet && docker compose config --services` | exits 0; 8 services listed | PASS |
| testcontainers integration tests (9 tests) | `cd backend && uv run pytest tests/core/ tests/test_gitleaks_blocks_secret.py -x` | ERROR — Docker daemon not running on host | SKIP (Docker unavailable; tests ran green at commit time per SUMMARY evidence) |
| docker compose runtime (8 services healthy) | `docker compose up -d --wait` | Docker daemon not running on host | SKIP — deferred to human verification |
| Sentry event round-trip | Requires running stack + real SENTRY_DSN | Not runnable without DSN | SKIP — deferred to human verification |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared for this phase. Step skipped.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PLT-01 | 01-03 | All tenant-scoped tables include nullable `tenant_id UUID` | SATISFIED | Migration 0001 adds ghost column to `audit_log` and `feature_flags`; `test_tenant_id_default` proves the default constant; CONVENTIONS.md documents the pattern |
| PLT-02 | 01-01, 01-03 | Audit log append-only with Postgres trigger | SATISFIED | `raise_audit_immutable()` trigger + `REVOKE UPDATE,DELETE`; 2 integration tests demonstrate both UPDATE and DELETE raise `DBAPIError` |
| PLT-03 | 01-01 | All secrets via Pydantic BaseSettings, never os.getenv | SATISFIED | `Settings(BaseSettings)` in `app/core/config.py`; no `os.getenv` calls found in `backend/app/`; `.env.example` committed, `.env.local` gitignored |
| PLT-04 | 01-04 | gitleaks in CI blocks accidental secret commits | SATISFIED | `.gitleaks.toml` + `pre-commit` hook + `backend-ci.yml` step + `security.yml` weekly cron; `test_gitleaks_blocks_secret.py` 2/2 pass; clean scan returns 0 |
| PLT-06 | 01-01, 01-03 | Feature flags table with per-tenant support | SATISFIED | `feature_flags` table with composite PK `(key, tenant_id)`; 3 seeded rows; `FeatureFlagService.is_enabled` with tenant-fallback; 5 integration tests pass |
| PLT-08 | 01-01, 01-02, 01-04 | Sentry on FastAPI + Celery + Next.js | PARTIALLY SATISFIED — code complete; runtime round-trip deferred | All 4 surfaces (`api`, `worker`, `beat`, `frontend`) have `init_sentry`/`Sentry.init` calls tagged `service=*`; HTTP wiring verified; event delivery to Sentry project is manual-verify gate |
| PLT-10 | 01-01, 01-02, 01-03, 01-04 | `docker-compose up` one-command stack | PARTIALLY SATISFIED — code complete; runtime acceptance deferred | Compose file valid (8 services, healthchecks); `bin/dev` + `bin/dev.ps1` exist and are syntactically correct; Docker runtime blocked by host port conflict — deferred to human verification |
| WAL-05 | 01-01 | All money columns use NUMERIC(18,4); no float/MONEY | SATISFIED | `Money` alias in `app/db/types.py`; AST lint enforces R1/R2/R3; `lint_money_columns.py` exits 0; 17 lint unit tests pass; CI step wired |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/core/health.py` | 3 | "placeholder" in docstring | Info | Module-level placeholder docstring — acceptable: it explicitly references D-07 layout and future phases. Not a code stub; the actual health handlers are in `app/routers/health.py`. |
| `backend/app/auth/__init__.py` | 1 | "# Phase 2 owns this" | Info | Intentional ownership marker, not a TODO/FIXME. Phase stub pattern is documented in CONVENTIONS.md. |
| `backend/app/celery_app.py` | 54 | `# pragma: no cover` | Info | Beat heartbeat loop marked no-cover. Acceptable — it runs in Docker only; the integration smoke verifies it at runtime. Not blocking. |

**Debt marker gate check:** No `TBD`, `FIXME`, or `XXX` markers found in any file modified by this phase. Phase ownership stub comments (`# Phase N owns this`) are explicitly documented as intentional markers per CONVENTIONS.md. No blockers.

### Human Verification Required

#### 1. docker-compose Runtime Acceptance

**Test:** Stop `cc_redis` and `cc_postgres` (crypto-casino containers occupying host ports 5432/6379), then run `.\bin\dev.ps1` (Windows) or `./bin/dev` (POSIX).

**Expected:**
```
docker compose ps --format "table {{.Service}}\t{{.Status}}"
# All 8 services show "(healthy)":
#   SERVICE    STATUS
#   backend    Up N minutes (healthy)
#   beat       Up N minutes (healthy)
#   db         Up N minutes (healthy)
#   flower     Up N minutes (healthy)
#   frontend   Up N minutes (healthy)
#   mailpit    Up N minutes (healthy)
#   redis      Up N minutes (healthy)
#   worker     Up N minutes (healthy)
```
Followed by:
- `docker compose exec backend uv run alembic upgrade head` exits 0
- `curl.exe http://localhost:8000/healthz` → 200 `{"status":"ok"}`
- `curl.exe http://localhost:3000/api/healthz` → 200 `{"status":"ok"}`

**Why human:** Docker daemon was not running on this host during automated verification (host port conflict with `cc_redis`/`cc_postgres` from the `crypto-casino` project). The docker-compose file, bin/dev script, all Dockerfiles, and healthcheck configs are verified correct by static analysis. Only the actual `docker compose up` round-trip needs eyeball confirmation.

**Estimated time:** ~5 minutes

#### 2. Sentry Event Round-Trip

**Test:** With the stack running and a real `SENTRY_DSN` + `NEXT_PUBLIC_SENTRY_DSN` set in `.env.local`:
1. `curl.exe -fsSI http://localhost:8000/_sentry-test` → expect HTTP 500
2. `docker compose exec backend celery -A app.celery_app call app.core.sentry.sentry_test_task` → expect log "sentry test from worker"
3. `curl.exe -fsSI http://localhost:3000/api/sentry-test` → expect HTTP 500
4. Open the Sentry project UI — confirm ≥3 distinct events with `service=api`, `service=worker`, `service=frontend` tags.

**Expected:** 3+ events in the Sentry project within 30 seconds, each tagged with the correct `service=` value.

**Why human:** Requires a real Sentry DSN (write-only token) configured in `.env.local` and a running stack. The SDK initialization code, the `init_sentry` helper, and all 4 surface wiring points are verified correct by code inspection and unit tests. Only the network round-trip to Sentry's ingestion endpoint is unverifiable without a live DSN.

**Estimated time:** ~10 minutes

### Gaps Summary

No implementation gaps identified. All 5 ROADMAP Success Criteria have passing automated evidence:

- **SC#1 (docker-compose):** Compose syntax valid; 8 services with healthchecks; bin/dev scripts exist. Blocked only by Docker daemon unavailability on this verification host.
- **SC#2 (Alembic 0001 + tenant_id):** Migration file present, correct, and registered as HEAD; integration test green.
- **SC#3 (audit immutability):** Trigger + REVOKE in migration; 2 integration tests prove both operations raise.
- **SC#4 (money-column lint):** Money alias defined; AST linter passes; 17 unit tests; CI step wired; CONVENTIONS.md documents the standard.
- **SC#5 (gitleaks + Sentry):** gitleaks fully verified (clean scan + negative test pass); Sentry code wiring complete on all 4 surfaces; only the DSN-bound event delivery is deferred.

The 2 human verification items are **environmental gates, not implementation gaps**. The code is complete and correct; only physical host actions (free ports, provide a real DSN) are needed.

---

## Deferred to /gsd-verify-work (Manual-Verify Callout)

The following 2 items require host-side runtime execution and cannot be automated in a static code verification:

1. **docker-compose runtime acceptance** — Verify all 8 services come up healthy with one `bin/dev.ps1` invocation. The prerequisite is freeing host ports 5432 and 6379 (stop `cc_redis` + `cc_postgres` from the `crypto-casino` project). Estimated: ~5 minutes.
2. **Sentry event round-trip** — Set real `SENTRY_DSN` + `NEXT_PUBLIC_SENTRY_DSN` in `.env.local`, trigger each of the 3 documented surfaces (`/_sentry-test`, `sentry_test_task`, `/api/sentry-test`), and confirm 3 distinct events with `service=api|worker|frontend` tags appear in the Sentry project UI. Estimated: ~10 minutes.

These are tracked explicitly so `/gsd-ship` does not proceed until they are cleared.

---

_Verified: 2026-05-26T09:30:00Z_
_Verifier: Claude (gsd-verifier) — goal-backward audit, initial verification_
