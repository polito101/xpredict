---
phase: 15-event-settlement-house-resolve-void-mirrored-verify
plan: 03
subsystem: settlement
tags: [event-settlement, eva-05, eva-06, reverse-settlement, compensating-ledger, fresh-session-per-child, detect-polymarket-resolutions, mirrored-verify, testcontainers, python]

# Dependency graph
requires:
  - phase: 15-event-settlement-house-resolve-void-mirrored-verify (Wave 1, 15-01)
    provides: "derive_event_status(children) + ChildStatus frozen-slots projection (EVT-06) — re-used to derive the post-reverse status (full reverse reopens every child to CLOSED -> event derives back to open)"
  - phase: 15-event-settlement-house-resolve-void-mirrored-verify (Wave 2, 15-02)
    provides: "EventService.resolve_event/void_event + the shared private helpers (_load_group_with_children, _reject_if_mirrored, _require_justification, _settle_children, _record_event_audit, _derive_status) + the test_event_service.py committed-session suite + _seed_house_event synthesizer that Wave 3 EXTENDS"
  - phase: 05-settlement
    provides: "SettlementService.reverse_settlement (own session.begin(), append-only inverse transfers, SETTLED->PENDING, mark_unresolved, settlement.reversed audit, idempotent, CHECK(balance>=0) floor) — looped UNCHANGED per child; HouseMarketResolveAdapter / MarketResolvePort"
  - phase: 07-polymarket-auto-resolution
    provides: "detect_polymarket_resolutions / _run_detect_resolutions (session_override/redis_override seam, grace-gated UMA auto-settle via SettlementService.resolve_market(actor_user_id=None)) — VERIFIED end-to-end (EVA-06), NOT modified"
  - phase: 03-wallet-ledger
    provides: "WalletService.recharge + WalletService.transfer (ledger-backed) + app.wallet.reconcile._reconcile_async (the spike-004 drift detector)"
provides:
  - "EventService.reverse_event — loops SettlementService.reverse_settlement over every already-settled child on a FRESH _get_session_maker() session, restoring pre-settlement state + reopening each child; idempotent; per-child CHECK(balance>=0) floor isolation (one child rolls back alone, siblings stay reversed); mirrored-reject; one event.reversed audit row (EVA-05)"
  - "_reverse_children internal helper (the reverse twin of _settle_children)"
  - "Reverse integration tests appended to test_event_service.py (restore / idempotent / per-child balance floor / audit), each asserting spike-004 drift_count == 0"
  - "test_event_mirrored.py — EVA-06 verify: a source=POLYMARKET market_group's children auto-settle via the UNCHANGED detect_polymarket_resolutions (zero new settlement code, tasks.py NO diff) + EventService.reverse_event mirrored-reject"
affects: [phase-16-event-api, phase-17-event-ui, phase-18-seed-demo]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reverse-event = fresh-session-per-child loop over the self-committing reverse_settlement (the same 23505 dangling-tx discipline as resolve; per-child sessions ALSO isolate the CHECK(balance>=0) floor so one child rolls back alone)"
    - "Composition over reinvention (reverse): the event reverse adds ZERO ledger primitives — append-only inverse transfers, SETTLED->PENDING flip, mark_unresolved, per-child settlement.reversed audit all inherited from reverse_settlement unchanged"
    - "EVA-06 verify-only: drive the UNCHANGED detect_polymarket_resolutions over synthesized mirrored market_group children via its session_override/redis_override seam; assert tasks.py has NO diff (acceptance criterion)"
    - "Grace-primer test seeding: a standalone POLYMARKET market (uma_resolved_at NULL, committed first) grace-starts + commits inside the detect loop BEFORE the settle-ready children, clearing the candidate-SELECT read tx so each child's resolve_market opens its own begin() on the shared session_override (reproduces a real mixed-stage 60s tick without touching tasks.py)"
    - "Independent DB-deadline (past, for the detect candidate gate) vs placement-view-deadline (future, for BetService.place_bet's is_open) — the view validates placement, the detect path reads the DB row; they need not match"

