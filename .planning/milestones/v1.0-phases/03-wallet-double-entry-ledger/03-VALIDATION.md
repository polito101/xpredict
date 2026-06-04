---
phase: 3
slug: wallet-double-entry-ledger
status: draft
nyquist_compliant: true
wave_0_complete: true
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
| 03-01-T1 | 03-01 | 1 | WAL-06 | T-03-03 | Money columns NUMERIC(18,4)/Mapped[Money]; no float | lint+import | `python scripts/lint_money_columns.py` | ❌ Wave 0 | ⬜ pending |
| 03-01-T2 | 03-01 | 1 | WAL-06, WAL-08 | T-03-01,T-03-02 | CHECK>=0 + immutability trigger/REVOKE | migration | `alembic history` single head | ❌ Wave 0 | ⬜ pending |
| 03-01-T3 | 03-01 | 1 | WAL-06, WAL-08 | T-03-01,T-03-02,T-03-04 | DB rejects neg balance + UPDATE/DELETE + dup key | integration | `pytest tests/wallet/test_models.py tests/wallet/test_migration_0003.py -x` | ❌ Wave 0 | ⬜ pending |
| 03-02-T1 | 03-02 | 2 | WAL-07 | T-03-06,T-03-07,T-03-09,T-03-10 | FOR UPDATE + 23505 idempotency + canonical lock; create_wallet no-commit | import+grep | `ruff check app/wallet/service.py` + signature check | ❌ Wave 0 | ⬜ pending |
| 03-02-T2 | 03-02 | 2 | WAL-07 | T-03-06,T-03-07,T-03-08 | 50 concurrent: drift 0, balance exact; fault rolls back | integration | `pytest tests/wallet/test_concurrent_transfers.py tests/wallet/test_idempotency.py tests/wallet/test_atomicity.py -x` | ❌ Wave 0 | ⬜ pending |
| 03-03-T1 | 03-03 | 3 | WAL-01 | T-03-11 | Wallet co-inserted in user tx (UserManager.create) | unit+grep | `pytest -m 'not integration' tests/auth -q` | ✅ tests/auth | ⬜ pending |
| 03-03-T2 | 03-03 | 3 | WAL-01 | T-03-11,T-03-12 | Register -> 1 wallet same tx; failure rolls back user | integration | `pytest tests/wallet/test_wallet_creation.py -x` | ❌ Wave 0 | ⬜ pending |
| 03-04-T1 | 03-04 | 3 | WAL-09 | T-03-13,T-03-16,T-03-17 | Admin-gated recharge; Idempotency-Key header; money string; audited | import+route | `ruff check` + route-list assert | ❌ Wave 0 | ⬜ pending |
| 03-04-T2 | 03-04 | 3 | WAL-09 | T-03-13,T-03-14 | Idempotent recharge; credited once; admin-only | integration | `pytest tests/wallet/test_recharge.py -x` | ❌ Wave 0 | ⬜ pending |
| 03-04-T3 | 03-04 | 3 | WAL-09 | T-03-15 | dst_user_id rejected 422; no user->user route/FK | unit+integration | `pytest tests/wallet/test_no_user_to_user.py -x` | ❌ Wave 0 | ⬜ pending |
| 03-05-T1 | 03-05 | 4 | WAL-03, WAL-04 | T-03-18,T-03-19 | Self-scoped reads; MoneyStr; pagination | import+route | `ruff check` + route-list assert | ❌ Wave 0 | ⬜ pending |
| 03-05-T2 | 03-05 | 4 | WAL-03, WAL-04, PLT-05 | T-03-19,T-03-20 | Raw JSON money is string; stripe stub raises | unit+integration | `pytest tests/wallet/test_money_serialization.py tests/wallet/test_stripe_stub.py -x` | ❌ Wave 0 | ⬜ pending |
| 03-05-T3 | 03-05 | 4 | PLT-05 | T-03-20 | Disabled Add funds button present | frontend | `pnpm test:run -- src/app/wallet` | ❌ Wave 0 | ⬜ pending |
| 03-06-T1 | 03-06 | 3 | PLT-09 | T-03-21,T-03-22 | Task registered+scheduled; sync wraps asyncio.run | import+assert | `ruff check` + task/schedule assert | ❌ Wave 0 | ⬜ pending |
| 03-06-T2 | 03-06 | 3 | PLT-09 | T-03-21 | Clean -> INFO; injected drift -> CRITICAL + Sentry | integration | `pytest tests/wallet/test_reconcile.py -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Planner fills. Likely: `backend/tests/test_wallet_ledger.py` + `backend/tests/test_wallet_concurrency.py` (integration, reuses the Spike 002 `asyncio.gather` + invariant-check shape) + shared fixtures in `backend/tests/conftest.py`.*

- [ ] `backend/tests/wallet/__init__.py` + `backend/tests/wallet/conftest.py` (03-01-T3) — wallet fixtures reusing parent engine/async_session
- [ ] `backend/tests/wallet/test_models.py` + `test_migration_0003.py` (03-01-T3) — schema/immutability/CHECK/tenant_id/idempotency
- [ ] `backend/tests/wallet/test_concurrent_transfers.py` (03-02-T2) — SC#2 signature gate, PORT harness run_load/LoadResult
- [ ] `backend/tests/wallet/test_idempotency.py` + `test_atomicity.py` (03-02-T2) — SC#3 + PITFALLS#10 (mirror harness)
- [ ] `backend/tests/wallet/test_wallet_creation.py` (03-03-T2) — SC#1 same-tx + rollback
- [ ] `backend/tests/wallet/test_recharge.py` (03-04-T2) + `test_no_user_to_user.py` (03-04-T3) — SC#3 idempotency + SC#5 firewall
- [ ] `backend/tests/wallet/test_money_serialization.py` + `test_stripe_stub.py` (03-05-T2) — SC#4 + SC#6
- [ ] `frontend/src/app/wallet/__tests__/wallet-page.test.tsx` (03-05-T3) — disabled Add funds button
- [ ] `backend/tests/wallet/test_reconcile.py` (03-06-T2) — SC#7 clean/drift
- Framework install: none (pytest + testcontainers + vitest already in dev deps)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Disabled "Add funds" button visible in player UI | WAL/SC#6 | Visual presence | Load wallet page; confirm button rendered + disabled |

*All money-correctness behaviors (SC#1–#5, #7) have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-complete (all tasks mapped; Nyquist continuity verified — no 3 consecutive tasks without an automated verify; every task has <automated> or a Wave 0 dependency)
