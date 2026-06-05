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
import uuid
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
from app.integrations.polymarket.schemas import GammaEvent, GammaMarket, resolve_category
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot
from app.realtime.publisher import publish_odds_change_async

log = structlog.get_logger()

LOCK_KEY = "xpredict:poll:polymarket:lock"
DETECT_LOCK_KEY = "xpredict:detect:polymarket:lock"
# Distinct lock for the curated per-category events poll (Phase 14, WR-05). NEVER
# reuse LOCK_KEY/DETECT_LOCK_KEY — the events poll fires on its own 5-min tick and
# must not block (or be blocked by) the 30s top-25 poll or the 60s detector.
EVENTS_LOCK_KEY = "xpredict:poll:events:lock"

# Compare-and-delete: only delete the lock if WE still own it (WR-05). An
# unconditional ``delete`` lets a slow task that has already lost the lock
# (TTL expired → another task re-acquired) delete the NEW owner's lock, letting
# two tasks overlap — exactly what the lock prevents. Releasing with the owning
# token closes that race.
_RELEASE_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


async def acquire_poll_lock(redis: AioRedis) -> str | None:
    """Acquire a Redis SETNX lock to prevent overlapping polls (T-06-05).

    Returns a unique ownership TOKEN on success (pass it to ``release_poll_lock``
    so only the owner can release — WR-05), or ``None`` if the lock is held.
    TTL is POLYMARKET_LOCK_TTL_SECONDS (default 25s < 30s poll interval), so
    crashed tasks auto-release the lock before the next scheduled poll.
    """
    settings = get_settings()
    ttl = settings.POLYMARKET_LOCK_TTL_SECONDS
    token = uuid.uuid4().hex
    acquired = await redis.set(LOCK_KEY, token, nx=True, ex=ttl)
    return token if acquired else None


async def release_poll_lock(redis: AioRedis, token: str) -> None:
    """Release the poll lock — only if THIS task still owns it (WR-05).

    Compare-and-delete via Lua so a task whose lock already expired (and was
    re-acquired by another task) cannot delete the new owner's lock.
    """
    # redis-py's async ``eval`` is typed ``Awaitable[str] | str`` in the stubs
    # (shared sync/async signature); the async client always returns an awaitable
    # at runtime, so the await is correct — the union is a stub limitation.
    await redis.eval(_RELEASE_LOCK_LUA, 1, LOCK_KEY, token)  # type: ignore[misc]


async def acquire_events_lock(redis: AioRedis) -> str | None:
    """Acquire the curated-events poll lock (T-14-13) — distinct from the poll lock.

    Mirrors ``acquire_poll_lock`` (SETNX owner-token, WR-05) but on
    ``EVENTS_LOCK_KEY`` with TTL = POLYMARKET_EVENTS_LOCK_TTL_SECONDS (default
    280s < the 300s events tick), so a crashed events poll auto-releases before
    the next scheduled run. Returns the ownership token on success, else ``None``.
    """
    settings = get_settings()
    ttl = settings.POLYMARKET_EVENTS_LOCK_TTL_SECONDS
    token = uuid.uuid4().hex
    acquired = await redis.set(EVENTS_LOCK_KEY, token, nx=True, ex=ttl)
    return token if acquired else None


async def release_events_lock(redis: AioRedis, token: str) -> None:
    """Release the events poll lock — only if THIS task still owns it (WR-05).

    Compare-and-delete via the shared ``_RELEASE_LOCK_LUA`` keyed on
    ``EVENTS_LOCK_KEY`` so a task whose lock already expired (and was re-acquired
    by another task) cannot delete the new owner's lock.
    """
    # See release_poll_lock for the eval stub-typing note.
    await redis.eval(_RELEASE_LOCK_LUA, 1, EVENTS_LOCK_KEY, token)  # type: ignore[misc]


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

    lock_token = await acquire_poll_lock(redis)
    if lock_token is None:
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
            # Real-time publish (MKT-04 / producer site #2): POST-COMMIT, per-market,
            # on-change only (adapter.changed_markets holds only committed changes).
            # A Redis hiccup must never fail the poll — log and swallow per market.
            for market_id, deltas in adapter.changed_markets:
                try:
                    await publish_odds_change_async(redis, market_id, deltas)
                except Exception as pub_exc:
                    log.warning(
                        "realtime.publish_failed",
                        market_id=market_id,
                        error=str(pub_exc),
                    )
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
        await release_poll_lock(redis, lock_token)
        await client.close()
        if redis_override is None:
            await redis.aclose()


