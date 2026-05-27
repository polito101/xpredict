from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market


@dataclass
class ResolutionResult:
    winning_outcome_id: UUID
    source: str
    confidence: str


@runtime_checkable
class MarketSource(Protocol):
    async def fetch_active_markets(
        self, session: AsyncSession, *, limit: int = 25,
    ) -> list[Market]: ...

    async def fetch_market(
        self, session: AsyncSession, market_id: UUID,
    ) -> Market | None: ...

    async def detect_resolution(
        self, session: AsyncSession, market_id: UUID,
    ) -> ResolutionResult | None: ...


REGISTRY: dict[MarketSourceEnum, MarketSource] = {}


def register_source(source: MarketSourceEnum, adapter: MarketSource) -> None:
    REGISTRY[source] = adapter


def get_adapter(source: MarketSourceEnum) -> MarketSource:
    try:
        return REGISTRY[source]
    except KeyError:
        raise ValueError(f"No adapter registered for source {source.value}") from None


class HouseAdapter:
    async def fetch_active_markets(
        self, session: AsyncSession, *, limit: int = 25,
    ) -> list[Market]:
        stmt = (
            select(Market)
            .where(Market.status == MarketStatus.OPEN.value)
            .where(Market.source == MarketSourceEnum.HOUSE.value)
            .options(selectinload(Market.outcomes))
            .order_by(Market.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def fetch_market(
        self, session: AsyncSession, market_id: UUID,
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

    async def detect_resolution(
        self, session: AsyncSession, market_id: UUID,
    ) -> ResolutionResult | None:
        return None


register_source(MarketSourceEnum.HOUSE, HouseAdapter())
