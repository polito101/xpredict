---
phase: 11
slug: hardening-operator-demo-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-02
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> NOTE: Phase 11 is a hardening/closure gate — most criteria are verified by **CI jobs**,
> **manual QA** (responsive, Sentry alert round-trips), or **doc-audit**, not new unit tests.
> The per-task map therefore leans on CI commands + `checkpoint:human-verify` rather than
> a dense automated-unit grid. Backend test-isolation is OUT OF SCOPE (Pol's track).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest (testcontainers + fakeredis) via `uv` |
| **Framework (frontend)** | vitest via `pnpm` |
| **Config file** | `backend/pyproject.toml` · `frontend/vitest.config.ts` |
| **Quick run command** | `cd backend && uv run pytest tests/<dir> -x` · `cd frontend && pnpm test` |
| **Full suite command** | backend CI job (testcontainers) · `pnpm test` · new CI: `prod-migration-dry-run.yml`, `security-scan.yml` |
| **Estimated runtime** | backend ~45s · frontend ~4s · ZAP baseline ~3–5min |

---

## Sampling Rate

- **After every task commit:** Run the task's CI job locally where feasible (e.g. `bandit`, `pip-audit`, `pnpm audit`), else stage the CI workflow and rely on the PR run.
- **After every plan wave:** Push the branch; the new CI workflows + existing `frontend-ci` must stay green.
- **Before `/gsd-verify-work`:** All NEW CI workflows green on the PR; responsive + Sentry manual-verify checklist signed off.
- **Max feedback latency:** ~5 min (ZAP baseline is the long pole).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _(populated by gsd-planner from PLAN.md tasks)_ | | | PLT-07 | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `.zap/rules.tsv` — ZAP baseline rule config (gate HIGH only)
- [ ] New CI workflow scaffolds (`prod-migration-dry-run.yml`, `security-scan.yml`)

*Existing backend/frontend test infrastructure otherwise covers Phase 11; no new unit-test framework needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Responsive QA 360–768px (home, market, bet, portfolio, wallet, auth) | PLT-07 | Real-device/viewport visual check | DevTools responsive mode + listed widths; no horizontal scroll, thumb-reachable |
| Sentry alert round-trips (4 scenarios) | PLT-07 | Alert rules live in Sentry org config, not repo (PLT-08 precedent) | Trigger each synthetic event; confirm alert lands in the configured channel; record in runbook |
| Tool installs (`bandit`/`pip-audit`/ZAP action) | PLT-07 | Versions `[ASSUMED]` — slopcheck unavailable | `checkpoint:human-verify` each install resolves before relying on its gate |

---

## Validation Sign-Off

- [ ] Each task has an `<automated>` CI command OR a `checkpoint:human-verify` / manual-verify entry
- [ ] Sampling continuity: no 3 consecutive tasks without a verification handle
- [ ] Wave 0 covers the new CI scaffolds + ZAP rules
- [ ] No watch-mode flags
- [ ] Feedback latency < ~300s
- [ ] `nyquist_compliant: true` set in frontmatter (by planner/executor)

**Approval:** pending
