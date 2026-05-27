---
phase: 3
slug: wallet-double-entry-ledger
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-27
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (asyncio_mode=auto) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run --directory backend pytest -m "not integration" -q` |
| **Full suite command** | `uv run --directory backend pytest -q` (integration uses testcontainers Postgres — needs Docker) |
| **Estimated runtime** | unit ~5s; full suite ~45–90s (testcontainers PG spin-up) |

---

## Sampling Rate

- **After every task commit:** Run `uv run --directory backend pytest -m "not integration" -q`
- **After every plan wave:** Run `uv run --directory backend pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~90 seconds (full suite with testcontainers)

---

## Per-Task Verification Map

*Populated by the planner — every task maps to a requirement, a test type, and an automated command (or a Wave 0 dependency).*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _(planner fills)_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Planner fills. Likely: `backend/tests/test_wallet_ledger.py` + `backend/tests/test_wallet_concurrency.py` (integration, reuses the Spike 002 `asyncio.gather` + invariant-check shape) + shared fixtures in `backend/tests/conftest.py`.*

- [ ] _(planner fills)_

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Disabled "Add funds" button visible in player UI | WAL/SC#6 | Visual presence | Load wallet page; confirm button rendered + disabled |

*All money-correctness behaviors (SC#1–#5, #7) have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
