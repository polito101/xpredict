---
phase: 11-hardening-operator-demo-gate
plan: 02
subsystem: infra
tags: [ci, github-actions, security, sast, dast, bandit, pip-audit, pnpm-audit, owasp-zap]

# Dependency graph
requires:
  - phase: 01-scaffold-foundations
    provides: backend-ci.yml / frontend-ci.yml CI conventions (checkout@v4, setup-python@v5, uv sync --frozen, pnpm/action-setup@v4 9.15.0, setup-node@v4), docker-compose.yml (8 healthchecked services), .gitattributes LF policy
  - phase: 11-hardening-operator-demo-gate
    provides: 11-01 prod-migration-dry-run.yml established the ephemeral staging-.env + compose-up/down CI pattern this plan's ZAP job mirrors
provides:
  - ".github/workflows/security-scan.yml — SC#4 four-scanner gate (bandit + pip-audit + pnpm audit + OWASP ZAP baseline), each HIGH-only"
  - ".zap/rules.tsv — ZAP baseline rule-action file (HIGH-only gate; IGNORE non-actionable passive alerts; documents /bets/* authenticated-DAST v2 deferral)"
  - "backend dev dependency group now carries bandit 1.9.4 + pip-audit 2.10.0 (CI/dev SAST + dependency-CVE tooling; NOT runtime)"
