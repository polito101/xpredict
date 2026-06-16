"""Catalog Redis cache (cache-aside) integration tests.

``GET /api/v1/catalog`` is the demo's heaviest read: its server-time scales with the
row count (it materializes every event's children + outcomes and projects status /
volume in Python), and the frontend re-fetches it on every navigation (``no-store``).
A short-TTL Redis cache makes repeat browses instant. These tests pin the cache-aside
contract, mirroring the SlotsLaunch casino cache (the project's existing pattern):

  - a warm key short-circuits the DB query (a row added after the first call is not
    visible on the second);
  - free-text search (``q``) is never cached (high-cardinality keys, already fast);
  - the ``CATALOG_CACHE_TTL_SECONDS=0`` kill-switch disables caching entirely;
  - an unavailable Redis degrades to a live query (never 500s) — the cache is an
    optimization, not a correctness dependency.
"""

from __future__ import annotations

import pytest

from app.core.redis import get_redis
from app.db.session import get_async_session
from app.main import app
from tests.catalog._factories import make_market

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


def _use(async_session) -> None:
    """Route the app's get_async_session dependency through the test's session."""
    app.dependency_overrides[get_async_session] = lambda: async_session


async def test_catalog_result_is_served_from_cache(api, async_session, catalog_redis) -> None:
    """A warm cache short-circuits the DB query.

    A market added *after* the first browse must NOT appear on a second identical
    browse — proving the second response came from Redis, not a fresh query.
    """
    _use(async_session)
    await make_market(async_session, question="Cached market alpha?")
    await async_session.flush()

    first = await api.get("/api/v1/catalog")
    assert first.status_code == 200
    first_titles = [it["title"] for it in first.json()]
    assert any("Cached market alpha" in t for t in first_titles)

    # Add a NEW market once the cache is warm.
    await make_market(async_session, question="Should-be-hidden market beta?")
    await async_session.flush()

    second = await api.get("/api/v1/catalog")
    assert second.status_code == 200
    second_titles = [it["title"] for it in second.json()]

    # Served from the warm cache -> identical to the first, new market invisible.
    assert all("Should-be-hidden market beta" not in t for t in second_titles)
    assert second_titles == first_titles


async def test_search_q_bypasses_cache(api, async_session, catalog_redis) -> None:
    """Free-text search is never cached.

    A row added between two identical searches must appear on the second call, and
    nothing is written to Redis for a search query (high-cardinality keys).
    """
    _use(async_session)
    await make_market(async_session, question="Searchable zorptoken one?")
    await async_session.flush()

    await api.get("/api/v1/catalog", params={"q": "zorptoken"})

    await make_market(async_session, question="Searchable zorptoken two?")
    await async_session.flush()

    second = await api.get("/api/v1/catalog", params={"q": "zorptoken"})
    second_titles = [it["title"] for it in second.json()]
    assert any("two" in t for t in second_titles)  # fresh, not served from cache
    assert await catalog_redis.dbsize() == 0  # a search query writes no cache keys


async def test_ttl_zero_disables_cache(api, async_session, monkeypatch) -> None:
    """CATALOG_CACHE_TTL_SECONDS=0 is the kill-switch — every browse is live."""
    from app.core.config import get_settings

    # Patch the cached settings instance in place; monkeypatch restores it after.
    monkeypatch.setattr(get_settings(), "CATALOG_CACHE_TTL_SECONDS", 0)
    _use(async_session)
    await make_market(async_session, question="Killswitch market uno?")
    await async_session.flush()

    await api.get("/api/v1/catalog")  # would warm a cache if it were enabled

    await make_market(async_session, question="Killswitch market dos?")
    await async_session.flush()

    titles = [it["title"] for it in (await api.get("/api/v1/catalog")).json()]
    assert any("dos" in t for t in titles)  # live — caching disabled


async def test_unavailable_redis_degrades_to_live_query(api, async_session) -> None:
    """A Redis that raises on every call must NOT 500 the catalog — it serves live."""

    class _BoomRedis:
        async def get(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("redis down")

        async def set(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("redis down")

    async def _dep():
        yield _BoomRedis()

    app.dependency_overrides[get_redis] = _dep  # replaces the conftest fake for this test
    _use(async_session)
    await make_market(async_session, question="Resilient market under redis outage?")
    await async_session.flush()

    resp = await api.get("/api/v1/catalog")
    assert resp.status_code == 200
    assert any("Resilient market" in it["title"] for it in resp.json())