async def _run_poll_events(
    *,
    redis_override: AioRedis | None = None,
    session_override: AsyncSession | None = None,
) -> None:
    """Async logic for poll_polymarket_events — the curated per-category sync loop.

    Loops ``POLYMARKET_CATEGORIES`` in PRIORITY ORDER (CAT-03). Per category:
    fetch ``/events`` by ``tag_id`` (volume-ranked), parse to ``GammaEvent``
    (skipping ``ValidationError`` elements), dedup by event id against a
    cycle-level ``seen_event_ids`` set (first-by-priority — a higher-priority
    category already took the event; CAT-02 + Pitfall 4), apply the
    ``POLYMARKET_VOLUME_FLOOR`` on ``volume_24hr_decimal`` AFTER dedup (CAT-02),
    take the first ``POLYMARKET_EVENTS_TOP_N``, then ``sync_events`` + COMMIT for
    THAT category. Each category is wrapped in its own try/except: on any failure
    it is logged, rolled back, and skipped — the other categories still sync and
    the failed category keeps its last-good committed rows (CAT-05; the catalog
    is never blanked because the sync only upserts, never deletes).

    A distinct ``EVENTS_LOCK_KEY`` SETNX owner-token lock prevents overlapping
    cycles (T-14-13). Testable via injected ``redis_override`` / ``session_override``.
    """
    from pydantic import ValidationError

    settings = get_settings()
    floor = settings.POLYMARKET_VOLUME_FLOOR
    top_n = settings.POLYMARKET_EVENTS_TOP_N

    # Redis connection — use override for tests, else create from URL.
    redis: AioRedis
    if redis_override is not None:
        redis = redis_override
    else:
        redis = AioRedis.from_url(str(settings.REDIS_URL))

    lock_token = await acquire_events_lock(redis)
    if lock_token is None:
        log.info("poll_events_skipped", reason="lock_held")
        if redis_override is None:
            await redis.aclose()
        return

    client = GammaClient()
    session: AsyncSession | None = None
    try:
        # Get an async session — use override for tests, else create from factory.
        if session_override is not None:
            session = session_override
        else:
            from app.db.session import _get_session_maker

            session_maker = _get_session_maker()
            session = session_maker()

        adapter = PolymarketAdapter()
        # Cycle-level event-id dedup set — gives first-by-priority across
        # categories (an event taken by a higher-priority category is skipped
        # when a lower-priority category surfaces the same id; Pitfall 4).
        seen_event_ids: set[str] = set()

        for entry in settings.POLYMARKET_CATEGORIES:  # priority order (CAT-03)
            try:
                raw_events = await client.fetch_events(tag_id=entry.tag_id, limit=top_n)

                # Parse, skipping malformed elements (T-14-12 — a poisoned element
                # must not crash the cycle).
                parsed: list[GammaEvent] = []
                for raw in raw_events:
                    try:
                        parsed.append(GammaEvent.model_validate(raw))
                    except ValidationError:
                        log.warning("poll_events.parse_failed", category=entry.name)
                        continue

                # Dedup by event id across the cycle BEFORE the floor (CAT-02 /
                # Pitfall 4 — avoids cross-category volume double-count inflating a
                # borderline event over the floor). This skip IS first-by-priority.
                deduped: list[GammaEvent] = []
                for event in parsed:
                    if event.id in seen_event_ids:
                        continue
                    seen_event_ids.add(event.id)
                    # Drift logging on unmapped tags (CAT-03 — logged, never auto-added).
                    resolve_category(event, settings.POLYMARKET_CATEGORIES)
                    deduped.append(event)

                # Volume floor AFTER dedup, then top-N (CAT-02).
                floored = [e for e in deduped if e.volume_24hr_decimal >= floor]
                curated = floored[:top_n]

                # CAT-06: never persist an empty category — sync_events is only
                # called with a non-empty curated list (empty-category suppression
                # is a Phase-16 read concern, not a write).
                if not curated:
                    log.info("poll_events.category_empty", category=entry.name)
                    continue

                # CR-02: reset per category so the post-commit publish below sees
                # ONLY this category's deltas. One adapter instance is reused across
                # all 7 categories; without this reset each category re-publishes
                # every prior category's accumulated deltas. (14-REVIEW CR-02)
                adapter.changed_markets = []
                synced = await adapter.sync_events(session, curated, category=entry.name)
                await session.commit()  # commit THIS category (CAT-05 keep-last-good)
                log.info(
                    "poll_events.category_synced",
                    category=entry.name,
                    event_count=len(curated),
                    market_count=synced,
                )

                # Real-time publish (POST-COMMIT, per-market, on-change only) —
                # mirrors _run_poll_sync. A Redis hiccup must never fail the poll.
                for market_id, deltas in adapter.changed_markets:
                    try:
                        await publish_odds_change_async(redis, market_id, deltas)
                    except Exception as pub_exc:
                        log.warning(
                            "realtime.publish_failed",
                            market_id=market_id,
                            error=str(pub_exc),
                        )
            except Exception as exc:
                # Keep-last-good per category (CAT-05 / T-14-12): one category's
                # Gamma 5xx / poisoned payload is logged + rolled back + skipped;
                # the other categories still sync and this category retains its
                # previously-committed rows (the sync never deletes).
                log.warning("poll_events.category_failed", category=entry.name, error=str(exc))
                sentry_sdk.capture_exception(exc)
                if session is not None:
                    with contextlib.suppress(Exception):
                        await session.rollback()
                continue
    finally:
        # Release the events lock + close client/redis exactly once (WR-04/WR-05).
        await release_events_lock(redis, lock_token)
        await client.close()
        if session is not None and session_override is None:
            with contextlib.suppress(Exception):
                await session.close()
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

    # Acquire a distinct lock — never reuse the poll lock (T-07-04). Use a unique
    # ownership token + compare-and-delete release (WR-05) so a slow task whose
    # lock expired can't delete a newer owner's lock.
    lock_ttl = settings.POLYMARKET_LOCK_TTL_SECONDS + 35
    detect_token = uuid.uuid4().hex
    acquired = await redis.set(DETECT_LOCK_KEY, detect_token, nx=True, ex=lock_ttl)
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

    except Exception as exc:
        log.error("detect_failed", error=str(exc))
        sentry_sdk.capture_exception(exc)
        if session is not None:
            with contextlib.suppress(Exception):
                await session.rollback()
    finally:
        # Close the session exactly once on every path (WR-04) — matches
        # _run_poll_sync / _run_snapshot_odds, which both close in a single
        # finally. The previous in-try + in-except closes were duplicated and
        # asymmetric; a reader could not prove a single close.
        if session is not None and session_override is None:
            with contextlib.suppress(Exception):
                await session.close()
        # Owner-checked release (WR-05) — only delete the lock if we still own it.
        # (See release_poll_lock for the eval stub-typing note.)
        await redis.eval(_RELEASE_LOCK_LUA, 1, DETECT_LOCK_KEY, detect_token)  # type: ignore[misc]
        if redis_override is None:
            await redis.aclose()


