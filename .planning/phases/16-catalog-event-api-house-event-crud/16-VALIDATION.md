---
phase: 16
slug: catalog-event-api-house-event-crud
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed behavior→test mapping lives in `16-RESEARCH.md` `## Validation Architecture`; the planner fills the per-task map below from it.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio, testcontainers — real Postgres via Docker) |
| **Config file** | `backend/pyproject.toml` (+ `backend/pytest.ini` markers) |
| **Quick run command** | `cd backend && uv run pytest tests/catalog tests/markets/test_admin_events*.py tests/settlement/test_event_router*.py -x` (per-module — Windows-worktree-safe) |
| **Full suite command** | `cd backend && uv run pytest` (trust **Linux CI** for the full suite + ruff + mypy — the Windows worktree flakes) |
| **Estimated runtime** | ~30–90s per module (testcontainers spin-up dominates) |

> **Windows worktree caveat:** the full `uv run pytest` flakes (testcontainers contention across unrelated modules) and `ruff check`/`format` flip-flop. Verify **per-module** locally; the Linux `backend` CI job is the source of truth. See [[xprediction-backend-fullsuite-testcontainers-flake]].

---

## Sampling Rate

- **After every task commit:** Run the per-module quick command for the touched module.
- **After every plan wave:** Run all Phase-16 endpoint modules.
- **Before `/gsd-verify-work`:** Per-module green locally; Linux CI full suite green is authoritative.
- **Max feedback latency:** ~90s (per-module).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _planner fills from RESEARCH `## Validation Architecture`_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/catalog/` — test files for `GET /catalog`, `GET /categories`, `GET /events/{slug}` (BRW-01..05): every filter combination bounded + explicit empty/zero; search local-only (never Gamma).
- [ ] `tests/markets/test_admin_events*.py` (or `tests/catalog/`) — house event create (EVA-01) + edit-lock-after-first-bet via `EXISTS(bets)` → 423 (EVA-02).
- [ ] `tests/settlement/test_event_router*.py` — resolve/void/reverse HTTP surface: two-step confirm preview-vs-execute, `ValueError`→HTTP map (mirrored 409 / blank justification 422 / bad outcome 422 / missing 404), auth-gate 401.
- [ ] Legacy `GET /markets` back-compat assertion (response still a `list[MarketListItem]`).

*Shared fixtures (admin Bearer, seeded group/children/bets) reuse `tests/conftest.py` + `tests/markets/conftest.py` patterns.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| _none expected_ | — | The whole phase is testable without UI (success criterion) — all behaviors have automated httpx/ASGITransport coverage. | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
