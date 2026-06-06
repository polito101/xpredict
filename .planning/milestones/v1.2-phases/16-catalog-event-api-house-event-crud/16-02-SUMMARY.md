# Plan 16-02 Summary — Catalog Read API (BRW-01..05)

**Status:** Complete · **Wave:** 1 · **Executed:** 2026-06-05 (inline, sequential)
**Self-Check: PASSED**

## Objective

Build the public catalog read surface: a new `app/catalog/` package (`CatalogService`
Approach B + discriminated `CatalogItem` schemas + `public_catalog_router`) exposing
`GET /api/v1/catalog`, `GET /api/v1/events/{slug}`, `GET /api/v1/categories`, with
integration tests proving local-only search, bounded/empty-safe filters, sort, the
≥2-child event gate, and the categories union.

## What was built

- **`app/catalog/schemas.py`** — `CatalogOutcome` (label + `yes_outcome_id` + `yes_price`),
  `CatalogItem` (`type: Literal["market","event"]` discriminator + public `status` + `volume`),
  `EventOutcomeRead`, `EventDetail`. Money/odds (`volume`, `yes_price`) serialize as JSON
  **strings** via `@field_serializer` (mirrors `markets/schemas.py:OutcomeRead`).
- **`app/catalog/service.py`** — `CatalogService.list_catalog` implements **Approach B**: two
  bounded `LIMIT 100` queries (standalone `markets` where `group_id IS NULL`; ≥2-child
  `market_groups`) merged + sorted + sliced `[:CATALOG_LIMIT]` in Python. Event status is
  IMPORTED from Phase 15 (`derive_event_status` + `ChildStatus`) — no new status logic. Local
  `pg_trgm` `.ilike(f"%{q}%")` bound-param search (no `text(`, no upstream proxy). Public status
  mapping (`partially_resolved`→open, `void`→resolved); `closing_soon` = OPEN AND deadline ≤
  now+48h. `get_event` (`scalar_one_or_none` by slug) + `list_categories` (DISTINCT non-empty
  union over markets ∪ groups). Shared pure helpers (`yes_leg`, `child_status_of`,
  `event_deadline`, `event_outcome_rows`) reused by the router.
- **`app/catalog/router.py`** — `public_catalog_router` (prefix `/api/v1`): `/catalog`
  (`Literal` status/sort → 422 before service), `/events/{slug}` (≥2-child → 200 else 404),
  `/categories`. Omits the `__future__` annotations import (FastAPI 3.13 `Annotated[...,Depends()]`
  rule); no auth on reads.
- **Tests (`tests/catalog/`)** — `test_catalog_router.py` (bounded list, search-local-only,
  status filter w/ derived mapping, sort, every-combo-empty-safe → 200+[], bad status/sort→422),
  `test_categories.py` (non-empty union, CAT-06 NULL/empty exclusion), `test_event_detail.py`
  (≥2-child 200, 1-child→404, missing→404). **10 passed** (`uv run pytest tests/catalog -x`, ~4s).

## Verification

- `cd backend && uv run pytest tests/catalog -x` → **10 passed**.
- Source assertions: service contains `.ilike(` (2) + `selectinload(` (3); contains no `text(`,
  no upstream-search reference, no `scalar_one(` in the list path; router has no `__future__`
  annotations import and no admin-auth dependency; schemas contain `Literal["market", "event"]`.
- `app/main.py` NOT edited (registration deferred to plan 16-05, per the wave plan).

## Key files

- created: `backend/app/catalog/__init__.py`, `backend/app/catalog/schemas.py`,
  `backend/app/catalog/service.py`, `backend/app/catalog/router.py`,
  `backend/tests/catalog/test_catalog_router.py`, `backend/tests/catalog/test_categories.py`,
  `backend/tests/catalog/test_event_detail.py`
- modified (justified deviations, see below): `backend/tests/catalog/conftest.py`,
  `backend/tests/catalog/_factories.py`

## Deviations (all justified, none reduce scope)

1. **Test-app router mount in `conftest.py`** — the catalog router is not in `app.main` until
   plan 16-05 (the `main.py` edit is deferred to avoid a wave-1/wave-2 collision). An idempotent,
   import-guarded autouse fixture (`_register_phase16_routers`) mounts `public_catalog_router` on
   the test `app` so 16-02's endpoint tests can run now; it is a no-op once 16-05 registers the
   router in `main.py`. This is the intended mechanism for testing a router before its `main.py`
   wiring lands.
2. **`make_single_child_group` added to `_factories.py`** — `make_event` forbids `n_outcomes < 2`,
   but the EVT-07 exclusion/404 tests need a 1-child group. Added a dedicated additive factory
   (reuses the module's `_add_binary_outcomes` / `generate_slug` / `_default_deadline`); does not
   change any existing factory.
3. **Comment rewording in `service.py`/`router.py`** — the original explanatory comments named the
   forbidden tokens ("Gamma /public-search", "from __future__ import annotations",
   "Depends(current_active_admin)") in the negative, which a literal grep-based acceptance check
   would false-positive on. Reworded to preserve the explanation without the exact tokens; the code
   genuinely uses none of them.

## Notes for the orchestrator

- Isolation pattern (reused by 16-03/16-04): override `get_async_session` → the test's
  `async_session` so the `api` client + the flush-only factories share one rolled-back transaction
  (zero leakage). The `_register_phase16_routers` conftest fixture will need extending to mount the
  event admin router once 16-03 creates it.
- Requirements BRW-01..05 delivered and tested.
