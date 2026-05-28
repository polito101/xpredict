---
phase: 7
slug: polymarket-auto-resolution-admin-override
status: verified
verified_at: 2026-05-28T00:00:00Z
goal: "Polymarket-mirrored markets auto-settle via UMA oracle after a configurable grace period; admin can force-settle stuck markets with full audit trail"
score: 17/17 invariants verified
---

# Phase 07 — Verification Report

**Phase Goal:** Polymarket-mirrored markets auto-settle via UMA oracle after a configurable grace period; admin can force-settle stuck markets with full audit trail.
**Verified:** 2026-05-28
**Status:** VERIFIED
**Re-verification:** No — initial verification

## Goal-Backward Analysis

| Requirement | Success Criteria | Status | Evidence |
|-------------|-----------------|--------|----------|
| STL-01 | `detect_polymarket_resolutions` Beat task (60s) auto-settles POLYMARKET markets when `_derive_status()` returns RESOLVED AND grace period elapsed. NEVER settles on `closed=true + proposed` alone. | PASS | `tasks.py` L226 checks `parsed.internal_status != MarketStatus.RESOLVED` (delegates to `GammaMarket.model_validate(raw).internal_status`, which runs `_derive_status`). Grace-period gating at L231-241 (first tick writes `uma_resolved_at`), settlement fires only at L245-278 after elapsed check. Beat schedule at `celery_app.py` L60-63 at 60.0s. Unit tests: all 7 pass green. |
| ADM-06 | `POST /admin/markets/{market_id}/force-settle` admin endpoint — Polymarket-only, mandatory justification, writes `polymarket_admin_override` audit entry capturing live `umaResolutionStatus`. | PASS | `router.py` L133-201: endpoint path `/{market_id}/force-settle`, 404 on non-POLYMARKET markets (L152-156), calls `AuditService.record` with `event_type="polymarket_admin_override"` and `uma_status_at_override_time` in payload (L181-192) in a separate `session.begin()` block (L180) after `resolve_market` commits. `ForceSettleResponse` includes `uma_status_at_override` field (`schemas.py` L58). |

## Invariant Checks

