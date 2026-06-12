"""``GET /api/v1/casino/games`` router contract (quick task 260611-u0q).

Hermetic: through the FastAPI app via httpx ASGITransport (NO Docker, NO Postgres,
NO real Redis, NO network). Mirrors ``tests/integrations/livebets/test_livebets_router.py``:
an autouse ``app.dependency_overrides.clear()`` fixture, ``get_slotslaunch_client``
overridden with a ``FakeSlotsLaunchClient``, and ``get_redis`` overridden with an
in-memory dict-backed ``FakeRedis`` so the cache path is exercised without a server.

The token is forced ON via ``monkeypatch`` of the settings singleton (so the service's
"token unset -> inactive" short-circuit does not mask the active-fetch path), then the
``get_settings`` LRU cache is cleared after each test.

Cases (the SC of the plan):
  - ACTIVE: upstream returns a ``data`` array -> 200, status="active", games whose
    ``iframe_url`` contains ``/iframe/`` and the composed token (token ONLY in iframe_url).
  - INACTIVE: upstream body ``{"error": ...}`` -> 200, status="inactive", games=[].
  - UPSTREAM ERROR: client raises (network) -> 200, status="inactive", games=[].
  - CACHE: a warm Redis hit short-circuits the upstream client entirely.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

from app.core.config import get_settings
from app.core.redis import get_redis
from app.integrations.slotslaunch.router import get_slotslaunch_client
from app.main import app

pytestmark = [pytest.mark.asyncio]

_TOKEN = "test-token-abc123"
_API_BASE = "https://slotslaunch.com"


# --------------------------------------------------------------------------- #
# FakeRedis — a tiny in-memory dict-backed double of the async Redis surface the
# service uses (get / set). No server: hermetic. ``set`` ignores the TTL (the test
# does not advance time); a warm-cache test seeds the dict directly.
# --------------------------------------------------------------------------- #
class FakeRedis:
    """In-memory async stand-in for ``redis.asyncio.Redis`` — get/set only."""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = store if store is not None else {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True


# --------------------------------------------------------------------------- #
# FakeSlotsLaunchClient — returns a canned upstream body (active data, inactive
# error, or raises). ``calls`` counts fetch invocations so the cache test can
# assert the upstream was never touched.
# --------------------------------------------------------------------------- #
class FakeSlotsLaunchClient:
    """In-memory stand-in for ``SlotsLaunchClient`` — canned ``fetch_games``."""

    def __init__(
        self,
        *,
        body: dict[str, object] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._body = body
        self._raises = raises
        self.calls = 0

    async def fetch_games(self, per_page: int = 150) -> dict[str, object]:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        assert self._body is not None
        return self._body


@pytest.fixture(autouse=True)
def _clear_overrides_and_settings() -> AsyncGenerator[None, None]:
    """Reset FastAPI overrides + the settings LRU cache after every test."""
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _token_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the SlotsLaunch token + api-base ON (the active-path tests need it set).

    Clears the LRU first so a fresh ``Settings()`` picks up the patched env, then
    the post-test fixture clears it again so other suites are unaffected.
    """
    get_settings.cache_clear()
    monkeypatch.setenv("SLOTSLAUNCH_TOKEN", _TOKEN)
    monkeypatch.setenv("SLOTSLAUNCH_API_BASE", _API_BASE)


@pytest_asyncio.fixture
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx ASGITransport client (no Docker) — mirrors the livebets router tests."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _wire(client: FakeSlotsLaunchClient, redis: FakeRedis | None = None) -> FakeRedis:
    redis = redis or FakeRedis()
    app.dependency_overrides[get_slotslaunch_client] = lambda: client

    async def _redis_dep() -> AsyncGenerator[FakeRedis, None]:
        yield redis

    app.dependency_overrides[get_redis] = _redis_dep
    return redis


