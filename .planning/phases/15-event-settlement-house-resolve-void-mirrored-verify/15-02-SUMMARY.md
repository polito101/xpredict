---
phase: 15-event-settlement-house-resolve-void-mirrored-verify
plan: 02
subsystem: settlement
tags: [event-settlement, eva-03, eva-04, eva-06, fresh-session-per-child, sqlalchemy-async, idempotency, double-entry, testcontainers, python]

# Dependency graph
requires:
  - phase: 15-event-settlement-house-resolve-void-mirrored-verify (Wave 1, 15-01)
    provides: "derive_event_status(children) + ChildStatus frozen-slots projection (EVT-06) — the pure layer Wave 2 extends and calls when projecting status from real rows"
  - phase: 05-settlement
    provides: "SettlementService.resolve_market (own session.begin(), per-bet idempotency, FOR-UPDATE lock order, settlement.resolved audit) — looped UNCHANGED per child; HouseMarketResolveAdapter / MarketResolvePort"
  - phase: 13-event-model-market-groups
    provides: "MarketGroup ORM + migration 0011 (deliberately NO status/winner column — EVT-06); Market.group_id/group_item_title; lazy='raise' relationships"
  - phase: 03-wallet-ledger
    provides: "WalletService.recharge (ledger-backed wallet funding) + app.wallet.reconcile._reconcile_async (the spike-004 drift detector)"
provides:
  - "EventService.resolve_event — loops SettlementService per child on a FRESH _get_session_maker() session: winner child on YES, every other child on NO, winner FIRST then losers by market.id; best-effort partial failure; one event.resolved audit row (EVA-03)"
  - "EventService.void_event — same loop, EVERY child on its NO outcome (YES bettors lose, NO bettors win), explicitly NOT a refund; one event.voided audit row (EVA-04)"
  - "Mirrored-reject gate (source==POLYMARKET -> ValueError) in resolve + void (EVA-06)"
  - "EventSettleResult summary (group_id, child_count, children_settled, children_failed, derived status)"
  - "Integration suite test_event_service.py + _seed_house_event synthesizer (committed market_groups + N HOUSE children with YES/NO outcomes + placed bets); spike-004 drift_count==0 asserted after resolve/void/partial/replay"
affects: [phase-16-event-api, phase-17-event-ui, phase-18-seed-demo]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fresh-session-per-child loop over a self-committing financial service (the 23505 dangling-tx landmine: never two settle calls in one with/begin())"
    - "Composition over reinvention: the event layer adds ZERO settlement primitives — payouts, idempotency, lock order, per-child audit all inherited from SettlementService unchanged"
    - "Case-insensitive YES/NO leg mapping via func.upper(Outcome.label) == 'YES' (IN-01) — mirrored title-case 'Yes' never silently missed"
    - "Event-level audit row in its OWN begin() AFTER the loop (action-THEN-audit), additional to the per-child settlement.resolved rows"
    - "Ledger-backed test wallet seeding (INSERT at 0 + WalletService.recharge) so the spike-004 _reconcile_async gate is a faithful drift_count==0"

key-files:
  created:
    - backend/tests/settlement/test_event_service.py
  modified:
    - backend/app/settlement/event_service.py

key-decisions:
  - "Failure injection for the partial-failure test = monkeypatch SettlementService.resolve_market to raise for exactly one child on the first pass, then restore for the re-run. Faithful (the real settle's session.begin() rolls that child back atomically -> bets stay PENDING, ledger stays consistent) and lets the re-run finish cleanly — cleaner than deleting a liability account (which would corrupt double-entry) or pointing a NO map at a missing outcome (which would abort during the read pass, not per-child)."
  - "Test wallets are LEDGER-BACKED (raw INSERT at balance 0 + WalletService.recharge) instead of the older test_resolve_market.py raw-balance shortcut, because this suite asserts the literal spike-004 _reconcile_async drift_count==0 after every path — a phantom (non-ledger-backed) opening balance registers as drift. house_promo (the recharge source) stays the one deliberately-excluded singleton."
  - "_get_session_maker is a top-level import in event_service.py (no circular dependency — app.db.session does not import event_service), not the in-function import the PATTERNS sketch suggested."
  - "EventSettleResult carries the derived status (via derive_event_status, re-projected from committed child rows) + the failed-child tuple so a caller surfaces a partial failure without a second query."

