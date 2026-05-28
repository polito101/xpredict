"""Tests for PolymarketAdapter — Protocol conformance, registry, and upsert.

Unit tests verify Protocol isinstance and REGISTRY lookup. Integration
tests (requiring testcontainers Postgres) verify upsert idempotency
and fetch_active_markets correctness.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from app.integrations.market_source import MarketSource, get_adapter
from app.integrations.polymarket import PolymarketAdapter
from app.markets.enums import MarketSourceEnum

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------

pytestmark_unit = pytest.mark.unit


class TestProtocolConformance:
    """Protocol and registry checks — no external deps."""

    pytestmark: ClassVar = [pytest.mark.unit]

    def test_protocol_conformance(self) -> None:
        """PolymarketAdapter passes MarketSource Protocol isinstance check."""
        adapter = PolymarketAdapter()
        assert isinstance(adapter, MarketSource)

    def test_registry_lookup(self) -> None:
        """get_adapter returns PolymarketAdapter for POLYMARKET key."""
        adapter = get_adapter(MarketSourceEnum.POLYMARKET)
        assert isinstance(adapter, PolymarketAdapter)
        assert isinstance(adapter, MarketSource)

    @pytest.mark.asyncio
    async def test_detect_resolution_returns_none_for_closed_proposed(self) -> None:
        """detect_resolution returns None when Gamma reports closed=true, proposed (SC#3)."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import uuid4

        from app.markets.enums import MarketSourceEnum

        market_id = uuid4()
        fake_market = MagicMock()
        fake_market.source_market_id = "gamma-123"
        fake_market.source = MarketSourceEnum.POLYMARKET.value
        fake_market.outcomes = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_market

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        closed_proposed_raw = {
            "id": "gamma-123",
            "question": "Will it happen?",
            "closed": True,
            "umaResolutionStatus": "proposed",
            "outcomePrices": '["0.5","0.5"]',
            "outcomes": '["Yes","No"]',
        }

        adapter = PolymarketAdapter()
        with (
            patch(
                "app.integrations.polymarket.adapter.GammaClient.fetch_market_by_id",
                new=AsyncMock(return_value=closed_proposed_raw),
            ),
            patch(
                "app.integrations.polymarket.adapter.GammaClient.close",
                new=AsyncMock(),
            ),
        ):
            result = await adapter.detect_resolution(session, market_id)

        assert result is None


# ---------------------------------------------------------------------------
# Integration tests — require testcontainers Postgres
# ---------------------------------------------------------------------------

_SAMPLE_RAW_MARKETS = [
    {
        "id": "integration-test-1",
        "question": "Will it snow in July?",
        "conditionId": "0xcondition1",
        "slug": "snow-july",
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.15", "0.85"],
        "volume": "500000.00",
        "volume24hr": 25000.0,
        "liquidity": "100000.00",
        "closed": False,
        "endDate": "2026-07-31T00:00:00Z",
        "description": "Will it snow?",
        "clobTokenIds": ["1001", "1002"],
    },
    {
        "id": "integration-test-2",
        "question": "Will the sun explode tomorrow?",
        "conditionId": "0xcondition2",
        "slug": "sun-explode",
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.001", "0.999"],
        "volume": "1000000.00",
        "volume24hr": 50000.0,
        "liquidity": "200000.00",
        "closed": False,
        "endDate": "2026-06-01T00:00:00Z",
        "description": "Sun explosion prediction",
        "clobTokenIds": ["2001", "2002"],
    },
]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
class TestAdapterIntegration:
    """Integration tests requiring testcontainers Postgres."""

    async def test_upsert_idempotent(self, async_session: AsyncSession) -> None:
        """Double sync with same data = zero duplicates."""
        from sqlalchemy import func, select

        from app.markets.models import Market

        adapter = PolymarketAdapter()

        # First sync
        count1 = await adapter.sync_top25(async_session, _SAMPLE_RAW_MARKETS)
        assert count1 == 2

        # Second sync — same data, should upsert (not duplicate).
        count2 = await adapter.sync_top25(async_session, _SAMPLE_RAW_MARKETS)
        assert count2 == 2

        # Total POLYMARKET markets in DB should be exactly 2.
        total = await async_session.execute(
            select(func.count()).select_from(
                select(Market)
                .where(Market.source == MarketSourceEnum.POLYMARKET.value)
                .where(
                    Market.source_market_id.in_(
                        ["integration-test-1", "integration-test-2"],
                    ),
                )
                .subquery(),
            ),
        )
        assert total.scalar_one() == 2

    async def test_fetch_active_markets(self, async_session: AsyncSession) -> None:
        """After sync, fetch_active_markets returns synced markets."""
        adapter = PolymarketAdapter()

        # Ensure data is synced.
        await adapter.sync_top25(async_session, _SAMPLE_RAW_MARKETS)

        markets = await adapter.fetch_active_markets(async_session)
        # At least our 2 test markets should be present.
        source_ids = {m.source_market_id for m in markets}
        assert "integration-test-1" in source_ids
        assert "integration-test-2" in source_ids
