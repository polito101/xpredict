---
phase: 01-scaffold-foundations
plan: 04
subsystem: infra
tags: [gitleaks, pre-commit, github-actions, ci-cd, bin-dev, makefile, readme, phase-1-acceptance-gate]

# Dependency graph
requires:
  - phase: 01-scaffold-foundations
    plan: 01
    provides: "backend/scripts/lint_money_columns.py (money-lint script CI invokes); backend/pyproject.toml ruff+mypy config; backend/tests/conftest.py testcontainers Postgres fixture; AuditLog/FeatureFlag models + AuditService.record + FeatureFlagService.is_enabled"
  - phase: 01-scaffold-foundations
    plan: 02
    provides: "frontend/package.json with pnpm scripts lint/typecheck/build/test; pnpm-lock.yaml frozen for CI"
  - phase: 01-scaffold-foundations
    plan: 03
    provides: "Alembic 0001_phase1_foundations baseline with audit_log + feature_flags + tenant_id ghost column; audit immutability trigger; integration tests against testcontainers Postgres"
provides:
  - ".gitleaks.toml — extends default ruleset + 2 XPredict custom rules (xpredict-session-signing-key, xpredict-admin-token per D-33) + allowlist (.gitleaks.toml + README*.md + docs/*.md + tests/.*fixtures.* + .planning/*)"
  - "backend/tests/fixtures/synthetic_secrets/.env.fake — known-fake-secrets fixture for PLT-04 negative test"
  - "backend/tests/test_gitleaks_blocks_secret.py — 2 integration tests proving the linter fires on the fixture AND the allowlisted full-repo scan is clean (PLT-04 acceptance)"
  - ".pre-commit-config.yaml — 6 hooks: gitleaks v8.30.1 (protect --staged), ruff v0.8.6 (check + format), mypy v1.13 strict on backend/app/, local lint-money-columns (WAL-05), local frontend-lint (pnpm lint + typecheck)"
  - ".github/workflows/backend-ci.yml — Python 3.12 + uv sync --frozen + ruff lint/format + mypy + money-lint + pytest + gitleaks; path-filtered to backend/** + .gitleaks.toml"
  - ".github/workflows/frontend-ci.yml — Node 20 + pnpm 9.15.0 + frozen install + lint + typecheck + build + vitest; path-filtered to frontend/**"
  - ".github/workflows/security.yml — gitleaks/gitleaks-action@v2 on PR + main push + weekly Mon 06:00 UTC cron; fetch-depth: 0 full-history; contents:read permissions"
  - "bin/dev — POSIX shell entrypoint (mode 100755) running docker compose up -d --wait + alembic upgrade head; fails fast if .env.local missing"
  - "bin/dev.ps1 — PowerShell entrypoint for Pol's Windows machine; identical behaviour to bin/dev"
  - "Makefile — 8 targets (dev/down/test/lint/format/db.shell/db.reset/seed) + help (D-47)"
  - "README.md — title + 1-line summary, prerequisites, one-command setup (POSIX + Windows + make), service URL table, test runner table, contribution checklist (pre-commit install), phase status pointer; links to README-SETUP.md"
affects: [02-auth-identity, 03-wallet-ledger, 04-markets-domain, 05-bets-and-settlement, 06-polymarket-sync, 07-polymarket-auto-resolution, 08-admin-crm, 09-user-ux-polish, 10-admin-dashboard, 11-hardening-demo-gate]