patterns-established:
  - "Event-of-binaries settlement = loop the per-market primitive on a fresh session per child; the only new risk surface is session discipline + YES/NO mapping + the mirrored-reject gate"
  - "Idempotent-replay test as the 23505 dangling-tx canary: resolve the same group twice, assert the second pass moves no money and drift_count==0"

requirements-completed: [EVA-03, EVA-04, EVT-06]

# Metrics
duration: 9min
completed: 2026-06-05
---

# Phase 15 Plan 02: EventService House Resolve/Void (Wave 2) Summary

**`EventService.resolve_event` / `void_event` compose the UNCHANGED `SettlementService` over a `MarketGroup`'s children — one FRESH session per child (the 23505 dangling-tx landmine), winner→YES / losers→NO (resolve) or all-children→NO (void) — with a mirrored-reject gate, a non-blank-justification guard, case-insensitive YES/NO mapping, and one extra event-level audit row, proven by a 12-test integration suite asserting spike-004 `drift_count == 0` after resolve / void / partial-failure / idempotent replay.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-06-05T17:10:14Z
- **Completed:** 2026-06-05T17:19:00Z
- **Tasks:** 2
- **Files modified:** 2 (1 extended, 1 created)

## Accomplishments
- Extended `backend/app/settlement/event_service.py` with `class EventService` (`resolve_event` / `void_event` classmethods) that LOOP the byte-for-byte-unchanged `SettlementService.resolve_market` over a group's child markets, **one fresh `_get_session_maker()` session per child** — the Option-A per-child ACID transaction that dodges the 23505 dangling-tx landmine (`InvalidRequestError: A transaction is already begun`). Zero new settlement primitives: payouts, loser sweep, bet flips, market-status flip, per-bet idempotency keys, FOR-UPDATE lock ordering, and the per-child `settlement.resolved` audit rows are all inherited.
- `resolve_event`: winning child settled FIRST on its supplied YES outcome, every other child on its NO leg (sorted by `market.id`); `void_event`: every child on its NO leg (YES bettors lose, NO bettors win — explicitly NOT a stake refund). Both are best-effort — a child whose settle raises is recorded, siblings stay intact, the event derives `partially_resolved`, and an idempotent re-run finishes.
- Guards: mirrored-reject (`group.source == MarketSourceEnum.POLYMARKET.value` → `ValueError`, EVA-06) in resolve + void; non-blank `justification` (V5); a defensive winning-outcome guard (the supplied outcome must map to exactly one child of the group — Open Q2); case-insensitive `func.upper(Outcome.label) == "YES"` YES/NO mapping (IN-01).
- One additional event-level `event.resolved` / `event.voided` audit row (actor + group_id + justification + child counts), written in its OWN `begin()` via `AuditService.record`, on top of the per-child `settlement.resolved` rows. The Wave 1 pure layer (`derive_event_status` / `ChildStatus`) is preserved and re-used to project the returned status from the committed child rows.
- New `backend/tests/settlement/test_event_service.py` — 12 testcontainers integration tests + a `_seed_house_event` synthesizer (a committed `market_groups` row + N HOUSE child markets each with a YES/NO `Outcome` + placed bets; no house-event seed exists pre-Phase-18). Every resolve / void / partial / replay path asserts the literal spike-004 gate `_reconcile_async(...)["drift_count"] == 0`.

## Task Commits

Each task was committed atomically:

1. **Task 1: EventService.resolve_event + void_event — fresh-session-per-child loop (EVA-03, EVA-04)** - `f897858` (feat)
   - Follow-up: **mypy strict annotation of the internal `session_maker` params (CI gate)** - `c62d2d0` (fix)
2. **Task 2: Integration suite — resolve/void/partial/replay/mirrored-reject/blank-justification + `_seed_house_event` + spike-004 gate (EVA-03, EVA-04)** - `db456a4` (test)

_Note: this is a `tdd="true"` plan executed module-then-tests (Task 2's tests import Task 1's `EventService`). The `feat` commit precedes the `test` commit because the plan orders the orchestration first; the integration tests were RED-impossible before the class existed and pass GREEN against it._

## Files Created/Modified
- `backend/app/settlement/event_service.py` - Extended with `class EventService` (`resolve_event` / `void_event` classmethods + `EventSettleResult` dataclass) and the shared private helpers (`_load_group_with_children` via `selectinload` to dodge `lazy="raise"`; `_yes_outcome_id` / `_no_outcome_id` case-insensitive; `_require_justification`; `_reject_if_mirrored`; `_settle_children` fresh-session loop; `_record_event_audit`; `_derive_status`). The Wave 1 `derive_event_status` / `ChildStatus` pure layer is unchanged.
- `backend/tests/settlement/test_event_service.py` - 12 integration tests (resolve happy-path, event-audit, idempotent replay, void, void-audit, partial-failure + re-run, resolve+void mirrored-reject, resolve+void blank-justification, foreign/unknown winning-outcome, unknown-group, loser-child-settled-on-NO), the `_seed_house_event` synthesizer, the ledger-backed `_seed_wallet`, and the `_assert_ledger_clean()` spike-004 gate.

