"""Celery Beat tasks for Polymarket sync — poll + snapshot + auto-resolution (STL-01).

poll_polymarket_top25: fetches top-25 active markets from Gamma API every 30s
and upserts them via PolymarketAdapter.sync_top25. Redis SETNX lock prevents
overlapping polls (T-06-05).

snapshot_odds: writes OddsSnapshot rows for every outcome of every OPEN market
(both HOUSE and POLYMARKET) every 5min, building the price-history dataset for
future chart rendering (Phase 9).

detect_polymarket_resolutions: checks Polymarket-mirrored markets for UMA oracle
resolution every 60s, applying a configurable grace period before triggering
SettlementService (STL-01). Lock key is distinct from the poll lock (T-07-04).
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import sentry_sdk
import structlog
from redis.asyncio import Redis as AioRedis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.core.config import get_settings
from app.integrations.polymarket.adapter import PolymarketAdapter, _map_winning_outcome_id
from app.integrations.polymarket.client import GammaClient
from app.integrations.polymarket.schemas import GammaMarket
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot

log = structlog.get_logger()

LOCK_KEY = "xpredict:poll:polymarket:lock"
DETECT_LOCK_KEY = "xpredict:detect:polymarket:lock"


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
    session: AsyncSession | None = None
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
        if session is not None:
            with contextlib.suppress(Exception):
                await session.rollback()
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
        with contextlib.suppress(Exception):
            await session.rollback()
    finally:
        if session_override is None:
            await session.close()


async def _run_detect_resolutions(
    *,
    redis_override: AioRedis | None = None,
    session_override: AsyncSession | None = None,
) -> None:
    """Async logic for detect_polymarket_resolutions — testable with injected deps."""
    from pydantic import ValidationError

    settings = get_settings()

    redis: AioRedis
    if redis_override is not None:
        redis = redis_override
    else:
        redis = AioRedis.from_url(str(settings.REDIS_URL))

    # Acquire a distinct lock — never reuse the poll lock (T-07-04).
    lock_ttl = settings.POLYMARKET_LOCK_TTL_SECONDS + 35
    acquired = await redis.set(DETECT_LOCK_KEY, "1", nx=True, ex=lock_ttl)
    if not acquired:
        log.info("detect_skipped", reason="lock_held")
        if redis_override is None:
            await redis.aclose()
        return

    session: AsyncSession | None = None
    try:
        if session_override is not None:
            session = session_override
        else:
            from app.db.session import _get_session_maker

            session = _get_session_maker()()

        now = datetime.now(UTC)
        stmt = (
            select(Market)
            .where(Market.source == MarketSourceEnum.POLYMARKET.value)
            .where(Market.status.in_([MarketStatus.OPEN.value, MarketStatus.CLOSED.value]))
            .where(Market.deadline < now)
            .options(selectinload(Market.outcomes))
        )
        result = await session.execute(stmt)
        candidates = list(result.scalars().all())

        for market in candidates:
            if market.source_market_id is None:
                continue

            client = GammaClient()
            try:
                raw = await client.fetch_market_by_id(market.source_market_id)
            finally:
                await client.close()

            if raw is None:
                continue

            try:
                parsed = GammaMarket.model_validate(raw)
            except ValidationError:
                log.warning("gamma.parse_failed", source_market_id=market.source_market_id)
                continue

            if parsed.internal_status != MarketStatus.RESOLVED:
                continue

            # Grace-period gating (T-07-04): first tick sets uma_resolved_at via conditional
            # UPDATE (WHERE uma_resolved_at IS NULL) to prevent double-start races.
            if market.uma_resolved_at is None:
                await session.execute(
                    text(
                        "UPDATE markets SET uma_resolved_at = :now"
                        " WHERE id = :id AND uma_resolved_at IS NULL"
                    ),
                    {"now": now, "id": market.id},
                )
                await session.commit()
                log.info("detect_grace_started", market_id=str(market.id))
                continue

            ts = market.uma_resolved_at
            aware_ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts
            elapsed = now - aware_ts
            if elapsed < timedelta(minutes=settings.POLYMARKET_GRACE_PERIOD_MINUTES):
                continue

            # Grace elapsed — settle via SettlementService (unchanged, STL-01).
            try:
                winning_outcome_id = _map_winning_outcome_id(
                    parsed.outcome_prices_raw,
                    parsed.outcomes_raw,
                    market.outcomes,
                )
            except ValueError as exc:
                log.warning(
                    "detect_winner_mapping_failed",
                    error=str(exc),
                    market_id=str(market.id),
                )
                continue

            from app.settlement.adapters import HouseMarketResolveAdapter
            from app.settlement.service import SettlementService

            try:
                await SettlementService.resolve_market(
                    session,
                    market_id=market.id,
                    winning_outcome_id=winning_outcome_id,
                    market_resolver=HouseMarketResolveAdapter(),
                    justification="Auto-resolved: Polymarket UMA oracle confirmed resolution",
                    actor_user_id=None,
                )
                log.info("detect_settled", market_id=str(market.id))
            except Exception as exc:
                log.error("detect_settle_failed", error=str(exc), market_id=str(market.id))
                sentry_sdk.capture_exception(exc)

        if session_override is None:
            with contextlib.suppress(Exception):
                await session.close()

    except Exception as exc:
        log.error("detect_failed", error=str(exc))
        sentry_sdk.capture_exception(exc)
        if session is not None:
            with contextlib.suppress(Exception):
                await session.rollback()
        if session is not None and session_override is None:
            with contextlib.suppress(Exception):
                await session.close()
    finally:
        await redis.delete(DETECT_LOCK_KEY)
        if redis_override is None:
            await redis.aclose()


@celery_app.task(name="app.integrations.polymarket.tasks.poll_polymarket_top25")  # type: ignore[untyped-decorator]
def poll_polymarket_top25() -> None:
    """Celery task wrapping _run_poll_sync in asyncio.run."""
    asyncio.run(_run_poll_sync())


@celery_app.task(name="app.integrations.polymarket.tasks.snapshot_odds")  # type: ignore[untyped-decorator]
def snapshot_odds() -> None:
    """Celery task wrapping _run_snapshot_odds in asyncio.run."""
    asyncio.run(_run_snapshot_odds())


@celery_app.task(name="app.integrations.polymarket.tasks.detect_polymarket_resolutions")  # type: ignore[untyped-decorator]
def detect_polymarket_resolutions() -> None:
    """Beat task: check for UMA-resolved Polymarket markets every 60s (STL-01)."""
    asyncio.run(_run_detect_resolutions())