# Tech tracking
tech-stack:
  added:
    - "gitleaks v8.30.1 (binary, scoop-installed locally; pinned in pre-commit + GitHub Actions)"
    - "(No new application deps — CI consumes the existing uv + pnpm stacks)"
  patterns:
    - "gitleaks .gitleaks.toml with [extend] useDefault = true + 2 XPredict-specific [[rules]] + 5-path [allowlist] (D-33 / Pitfall 6)"
    - "Pre-commit local hooks invoke `uv run` and `pnpm` so the linter versions match CI exactly (T-04-04 mitigation: CI doesn't drift from local lint)"
    - "GitHub Actions path-filtered triggers — backend-ci only runs on backend/** + .gitleaks.toml changes; frontend-ci only on frontend/**; security.yml runs on every PR + weekly cron"
    - "Defense-in-depth secret scanning: pre-commit (local diff) → backend-ci (PR diff) → security.yml (full history weekly) — three layers cover both fast feedback and retroactive sweep"
    - "Allowlisted synthetic-secret fixture lives at backend/tests/fixtures/synthetic_secrets/ with a .gitleaksignore-note.md documenting 'never put real secrets here'"
    - "bin/dev + bin/dev.ps1 dual entrypoints — Pol's Windows machine uses .ps1; CI / Linux / macOS use bash. Same docker compose commands, same alembic upgrade head, same printed URL list."

key-files:
  created:
    - ".gitleaks.toml (root)"
    - ".pre-commit-config.yaml (root)"
    - ".github/workflows/backend-ci.yml"
    - ".github/workflows/frontend-ci.yml"
    - ".github/workflows/security.yml"
    - "bin/dev (POSIX, executable mode 100755)"
    - "bin/dev.ps1 (Windows PowerShell)"
    - "Makefile (root)"
    - "README.md (root)"
    - "backend/tests/fixtures/__init__.py"
    - "backend/tests/fixtures/synthetic_secrets/.env.fake"
    - "backend/tests/fixtures/synthetic_secrets/.gitleaksignore-note.md"
    - "backend/tests/test_gitleaks_blocks_secret.py"
  modified:
    - "backend/tests/core/test_audit_immutability.py (ruff format only, no behaviour change)"
    - "backend/tests/core/test_feature_flags.py (ruff format only, no behaviour change)"

key-decisions:
  - ".gitleaks.toml allowlist includes .planning/* in addition to docs/*.md + README*.md + tests/.*fixtures.* + the gitleaks config itself — Pol's GSD planning artifacts contain example env strings + decision records mentioning secret-key shapes; without the .planning/ allowlist, the linter false-positives on its own context document."
  - "Pre-commit + 3 GitHub Actions workflows use path filters (backend/**, frontend/**, .gitleaks.toml, the workflow files themselves) so PRs that only touch docs or .planning/ don't burn CI minutes; security.yml is the unfiltered safety net that runs on every PR + weekly cron."
  - "gitleaks pre-commit hook uses `protect --staged` (not `detect`) — Pitfall 9 mitigation: protect scans only the staged diff so pre-commit completes in <1s even on large repos; the security.yml weekly cron is the full-history scan."
  - "bin/dev shell script committed with mode 100755 via `git update-index --add --chmod=+x` — git's mode bit, not the filesystem bit, is what survives `git clone` on POSIX systems."

patterns-established:
  - "Three-tier secret scanning: pre-commit (developer machine) → PR CI (every push) → weekly full-history cron. Each tier has a different latency/coverage tradeoff."
  - "Path-filtered workflow triggers — backend/frontend CI only runs when its tree changes; security.yml is path-unfiltered (every PR + cron)."
  - "Local pre-commit hooks invoke `uv run` and `pnpm` instead of the pre-commit repo's prebuilt mypy/ruff binaries — keeps the linter versions in sync with what CI's `uv sync --frozen` produces (T-04-04 alignment)."
  - "Allowlisted-fixture pattern: known-fake secrets live in tests/fixtures/ paths the allowlist permits; the linter test (test_gitleaks_blocks_secret.py) invokes gitleaks with a temp no-allowlist config to verify the rules still fire on those files."

requirements-completed: [PLT-04, PLT-08, PLT-10]

# Metrics
duration: pending
completed: pending
---

# Phase 01 Plan 01-04: CI + gitleaks + dev loop + Phase 1 acceptance gate Summary

