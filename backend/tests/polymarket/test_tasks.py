"""Tests for Polymarket Celery tasks — poll lock, upsert, snapshot, beat schedule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.polymarket.tasks import (
    LOCK_KEY,
    _run_poll_sync,
    _run_snapshot_odds,
    acquire_poll_lock,
    release_poll_lock,
)
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Unit tests — mock Redis, no DB
# ---------------------------------------------------------------------------
pytestmark_unit = [pytest.mark.unit]


@pytest.mark.unit
async def test_acquire_poll_lock_calls_setnx() -> None:
    """acquire_poll_lock uses SETNX with TTL."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    result = await acquire_poll_lock(redis)

    assert result is True
    redis.set.assert_called_once()
    call_kwargs = redis.set.call_args
    assert call_kwargs.kwargs.get("nx") is True or call_kwargs[1].get("nx") is True


@pytest.mark.unit
async def test_release_poll_lock_deletes_key() -> None:
    """release_poll_lock calls redis.delete with the lock key."""
    redis = AsyncMock()
    redis.delete = AsyncMock()

    await release_poll_lock(redis)

    redis.delete.assert_called_once_with(LOCK_KEY)


@pytest.mark.unit
async def test_poll_skipped_when_lock_held() -> None:
    """When lock is held, GammaClient.fetch_top_markets is NOT called."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=False)  # lock NOT acquired

    with patch(
        "app.integrations.polymarket.tasks.GammaClient",
    ) as mock_client_cls:
        await _run_poll_sync(redis_override=redis)
        mock_client_cls.assert_not_called()


@pytest.mark.unit
async def test_poll_acquires_and_releases_lock() -> None:
    """Poll acquires lock before sync and releases after."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()
    redis.aclose = AsyncMock()

    mock_client = AsyncMock()
    mock_client.fetch_top_markets = AsyncMock(return_value=[])
    mock_client.close = AsyncMock()

    with (
        patch(
            "app.integrations.polymarket.tasks.GammaClient",
            return_value=mock_client,
        ),
        patch(
            "app.integrations.polymarket.tasks.PolymarketAdapter",
        ) as mock_adapter_cls,
    ):
        mock_adapter = AsyncMock()
        mock_adapter.sync_top25 = AsyncMock(return_value=0)
        mock_adapter_cls.return_value = mock_adapter

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        await _run_poll_sync(
            redis_override=redis,
            session_override=mock_session,
        )

    # Lock was acquired (set with nx=True)
    redis.set.assert_called_once()
    # Lock was released
    redis.delete.assert_called_once_with(LOCK_KEY)


@pytest.mark.unit
def test_beat_schedule_entries() -> None:
    """Beat schedule contains poll and snapshot tasks with correct intervals."""
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule

    assert "poll-polymarket-top25" in schedule
    assert schedule["poll-polymarket-top25"]["schedule"] == 30.0
    assert (
        schedule["poll-polymarket-top25"]["task"]
        == "app.integrations.polymarket.tasks.poll_polymarket_top25"
    )

    assert "snapshot-odds" in schedule
    assert schedule["snapshot-odds"]["schedule"] == 300.0
    assert schedule["snapshot-odds"]["task"] == "app.integrations.polymarket.tasks.snapshot_odds"


# ---------------------------------------------------------------------------
# Integration tests — testcontainers Postgres
# ---------------------------------------------------------------------------

_integration_marks = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_poll_upserts_markets(async_session: AsyncSession) -> None:
    """Polling with mocked GammaClient creates markets in DB via adapter."""
    from sqlalchemy import delete, select

    sample_markets = [
        {
            "id": "test-poll-001",
            "question": "Will poll test market 1 resolve?",
            "slug": "poll-test-1",
            "conditionId": "cond-001",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.65","0.35"]',
            "clobTokenIds": '["tok1","tok2"]',
            "volume": "1000000",
            "liquidity": "500000",
            "volume24hr": 50000.0,
            "closed": False,
            "endDate": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            "description": "Test poll market 1",
        },
        {
            "id": "test-poll-002",
            "question": "Will poll test market 2 resolve?",
            "slug": "poll-test-2",
            "conditionId": "cond-002",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.40","0.60"]',
            "clobTokenIds": '["tok3","tok4"]',
            "volume": "2000000",
            "liquidity": "800000",
            "volume24hr": 80000.0,
            "closed": False,
            "endDate": (datetime.now(UTC) + timedelta(days=15)).isoformat(),
            "description": "Test poll market 2",
        },
    ]

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()

    mock_client = AsyncMock()
    mock_client.fetch_top_markets = AsyncMock(return_value=sample_markets)
    mock_client.close = AsyncMock()

    with patch(
        "app.integrations.polymarket.tasks.GammaClient",
        return_value=mock_client,
    ):
        await _run_poll_sync(
            redis_override=redis,
            session_override=async_session,
        )

    # Verify markets were upserted
    result = await async_session.execute(
        select(Market).where(
            Market.source == MarketSourceEnum.POLYMARKET.value,
            Market.source_market_id.in_(["test-poll-001", "test-poll-002"]),
        ),
    )
    markets = list(result.scalars().all())
    assert len(markets) == 2

    # Clean up
    for m in markets:
        await async_session.execute(
            delete(Outcome).where(Outcome.market_id == m.id),
        )
        await async_session.execute(
            delete(Market).where(Market.id == m.id),
        )
    await async_session.flush()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_snapshot_odds_writes_rows(async_session: AsyncSession) -> None:
    """Snapshot task writes OddsSnapshot rows for open markets."""
    from sqlalchemy import delete, select

    # Create a market with 2 outcomes
    market = Market(
        question="Snapshot test market?",
        slug=generate_slug("Snapshot test market?"),
        resolution_criteria="Test criteria",
        source=MarketSourceEnum.HOUSE.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    async_session.add(market)
    await async_session.flush()

    yes = Outcome(
        market_id=market.id,
        label="YES",
        initial_odds=Decimal("0.600000"),
        current_odds=Decimal("0.600000"),
    )
    no = Outcome(
        market_id=market.id,
        label="NO",
        initial_odds=Decimal("0.400000"),
        current_odds=Decimal("0.400000"),
    )
    async_session.add_all([yes, no])
    await async_session.flush()

    # Run snapshot
    await _run_snapshot_odds(session_override=async_session)

    # Verify snapshots were created
    result = await async_session.execute(
        select(OddsSnapshot).where(OddsSnapshot.market_id == market.id),
    )
    snapshots = list(result.scalars().all())
    assert len(snapshots) == 2

    # Verify probabilities match current_odds
    snap_probs = sorted([s.probability for s in snapshots])
    assert snap_probs == sorted([Decimal("0.400000"), Decimal("0.600000")])

    # Clean up
    await async_session.execute(
        delete(OddsSnapshot).where(OddsSnapshot.market_id == market.id),
    )
    await async_session.execute(
        delete(Outcome).where(Outcome.market_id == market.id),
    )
    await async_session.execute(
        delete(Market).where(Market.id == market.id),
    )
    await async_session.flush()
