---
phase: 15-event-settlement-house-resolve-void-mirrored-verify
plan: 01
subsystem: settlement
tags: [event-settlement, derived-status, pure-function, dataclass, evt-06, multi-outcome, python]

# Dependency graph
requires:
  - phase: 13-event-model-market-groups
    provides: "MarketGroup ORM + migration 0011 (deliberately NO status/winning_outcome column — EVT-06)"
  - phase: 05-settlement
    provides: "MarketStatus enum + the BetToSettle frozen-slots pure-projection idiom (plan.py) this mirrors"
provides:
  - "derive_event_status(children) pure read-projection — open/partially_resolved/resolved/void (EVT-06)"
  - "ChildStatus frozen-slots input dataclass (status, is_yes_winner) — ORM-decoupled, session-free"
  - "backend/app/settlement/event_service.py module (Wave 1 pure layer; Wave 2 EventService class extends it)"
affects: [phase-15-wave-2-event-service, phase-16-event-api, phase-17-event-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure read-projection (free function over a Sequence of frozen-slots dataclasses, stdlib-only) — mirrors build_settlement_plan"
    - "Derived event status as the source of truth (no stored authoritative column on market_groups — EVT-06)"

key-files:
  created:
    - backend/app/settlement/event_service.py
    - backend/tests/settlement/test_derive_event_status.py
  modified: []

key-decisions:
  - "derive_event_status + ChildStatus live in event_service.py at module level (not classmethods) so they unit-test without a session — Wave 2's EventService class will extend the same module"
  - "ChildStatus carries only (status, is_yes_winner) — two ORM-decoupled scalars — so the unit surface needs no DB; the service computes is_yes_winner from Market.winning_outcome_id vs the YES outcome when projecting real rows"
  - "Wave 1 ships ONLY the pure layer: NO AsyncSession / select( / session param / EventService class / migration in this file (acceptance grep-asserts their absence)"

patterns-established:
  - "Pure, total event-status projection: empty -> open, never raises; void vs resolved disambiguated by 'any child won YES' (event outcomes mutually exclusive)"

requirements-completed: [EVT-06]

# Metrics
duration: 3min
completed: 2026-06-05
---

# Phase 15 Plan 01: EVT-06 Derived Event-Status Read-Projection Summary

**Column-free `derive_event_status(children)` pure projection (open/partially_resolved/resolved/void) plus its `ChildStatus` frozen-slots input, in the new `event_service.py`, with 8 no-Docker unit tests covering all four states + empty + the void edge.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-05T16:57:50Z
- **Completed:** 2026-06-05T17:00:43Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- New module `backend/app/settlement/event_service.py` hosting the Wave 1 pure layer only — `ChildStatus` (`@dataclass(frozen=True, slots=True)`) + the module-level `derive_event_status` free function, mirroring the `build_settlement_plan` / `BetToSettle` idiom in `plan.py`.
- EVT-06 honored literally: the file is pure (no `AsyncSession`, no `select(`, no `session` parameter — grep-asserted at 0) and adds **no migration / no `market_groups` status or winning_outcome column** — status is derived at read time, not stored.
- 8 pure unit tests (`test_derive_event_status.py`) mirroring `test_plan.py`'s direct-construct-and-assert style — no fixtures, no `pytest.mark.integration`, no testcontainers — running in 0.41s without Docker.
- The load-bearing `void` vs `resolved` disambiguation (threat T-15-01) is asserted explicitly: all children RESOLVED with no YES-winner -> `void`; with exactly one YES-winner -> `resolved`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create event_service.py with ChildStatus + derive_event_status pure projection (EVT-06)** - `c907ba7` (feat)
2. **Task 2: Unit tests for derive_event_status — all four states + empty + void edge** - `7f090b2` (test)

_Note: this is a `type: tdd`-style plan executed as module-then-tests (Task 2's tests import Task 1's module). The `feat` commit precedes the `test` commit because the plan orders the pure function first; tests were RED-impossible before the module existed and pass GREEN against it._

## Files Created/Modified
- `backend/app/settlement/event_service.py` - Wave 1 pure layer: `ChildStatus` frozen-slots dataclass (`status`, `is_yes_winner`) + `derive_event_status(children) -> str` (open/partially_resolved/resolved/void). No I/O, no session, no migration (EVT-06). The Wave 2 `EventService` orchestration class will extend this same module.
- `backend/tests/settlement/test_derive_event_status.py` - 8 pure unit tests (no Docker): empty->open, none-resolved->open, partial->partially_resolved (incl. winner-resolved-while-sibling-open), all-resolved-one-YES->resolved (incl. single-child), all-resolved-no-YES->void (incl. single-child).

## Decisions Made
None beyond the plan — followed the authoritative `derive_event_status` reference body (15-RESEARCH Code Examples / 15-PATTERNS analog of `plan.py`) and the `test_plan.py` analog exactly. Added three extra unit cases beyond the five the plan names (`single_resolved_yes_winner`, `single_resolved_no_yes_winner`, `partial_resolution_with_winner_still_partially_resolved`) to strengthen the four-state contract and the mutually-exclusive-outcome assumption; all on-contract, no behavior change to the function.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. One acceptance-criteria nuance handled proactively: the initial module docstring contained the word "AsyncSession" (in prose, describing what the file deliberately omits). Because the acceptance criteria grep-assert that `AsyncSession` "returns nothing in this file", the docstring was reworded to "DB session" before the Task 1 commit so the grep is literally 0. No functional impact.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `derive_event_status` + `ChildStatus` are import-clean and exhaustively unit-covered — Wave 2's `EventService` (resolve/void/reverse) can extend the same `event_service.py` and call `derive_event_status` when projecting status from real `Market` rows (computing `is_yes_winner` from `Market.winning_outcome_id` vs the `func.upper(label)=="YES"` outcome).
- No blockers. EVT-06's column-free contract is preserved (no migration, no stored status/winner on `market_groups`).
- Environmental note (not a code issue): per-module test command is GREEN locally; the full backend suite + ruff flip-flop on this Windows worktree — trust Linux CI for the full picture, per the standing memory.

## Self-Check: PASSED

- FOUND: `backend/app/settlement/event_service.py`
- FOUND: `backend/tests/settlement/test_derive_event_status.py`
- FOUND: `.planning/phases/15-event-settlement-house-resolve-void-mirrored-verify/15-01-SUMMARY.md`
- FOUND commit: `c907ba7` (Task 1, feat)
- FOUND commit: `7f090b2` (Task 2, test)

---
*Phase: 15-event-settlement-house-resolve-void-mirrored-verify*
*Completed: 2026-06-05*