**gitleaks .gitleaks.toml + 2 custom rules (xpredict-session-signing-key, xpredict-admin-token per D-33) + synthetic-secret negative-test fixture; .pre-commit-config.yaml with 6 hooks (gitleaks/ruff/ruff-format/mypy/money-lint/frontend-lint); 3 GitHub Actions workflows (backend-ci, frontend-ci, security with weekly full-history cron); bin/dev + bin/dev.ps1 + Makefile + README dev loop — and the Phase 1 acceptance gate runs the 5 ROADMAP Success Criteria, with 3.5/5 auto-verified and 1.5/5 deferred to Pol's manual checklist (docker-compose runtime + Sentry-event round-trip).**

> **Note:** This SUMMARY is a **Task-3-checkpoint skeleton**. Tasks 1 and 2 are fully shipped + committed; Task 3 (the Phase 1 acceptance gate) ran the automated portion and is awaiting Pol's manual verification of the docker-compose runtime + Sentry-event-landing checks (deferred from Plan 01-03 due to host port conflicts with crypto-casino containers). When Pol returns "approved" or describes failures, this SUMMARY will be closed out with the final manual-verify results, duration metric, and the plan-metadata commit.

## Performance

- **Started:** 2026-05-26T09:03:00Z
- **Tasks committed so far:** 2 of 3 (Task 3 is the human-verify gate)
- **Files modified:** 13 created + 2 ruff-formatted

## Accomplishments (Tasks 1 and 2)

- **Task 1 — gitleaks config + custom rules + synthetic-secret negative test (committed `a5d7601`)**
  - `.gitleaks.toml` extends default ruleset with 2 XPredict-specific `[[rules]]` (xpredict-session-signing-key, xpredict-admin-token verbatim from D-33) and a 5-path allowlist.
  - `backend/tests/fixtures/synthetic_secrets/.env.fake` ships two known-fake secrets matching both custom rules.
  - `backend/tests/test_gitleaks_blocks_secret.py` has 2 integration tests proving (a) the rules detect the fixture with a temp no-allowlist config, (b) the full repo with the committed allowlist scans cleanly.
  - **Verified locally:** 2/2 tests pass in 1.4s; gitleaks finds 2 leaks against the fixture; clean repo scan returns 0 findings.

- **Task 2 — pre-commit + 3 GH Actions + bin/dev + Makefile + README (committed `4c515ad`)**
  - `.pre-commit-config.yaml` — 6 hooks (gitleaks v8.30.1, ruff v0.8.6 check + format, mypy v1.13, lint-money-columns local, frontend-lint local).
  - `.github/workflows/backend-ci.yml` — Python 3.12 + uv sync --frozen + ruff check + ruff format --check + mypy strict + money-lint + pytest + gitleaks; path-filtered.
  - `.github/workflows/frontend-ci.yml` — Node 20 + pnpm 9.15.0 + frozen install + lint + typecheck + build + vitest; path-filtered.
  - `.github/workflows/security.yml` — gitleaks/gitleaks-action@v2 on PR + main push + weekly Mon 06:00 UTC cron; fetch-depth: 0.
  - `bin/dev` — POSIX entrypoint (mode 100755), fails fast if `.env.local` missing, runs `docker compose up -d --wait` then `alembic upgrade head`.
  - `bin/dev.ps1` — PowerShell mirror for Pol's Windows machine.
  - `Makefile` — 8 targets (dev/down/test/lint/format/db.shell/db.reset/seed) + help.
  - `README.md` — prerequisites, one-command setup, service URLs, test runner table, contribution checklist.

- **Task 3 (automated portion) — Phase 1 ROADMAP Success Criteria machine-checked.** See "Acceptance gate" section below.

## Task Commits

1. **Task 1: gitleaks config + custom rules + synthetic-secret fixture (PLT-04)** — `a5d7601` (feat)
2. **Task 2: pre-commit hooks + 3 GitHub Actions workflows + bin/dev + Makefile + README** — `4c515ad` (chore)
3. **Style: ruff format on test files (CI gate alignment)** — `99ee37e` (style)
4. **Plan metadata commit:** _pending — added after Pol approves the acceptance gate_

