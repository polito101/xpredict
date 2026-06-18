"""Live-app wiring smoke test (Phase 16, plan 16-05).

Proves that every Phase-16 route is reachable on the assembled ``app.main`` app (the
catalog + event-admin routers are registered via the deferred-import ``include_router``
block) and that ``GET /api/v1/catalog`` answers on the wired app. The legacy
``/markets`` back-compat guard lives in ``tests/markets/test_public_router.py``.
"""

from __future__ import annotations

import warnings

import pytest

from app.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# Every Phase-16 route that must be reachable on the live app after 16-05 wiring.
_PHASE16_ROUTES = {
    "/api/v1/catalog",
    "/api/v1/categories",
    "/api/v1/events/{slug}",
    "/admin/events",
    "/admin/events/{group_id}",
    "/admin/events/{group_id}/resolve",
    "/admin/events/{group_id}/void",
    "/admin/events/{group_id}/reverse",
}


async def test_new_routes_registered() -> None:
    """All eight Phase-16 paths are present on the assembled app (registered in main.py).

    Asserted against the public OpenAPI path table rather than by walking
    ``app.routes``: FastAPI 0.137 stopped flattening ``include_router`` into the top
    level (each inclusion is now an opaque ``_IncludedRouter`` whose leaf routes are
    not exposed as ``.path``), so the old ``{r.path for r in app.routes}`` set no
    longer sees included paths. ``app.openapi()`` is the stable contract. The
    duplicate-operation-id ``UserWarning`` (GET+HEAD on ``/_sentry-test``) is
    orthogonal to route registration, so it is ignored for the schema build only.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        paths = set(app.openapi().get("paths", {}).keys())
    missing = _PHASE16_ROUTES - paths
    assert not missing, f"unregistered Phase-16 routes: {sorted(missing)}"


async def test_catalog_endpoint_live(api) -> None:
    """GET /api/v1/catalog answers 200 + a JSON list on the wired app (empty or not)."""
    resp = await api.get("/api/v1/catalog")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
