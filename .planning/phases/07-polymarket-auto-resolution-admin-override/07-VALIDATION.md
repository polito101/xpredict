---
phase: 7
slug: polymarket-auto-resolution-admin-override
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-28
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.25 |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && uv run pytest tests/polymarket/test_detect_resolution.py tests/settlement/test_force_settle.py -x -v` |
| **Full suite command** | `cd backend && uv run pytest -x -v` |
| **Estimated runtime** | ~60 seconds (integration: testcontainers Postgres) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/polymarket/test_detect_resolution.py tests/settlement/test_force_settle.py -x`
- **After every plan wave:** Run `cd backend && uv run pytest -x -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-T1 | 01 | 1 | STL-01 | — | `uma_resolved_at` nullable column on markets; alembic upgrade succeeds | migration | `cd backend && uv run alembic upgrade head` | ❌ W0 | ⬜ pending |
| 07-01-T2 | 01 | 1 | STL-01 | — | `POLYMARKET_GRACE_PERIOD_MINUTES` in Settings; `.env.example` updated | unit | `pytest tests/core/test_config.py -k grace` | ❌ W0 | ⬜ pending |
| 07-02-T1 | 02 | 2 | STL-01 | — | Candidate query returns expired POLYMARKET markets only | unit | `pytest tests/polymarket/test_detect_resolution.py::test_candidate_query_returns_expired_markets` | ❌ W0 | ⬜ pending |
| 07-02-T2 | 02 | 2 | STL-01 | — | `closed=true + umaResolutionStatus='proposed'` → no settlement (SC#3) | unit | `pytest tests/polymarket/test_detect_resolution.py::test_closed_proposed_not_settled` | ❌ W0 | ⬜ pending |
| 07-02-T3 | 02 | 2 | STL-01 | — | Grace period gates settlement (start clock first tick, settle on subsequent tick after elapsed) | unit | `pytest tests/polymarket/test_detect_resolution.py::test_grace_period_triggers_resolution` | ❌ W0 | ⬜ pending |
| 07-02-T4 | 02 | 2 | STL-01 | — | `resolve_market()` called with `actor_user_id=None` (system resolution); winner label mapped correctly | integration | `pytest tests/polymarket/test_detect_resolution.py::test_auto_resolution_settles_correctly` | ❌ W0 | ⬜ pending |
| 07-02-T5 | 02 | 2 | STL-01 | — | Stub retirement: `detect_resolution` no longer returns None | unit | `pytest tests/polymarket/test_adapter.py -k detect_resolution` | ✅ (replace) | ⬜ pending |
| 07-02-T6 | 02 | 2 | STL-01 | — | Beat schedule entry `detect-polymarket-resolutions` (60s) present in celery_app | unit | `pytest tests/polymarket/test_detect_resolution.py::test_beat_schedule_registered` | ❌ W0 | ⬜ pending |
| 07-03-T1 | 03 | 3 | ADM-06 | T-07-01 | Force-settle rejects non-POLYMARKET markets (404) | unit | `pytest tests/settlement/test_force_settle.py::test_force_settle_rejects_house_market` | ❌ W0 | ⬜ pending |
| 07-03-T2 | 03 | 3 | ADM-06 | T-07-01 | Force-settle requires `is_admin=true` (403 for players) | unit | `pytest tests/settlement/test_force_settle.py::test_force_settle_requires_admin` | ❌ W0 | ⬜ pending |
| 07-03-T3 | 03 | 3 | ADM-06 | T-07-01 | Force-settle writes `polymarket_admin_override` audit entry with `uma_status_at_override_time` | integration | `pytest tests/settlement/test_force_settle.py::test_force_settle_audit_entry` | ❌ W0 | ⬜ pending |
| 07-03-T4 | 03 | 3 | ADM-06 | T-07-01 | Force-settle idempotency: second call on resolved market is a no-op | integration | `pytest tests/settlement/test_force_settle.py::test_force_settle_idempotent` | ❌ W0 | ⬜ pending |
| 07-04-T1 | 04 | 4 | STL-01 | — | Reversal after auto-settlement: compensating entries restore balances; audit chains back | integration | `pytest tests/polymarket/test_detect_resolution.py::test_reversal_after_auto_settlement` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/polymarket/test_detect_resolution.py` — scaffold test file; covers STL-01 SC#1–3, SC#6; imports and stubs for Wave 0 validation
- [ ] `tests/settlement/test_force_settle.py` — scaffold test file; covers ADM-06 SC#5; imports and stubs for Wave 0 validation
- [ ] `alembic/versions/0007_phase7_grace_period.py` — adds `uma_resolved_at` column to `markets` table (nullable, no default); must chain from `0006_merge_phase5_phase6`
- [ ] `app/core/config.py` — `POLYMARKET_GRACE_PERIOD_MINUTES: int = 30` setting

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Player sees "Polymarket UMA" attribution on auto-resolved market detail page | STL-01 (SC#4) | Frontend display layer; Phase 7 is primarily backend | Load a resolved Polymarket market in the UI; verify resolver attribution shows "Polymarket UMA" not "Operator: admin" |
| Force-settle two-step confirm flow in admin UI | ADM-06 | Frontend UX concern; API is the gate | POST `/admin/markets/{id}/force-settle` directly; frontend confirm step is deferred to Phase 8/9 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
