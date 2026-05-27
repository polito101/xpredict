"""/healthz + /readyz tests with mocked dependencies — D-30 / PLT-10 coverage.

The /readyz tests use FastAPI's ``app.dependency_overrides`` to swap
``get_async_session`` and ``get_redis`` for in-test stubs. This keeps the test
suite under 30 seconds — testcontainers Postgres lives in Plan 01-03 where the
real DB+Redis integration test runs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest

from app.core.redis import get_redis
from app.db.session import get_async_session
from app.main import app

# ---------------------------------------------------------------------------
# Stubs that mimic the AsyncSession / Redis surface readyz pings
# ---------------------------------------------------------------------------


class _StubSession:
    """Mimics AsyncSession; .execute() returns a no-op result."""

    def __init__(self, *, raise_on_execute: Exception | None = None) -> None:
        self._raise = raise_on_execute

    async def execute(self, _stmt: Any) -> Any:
        if self._raise is not None:
            raise self._raise
        return None


class _StubRedis:
    """Mimics redis.asyncio.Redis; .ping() returns True or raises."""

    def __init__(self, *, raise_on_ping: Exception | None = None) -> None:
        self._raise = raise_on_ping

    async def ping(self) -> bool:
        if self._raise is not None:
            raise self._raise
        return True

    async def aclose(self) -> None:
        return None


def _override_session(
    raise_on_execute: Exception | None = None,
) -> Any:
    async def _dep() -> AsyncGenerator[_StubSession, None]:
        yield _StubSession(raise_on_execute=raise_on_execute)

    return _dep


def _override_redis(raise_on_ping: Exception | None = None) -> Any:
    async def _dep() -> AsyncGenerator[_StubRedis, None]:
        yield _StubRedis(raise_on_ping=raise_on_ping)

    return _dep


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_healthz_returns_ok(client: httpx.AsyncClient) -> None:
    """GET /healthz returns 200 + {"status":"ok"} with no dependency probes."""
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_ready_when_deps_ok(client: httpx.AsyncClient) -> None:
    """GET /readyz returns 200 + {"status":"ready"} when both deps respond."""
    app.dependency_overrides[get_async_session] = _override_session()
    app.dependency_overrides[get_redis] = _override_redis()
    try:
        response = await client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readyz_returns_503_when_db_fails(client: httpx.AsyncClient) -> None:
    """GET /readyz returns 503 with `db` listed in failures when DB raises."""
    app.dependency_overrides[get_async_session] = _override_session(
        raise_on_execute=RuntimeError("simulated db outage")
    )
    app.dependency_overrides[get_redis] = _override_redis()
    try:
        response = await client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        # FastAPI wraps HTTPException(detail=...) under `detail`
        assert body["detail"]["status"] == "not_ready"
        assert "db" in body["detail"]["failures"]
        # MUST NOT echo the connection string
        assert "postgresql" not in str(body).lower()
        assert "redis" not in body["detail"]["failures"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readyz_returns_503_when_redis_fails(client: httpx.AsyncClient) -> None:
    """GET /readyz returns 503 with `redis` listed in failures when Redis raises."""
    app.dependency_overrides[get_async_session] = _override_session()
    app.dependency_overrides[get_redis] = _override_redis(
        raise_on_ping=RuntimeError("simulated redis outage")
    )
    try:
        response = await client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["detail"]["status"] == "not_ready"
        assert "redis" in body["detail"]["failures"]
        assert "db" not in body["detail"]["failures"]
    finally:
        app.dependency_overrides.clear()
