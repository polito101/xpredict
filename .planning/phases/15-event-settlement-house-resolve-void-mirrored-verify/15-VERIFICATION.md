---
phase: 15-event-settlement-house-resolve-void-mirrored-verify
verified: 2026-06-05T00:00:00Z
status: passed
score: 13/13 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 15: Event Settlement (House Resolve/Void + Mirrored Verify) Verification Report

**Phase Goal:** A multi-outcome event settles correctly and idempotently by looping the proven per-market `SettlementService`, with void/reverse paths and a derived status — and mirrored event children auto-settle with no new settlement code.
**Verified:** 2026-06-05T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

The phase goal is achieved. `EventService` in `backend/app/settlement/event_service.py` (the single new production file) orchestrates resolve/void/reverse by looping the unchanged `SettlementService` per child on fresh sessions, `derive_event_status` is a column-free pure projection, and mirrored children auto-settle via the unchanged `detect_polymarket_resolutions` path (verified, not rebuilt). All 28 tests pass; the ledger integrity gate (`drift_count == 0`) is asserted after every resolution path.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `derive_event_status([])` returns `"open"` (empty event is open) | VERIFIED | `event_service.py:111-112`: `if not children: return "open"`; confirmed by `test_empty_event_is_open` (8 passed pure unit tests) |
| 2 | `derive_event_status` returns `"open"` when no child is RESOLVED | VERIFIED | `event_service.py:113-116`: `resolved = [c for c in children if c.status == MarketStatus.RESOLVED.value]; if n_resolved == 0: return "open"`; `test_no_resolved_children_is_open` |
| 3 | `derive_event_status` returns `"partially_resolved"` when >=1 child RESOLVED and >=1 unresolved | VERIFIED | `event_service.py:117-118`: `if n_resolved < n_total: return "partially_resolved"`; `test_partial_resolution_is_partially_resolved` |
| 4 | `derive_event_status` returns `"resolved"` when all children RESOLVED with exactly one YES winner | VERIFIED | `event_service.py:122`: `return "resolved" if any(c.is_yes_winner for c in resolved) else "void"`; `test_all_resolved_one_yes_winner_is_resolved` |
| 5 | `derive_event_status` returns `"void"` when all children RESOLVED and none won YES | VERIFIED | Same line as T4, else branch; `test_all_resolved_no_yes_winner_is_void` |
| 6 | Resolving a house event settles the winning child on its YES outcome and every other child on its NO outcome, each on its own fresh session | VERIFIED | `event_service.py:480-500` (`_settle_children`): `async with session_maker() as child_session:` per child; winner gets `winning_outcome_id` (YES), losers get `_no_outcome_id`; `test_resolve_event_settles_all_children` asserts correct balances + bet statuses + market RESOLVED |
| 7 | Re-running resolve over the same event is a true no-op (idempotent replay; no double-credit) | VERIFIED | `test_resolve_event_is_idempotent`: second pass finds SETTLED bets (no PENDING), `children_failed == ()`, balances unchanged, `drift_count == 0`; the 23505 dangling-tx canary |
| 8 | Voiding a house event settles EVERY child on its NO outcome (YES bettors lose, NO bettors win) — not a stake refund | VERIFIED | `event_service.py:350-353`: every child mapped to `_no_outcome_id`; `test_void_event_settles_every_child_on_no` asserts YES bettors lose stake, NO bettors receive payout, `result.status == "void"`, `drift_count == 0` |
| 9 | A child failure leaves already-settled siblings intact, surfaces the failed child(ren), and the event derives to `partially_resolved`; re-run finishes | VERIFIED | `event_service.py:491-500`: `except Exception`: log + append + `continue`; `test_resolve_event_partial_failure_lands_partially_resolved`: monkeypatched one child failure, siblings settled, `result.status == "partially_resolved"`, re-run completes, no double-credit, `drift_count == 0` |
| 10 | `EventService` raises on a `source=POLYMARKET` group and on a blank/whitespace justification | VERIFIED | `_reject_if_mirrored` (line 193) and `_require_justification` (line 182) guards; `test_resolve_event_rejects_mirrored_group`, `test_void_event_rejects_mirrored_group`, `test_event_service_rejects_mirrored_reverse`, `test_resolve_event_rejects_blank_justification`, `test_void_event_rejects_blank_justification`, `test_reverse_event_rejects_blank_justification` |
| 11 | An `event.resolved` / `event.voided` audit row is written in its own transaction with actor + group_id + justification | VERIFIED | `event_service.py:581-596` (`_record_event_audit`): `async with session_maker() as audit_session, audit_session.begin():`; `test_resolve_event_writes_event_audit` and `test_void_event_settles_every_child_on_no` both assert audit row with correct payload fields |
| 12 | `reverse_event` loops `SettlementService.reverse_settlement` over every already-settled child on a fresh session, restoring pre-settlement state; idempotent; per-child balance floor isolates failures; writes `event.reversed` audit row; rejects mirrored groups | VERIFIED | `event_service.py:504-543` (`_reverse_children`): same fresh-session idiom; `test_reverse_event_restores_pre_settlement_state` (balances + bet statuses + CLOSED markets), `test_reverse_event_is_idempotent` (no-op second pass), `test_reverse_event_per_child_balance_floor` (failed child surfaced, siblings reversed, `drift_count == 0`), `test_reverse_event_writes_audit`, `test_event_service_rejects_mirrored_reverse` |
| 13 | A mirrored (POLYMARKET) market_group's children auto-settle through the UNCHANGED `detect_polymarket_resolutions` path — verified, not rebuilt (EVA-06) | VERIFIED | `backend/app/integrations/polymarket/tasks.py`: 0 diff vs e9a4ac4 (confirmed `git diff --quiet e9a4ac4 HEAD -- backend/app/integrations/polymarket/tasks.py` exits 0); `test_mirrored_event_children_auto_settle_via_detect` drives `_run_detect_resolutions(session_override, redis_override)`, asserts both children RESOLVED with correct bet outcomes and `resolution_source == "POLYMARKET_UMA"`, `drift_count == 0`; `EventService` is never invoked on the mirrored path |

