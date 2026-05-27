from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.markets.enums import MarketStatus
from app.markets.schemas import MarketCreate, MarketUpdate
from app.markets.service import MarketService

pytestmark = [pytest.mark.integration]

_async = pytest.mark.asyncio(loop_scope="session")


class TestMarketCreateSchema:
    def test_rejects_past_deadline(self):
        with pytest.raises(ValueError, match="future"):
            MarketCreate(
                question="test",
                resolution_criteria="test",
                deadline=datetime.now(UTC) - timedelta(hours=1),
            )

    def test_rejects_odds_below_zero(self):
        with pytest.raises(ValueError):
            MarketCreate(
                question="test",
                resolution_criteria="test",
                deadline=datetime.now(UTC) + timedelta(days=1),
                initial_odds_yes=Decimal("-0.1"),
            )

    def test_rejects_odds_above_one(self):
        with pytest.raises(ValueError):
            MarketCreate(
                question="test",
                resolution_criteria="test",
                deadline=datetime.now(UTC) + timedelta(days=1),
                initial_odds_yes=Decimal("1.1"),
            )

    def test_accepts_valid_create(self):
        body = MarketCreate(
            question="Will it rain?",
            resolution_criteria="Rain at station X",
            deadline=datetime.now(UTC) + timedelta(days=1),
            initial_odds_yes=Decimal("0.7"),
            category="weather",
        )
        assert body.initial_odds_yes == Decimal("0.7")


class TestMarketReadSerialization:
    def test_outcome_read_serializes_decimal_as_string(self):
        from app.markets.schemas import OutcomeRead

        data = OutcomeRead(
            id="00000000-0000-0000-0000-000000000001",
            label="YES",
            initial_odds=Decimal("0.500000"),
            current_odds=Decimal("0.650000"),
        )
        d = data.model_dump(mode="json")
        assert isinstance(d["initial_odds"], str)
        assert isinstance(d["current_odds"], str)


@_async
class TestMarketServiceCreate:
    async def test_create_market(self, async_session, admin_user):
        body = MarketCreate(
            question="Will BTC hit 100k?",
            resolution_criteria="CoinGecko price > 100000 by deadline",
            deadline=datetime.now(UTC) + timedelta(days=7),
            initial_odds_yes=Decimal("0.6"),
            category="crypto",
        )
        market = await MarketService.create_market(async_session, admin_user, body)
        assert market.question == "Will BTC hit 100k?"
        assert market.slug.startswith("will-btc-hit-100k")
        assert market.status == "OPEN"
        assert market.source == "HOUSE"


@_async
class TestMarketServiceUpdate:
    async def test_update_allows_all_fields_no_bets(self, async_session, admin_user, sample_market):
        body = MarketUpdate(
            resolution_criteria="Updated criteria",
            deadline=datetime.now(UTC) + timedelta(days=30),
        )
        updated = await MarketService.update_market(
            async_session, sample_market, body, admin_user,
        )
        assert updated.resolution_criteria == "Updated criteria"

    async def test_update_locks_criteria_with_bets(
        self, async_session, admin_user, market_with_bets,
    ):
        body = MarketUpdate(resolution_criteria="Try to change")
        with pytest.raises(HTTPException) as exc_info:
            await MarketService.update_market(
                async_session, market_with_bets, body, admin_user,
            )
        assert exc_info.value.status_code == 423

    async def test_update_allows_odds_with_bets(self, async_session, admin_user, market_with_bets):
        body = MarketUpdate(odds_yes=Decimal("0.7"))
        updated = await MarketService.update_market(
            async_session, market_with_bets, body, admin_user,
        )
        assert updated is not None


@_async
class TestMarketServiceClose:
    async def test_close_market(self, async_session, admin_user, sample_market):
        closed = await MarketService.close_market(async_session, sample_market, admin_user)
        assert closed.status == "CLOSED"
        assert closed.closed_at is not None

    async def test_close_non_open_raises_409(self, async_session, admin_user, sample_market):
        sample_market.status = MarketStatus.CLOSED.value
        await async_session.flush()
        with pytest.raises(HTTPException) as exc_info:
            await MarketService.close_market(async_session, sample_market, admin_user)
        assert exc_info.value.status_code == 409


@_async
class TestMarketServiceList:
    async def test_list_markets_with_pagination(self, async_session, sample_market):
        items, total = await MarketService.list_markets(async_session, page=1, page_size=10)
        assert total >= 1
        assert any(m.id == sample_market.id for m in items)

    async def test_list_markets_filter_by_source(self, async_session, sample_market):
        items, total = await MarketService.list_markets(
            async_session, source="HOUSE",
        )
        assert total >= 1

    async def test_list_markets_filter_by_status(self, async_session, sample_market):
        items, total = await MarketService.list_markets(
            async_session, status="OPEN",
        )
        assert all(m.status == "OPEN" for m in items)


@_async
class TestMarketServiceGet:
    async def test_get_by_slug(self, async_session, sample_market):
        market = await MarketService.get_market_by_slug(async_session, sample_market.slug)
        assert market is not None
        assert market.id == sample_market.id

    async def test_get_by_slug_not_found(self, async_session):
        market = await MarketService.get_market_by_slug(async_session, "nonexistent-slug")
        assert market is None
