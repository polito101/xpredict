"""Redis async client + FastAPI dependency.

Phase 1 ships a real ``get_redis()`` (per RESEARCH.md Open Question #1) so
``/readyz`` can PING it (D-30) and Phases 2+ inherit a working dep without
rewiring.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import get_settings


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding an async Redis client.

    Creates a fresh client per request and closes it on teardown. For Phases 2+
    that need a shared connection pool, consider promoting to a lifespan-managed
    singleton — but the per-request pattern keeps tests trivial.
    """
    settings = get_settings()
    client: Redis = Redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
