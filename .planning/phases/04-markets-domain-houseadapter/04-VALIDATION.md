---
phase: 4
slug: markets-domain-houseadapter
status: complete
nyquist_compliant: true
wave_0_complete: true
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
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/markets/ -x -q`
- **After every plan wave:** Run `cd backend && uv run pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | MKT-07 | — | N/A | unit | `uv run pytest tests/markets/test_models.py -x -q` | ✅ | ✅ green |
| 04-01-02 | 01 | 1 | MKT-08 | — | Binary-only enforced | unit | `uv run pytest tests/markets/test_models.py -x -q` | ✅ | ✅ green |
| 04-02-01 | 02 | 1 | ADM-01 | — | Admin Bearer required | integration | `uv run pytest tests/markets/test_admin_router.py -x -q` | ✅ | ✅ green |
| 04-02-02 | 02 | 1 | ADM-02 | — | N/A | integration | `uv run pytest tests/markets/test_admin_router.py -x -q` | ✅ | ✅ green |
| 04-02-03 | 02 | 1 | ADM-03 | — | Criteria lock after bet | integration | `uv run pytest tests/markets/test_admin_router.py -x -q` | ✅ | ✅ green |
| 04-02-04 | 02 | 1 | ADM-04 | — | N/A | integration | `uv run pytest tests/markets/test_admin_router.py -x -q` | ✅ | ✅ green |
| 04-02-05 | 02 | 1 | ADM-07 | — | 423 Locked response | integration | `uv run pytest tests/markets/test_admin_router.py -x -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/markets/__init__.py` — test package
- [x] `tests/markets/conftest.py` — shared fixtures (admin user, async session, test market factory)
- [x] `tests/markets/test_models.py` — model unit tests (18 tests)
- [x] `tests/markets/test_admin_router.py` — admin API integration tests (11 tests)
- [x] `tests/markets/test_public_router.py` — public API integration tests (5 tests)
- [x] `tests/markets/test_service.py` — service layer tests (15 tests)
- [x] `tests/markets/test_protocol.py` — MarketSource protocol tests (6 tests)

*56 total tests passing in ~10s.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ✅ complete — 56/56 tests green
