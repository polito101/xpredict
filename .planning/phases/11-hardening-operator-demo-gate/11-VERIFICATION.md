---
phase: 11-hardening-operator-demo-gate
verified: 2026-06-02T16:10:00Z
status: human_needed
score: 7/7 must-haves verified (5 fully closed + 2 code/doc-complete, awaiting documented live-runtime human-verify)
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: none
  note: "Initial verification (no prior 11-VERIFICATION.md)."
human_verification:
  - test: "Sentry alert round-trip (SC#5, plan 11-03) — DEFERRED-1 per docs/DEFERRED-MANUAL-GATES.md"
    expected: "Define the 4 alert rules in the Sentry UI per docs/runbooks/sentry-alerts.md §3, run the 4 synthetic triggers (§4) against xpredict-staging with the real SENTRY_DSN, confirm each event + alert lands in the configured channel (Slack #general or email), and fill the §5 sign-off table."
    why_human: "Sentry is external SaaS; alert delivery cannot be asserted in CI without a live staging DSN. Same precedent as Phase 1 PLT-08. The 4 in-code emit sites already exist and are verified; the runbook (208 lines, 4 fully-specified rules) shipped. Only the live round-trip remains. Owner: Pol."
  - test: "Responsive visual QA 360-768px (SC#1 / PLT-07, plan 11-05) — DEFERRED-2 per docs/DEFERRED-MANUAL-GATES.md"
    expected: "Run the frontend (dev server or CI preview) and check home / market-detail / bet flow / portfolio / wallet / auth at 360 / 390 / 414 / 768px — no horizontal scroll on any surface at any width, all controls thumb-reachable and text readable. Record pass, or list surface+width+issue for a CSS-only follow-up."
    why_human: "Responsive correctness is inherently visual and cannot be unit-asserted. Local `pnpm build` is environmentally broken in the deep Windows worktree (DEF-FE-BUILD-01 — reproduces on pristine HEAD; real CI builds fine), so a stable preview/dev runtime is needed for the human visual pass. The CSS/layout-only fixes shipped and `pnpm typecheck` is green (verified). Owner: Pol / operator."
---

# Phase 11: Hardening & Operator-Demo Gate — Verification Report

**Phase Goal:** Final gate before any operator demo: validate mobile responsiveness end-to-end, tune rate limits and Sentry alert rules against realistic load, execute the "Looks Done But Isn't" checklist from PITFALLS.md, run prod-migration dry-run and security scan, and ship the regulatory ToS posture review.
**Requirement:** PLT-07 (Player-facing UI is fully responsive on mobile browsers ≥360px; admin desktop-only acceptable).
**Verified:** 2026-06-02T16:10:00Z
**Status:** human_needed
**Re-verification:** No — initial verification.
**Mode note:** Phase 11 is tagged `mode: mvp` in ROADMAP.md, but its goal is a hardening-gate goal, NOT a User Story ("As a … I want … so that …"). MVP user-flow-coverage verification does not apply; standard goal-backward verification against the 6 success criteria + PLT-07 is used (per GSD MVP-mode rule: the user-flow table only applies when the phase goal IS a user story).

## Gate Resolution Context (operator decision 2026-06-02)

Per `docs/DEFERRED-MANUAL-GATES.md`, the 4 Phase-11 human gates resolved as:

| Gate | Plan / SC | Decision | Scored here as |
|------|-----------|----------|----------------|
| Regulatory scaffold ack | 11-04 / SC#6 | CLOSED (approved) | VERIFIED |
| "Looks Done But Isn't" sign-off | 11-06 / SC#2 | CLOSED (signed off) | VERIFIED |
| Sentry alert round-trip | 11-03 / SC#5 | DEFERRED (documented manual-verify) | VERIFIED (code/doc-complete) + `human_needed` item |
| Responsive visual QA | 11-05 / SC#1 / PLT-07 | DEFERRED (documented manual-verify) | VERIFIED (code/doc-complete) + `human_needed` item |

The two deferrals are **legitimate documented deferrals** (same precedent as Phase 1 PLT-08): all code/doc deliverables shipped; only the live-runtime human check remains. They are scored as `human_needed`, **NOT** `gaps_found`.

## Goal Achievement

