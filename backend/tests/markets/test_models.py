from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug

pytestmark = [pytest.mark.integration]

_async = pytest.mark.asyncio(loop_scope="session")


class TestMarketStatus:
    def test_has_five_values(self):
        assert len(MarketStatus) == 5

    def test_values(self):
        assert set(MarketStatus) == {
            MarketStatus.DRAFT,
            MarketStatus.OPEN,
            MarketStatus.CLOSED,
            MarketStatus.RESOLVED,
            MarketStatus.CANCELLED,
        }


class TestMarketSourceEnum:
    def test_has_two_values(self):
        assert len(MarketSourceEnum) == 2

    def test_values(self):
        assert set(MarketSourceEnum) == {
            MarketSourceEnum.HOUSE,
            MarketSourceEnum.POLYMARKET,
        }


class TestMarketColumns:
    def test_market_has_expected_columns(self):
        columns = {c.name for c in Market.__table__.columns}
        expected = {
            "id",
            "question",
            "slug",
            "resolution_criteria",
            "category",
            "source",
            "source_market_id",
            "condition_id",
            "status",
            "deadline",
            "bet_count",
            "created_at",
            "updated_at",
            "closed_at",
            "resolved_at",
            "tenant_id",
        }
        assert expected.issubset(columns)

    def test_outcome_has_expected_columns(self):
        columns = {c.name for c in Outcome.__table__.columns}
        expected = {
            "id",
            "market_id",
            "label",
            "initial_odds",
            "current_odds",
            "tenant_id",
        }
        assert expected.issubset(columns)

    def test_odds_snapshot_has_expected_columns(self):
        columns = {c.name for c in OddsSnapshot.__table__.columns}
        expected = {
            "id",
            "market_id",
            "outcome_id",
            "probability",
            "snapshot_at",
            "tenant_id",
        }
        assert expected.issubset(columns)


class TestGenerateSlug:
    def test_slug_from_question(self):
        slug = generate_slug("Will Bitcoin hit 100k?")
        assert slug.startswith("will-bitcoin-hit-100k")
        assert len(slug.split("-")[-1]) == 6

    def test_slug_uniqueness(self):
        s1 = generate_slug("Same question")
        s2 = generate_slug("Same question")
        assert s1 != s2


@_async
class TestMarketCreation:
    async def test_create_market_with_outcomes(self, async_session, sample_market):
        stmt = (
            select(Market)
            .where(Market.id == sample_market.id)
            .options(selectinload(Market.outcomes))
        )
        result = await async_session.execute(stmt)
        market = result.scalar_one()
        assert market.question == "Will it rain tomorrow?"
        assert len(market.outcomes) == 2
        labels = {o.label for o in market.outcomes}
        assert labels == {"YES", "NO"}

    async def test_tenant_id_default(self, async_session, sample_market):
        assert sample_market.tenant_id == UUID("00000000-0000-0000-0000-000000000001")

    async def test_outcome_tenant_id(self, async_session, sample_market):
        stmt = select(Outcome).where(Outcome.market_id == sample_market.id)
        result = await async_session.execute(stmt)
        for outcome in result.scalars():
            assert outcome.tenant_id == UUID("00000000-0000-0000-0000-000000000001")

    async def test_odds_snapshot_tenant_id(self, async_session, sample_market):
        stmt = select(OddsSnapshot).where(OddsSnapshot.market_id == sample_market.id)
        result = await async_session.execute(stmt)
        for snap in result.scalars():
            assert snap.tenant_id == UUID("00000000-0000-0000-0000-000000000001")


@_async
class TestCheckConstraints:
    async def test_invalid_status_rejected(self, async_session):
        nested = await async_session.begin_nested()
        market = Market(
            question="Bad status",
            slug=generate_slug("Bad status"),
            resolution_criteria="N/A",
            source=MarketSourceEnum.HOUSE.value,
            status="INVALID",
            deadline=datetime.now(UTC) + timedelta(days=1),
        )
        async_session.add(market)
        with pytest.raises(IntegrityError):
            await async_session.flush()
        await nested.rollback()

    async def test_invalid_source_rejected(self, async_session):
        nested = await async_session.begin_nested()
        market = Market(
            question="Bad source",
            slug=generate_slug("Bad source"),
            resolution_criteria="N/A",
            source="BINANCE",
            status=MarketStatus.OPEN.value,
            deadline=datetime.now(UTC) + timedelta(days=1),
        )
        async_session.add(market)
        with pytest.raises(IntegrityError):
            await async_session.flush()
        await nested.rollback()


@_async
class TestBinaryOnlyTrigger:
    async def test_third_outcome_rejected(self, async_session, sample_market):
        nested = await async_session.begin_nested()
        third = Outcome(
            market_id=sample_market.id,
            label="MAYBE",
            initial_odds=Decimal("0.333333"),
            current_odds=Decimal("0.333333"),
        )
        async_session.add(third)
        with pytest.raises(IntegrityError, match="MKT-08"):
            await async_session.flush()
        await nested.rollback()


@_async
class TestBetCountLock:
    async def test_bet_count_increments(self, async_session, market_with_bets):
        assert market_with_bets.bet_count == 1


@_async
class TestLazyRaise:
    async def test_outcomes_lazy_raise(self, async_session, sample_market):
        stmt = select(Market).where(Market.id == sample_market.id)
        result = await async_session.execute(stmt)
        market = result.scalar_one()
        with pytest.raises(
            sqlalchemy.exc.InvalidRequestError,
            match="lazy='raise'",
        ):
            _ = market.outcomes
