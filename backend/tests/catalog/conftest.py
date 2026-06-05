"""Shared fixtures for the Phase-16 catalog + admin-event endpoint tests.

This conftest is the Wave-0 scaffolding the later Phase-16 plans import. It mirrors
``tests/settlement/test_settlement_router.py`` (lines 36-64) byte-for-byte for the
``api`` AsyncClient fixture and the autouse testcontainer/override fixtures, and it
deliberately does **not** redefine the heavyweight ``engine`` / ``async_session``
fixtures — those live in the parent ``backend/tests/conftest.py`` and are discovered
automatically by pytest (a child conftest inherits its parents' fixtures).

Why each piece exists:

- ``pytestmark`` — every test in this package is an integration test on the
  session-scoped event loop (real Postgres via testcontainers).
- ``api`` — an httpx ``AsyncClient`` over ``ASGITransport(app=app,
  raise_app_exceptions=False)`` so a route that intentionally raises returns a real
  4xx/5xx response (FastAPI's ``ServerErrorMiddleware`` converts it) instead of
  bubbling the exception into the test.
- ``_require_testcontainer`` — an autouse fixture that simply depends on the parent
  ``engine`` fixture so the testcontainer Postgres is spun up (and ``alembic upgrade
  head`` applied) before any catalog test runs, even one that only touches the
  ``api`` client.
- ``_clear_overrides`` — an autouse fixture that clears ``app.dependency_overrides``
  after every test so an admin override set by one test (e.g. ``current_active_admin``)
  never leaks into the next, keeping the auth-gate negative tests (16-03/16-04) honest
  (threat T-16-00b: a leaked override would mask the real 401 gate).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import httpx
import pytest
import pytest_asyncio

from app.main import app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Force the testcontainer Postgres up (parent ``engine`` fixture) for every test."""
    return engine


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Clear FastAPI dependency overrides after each test (no auth-override leak)."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _register_phase16_routers() -> None:
    """Mount the Phase-16 catalog/event routers on the test app (idempotently).

    ``app.main`` registers these routers only in plan 16-05 (deferred so a single
    plan owns the ``main.py`` edit instead of having both the wave-1 catalog router
    and the wave-2 event router collide on it). The endpoint tests in this package
    must reach those routes via the shared ``api`` client BEFORE 16-05 wires them in,
    so this autouse fixture includes them here. It is idempotent (skips a router
    already present) and import-guarded (a router whose plan has not run yet is simply
    skipped), so it is a no-op once 16-05 registers them in ``main.py``.
    """
    existing = {getattr(r, "path", None) for r in app.routes}
    try:
        from app.catalog.router import public_catalog_router

        if "/api/v1/catalog" not in existing:
            app.include_router(public_catalog_router)
    except ImportError:
        pass


@pytest_asyncio.fixture(loop_scope="session")
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    """An httpx ``AsyncClient`` wired through the FastAPI app via ``ASGITransport``."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