## Phase 1 Acceptance Gate — Results

The 5 ROADMAP Phase 1 Success Criteria are listed below with their verification status as of this checkpoint.

| # | ROADMAP Success Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `docker-compose up` brings all 8 services online with healthchecks passing | **mixed** | ✓ AUTO: `docker compose config --quiet` exits 0; 8 services; `bin/dev` shell syntax valid; `bin/dev.ps1` present. **⚠ MANUAL:** actually running `bin/dev` blocked by host port conflicts (crypto-casino + other dev containers occupy 5432/6379 — `docker ps` shows 15+ active containers). 01-03 manual-verify checklist applies. |
| 2 | Alembic 0001 migration with `tenant_id UUID` ghost column on every player/market table that v1 will have | **✓ AUTOMATED** | `tests/core/test_audit_immutability.py::test_tenant_id_default` PASSES (proves both `audit_log` and `feature_flags` have the ghost column with default `00000000-0000-0000-0000-000000000001`). `alembic heads` returns `0001_phase1_foundations (head)`. |
| 3 | `audit_log` table has Postgres trigger blocking UPDATE+DELETE; integration test demonstrates both raise | **✓ AUTOMATED** | `tests/core/test_audit_immutability.py::test_audit_log_update_blocked` + `::test_audit_log_delete_blocked` BOTH PASS. Trigger error message D-44 verbatim in migration: `audit_log is append-only -- UPDATE and DELETE are forbidden`. |
| 4 | Money-column standard documented + CI lint enforces (no Float/Real/MONEY) | **✓ AUTOMATED** | `cd backend && uv run python scripts/lint_money_columns.py` exits 0 against current schema. 17 money-lint unit tests in `tests/test_money_lint.py` pass (proves R1/R2/R3 fire correctly on synthetic-bad fixtures + suppress on JSONB/non-money columns). CI workflow includes the lint step (`grep lint_money_columns .github/workflows/backend-ci.yml` returns 1 match). Money-column standard documented in `backend/CONVENTIONS.md`. |
| 5 | `gitleaks` blocks secret commits + Sentry receives errors from FastAPI + Celery + Next.js | **mixed** | ✓ AUTO (gitleaks portion): `tests/test_gitleaks_blocks_secret.py` 2/2 PASS; clean-repo scan returns 0 findings; CI workflow has gitleaks step. **⚠ MANUAL** (Sentry portion): event landing needs a real `SENTRY_DSN` configured in `.env.local` + the stack running + each of the 4 surfaces (api/worker/beat/frontend) triggered manually; the HTTP wiring (500 from `/_sentry-test`, 500 from `/api/sentry-test`) is wired up but the Sentry-server round-trip is not auto-verifiable without a DSN. |

### Automated portion — auto-verifications (3.5 / 5)

```text
SC#2 (Alembic + tenant_id):       9/9 integration tests pass — test_tenant_id_default proves the ghost column default
SC#3 (audit immutability):        9/9 integration tests pass — UPDATE + DELETE both raise from the trigger
SC#4 (money-column lint):         17/17 money-lint tests pass + CI workflow includes the step
SC#5 (gitleaks portion):          2/2 gitleaks tests pass + clean-repo scan returns 0 findings
SC#1 (compose config syntax):     docker compose config --quiet exits 0; 8 services declared; bin/dev shell-syntax valid
```

Backend test suite end-to-end: **41/41 tests pass in ~15s** (32 unit + 9 integration). Backend lint: ruff check + ruff format --check + mypy strict all clean. Frontend: pnpm typecheck + 2/2 Vitest tests green.

### Manual-verify portion — deferred to Pol (1.5 / 5)