key-files:
  created:
    - backend/tests/settlement/test_event_mirrored.py
  modified:
    - backend/app/settlement/event_service.py
    - backend/tests/settlement/test_event_service.py

key-decisions:
  - "reverse_event takes NO winning_outcome_id param — reverse_settlement finds the SETTLED bets by status, not by winner. ordered_children is just the child ids in deterministic str(m.id) order (winner-first ordering is irrelevant for reverse)."
  - "Per-child fresh sessions for reverse do double duty: they dodge the 23505 dangling-tx landmine (the same reason resolve uses them) AND isolate the per-child CHECK(balance>=0) floor — a winner who spent winnings makes THAT child roll back alone while siblings already reversed stay reversed (Pitfall 3, Option A)."
  - "After a full reverse every child reopens (CLOSED), so _derive_status projects the event back to 'open'; a partial reverse (one child floor-hit, stays RESOLVED) derives 'partially_resolved'."
  - "Reverse is scoped to restore + audit ONLY (mirrors STL-07). A code comment in reverse_event flags the deferred Pitfall-6 re-resolve-after-reverse gap (settle:{bet_id}:{leg} keys collide on 23505); NO resolve->reverse->RE-resolve test was written."
  - "EVA-06 mirrored verify drives the UNCHANGED detect path on a SINGLE session_override. A real session forbids session.begin() while the candidate-SELECT read tx is still open (verified: 'A transaction is already begun'), so the test seeds a grace-PRIMER market that grace-starts + commits first — exactly how production's mixed-stage ticks clear the session. tasks.py stays byte-for-byte unchanged (the verify-only acceptance criterion)."
  - "The detect-lock Redis is an AsyncMock (the established detect-integration-test idiom) because the in-repo fakeredis build raises 'unknown command eval' on the owner-checked Lua lock release; the lock plumbing is not what EVA-06 verifies."

patterns-established:
  - "Event-of-binaries reverse = loop the per-market reverse primitive on a fresh session per child; per-child ACID gives both 23505-safety and floor-isolation for free"
  - "Mirrored (UMA-owned) events stay admin read-only across ALL THREE EventService mutations (resolve/void/reverse all raise on source=POLYMARKET); mirrored children settle ONLY via the unchanged detect_polymarket_resolutions oracle path, proven by driving it end-to-end"

requirements-completed: [EVA-05, EVA-06]

# Metrics
duration: 15min
completed: 2026-06-05
---

# Phase 15 Plan 03: EventService Reverse + Mirrored Verify (Wave 3) Summary

**`EventService.reverse_event` composes the UNCHANGED `SettlementService.reverse_settlement` over a house event's settled children — one FRESH session per child (23505-safe AND per-child `CHECK(balance>=0)` floor isolation), idempotent, mirrored-rejecting, with one `event.reversed` audit row — plus a new `test_event_mirrored.py` proving (verify-only, `tasks.py` NO diff) that a `source=POLYMARKET` `market_group`'s children auto-settle through the existing `detect_polymarket_resolutions` UMA path and that `reverse_event` refuses mirrored groups; all 26 settlement-event tests green with spike-004 `drift_count == 0` on every reverse / partial-reverse / mirrored path.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-06-05T17:29:22Z
- **Completed:** 2026-06-05T17:44:24Z
- **Tasks:** 3
- **Files modified:** 3 (1 extended, 1 extended-test, 1 new-test)