**Score: 13/13 truths verified**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/settlement/event_service.py` | Pure `derive_event_status` + `ChildStatus` + `EventService.resolve_event` + `void_event` + `reverse_event` (all three required requirements) | VERIFIED | 620-line file; all three classmethods present; `ChildStatus` `@dataclass(frozen=True, slots=True)`; `derive_event_status` pure free function; no `AsyncSession` in production scope (only `TYPE_CHECKING`); no migration; no status/winning_outcome column on `market_groups` |
| `backend/tests/settlement/test_derive_event_status.py` | 5+ pure unit tests, no Docker, no `pytest.mark.integration` | VERIFIED | 8 pure sync tests; no Docker dependency; `void` edge case covered; all 8 passed confirmed |
| `backend/tests/settlement/test_event_service.py` | Integration tests with `_seed_house_event`, committed sessions, `pytest.mark.integration`, spike-004 gate after every path | VERIFIED | 18 async integration tests; `pytest.mark.integration` present; `_assert_ledger_clean()` called at lines 394, 460, 511, 560, 583, 706, 815, 857, 922; `_seed_house_event` builds `MarketGroup` + N child markets with YES/NO outcomes |
| `backend/tests/settlement/test_event_mirrored.py` | EVA-06 verify: `_run_detect_resolutions` settles mirrored event children; `EventService.reverse_event` rejects POLYMARKET group | VERIFIED | 2 tests; `_run_detect_resolutions(redis_override, session_override)` idiom; title-case `"Yes"`/`"No"` labels (Pitfall 2 guard); `drift_count == 0` gate; no `EventService` invocation on the mirrored settle path |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `event_service.py` | `app.settlement.service.SettlementService.resolve_market` | per-child loop on fresh `_get_session_maker()` session | WIRED | `event_service.py:483-490`; `SettlementService.resolve_market` called inside `async with session_maker() as child_session:` |
| `event_service.py` | `app.settlement.service.SettlementService.reverse_settlement` | per-settled-child loop on fresh session | WIRED | `event_service.py:527-531`; `SettlementService.reverse_settlement` called inside `async with session_maker() as child_session:` |
| `event_service.py` | `app.db.session._get_session_maker` | fresh session per child (23505 dangling-tx avoidance) | WIRED | `event_service.py:57` import; called at lines 236, 341, 419 in all three classmethods |
| `event_service.py` | `app.core.audit.service.AuditService.record` | event-level audit row in its own `begin()` | WIRED | `event_service.py:583-596`; `AuditService.record` inside `async with session_maker() as audit_session, audit_session.begin():`; event types `"event.resolved"`, `"event.voided"`, `"event.reversed"` all present |
| `test_event_mirrored.py` | `app.integrations.polymarket.tasks._run_detect_resolutions` | `session_override`/`redis_override` injection over a POLYMARKET `market_group`'s children | WIRED | `test_event_mirrored.py:59` import; `test_event_mirrored.py:443` call |
| `event_service.py` | `app.markets.enums.MarketStatus.RESOLVED` | `RESOLVED` comparison in `derive_event_status` | WIRED | `event_service.py:113`: `c.status == MarketStatus.RESOLVED.value` |
| `event_service.py` | `app.markets.enums.MarketSourceEnum.POLYMARKET` | mirrored-reject gate | WIRED | `event_service.py:193`: `group.source == MarketSourceEnum.POLYMARKET.value` |

### Data-Flow Trace (Level 4)

`event_service.py` contains no UI rendering components. The module is a service layer — it orchestrates data flow from the ORM to `SettlementService` to the double-entry ledger. Data-flow verification is fully covered by the integration tests which assert committed DB state (wallet balances, bet statuses, audit rows, market status) after each operation.

Key flow integrity: `derive_event_status` reads from committed `Market.status` + `Market.winning_outcome_id` (re-loaded via `_derive_status` after each settlement loop), not from any cached or stub value.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `derive_event_status([])` returns `"open"` | `uv run python -c "from app.settlement.event_service import derive_event_status; print(derive_event_status([]))"` | `open` | PASS |
| `EventService` has all three required classmethods | `uv run python -c "from app.settlement.event_service import EventService; assert all(hasattr(EventService, m) for m in ['resolve_event','void_event','reverse_event']); print('ok')"` | `ok` | PASS |
| Pure unit tests pass without Docker | `uv run pytest tests/settlement/test_derive_event_status.py -q` | `8 passed in 0.58s` | PASS |

### Probe Execution

No probe scripts defined or conventional for this phase type (service-only, no CLI/migration scripts).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| EVT-06 | 15-01-PLAN.md | Event status (open/partially_resolved/resolved/void) derived from constituent markets — never stored authoritative column | SATISFIED | `derive_event_status` pure projection in `event_service.py:98-122`; `MarketGroup` has no `status`/`winning_outcome` column (migration 0011, unchanged); 8 unit tests covering all four states |
| EVA-03 | 15-02-PLAN.md | Admin resolves a house event; loops `SettlementService` per child (winner→YES, losers→NO), idempotently | SATISFIED | `EventService.resolve_event` classmethod; winner first, losers by `market.id`; CR-01 guard (winning_outcome must be YES leg); idempotent replay confirmed by integration test |
| EVA-04 | 15-02-PLAN.md | Admin voids a house event; every child resolves on NO (YES bettors lose, NO bettors win) — NOT a stake refund | SATISFIED | `EventService.void_event` classmethod; every child mapped to `_no_outcome_id`; `test_void_event_settles_every_child_on_no` asserts no refund semantics (`void` status, YES bettors lose stake) |
| EVA-05 | 15-03-PLAN.md | Admin reverses event resolution via compensating ledger entries (mirrors STL-07), audit-logged | SATISFIED | `EventService.reverse_event` classmethod; loops `SettlementService.reverse_settlement`; per-child balance floor isolation; `event.reversed` audit row; `drift_count == 0` on all reverse paths |
| EVA-06 | 15-03-PLAN.md | Mirrored (Polymarket) events read-only except emergency force-settle; children auto-settle via existing UMA detection (verify, no new code) | SATISFIED | `tasks.py` 0 diff confirmed; all three `EventService` methods reject `source=POLYMARKET`; `test_mirrored_event_children_auto_settle_via_detect` drives the unchanged `_run_detect_resolutions` path and asserts `resolution_source == "POLYMARKET_UMA"` |

### Anti-Patterns Found

No blockers or warnings found.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | No TBD/FIXME/XXX markers; no empty implementations; no hardcoded stub data in production paths; no return null/return {}/return [] in settlement logic |

**Code review findings (all resolved in commit 5c2add9):**
- CR-01 (BLOCKER, now fixed): `resolve_event` now rejects a non-YES `winning_outcome_id` via the `_yes_outcome_id` cross-check
- WR-01 (now fixed): `_settle_children` / `_reverse_children` log exceptions with traceback (`logger.exception`)
- WR-02 (now fixed): `test_reverse_event_rejects_blank_justification` added
- WR-03 (now fixed): `test_resolve_event_rejects_no_outcome_as_winner` added
- WR-04 (now fixed): `_record_event_audit` logs with traceback before re-raising; comment documents the action-then-audit trade-off
- IN-01 / IN-02 (info, deferred non-blocking): opaque `scalar_one()` context and test-helper deduplication

### Pitfall Coverage (from 15-RESEARCH.md)

| Pitfall | Description | Status |
|---------|-------------|--------|
| Pitfall 1 — 23505 dangling-tx | Two settle calls on one session | AVOIDED: fresh `async with session_maker() as child_session:` per child in all three methods |
| Pitfall 2 — case-insensitive YES/NO | Mirrored labels are title-case "Yes"/"No" | AVOIDED: `func.upper(Outcome.label) == "YES"` in both helpers; title-case labels in `test_event_mirrored.py` |
| Pitfall 3 — per-child balance floor | `CHECK(balance>=0)` floor hits must roll back that child only | AVOIDED: Option A per-child sessions; `test_reverse_event_per_child_balance_floor` proves isolation |
| Pitfall 4 — FOR UPDATE lock ordering | Must not add new locks on top of SettlementService | HONORED: no lock logic in `event_service.py`; delegates to `SettlementService` |
| Pitfall 5 — rolled-back fixture | Committed state needed for act + assert | HONORED: all integration tests use `_get_session_maker()` committed sessions, NOT the `async_session` fixture |
| Pitfall 6 — re-resolve-after-reverse | `settle:{bet_id}:{leg}` key collision on 23505 | SCOPED OUT: `reverse_event` docstring explicitly flags the deferred limitation; no re-resolve test written |

### Human Verification Required

None — all must-haves are verifiable from code inspection and per-module test results. The phase ships service + tests only (no HTTP endpoints, no UI). The Linux CI full suite (Docker + testcontainers) is the authoritative test runner for the integration tests.

### Gaps Summary

No gaps. The phase goal is fully achieved:

1. `derive_event_status` is a pure, stdlib-only, column-free projection over the four mandated states (`open` / `partially_resolved` / `resolved` / `void`) with 8 exhaustive unit tests passing without Docker.
2. `EventService.resolve_event` / `void_event` / `reverse_event` compose the unchanged `SettlementService` per-child on fresh `AsyncSession`s (Option A); idempotent; best-effort with partial-failure surfacing; mirrored-reject and blank-justification guards on all three methods; event-level audit rows in their own transactions.
3. The spike-004 double-entry integrity check (`drift_count == 0`) is asserted after every resolution path in the integration suite.
4. `tasks.py` has 0 diff vs the pre-phase commit; the mirrored auto-settle path is verified end-to-end via `test_event_mirrored.py` with `drift_count == 0`.
5. No migration added; no authoritative `status`/`winning_outcome` column on `market_groups`; no new dependencies; no changes to `service.py` / `adapters.py` / `market_port.py` / `plan.py` / `tasks.py`.

---

_Verified: 2026-06-05T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
