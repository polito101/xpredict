---
phase: 01
slug: scaffold-foundations
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-26
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest 8.x + pytest-asyncio 0.24+ (`asyncio_mode = "auto"`) |
| **Frontend framework** | Vitest 2.x (with `environment: "node"` for route-handler tests) |
| **Backend config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` — created in 01-01-PLAN Task 1 |
| **Frontend config file** | `frontend/vitest.config.ts` — created in 01-02-PLAN Task 2 |
| **Backend quick run command** | `cd backend && uv run pytest tests/test_settings.py tests/test_money_lint.py tests/test_sentry_init.py tests/test_health.py -x` (< 10s, unit-only) |
| **Backend full suite command** | `cd backend && uv run pytest tests/ -x` (includes testcontainers Postgres spin-up ~30-60s) |
| **Frontend quick run command** | `cd frontend && pnpm test --run` (< 10s) |
| **Frontend full suite command** | `cd frontend && pnpm test --run && pnpm build` |
| **docker-compose smoke** | `docker compose up -d --wait && docker compose ps --format json` — all 8 services healthy |
| **Estimated runtime (quick)** | ~10 seconds (backend) + ~10 seconds (frontend) |
| **Estimated runtime (full)** | ~60 seconds (backend with testcontainers) + ~20 seconds (frontend with build) + ~90 seconds (compose smoke first-boot) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/test_settings.py tests/test_money_lint.py tests/test_sentry_init.py -x` AND `cd frontend && pnpm test --run` — both < 30s.
- **After every plan wave:** Full backend (`uv run pytest tests/ -x`) + frontend (`pnpm test --run && pnpm build`) + docker-compose smoke (only after 01-03 ships compose).
- **Before `/gsd-verify-work`:** Full suite must be green; `bin/dev` must boot the stack; 5 ROADMAP Success Criteria all sign off in 01-04 Task 3.
- **Max feedback latency:** 30 seconds (quick) / 120 seconds (full + compose smoke).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | PLT-03, WAL-05 | T-01-01, T-01-03 | Settings reads env safely, Money type forces Numeric(18,4) | unit | `cd backend && uv run ruff check app/ scripts/ && uv run mypy app/` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | PLT-08, WAL-05 | T-01-04 | Sentry tags `service=`; money-lint enforces D-17 | unit | `cd backend && uv run python scripts/lint_money_columns.py && uv run ruff check app/ scripts/` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | PLT-03, PLT-08, PLT-10, WAL-05 | T-01-01, T-01-02, T-01-04, T-01-05 | Settings env loading; Sentry init; money-lint 4 cases; health endpoints | unit | `cd backend && uv run pytest tests/test_settings.py tests/test_money_lint.py tests/test_sentry_init.py tests/test_sentry_test_endpoint.py tests/test_sentry_test_task.py tests/test_health.py -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | PLT-10 | T-02-04 | Frontend scaffold builds; Dockerfile ready | unit | `cd frontend && pnpm typecheck && pnpm build` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | PLT-08 | T-02-03 | Sentry init on server + client; both tag `service=frontend`; sentry-test throws | unit | `cd frontend && pnpm test --run` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | PLT-10 | T-03-03, T-03-06 | docker-compose.yml syntactically valid; 8 services with healthchecks; .gitattributes prevents CRLF | unit | `docker compose config --quiet && docker compose config --services | wc -l` (expect 8) | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | PLT-01, PLT-02, PLT-06 | T-03-01, T-03-04 | Alembic migration creates tables with tenant_id ghost + immutability trigger + REVOKE + seeded flags; integration tests prove it | integration | `cd backend && uv run pytest tests/core/ -x -m integration` | ❌ W0 | ⬜ pending |
| 01-03-03 | 03 | 2 | PLT-08, PLT-10 | T-03-05 | docker compose up brings 8 services healthy; alembic upgrade head applies; Sentry triple-trigger fires | integration | `./bin/dev && docker compose ps --format json` (manual gate — Task 3 records evidence) | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 3 | PLT-04 | T-04-01, T-04-02 | gitleaks blocks known-fake secrets; clean repo scans clean (allowlist works) | integration | `gitleaks detect --config=.gitleaks.toml --source=. --no-banner --report-format json --report-path /tmp/gitleaks-clean.json && [ "$(jq 'length' /tmp/gitleaks-clean.json)" = "0" ]` | ❌ W0 | ⬜ pending |
| 01-04-02 | 04 | 3 | PLT-04, PLT-08, PLT-10 | T-04-03, T-04-04 | pre-commit hooks wired; 3 GitHub Actions workflows committed; bin/dev one-command works | unit | `(command -v pre-commit > /dev/null 2>&1 && pre-commit run --all-files) ; ls bin/dev bin/dev.ps1 Makefile README.md .github/workflows/backend-ci.yml .github/workflows/frontend-ci.yml .github/workflows/security.yml` | ❌ W0 | ⬜ pending |
| 01-04-03 | 04 | 3 | PLT-01..04, PLT-06, PLT-08, PLT-10, WAL-05 | T-01..T-04 | All 5 ROADMAP Phase 1 Success Criteria pass | human-check (blocking gate) | Manual sign-off in 01-04-SUMMARY.md | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All test infrastructure is created INSIDE the plans (Phase 1 is greenfield — there is no pre-existing test infra). The orchestration:

- [ ] `backend/pyproject.toml` `[tool.pytest.ini_options]` block — 01-01 Task 1
- [ ] `backend/tests/conftest.py` (testcontainers Postgres + fakeredis + async_session + client fixtures) — 01-01 Task 3, EXTENDED in 01-03 Task 2 with alembic-upgrade-on-engine-fixture
- [ ] `backend/tests/test_settings.py` — 01-01 Task 3 (covers PLT-03)
- [ ] `backend/tests/test_money_lint.py` — 01-01 Task 3 (covers WAL-05, 4 cases)
- [ ] `backend/tests/test_sentry_init.py` — 01-01 Task 3 (covers PLT-08 init)
- [ ] `backend/tests/test_sentry_test_endpoint.py` — 01-01 Task 3 (covers PLT-08 backend HTTP trigger)
- [ ] `backend/tests/test_sentry_test_task.py` — 01-01 Task 3 (covers PLT-08 celery worker trigger)
- [ ] `backend/tests/test_health.py` — 01-01 Task 3 (covers PLT-10 health endpoints with mocked deps)
- [ ] `backend/tests/core/test_audit_immutability.py` — 01-03 Task 2 (covers PLT-01 + PLT-02 — integration vs testcontainers PG)
- [ ] `backend/tests/core/test_feature_flags.py` — 01-03 Task 2 (covers PLT-06 — integration vs testcontainers PG)
- [ ] `backend/tests/fixtures/synthetic_secrets/.env.fake` — 01-04 Task 1 (PLT-04 negative fixture)
- [ ] `frontend/vitest.config.ts` — 01-02 Task 2
- [ ] `frontend/src/app/api/healthz/route.test.ts` — 01-02 Task 2 (covers PLT-10 frontend)
- [ ] `frontend/src/app/api/sentry-test/route.test.ts` — 01-02 Task 2 (covers PLT-08 frontend)
- [ ] Framework install: `uv add --dev pytest pytest-asyncio testcontainers fakeredis dirty-equals pytest-httpx ruff mypy pre-commit` — covered by `backend/pyproject.toml` in 01-01 Task 1; `pnpm add --save-dev vitest @vitest/coverage-v8` — covered by 01-02 Task 2.

*Greenfield phase: every test file listed above is created by Phase 1's plans. There is no existing infra to reuse.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sentry triple-trigger end-to-end (events appear in Sentry project tagged `service=api|worker|frontend`) | PLT-08 | Requires a real `SENTRY_DSN` + `NEXT_PUBLIC_SENTRY_DSN` configured and the Sentry web UI to eyeball; cannot be asserted from code without Sentry CLI integration (out of scope for Phase 1) | 01-03 Task 3 + 01-04 Task 3: with DSN set, run `curl /_sentry-test` (backend), `celery call sentry_test_task` (worker), `curl /api/sentry-test` (frontend); check Sentry project for 3+ events. |
| docker-compose runtime health (all 8 services pass `healthy` status) | PLT-10 | docker-compose state is system-level, not code-level; the test depends on Docker daemon, host port availability, image pulls | 01-03 Task 3: run `./bin/dev`, eyeball `docker compose ps`; programmatic check is `docker compose ps --format json | jq '.[].Health'` returning 8x `healthy`. |
| Direct DB `UPDATE audit_log` raises in psql shell | PLT-02 | The pytest integration test covers this via SQLAlchemy DBAPIError; a direct psql round-trip is "eyeball confirmation" but not strictly required | 01-04 Task 3: `docker compose exec db psql -U xpredict -d xpredict -c "INSERT INTO audit_log..." ; "UPDATE audit_log..."` — expect Postgres error message containing `audit_log is append-only -- UPDATE and DELETE are forbidden`. |
| `gitleaks` CLI blocking a known-secret commit on a real branch | PLT-04 | The integration command `gitleaks detect` is automated, but observing CI's PR-blocking behavior requires pushing a throwaway branch with a fake secret — out of scope to script in Phase 1 | 01-04 Task 3 + post-merge throwaway: push a branch with a real-looking ADMIN_TOKEN value; expect security.yml workflow to fail; revert. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (01-04 Task 3 is `human-check` gate per the manual-only nature of full Phase 1 acceptance; this is the documented exception)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (01-04 Task 3 follows 2 fully-automated tasks)
- [x] Wave 0 covers all MISSING references — every test file is created by Phase 1's plans
- [x] No watch-mode flags (all `pnpm test --run` and `pytest -x`, no `--watch`)
- [x] Feedback latency < 120s for full suite + compose smoke (estimated)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner sign-off — final acceptance by Pol via 01-04 Task 3)
