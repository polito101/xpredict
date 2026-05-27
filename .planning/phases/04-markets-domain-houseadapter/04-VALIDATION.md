---
phase: 4
slug: markets-domain-houseadapter
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-27
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.25 |
| **Config file** | backend/pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && uv run pytest tests/markets/ -x -q` |
| **Full suite command** | `cd backend && uv run pytest -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/markets/ -x -q`
- **After every plan wave:** Run `cd backend && uv run pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | MKT-07 | — | N/A | unit | `uv run pytest tests/markets/test_models.py -x -q` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | MKT-08 | — | Binary-only enforced | unit | `uv run pytest tests/markets/test_models.py::test_binary_only -x -q` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | ADM-01 | — | Admin Bearer required | integration | `uv run pytest tests/markets/test_admin_api.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | ADM-02 | — | N/A | integration | `uv run pytest tests/markets/test_admin_api.py::test_create_market -x -q` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | ADM-03 | — | Criteria lock after bet | integration | `uv run pytest tests/markets/test_admin_api.py::test_edit_locked -x -q` | ❌ W0 | ⬜ pending |
| 04-02-04 | 02 | 1 | ADM-04 | — | N/A | integration | `uv run pytest tests/markets/test_admin_api.py::test_close_market -x -q` | ❌ W0 | ⬜ pending |
| 04-02-05 | 02 | 1 | ADM-07 | — | 423 Locked response | integration | `uv run pytest tests/markets/test_admin_api.py::test_423_locked -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/markets/__init__.py` — test package
- [ ] `tests/markets/conftest.py` — shared fixtures (admin user, async session, test market factory)
- [ ] `tests/markets/test_models.py` — model unit tests
- [ ] `tests/markets/test_admin_api.py` — admin API integration tests

*Existing pytest infrastructure from Phase 1/2 covers framework needs.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