**SC#1 docker-compose runtime acceptance** — deferred from Plan 01-03 due to host port conflicts. Pol's machine has 15+ active containers running (multiple `postgres:17-alpine`, `redis:7.4-alpine` — including crypto-casino and other dev work), and at least one is bound to host port 5432 or 6379 which would prevent `bin/dev` from binding. Run the 01-03 manual-verify checklist (`.planning/phases/01-scaffold-foundations/01-03-SUMMARY.md §"Task 3 — Runtime Acceptance (Manual-Verify)"`).

**SC#5 Sentry-event round-trip** — needs:
1. Real `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN` (frontend) in `.env.local`.
2. `bin/dev` (or `bin\dev.ps1`) running with the stack healthy.
3. Trigger each of the 4 surfaces:
   - `curl -fsSI http://localhost:8000/_sentry-test` → 500 (FastAPI)
   - `docker compose exec backend celery -A app.celery_app call app.core.sentry.sentry_test_task` (Celery worker)
   - `docker compose exec beat celery -A app.celery_app call app.core.sentry.sentry_test_task` (Celery beat — same task, beat triggers it)
   - `curl -fsSI http://localhost:3000/api/sentry-test` → 500 (Next.js)
4. Open the Sentry project UI and confirm ≥3 distinct events tagged `service=api`, `service=worker`, `service=frontend` (beat shares the worker tag if both run the same task; that's acceptable per CONTEXT D-27).

Estimated total manual-verify time: 10-15 min (5 min for SC#1 runtime acceptance + 10 min for SC#5 Sentry round-trip).

## Decisions Made

1. **`.gitleaks.toml` allowlist also covers `.planning/*`** — beyond the spec's `tests/.*fixtures.* + docs/*.md + README*.md + .gitleaks.toml` paths, Pol's GSD planning artifacts (`.planning/phases/*/01-CONTEXT.md`, etc.) contain example secret strings (e.g., `SESSION_SIGNING_KEY=` mentions in D-33). Without `.planning/*` in the allowlist, the linter would flag the GSD documents themselves. This is an in-spec extension of D-46 ("planner can add more rules" + symmetric allowlist additions).
2. **Pre-commit `gitleaks` hook uses `protect --staged`** — Pitfall 9 says full-history scans are slow; the local hook scans only the staged diff (sub-second on big repos). The security.yml workflow does the weekly full-history sweep.
3. **All 3 GitHub Actions workflows path-filtered to the relevant tree** — backend-ci only runs on `backend/** + .gitleaks.toml + the workflow file`; frontend-ci only on `frontend/**`; security.yml is intentionally unfiltered (it must run on every PR + cron, regardless of what changed). This keeps CI fast for doc/planning-only PRs.
4. **`bin/dev` mode 100755 set via `git update-index --add --chmod=+x`** — git's mode-bit, not the filesystem bit (which Windows doesn't track), is what survives across clones on POSIX systems.
5. **3 test files re-formatted via `ruff format`** — Plan 01-03 committed `test_audit_immutability.py` and `test_feature_flags.py` with formatting that ruff would reformat; Task 1's new `test_gitleaks_blocks_secret.py` had the same issue. Since 01-04's `backend-ci.yml` includes a `ruff format --check` step that fails CI on un-formatted files, I committed format-only changes (commit `99ee37e`) as a Rule 3 blocking-CI fix. Zero behaviour change; verified 41/41 tests still pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking CI gate] ruff format on Plan 01-03 + Task 1 test files**
- **Found during:** Task 3 (running `ruff format --check` to align with the new backend-ci.yml workflow gate)
- **Issue:** 3 files would be reformatted by ruff: `tests/core/test_audit_immutability.py` + `tests/core/test_feature_flags.py` (both from Plan 01-03) + `tests/test_gitleaks_blocks_secret.py` (Task 1 of this plan). Plan 01-03 ran `ruff check` but not `ruff format --check`; Task 1 mirrored the same gap. With the new backend-ci.yml workflow running `ruff format --check`, every CI run would fail until these files are reformatted.
- **Fix:** Ran `uv run ruff format <files>` against the 3 files; pure formatting-only changes (string wraps, trailing-comma alignment). Re-ran `pytest tests/` to confirm 41/41 still pass.
- **Files modified:** `backend/tests/core/test_audit_immutability.py`, `backend/tests/core/test_feature_flags.py`, `backend/tests/test_gitleaks_blocks_secret.py`
- **Verification:** `uv run ruff format --check app/ scripts/ tests/ alembic/` → `42 files already formatted`
- **Committed in:** `99ee37e` (style commit, separate from the per-task feat/chore commits)

