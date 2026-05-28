"""Celery Beat tasks for Polymarket sync — poll + snapshot (MKT-05, MKT-06).

poll_polymarket_top25: fetches top-25 active markets from Gamma API every 30s
and upserts them via PolymarketAdapter.sync_top25. Redis SETNX lock prevents
overlapping polls (T-06-05).

snapshot_odds: writes OddsSnapshot rows for every outcome of every OPEN market
(both HOUSE and POLYMARKET) every 5min, building the price-history dataset for
future chart rendering (Phase 9).
"""

from __future__ import annotations

import asyncio

import sentry_sdk
import structlog
from redis.asyncio import Redis as AioRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.core.config import get_settings
from app.integrations.polymarket.adapter import PolymarketAdapter
from app.integrations.polymarket.client import GammaClient
from app.markets.enums import MarketStatus
from app.markets.models import Market, OddsSnapshot

log = structlog.get_logger()

LOCK_KEY = "xpredict:poll:polymarket:lock"


async def acquire_poll_lock(redis: AioRedis) -> bool:
    """Acquire a Redis SETNX lock to prevent overlapping polls (T-06-05).

    TTL is POLYMARKET_LOCK_TTL_SECONDS (default 25s < 30s poll interval),
    so crashed tasks auto-release the lock before the next scheduled poll.
    """
    settings = get_settings()
    ttl = settings.POLYMARKET_LOCK_TTL_SECONDS
    acquired = await redis.set(LOCK_KEY, "1", nx=True, ex=ttl)
    return bool(acquired)


async def release_poll_lock(redis: AioRedis) -> None:
    """Release the poll lock after sync completes."""
    await redis.delete(LOCK_KEY)


async def _run_poll_sync(
    *,
    redis_override: AioRedis | None = None,
    session_override: AsyncSession | None = None,
) -> None:
    """Async logic for poll_polymarket_top25 — testable with injected deps."""
    settings = get_settings()

    # Redis connection — use override for tests, else create from URL.
    redis: AioRedis
    if redis_override is not None:
        redis = redis_override
    else:
        redis = AioRedis.from_url(str(settings.REDIS_URL))

    if not await acquire_poll_lock(redis):
        log.info("poll_skipped", reason="lock_held")
        return

    client = GammaClient()
    try:
        raw_markets = await client.fetch_top_markets(limit=25)

        # Get an async session — use override for tests, else create from factory.
        if session_override is not None:
            session = session_override
        else:
            from app.db.session import _get_session_maker

            session_maker = _get_session_maker()
            session = session_maker()

        try:
            adapter = PolymarketAdapter()
            market_count = await adapter.sync_top25(session, raw_markets)
            await session.commit()
            log.info("poll_complete", market_count=market_count)
        finally:
            if session_override is None:
                await session.close()
    except Exception as exc:
        log.error("poll_failed", error=str(exc))
        sentry_sdk.capture_exception(exc)
    finally:
        await release_poll_lock(redis)
        await client.close()
        if redis_override is None:
            await redis.aclose()


async def _run_snapshot_odds(
    *,
    session_override: AsyncSession | None = None,
) -> None:
    """Async logic for snapshot_odds — writes OddsSnapshot rows for all open markets."""
    if session_override is not None:
        session = session_override
    else:
        from app.db.session import _get_session_maker

        session_maker = _get_session_maker()
        session = session_maker()

    try:
        # Query all OPEN markets with their outcomes.
        stmt = (
            select(Market)
            .where(Market.status == MarketStatus.OPEN.value)
            .options(selectinload(Market.outcomes))
        )
        result = await session.execute(stmt)
        markets = list(result.scalars().all())

        snapshots: list[OddsSnapshot] = []
        for market in markets:
            for outcome in market.outcomes:
                snapshots.append(
                    OddsSnapshot(
                        market_id=market.id,
                        outcome_id=outcome.id,
                        probability=outcome.current_odds,
                    ),
                )

        if snapshots:
            session.add_all(snapshots)
            await session.commit()

        log.info("snapshot_complete", snapshot_count=len(snapshots))
    except Exception as exc:
        log.error("snapshot_failed", error=str(exc))
        sentry_sdk.capture_exception(exc)
    finally:
        if session_override is None:
            await session.close()


@celery_app.task(name="app.integrations.polymarket.tasks.poll_polymarket_top25")
def poll_polymarket_top25() -> None:
    """Celery task wrapping _run_poll_sync in asyncio.run."""
    asyncio.run(_run_poll_sync())


@celery_app.task(name="app.integrations.polymarket.tasks.snapshot_odds")
def snapshot_odds() -> None:
    """Celery task wrapping _run_snapshot_odds in asyncio.run."""
    asyncio.run(_run_snapshot_odds())
