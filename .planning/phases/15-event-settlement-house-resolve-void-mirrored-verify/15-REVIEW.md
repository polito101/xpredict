---
phase: 15-event-settlement-house-resolve-void-mirrored-verify
reviewed: 2026-06-05T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/app/settlement/event_service.py
  - backend/tests/settlement/test_derive_event_status.py
  - backend/tests/settlement/test_event_service.py
  - backend/tests/settlement/test_event_mirrored.py
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: resolved
resolution_commit: 5c2add9
resolution:
  fixed: [CR-01, WR-01, WR-02, WR-03, WR-04]
  deferred_info: [IN-01, IN-02]
---

# Phase 15: Code Review Report

**Reviewed:** 2026-06-05T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** resolved (1 critical + 4 warnings fixed in `5c2add9`; 2 info deferred)

## Resolution (2026-06-05)

- **CR-01 — FIXED:** `resolve_event` now validates the supplied `winning_outcome_id` is the winner child's YES outcome (reuses the existing `_yes_outcome_id` helper), raising otherwise. Regression test `test_resolve_event_rejects_no_outcome_as_winner` added (WR-03).
- **WR-01 — FIXED:** `_settle_children` / `_reverse_children` now `logger.exception(...)` each best-effort child failure — no more silent swallow in financial code.
- **WR-02 — FIXED:** `test_reverse_event_rejects_blank_justification` added.
- **WR-04 — FIXED:** `_record_event_audit` logs (with traceback) before re-raising on an audit-write failure, and documents that the per-child `settlement.*` rows are the authoritative audit trail.
- **IN-01 / IN-02 — DEFERRED (info, non-blocking):** the opaque `scalar_one()` error context and the test-helper `conftest.py` dedup are quality nice-to-haves for a follow-up.

Validation after fixes: `pytest tests/settlement/{test_event_service,test_derive_event_status,test_event_mirrored}.py` → **28 passed**; `ruff check` + `ruff format --check` clean; `mypy app/settlement/event_service.py` → Success.

## Summary

The implementation delivers the EVT-06 derived-status projection, EVA-03/04/05/06
orchestration, and the mirrored-event verify correctly at the structural level.
The fresh-session-per-child invariant (the 23505 dangling-tx landmine guard) is
correctly implemented in all three mutation paths. `derive_event_status` is a
pure, column-free projection as required. The mirrored-reject gate fires on all
three mutations. Justification guards exist on all three mutations.

However one critical semantic bug exists: `resolve_event` accepts any outcome
(YES or NO) of any child as `winning_outcome_id` — passing a NO outcome triggers
settlement on that outcome, derives the event as `"void"`, and writes an
`event.resolved` audit row with a mismatched event type. The service-layer
winning-outcome guard validates group membership only, not that the supplied
outcome is the YES leg of the intended winner. This is a data-integrity bug in
financial code.

Four warnings follow: silent exception swallowing with no logging in the
best-effort loops, a missing test for `reverse_event` blank-justification
rejection, a missing validation test for `resolve_event` with a NO outcome as
winner, and the audit write occurring after committed child settlements with no
retry or fallback.

## Structural Findings (fallow)

No structural pre-pass was provided for this review.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `resolve_event` does not validate that `winning_outcome_id` is the YES leg — passing the NO outcome settles wrongly and mismatches audit

**File:** `backend/app/settlement/event_service.py:248-274`

**Issue:** The defensive guard at lines 248-264 validates only that `winning_outcome_id`
belongs to exactly one child of the group. It does NOT validate that the outcome is the
YES outcome of the winner child. If the caller passes the NO outcome ID of any child as
`winning_outcome_id`, the winner child settles on its NO leg. After settlement:

- `_derive_status` finds `child.winning_outcome_id == no_id`, so `is_yes_winner=False`
  for the intended winner child.
- All children have `is_yes_winner=False`.
- `derive_event_status` returns `"void"`.
- `EventSettleResult.status == "void"`.
- The audit row uses `event_type="event.resolved"`.

