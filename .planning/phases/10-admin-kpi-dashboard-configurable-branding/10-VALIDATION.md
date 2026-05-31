---
phase: 10
slug: admin-kpi-dashboard-configurable-branding
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-31
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Test seams + Wave 0 gaps are detailed in `10-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend, testcontainers for integration) / vitest (frontend) |
| **Config file** | `backend/pyproject.toml` / `frontend/vitest.config.ts` |
| **Quick run command** | `cd backend && .venv/Scripts/python.exe -m pytest -q -m "not integration"` |
| **Full suite command** | `cd backend && .venv/Scripts/python.exe -m pytest` + `cd frontend && pnpm test` |
| **Estimated runtime** | ~TBD (planner/nyquist to confirm) |

---

## Sampling Rate

- **After every task commit:** Run quick (non-integration) suite for the touched side.
- **After every plan wave:** Run full suite.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** TBD (planner to set).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _to be filled by planner / nyquist audit_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] _to be filled from `10-RESEARCH.md` §Validation Architecture (test stubs for KPI queries + runtime-theming flow)_

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Palette swap re-skins player UI on next navigation (no rebuild) | ADD-06 | Cross-process runtime behavior; visual | Change palette in admin → navigate player UI → confirm `--brand-*` vars + colors updated |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < {N}s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