### Observable Truths (the 6 ROADMAP Success Criteria + PLT-07)

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| SC#1 / PLT-07 | Player UI passes responsive QA 360–768px (home, market detail, bet flow, portfolio, wallet, auth) — no horizontal scroll, thumb-reachable | ✓ VERIFIED (code-complete) + ⏸ human-verify | CSS/layout-only fixes shipped (`dac111e`): `git diff origin/main` on wallet/portfolio/market-detail/market-card = **4 files, 18 ins / 16 del, EVERY hunk a Tailwind className change** (canonical idioms: `min-w-0`, `truncate`, `flex-wrap`, `shrink-0`, `whitespace-nowrap`, `px-4 sm:px-6`). No prop/import/data-flow change. `pnpm typecheck` (tsc --noEmit) → **exit 0** (re-run by verifier). Live visual pass = DEFERRED-2 (human item below). |
| SC#2 | "Looks Done But Isn't" checklist executed in full; every box ticked or documented/approved deferral | ✓ VERIFIED | `docs/LOOKS-DONE-CHECKLIST.md` (110 lines, `df0038d`): all **32** PITFALLS items, each with a non-blank Result + concrete evidence (17 VERIFIED, 6 CLOSED-BY-PHASE-11, 6 VERIFY-ONLY Pol track, 4 DEFERRED w/ owner). Verifier independently confirmed cited evidence is real: `reconcile.py`, `test_concurrent_transfers.py`, `test_audit_immutability.py` all exist; `CHECK (balance >= 0)` in migration `0004`; CORS `allow_origins=[settings.FRONTEND_BASE_URL]` (not `*`). Sign-off CLOSED per gate resolution. |
| SC#3 | `prod-migration-dry-run` CI: staging-style boot + bet→settle E2E; fails on hardcoded dev URLs / DEBUG | ✓ VERIFIED | `.github/workflows/prod-migration-dry-run.yml` (`d244962`) + `bin/check_no_dev_config.sh` (`1e1a39d`, 90 lines). Valid YAML (verifier re-validated). Workflow: ephemeral staging `.env` → `docker compose up -d --wait` (8 healthchecks) → `alembic upgrade head` → reused Phase-5 `test_phase5_e2e.py` under `ENVIRONMENT=staging` → guard → `down -v`. Verifier ran the guard on the real tree: clean → **exit 0**; the SUMMARY's inject→exit-1 smokes documented. |
| SC#4 | Security scan: gitleaks + bandit (no HIGH) + npm/pnpm audit (no HIGH) + OWASP ZAP baseline (no HIGH) | ✓ VERIFIED | `.github/workflows/security-scan.yml` (`6dfd049`, 4 jobs) + `.zap/rules.tsv` (`d5b7634`, 42 lines / 23 IGNORE = HIGH-only) + bandit/pip-audit in backend DEV group (`b33dd72`). Valid YAML (re-validated). Verifier ran **bandit -r app/ --severity-level high → High: 0, exit 0**. gitleaks already 3-tier green (Phase 1); not re-added. ZAP baseline targets `/auth/*` + public market routes; authenticated `/bets/*` DAST = documented v2 deferral. |
| SC#5 | Sentry alert rules configured + synthetically triggered for 4 scenarios (settlement, Polymarket spike, reconciliation drift, auth abuse); each lands in notification channel | ✓ VERIFIED (code/doc-complete) + ⏸ human-verify | `docs/runbooks/sentry-alerts.md` (208 lines, `3fcdcc5`): 4 fully-specified rules (dataset/filter/aggregate/threshold/channel) + 4 synthetic-trigger procedures + blank sign-off table. Verifier confirmed the 4 emit sites are real: `reconcile_wallets` task in `reconcile.py`, `task_failure→capture_exception`, Polymarket `capture_exception`, the 429 path. Live round-trip vs real DSN = DEFERRED-1 (human item below). Closes the Phase-1 PLT-08 alert-rule deferral. |
| SC#6 | Counsel-reviewable ToS + token policy linked in player + admin footers; `docs/regulatory.md` posture + operator-agreement template checked in | ✓ VERIFIED | `docs/regulatory.md` (70 lines) + `docs/terms-of-service.md` + `docs/operator-agreement.md` (7 commitments as headers) — all scaffold-only with bracketed `[COUNSEL REVIEW REQUIRED]` / `[PLACEHOLDER]` / `[TEMPLATE]` / `[DEFERRED: external counsel]` notes (commit `89c6472`); the only concrete claim is the WAL-09-matching token-value characterization (engineering fact). Footer links to ToS + token-policy in BOTH player + admin layouts (`76c8806`, +39 markup-only). Scaffold ack CLOSED per gate resolution; Spanish-counsel review is the documented external dependency. |

