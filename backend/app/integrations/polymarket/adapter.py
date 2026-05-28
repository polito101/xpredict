"""PolymarketAdapter — implements the MarketSource Protocol for Polymarket.

Provides: fetch_active_markets, fetch_market, detect_resolution, sync_top25.
sync_top25 uses PostgreSQL INSERT ... ON CONFLICT for idempotent upsert
on the (source, source_market_id) partial unique index (migration 0004).

detect_resolution returns None in Phase 6. Phase 7 implements real
resolution detection via Gamma API + UMA oracle status.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.market_source import ResolutionResult
from app.integrations.polymarket.schemas import GammaMarket
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, Outcome, generate_slug

log = structlog.get_logger()


class PolymarketAdapter:
    """Adapter implementing the MarketSource Protocol for Polymarket."""

    async def fetch_active_markets(
        self, session: AsyncSession, *, limit: int = 25,
    ) -> list[Market]:
        """Fetch active Polymarket-sourced markets from local DB."""
        stmt = (
            select(Market)
            .where(Market.source == MarketSourceEnum.POLYMARKET.value)
            .where(Market.status == MarketStatus.OPEN.value)
            .options(selectinload(Market.outcomes))
            .order_by(Market.volume_24hr.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def fetch_market(
        self, session: AsyncSession, market_id: UUID,
    ) -> Market | None:
        """Fetch a single market by internal UUID with outcomes + snapshots."""
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
        """Phase 6 stub — returns None. Phase 7 implements real detection."""
        return None

    async def sync_top25(
        self, session: AsyncSession, raw_markets: list[dict[str, object]],
    ) -> int:
        """Upsert raw Gamma API markets into the local DB.

        Uses INSERT ... ON CONFLICT (source, source_market_id) DO UPDATE
        to avoid duplicates. Returns count of markets synced.
        """
        synced = 0
        for raw in raw_markets:
            # --- Phase 1: Parse (ValidationError only) ---
            try:
                parsed = GammaMarket.model_validate(raw)
            except ValidationError:
                log.warning("gamma.parse_failed", raw_id=raw.get("id"))
                continue

            # Parse deadline from end_date_raw, fallback to 30 days from now.
            deadline = datetime.now(UTC) + timedelta(days=30)
            if parsed.end_date_raw:
                with contextlib.suppress(ValueError, TypeError):
                    deadline = datetime.fromisoformat(
                        parsed.end_date_raw.replace("Z", "+00:00"),
                    )

            slug = generate_slug(parsed.question)
            description = (
                parsed.description
                or "Resolution via Polymarket UMA oracle"
            )

            # --- Phase 2: DB upsert (IntegrityError handled separately) ---
            try:
                # Upsert market
                market_values = {
                    "source": MarketSourceEnum.POLYMARKET.value,
                    "source_market_id": parsed.id,
                    "condition_id": parsed.condition_id,
                    "question": parsed.question,
                    "slug": slug,
                    "polymarket_slug": parsed.slug,
                    "status": parsed.internal_status.value,
                    "volume": parsed.volume,
                    "volume_24hr": parsed.volume_24hr_decimal,
                    "deadline": deadline,
                    "resolution_criteria": description,
                }

                stmt = pg_insert(Market).values(**market_values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["source", "source_market_id"],
                    index_where=Market.source_market_id.isnot(None),
                    set_={
                        "question": stmt.excluded.question,
                        "status": stmt.excluded.status,
                        "volume": stmt.excluded.volume,
                        "volume_24hr": stmt.excluded.volume_24hr,
                        "updated_at": datetime.now(UTC),
                    },
                )
                await session.execute(stmt)

                # After upsert, fetch the market to get its id for outcomes.
                market_row = await session.execute(
                    select(Market).where(
                        Market.source == MarketSourceEnum.POLYMARKET.value,
                        Market.source_market_id == parsed.id,
                    ),
                )
                market = market_row.scalar_one_or_none()
                if market is None:
                    continue

                # Upsert YES and NO outcomes with current odds.
                if parsed.outcomes_raw and parsed.outcome_prices_raw:
                    for idx, label in enumerate(parsed.outcomes_raw[:2]):
                        price = (
                            Decimal(parsed.outcome_prices_raw[idx])
                            if idx < len(parsed.outcome_prices_raw)
                            else Decimal("0.5")
                        )
                        # Outcomes don't have a unique constraint for upsert,
                        # so we check existence first and update if present.
                        existing = await session.execute(
                            select(Outcome).where(
                                Outcome.market_id == market.id,
                                Outcome.label == label[:50],
                            ),
                        )
                        existing_outcome = existing.scalar_one_or_none()
                        if existing_outcome:
                            existing_outcome.current_odds = price
                        else:
                            session.add(
                                Outcome(
                                    market_id=market.id,
                                    label=label[:50],
                                    initial_odds=price,
                                    current_odds=price,
                                ),
                            )

                await session.flush()
                synced += 1
                log.info(
                    "market.synced",
                    source_market_id=parsed.id,
                    status=parsed.internal_status.value,
                )
            except IntegrityError:
                await session.rollback()
                log.warning(
                    "gamma.upsert_conflict",
                    source_market_id=parsed.id,
                )
                continue

        return synced
