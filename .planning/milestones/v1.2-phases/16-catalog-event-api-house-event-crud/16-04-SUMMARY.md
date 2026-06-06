# Plan 16-04 Summary — Resolve/Void/Reverse HTTP + Two-Step Confirm

**Status:** Complete · **Wave:** 2 · **Executed:** 2026-06-05 (inline, sequential)
**Self-Check: PASSED**

## Objective

Expose the Phase-15 `EventService.resolve_event/void_event/reverse_event` over HTTP
(`POST /admin/events/{group_id}/resolve|void|reverse`) with the stateless two-step
confirm (`confirm:false`/absent → non-mutating preview; `confirm:true` → execute), a
mandatory non-empty justification, the `ValueError`→HTTP map, and the settlement
session choreography — re-implementing none of the settle loop.

## What was built

- **`app/settlement/event_schemas.py`** (extended, additive) — `ResolveEventRequest`
  (`winning_outcome_id`, `justification` `min_length=1`, `confirm: bool = False`),
  `VoidEventRequest`, `ReverseEventRequest` (each `extra="forbid"`), and `EventActionResponse`
  (unified preview+execute: `preview`, `child_count`, preview `winners`/`losers`/
  `settled_children_to_reverse`, execute `children_settled`/`children_failed`, `projected_status`).
- **`app/settlement/event_router.py`** (extended) — `_map_event_value_error` (Mirrored→409,
  No-market-group→404, winning_outcome_id→422, justification→422, else 400 — matches the exact
  `event_service.py` raise messages); `_load_for_settle` (read-only load → 404 missing / 409
  mirrored, mirroring the service guards for the preview branch); and three routes on
  `event_admin_router`. Each: PREVIEW branch reads via `_load_group_with_children` (+ resolve
  pre-validates the winner is a child YES leg → 422) and returns `preview=True` with NO mutation;
  EXECUTE branch does `admin_id = admin.id` → `await session.rollback()` → calls the EventService
  method (which owns per-child fresh sessions — the endpoint never loops children) → `except
  ValueError → _map_event_value_error`. All three `Depends(current_active_admin)`.
- **`tests/settlement/test_event_settle_router.py`** (new) — 9 tests reusing the ledger-backed
  seed/drift helpers from `test_event_service` (`_seed_house_event`/`_seed_wallet`/`_place` via
  `BetService.place_bet`/`_assert_ledger_clean`): resolve preview-no-mutation (children stay OPEN),
  resolve/void/reverse execute (children settle/reopen + spike-004 `drift_count == 0`), mirrored→409
  on BOTH preview and execute for all three ops, blank-justification→422, bad-winning-outcome→422,
  missing-group→404, and the 401 admin gate on all three. **9 passed**.

## Verification

- `cd backend && uv run pytest tests/settlement/test_event_settle_router.py -x` → **9 passed**.
- Source assertions: schemas have the 3 settle requests with `confirm: bool = False` +
  `winning_outcome_id`; router has `_map_event_value_error`, the 3 settle routes, `await
  session.rollback()` ×3 (execute branches) + `admin_id = admin.id`, `current_active_admin` on
  every route, no future-annotations import, and no manual per-child settle loop (mutation is only
  via `EventService.{resolve,void,reverse}_event`).
- `git diff` of `event_router.py`/`event_schemas.py`: appended models + helper + 3 routes; the
  16-03 create/PATCH routes + create/update schemas are unchanged (only imports extended).
- `app/main.py` NOT edited (registration is plan 16-05).

## Key files

- created: `backend/tests/settlement/test_event_settle_router.py`
- modified (additive): `backend/app/settlement/event_schemas.py`, `backend/app/settlement/event_router.py`

## Deviations / notes

- **Reverse-test seeding** — `reverse_settlement` only reopens a child that had bets to reverse, so
  a loser child with no bets stays RESOLVED (the event derives `partially_resolved`). The test seeds
  a bet on EVERY child so reverse reopens them all → derived `open` (this is correct EventService
  behaviour, faithfully reflected by the endpoint's `result.status`).
- **Testcontainer flake** — the first run hit a transient testcontainer connection drop during
  `alembic upgrade` (the documented Windows-worktree flake); a retry ran clean. Verified per-module.
- The resolve/void/reverse HTTP surface (success criterion 4) is complete. Router registration +
  legacy `/markets` back-compat verification land in plan 16-05.
