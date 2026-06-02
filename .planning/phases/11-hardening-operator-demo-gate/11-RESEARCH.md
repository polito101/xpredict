# Phase 11: Hardening & Operator-Demo Gate - Research

**Researched:** 2026-06-02
**Domain:** Release hardening — responsive QA, CI security/migration gates, observability alerting, regulatory scaffolding
**Confidence:** HIGH (codebase facts verified directly; tool versions verified on registries; external tool wiring CITED from official docs)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (HARD SCOPE — operator-set, non-negotiable)

1. **No new features, no refactors, no architecture changes.** Hardening, verification, CI/observability, and scaffolding ONLY.
2. **Legal / ToS (SC#6) = STRUCTURE + BASE + NOTES ONLY.** Create skeletons: `docs/regulatory.md` (section scaffold + notes on what counsel must review), a ToS placeholder, and an operator-agreement template stub. Do NOT write deep legal content or expand the regulatory scope. The actual Spanish-counsel review is an EXTERNAL deferred dependency — out of this phase.
3. **Backend test-isolation / `backend-ci` pytest residual is OUT OF SCOPE.** Owned by a SEPARATE track (Pol), follow-up to PR #16 (`tests/wallet/test_concurrent_transfers.py::test_50_concurrent_overdraft`; DEF-03-01 isolation debt). Phase 11 MUST NOT touch backend tests, the wallet test suite, or re-fix that issue. The "Looks Done But Isn't" wallet / ledger / concurrency items are VERIFY-ONLY / documentation, coordinated with Pol — never re-implemented here.
4. **CI hotfix PR #16 stays untouched.** Phase 11 builds on top of `origin/main` (F1–F10); it neither modifies nor depends on PR #16's branch.
5. Security scan adds `bandit` (Python), `pnpm/npm audit`, and an OWASP ZAP baseline against `/auth/*` and `/bets/*` to CI; `gitleaks` is already green.

### Claude's Discretion
Within the boundaries above, implementation details (script structure, CI wiring, Sentry alert-rule definitions, responsive-QA method) are at Claude's discretion, guided by ROADMAP success criteria, PITFALLS.md, and existing repo conventions.

### Deferred Ideas (OUT OF SCOPE)
- Spanish legal counsel review of ToS + token policy (external; not in this phase).
- Backend test-isolation / `backend-ci` pytest greening (Pol's separate track).
- Any feature work, refactors, or architecture changes.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLT-07 | Player-facing UI is fully responsive on mobile browsers (≥360px width); admin UI desktop-only acceptable | SC#1 — responsive QA method (Tailwind v4 mobile-first), player page inventory in `frontend/src/app/`, CSS/layout-only fixes. The other 5 SCs are hardening tasks tied to the same operator-demo gate (PITFALLS.md "Looks Done But Isn't" + "Demo Trap" + "Regulatory Line"), not new requirements. |

**Note:** PLT-07 is the only formal requirement, but the phase's 6 success criteria (ROADMAP Phase 11) are the real scope contract. PLT-08 (Sentry alert rules) was code-completed in Phase 1 with **alert rules explicitly deferred to Phase 11** (REQUIREMENTS.md line 114) — SC#5 closes that deferral.
</phase_requirements>

## Summary

Phase 11 is a **closure/hardening gate**, not a feature phase. Five of its six success criteria are CI/observability/documentation work layered on the already-shipped F1–F10 base (`origin/main @ 0fb3fee`, single Alembic head `0009`). The sixth (SC#1) is CSS/layout-only responsive QA on the existing player pages. Nothing here touches business logic, the ledger, settlement, or the schema.

The codebase is in excellent shape for this gate: CORS is already explicit-origin (passes a "Looks Done But Isn't" item outright), money columns are `NUMERIC(18,4)` end-to-end, the audit log is DB-trigger-immutable, `gitleaks` runs in three tiers, Sentry is wired across all four surfaces (`api`/`worker`/`beat`/`frontend`) with a `service` tag, and a working bet→resolve→wallet→portfolio E2E test (`backend/tests/integration/test_phase5_e2e.py`) already exists — it is the direct reference for SC#3's dry-run E2E. The frontend already uses Tailwind v4 mobile-first patterns (`px-4 sm:px-6`, `max-w-6xl`, responsive grids), so SC#1 is an audit-and-patch pass, not a rebuild.

**Primary recommendation:** Add **three new GitHub Actions workflow files** (`prod-migration-dry-run.yml`, `security-scan.yml`, and either extend `security.yml` or add a ZAP job) rather than mutating the three existing CI files — this keeps PR #16's territory and the green base untouched (constraint 4). Pin every action by version. Configure `bandit` and the audit tools to **fail only on high-severity** to avoid false-positive build breaks. For SC#5, define Sentry alert rules **declaratively** (via the Sentry UI/API — there is no repo-side "alert rules" file in this stack; the four trigger sites already exist in code) and document the synthetic-trigger procedure. **Critical landmine:** the app has **no `DEBUG` flag** — it uses `ENVIRONMENT: Literal["dev","staging","prod"]` + an `is_dev` property; the dry-run's "fail on DEBUG=True / dev URL" check must target `ENVIRONMENT=dev` and hardcoded `localhost` **in application code**, while explicitly allow-listing the legitimate `localhost` healthcheck probes in `docker-compose.yml` and the intentional dev defaults in `.env.example`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Responsive QA (SC#1) | Frontend (Next.js/Tailwind CSS) | — | Pure presentation-layer; CSS/layout only, no API or data change |
| "Looks Done But Isn't" audit (SC#2) | CI + Docs | Backend (verify-only) | Documented verification gate; wallet/ledger/concurrency items are read-only checks coordinated with Pol |
| prod-migration-dry-run (SC#3) | CI (GitHub Actions) | Docker Compose + Backend E2E | Boots the existing stack in a staging-style env and replays the existing Phase-5 E2E path |
| Security scan (SC#4) | CI (GitHub Actions) | Backend (bandit) + Frontend (pnpm audit) + running app (ZAP) | DAST/SAST/dependency scanning wired as CI jobs; no app code change |
| Sentry alert rules (SC#5) | Observability (Sentry org config) | Backend (existing trigger sites) | Alert rules live in Sentry, not the repo; the four error-emit sites already exist in code |
| Regulatory scaffold (SC#6) | Docs | Frontend (footer links only — within "structure" scope) | Markdown skeletons + template stubs; no legal content authored |

## Standard Stack

This phase adds **tooling**, not runtime dependencies. No new backend/frontend runtime packages are introduced into `pyproject.toml` or `package.json` business deps. The tools below run in CI (or are dev-only) and are pinned in workflow files / a dev dependency group.

### Core (CI tooling)
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| `bandit` | `1.9.4` `[VERIFIED: PyPI]` `[ASSUMED]` | Python SAST — finds common security issues | De-facto Python security linter; PyCQA-maintained; PITFALLS.md "Demo Trap" names it explicitly |
| `pip-audit` | `2.10.0` `[VERIFIED: PyPI]` `[ASSUMED]` | Python dependency CVE audit (optional complement) | PyPA-maintained; audits `uv.lock`/installed deps against the advisory DB. Use IF a Python-dep audit is wanted alongside `pnpm audit` (frontend) |
| `pnpm audit` | bundled with pnpm 9.15.0 | Frontend dependency CVE audit | Already the project's package manager (pinned 9.15.0 in `frontend-ci.yml`); zero new install |
| `zaproxy/action-baseline` | `v0.14.0` `[CITED: github.com/zaproxy/action-baseline]` `[ASSUMED]` | OWASP ZAP DAST baseline (passive, ~1 min spider, no real attacks) | The standard GitHub Action for ZAP baseline; CONTEXT constraint 5 mandates ZAP baseline on `/auth/*` + `/bets/*` |
| `gitleaks/gitleaks-action` | `v2.3.9` (already pinned) | Secret scanning | Already green in `security.yml` + `backend-ci.yml` — reuse, do not re-add |

> **`[ASSUMED]` rationale:** `slopcheck` is NOT available in this environment (verified — `command -v slopcheck` returns nothing), so per the package-legitimacy protocol every tool above is tagged `[ASSUMED]` even though `bandit`/`pip-audit` versions were confirmed on PyPI. The planner MUST gate each tool install behind a `checkpoint:human-verify` task before first use. Registry existence alone does not confer `[VERIFIED]` legitimacy status.

### Supporting (observability — no install)
| Tool | Purpose | When to Use |
|------|---------|-------------|
| Sentry alert rules (org-level config) | SC#5 — the 4 critical alerts | Defined in Sentry UI or via Sentry Alerts API; NOT a repo artifact in this stack |
| Sentry `sentry-cli` (optional) | Could script alert-rule creation | Only if Pol wants alert rules version-controlled; otherwise UI definition + documented procedure is sufficient and lower-risk |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `bandit` CLI in a dedicated job | `shundor/python-bandit-scan` action (SARIF upload to code-scanning) | The action adds GitHub Advanced Security coupling; a plain `uv run bandit -r app/ -ll` step is simpler, self-contained, and matches the repo's existing "run the tool directly" convention (cf. money-lint step). **Recommend the plain CLI step.** |
| `zaproxy/action-baseline` | `zaproxy/action-full-scan` | Full scan performs active attacks (much slower, can be destructive against a stateful bet/settle DB). CONTEXT says **baseline** — use baseline only. |
| `pnpm audit` | `npm audit` | `pnpm` is already the pinned package manager; use `pnpm audit` to match the lockfile. CONTEXT says "pnpm/npm audit" — pnpm is the correct one here. |
| Sentry alert rules via API/IaC | Sentry UI definition + documented runbook | UI definition is faster and needs no Sentry auth token in CI. Given SC#5 only requires rules "configured and synthetically triggered… land in the notification channel," a documented UI procedure + a synthetic-trigger script satisfies it. IaC is over-engineering for a 4-rule, single-project setup. |

**Installation (CI-scoped, not runtime):**
```bash
# bandit + pip-audit go in the backend dev dependency group (pyproject.toml [dependency-groups] dev),
# NOT the runtime [project] dependencies. They are CI/dev tools.
#   uv add --dev bandit pip-audit       # only after the checkpoint:human-verify gate
# pnpm audit needs no install (bundled with pnpm 9.15.0).
# ZAP runs entirely inside the GitHub Action container — nothing installed in the repo.
```

**Version verification performed (2026-06-02):**
- `bandit` → PyPI returns `1.9.4` (latest) `[VERIFIED: PyPI]`
- `pip-audit` → PyPI returns `2.10.0` (latest) `[VERIFIED: PyPI]`
- `zaproxy/action-baseline` → latest tagged `v0.14.0` `[CITED: github.com/zaproxy/action-baseline]`
- `gitleaks/gitleaks-action@v2.3.9` → already pinned in-repo

## Package Legitimacy Audit

> This phase installs **CI/dev tooling only** (no new runtime business dependencies). `slopcheck` was unavailable at research time, so all rows are `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `bandit` | PyPI | mature (years; 1.9.4 latest) | very high | github.com/PyCQA/bandit | unavailable | Approved — gate behind checkpoint:human-verify |
| `pip-audit` | PyPI | mature (2.x; 2.10.0 latest) | high | github.com/pypa/pip-audit | unavailable | Approved (optional) — gate behind checkpoint:human-verify |
| `zaproxy/action-baseline` | GitHub Marketplace | mature (v0.x, OWASP-maintained) | high | github.com/zaproxy/action-baseline | n/a (GH Action, not a package) | Approved — pin `@v0.14.0` |
| `pnpm audit` | bundled w/ pnpm 9.15.0 | n/a | n/a | github.com/pnpm/pnpm | n/a | Approved — no install |

**Packages removed due to slopcheck [SLOP] verdict:** none (slopcheck unavailable; none removed)
**Packages flagged as suspicious [SUS]:** none

*Because slopcheck was unavailable, the planner MUST insert a `checkpoint:human-verify` task before the first `uv add --dev bandit pip-audit` and confirm the ZAP action pin before merge.*

## Architecture Patterns

### System Architecture Diagram — Phase 11 CI / Observability flow

```
                    ┌─────────────────────────── GitHub PR (gsd/phase-11-…) ──────────────────────────┐
                    │                                                                                   │
   developer push ──┤                                                                                   │
                    ▼                                                                                   │
        ┌───────────────────────┐   ┌───────────────────────┐   ┌──────────────────────────────────┐ │
        │  backend-ci.yml        │   │  frontend-ci.yml       │   │  security.yml (gitleaks weekly)   │ │
        │  (EXISTING — untouched │   │  (EXISTING — untouched │   │  (EXISTING — untouched OR add ZAP │ │
        │   except maybe + bandit│   │   except maybe +audit) │   │   job as a NEW workflow instead)  │ │
        └───────────────────────┘   └───────────────────────┘   └──────────────────────────────────┘ │
                                                                                                        │
        ┌───────────────────────────────────────── NEW WORKFLOWS ─────────────────────────────────┐   │
        │                                                                                            │   │
        │  prod-migration-dry-run.yml                       security-scan.yml                         │  │
        │  ───────────────────────────                      ──────────────────                        │  │
        │  1. checkout                                      job: bandit  → uv run bandit -r app/ -ll  │  │
        │  2. write staging-style .env                          (fail on HIGH severity only)          │  │
        │     (ENVIRONMENT=staging, non-dev secrets,        job: pnpm-audit → pnpm audit             │  │
        │      placeholder non-localhost DSN)                   --audit-level high (frontend/)         │  │
        │  3. docker compose up -d --wait  (8 services)     job: pip-audit → uv run pip-audit (opt.)  │  │
        │  4. alembic upgrade head (single head 0009)       job: zap-baseline                          │  │
        │  5. RUN bet→settle E2E (reuse Phase 5 path)           ┌───────────────────────────────┐    │  │
        │  6. grep app code for localhost / ENVIRONMENT=dev     │ docker compose up -d --wait    │    │  │
        │     → FAIL build if found (allow-list compose         │ zaproxy/action-baseline@v0.14  │    │  │
        │       healthchecks + .env.example)                    │ target: http://localhost:8000  │    │  │
        │                                                       │ rules_file: .zap/rules.tsv     │    │  │
        └───────────────────────────────────────────────────── │  (path-scope /auth/* /bets/*)  │ ───┘  │
                                                                └───────────────────────────────┘       │
                                                                                                         │
   ┌─────────────────────────────── SENTRY (org config, NOT repo) ──────────────────────────────────┐  │
   │  4 alert rules over the EXISTING emit sites:                                                      │ │
   │   • settlement failure  ← FastAPI ServerErrorMiddleware capture (main.py:103) + Celery           │ │
   │                            task_failure signal (celery_app.py:164)                                │ │
   │   • polymarket sync error-rate spike ← tasks.py capture_exception (lines 138/190/318/322)        │ │
   │   • ledger reconciliation drift ← reconcile.py capture_message level=error (line 139)            │ │
   │   • auth-abuse / failed-login burst ← 429 handler (main.py:163) + auth.manager log sites          │ │
   │  Synthetic triggers: /api/sentry-test, celery sentry_test_task, injected drift, 429 burst.       │ │
   └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (new files only)
```
.github/workflows/
├── backend-ci.yml            # EXISTING — leave as-is (or add ONE bandit step; prefer separate workflow)
├── frontend-ci.yml           # EXISTING — leave as-is (or add ONE pnpm audit step; prefer separate workflow)
├── security.yml              # EXISTING — gitleaks weekly; leave as-is
├── prod-migration-dry-run.yml  # NEW (SC#3)
└── security-scan.yml         # NEW (SC#4 — bandit + pnpm audit + ZAP baseline)
.zap/
└── rules.tsv                 # NEW — ZAP alert allow/ignore list (false-positive suppression)
bin/  (or scripts/)
└── check_no_dev_config.(sh|py)  # NEW (SC#3) — the "fail on localhost/ENVIRONMENT=dev in app code" guard
docs/
├── regulatory.md             # NEW (SC#6) — section SKELETON + counsel-review notes (no legal content)
├── terms-of-service.md       # NEW (SC#6) — ToS PLACEHOLDER (no legal content)
├── operator-agreement.md     # NEW (SC#6) — operator-agreement TEMPLATE STUB
└── LOOKS-DONE-CHECKLIST.md   # NEW (SC#2) — the executed audit, each item ticked or deferred-with-reason
```

### Pattern 1: New CI workflow mirroring existing conventions
**What:** Each new workflow copies the structure of `backend-ci.yml` / `frontend-ci.yml` verbatim (checkout → setup → run), pins all actions, sets `permissions: contents: read`, `timeout-minutes`, and triggers on `pull_request` + `push: branches:[main]`.
**When to use:** SC#3 and SC#4 jobs.
**Example:**
```yaml
# Source: pattern lifted from this repo's .github/workflows/backend-ci.yml (verified in-repo)
name: security-scan
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  bandit:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install uv
      - working-directory: backend
        run: uv sync --frozen
      # -ll = report MEDIUM+; -lll would be HIGH only. CONTEXT: "no high".
      # Use --severity-level high to FAIL only on high (avoid false-positive breaks).
      - working-directory: backend
        run: uv run bandit -r app/ --severity-level high
```

### Pattern 2: ZAP baseline scoped to specific paths
**What:** Boot the compose stack, point `zaproxy/action-baseline@v0.14.0` at the API, and use a `.zap/rules.tsv` file to ignore non-actionable passive alerts (the baseline reports informational findings that must not break the build).
**When to use:** SC#4 ZAP job.
**Example:**
```yaml
# Source: github.com/zaproxy/action-baseline README [CITED]
- name: ZAP Baseline Scan
  uses: zaproxy/action-baseline@v0.14.0
  with:
    target: 'http://localhost:8000'
    rules_file_name: '.zap/rules.tsv'   # suppress known false positives → no build break
    cmd_options: '-a'
    allow_issue_writing: false          # don't auto-open GitHub issues from CI
    fail_action: true                    # fail only on configured (high) alert thresholds
```
> ZAP baseline is path-agnostic at the spider level; "against `/auth/*` and `/bets/*`" is satisfied by ensuring the spider reaches those routes (seed URLs) and that `.zap/rules.tsv` keeps the gate focused on high-severity findings there. The baseline does NOT perform authenticated active attacks — it is passive.

### Pattern 3: Sentry alert rule (declarative, org-side)
**What:** A metric/issue alert rule with a static or percent-change threshold and a notification action (Slack `#general`, matching the repo's existing GitHub↔Slack channel, or email).
**When to use:** SC#5, all four rules.
**Example (conceptual — defined in Sentry UI or via Alerts API):**
```
# Source: docs.sentry.io/api/alerts/create-a-metric-alert-rule-for-an-organization [CITED]
Rule: "Settlement failure"
  dataset: events (errors)
  filter: service:worker OR service:api  AND  (transaction/message matches settlement)
  aggregate: count()
  threshold: static, > 0 in 5m   (any settlement exception is alert-worthy)
  trigger action: slack #general  (or email)
```
Valid aggregates include `count`, `count_unique`, `percentage`, `failure_rate`, `p95`. Trigger action types include `email`, `slack`, `msteams`, `pagerduty`. Threshold types: **Static** (fixed number) or **Percent change** (e.g. ">10% more errors vs prior period" — use this for the Polymarket "error-rate spike").

### Anti-Patterns to Avoid
- **Mutating the three existing CI workflows heavily.** Violates the spirit of constraint 4 (keep the green base + PR #16 territory clean). Prefer NEW workflow files; if you must add a step to an existing file, add exactly one minimal step.
- **Failing the build on MEDIUM/LOW bandit, `npm audit` moderate, or ZAP informational alerts.** Guarantees a red build on day one. Gate strictly on HIGH (`bandit --severity-level high`, `pnpm audit --audit-level high`, ZAP `.zap/rules.tsv` ignore list).
- **Grepping the WHOLE repo for `localhost` in the dry-run.** Will flag `docker-compose.yml` healthchecks (legitimate intra-container loopback) and `.env.example` (intentional dev template). Scope the grep to **application source** (`backend/app/`, `frontend/src/`) and allow-list compose/env templates.
- **Looking for `DEBUG=True`.** This app has NO `DEBUG` flag. The equivalent guard is `ENVIRONMENT=dev` leaking into a staging/prod boot, and `is_dev`-gated behavior. Translate the PITFALLS checklist item to this codebase's actual config shape.
- **Authoring real legal text in SC#6.** Constraint 2: skeleton + placeholder + notes ONLY. Counsel review is external/deferred.
- **Re-implementing wallet/ledger/concurrency fixes during SC#2.** Constraint 3: those items are VERIFY-ONLY and coordinated with Pol.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Python SAST | Custom AST security linter | `bandit -r app/ --severity-level high` | Hundreds of curated rules; PITFALLS.md names it |
| DAST / web vuln scan | Custom HTTP fuzzer | `zaproxy/action-baseline@v0.14.0` | OWASP-maintained passive scanner; one action |
| Dependency CVE check | Manual advisory lookups | `pnpm audit` (FE) + optional `pip-audit` (BE) | Advisory DBs auto-updated |
| Secret scanning | New regex scanner | EXISTING `gitleaks` (3-tier, already green) | Already shipped in Phase 1; reuse |
| bet→settle E2E for the dry-run | New E2E from scratch | Reuse `backend/tests/integration/test_phase5_e2e.py` shape | A complete, passing bet→resolve→wallet→portfolio integration test already exists |
| Responsive breakpoints | Custom media queries | Tailwind v4 mobile-first prefixes (`sm:`/`md:`) | Already the project's system; unprefixed = mobile (≥360px) |
| Sentry alert plumbing | Custom error-rate poller | Sentry metric/issue alert rules | The four emit sites already exist in code; only rules need defining |

**Key insight:** Phase 11 is almost entirely **assembly of existing, well-maintained tools + verification of already-shipped invariants.** The single highest-value engineering deliverable is the `check_no_dev_config` guard for SC#3 — and even that is a ~30-line grep-with-allowlist, not a framework.

## Runtime State Inventory

> Phase 11 is a hardening/CI/docs phase — it ships **no migrations, no schema changes, no data writes, no renames**. The standard rename/refactor inventory categories are therefore N/A. Documented explicitly per protocol:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no data model touched. Verified: no migration added (head stays `0009`); SC#3 dry-run only READS via the existing E2E path. | none |
| Live service config | **Sentry org config** is the one externally-stored item SC#5 changes — but it lives in Sentry, not the repo, and is *additive* (new alert rules). | Define 4 alert rules in Sentry (UI or API). Document the procedure. |
| OS-registered state | None — no OS task/service registration. | none |
| Secrets / env vars | SC#3 introduces a **staging-style `.env` written inside the CI job only** (ephemeral; never committed). No new secret KEY names enter the codebase. ZAP/bandit need no secrets. | Ensure the dry-run `.env` is generated in-job and `.gitignore`'d; never echo secret values to logs. |
| Build artifacts | None new. `bandit`/`pip-audit` added to the **dev** dependency group regenerate `uv.lock` (dev-group only). | After `uv add --dev`, commit the updated `uv.lock`. |

**Nothing found in OS-registered / stored-data / new-secret-keys categories — verified by: no migration, no schema edit, no `setx`/cron/systemd work in scope, no new `Settings` field required.**

## Common Pitfalls

### Pitfall 1: The dry-run flags legitimate `localhost` and there is no `DEBUG` flag
**What goes wrong:** A naive "fail the build if `localhost` or `DEBUG=True` appears anywhere" check turns red immediately on `docker-compose.yml` healthchecks (`http://localhost:8000/healthz`, `:8025`, `:5555`, `:3000`) and on `.env.example` dev defaults — and never matches `DEBUG` because the app uses `ENVIRONMENT`/`is_dev` instead.
**Why it happens:** The PITFALLS.md checklist item is written generically ("change every `localhost`, every dev secret, every `DEBUG=True`"); this codebase's config shape differs.
**How to avoid:** Scope the guard to `backend/app/**` + `frontend/src/**` only; allow-list `docker-compose.yml`, `.env.example`, test files, and the `.zap/` dir. Translate "DEBUG=True" to "the booted stack must run with `ENVIRONMENT=staging` (or prod) and must NOT contain hardcoded `localhost`/dev secrets in application source." Confirmed config facts: `backend/app/core/config.py` defines `ENVIRONMENT: Literal["dev","staging","prod"]` (default `dev`), `is_dev`/`is_prod` properties, and `SENTRY_DSN`/`SECRET_KEY` are env-driven (no hardcoded defaults for secrets).
**Warning signs:** First CI run is red with matches inside compose/env-example.

### Pitfall 2: Security-scan jobs break the build on non-high findings
**What goes wrong:** `bandit` at default verbosity reports MEDIUM/LOW (e.g., `assert` usage, `subprocess` flags); `npm/pnpm audit` reports moderate transitive advisories; ZAP baseline emits informational passive alerts. Any of these failing the job blocks the PR with noise.
**Why it happens:** Default tool exit codes are non-zero on any finding.
**How to avoid:** `bandit --severity-level high` (and optionally `--confidence-level high`); `pnpm audit --audit-level high`; ZAP `fail_action` gated by a `.zap/rules.tsv` that downgrades/ignores known-benign rule IDs. CONTEXT success criterion is explicitly "no **high**-severity findings."
**Warning signs:** Long red logs full of LOW/MEDIUM/INFO items.

### Pitfall 3: ZAP baseline expects to reach `/auth/*` and `/bets/*` but the spider can't authenticate
**What goes wrong:** `/bets` is auth-gated (cookie player); an unauthenticated baseline spider sees 401/403 and reports thin coverage, or reports the 401s as "findings."
**Why it happens:** Baseline scan is passive and unauthenticated by default.
**How to avoid:** Accept that the baseline primarily exercises the **public surface + auth endpoints** (`/auth/login`, `/auth/register`, `/auth/forgot-password` are unauthenticated and the most security-relevant — exactly what CONTEXT names first). For `/bets/*`, seed the spider with the public market routes and document that authenticated DAST is a v2 item. Do NOT attempt to wire full ZAP authentication context in this phase (would be new infra; out of the "baseline" scope). Suppress 401/403-as-finding noise via `.zap/rules.tsv`.
**Warning signs:** ZAP report dominated by "401 Unauthorized" entries.

### Pitfall 4: `docker compose up --wait` host-port conflicts in CI (and the documented local conflict)
**What goes wrong:** The compose stack binds host ports 5432/6379/3000/8000/5555/8025/1025. Phase 1's `01-03-SUMMARY` documented local conflicts with Pol's `crypto-casino` containers; in CI a port could collide with a service container.
**Why it happens:** Fixed host-port mappings in `docker-compose.yml`.
**How to avoid:** In the GitHub Actions runner, the host is clean so default ports are fine; do NOT add Postgres/Redis as `services:` containers (they'd collide with compose). If a collision ever appears, run compose with an override that drops host port publishing (the dry-run only needs intra-network reachability + the API port). Use `docker compose up -d --wait` (the compose file already has healthchecks on all 8 services) so the job blocks until healthy before the E2E step.
**Warning signs:** "port is already allocated" in CI logs.

### Pitfall 5: Sentry alert rules can't be synthetically verified without a real DSN
**What goes wrong:** PLT-08 already flagged "Sentry event round-trip needs real `SENTRY_DSN`" as a manual-verify item. Alert rules can't fire in CI without a live project + DSN, and the four triggers must actually reach Sentry.
**Why it happens:** Sentry is an external SaaS; CI has no DSN by default.
**How to avoid:** Treat SC#5 verification as a **documented manual-verify runbook** (consistent with how Phase 1 handled the Sentry round-trip), executed by Pol against the real `xpredict-staging` project. Provide: (1) the 4 rule definitions, (2) the 4 synthetic-trigger commands (`GET /api/sentry-test` for FastAPI; `celery -A app.celery_app call app.core.sentry.sentry_test_task` for worker; inject a drift row + run `reconcile_wallets` for reconciliation; fire >6 failed logins in the rate-limit window for auth-abuse), (3) the expected notification-channel landing. The synthetic-trigger sites ALL already exist in code (verified).
**Warning signs:** Trying to assert Sentry delivery inside a GitHub Action.

### Pitfall 6: Responsive fixes accidentally become refactors
**What goes wrong:** "While I'm in here" component restructuring to fix a mobile layout crosses the no-refactor line (constraint 1).
**Why it happens:** Tempting to refactor a component to make it responsive.
**How to avoid:** Restrict SC#1 edits to Tailwind class changes (add `sm:`/`md:` prefixes, `flex-col`→`sm:flex-row`, `overflow-x-auto` wrappers, `min-w-0`, `truncate`) and container width tweaks. No prop changes, no new components, no data-flow changes. The existing pages already use the right primitives (`max-w-6xl mx-auto px-4 sm:px-6`), so most fixes are additive prefixes.
**Warning signs:** A "responsive" diff that adds/removes props or splits components.

## Code Examples

### SC#3 — "no dev config in app source" guard (the one real script)
```bash
#!/usr/bin/env bash
# Source: derived from this repo's config facts (backend/app/core/config.py: ENVIRONMENT/is_dev;
# docker-compose.yml localhost healthchecks are LEGITIMATE and allow-listed).
set -euo pipefail
# Scope ONLY application source. Allow-list compose, env templates, tests, .zap, docs.
violations=$(grep -rnE 'localhost|127\.0\.0\.1|ENVIRONMENT *= *.?dev' \
  backend/app frontend/src \
  --include='*.py' --include='*.ts' --include='*.tsx' \
  || true)
if [[ -n "$violations" ]]; then
  echo "::error::Hardcoded dev URL or ENVIRONMENT=dev found in application source:"
  echo "$violations"
  exit 1
fi
echo "OK: no hardcoded localhost / ENVIRONMENT=dev in application source."
```

### SC#3 — staging-style boot + reuse the existing E2E (job sketch)
```yaml
# Source: docker-compose.yml (8 services, all healthchecked) + test_phase5_e2e.py (existing)
- name: Write staging-style env (ephemeral, never committed)
  run: |
    cat > .env <<'EOF'
    ENVIRONMENT=staging
    SECRET_KEY=ci-staging-placeholder-32-characters-minimum-xx
    ADMIN_JWT_PUBLIC_SECRET=ci-staging-placeholder-32-characters-minimum
    SENTRY_DSN=
    EOF
- name: Boot stack
  run: docker compose up -d --wait            # blocks on the 8 healthchecks
- name: Migrate (single head 0009)
  run: docker compose exec -T backend alembic upgrade head
- name: bet -> settle E2E (reuse Phase 5 integration path)
  run: docker compose exec -T backend uv run pytest tests/integration/test_phase5_e2e.py -x
- name: Guard against dev config in app source
  run: bash bin/check_no_dev_config.sh
```
> Note: the in-CI E2E uses the app's own routes/adapters (the existing test overrides only AUTH). This validates "places a bet end-to-end, settles, verifies nothing broke" (SC#3) without authoring new test logic.

### SC#2 — checklist execution artifact (Markdown shape)
```markdown
# Looks Done But Isn't — Phase 11 Audit (executed 2026-06-XX)
| # | Item | Class | Result | Evidence |
|---|------|-------|--------|----------|
| 1 | SUM(ledger)==balance per user | VERIFY (Pol track) | ✅ | reconcile_wallets clean on seed; `reconcile.py` |
| 5 | CORS not `*` / no dev origin in prod | VERIFY (do here) | ✅ | main.py:151 `allow_origins=[settings.FRONTEND_BASE_URL]` |
| … | … | … | … | … |
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tailwind `tailwind.config.js` for breakpoints | Tailwind v4 `@theme` in CSS + same default `sm`/`md`/`lg` (640/768/1024px), mobile-first | Tailwind v4 (in use here) | SC#1 uses prefixes directly; no config file needed (repo has none, by design) |
| Sentry "metric alerts" vs "issue alerts" naming | Both still exist; metric alerts now support static + percent-change thresholds, `failure_rate`/`percentage` aggregates | current Sentry | SC#5 "error-rate spike" → percent-change metric alert; "settlement failure" → issue/metric count alert |
| ZAP full active scan in CI | Baseline (passive, ~1 min) for PR gating; full/active scans run out-of-band | current ZAP guidance | CONTEXT correctly specifies **baseline** — fast, non-destructive against the stateful DB |

**Deprecated/outdated:**
- Looking for a `tailwind.config.{js,ts}` — **does not exist** in this repo (Tailwind v4 CSS-first config in `globals.css` via `@theme inline`). Do not create one.
- Looking for a `DEBUG` env var — **does not exist**; `ENVIRONMENT`/`is_dev` is the equivalent.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `bandit 1.9.4`, `pip-audit 2.10.0`, `zaproxy/action-baseline@v0.14.0` are current + correct package/action identities | Standard Stack | LOW — versions PyPI/GitHub-verified, but tagged `[ASSUMED]` because slopcheck was unavailable; planner gates installs behind checkpoint:human-verify |
| A2 | Sentry alert rules in this stack are org-side config (UI/API), not a repo artifact; UI definition + documented runbook satisfies SC#5 | Standard Stack / SC#5 | LOW-MED — if Pol wants alert rules version-controlled, add `sentry-cli`/IaC (more work, needs a Sentry auth token). Confirm preference. |
| A3 | SC#5 round-trip is a documented MANUAL-verify (real DSN required), consistent with Phase 1's handling | Pitfall 5 | LOW — matches PLT-08's existing manual-verify treatment |
| A4 | ZAP baseline against `/bets/*` is effectively public-surface + auth-endpoint coverage (no authenticated DAST in this phase) | Pitfall 3 | MED — if a reviewer expects authenticated `/bets` scanning, that's new infra and out of "baseline" scope; flag at planning |
| A5 | Optional `pip-audit` is wanted alongside `pnpm audit`; CONTEXT names only "pnpm/npm audit" explicitly | Standard Stack | LOW — `pip-audit` is additive and beneficial; drop it if Pol wants to scope tightly to CONTEXT's literal list |
| A6 | The Slack `#general` GitHub↔Slack channel is an acceptable Sentry notification target (or email is) | SC#5 examples | LOW — "configured notification channel" is satisfied by either; confirm channel preference |

## Open Questions

1. **Should Sentry alert rules be version-controlled (IaC) or UI-defined?**
   - What we know: The four trigger sites exist in code; Sentry supports both UI and Alerts-API definition.
   - What's unclear: Pol's preference for repo-tracked alert config vs. UI + runbook.
   - Recommendation: Default to **UI definition + a documented runbook** in `docs/` (no CI Sentry token needed, lowest risk). Offer IaC as a follow-up if desired.

2. **Does `/bets/*` ZAP coverage need authenticated scanning, or is baseline (public + auth endpoints) sufficient?**
   - What we know: CONTEXT says "OWASP ZAP **baseline**"; baseline is passive/unauthenticated.
   - What's unclear: Whether "against `/auth/* and /bets/*`" implies authenticated `/bets` traversal.
   - Recommendation: Ship baseline (covers the high-value unauthenticated `/auth/*` attack surface); document authenticated DAST as a v2 item. Confirm at planning.

3. **Extend existing CI files or add new workflows?**
   - What we know: Constraint 4 wants the green base + PR #16 territory untouched.
   - Recommendation: **New workflow files** (`prod-migration-dry-run.yml`, `security-scan.yml`) — cleanest separation. Add at most one minimal `bandit` step to `backend-ci.yml` / one `pnpm audit` step to `frontend-ci.yml` only if Pol prefers consolidation.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker + docker compose | SC#3 dry-run, SC#4 ZAP | ✓ (project requires it; GH runners have it) | runner-provided | — |
| `uv` | bandit/pip-audit install + run | ✓ (already in `backend-ci.yml`) | latest via pip | — |
| `pnpm` 9.15.0 | `pnpm audit` | ✓ (pinned in `frontend-ci.yml`) | 9.15.0 | `npm audit` |
| `bandit` | SC#4 Python SAST | ✗ (not yet installed) | `1.9.4` on PyPI | none — required install (gated) |
| `pip-audit` | SC#4 (optional) | ✗ | `2.10.0` on PyPI | drop (optional) |
| `zaproxy/action-baseline` | SC#4 DAST | ✓ (GH Action, runs in-container) | `v0.14.0` | none needed |
| `slopcheck` | package legitimacy gate | ✗ (verified absent) | — | mark all installs `[ASSUMED]` + checkpoint:human-verify |
| Real `SENTRY_DSN` + `xpredict-staging` project | SC#5 synthetic verification | ✗ in CI (✓ for Pol manually) | — | documented manual-verify runbook |
| Real mobile devices / browser devtools | SC#1 responsive QA | manual (Pol/dev) | iOS Safari, Android Chrome, desktop Firefox | Chrome DevTools device emulation 360–768px |

**Missing dependencies with no fallback:**
- `bandit` — must be installed (dev group), gated behind `checkpoint:human-verify`.
- Live Sentry DSN/project for SC#5 round-trip — supplied by Pol at manual-verify time.

**Missing dependencies with fallback:**
- `slopcheck` absent → all tool installs tagged `[ASSUMED]` + checkpoint-gated (strictly safer baseline).
- `pip-audit` optional → drop if scoping to CONTEXT's literal "pnpm/npm audit."

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework (backend) | `pytest` 8.3.x + `pytest-asyncio` 0.24+ + `testcontainers` (Postgres 16) + `fakeredis` |
| Framework (frontend) | `vitest` (config: `frontend/vitest.config.ts`) |
| Config file (backend) | `backend/pyproject.toml` (`[tool.pytest...]`) + `backend/tests/conftest.py` (lazy testcontainer + alembic-upgrade-head engine) |
| Quick run command (backend) | `cd backend && uv run pytest tests/ -x --tb=short` |
| Quick run command (frontend) | `cd frontend && pnpm test` |
| Full suite (backend) | `cd backend && uv run pytest tests/` |
| Dry-run E2E reuse | `uv run pytest tests/integration/test_phase5_e2e.py -x` (bet→settle path) |

### Phase Requirements → Test Map
| Req / SC | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| SC#1 / PLT-07 | Player pages render at 360–768px with no horizontal scroll | manual + visual | DevTools/device QA at 360/390/414/768px | ❌ manual-verify (visual; not unit-testable) |
| SC#2 | Looks-Done checklist executed | doc audit | run referenced existing tests + record evidence | ✅ existing suites are the evidence; checklist doc is NEW |
| SC#3 | Staging-style boot + bet→settle E2E + no dev-config | integration + script | `pytest tests/integration/test_phase5_e2e.py -x` + `bin/check_no_dev_config.sh` | ✅ E2E exists; ❌ guard script is Wave 0 |
| SC#4 | bandit/pnpm-audit/ZAP no high-severity | CI jobs | `uv run bandit -r app/ --severity-level high`; `pnpm audit --audit-level high`; ZAP action | ❌ workflows are Wave 0 |
| SC#5 | 4 alert rules fire to notification channel | manual-verify | synthetic triggers (4 commands, all sites exist) | ❌ manual-verify runbook (needs real DSN) |
| SC#6 | Regulatory/ToS/operator-agreement skeletons + footer links | doc presence + link check | file existence + footer render | ❌ docs are Wave 0; footer-link is a 1-line layout edit |

### Sampling Rate
- **Per task commit:** the relevant quick command for the file touched (e.g., frontend `pnpm test` after a responsive class change; `bandit` step locally after wiring the job).
- **Per wave merge:** full backend suite `uv run pytest tests/` + `pnpm test` + the new CI workflows green on the PR.
- **Phase gate:** all new CI workflows green; checklist doc complete; SC#1 + SC#5 manual-verify runbooks executed by Pol before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `.github/workflows/prod-migration-dry-run.yml` — SC#3
- [ ] `.github/workflows/security-scan.yml` — SC#4 (bandit + pnpm audit + ZAP)
- [ ] `.zap/rules.tsv` — ZAP false-positive suppression (SC#4)
- [ ] `bin/check_no_dev_config.sh` (or `.py`) — SC#3 dev-config guard
- [ ] `docs/regulatory.md`, `docs/terms-of-service.md`, `docs/operator-agreement.md` — SC#6 skeletons
- [ ] `docs/LOOKS-DONE-CHECKLIST.md` — SC#2 executed audit
- [ ] `uv add --dev bandit` (+ optional `pip-audit`) — behind checkpoint:human-verify
- [ ] Sentry runbook (`docs/` or in the checklist) — SC#5 manual-verify procedure
- [ ] Footer ToS/policy links in `frontend/src/app/layout.tsx` (player) + admin layout — SC#6 (1-line edits, within "structure" scope)

*Most automated coverage for Phase 11 is CI-job existence + the reuse of the existing Phase-5 E2E; SC#1 and SC#5 are inherently manual-verify (visual / external-SaaS round-trip).*

## Security Domain

> `security_enforcement` not set to `false` → section included. This phase IS the security-hardening gate.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control (already in place / verified this phase) |
|---------------|---------|-----------------------------------------------------------|
| V1 Architecture | yes | Tenant seam, audit immutability, separation — verified, not changed |
| V2 Authentication | yes | Argon2id (fastapi-users v15), refresh rotation, rate-limit (slowapi+Redis) — VERIFY via SC#2 + ZAP `/auth/*` |
| V3 Session Management | yes | HTTP-only Secure cookies (player), Bearer JWT (admin), token_version invalidation — VERIFY only |
| V4 Access Control | yes | `is_admin` enforced on `/admin/*`; self-bet ban; no user-to-user transfer (WAL-09) — VERIFY (SC#2) |
| V5 Input Validation | yes | Pydantic v2 schemas, hex allow-list for branding, CSV-injection escaping (Phase 8) — VERIFY only |
| V6 Cryptography | yes | HS256 JWT (config notes RS256 as a hardening option), no hand-rolled crypto — VERIFY; RS256 split is explicitly a possible Phase 11 item but NOT mandated by the 6 SCs |
| V7 Error Handling / Logging | yes | structlog secret-scrubber, Sentry `send_default_pii=False`, generic 429 (no email enumeration) — VERIFY + SC#5 |
| V9 Communications | partial | TLS in prod (compose is dev-only); CORS explicit-origin (main.py:151) — VERIFY |
| V14 Configuration | yes | Secrets via `Settings(BaseSettings)`, `gitleaks` 3-tier, no `DEBUG`/dev URL in app source — SC#3 + SC#4 enforce |

### Known Threat Patterns for {FastAPI + Next.js + Postgres + Celery}

| Pattern | STRIDE | Standard Mitigation (status) |
|---------|--------|------------------------------|
| SQL injection | Tampering | SQLAlchemy 2 parameterized / ORM; no string-interpolated SQL — VERIFY (bandit + ZAP) |
| Secret in repo | Info Disclosure | `gitleaks` 3-tier (pre-commit + PR diff + weekly full-history) — already green |
| Hardcoded dev URL / config to prod | Tampering/Config | SC#3 dry-run + `check_no_dev_config` guard (scoped to app source) |
| Email enumeration | Info Disclosure | Generic 429 + identical responses (main.py:163, T-02-08/10) — VERIFY |
| Login brute force | Spoofing | slowapi per-IP/per-email rate limit; SC#5 auth-abuse alert on 429 burst |
| Dependency CVE | multiple | `pnpm audit --audit-level high` (FE) + optional `pip-audit` (BE) |
| Vulnerable HTTP headers / passive web issues | multiple | ZAP baseline against the booted API |
| CSV/formula injection (admin export) | Tampering | `sanitize_csv_cell` (Phase 8, T-08-05) — VERIFY only |
| Audit-log tampering | Repudiation | Postgres UPDATE/DELETE trigger + REVOKE (Phase 1) — VERIFY (SC#2) |

## Project Constraints (from CLAUDE.md)

- **Phase tracking:** `PHASES.md` is the source of truth; AI marks Phase 11 `🔄 In progress` (already done — commit `cc7672a`) and later `👀 In review` + PR number. Never edited manually by the dev.
- **Branches/PRs:** Work ONLY on `gsd/phase-11-<slug>`, never `main`. 1 PR per phase, opened via `gh pr create` or GitHub MCP `create_pull_request` (never push to `main`). Only Pol merges.
- **Mode `yolo`:** Gates mandatory — `plan_check`, `verifier`, `code_review` ON; `auto_advance:false`.
- **Product is English; conversation Spanish.** Docs/ToS/regulatory skeletons authored in English.
- **Secrets:** Never commit `.env.local`, the GitHub PAT, or `LINEAR_API_KEY`. The SC#3 staging `.env` must be CI-ephemeral and gitignored.
- **Python 3.12 + uv + Docker** required for the backend dry-run + bandit jobs.
- **Spike findings:** `Skill("spike-findings-xpredict")` holds proven wallet/settlement/polymarket/realtime patterns — relevant only as VERIFY references for SC#2 (do not re-implement).

## Sources

### Primary (HIGH confidence — verified in-repo or on registry)
- This repository (read directly 2026-06-02): `.github/workflows/{backend-ci,frontend-ci,security}.yml`, `docker-compose.yml`, `backend/app/core/config.py`, `backend/app/core/sentry.py`, `backend/app/wallet/reconcile.py`, `backend/app/main.py` (CORS + 429 handler + Sentry capture), `backend/app/celery_app.py` (task_failure capture), `backend/app/integrations/polymarket/tasks.py` (capture_exception sites), `backend/app/settlement/service.py`, `backend/tests/conftest.py`, `backend/tests/integration/test_phase5_e2e.py`, `frontend/src/app/{layout.tsx,globals.css,page.tsx}`, `frontend/src/components/market-card.tsx`, `.planning/research/PITFALLS.md` ("Looks Done But Isn't" 443-478, "Demo Trap" 528-560, "The Regulatory Line" 563-629).
- PyPI (verified 2026-06-02): `bandit` latest `1.9.4`; `pip-audit` latest `2.10.0`.

### Secondary (MEDIUM confidence — official docs)
- ZAP Baseline GitHub Action — https://github.com/zaproxy/action-baseline (usage, `target`/`rules_file_name`/`cmd_options`, baseline = passive ~1 min) [CITED]
- bandit — https://github.com/PyCQA/bandit + marketplace docs (`--severity-level high`, pyproject `[tool.bandit]`, SARIF) [CITED]
- Sentry Alerts API — https://docs.sentry.io/api/alerts/create-a-metric-alert-rule-for-an-organization/ + https://docs.sentry.io/product/alerts/alert-types/ (metric vs issue alerts; static vs percent-change thresholds; aggregates incl. `failure_rate`/`percentage`; actions: email/slack/pagerduty) [CITED]
- Tailwind CSS responsive design — https://tailwindcss.com/docs/responsive-design (mobile-first; `sm`=640px `md`=768px `lg`=1024px; v4 `@theme` breakpoint customization) [CITED]

### Tertiary (LOW confidence)
- None relied upon for load-bearing claims.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions registry-verified; action/tool identities CITED from official repos (tagged `[ASSUMED]` only because slopcheck was unavailable to certify, not because of doubt).
- Architecture / repo references: HIGH — every file path, line reference, config fact (no `DEBUG`, `ENVIRONMENT`/`is_dev`, explicit CORS, existing E2E, Tailwind v4 patterns) read directly this session.
- Pitfalls: HIGH — derived from concrete codebase facts (compose localhost healthchecks, `.env.example` defaults, PLT-08 manual-verify precedent, port-conflict history).
- Sentry alert mechanics: MEDIUM-HIGH — CITED from current Sentry docs; exact UI vs API choice deferred to Pol (Open Question 1).

**Research date:** 2026-06-02
**Valid until:** ~2026-07-02 (30 days — stable domain; re-verify `bandit`/`pip-audit`/`action-baseline` pins before install if later).