@celery_app.task(name="app.integrations.polymarket.tasks.poll_polymarket_top25")  # type: ignore[untyped-decorator]
def poll_polymarket_top25() -> None:
    """Celery task wrapping _run_poll_sync in asyncio.run.

    Kept importable + registered for back-compat (Phase 14 dropped it from the
    beat schedule in favour of poll_polymarket_events, but the task itself stays
    so a lingering redbeat key is a harmless no-op until beat restarts).
    """
    asyncio.run(_run_poll_sync())


@celery_app.task(name="app.integrations.polymarket.tasks.poll_polymarket_events")  # type: ignore[untyped-decorator]
def poll_polymarket_events() -> None:
    """Beat task: curated per-category Gamma /events sync every 300s (Phase 14)."""
    asyncio.run(_run_poll_events())


@celery_app.task(name="app.integrations.polymarket.tasks.snapshot_odds")  # type: ignore[untyped-decorator]
def snapshot_odds() -> None:
    """Celery task wrapping _run_snapshot_odds in asyncio.run."""
    asyncio.run(_run_snapshot_odds())


@celery_app.task(name="app.integrations.polymarket.tasks.detect_polymarket_resolutions")  # type: ignore[untyped-decorator]
def detect_polymarket_resolutions() -> None:
    """Beat task: check for UMA-resolved Polymarket markets every 60s (STL-01)."""
    asyncio.run(_run_detect_resolutions())
