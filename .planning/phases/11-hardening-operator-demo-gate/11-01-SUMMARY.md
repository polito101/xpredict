---
phase: 11-hardening-operator-demo-gate
plan: 01
subsystem: infra
tags: [ci, github-actions, docker-compose, bash, e2e, security, dry-run]

# Dependency graph
requires:
  - phase: 05-bets-settlement
    provides: tests/integration/test_phase5_e2e.py (bet->settle->wallet->portfolio E2E reused verbatim)
  - phase: 01-scaffold-foundations
    provides: docker-compose.yml (8 healthchecked services), backend-ci.yml CI conventions, .gitattributes LF policy
  - phase: 10-admin-kpi-branding
    provides: single Alembic head 0009_phase10_tenant_config (the dry-run migrates to head)
provides:
  - "bin/check_no_dev_config.sh — SC#3 Demo-Trap guard: fails on ENVIRONMENT=dev or hardcoded localhost/127.0.0.1 in backend/app or frontend/src"
  - ".github/workflows/prod-migration-dry-run.yml — boots the full stack staging-style, replays the Phase-5 E2E, runs the guard, tears down"
affects: [11-06 (Looks-Done audit cites this as SC#3 evidence), 11-02 (security-scan sibling workflow), operator-demo-gate]

# Tech tracking
tech-stack:
  added: []  # no runtime or dev package installed — reuses existing `uv sync --frozen` env + bundled docker compose
  patterns:
    - "New CI workflow mirrors backend-ci.yml conventions (trigger shape, permissions: contents: read, timeout-minutes, actions/checkout@v4) rather than mutating existing CI"
    - "Dev-config guard scoped to app-source roots with a documented allow-list of intentional localhost classes (Pitfall 1)"

key-files:
  created:
    - bin/check_no_dev_config.sh
    - .github/workflows/prod-migration-dry-run.yml
  modified: []

key-decisions:
  - "Guard localhost rule applied to BOTH app roots with a 4-class allow-list (||-fallback idiom, multi-line continuation, comment/docstring incl. RST ``..``, typed config default) — chosen over the plan's narrower options so the clean tree exits 0 without editing app code (constraint 1)"
  - "ENVIRONMENT=dev rule applied across both roots with NO allow-list (zero legitimate occurrences; config.py's typed annotation default is not matched by the regex)"
  - "E2E exec step passes -e ENVIRONMENT=staging because compose's x-backend-env anchor hardcodes ENVIRONMENT: dev for backend services; the functional bet->settle path is the load-bearing check, the staging-env assertion is applied per-exec"
  - "alembic invoked via `uv run alembic upgrade head` inside the container (matches bin/dev; alembic lives in the container's uv venv)"
  - "YAML-validity verify run through the backend uv venv (which ships PyYAML 6.0.3 transitively) — no new package installed, honoring the RULE 3 package-install exclusion"

patterns-established:
  - "SC#3 dev-config guard: grep -rnE rooted at backend/app + frontend/src with --include filters and test-file --exclude, then grep -vE allow-list passes; emits ::error:: + exit 1 on a genuine NEW leak"
  - "Ephemeral CI secrets: heredoc-generated .env (gitignored) with throwaway placeholders, contents never echoed (T-11-01-01)"

requirements-completed: [PLT-07]

# Metrics
duration: 4min
completed: 2026-06-02
---

# Phase 11 Plan 01: prod-migration-dry-run CI (SC#3 Demo-Trap Gate) Summary

**A non-mutating GitHub Actions dry-run that boots the full 8-service compose stack staging-style, replays the existing Phase-5 bet→settle→wallet→portfolio E2E, and a ~90-line bash guard that fails the build on hardcoded `localhost`/`ENVIRONMENT=dev` leaking into application source — with zero app-code, migration, or new-dependency changes.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-02T12:52:23Z
- **Completed:** 2026-06-02T12:56:46Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- `bin/check_no_dev_config.sh` — the SC#3 "Demo Trap" guard targeting this codebase's real config shape (`ENVIRONMENT`/`is_dev`, no `DEBUG` flag). Exits 0 on the clean tree, exits 1 on a NEW hardcoded `localhost` / `127.0.0.1` / `ENVIRONMENT=dev` in `backend/app` or `frontend/src`, and never scans compose / `.env.example` / tests / `.zap` / docs (Pitfall 1 allow-list).
- `.github/workflows/prod-migration-dry-run.yml` — `pull_request` + `push:main` triggered, `permissions: contents: read`, single `dry-run` job, `timeout-minutes: 20`. Writes an ephemeral staging-style `.env` (never logged), `docker compose up -d --wait` on all 8 healthchecks, `alembic upgrade head`, replays `test_phase5_e2e.py` under `ENVIRONMENT=staging`, runs the guard, always-tears-down `docker compose down -v`.
- The three existing CI workflows (`backend-ci.yml` / `frontend-ci.yml` / `security.yml`) are byte-identical to their pre-plan state — confirmed via `git diff --stat` (empty). No backend tests / wallet suite touched (Pol's track, constraint 3).

## Task Commits

Each task was committed atomically:

1. **Task 1: dev-config guard script (`bin/check_no_dev_config.sh`)** — `1e1a39d` (feat)
2. **Task 2: `prod-migration-dry-run.yml` CI workflow** — `d244962` (ci)

**Plan metadata:** (this SUMMARY + STATE + ROADMAP) — committed separately as `docs(11-01)` closeout.

_Task 1 carries `tdd="true"`; for a CI bash guard the RED/GREEN gate is the smoke check in the acceptance criteria (clean→0, injected violation→1) rather than a pytest file — verified empirically below, not via a separate `test(...)` commit. See TDD Gate Compliance._

## Files Created/Modified
- `bin/check_no_dev_config.sh` — 90-line bash guard (`#!/usr/bin/env bash`, `set -euo pipefail`, mirrors `bin/dev`); Rule A `ENVIRONMENT=dev` across both roots, Rule B `localhost`/`127.0.0.1` minus a 4-class allow-list.
- `.github/workflows/prod-migration-dry-run.yml` — 80-line workflow; mirrors `backend-ci.yml` conventions; no `services:` block (Pitfall 4); ephemeral `.env` (T-11-01-01).

## Acceptance Evidence

### Task 1 — `bin/check_no_dev_config.sh`
- `<verify>` (clean tree): `bash bin/check_no_dev_config.sh` → `OK: no hardcoded localhost / ENVIRONMENT=dev in application source.` **exit=0** ✅
- Smoke (injected bare `host = "localhost"` under `backend/app/__sc3_scratch__.py`) → `::error::...` **exit=1** ✅
- Smoke (injected `ENVIRONMENT = "dev"`) → **exit=1** ✅
- Smoke (injected bare `http://127.0.0.1:9000/internal`) → **exit=1** ✅
- Scratch file removed; clean tree re-verified **exit=0**; `git status` showed only the new guard (no app code touched) ✅
- Grep roots literally `backend/app` + `frontend/src` (no whole-repo scan); compose/`.env.example` structurally excluded (they live at repo root) ✅
- must_haves: `grep -c ENVIRONMENT` = 8 (≥1) ✅; `wc -l` = 90 (≥20) ✅

### Task 2 — `.github/workflows/prod-migration-dry-run.yml`
- `<verify>`: `python -c "import yaml,sys; yaml.safe_load(open(...)); print('yaml-ok')"` (run via backend uv venv) → `yaml-ok` **exit=0** ✅
- `grep -c 'ENVIRONMENT=staging'` = 3 (≥1) ✅
- references `tests/integration/test_phase5_e2e.py` (1×) and `check_no_dev_config` (1×) — both `key_links` match ✅
- contains `docker compose up -d --wait` (1×) and `if: always()` teardown (1×) ✅
- NO top-level `services:` block: `grep -cE '^\s*services:'` = 0 (Pitfall 4) ✅
- `git diff --stat` on the three existing CI workflows = empty (constraint 4) ✅

> The actual stack-boot + migrate + E2E run executes on the GitHub Actions runner (the workflow's own `dry-run` job — it requires Docker + the full compose stack). The plan's local `<verify>` is deliberately scoped to YAML-validity; runtime green is observed as the PR check.

## TDD Gate Compliance
Task 1 is `tdd="true"`. A CI bash guard has no natural pytest harness; the plan's `<acceptance_criteria>` defines the RED/GREEN equivalent as the inject→exit-1 / clean→exit-0 smoke check, which was executed and passed (see Acceptance Evidence). No standalone `test(...)` commit was created because there is no committable test artifact for a shell guard — the guard *is* the verification surface and its behavior was proven empirically before the commit. The phase-level `type: execute` (not `type: tdd`) means the plan-level RED/GREEN/REFACTOR commit-gate sequence does not apply.

## Decisions Made
See `key-decisions` in frontmatter. Summary: the localhost guard uses a 4-class allow-list across both roots (the most robust of the plan's offered narrowings), the E2E runs under `ENVIRONMENT=staging` via a per-exec override (compose anchor hardcodes `dev`), and YAML verification reused the backend uv venv's bundled PyYAML to avoid any install.

## Deviations from Plan

None — plan executed exactly as written.

The guard-narrowing (allow-listing intentional `localhost` idioms) was **explicitly directed** by the plan's `<acceptance_criteria>` "NOTE FOR EXECUTOR" (11-01-PLAN lines 111–119), which anticipated the clean-tree `|| "http://localhost:8000"` fallbacks and the `FRONTEND_BASE_URL` default and instructed narrowing the guard rather than editing app code. This is planned work, not a Rule 1–4 deviation. No app source, no backend tests, and none of the three existing CI workflows were modified.

## Issues Encountered
- **PyYAML absent from the base interpreter** (the Task 2 `<verify>` needs `import yaml`). Resolved without any install by running the exact verify command through the backend uv venv (`cd backend && uv run python -c ...`), which ships PyYAML 6.0.3 transitively. This honors the RULE 3 exclusion against auto package-manager installs and adds nothing to the dependency tree.
- **Compose `x-backend-env` anchor hardcodes `ENVIRONMENT: dev`** for backend/worker/beat/flower (it is dev-only infra). The generated `.env`'s `ENVIRONMENT=staging` therefore does not win for those services. Handled by passing `-e ENVIRONMENT=staging` on the E2E `docker compose exec` step so the bet→settle path is exercised under staging env; the `.env` still supplies `SECRET_KEY` / `ADMIN_JWT_PUBLIC_SECRET`. Documented as the plan permitted (functional path is load-bearing; staging-env assertion is per-exec).
- **Windows + `core.autocrlf=true`:** both new files are covered by `.gitattributes` (`*.sh text eol=lf`, `*.yml text eol=lf`) and were written LF-only (verified) so the bash script and workflow parse correctly on the Linux runner.

## User Setup Required
None - no external service configuration required. (The dry-run runs entirely in CI; SC#4 security-tool installs and SC#5 Sentry DSN are other plans' concerns.)

## Next Phase Readiness
- SC#3 deliverables are in place and locally green; the workflow will execute on the phase PR (full stack boot + E2E + guard) as the observable phase-gate check.
- 11-06 ("Looks Done But Isn't" audit) can cite this plan's guard + dry-run as the SC#3 evidence row.
- No blockers introduced. Plan 11-01 of 6 complete.

## Self-Check: PASSED

---
*Phase: 11-hardening-operator-demo-gate*
*Completed: 2026-06-02*