affects: [11-06 (Looks-Done audit cites this as SC#4 evidence), operator-demo-gate]

# Tech tracking
tech-stack:
  added:
    - "bandit==1.9.4 (backend dev group — Python SAST)"
    - "pip-audit==2.10.0 (backend dev group — Python dependency CVE audit)"
    - "zaproxy/action-baseline@v0.14.0 (GitHub Action — OWASP ZAP passive DAST; runs in-container, no repo install)"
  patterns:
    - "New security-scan workflow mirrors backend-ci/frontend-ci conventions (trigger shape, permissions: contents: read, timeout-minutes, pinned actions) rather than mutating existing CI"
    - "Four INDEPENDENT jobs so one scanner failing is isolated from the others"
    - "Every scanner HIGH-gated: bandit --severity-level high, pnpm audit --audit-level high, ZAP via .zap/rules.tsv IGNORE list; pip-audit (no severity flag) ignores known non-HIGH transitives via --ignore-vuln"

key-files:
  created:
    - .github/workflows/security-scan.yml
    - .zap/rules.tsv
  modified:
    - backend/pyproject.toml
    - backend/uv.lock

key-decisions:
  - "Task 1 (package-legitimacy human-verify gate) APPROVED BY OPERATOR (Pol/Agustin) before any install — confirmed pins: bandit 1.9.4, pip-audit 2.10.0, zaproxy/action-baseline v0.14.0. The three [ASSUMED] tools (slopcheck was unavailable at research time) are cleared as legitimate; no install ran before approval."
  - "pip-audit has NO severity-threshold flag (exits non-zero on ANY advisory). A live audit of the backend lockfile surfaced 4 known non-HIGH transitive advisories (starlette x3 via fastapi, pytest x1 dev-only) whose fixes lie OUTSIDE the existing dependency pins (fastapi>=0.115.7,<0.116.0; pytest<9.0). To honor the HIGH-only gate (constraint 4) without breaking the green base and without out-of-scope dependency churn (constraint 1), those 4 IDs are suppressed via --ignore-vuln (PYSEC-2026-161, CVE-2025-54121, CVE-2025-62727, CVE-2025-71176). The job then gates on NEW/actionable CVEs only. Documented in-workflow with a re-audit-on-pin-bump note."
  - "bandit + pip-audit added to [dependency-groups] dev ONLY (mirroring ruff/mypy/pytest); never to runtime [project] dependencies. uv.lock delta is purely additive (239 insertions, 0 deletions — no runtime dep churn)."
  - "ZAP job mirrors 11-01's ephemeral staging-.env pattern (ENVIRONMENT=staging + placeholder SECRET_KEY/ADMIN_JWT_PUBLIC_SECRET + empty SENTRY_DSN, written in-job, never echoed, gitignored). NO services: block — compose owns Postgres/Redis (Pitfall 4)."
  - "YAML-validity verified through the backend uv venv's bundled PyYAML (the base interpreter lacks it) — no new package installed, honoring the RULE 3 package-install exclusion. The plan's `python -c \"import yaml\"` verify is the same approach 11-01 used."

patterns-established:
  - "Security-scan gate: four isolated HIGH-only scanner jobs; bandit/pnpm/ZAP fail only on HIGH, pip-audit ignores known non-HIGH transitives so it catches new CVEs without a day-one red"
  - "ZAP baseline .zap/rules.tsv seed: IGNORE the informational passive alerts a JSON-API baseline always emits; tune against the first real scan; authenticated /bets/* DAST is a documented v2 deferral"

requirements-completed: [PLT-07]

# Metrics
duration: ~18min
completed: 2026-06-02
---

# Phase 11 Plan 02: security-scan CI (SC#4 — bandit + pip-audit + pnpm audit + OWASP ZAP, HIGH-only) Summary

**A new `security-scan` GitHub Actions workflow running four independent, HIGH-severity-gated scanners — bandit (Python SAST), pip-audit (backend dependency CVEs), pnpm audit (frontend dependency CVEs), and OWASP ZAP passive baseline DAST against the booted API's `/auth/*` + public market surface — plus a `.zap/rules.tsv` HIGH-only suppression file, with bandit + pip-audit added to the backend DEV dependency group only. The three existing CI workflows and the backend test suite are untouched.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-02T12:56:46Z (after 11-01 close)
- **Completed:** 2026-06-02
- **Tasks:** 4 (Task 1 = operator-approved checkpoint; Tasks 2-4 = auto)
- **Files:** 4 (2 created, 2 modified)

## Task 1 — Package-legitimacy checkpoint: APPROVED BY OPERATOR

Task 1 is the `checkpoint:human-verify gate="blocking-human"` package-legitimacy gate. It existed because `slopcheck` was unavailable at research time, so the three tools were tagged `[ASSUMED]`. **The operator (Pol/Agustin) approved this gate before execution**, confirming all three as legitimate with their pins:

| Tool | Pin | Source | Verdict |
|------|-----|--------|---------|
| bandit | 1.9.4 | PyPI / github.com/PyCQA/bandit | APPROVED |
| pip-audit | 2.10.0 | PyPI / github.com/pypa/pip-audit | APPROVED |
| zaproxy/action-baseline | v0.14.0 | github.com/zaproxy/action-baseline (OWASP) | APPROVED |

No tool was installed or referenced before this approval. Threat **T-11-02-SC (Tampering — supply chain)** is mitigated: the blocking human gate confirmed each `[ASSUMED]` tool on its registry and pinned the version before first use.

## Accomplishments

- **bandit 1.9.4 + pip-audit 2.10.0** added to `backend/pyproject.toml` `[dependency-groups] dev` (never runtime); `uv.lock` regenerated additively (239 insertions, 0 deletions).
- **`.zap/rules.tsv`** — 20 TAB-separated `IGNORE` rows suppressing the non-actionable informational passive alerts a JSON-API baseline always emits (header/cache/CSP/timestamp/cookie-scope informational rules), a header comment block documenting the HIGH-only intent, and the explicit **`/bets/*` authenticated-DAST v2 deferral** (Pitfall 3 / RESEARCH A4).
- **`.github/workflows/security-scan.yml`** — `pull_request` + `push:main`, `permissions: contents: read`, four independent jobs:
  - **bandit** (timeout 15): checkout@v4 → setup-python@v5 3.12 → `pip install uv` → `uv sync --frozen` → `uv run bandit -r app/ --severity-level high` (FAIL only on HIGH).
  - **pip-audit** (timeout 15): same python/uv setup → `uv run pip-audit --ignore-vuln …` (4 known non-HIGH transitives suppressed; gates on new CVEs).
  - **pnpm-audit** (timeout 15): checkout@v4 → `pnpm/action-setup@v4` 9.15.0 → setup-node@v4 node 20 + pnpm cache → `pnpm install --frozen-lockfile` → `pnpm audit --audit-level high` (FAIL only on HIGH).
  - **zap-baseline** (timeout 20): checkout@v4 → write ephemeral staging `.env` (never logged) → `docker compose up -d --wait` → `zaproxy/action-baseline@v0.14.0` (target `http://localhost:8000`, `rules_file_name .zap/rules.tsv`, `cmd_options -a`, `allow_issue_writing false`, `fail_action true`) → `if: always()` `docker compose down -v`. NO `services:` block (Pitfall 4).
- The three existing CI workflows (`backend-ci.yml` / `frontend-ci.yml` / `security.yml`) are **byte-identical** to their pre-plan state (`git diff --stat` empty — constraint 4). The backend tests / wallet suite were NOT touched (constraint 3); this plan is fully separate from PR #16 (constraint, CONTEXT 3-4).

## Task Commits

Each auto task committed atomically:

1. **Task 2: bandit + pip-audit in backend dev group** — `b33dd72` (chore)
2. **Task 3: `.zap/rules.tsv` HIGH-only gate** — `d5b7634` (feat)
3. **Task 4: `security-scan.yml` four-scanner workflow** — `6dfd049` (feat)

**Plan metadata** (this SUMMARY + STATE + ROADMAP) — committed separately as the `docs(11-02)` closeout.

## Files Created/Modified

- `backend/pyproject.toml` (modified) — `bandit==1.9.4` + `pip-audit==2.10.0` appended to `[dependency-groups] dev`.
- `backend/uv.lock` (modified) — additive dev-group lock entries only (239 insertions, 0 deletions).
- `.zap/rules.tsv` (created) — 42 lines; 20 TAB-separated `IGNORE` data rows + comment header documenting HIGH-only intent + v2 `/bets/*` deferral.
- `.github/workflows/security-scan.yml` (created) — 169 lines; four HIGH-only scanner jobs; all actions pinned; no `services:` block.

## Acceptance Evidence

### Task 2 — bandit + pip-audit in dev group
- `<verify>` `uv run bandit --version` → `bandit 1.9.4` **exit=0** ✅ ; `uv run pip-audit --version` → `pip-audit 2.10.0` **exit=0** ✅
- `bandit` + `pip-audit` present under `[dependency-groups] dev` ✅
- `bandit`/`pip-audit` ABSENT from runtime `[project] dependencies` (verified via parser) ✅
- `git diff --numstat backend/uv.lock` → `239  0` (additive only, no runtime dep churn) ✅
- **Live smoke:** `uv run bandit -r app/ --severity-level high` → **No issues identified. High: 0** (2 Low + 1 Medium correctly ignored), **exit=0** — the HIGH gate is green on the real `backend/app` ✅

### Task 3 — `.zap/rules.tsv`
- `<verify>` `test -f .zap/rules.tsv && grep -cP '\t'` → **21** TAB-containing rows (≥1) ✅ (run with `LC_ALL=C.UTF-8`; the GH runner is UTF-8 by default)
- 20 data rows, every action token ∈ {WARN, IGNORE, FAIL} (all `IGNORE`) — validated programmatically ✅
- v2 `/bets/*` authenticated-DAST deferral comment present ✅ ; comment header present ✅
- must_haves `min_lines: 5` → 42 lines ✅

### Task 4 — `.github/workflows/security-scan.yml`
- `<verify>` `python -c "import yaml; … print('jobs:', sorted(d['jobs'].keys()))"` (via backend uv venv) → `jobs: ['bandit', 'pip-audit', 'pnpm-audit', 'zap-baseline']` **exit=0** ✅
- `grep -c 'severity-level high'` = 2 (≥1; bandit run + the pip-audit design comment) ✅
- `grep -c 'audit-level high'` = 1 (≥1) ✅
- `grep -c 'rules_file_name'` = 1, value = `.zap/rules.tsv` ✅
- ZAP action ref = `zaproxy/action-baseline@v0.14.0` (the Task-1 approved pin) ✅
- NO top-level `services:` block: `grep -cE '^services:'` = 0 (Pitfall 4) ✅
- `bandit -r app/` present (key_link) ✅
- `git diff --stat` on the three existing CI workflows = empty (constraint 4) ✅
- **Live smoke (pip-audit):** plain `uv run pip-audit` → 4 advisories, exit=1; with the 4 `--ignore-vuln` flags → `No known vulnerabilities found, 4 ignored`, **exit=0** — the job is green on the current lockfile ✅

> The bandit/pnpm/pip-audit scans and the full ZAP stack-boot run on the GitHub Actions runner (the workflow's own jobs require Docker + the compose stack for ZAP). The local `<verify>` is scoped to tool resolution + YAML validity + the HIGH-gate smoke; runtime green is observed as the PR checks.

## Hard-Constraint Compliance

- **Constraint 1 (no features/refactors; dev-group only):** bandit + pip-audit live in the DEV group, not runtime. No app code touched. ✅
- **Constraint 2 (don't modify existing CI):** `backend-ci.yml` / `frontend-ci.yml` / `security.yml` byte-identical (empty `git diff --stat`). New scanning lives only in the new `security-scan.yml`. ✅
- **Constraint 3 (don't touch backend tests / wallet suite / PR #16):** zero changes under `backend/tests`; no wallet/concurrency code touched; fully separate from PR #16. ✅
- **Constraint 4 (HIGH-only gating):** bandit `--severity-level high`, pnpm `--audit-level high`, ZAP `.zap/rules.tsv` IGNORE list; pip-audit (no native severity flag) ignores known non-HIGH transitives so it gates on new CVEs. ZAP = baseline only (`zaproxy/action-baseline`), public + `/auth/*`; `/bets/*` authenticated DAST deferred to v2. ✅
- **Constraint 5 (commit pyproject + uv.lock together):** both committed in `b33dd72`; the `uv.lock` delta is dev-group-additive so the existing `backend-ci` `uv sync --frozen` stays consistent (it installs dev deps — backend-ci.yml unchanged). ✅

## Threat-Model Compliance
- **T-11-02-SC (Tampering, supply chain):** mitigated — operator-approved blocking checkpoint confirmed each `[ASSUMED]` tool + pinned version before first use.
- **T-11-02-01 (Info Disclosure, false-negative coverage):** accepted — ZAP baseline is passive/unauthenticated; `/auth/*` (the high-value unauthenticated surface) is covered; `/bets/*` authenticated DAST is the documented v2 deferral.
- **T-11-02-02 (Info Disclosure, ZAP `.env` in CI logs):** mitigated — `.env` heredoc-generated in-job, never echoed, gitignored (`git check-ignore .env` confirms), throwaway placeholders only.
- **T-11-02-03 (DoS, scanners breaking the green base on non-HIGH noise):** mitigated — every gate HIGH-only; pip-audit's known non-HIGH transitives suppressed; bandit/pnpm/ZAP HIGH-gated. Live smokes prove bandit + pip-audit are green now.
- **T-11-02-04 (Tampering, SQLi / passive web vulns):** mitigated — bandit SAST over `backend/app` (0 HIGH) + ZAP baseline over the booted API surface the standard SQLi / header issues for triage.

## Deviations from Plan

**1. [Rule 3 — Blocking issue, plan-anticipated] pip-audit `--ignore-vuln` for 4 known non-HIGH transitive advisories**
- **Found during:** Task 4 (live pip-audit smoke against the real backend lockfile).
- **Issue:** Plain `uv run pip-audit` exits non-zero (it has no severity-threshold flag) on 4 known advisories — `starlette` x3 (`PYSEC-2026-161`, `CVE-2025-54121`, `CVE-2025-62727`, transitive via `fastapi[standard]`) and `pytest` x1 (`CVE-2025-71176`, DEV-only). Their fixes (starlette 0.47.2/0.49.1/1.0.1; pytest 9.0.3) lie OUTSIDE the existing pins (`fastapi>=0.115.7,<0.116.0`, `pytest<9.0`). As literally written the job would be **red on day one** — violating constraint 4 (HIGH-only, keep the green base) and the plan's own Anti-Pattern. Remediating by bumping pins is out-of-scope dependency churn (constraint 1).
- **Fix:** Suppressed the 4 IDs via `--ignore-vuln` with a documented in-workflow rationale + a re-audit-on-pin-bump note, so the gate catches NEW/actionable CVEs without a day-one red. This is **exactly what the plan's Task 4 directed**: *"If pip-audit's default exit-on-any-finding is too noisy, scope it with the documented ignore flags so it gates on actionable CVEs; document the exact flag choice in the SUMMARY."*
- **Files modified:** `.github/workflows/security-scan.yml` (Task 4 commit).
- **Commit:** `6dfd049`
- **Verification:** `uv run pip-audit --ignore-vuln …` → `No known vulnerabilities found, 4 ignored`, exit=0.

**2. [Tooling, environment] `grep -P` / `import yaml` unavailable in the base shell — verified via supported fallbacks**
- The plan's `grep -cP '\t'` fails under this Windows Git-Bash's default locale; re-run with `LC_ALL=C.UTF-8` it returns 21 (the GH runner is UTF-8 native, so the plan's command works there unchanged). The `python -c "import yaml"` verify needs PyYAML, absent from the base interpreter; run through the backend uv venv (bundled PyYAML) per the same approach 11-01 used — honoring the RULE 3 package-install exclusion (no new install). Not a code deviation; verification-method only.

No app source, no backend tests, and none of the three existing CI workflows were modified.

## Known Stubs
None. No placeholder data, empty-array UI sinks, or "coming soon" text introduced — this plan ships CI configuration + a dev-dependency add only.

## Issues Encountered
- **YAML `name:` colon-space parse error** — the first draft of `security-scan.yml` had a step name `Boot stack (compose owns db/redis — no services: block)`; the unquoted `: ` in `services: block` is parsed by YAML as a mapping separator (`ScannerError: mapping values are not allowed here`, line 141). Fixed by rewording to `… no services block` (no colon). Re-parse confirmed valid YAML with the four jobs.
- **pip-audit day-one red** (covered as Deviation 1) — resolved via documented `--ignore-vuln`.

## User Setup Required
None — the scanners run entirely in CI. No secret KEY names enter the codebase (the ZAP job's staging `.env` is CI-ephemeral placeholders). The bandit/pip-audit dev deps install via the existing `uv sync --frozen`.

## Next Phase Readiness
- SC#4 deliverables are in place and locally green (bandit HIGH gate clean; pip-audit clean with the documented ignore-list; YAML valid; rules file well-formed). The four jobs execute on the phase PR as the observable phase-gate check.
- 11-06 ("Looks Done But Isn't" audit) can cite this plan's `security-scan.yml` + the bandit/pip-audit HIGH-gate smokes as the SC#4 evidence row.
- No blockers introduced. Plan 11-02 of 6 complete.

## Self-Check: PASSED

All 5 files verified present on disk (`security-scan.yml`, `.zap/rules.tsv`, `pyproject.toml`, `uv.lock`, `11-02-SUMMARY.md`) and all 3 task commits resolve in `git log` (`b33dd72`, `d5b7634`, `6dfd049`).

---
*Phase: 11-hardening-operator-demo-gate*
*Completed: 2026-06-02*
