---
phase: 6
slug: polymarket-sync-catalog-replication
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-28
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `backend/pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `cd backend && uv run pytest tests/polymarket/ -x -q` |
| **Full suite command** | `cd backend && uv run pytest --tb=short` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/polymarket/ -x -q`
- **After every plan wave:** Run `cd backend && uv run pytest --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | MKT-01 | — | N/A | unit | TBD | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MKT-02 | — | N/A | unit | TBD | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MKT-05 | — | N/A | unit | TBD | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MKT-06 | — | N/A | unit | TBD | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/polymarket/` — test directory for Polymarket integration tests
- [ ] `backend/tests/polymarket/conftest.py` — shared fixtures (VCR cassettes, mock Gamma responses)
- [ ] `backend/tests/polymarket/test_gamma_client.py` — Gamma client unit tests
- [ ] `backend/tests/polymarket/test_parser.py` — Pydantic parser + state machine tests
- [ ] `backend/tests/polymarket/test_adapter.py` — PolymarketAdapter Protocol conformance tests
- [ ] `backend/tests/polymarket/test_tasks.py` — Celery task tests (poll + snapshot)

*Existing pytest infrastructure covers framework installation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Market cards display correctly on home page | MKT-01 | Visual UI verification | Load home page, verify house markets appear first, Polymarket markets below with source badge |
| Source badge links to Polymarket | MKT-01 | External link verification | Click "Polymarket" badge on a synced market card, verify it opens correct polymarket.com URL |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