The caller issued a `resolve_event` call, an `event.resolved` audit row is written, but the
derived event status is `"void"`. This is a semantic integrity failure: the audit claims a
resolution that the system state contradicts. In a house-market context, this means the
YES bettors on the intended winner child lose their stakes (settled NO), NO bettors win,
while the non-repudiation log records the event as "resolved" — a financial record
inconsistency.

The `_yes_outcome_id` helper already exists in this module (line 143) for exactly this
purpose. The guard must additionally verify the supplied outcome is the YES leg of the
matched child.

**Fix:**
```python
# After computing winner_market_id (line 265), add:
yes_id_of_winner = await _yes_outcome_id(read_session, winner_market_id)
if winning_outcome_id != yes_id_of_winner:
    raise ValueError(
        f"winning_outcome_id {winning_outcome_id} is not the YES outcome of "
        f"child {winner_market_id} in group {group_id}. "
        f"Expected YES outcome {yes_id_of_winner}."
    )
```

Insert this block immediately after line 265 (`winner_market_id = winner_market_ids[0]`)
and before line 269 (the `loser_children` sort).

## Warnings

### WR-01: Exception swallowing in `_settle_children` and `_reverse_children` — zero diagnostic visibility on child-settle failures in production

**File:** `backend/app/settlement/event_service.py:474-476` and `509-511`

**Issue:** Both best-effort loops catch all `Exception` and silently continue:

```python
except Exception:  # best-effort partial failure (CONTEXT)
    failed.append(child_market_id)
    continue
```

No logging call is present anywhere in `event_service.py`. When a child's settlement
raises — whether due to a transient DB error, a constraint violation, a bug in
`SettlementService`, or anything else — the failure is recorded only in the `failed`
list and surfaced in `EventSettleResult.children_failed`. The exception itself, including
its type, message, and traceback, is permanently lost. In production, an operator who
sees `children_failed != ()` in an API response has no log evidence to diagnose why a
child's settlement failed. For financial code, this is an unacceptable operational risk.

**Fix:**

Add a module-level logger and log the exception at ERROR level inside each bare `except`:

```python
import logging
_log = logging.getLogger(__name__)

# In _settle_children:
except Exception:
    _log.exception(
        "child settle failed — market_id=%s will be in children_failed",
        child_market_id,
    )
    failed.append(child_market_id)
    continue

# In _reverse_children:
except Exception:
    _log.exception(
        "child reverse failed — market_id=%s will be in children_failed",
        child_market_id,
    )
    failed.append(child_market_id)
    continue
```

### WR-02: Missing test: `reverse_event` blank/whitespace justification guard is not tested

**File:** `backend/tests/settlement/test_event_service.py` (no line — test is absent)

**Issue:** `test_event_service.py` tests `_require_justification` for `resolve_event`
(line 608) and `void_event` (line 618), but there is NO corresponding test for
`reverse_event`. The guard is present in `event_service.py:400` but if the guard code
were accidentally removed, no test would catch the regression. The three mutations must
each have a blank-justification test to give the guard full coverage.

**Fix:** Add to `test_event_service.py`:

```python
async def test_reverse_event_rejects_blank_justification() -> None:
    group_id, _children, _src = await _seed_house_event(2)
    with pytest.raises(ValueError, match="(?i)justification"):
        await EventService.reverse_event(group_id=group_id, justification="   ")
```

### WR-03: Missing validation test — `resolve_event` with a NO outcome as `winning_outcome_id` is not tested; the current guard allows it silently

**File:** `backend/tests/settlement/test_event_service.py` (no line — test is absent)

**Issue:** The service-level guard (lines 248-264) validates only group membership.
As described in CR-01, passing a NO outcome as `winning_outcome_id` is currently
accepted without error. There is no test that covers this path. Even before CR-01 is
fixed, a test should document the expected behavior (reject) and catch any regression
if the fix is later removed.

