"""``/api/live/*`` router contract (v1.3, LB-A, SC1) — auth gate + light happy path.

Through the FastAPI app via httpx ASGITransport (the lightweight ``client`` fixture in
``tests/conftest.py`` — NO Docker, NO Postgres). Mirrors ``tests/bets/test_bet_router.py``
and ``tests/settlement/test_settlement_router.py``: the real ``current_active_player``
cookie gate 401s without a session; the happy path overrides ``current_active_player``
(a stub player) and ``get_livebets_client`` (a fake, no network) via
``app.dependency_overrides``, cleaned up after every test so nothing leaks.

Two slices, deliberately split for the lightest correctness:
  - AUTH GATE (core SC1): without auth, all four routes — ``POST /bets/{uuid}/placed``,
    ``POST /bets/{uuid}/settled``, ``POST /session``, ``GET /tables`` — return 401. No DB.
  - HAPPY PATH (no DB): ``GET /tables`` -> 200 with the faked catalog and ``POST /session``
    -> 200 with the faked token, via overridden client + auth deps. The DB-touching
    placed/settled money path is proven by ``test_livebets_bridge.py`` (the bridge tests),
    so it is intentionally NOT re-exercised here.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.auth.deps import current_active_player
from app.integrations.livebets.router import get_livebets_client
from app.main import app

pytestmark = [pytest.mark.asyncio]


# --------------------------------------------------------------------------- #
# FakeLiveBetsClient — a tiny in-memory double of the LiveBetsClient surface the
# router calls (mint_session + list_tables). No network: hermetic. (A small local
# copy of the bridge-test double — the router only needs these two methods.)
# --------------------------------------------------------------------------- #
class FakeLiveBetsClient:
    """In-memory stand-in for ``LiveBetsClient`` — the router's reader slice."""

    async def get_bet(self, bet_id: str) -> dict[str, object]:  # pragma: no cover - unused here
        raise AssertionError("router happy-path tests must not reach get_bet")

    async def mint_session(self, **kw: object) -> dict[str, object]:
        return {"session_token": "fake-token", "expires_at": "2026-01-01T00:00:00Z"}

    async def list_tables(self) -> list[dict[str, object]]:
        return [{"table_id": "tbl-1", "name": "Demo Table"}]


class _Player:
    """Minimal authenticated-player stand-in — the routes only read ``id``."""

    def __init__(self, user_id: object) -> None:
        self.id = user_id


@pytest.fixture(autouse=True)
def _clear_overrides() -> AsyncGenerator[None, None]:
    """Reset FastAPI dependency overrides after every test — no cross-test leakage."""
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx ASGITransport client (no Docker) — mirrors the bets/settlement router tests."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _auth_as(player: _Player) -> None:
    app.dependency_overrides[current_active_player] = lambda: player


def _wire_client(client: FakeLiveBetsClient) -> None:
    app.dependency_overrides[get_livebets_client] = lambda: client


# --------------------------------------------------------------------------- #
# AUTH GATE (SC1) — every /api/live/* route rejects an unauthenticated request
# with 401 (the real current_active_player cookie gate, no override). No DB needed.
# --------------------------------------------------------------------------- #
async def test_post_placed_requires_auth(api: httpx.AsyncClient) -> None:
    r = await api.post(f"/api/live/bets/{uuid4()}/placed")
    assert r.status_code == 401


async def test_post_settled_requires_auth(api: httpx.AsyncClient) -> None:
    r = await api.post(f"/api/live/bets/{uuid4()}/settled")
    assert r.status_code == 401


async def test_post_session_requires_auth(api: httpx.AsyncClient) -> None:
    r = await api.post("/api/live/session", json={})
    assert r.status_code == 401


async def test_get_tables_requires_auth(api: httpx.AsyncClient) -> None:
    r = await api.get("/api/live/tables")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# HAPPY PATH (no DB) — GET /tables and POST /session succeed with overridden
# client + auth deps, returning the faked catalog / token.
# --------------------------------------------------------------------------- #
async def test_get_tables_happy_path_returns_faked_catalog(api: httpx.AsyncClient) -> None:
    _auth_as(_Player(uuid4()))
    _wire_client(FakeLiveBetsClient())

    r = await api.get("/api/live/tables")

    assert r.status_code == 200
    body = r.json()
    assert body["tables"] == [{"table_id": "tbl-1", "name": "Demo Table"}]


async def test_post_session_happy_path_returns_faked_token(api: httpx.AsyncClient) -> None:
    _auth_as(_Player(uuid4()))
    _wire_client(FakeLiveBetsClient())

    # Supply table_id in the body so the route does not need LIVEBETS_DEFAULT_TABLE_ID
    # (which defaults to None in the test env).
    r = await api.post("/api/live/session", json={"table_id": "tbl-1"})

    assert r.status_code == 200
    body = r.json()
    assert body["session_token"] == "fake-token"
    assert body["expires_at"] == "2026-01-01T00:00:00Z"