### Awaiting human decisions

None — all Task 1+2 work was auto-fixable per Rules 1-3.

## Deferred Items

The following will be closed out **after Pol's manual approval** of the Phase 1 acceptance gate:

1. **Plan metadata commit** — adds this SUMMARY + STATE/ROADMAP updates to a single closeout commit.
2. **STATE.md** — increment plan counter to 4/4, update Performance Metrics (duration), flip phase status, record acceptance-gate outcome.
3. **ROADMAP.md** — flip Phase 1 row to "completed" with 4/4 plans + completion date.
4. **`requirements mark-complete`** for PLT-04, PLT-08, PLT-10 (this plan's requirements).
5. **SUMMARY closeout sections** — duration metric, final accomplishments list, "Next phase readiness" (Phase 2 prereqs all in place per Plan 01-01's pre-locked contracts).

## Self-Check: PASSED (auto portion)

**Files created (13):**
- `.gitleaks.toml`, `.pre-commit-config.yaml`, `Makefile`, `README.md` (root, 4 files)
- `.github/workflows/{backend-ci.yml, frontend-ci.yml, security.yml}` (3 workflows)
- `bin/dev`, `bin/dev.ps1` (2 entrypoints)
- `backend/tests/fixtures/__init__.py`, `backend/tests/fixtures/synthetic_secrets/.env.fake`, `backend/tests/fixtures/synthetic_secrets/.gitleaksignore-note.md`, `backend/tests/test_gitleaks_blocks_secret.py` (4 fixture/test files)

**Files reformatted (2):** `backend/tests/core/test_audit_immutability.py`, `backend/tests/core/test_feature_flags.py` (format-only).

**Commits so far (3):**
- `a5d7601` — `feat(01-04): gitleaks config + custom rules + synthetic-secret fixture (PLT-04)`
- `4c515ad` — `chore(01-04): pre-commit hooks + 3 GitHub Actions workflows + bin/dev + Makefile + README`
- `99ee37e` — `style(01-04): apply ruff format to test files (Rule 3 — CI gate alignment)`

**End-to-end re-runs:**
- `cd backend && uv run pytest tests/` → **41/41 passing in ~15s**
- `cd backend && uv run ruff check app/ scripts/ tests/ alembic/` → All checks passed
- `cd backend && uv run ruff format --check app/ scripts/ tests/ alembic/` → 42 files already formatted
- `cd backend && uv run mypy app/` → Success: no issues found in 27 source files
- `cd backend && uv run python scripts/lint_money_columns.py` → OK: 2 files checked, 0 warnings
- `cd frontend && pnpm typecheck` → exit 0
- `cd frontend && pnpm test` → 2/2 Vitest tests green
- `gitleaks detect --config=.gitleaks.toml --source=. --no-banner` → **no leaks found**
- `docker compose config --quiet` → exit 0
- `cd backend && uv run alembic heads` → `0001_phase1_foundations (head)`

All 4 YAML files parse cleanly. `bin/dev` `bash -n` syntax check OK. `bin/dev` committed as `100755` (executable). All required README strings present (Prerequisites, bin/dev, http://localhost:3000, http://localhost:8000, pre-commit install, ROADMAP.md). All 8 Makefile targets declared.

---

*Phase: 01-scaffold-foundations*
*Plan: 04*
*Status: Awaiting Pol's manual approval of the Phase 1 acceptance gate (SC#1 runtime + SC#5 Sentry round-trip). Tasks 1+2 are shipped and committed.*
