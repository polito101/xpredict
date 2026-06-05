from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
import sqlalchemy.exc
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import (
    Market,
    MarketGroup,
    OddsSnapshot,
    Outcome,
    generate_slug,
)

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
            # Phase 13 (EVT-01) multi-outcome seam — additive columns.
            "group_id",
            "group_item_title",
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


# ---------------------------------------------------------------------------
# Phase 13 (EVT-01) — MarketGroup event-of-binaries seam
# ---------------------------------------------------------------------------


def _child_market(title: str, group_id) -> Market:
    """Build a fully-valid binary child Market for a MarketGroup.

    Mirrors the required kwargs from the ``sample_market`` fixture
    (tests/markets/conftest.py) — ``question``, unique ``slug``,
    ``resolution_criteria``, ``source``, ``status``, ``deadline`` — plus the
    Phase 13 ``group_id`` + ``group_item_title``.
    """
    return Market(
        question=f"Will {title} win?",
        slug=generate_slug(title),
        resolution_criteria="Official result certified by 23:59 UTC",
        category="politics",
        source=MarketSourceEnum.HOUSE.value,
        status=MarketStatus.OPEN.value,
        deadline=datetime.now(UTC) + timedelta(days=1),
        group_id=group_id,
        group_item_title=title,
    )


@_async
class TestMarketGroup:
    """SC#4 — a MarketGroup round-trips a parent with >=2 children via selectinload."""

    async def test_group_round_trips_two_children(self, async_session):
        grp = MarketGroup(
            title="2028 Presidential Election",
            source=MarketSourceEnum.HOUSE.value,
            slug=generate_slug("2028 Presidential Election"),
            category="politics",
        )
        async_session.add(grp)
        await async_session.flush()

        async_session.add_all(
            [
                _child_market("Candidate A", grp.id),
                _child_market("Candidate B", grp.id),
            ]
        )
        await async_session.flush()

        stmt = (
            select(MarketGroup)
            .where(MarketGroup.id == grp.id)
            .options(selectinload(MarketGroup.markets))
        )
        loaded = (await async_session.execute(stmt)).scalar_one()

        assert len(loaded.markets) == 2
        assert {m.group_item_title for m in loaded.markets} == {
            "Candidate A",
            "Candidate B",
        }
        # Every child points back to the parent group (the FK seam).
        assert {m.group_id for m in loaded.markets} == {grp.id}

    async def test_group_tenant_id_default(self, async_session):
        grp = MarketGroup(
            title="Default-tenant group",
            source=MarketSourceEnum.HOUSE.value,
            slug=generate_slug("Default-tenant group"),
        )
        async_session.add(grp)
        await async_session.flush()
        assert grp.tenant_id == UUID("00000000-0000-0000-0000-000000000001")

    async def test_deleting_group_orphans_children_not_cascade(self, async_session):
        """T-13-01 (financial safety): DELETE FROM market_groups must ORPHAN children.

        The single most financially important invariant of this phase: deleting a
        group must NULL ``markets.group_id`` (orphan the child back to standalone),
        NEVER cascade-delete a market that carries bets/odds/ledger state. The
        catalog-metadata check (``test_markets_group_id_fk_set_null``) proves the DDL
        SAYS ``ON DELETE SET NULL``; THIS test exercises the actual DELETE so a
        future ORM ``cascade=`` regression, a trigger, or a second conflicting
        constraint that deleted the child anyway would be caught.

        Savepoint-scoped (``begin_nested``) to match the module's isolation
        discipline — the savepoint is released on success, and the ``async_session``
        outer transaction is rolled back on teardown regardless.
        """
        nested = await async_session.begin_nested()
        try:
            grp = MarketGroup(
                title="Orphan test",
                source=MarketSourceEnum.HOUSE.value,
                slug=generate_slug("orphan-test"),
            )
            async_session.add(grp)
            await async_session.flush()

            child = _child_market("Orphan child", grp.id)
            async_session.add(child)
            await async_session.flush()
            child_id = child.id

            await async_session.execute(delete(MarketGroup).where(MarketGroup.id == grp.id))
            await async_session.flush()
            # Drop the cached child so the assertions read DB-resident state.
            async_session.expire(child)

            reloaded = (
                await async_session.execute(select(Market).where(Market.id == child_id))
            ).scalar_one_or_none()
            assert reloaded is not None, "child market was cascade-deleted — T-13-01 violated"
            assert (
                reloaded.group_id is None
            ), "group_id was not nulled on group delete (ON DELETE SET NULL)"
        finally:
            await nested.rollback()


@_async
class TestMarketGroupLazyRaise:
    """SC#4 — Market.group is lazy='raise': access without eager-load must raise."""

    async def test_group_relationship_lazy_raise(self, async_session):
        grp = MarketGroup(
            title="Lazy-raise group",
            source=MarketSourceEnum.HOUSE.value,
            slug=generate_slug("Lazy-raise group"),
        )
        async_session.add(grp)
        await async_session.flush()

        child = _child_market("Lazy child", grp.id)
        async_session.add(child)
        await async_session.flush()

        # Re-load the child WITHOUT eager-loading .group; accessing the unloaded
        # relationship must raise (lazy="raise"), never silently emit lazy I/O.
        stmt = select(Market).where(Market.id == child.id)
        market = (await async_session.execute(stmt)).scalar_one()
        with pytest.raises(
            sqlalchemy.exc.InvalidRequestError,
            match="lazy='raise'",
        ):
            _ = market.group


@_async
class TestStandaloneMarketRegression:
    """SC#2 — a standalone (group_id IS NULL) market is byte-for-byte unchanged.

    The two additive Phase 13 columns must NOT alter the existing binary
    read/round-trip path: the standalone ``sample_market`` has ``group_id IS NULL``
    and still loads its two YES/NO outcomes exactly as before.
    """

    async def test_standalone_market_group_id_is_null(self, async_session, sample_market):
        assert sample_market.group_id is None
        assert sample_market.group_item_title is None

    async def test_standalone_market_outcomes_unchanged(self, async_session, sample_market):
        stmt = (
            select(Market)
            .where(Market.id == sample_market.id)
            .options(selectinload(Market.outcomes))
        )
        market = (await async_session.execute(stmt)).scalar_one()
        assert market.group_id is None
        assert len(market.outcomes) == 2
        assert {o.label for o in market.outcomes} == {"YES", "NO"}