## Decisions Made
- **Partial-failure injection via monkeypatch** (see frontmatter `key-decisions`): patch `SettlementService.resolve_market` to raise for exactly one child on the first `resolve_event`, then restore for the re-run. Faithful and ledger-safe (the real settle's `session.begin()` rolls that one child back atomically), and the re-run finishes cleanly. Avoids the corruption of deleting a liability account and the read-pass abort of an absent NO outcome.
- **Ledger-backed test wallets** (`_seed_wallet` = INSERT at 0 + `WalletService.recharge`) so the spike-004 `_reconcile_async` gate is a faithful `drift_count == 0`. The older `test_resolve_market.py` raw-balance shortcut leaves a phantom non-ledger-backed opening balance that the reconciler (correctly) reports as drift; that suite sidesteps it with per-account delta assertions and never calls the reconciler. This plan's requirement to assert the literal reconcile gate forced the ledger-backed seed.
- `_get_session_maker` is a clean top-level import (verified no circular dependency), not the in-function import the PATTERNS sketch suggested.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] mypy-strict type annotations on the internal `session_maker` params**
- **Found during:** Task 1 (post-implementation verification)
- **Issue:** The three private helpers (`_settle_children` / `_record_event_audit` / `_derive_status`) took an untyped `session_maker`, tripping `mypy --strict` `no-untyped-def`. CI runs `uv run mypy app/` as a hard gate, so this would have failed the PR.
- **Fix:** Annotated each as `async_sessionmaker[AsyncSession]` (a `TYPE_CHECKING` import; string-form under `from __future__ import annotations`, no runtime cost).
- **Files modified:** `backend/app/settlement/event_service.py`
- **Verification:** `uv run mypy app/settlement/event_service.py` → "Success: no issues found"; ruff + import still clean; the full settlement suite still green.
- **Committed in:** `c62d2d0` (separate fix commit on Task 1's file).

**2. [Rule 1 - Bug] Ledger-backed test-wallet seeding to make the spike-004 gate faithful**
- **Found during:** Task 2 (first integration run)
- **Issue:** `_seed_wallet` copied `test_resolve_market.py`'s raw-balance INSERT (no opening ledger entry), so the seeded opening balance was non-ledger-backed. `_assert_ledger_clean()` then (correctly) reported `drift_count == 4` — the four seeded wallets — even though all business-logic assertions (winners paid, losers swept, bets flipped, markets RESOLVED) passed. This is the RESEARCH Pitfall-5 / Open-Q1 tension surfacing.
- **Fix:** `_seed_wallet` now INSERTs the wallet at balance 0 (so `SUM(entries) == balance == 0`) then funds it to the target via `WalletService.recharge` (a real `house_promo → wallet` ledger-backed credit). The wallet is fully ledger-backed; `house_promo` (the funding source) is the one deliberately-excluded singleton, so `drift_count == 0` holds.
- **Files modified:** `backend/tests/settlement/test_event_service.py`
- **Verification:** `test_resolve_event_settles_all_children` → PASS with `drift_count == 0`; all 12 event tests + 8 derive_event_status unit tests green; full `tests/settlement/` (66 tests) green.
- **Committed in:** `db456a4` (part of the Task 2 test commit).

---

**Total deviations:** 2 auto-fixed (1 blocking CI gate, 1 test-correctness bug).
**Impact on plan:** Both were necessary for correctness/CI. No scope creep — the service behavior matches the plan exactly; the deviations only made the type-check pass and the spike-004 gate faithful. The production `app/` settlement code is unchanged beyond the new `EventService` (no `service.py` / `adapters.py` / `market_port.py` edits; no migration; EVT-06's column-free contract preserved).

## Issues Encountered
- **First integration run failed only on the spike-004 reconcile assertion** (see Deviation #2). The fix was the ledger-backed seed; no settlement logic was wrong.
- **mypy on the test file** reports one `attr-defined` on `Bet.__table__.create` — this is the IDENTICAL pre-existing artifact in the committed `test_resolve_market.py` template, and CI runs `mypy app/` only (the `tests.*` mypy override also disables `no-untyped-def`). Not a code defect; no action taken, consistent with the established test suite.
- **Environmental (not code):** the per-module command ran GREEN on this Windows worktree this session (no testcontainers flake hit); per standing memory the FULL suite + ruff can flip-flop here — trust Linux CI for the full picture.

## User Setup Required
None - no external service configuration required (no new dependency, no migration, no env var).

## Next Phase Readiness
- **Phase 16 (Event API)** can wire `EventService.resolve_event` / `void_event` behind the admin HTTP surface: the service raises `ValueError` for mirrored groups / blank justification / foreign-or-unknown winning-outcome — map these to HTTP 4xx; the authoritative winning-outcome validation + the two-step confirm live at the endpoint. `EventSettleResult` carries the derived status + failed-child list for the response.
- **Reverse (EVA-05) is Plan 03** — deliberately NOT in this plan; no resolve→reverse→re-resolve test exists (the deferred Pitfall-6 `reverse_idempotency_key` collision gap).
- No blockers. `service.py` / `adapters.py` / `market_port.py` unchanged; no migration added; EVT-06's column-free derived-status contract preserved.

## Self-Check: PASSED

- FOUND: `backend/app/settlement/event_service.py`
- FOUND: `backend/tests/settlement/test_event_service.py`
- FOUND: `.planning/phases/15-event-settlement-house-resolve-void-mirrored-verify/15-02-SUMMARY.md`
- FOUND commit: `f897858` (Task 1, feat)
- FOUND commit: `c62d2d0` (Task 1 follow-up, fix — mypy gate)
- FOUND commit: `db456a4` (Task 2, test)
- Per-module verify GREEN: `uv run pytest tests/settlement/test_event_service.py tests/settlement/test_derive_event_status.py -x -q` → 20 passed
- Regression GREEN: `uv run pytest tests/settlement/` → 66 passed
- `uv run mypy app/settlement/event_service.py` → Success; ruff check + format clean

---
*Phase: 15-event-settlement-house-resolve-void-mirrored-verify*
*Completed: 2026-06-05*
