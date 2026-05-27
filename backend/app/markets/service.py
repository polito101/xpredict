from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.core.audit.service import AuditService
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug
from app.markets.schemas import MarketCreate, MarketUpdate


class MarketService:
    @staticmethod
    async def create_market(
        session: AsyncSession,
        admin_user: User,
        body: MarketCreate,
        ip: str | None = None,
    ) -> Market:
        slug = generate_slug(body.question)
        market = Market(
            question=body.question,
            slug=slug,
            resolution_criteria=body.resolution_criteria,
            deadline=body.deadline,
            category=body.category,
            source=MarketSourceEnum.HOUSE.value,
            status=MarketStatus.OPEN.value,
        )
        session.add(market)
        await session.flush()

        odds_no = Decimal("1") - body.initial_odds_yes
        yes_outcome = Outcome(
            market_id=market.id,
            label="YES",
            initial_odds=body.initial_odds_yes,
            current_odds=body.initial_odds_yes,
        )
        no_outcome = Outcome(
            market_id=market.id,
            label="NO",
            initial_odds=odds_no,
            current_odds=odds_no,
        )
        session.add_all([yes_outcome, no_outcome])
        await session.flush()

        snap_yes = OddsSnapshot(
            market_id=market.id,
            outcome_id=yes_outcome.id,
            probability=body.initial_odds_yes,
        )
        snap_no = OddsSnapshot(
            market_id=market.id,
            outcome_id=no_outcome.id,
            probability=odds_no,
        )
        session.add_all([snap_yes, snap_no])

        await AuditService.record(
            session,
            actor=f"user:{admin_user.id}",
            event_type="market.created",
            payload={
                "market_id": str(market.id),
                "question": body.question,
                "source": "HOUSE",
            },
            ip=ip,
        )
        await session.flush()
        return market

    @staticmethod
    async def update_market(
        session: AsyncSession,
        market: Market,
        body: MarketUpdate,
        admin_user: User,
        ip: str | None = None,
    ) -> Market:
        if market.bet_count > 0 and body.resolution_criteria is not None:
            raise HTTPException(
                status_code=423,
                detail={
                    "code": "CRITERIA_LOCKED",
                    "reason": "Resolution criteria cannot be changed after bets have been placed",
                },
            )

        changed_fields: list[str] = []

        if body.resolution_criteria is not None:
            market.resolution_criteria = body.resolution_criteria
            changed_fields.append("resolution_criteria")
        if body.deadline is not None:
            market.deadline = body.deadline
            changed_fields.append("deadline")
        if body.category is not None:
            market.category = body.category
            changed_fields.append("category")
        if body.odds_yes is not None:
            odds_no = Decimal("1") - body.odds_yes
            stmt = select(Outcome).where(Outcome.market_id == market.id)
            result = await session.execute(stmt)
            for outcome in result.scalars():
                if outcome.label == "YES":
                    outcome.current_odds = body.odds_yes
                else:
                    outcome.current_odds = odds_no
                session.add(
                    OddsSnapshot(
                        market_id=market.id,
                        outcome_id=outcome.id,
                        probability=outcome.current_odds,
                    ),
                )
            changed_fields.append("odds")

        await AuditService.record(
            session,
            actor=f"user:{admin_user.id}",
            event_type="market.updated",
            payload={
                "market_id": str(market.id),
                "changed_fields": changed_fields,
            },
            ip=ip,
        )
        await session.flush()
        return market

    @staticmethod
    async def close_market(
        session: AsyncSession,
        market: Market,
        admin_user: User,
        ip: str | None = None,
    ) -> Market:
        if market.status != MarketStatus.OPEN.value:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVALID_STATUS",
                    "reason": f"Cannot close market with status {market.status}",
                },
            )
        market.status = MarketStatus.CLOSED.value
        market.closed_at = datetime.now(UTC)

        await AuditService.record(
            session,
            actor=f"user:{admin_user.id}",
            event_type="market.closed",
            payload={"market_id": str(market.id)},
            ip=ip,
        )
        await session.flush()
        return market

    @staticmethod
    async def list_markets(
        session: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        source: str | None = None,
        status: str | None = None,
        category: str | None = None,
    ) -> tuple[list[Market], int]:
        base = select(Market)
        if source:
            base = base.where(Market.source == source)
        if status:
            base = base.where(Market.status == status)
        if category:
            base = base.where(Market.category == category)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        items_stmt = (
            base.options(selectinload(Market.outcomes))
            .order_by(Market.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(items_stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_market_by_id(
        session: AsyncSession, market_id: UUID,
    ) -> Market | None:
        stmt = (
            select(Market)
            .where(Market.id == market_id)
            .options(
                selectinload(Market.outcomes),
                selectinload(Market.odds_snapshots),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_market_by_slug(
        session: AsyncSession, slug: str,
    ) -> Market | None:
        stmt = (
            select(Market)
            .where(Market.slug == slug)
            .options(
                selectinload(Market.outcomes),
                selectinload(Market.odds_snapshots),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
