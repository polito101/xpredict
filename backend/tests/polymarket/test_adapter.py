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


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
class TestSyncEventsIntegration:
    """sync_events grouping / EVT-07 / category / dedup / idempotency (CAT-04, EVT-07).

    Asserts against the live-captured fixtures:
      - events_multi_outcome.json: 1 Crypto event id=538337, 3 Bitcoin-ladder
        children (group_item_titles 64,000 / 66,000 / 68,000), distinct conditionIds.
      - events_single_market.json: 1 Politics/World event id=108634, len==1, lone
        market source_market_id=958443, groupItemTitle="" (EVT-07).
    """

    async def test_sync_events_groups_multi_outcome(
        self,
        async_session: AsyncSession,
        gamma_events_multi: list[dict],
    ) -> None:
        """Multi-outcome event → 1 market_groups row + 3 stamped children (SC#1/SC#3)."""
        from sqlalchemy import select

        from app.integrations.polymarket.schemas import GammaEvent
        from app.markets.models import Market, MarketGroup

        adapter = PolymarketAdapter()
        events = [GammaEvent.model_validate(e) for e in gamma_events_multi]

        n = await adapter.sync_events(async_session, events, category="Crypto")
        assert n == 3  # 3 deduped children upserted

        # Exactly one market_groups row, source_event_id=538337, category=Crypto.
        grp = (
            await async_session.execute(
                select(MarketGroup).where(MarketGroup.source_event_id == "538337"),
            )
        ).scalar_one()
        assert grp.category == "Crypto"

        # 3 children stamped with group_id + category + group_item_title.
        kids = (
            (
                await async_session.execute(
                    select(Market).where(Market.group_id == grp.id),
                )
            )
            .scalars()
            .all()
        )
        assert len(kids) == 3
        assert all(k.category == "Crypto" for k in kids)
        assert {k.group_item_title for k in kids} == {"64,000", "66,000", "68,000"}

    async def test_sync_events_single_market_no_group(
        self,
        async_session: AsyncSession,
        gamma_events_single: list[dict],
    ) -> None:
        """len==1 event → standalone market, NO group row, category populated (EVT-07/SC#4)."""
        from sqlalchemy import select

        from app.integrations.polymarket.schemas import GammaEvent
        from app.markets.models import Market, MarketGroup

        adapter = PolymarketAdapter()
        events = [GammaEvent.model_validate(e) for e in gamma_events_single]

        await adapter.sync_events(async_session, events, category="Politics")

        # NO market_groups row for a len==1 event (EVT-07).
        grp = (
            await async_session.execute(
                select(MarketGroup).where(MarketGroup.source_event_id == "108634"),
            )
        ).scalar_one_or_none()
        assert grp is None

        # The lone market is standalone (group_id IS NULL) with category populated.
        m = (
            await async_session.execute(
                select(Market).where(Market.source_market_id == "958443"),
            )
        ).scalar_one()
        assert m.group_id is None
        assert m.category == "Politics"

    async def test_sync_events_idempotent(
        self,
        async_session: AsyncSession,
        gamma_events_multi: list[dict],
    ) -> None:
        """Replaying the same event creates no second market_groups row (ON CONFLICT)."""
        from sqlalchemy import select

        from app.integrations.polymarket.schemas import GammaEvent
        from app.markets.models import MarketGroup

        adapter = PolymarketAdapter()
        events = [GammaEvent.model_validate(e) for e in gamma_events_multi]

        await adapter.sync_events(async_session, events, category="Crypto")
        await adapter.sync_events(async_session, events, category="Crypto")  # replay

        grps = (
            (
                await async_session.execute(
                    select(MarketGroup).where(MarketGroup.source_event_id == "538337"),
                )
            )
            .scalars()
            .all()
        )
        assert len(grps) == 1  # no duplicate group
