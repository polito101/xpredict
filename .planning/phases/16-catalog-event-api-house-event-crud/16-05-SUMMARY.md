# Plan 16-05 Summary — Router Registration + Legacy Back-Compat

**Status:** Complete · **Wave:** 3 · **Executed:** 2026-06-05 (inline, sequential)
**Self-Check: PASSED**

## Objective

Wire the two new Phase-16 routers into the application and prove back-compat: register
`public_catalog_router` (16-02) and `event_admin_router` (16-03/16-04) in `app/main.py`
via the deferred-import `include_router` block, add a live-app route-presence smoke test,
and reinforce the legacy `GET /api/v1/markets` flat-list contract.

## What was built

- **`app/main.py`** (2 imports + 2 registrations, nothing else) — added
  `from app.catalog.router import public_catalog_router  # noqa: E402` and
  `from app.settlement.event_router import event_admin_router  # noqa: E402` in the deferred
  route-import block, and `app.include_router(public_catalog_router)` +
  `app.include_router(event_admin_router)` in the include block. `git diff`: **4 insertions, 0
  deletions** — no existing import/registration reordered or removed.
- **`tests/catalog/test_wiring.py`** (new) — `test_new_routes_registered` asserts all eight
  Phase-16 paths are present on the assembled app (`/api/v1/catalog`, `/api/v1/categories`,
  `/api/v1/events/{slug}`, `/admin/events`, `/admin/events/{group_id}`, and the resolve/void/reverse
  routes); `test_catalog_endpoint_live` asserts `GET /api/v1/catalog` → 200 + a list on the wired app.
- **`tests/markets/test_public_router.py`** (reinforced) — added
  `test_public_markets_backcompat_flat_list` asserting `GET /api/v1/markets` still returns 200 +
  `isinstance(body, list)` after the new routers were registered (T-16-16). The legacy endpoint and
  its existing tests are unchanged.

## Verification

- `cd backend && uv run pytest tests/catalog/test_wiring.py tests/markets/test_public_router.py -x`
  → **10 passed**.
- **Full Phase-16 surface in one invocation:** `uv run pytest tests/catalog
  tests/settlement/test_event_router.py tests/settlement/test_event_settle_router.py` → **29 passed**
  — the `main.py` registration and the per-module idempotent router-mount fixtures coexist cleanly.
- `git diff` of `main.py`: only the 2 added imports + 2 added `include_router` calls.
- The app imports cleanly with both routers wired (no circular import — deferred-import placement).

## Key files

- created: `backend/tests/catalog/test_wiring.py`
- modified: `backend/app/main.py` (additive), `backend/tests/markets/test_public_router.py` (additive test)

## Deviations / notes

- `test_new_routes_registered` is `async def` (the module's `pytestmark` applies the asyncio mark;
  a sync test under it is a warning→error with `filterwarnings=error`) — it awaits nothing but
  satisfies the mark.
- The idempotent test-mount fixtures from 16-01/16-03/16-04 are now no-ops (main.py registers the
  routers at import) but are kept so each per-module test stays self-contained.
- BRW-01..05 + EVA-01/02 are now reachable on the live app; the legacy `/markets` contract holds.
