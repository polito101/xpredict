from __future__ import annotations

import pytest

from app.integrations.market_source import (
    HouseAdapter,
    MarketSource,
    get_adapter,
)
from app.markets.enums import MarketSourceEnum

pytestmark = [pytest.mark.integration]

_async = pytest.mark.asyncio(loop_scope="session")


class TestProtocolConformance:
    def test_house_adapter_isinstance(self):
        adapter = HouseAdapter()
        assert isinstance(adapter, MarketSource)

    def test_registry_lookup(self):
        adapter = get_adapter(MarketSourceEnum.HOUSE)
        assert isinstance(adapter, HouseAdapter)
        assert isinstance(adapter, MarketSource)


@_async
class TestHouseAdapter:
    async def test_detect_resolution_returns_none(self, async_session, sample_market):
        adapter = HouseAdapter()
        result = await adapter.detect_resolution(async_session, sample_market.id)
        assert result is None

    async def test_fetch_active_markets(self, async_session, sample_market):
        adapter = HouseAdapter()
        markets = await adapter.fetch_active_markets(async_session)
        assert len(markets) >= 1
        found = any(m.id == sample_market.id for m in markets)
        assert found

    async def test_fetch_market(self, async_session, sample_market):
        adapter = HouseAdapter()
        market = await adapter.fetch_market(async_session, sample_market.id)
        assert market is not None
        assert market.id == sample_market.id
        assert len(market.outcomes) == 2

    async def test_fetch_market_not_found(self, async_session):
        from uuid import uuid4

        adapter = HouseAdapter()
        market = await adapter.fetch_market(async_session, uuid4())
        assert market is None