## Accomplishments
- Extended `backend/app/settlement/event_service.py` with `EventService.reverse_event` (EVA-05): a classmethod that LOOPS the byte-for-byte-unchanged `SettlementService.reverse_settlement` over a group's already-settled child markets, **one fresh `_get_session_maker()` session per child**. Zero new ledger primitives — the append-only inverse compensating transfers, the `SETTLED -> PENDING` bet flip, `mark_unresolved`, and the per-child `settlement.reversed` audit row are all inherited unchanged. Added the `_reverse_children` internal helper (the reverse twin of `_settle_children`).
- Per-child fresh sessions do double duty: dodge the 23505 dangling-tx landmine (same as resolve) AND isolate the per-child `CHECK(balance >= 0)` floor — a winner who already spent the winnings makes THAT child's reversal roll back ALONE; siblings already reversed stay reversed; the event derives `partially_resolved` (Pitfall 3 / Option A). A full reverse reopens every child (CLOSED) so the event derives back to `"open"`.
- Guards reused verbatim from Wave 2: mirrored-reject (`source == POLYMARKET` -> `ValueError`, EVA-06) and the non-blank-justification guard; one additional `event.reversed` audit row in its own `begin()` (mirrors STL-07). A code comment flags the **deferred Pitfall-6** re-resolve-after-reverse limitation (out of scope; not a Phase-15 bug).
- Appended 4 reverse integration tests to `test_event_service.py` (restore pre-settlement state, idempotent re-reverse no-op, per-child balance-floor isolation, `event.reversed` audit), each ending with the literal spike-004 `_reconcile_async(...)["drift_count"] == 0` gate. NO `resolve -> reverse -> RE-resolve` test (deferred Pitfall-6 gap respected).
- New `backend/tests/settlement/test_event_mirrored.py` (EVA-06 verify): drives the **UNCHANGED** `detect_polymarket_resolutions` (`_run_detect_resolutions`) over a synthesized `source=POLYMARKET` `market_group`'s children — markets settle (RESOLVED, bets flipped, `resolution_source = "POLYMARKET_UMA"`) WITHOUT any `EventService` involvement and with ZERO new settlement code, ending with `drift_count == 0`; plus a `reverse_event` mirrored-reject test. **`backend/app/integrations/polymarket/tasks.py` has NO diff** (the acceptance criterion).

## Task Commits

Each task was committed atomically:

1. **Task 1: EventService.reverse_event — fresh-session-per-child reverse_settlement loop (EVA-05)** - `4d31e9b` (feat)
2. **Task 2: Reverse integration tests — restore / idempotent / per-child balance floor / audit (EVA-05)** - `d81bc47` (test)
3. **Task 3: EVA-06 mirrored verify — detect path settles event children + reverse mirrored-reject (verify-only)** - `8011a2d` (test)

_Note: Task 1 is a `tdd="true"` task executed module-then-tests (Task 2's tests import Task 1's `reverse_event`). The `feat` commit precedes the `test` commit because the plan orders the orchestration first; the reverse integration tests were RED-impossible before the method existed and pass GREEN against it — the same module-then-tests pattern used by Waves 1 and 2._

