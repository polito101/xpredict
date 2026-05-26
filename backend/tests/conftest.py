"""pytest fixtures — testcontainers Postgres + fakeredis + FastAPI client (Plan 01-01 Task 3).

Phase 1 Plan 01-01 ships the fixture *definitions*; only the lightweight ones
(``fake_redis``, ``client``) are actually used in this plan's tests. The
testcontainers Postgres fixture (``postgres_container``, ``engine``,
``async_session``) is defined here so Plan 01-03 — which adds the audit
immutability + feature-flag integration tests — inherits a working
infrastructure with zero rewiring.

Crucially: the Postgres-touching fixtures are *lazy* — they only spawn Docker
when a test actually requests them. Tests that don't reference them run with
zero Docker dependency.

A session-level ``_test_env_setup`` autouse fixture seeds ``DATABASE_URL``,
``DATABASE_URL_SYNC``, and ``REDIS_URL`` env vars so ``Settings()`` can be
instantiated everywhere without bespoke per-test monkeypatch. Tests that
exercise validation errors (e.g., malformed URLs) override this with explicit
constructor args.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from testcontainers.postgres import PostgresContainer


# ---------------------------------------------------------------------------
# Environment seeding (runs at conftest IMPORT, before any test collection)
# ---------------------------------------------------------------------------
#
# Module-level seeding is required because ``app.celery_app`` (and any future
# module that instantiates ``Settings()`` at import time) is loaded during
# collection — before any pytest fixture runs. Setting env vars in a
# session-scoped fixture would be too late.
#
# Tests that need to verify Settings validation (e.g., malformed URL,
# extra-key ignore) pass explicit constructor args, so they don't rely on
# this default.

_DEFAULT_TEST_ENV: dict[str, str] = {
    "ENVIRONMENT": "dev",
    "DATABASE_URL": "postgresql+asyncpg://xpredict:xpredict@localhost:5432/xpredict",
    "DATABASE_URL_SYNC": "postgresql+psycopg2://xpredict:xpredict@localhost:5432/xpredict",
    "REDIS_URL": "redis://localhost:6379/0",
    "SENTRY_DSN": "",
    "LOG_LEVEL": "INFO",
}

for _k, _v in _DEFAULT_TEST_ENV.items():
    os.environ.setdefault(_k, _v)


# ---------------------------------------------------------------------------
# Lightweight fixtures (no Docker, used by Plan 01-01 tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> Generator[Any, None, None]:
    """Yield an in-memory ``fakeredis.aioredis.FakeRedis`` client."""
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        # FakeRedis cleanup is sync — no aclose() needed for in-memory state
        pass


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """FastAPI test client wired through httpx ASGITransport.

    ``raise_app_exceptions=False`` so that ``/_sentry-test`` (and any future
    route that intentionally raises) returns a real 500 response — Sentry's
    integration relies on FastAPI's ``ServerErrorMiddleware`` to convert the
    exception, and we want to exercise that path in the test.
    """
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Heavyweight fixtures (testcontainers Postgres) — used by Plan 01-03+
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Session-scoped Postgres 16 container.

    Marked LAZY: only starts when a test that actually depends on this
    fixture is collected. Plan 01-01 tests do NOT request it, so no Docker
    daemon is required to run the Wave-0 unit suite.
    """
    pytest.importorskip("testcontainers", reason="testcontainers required for Postgres fixtures")
    from testcontainers.postgres import PostgresContainer

    with warnings.catch_warnings():
        # testcontainers emits DeprecationWarnings on its internal HTTP probes.
        warnings.simplefilter("ignore", DeprecationWarning)
        with PostgresContainer("postgres:16-alpine") as pg:
            yield pg


@pytest.fixture(scope="session")
async def engine(postgres_container: PostgresContainer) -> AsyncGenerator[AsyncEngine, None]:
    """Async engine bound to the testcontainer.

    Plan 01-03 will replace this fixture's body with one that runs
    ``alembic upgrade head`` first; for now it just constructs the engine —
    schema setup is the responsibility of the test that uses it.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    eng = create_async_engine(url, pool_pre_ping=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def async_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped ``AsyncSession`` wrapped in a transaction that rolls back.

    Provides clean DB state between tests without recreating the schema.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                yield session
        finally:
            await trans.rollback()
