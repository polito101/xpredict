---
phase: 15
slug: event-settlement-house-resolve-void-mirrored-verify
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Cross-cutting invariant (every resolution path): the **spike-004 double-entry integrity check**
> (`app.wallet.reconcile._reconcile_async`) must report `drift_count == 0` after resolve / void /
> reverse / partial-failure / idempotent-replay / mirrored-verify.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (uv-managed) + pytest-asyncio + testcontainers (Postgres 16 via Docker) |
| **Config file** | `backend/pyproject.toml` (+ `backend/tests/conftest.py` fixtures) |
| **Quick run command** | `cd backend && uv run pytest tests/settlement -x -q` |
| **Full suite command** | `cd backend && uv run pytest` |
| **Estimated runtime** | per-module ~30–90s; full suite minutes (testcontainers) |

> **Windows-worktree caveat** ([[xprediction-backend-fullsuite-testcontainers-flake]]): the full `uv run pytest`
> flakes locally (testcontainers contention across unrelated modules) and `ruff check`/`format` flip-flop.
> Sample **per-module** locally (settlement); trust the **Linux `backend` CI job** (full suite + ruff + mypy) as the source of truth.
> Settlement services commit internally → integration tests MUST use committed `_get_session_maker()` sessions, NOT the rolled-back `async_session` fixture (RESEARCH Pitfall 5).

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/settlement -x -q`
- **After every plan wave:** Run the full settlement + wallet + bets module set (`uv run pytest tests/settlement tests/wallet tests/bets -q`)
- **Before `/gsd-verify-work`:** Full suite green on **Linux CI** (the worktree full-suite run is advisory only)
- **Max feedback latency:** ~90 seconds (per-module)

---

## Per-Task Verification Map

> Filled during planning/execution from PLAN.md task IDs (Nyquist Wave 0). One row per task.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {15-NN-NN} | NN | N | EVT-06 / EVA-03..06 | T-15-NN / — | {expected secure behavior or "N/A"} | unit/integration | `cd backend && uv run pytest {path} -x` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Populated by the planner/Nyquist Wave 0. Expected test surfaces:

- [ ] `backend/tests/settlement/test_event_service.py` — resolve / void / reverse / partial-failure / idempotent-replay (EVA-03, EVA-04, EVA-05)
- [ ] `backend/tests/settlement/test_derive_event_status.py` — pure-projection unit tests for all four states (EVT-06)
- [ ] `backend/tests/settlement/test_event_mirrored.py` — mirrored-reject gate + `detect_polymarket_resolutions` event-child verify (EVA-06)
- [ ] Shared house-event synthesis fixture (no house events exist pre-Phase-16) in `backend/tests/settlement/conftest.py` or reuse existing factories

*If existing infrastructure covers a surface, mark it accordingly during Wave 0.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none expected — service layer is fully automatable) | — | — | — |

*The EVA-03 two-step confirm + admin auth surface is deferred to Phase 16 (API) — out of scope here.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] spike-004 integrity assertion present in every resolution-path test
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