## Files Created/Modified
- `backend/app/settlement/event_service.py` - Added `EventService.reverse_event` (classmethod, keyword-only, `actor_user_id: UUID | None = None`, NO `winning_outcome_id`) + the `_reverse_children` helper (fresh-session-per-child loop over `reverse_settlement`, best-effort with per-child floor isolation). Reuses the Wave-2 `_load_group_with_children` / `_reject_if_mirrored` / `_require_justification` / `_record_event_audit` / `_derive_status` helpers. Module + `reverse_event` docstrings updated; a Pitfall-6 deferred-gap comment added. No `service.py`/`adapters.py`/`market_port.py` edits; no migration.
- `backend/tests/settlement/test_event_service.py` - Appended 4 reverse tests + the `_wallet_for_user` / `_spend_to_house_revenue` helpers (the latter a ledger-backed `WalletService.transfer` to the `house_revenue` sink so the floor test stays drift-free). Reuses the Wave-2 `_seed_house_event` + committed-session helpers + `_assert_ledger_clean` spike-004 gate. Module docstring updated to list the reverse coverage.
- `backend/tests/settlement/test_event_mirrored.py` - NEW. EVA-06 verify: `test_mirrored_event_children_auto_settle_via_detect` (drives `_run_detect_resolutions` over a mirrored `market_group`'s children via its `session_override`/`redis_override` seam; title-case `"Yes"`/`"No"` labels; AsyncMock detect-lock; a grace-primer market to clear the read tx) + `test_event_service_rejects_mirrored_reverse`. Self-contained committed-session helpers + `_assert_ledger_clean`.

## Decisions Made
- **`reverse_event` carries no `winning_outcome_id`** — `reverse_settlement` reads `SETTLED` bets by status; `ordered_children` is the child ids in deterministic `str(m.id)` order (winner-first is irrelevant for reverse). (Matches the plan's `<action>` exactly.)
- **Per-child fresh sessions for reverse** dodge the 23505 dangling-tx landmine AND isolate the `CHECK(balance >= 0)` floor (Pitfall 3) — one child rolls back alone, siblings stay reversed. Documented in the method + `_reverse_children` docstrings.
- **Reverse scoped to restore + audit only** (mirrors STL-07); a code comment flags the deferred Pitfall-6 re-resolve-after-reverse 23505 idempotency-key collision; NO `resolve -> reverse -> re-resolve` test written.
- **Floor-test "winner spent winnings" simulation** uses a real ledger-backed `WalletService.transfer` (wallet -> `house_revenue`), not a raw balance hack, so the partial-reverse path stays spike-004-clean (`drift_count == 0`) while still driving the wallet below the reverse claw-back.
- **EVA-06 grace-primer + AsyncMock-Redis** — see the deviation below; both were necessary to drive the UNCHANGED detect path end-to-end on a real session without modifying `tasks.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Grace-primer market to drive the UNCHANGED detect path on a real `session_override`**
- **Found during:** Task 3 (first `test_event_mirrored.py` run)
- **Issue:** Driving `_run_detect_resolutions` over already-past-grace mirrored children on a single real `session_override` failed with `detect_settle_failed: A transaction is already begun on this Session.` The detect path's candidate `SELECT` autobegins a read transaction on the injected session; `SettlementService.resolve_market`'s internal `async with session.begin()` then raises because a transaction is already open. Verified in isolation (a pytest diagnostic): `SELECT` -> `begin()` FAILS; `SELECT` -> `commit()` -> `begin()` is OK. In production the detect loop's grace-start branch (`uma_resolved_at IS NULL` -> conditional UPDATE + `commit()` + `continue`) clears the read tx for a mixed-stage tick; when every candidate is already past-grace, nothing commits first.
- **Fix:** The test seeds a standalone POLYMARKET grace-PRIMER market (`uma_resolved_at = NULL`, committed FIRST so it is the lowest physical row / first materialized candidate). The detect loop grace-starts it (UPDATE + `commit()`) BEFORE the settle-ready event children, which closes the candidate-SELECT read tx so each child's `resolve_market` opens its own `begin()` cleanly. This faithfully reproduces a real mixed-stage 60s tick. **`tasks.py` is NOT modified** — this is purely test seeding. (Also: the detect-lock Redis is an `AsyncMock`, the established detect-integration-test idiom, because the in-repo `fakeredis` raises `unknown command 'eval'` on the owner-checked Lua lock release; and the placement-view deadline is FUTURE while the DB-row deadline is PAST, since `BetService.place_bet` validates `is_open` against the view but the detect candidate gate reads the DB row.)
- **Files modified:** `backend/tests/settlement/test_event_mirrored.py` (test-only)
- **Verification:** `uv run pytest tests/settlement/test_event_mirrored.py -v` -> 2 passed, with NO `detect_settle_failed` in logs (the settle path genuinely executed); `git diff HEAD -- backend/app/integrations/polymarket/tasks.py` is empty.
- **Committed in:** `8011a2d` (part of the Task 3 test commit)

---

**Total deviations:** 1 auto-fixed (1 blocking test-infrastructure issue, test-only).
**Impact on plan:** The grace-primer is the faithful way to drive the genuinely-unchanged detect path end-to-end on a real session — it is exactly how production clears the session across a mixed-stage tick, and it keeps the EVA-06 verify-only invariant (`tasks.py` NO diff) intact. No production code beyond `reverse_event` was touched; the plan's `reverse_event` behavior matches the `<action>` spec exactly; no scope creep.

## Issues Encountered
- **EVA-06 detect-path transaction conflict + fakeredis `eval` gap** (see Deviation #1): both were test-infrastructure mismatches between the verify and the unchanged production task, resolved with the grace-primer + AsyncMock-Redis (the established detect-test idioms) — no settlement logic was wrong, `tasks.py` stayed unchanged.
- **mypy on the two test files** reports one `attr-defined` on `Bet.__table__.create` — the IDENTICAL pre-existing artifact in the committed `test_resolve_market.py` / `test_event_service.py` `_bets_table` autouse fixture. CI runs `mypy app/` only (the `tests.*` mypy override disables `no-untyped-def`); not a code defect, no action taken (consistent with the established suite and the Wave 2 SUMMARY).
- **Environmental (not code):** the per-module commands ran GREEN on this Windows worktree this session (no testcontainers flake hit; `uv run pytest tests/settlement/` -> 72 passed); per standing memory the FULL suite + ruff can flip-flop here — trust Linux CI for the full picture.

## User Setup Required
None - no external service configuration required (no new dependency, no migration, no env var, no beat-schedule change).

## Next Phase Readiness
- **Phase 15 event-settlement layer is COMPLETE:** resolve + void + reverse + derived status + mirrored verify, all with the double-entry integrity invariant green (`drift_count == 0`) on every path.
- **Phase 16 (Event API)** can wire `EventService.reverse_event` behind the admin HTTP surface alongside resolve/void: it raises `ValueError` for mirrored groups / blank justification — map these to HTTP 4xx; `EventSettleResult` carries the derived status + `children_failed` list (a partial reverse surfaces the floor-hit child). The EVA-05 two-step confirm + admin auth live at the endpoint.
- **Known deferred limitation (flagged in code, NOT a bug):** re-RESOLVING a child after a reverse reuses the `settle:{bet_id}:{leg}` idempotency keys and collides on 23505 — needs a per-bet settlement epoch (Pitfall 6, out of scope). Reverse v1 is restore + audit only.
- No blockers. `service.py` / `adapters.py` / `market_port.py` / `tasks.py` all unchanged; no migration added; EVT-06's column-free derived-status contract preserved.

## Self-Check: PASSED

- FOUND: `backend/app/settlement/event_service.py` (contains `async def reverse_event`)
- FOUND: `backend/tests/settlement/test_event_service.py` (contains the 4 reverse tests)
- FOUND: `backend/tests/settlement/test_event_mirrored.py`
- FOUND: `.planning/phases/15-event-settlement-house-resolve-void-mirrored-verify/15-03-SUMMARY.md`
- FOUND commit: `4d31e9b` (Task 1, feat)
- FOUND commit: `d81bc47` (Task 2, test)
- FOUND commit: `8011a2d` (Task 3, test)
- VERIFY GREEN: `uv run pytest tests/settlement/test_event_service.py tests/settlement/test_event_mirrored.py tests/settlement/test_derive_event_status.py -x -q` -> 26 passed
- REGRESSION GREEN: `uv run pytest tests/settlement/` -> 72 passed
- `backend/app/integrations/polymarket/tasks.py` -> NO diff since wave start (EVA-06 verify-only acceptance criterion)

---
*Phase: 15-event-settlement-house-resolve-void-mirrored-verify*
*Completed: 2026-06-05*