# --------------------------------------------------------------------------- #
# ACTIVE — upstream `data` array -> status="active" with composed iframe URLs.
# --------------------------------------------------------------------------- #
async def test_active_returns_games_with_composed_iframe_url(
    api: httpx.AsyncClient,
) -> None:
    body = {
        "data": [
            {
                "id": 42,
                "name": "Starburst",
                "slug": "starburst",
                "provider": "NetEnt",
                "thumb": "https://cdn.example/starburst.png",
            }
        ],
        "meta": {},
    }
    _wire(FakeSlotsLaunchClient(body=body))

    r = await api.get("/api/v1/casino/games")

    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "active"
    assert len(payload["games"]) == 1
    game = payload["games"][0]
    assert game["id"] == "42"
    assert game["name"] == "Starburst"
    assert game["provider"] == "NetEnt"
    assert game["thumb"] == "https://cdn.example/starburst.png"
    # The iframe_url is backend-composed and is the ONLY field carrying the token.
    assert game["iframe_url"] == f"{_API_BASE}/iframe/42?token={_TOKEN}"
    assert "/iframe/" in game["iframe_url"]
    assert _TOKEN in game["iframe_url"]
    # Token never leaks into any other game field.
    for key, value in game.items():
        if key == "iframe_url":
            continue
        assert _TOKEN not in str(value)


# --------------------------------------------------------------------------- #
# INACTIVE — upstream `{"error": ...}` body -> status="inactive", games=[], 200.
# --------------------------------------------------------------------------- #
async def test_inactive_subscription_returns_empty_200(api: httpx.AsyncClient) -> None:
    body = {"error": "Your Slots Launch subscription is not active"}
    fake = FakeSlotsLaunchClient(body=body)
    _wire(fake)

    r = await api.get("/api/v1/casino/games")

    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "inactive"
    assert payload["games"] == []
    assert fake.calls == 1


async def test_inactive_is_not_cached(api: httpx.AsyncClient) -> None:
    """Inactive must NOT be cached — it must light up the moment the sub activates."""
    fake = FakeSlotsLaunchClient(body={"error": "not active"})
    redis = _wire(fake)

    await api.get("/api/v1/casino/games")

    assert "casino:catalog" not in redis.store


# --------------------------------------------------------------------------- #
# UPSTREAM ERROR — client raises (network) -> status="inactive", games=[], 200.
# --------------------------------------------------------------------------- #
async def test_upstream_failure_degrades_to_inactive_200(
    api: httpx.AsyncClient,
) -> None:
    fake = FakeSlotsLaunchClient(raises=httpx.ConnectError("boom"))
    _wire(fake)

    r = await api.get("/api/v1/casino/games")

    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "inactive"
    assert payload["games"] == []


# --------------------------------------------------------------------------- #
# CACHE — a warm Redis hit short-circuits the upstream client entirely.
# --------------------------------------------------------------------------- #
async def test_warm_cache_short_circuits_upstream(api: httpx.AsyncClient) -> None:
    cached = (
        '{"status":"active","games":[{"id":"7","name":"Cached Slot",'
        '"provider":null,"thumb":null,'
        f'"iframe_url":"{_API_BASE}/iframe/7?token={_TOKEN}"}}]}}'
    )
    fake = FakeSlotsLaunchClient(body={"data": []})
    _wire(fake, redis=FakeRedis(store={"casino:catalog": cached}))

    r = await api.get("/api/v1/casino/games")

    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "active"
    assert payload["games"][0]["id"] == "7"
    # The upstream client was never invoked — served from the warm cache.
    assert fake.calls == 0


async def test_active_fetch_populates_cache(api: httpx.AsyncClient) -> None:
    body = {"data": [{"id": 1, "name": "S", "provider": "P", "thumb": None}]}
    fake = FakeSlotsLaunchClient(body=body)
    redis = _wire(fake)

    await api.get("/api/v1/casino/games")

    assert "casino:catalog" in redis.store
    assert fake.calls == 1