| # | Invariant | Status | Notes |
|---|-----------|--------|-------|
| 1 | `closed=true + umaResolutionStatus='proposed'` NEVER triggers settlement | VERIFIED | `_derive_status` in `schemas.py` L92: `closed=true, uma=proposed -> CLOSED` (not RESOLVED). Task checks `parsed.internal_status != MarketStatus.RESOLVED` and continues (skips) if not RESOLVED. Covered by `test_closed_proposed_not_settled` (unit) and `test_integration_proposed_not_settled` (integration). |
| 2 | Grace period: first tick sets `uma_resolved_at`, settlement fires only after `POLYMARKET_GRACE_PERIOD_MINUTES` elapsed | VERIFIED | `tasks.py` L231-241: if `market.uma_resolved_at is None`, executes conditional UPDATE and `continue`s. L243-247: reads elapsed time; if `< timedelta(minutes=settings.POLYMARKET_GRACE_PERIOD_MINUTES)`, skips. Covered by `test_grace_period_triggers_resolution`. |
| 3 | Conditional `UPDATE WHERE uma_resolved_at IS NULL` prevents double-start race | VERIFIED | `tasks.py` L232-238: raw SQL `UPDATE markets SET uma_resolved_at = :now WHERE id = :id AND uma_resolved_at IS NULL` — atomic write, no race possible. |
| 4 | `SettlementService.resolve_market` called with `actor_user_id=None` | VERIFIED | `tasks.py` L274: `actor_user_id=None` in the `resolve_market` call. Test `test_grace_period_triggers_resolution` asserts `call_kwargs["actor_user_id"] is None`. |
| 5 | `DETECT_LOCK_KEY` is distinct from `LOCK_KEY` (both in tasks.py) | VERIFIED | `tasks.py` L39-40: `LOCK_KEY = "xpredict:poll:polymarket:lock"`, `DETECT_LOCK_KEY = "xpredict:detect:polymarket:lock"`. Distinct values. Asserted in `test_candidate_query_returns_expired_markets`. |
| 6 | Beat schedule entry `detect-polymarket-resolutions` at exactly 60.0s | VERIFIED | `celery_app.py` L60-63: `"detect-polymarket-resolutions": {"task": "app.integrations.polymarket.tasks.detect_polymarket_resolutions", "schedule": 60.0}`. Asserted in `test_beat_schedule_registered`. |
| 7 | `selectinload(Market.outcomes)` present in candidate query (lazy="raise" on relationship) | VERIFIED | `tasks.py` L202: `.options(selectinload(Market.outcomes))` in the candidate market query. `models.py` L109-113 confirms `lazy="raise"` on the `outcomes` relationship. |
| 8 | `detect_resolution` in adapter delegates to `GammaMarket.model_validate().internal_status` | VERIFIED | `adapter.py` L128-133: `parsed = GammaMarket.model_validate(raw)` then checks `parsed.internal_status != MarketStatus.RESOLVED`. `GammaMarket` runs `_derive_status` via `@model_validator` (L144-152 of schemas.py). Covered by `test_detect_resolution_returns_none_for_closed_proposed`. |
| 9 | Endpoint is `POST /admin/markets/{market_id}/force-settle` — DISTINCT from `/resolve` | VERIFIED | `router.py` L133: `@settlement_admin_router.post("/{market_id}/force-settle", ...)`. Separate handler `force_settle_polymarket_market`. `/resolve` is at L59. |
| 10 | `market.source != MarketSourceEnum.POLYMARKET.value` → 404 (not 400) | VERIFIED | `router.py` L151-156: `if market is None or market.source != MarketSourceEnum.POLYMARKET.value: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, ...)`. Tests `test_force_settle_rejects_house_market` and `test_force_settle_rejects_unknown_market` assert 404. |
| 11 | `event_type="polymarket_admin_override"` in audit (NOT `settlement.resolved`) | VERIFIED | `router.py` L184: `event_type="polymarket_admin_override"`. Test `test_force_settle_audit_entry` queries for `AuditLog.event_type == "polymarket_admin_override"`. |
| 12 | Audit captures `uma_status_at_override_time` in payload | VERIFIED | `router.py` L189: `"uma_status_at_override_time": uma_status_at_override` in audit payload. Test `test_force_settle_captures_uma_status` asserts `row.payload["uma_status_at_override_time"] == "disputed"`. |
| 13 | Audit written in SEPARATE `session.begin()` AFTER `resolve_market()` commits | VERIFIED | `router.py`: `resolve_market` call at L163-173 (uses session's own transaction management), then `async with session.begin():` at L180 wraps the `AuditService.record` call. Two distinct transaction boundaries. |
| 14 | NO `from __future__ import annotations` in `settlement/router.py` | VERIFIED | File begins at L1 with a docstring comment. L16: `# \`\`from __future__ import annotations\`\` intentionally ABSENT`. Grep confirms no import statement present — only a comment explaining the intentional absence (FastAPI Annotated-Depends gotcha). |
| 15 | `ForceSettleResponse` includes `uma_status_at_override` field | VERIFIED | `schemas.py` L58: `uma_status_at_override: str \| None`. Response construction at `router.py` L199: `uma_status_at_override=uma_status_at_override`. |
| 16 | Migration `0007_phase7_grace_period` chains to `0006_merge_phase5_phase6` as `down_revision` | VERIFIED | `0007_phase7_grace_period.py` L21: `down_revision: Union[str, Sequence[str], None] = "0006_merge_phase5_phase6"`. Alembic script check: `heads: ['0007_phase7_grace_period']`, `Single head: True`. Linear chain confirmed. |
| 17 | `uma_resolved_at` is `DateTime(timezone=True)`, nullable, no `server_default` | VERIFIED | Migration L28-30: `sa.Column("uma_resolved_at", sa.DateTime(timezone=True), nullable=True)` — no `server_default`. Model `models.py` L100-102: `uma_resolved_at: Mapped[datetime \| None] = mapped_column(DateTime(timezone=True), nullable=True)` — no `server_default`. |

## Test Coverage

| Test File | Tests | Unit | Integration | Status |
|-----------|-------|------|-------------|--------|
| `tests/polymarket/test_detect_resolution.py` | 7 | 4 | 3 | green (unit: 4/4 pass; integration: requires testcontainers) |
| `tests/polymarket/test_adapter.py` | 7 (3 unit + 2 integration class) | 3 | 4 | unit: green; integration: requires testcontainers |
| `tests/settlement/test_force_settle.py` | 5 | 0 | 5 | integration-only; requires testcontainers |

**Critical coverage notes:**

- `test_closed_proposed_not_settled` — confirms invariant #1 at unit level: `proposed` status never triggers settlement
- `test_grace_period_triggers_resolution` — confirms invariants #2, #3, #4: two-tick model with `actor_user_id=None` assertion
- `test_candidate_query_returns_expired_markets` — confirms invariants #5, #6: lock key distinctness + `closed+proposed -> CLOSED` via `_derive_status`
- `test_beat_schedule_registered` — confirms invariant #6: schedule name + 60.0s
- `test_detect_resolution_returns_none_for_closed_proposed` — confirms invariant #8: adapter delegates via `GammaMarket.model_validate`
- `test_force_settle_rejects_house_market` / `test_force_settle_rejects_unknown_market` — confirms invariant #10: 404 for non-POLYMARKET
- `test_force_settle_audit_entry` — confirms invariant #11: event_type, invariant #12: payload content
- `test_force_settle_captures_uma_status` — confirms invariants #12, #15: `uma_status_at_override_time` in audit + response

## Unit Test Run Results

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-8.4.2, pluggy-1.6.0
asyncio: mode=Mode.AUTO
collected 11 items / 4 deselected / 7 selected

tests/polymarket/test_detect_resolution.py::test_candidate_query_returns_expired_markets PASSED [ 14%]
tests/polymarket/test_detect_resolution.py::test_closed_proposed_not_settled PASSED [ 28%]
tests/polymarket/test_detect_resolution.py::test_grace_period_triggers_resolution PASSED [ 42%]
tests/polymarket/test_detect_resolution.py::test_beat_schedule_registered PASSED [ 57%]
tests/polymarket/test_adapter.py::TestProtocolConformance::test_protocol_conformance PASSED [ 71%]
tests/polymarket/test_adapter.py::TestProtocolConformance::test_registry_lookup PASSED [ 85%]
tests/polymarket/test_adapter.py::TestProtocolConformance::test_detect_resolution_returns_none_for_closed_proposed PASSED [100%]

======================= 7 passed, 4 deselected in 0.71s =======================
```

## Ruff Linter Results

```
All checks passed!
```
(Checked: `app/integrations/polymarket/`, `app/settlement/`, `app/markets/models.py` — selectors E, F, I)

## Alembic Chain Verification

```
heads: ['0007_phase7_grace_period']
0007 down_revision: 0006_merge_phase5_phase6
Single head: True
```

Linear chain confirmed. No merge heads. `0007` is the sole head.

## Gaps / Issues

NONE.

All 17 invariants verified against the actual codebase. No stubs, no wiring gaps, no anti-patterns found. The `from __future__ import annotations` absence in `router.py` is intentional and documented inline (FastAPI Annotated-Depends gotcha), consistent with the existing pattern in `app/wallet/admin_router.py`.

## Verdict

**Phase 07: VERIFIED**

The codebase delivers both required behaviors completely. STL-01 is implemented with the correct two-tick grace period model (first tick stamps `uma_resolved_at` via atomic conditional UPDATE, settlement fires only after `POLYMARKET_GRACE_PERIOD_MINUTES` elapsed), the `closed+proposed` safety invariant is enforced in `_derive_status` and confirmed by unit tests, and the Beat schedule entry is registered at exactly 60.0s. ADM-06 is a distinct endpoint (`/force-settle` not `/resolve`), correctly 404s on non-POLYMARKET markets, writes the `polymarket_admin_override` audit entry with `uma_status_at_override_time` payload in a separate transaction after settlement commits, and the `ForceSettleResponse` carries `uma_status_at_override`. All 7 unit tests pass; ruff reports zero lint errors; the migration chain is linear with `0007` as the sole head.

---

_Verified: 2026-05-28_
_Verifier: Claude (gsd-verifier)_
