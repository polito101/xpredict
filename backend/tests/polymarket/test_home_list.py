"""Tests for the home page market list — house-first sorting (D-01)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import delete

from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug
from app.markets.service import MarketService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def _create_market(
    session: AsyncSession,
    *,
    source: str = MarketSourceEnum.HOUSE.value,
    status: str = MarketStatus.OPEN.value,
    question: str = "Test market?",
    volume_24hr: Decimal = Decimal("0"),
    source_market_id: str | None = None,
    polymarket_slug: str | None = None,
) -> Market:
    """Helper to insert a market with 2 outcomes."""
    market = Market(
        question=question,
        slug=generate_slug(question),
        resolution_criteria="Test criteria",
        source=source,
        status=status,
        deadline=datetime.now(UTC) + timedelta(days=1),
        volume_24hr=volume_24hr,
        source_market_id=source_market_id,
        polymarket_slug=polymarket_slug,
    )
    session.add(market)
    await session.flush()

    yes = Outcome(
        market_id=market.id,
        label="YES",
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    no = Outcome(
        market_id=market.id,
        label="NO",
        initial_odds=Decimal("0.500000"),
        current_odds=Decimal("0.500000"),
    )
    session.add_all([yes, no])
    await session.flush()
    return market


async def _cleanup_market(session: AsyncSession, market_id: object) -> None:
    """Remove market and related rows."""
    await session.execute(
        delete(OddsSnapshot).where(OddsSnapshot.market_id == market_id),
    )
    await session.execute(
        delete(Outcome).where(Outcome.market_id == market_id),
    )
    await session.execute(
        delete(Market).where(Market.id == market_id),
    )
    await session.flush()


async def test_house_first_ordering(async_session: AsyncSession) -> None:
    """House markets appear before Polymarket markets (D-01)."""
    pm = await _create_market(
        async_session,
        source=MarketSourceEnum.POLYMARKET.value,
        question="PM ordering test?",
        volume_24hr=Decimal("100000"),
        source_market_id="pm-order-001",
    )
    house = await _create_market(
        async_session,
        source=MarketSourceEnum.HOUSE.value,
        question="House ordering test?",
    )

    try:
        markets = await MarketService.list_home_markets(async_session)

        # Find positions
        house_idx = next(i for i, m in enumerate(markets) if m.id == house.id)
        pm_idx = next(i for i, m in enumerate(markets) if m.id == pm.id)
        assert house_idx < pm_idx, "House market must appear before Polymarket market"
    finally:
        await _cleanup_market(async_session, house.id)
        await _cleanup_market(async_session, pm.id)


async def test_polymarket_sorted_by_volume(async_session: AsyncSession) -> None:
    """Polymarket markets are sorted by volume_24hr descending."""
    pm_low = await _create_market(
        async_session,
        source=MarketSourceEnum.POLYMARKET.value,
        question="PM low volume?",
        volume_24hr=Decimal("10000"),
        source_market_id="pm-vol-low",
    )
    pm_high = await _create_market(
        async_session,
        source=MarketSourceEnum.POLYMARKET.value,
        question="PM high volume?",
        volume_24hr=Decimal("500000"),
        source_market_id="pm-vol-high",
    )

    try:
        markets = await MarketService.list_home_markets(async_session)

        pm_markets = [
            m
            for m in markets
            if m.source == MarketSourceEnum.POLYMARKET.value and m.id in (pm_low.id, pm_high.id)
        ]
        assert len(pm_markets) >= 2
        # Higher volume should be first
        high_idx = next(i for i, m in enumerate(pm_markets) if m.id == pm_high.id)
        low_idx = next(i for i, m in enumerate(pm_markets) if m.id == pm_low.id)
        assert high_idx < low_idx, "Higher volume PM market must appear first"
    finally:
        await _cleanup_market(async_session, pm_low.id)
        await _cleanup_market(async_session, pm_high.id)


async def test_only_open_markets_shown(async_session: AsyncSession) -> None:
    """Only OPEN markets appear in the home list."""
    open_market = await _create_market(
        async_session,
        question="Open market for filter test?",
    )
    closed_market = await _create_market(
        async_session,
        question="Closed market for filter test?",
        status=MarketStatus.CLOSED.value,
    )

    try:
        markets = await MarketService.list_home_markets(async_session)
        market_ids = {m.id for m in markets}

        assert open_market.id in market_ids
        assert closed_market.id not in market_ids
    finally:
        await _cleanup_market(async_session, open_market.id)
        await _cleanup_market(async_session, closed_market.id)


async def test_public_endpoint_returns_mixed_list(engine: AsyncEngine) -> None:
    """GET /api/v1/markets returns flat list with house first, volume and source_url."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS

    # Seed markets directly via engine to avoid session fixture scope issues.
    async with engine.connect() as conn, AS(conn, expire_on_commit=False) as session:
        house = await _create_market(
            session,
            source=MarketSourceEnum.HOUSE.value,
            question="Endpoint test house market?",
        )
        pm = await _create_market(
            session,
            source=MarketSourceEnum.POLYMARKET.value,
            question="Endpoint test PM market?",
            volume_24hr=Decimal("75000"),
            source_market_id="pm-endpoint-test-001",
            polymarket_slug="endpoint-test-pm-market",
        )
        await session.commit()

    try:
        from app.main import app

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/markets")

        assert resp.status_code == 200
        body = resp.json()

        # Response is a flat list (not paginated)
        assert isinstance(body, list)

        # Find our test markets
        house_item = next(
            (item for item in body if item["id"] == str(house.id)),
            None,
        )
        pm_item = next(
            (item for item in body if item["id"] == str(pm.id)),
            None,
        )

        assert house_item is not None, "House market must be in response"
        assert pm_item is not None, "Polymarket market must be in response"

        # House before Polymarket
        house_idx = body.index(house_item)
        pm_idx = body.index(pm_item)
        assert house_idx < pm_idx, "House market must appear before PM in response"

        # Volume fields present
        assert "volume" in pm_item
        assert "volume_24hr" in pm_item

        # source_url for Polymarket market
        assert pm_item["source_url"] is not None
        assert pm_item["source_url"].startswith("https://polymarket.com/event/")
        assert "endpoint-test-pm-market" in pm_item["source_url"]

        # source_url for house market is null
        assert house_item["source_url"] is None
    finally:
        # Clean up via engine
        async with engine.connect() as conn, AS(conn, expire_on_commit=False) as session:
            await _cleanup_market(session, house.id)
            await _cleanup_market(session, pm.id)
            await session.commit()
