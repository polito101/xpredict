# Plan 16-03 Summary — Admin House-Event Create + Edit-Lock (EVA-01/02)

**Status:** Complete · **Wave:** 1 · **Executed:** 2026-06-05 (inline, sequential)
**Self-Check: PASSED**

## Objective

Build the admin authoring surface for house multi-outcome events: `POST /admin/events`
(create one `MarketGroup` + N binary YES/NO children in one request transaction) and
`PATCH /admin/events/{group_id}` (pre-bet edit; HTTP 423 after the first bet via
`EXISTS(bets)`), the `EventService.create_house_event` / `update_house_event` service
path, request/response schemas, and integration tests.

## What was built

- **`app/settlement/event_schemas.py`** (new) — `OutcomeInput` (`label`, `initial_odds`
  `Field(gt=0, lt=1)`), `CreateEventRequest` (`outcomes: Field(min_length=2)`, future-deadline
  validator), `UpdateEventRequest` (all-optional, whole-list outcomes replace), `EventChildRead`
  / `EventCreatedResponse` / `EventDetailResponse` (YES price as a JSON string via `DecimalStr`).
  Every request `extra="forbid"`.
- **`app/settlement/event_service.py`** (extended, additive — resolve/void/reverse untouched) —
  `EventService.create_house_event` (group via the `begin_nested()`+IntegrityError slug-retry
  copied from `create_market`, then per-outcome child with exactly a YES+NO pair, one
  `event.created` audit row, one `commit`, returns the eager-reloaded group); `update_house_event`
  (pre-bet metadata/outcomes edit, whole-list child replace); module helpers `_add_event_child`
  (binary-trigger-safe child + YES/NO seeding) and `event_has_bets` (`EXISTS(bets)` over child
  ids — `Bet` lazy-imported to avoid a settlement↔bets cycle; never the dead counter column).
- **`app/settlement/event_router.py`** (new) — `event_admin_router` (prefix `/admin/events`):
  `POST ""` (create, 201) + `PATCH /{group_id}` (load→404, `event_has_bets`→423 `EVENT_LOCKED`,
  else update). Both `Depends(current_active_admin)`. Omits the PEP 563 future-annotations import.
  Resolve/void/reverse routes deferred to plan 16-04.
- **`tests/settlement/test_event_router.py`** (new) — 8 tests: create (group + 3 children, each
  exactly YES+NO, YES price round-trips the requested odds as a string), single-outcome→422,
  bad-odds→422, pre-bet edit→200, edit-after-bet→423 `EVENT_LOCKED` (seeds a real ledger-backed
  bet on a committed session), missing-group→404, and the 401 admin gate on both endpoints.
  **8 passed** (`uv run pytest tests/settlement/test_event_router.py`, ~5s).

## Verification

- `cd backend && uv run pytest tests/settlement/test_event_router.py -x` → **8 passed**.
- Source assertions: schemas contain `min_length=2` + `Field(gt=0, lt=1)` + `extra="forbid"`;
  service contains `def create_house_event` / `def event_has_bets` / `def update_house_event`;
  `event_has_bets` uses `exists(` + `Bet.market_id` and contains no counter-column reference;
  router has no future-annotations import, registers `POST ""` + `PATCH /{group_id}`, raises
  `HTTP_423_LOCKED` with code `EVENT_LOCKED`, and gates both routes with `current_active_admin`.
- `git diff` of `event_service.py`: additions only (2 import-line edits + appended code); the
  existing `resolve_event`/`void_event`/`reverse_event` bodies are byte-for-byte unchanged.
- `app/main.py` NOT edited (registration deferred to plan 16-05).

## Key files

- created: `backend/app/settlement/event_schemas.py`, `backend/app/settlement/event_router.py`,
  `backend/tests/settlement/test_event_router.py`
- modified (additive): `backend/app/settlement/event_service.py`

## Deviations (justified)

1. **Test-app router mount** — the event router is mounted on the test app by a local autouse
   fixture in `test_event_router.py` (idempotent); `main.py` registration is plan 16-05's job.
2. **`create_house_event` returns the eager-reloaded group** (captures the id pre-commit and
   re-loads with `selectinload`) so the router can serialize `.markets` without a `MissingGreenlet`
   from expire-on-commit — a faithful implementation of "return the group".
3. **Comment rewording** — explanatory comments that named the forbidden tokens (the dead counter
   column, the future-annotations import) in the negative were reworded to avoid grep false-positives;
   the code uses neither.

## Notes for the orchestrator

- Plan 16-04 EXTENDS `event_router.py` (resolve/void/reverse) + `event_schemas.py` — wave 2,
  `depends_on: 16-03`. The settle endpoints will call the Phase-15 `EventService.resolve_event`/
  `void_event`/`reverse_event` (already present) with the stateless two-step confirm.
- EVA-01 + EVA-02 delivered and tested.