**Fix:** Add after CR-01 fix is applied:

```python
async def test_resolve_event_rejects_no_outcome_as_winner() -> None:
    group_id, children, _src = await _seed_house_event(2)
    winner_child = children[0]
    with pytest.raises(ValueError, match="(?i)yes"):
        await EventService.resolve_event(
            group_id=group_id,
            winning_outcome_id=winner_child.no_id,  # NO outcome — must be rejected
            justification="should be rejected: NO outcome is not a valid winner",
        )
```

### WR-04: Audit write after committed child settlements has no retry or fallback — a failure here leaves children settled with no audit row

**File:** `backend/app/settlement/event_service.py:281-291` (resolve), `343-353` (void), `421-431` (reverse)

**Issue:** `_record_event_audit` runs AFTER the child settlement loop returns successfully.
If `_record_event_audit` raises (e.g., the audit session fails to commit), the exception
propagates to the caller. The caller receives an exception and cannot distinguish "nothing
happened" from "children settled but audit row was not written". The children's transactions
are already individually committed (Option A), so the caller has no rollback lever. The
event-level audit row is silently absent, violating the non-repudiation requirement.

This is a known trade-off of the action-then-audit pattern, but it is undocumented at the
call site and there is no compensating mechanism (retry, dead-letter, or at-least-once
guarantee).

**Fix:** At minimum, document the gap in the module docstring and at each call site:

```python
# NOTE: if this call raises, the child settlements are already committed and
# cannot be rolled back. The event-level audit row is lost. A compensating
# retry or a dead-letter queue (Phase 16+) is needed for full durability.
await cls._record_event_audit(...)
```

Longer term, wrap `_record_event_audit` in a retry loop with exponential backoff, or
log the payload at ERROR level before calling it so the data survives even if the DB
write fails.

## Info

### IN-01: `_no_outcome_id` uses `scalar_one()` which emits an opaque error if the binary-outcomes trigger is bypassed

**File:** `backend/app/settlement/event_service.py:160-169`

**Issue:** `_no_outcome_id` selects all outcomes with `label != "YES"` and calls
`scalar_one()`. The `trg_binary_outcomes_only` trigger (migration 0003) guarantees
exactly one such outcome per market in production. However, if the trigger is bypassed
(e.g., during a migration, in a test without a container, or by a direct DB insert),
`scalar_one()` raises `MultipleResultsFound` or `NoResultFound` with no context about
which market or operation triggered the error. This makes debugging harder.

**Fix:** Use `scalar_one_or_none()` with an explicit guard, or add a descriptive error:

```python
result = (
    await session.execute(
        select(Outcome.id).where(
            Outcome.market_id == market_id,
            func.upper(Outcome.label) != "YES",
        )
    )
).scalars().all()
if len(result) != 1:
    raise ValueError(
        f"Expected exactly one non-YES outcome for market {market_id}, "
        f"got {len(result)}. Check trg_binary_outcomes_only trigger."
    )
return result[0]
```

### IN-02: `StubMarketSource` and `_seed_wallet` are duplicated verbatim between `test_event_service.py` and `test_event_mirrored.py`

**File:** `backend/tests/settlement/test_event_service.py:103-158` and `backend/tests/settlement/test_event_mirrored.py:97-149`

**Issue:** Both test files define identical `StubMarketSource` classes and `_seed_wallet`
helpers. Any change to the seeding pattern (e.g., the ledger-backed wallet requirement)
must be applied to both files independently. A conftest.py extraction would keep the
idiom consistent and make future changes safer.

**Fix:** Extract shared helpers to `backend/tests/settlement/conftest.py`:

```python
# backend/tests/settlement/conftest.py
import pytest_asyncio
from ... import StubMarketSource, _seed_wallet  # move definitions here
```

Both test files would then import from the conftest implicitly (pytest auto-discovers
conftest.py fixtures) or via an explicit import.

---

_Reviewed: 2026-06-05T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
