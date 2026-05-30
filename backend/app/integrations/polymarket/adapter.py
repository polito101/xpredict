"""PolymarketAdapter — implements the MarketSource Protocol for Polymarket.

Provides: fetch_active_markets, fetch_market, detect_resolution, sync_top25.
sync_top25 uses PostgreSQL INSERT ... ON CONFLICT for idempotent upsert
on the (source, source_market_id) partial unique index (migration 0004).

detect_resolution queries Gamma for a single market's current UMA state and
returns a ResolutionResult if the canonical _derive_status() reports RESOLVED,
otherwise None. Phase 7 (STL-01).
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
from app.integrations.polymarket.client import GammaClient
from app.integrations.polymarket.schemas import GammaMarket
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, Outcome, generate_slug
from app.realtime.publisher import format_odds

log = structlog.get_logger()


def _map_winning_outcome_id(
    outcome_prices_raw: list[str],
    outcomes_raw: list[str],
    db_outcomes: list[Outcome],
) -> UUID:
    """Return the DB Outcome UUID whose label matches the winning Gamma outcome.

    Winner is the first index where outcomePrices is "1" or "1.0".
    Labels were stored as label[:50] during sync_top25.
    Raises ValueError on no clear winner or label mismatch.
    """
    winner_idx = next(
        (i for i, p in enumerate(outcome_prices_raw) if p in ("1", "1.0")),
        None,
    )
    if winner_idx is None or winner_idx >= len(outcomes_raw):
        raise ValueError(f"No clear winner in outcomePrices: {outcome_prices_raw}")
    winner_label = outcomes_raw[winner_idx]
    label_to_id = {o.label: o.id for o in db_outcomes}
    truncated = winner_label[:50]
    if truncated not in label_to_id:
        raise ValueError(
            f"Winner label '{truncated}' not found in DB outcomes: {list(label_to_id)}"
        )
    return label_to_id[truncated]


class PolymarketAdapter:
    """Adapter implementing the MarketSource Protocol for Polymarket."""

    def __init__(self) -> None:
        # Per-sync record of markets whose outcome odds ACTUALLY changed, for the
        # real-time publish (MKT-04 / producer site #2). Only markets whose
        # per-market upsert committed (i.e. did NOT hit the IntegrityError
        # rollback+continue) appear here. Read by _run_poll_sync to publish
        # POST-COMMIT, on-change only (Pitfall 3 + 4). Each entry is
        # ``(market_id_str, [{"outcome_id", "odds"}])``.
        self.changed_markets: list[tuple[str, list[dict[str, str]]]] = []

    async def fetch_active_markets(
        self,
        session: AsyncSession,
        *,
        limit: int = 25,
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
        self,
        session: AsyncSession,
        market_id: UUID,
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
        self,
        session: AsyncSession,
        market_id: UUID,
    ) -> ResolutionResult | None:
        """Check if a Polymarket-mirrored market has been resolved by UMA (STL-01).

        Delegates the closed/UMA truth table entirely to GammaMarket._derive_status().
        Returns ResolutionResult when RESOLVED with a clear winner, None otherwise.
        """
        stmt = select(Market).where(Market.id == market_id).options(selectinload(Market.outcomes))
        result = await session.execute(stmt)
        market = result.scalar_one_or_none()
        if market is None or market.source_market_id is None:
            log.warning("gamma.market_not_found", market_id=str(market_id))
            return None

        client = GammaClient()
        try:
            raw = await client.fetch_market_by_id(market.source_market_id)
        finally:
            await client.close()

        if raw is None:
            log.warning("gamma.market_not_found", source_market_id=market.source_market_id)
            return None

        try:
            parsed = GammaMarket.model_validate(raw)
        except ValidationError:
            log.warning("gamma.parse_failed", source_market_id=market.source_market_id)
            return None

        if parsed.internal_status != MarketStatus.RESOLVED:
            return None

        try:
            winning_outcome_id = _map_winning_outcome_id(
                parsed.outcome_prices_raw,
                parsed.outcomes_raw,
                market.outcomes,
            )
        except ValueError as exc:
            log.warning("gamma.winner_mapping_failed", error=str(exc), market_id=str(market_id))
            return None

        return ResolutionResult(
            winning_outcome_id=winning_outcome_id,
            source="polymarket_uma",
            confidence="high",
        )

    async def sync_top25(
        self,
        session: AsyncSession,
        raw_markets: list[dict[str, object]],
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

            # Use a deterministic slug from the Gamma API slug to avoid
            # random-suffix collisions on every sync cycle (WR-01).
            # Prefix with "pm-" to namespace away from house market slugs.
            slug = f"pm-{parsed.slug}"[:100] if parsed.slug else generate_slug(parsed.question)
            description = parsed.description or "Resolution via Polymarket UMA oracle"

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
                        "polymarket_slug": stmt.excluded.polymarket_slug,
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
                # Track per-market odds CHANGES for the real-time publish: only an
                # existing outcome whose current_odds actually differs from the
                # synced price counts (Pitfall 4 — no publish on an unchanged tick).
                market_deltas: list[dict[str, str]] = []
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
                            if existing_outcome.current_odds != price:
                                existing_outcome.current_odds = price
                                market_deltas.append(
                                    {
                                        "outcome_id": str(existing_outcome.id),
                                        "odds": format_odds(price),
                                    },
                                )
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
                # Record this market's deltas only AFTER a successful flush (a
                # market that hits IntegrityError below rolls back + continues, so
                # its deltas are never recorded — published state == committed state).
                if market_deltas:
                    self.changed_markets.append((str(market.id), market_deltas))
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