**Score:** 7/7 truths verified at the code/doc-deliverable level (SC#1 = PLT-07). 5 fully closed; SC#1 and SC#5 are code/doc-complete with documented live-runtime human-verify remaining (the two operator-approved deferrals).

### Required Artifacts (all 12 — three-level check via gsd-sdk verify.artifacts + verifier read)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bin/check_no_dev_config.sh` | dev-config guard, allow-listed, ≥20 lines, contains ENVIRONMENT | ✓ VERIFIED | 90 lines; runs clean on real tree (exit 0); 4-class allow-list documented; wired into dry-run workflow. |
| `.github/workflows/prod-migration-dry-run.yml` | SC#3 boot + E2E + guard; contains ENVIRONMENT=staging | ✓ VERIFIED | Valid YAML; references `test_phase5_e2e.py` + `check_no_dev_config`; no `services:` block (Pitfall 4). |
| `.github/workflows/security-scan.yml` | SC#4 4 scanners HIGH-only; contains severity-level high | ✓ VERIFIED | Valid YAML; 4 jobs (bandit/pip-audit/pnpm-audit/zap-baseline); bandit HIGH gate green (re-run). |
| `.zap/rules.tsv` | ZAP HIGH-only gate, ≥5 lines | ✓ VERIFIED | 42 lines, 23 IGNORE rows; `/bets/*` v2 deferral documented; wired via `rules_file_name`. |
| `backend/pyproject.toml` | bandit + pip-audit in DEV group, not runtime | ✓ VERIFIED | bandit 1.9.4 + pip-audit 2.10.0 in `[dependency-groups] dev`; uv.lock additive (239 ins / 0 del). |
| `docs/runbooks/sentry-alerts.md` | SC#5 4 rules + triggers + sign-off, ≥60 lines, contains reconcile_wallets | ✓ VERIFIED | 208 lines; 4 rules; emit sites map to real code; sign-off table present (blank = the manual gate). |
| `docs/regulatory.md` | SC#6 skeleton + counsel notes, ≥30 lines, contains "Counsel review" | ✓ VERIFIED | 70 lines; all legal claims bracketed; references PITFALLS (not re-authored). Scaffold-only per constraint 2. |
| `docs/terms-of-service.md` | ToS placeholder, contains PLACEHOLDER | ✓ VERIFIED | NOT-LEGALLY-REVIEWED banner + `[PLACEHOLDER]` sections; only concrete = WAL-09 token-value assertion. |
| `docs/operator-agreement.md` | operator-agreement stub, contains operator | ✓ VERIFIED | 7 operator commitments as `## 1.`–`## 7.` headers + signature block; all `[TEMPLATE — counsel to finalize]`. |
| `frontend/src/app/wallet/page.tsx` | responsive (no overflow 360px), contains sm: | ✓ VERIFIED | `px-4 sm:px-6` + `min-w-0`/`truncate`/`shrink-0`/`whitespace-nowrap` on tx rows. className-only diff. |
| `frontend/src/app/portfolio/page.tsx` | responsive cards, contains sm: | ✓ VERIFIED | `px-4 sm:px-6` + `flex-wrap`/`min-w-0` on P&L rows. className-only diff. |
| `docs/LOOKS-DONE-CHECKLIST.md` | SC#2 executed audit, ≥50 lines, contains VERIFY | ✓ VERIFIED | 110 lines; 32 audit rows; cites all Phase-11 workstreams; wallet rows verify-only. |

`gsd-sdk verify.artifacts` → **12/12 passed** across all 6 plans (existence + substantive pattern/min-line checks). Verifier additionally read all 12 and confirmed substance (not hollow).

### Key Link Verification (all 11 — gsd-sdk verify.key-links + verifier spot-check)

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| prod-migration-dry-run.yml | test_phase5_e2e.py | docker compose exec pytest | ✓ WIRED | Pattern in source; target test file exists. |
| prod-migration-dry-run.yml | check_no_dev_config.sh | bash invocation | ✓ WIRED | Pattern in source; guard runs (exit 0). |
| security-scan.yml | backend/app | bandit -r app/ --severity-level high | ✓ WIRED | Pattern in source; bandit re-run green. |
| security-scan.yml | .zap/rules.tsv | rules_file_name | ✓ WIRED | Pattern in source; rules file present. |
| sentry-alerts.md | reconcile.py | reconciliation-drift trigger | ✓ WIRED | `reconcile_wallets` task exists in target. |
| sentry-alerts.md | sentry-test/route.ts | error synthetic trigger | ✓ WIRED | `/api/sentry-test` route exists. |
| layout.tsx (player) | terms-of-service.md | footer link | ✓ WIRED | `<footer>` + ToS + token-policy links (verified diff). |
| admin/layout.tsx | terms-of-service.md | admin footer link | ✓ WIRED | `<footer>` + ToS + token-policy links (verified diff). |
| page.tsx | market-list.tsx | responsive market grid | ✓ WIRED | `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` in target. |
| LOOKS-DONE-CHECKLIST.md | prod-migration-dry-run.yml | dry-run evidence citation | ✓ WIRED | Cited 2×. |
| LOOKS-DONE-CHECKLIST.md | security-scan.yml | security-scan evidence citation | ✓ WIRED | Cited 6×. |

`gsd-sdk verify.key-links` → **11/11 verified** across all 6 plans.

### Behavioral Spot-Checks (verifier-run, not SUMMARY claims)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Dev-config guard clean on real tree | `bash bin/check_no_dev_config.sh` | `OK: no hardcoded localhost / ENVIRONMENT=dev …` exit 0 | ✓ PASS |
| Bandit HIGH gate on real backend | `uv run bandit -r app/ --severity-level high` | `No issues identified. High: 0` exit 0 | ✓ PASS |
| Frontend compiles with all Phase-11 edits | `pnpm typecheck` (tsc --noEmit) | exit 0 | ✓ PASS |
| Both new workflows are valid YAML | `yaml.safe_load(...)` (via backend uv venv) | `both-yaml-ok` | ✓ PASS |
| All 10 SUMMARY commit hashes resolve | `git log -1 --format=%s <hash>` ×10 | all 10 resolve with stated messages | ✓ PASS |
| Live mobile-browser responsive pass | (needs preview runtime) | n/a | ? SKIP → human (DEFERRED-2) |
| Sentry alert live round-trip | (needs staging DSN) | n/a | ? SKIP → human (DEFERRED-1) |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` and no probe markers declared in the Phase-11 PLANs/SUMMARYs. The phase's runnable verification surfaces (the 2 CI workflows + the bash guard) execute on the GitHub Actions PR run by design and were verified by artifact correctness + the in-process spot-checks above (guard exit-0, bandit exit-0, YAML-valid). N/A — no probes to run.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| PLT-07 | 11-01 … 11-06 (all declare `requirements: [PLT-07]`) | Player-facing UI fully responsive ≥360px; admin desktop-only acceptable | ✓ SATISFIED (code-complete) + ⏸ human-verify | SC#1 CSS deliverables shipped + typecheck-green; SC#2–6 hardening/CI/observability/regulatory deliverables all present + correct. The literal responsive-at-360px assertion's final live visual confirmation = DEFERRED-2. No other Phase-11 requirements; REQUIREMENTS.md maps only PLT-07 to Phase 11 (no orphans). |

No ORPHANED requirements: REQUIREMENTS.md §"11 — Hardening & Operator-Demo Gate | 1 | PLT-07" matches the plans' declared coverage exactly.

### Data-Flow Trace (Level 4)

N/A for the rendering sense — Phase 11 ships NO new dynamic-data UI (CONTEXT constraint 1: CI / observability / docs / CSS only). The CSS edits adjust Tailwind classes on already-wired Phase 3/9 surfaces (no new fetch/state); the footers are static links; the docs are static. No artifact in this phase introduces a data variable that could be hollow. The closest data-flow surfaces (Sentry emit sites, the dry-run E2E, the reconcile task) are pre-existing and were confirmed to exist as real code, not stubs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No `TBD`/`FIXME`/`XXX` debt markers in any of the 9 Phase-11 deliverables | — | Clean — completion is auditable. |

Note on scaffold markers: the `[PLACEHOLDER]` / `[TEMPLATE — counsel to finalize]` / `[DEFERRED: external counsel]` brackets in the 3 legal docs are **intentional, required scaffold markers** per SC#6 + CONTEXT constraint 2 (legal = structure + notes only). Each is tied to the formal "counsel review" external dependency (the documented follow-up). They are NOT unreferenced debt markers and do NOT trigger the debt-marker gate.

### Hard-Constraint Compliance (CONTEXT decisions 1–5)

| Constraint | Status | Evidence |
|------------|--------|----------|
| 1. No new features / refactors / architecture — hardening/CI/observability/scaffold only | ✓ HELD | CSS diff = className-only (verified hunk-by-hunk); footers = additive markup (+39, 0 del); legal = scaffold-only; security deps in DEV group only. No app logic/route/prop/data change. |
| 2. Legal/ToS = structure + base + notes only (no authored prose) | ✓ HELD | All 3 legal docs are bracketed `[COUNSEL/PLACEHOLDER/TEMPLATE/DEFERRED]` scaffolds; only concrete claim = WAL-09 token-value fact. Counsel review = documented external dependency. |
| 3. Backend tests / wallet suite untouched; "Looks Done" wallet/ledger/concurrency = verify-only (Pol track) | ✓ HELD | No `backend/tests` edit in any Phase-11 commit; LOOKS-DONE rows 1/2/4/5/6 = VERIFY-ONLY citing existing tests + Pol's DEF-03-01; none re-implemented. |
| 4. CI hotfix PR #16 untouched; existing CI untouched | ✓ HELD | `git diff origin/main` on `backend-ci.yml` / `frontend-ci.yml` / `security.yml` = **empty**. New scanning lives only in new `security-scan.yml` + `prod-migration-dry-run.yml`. Built on `origin/main` (F1–F10), not PR #16. |
| 5. Security scan = bandit + pnpm/npm audit + OWASP ZAP baseline (`/auth/*` + `/bets/*`); gitleaks already green; HIGH-only | ✓ HELD | All four scanners present, each HIGH-gated (bandit `--severity-level high`, pnpm `--audit-level high`, ZAP `.zap/rules.tsv` IGNORE, pip-audit ignores known non-HIGH transitives). ZAP reaches `/auth/*` + public routes; authenticated `/bets/*` DAST = documented v2 deferral. gitleaks not re-added. |

### Human Verification Required

Two items — both **documented manual-verify deferrals** (operator-approved 2026-06-02), gating the LIVE operator demo, NOT the code merge. Their code/doc deliverables shipped and are verified above.

#### 1. Sentry alert round-trip (SC#5 / plan 11-03) — DEFERRED-1

**Test:** Define the 4 alert rules in the Sentry UI per `docs/runbooks/sentry-alerts.md` §3; run the 4 synthetic triggers (§4) against `xpredict-staging` with the real `SENTRY_DSN`; confirm each event + alert lands in the configured channel (Slack #general or email); fill the §5 sign-off table and commit.
**Expected:** All 4 rows ☑ across trigger-run / event-in-Sentry / alert-fired.
**Why human:** Sentry is external SaaS — alert delivery cannot be asserted in CI without a live staging DSN (same precedent as Phase 1 PLT-08). The 4 in-code emit sites already exist and are verified; only the live round-trip remains. Owner: Pol.

#### 2. Responsive visual QA 360–768px (SC#1 / PLT-07 / plan 11-05) — DEFERRED-2

**Test:** Run the frontend (dev server or CI preview) and check home / market-detail / bet flow / portfolio / wallet / auth at 360 / 390 / 414 / 768px.
**Expected:** No horizontal scroll on any surface at any width; all controls thumb-reachable; text readable. Record pass, or list surface+width+issue for a CSS-only follow-up.
**Why human:** Responsive correctness is inherently visual and cannot be unit-asserted. Local `pnpm build` is environmentally broken in the deep Windows worktree (DEF-FE-BUILD-01 — reproduces on pristine HEAD; real CI builds fine), so a stable preview/dev runtime is needed. The CSS/layout-only fixes shipped and `pnpm typecheck` is green (verified by verifier). Owner: Pol / operator.

### Gaps Summary

**No gaps.** Every code/doc deliverable for all 6 success criteria + PLT-07 is present, substantive, correctly wired, and (where runnable in-process) verified by the verifier: the dev-config guard runs clean (exit 0), bandit's HIGH gate is green (High: 0), both new workflows are valid YAML, the responsive diff is verifiably Tailwind-className-only, `pnpm typecheck` exits 0, all 32 LOOKS-DONE rows carry real evidence (independently spot-checked), and all 10 SUMMARY commit hashes resolve. All five hard constraints hold (existing CI byte-identical to origin/main; legal scaffold-only; backend tests / wallet suite untouched; separate from PR #16; scanners HIGH-only).

The only open items are the **two documented, operator-approved manual-verify deferrals** (Sentry live round-trip and responsive visual QA), which require external runtime (real staging DSN / a stable preview) not yet available and which gate the live operator demo rather than the merge — recorded in `docs/DEFERRED-MANUAL-GATES.md` with ready runbooks. Per GSD conventions and the gate-resolution context, these are scored as `human_needed`, NOT `gaps_found`. Status: **human_needed**.

---

_Verified: 2026-06-02T16:10:00Z_
_Verifier: Claude (gsd-verifier)_
