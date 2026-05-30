from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.bets.models import Bet
from app.core.audit.service import AuditService
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot, Outcome, generate_slug
from app.markets.schemas import (
    ActivityItem,
    MarketCreate,
    MarketUpdate,
    PriceHistoryResponse,
    PricePoint,
)
from app.realtime.publisher import format_odds

# Price-history window allowlist (T-09-08). The cutoff is derived from these
# validated values — never from a raw interval string interpolated into SQL.
_WINDOW_CUTOFFS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
# Windows that ship RAW 5-min snapshots; everything else (30d) is downsampled.
_RAW_WINDOWS = frozenset({"24h", "7d"})


class MarketService:
    @staticmethod
    async def create_market(
        session: AsyncSession,
        admin_user: User,
        body: MarketCreate,
        ip: str | None = None,
    ) -> Market:
        for _attempt in range(3):
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
            try:
                nested = await session.begin_nested()
                await session.flush()
                break
            except IntegrityError:
                await nested.rollback()
                session.expunge(market)
        else:
            raise HTTPException(status_code=409, detail="Slug collision — try again")

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
    ) -> tuple[Market, list[dict[str, str]]]:
        """Update a market in place; return ``(market, odds_deltas)``.

        ``odds_deltas`` is the list of ``{"outcome_id", "odds"}`` changed by an
        ``odds_yes`` edit (empty otherwise). The caller (router) publishes them
        POST-COMMIT for the real-time stream (MKT-04 / Pitfall 3) — this method
        only flush()es, never commits, and never publishes inside the transaction.
        """
        if market.status != MarketStatus.OPEN.value:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVALID_STATUS",
                    "reason": f"Cannot update market with status {market.status}",
                },
            )
        if market.bet_count > 0 and body.resolution_criteria is not None:
            raise HTTPException(
                status_code=423,
                detail={
                    "code": "CRITERIA_LOCKED",
                    "reason": "Resolution criteria cannot be changed after bets have been placed",
                },
            )

        changed_fields: list[str] = []
        # Odds-change deltas returned for the router's POST-COMMIT publish (MKT-04 /
        # Pitfall 3 / T-09-03) — never published inside this transaction. Empty when
        # the PATCH carries no odds_yes.
        odds_deltas: list[dict[str, str]] = []

        if body.resolution_criteria is not None:
            market.resolution_criteria = body.resolution_criteria
            changed_fields.append("resolution_criteria")
        if body.deadline is not None:
            market.deadline = body.deadline
            changed_fields.append("deadline")
        if "category" in body.model_fields_set:
            market.category = body.category
            changed_fields.append("category")
        if body.odds_yes is not None:
            odds_no = Decimal("1") - body.odds_yes
            stmt = select(Outcome).where(Outcome.market_id == market.id)
            result = await session.execute(stmt)
            for outcome in result.scalars():
                # Case-insensitive YES match (IN-01): house markets store "YES",
                # but the Polymarket adapter stores the Gamma title-case "Yes"
                # verbatim. An admin odds_yes edit on a Polymarket-mirrored market
                # must still target the YES leg — a case-sensitive ``== "YES"`` would
                # miss it and assign odds_no to BOTH outcomes.
                if outcome.label.upper() == "YES":
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
                odds_deltas.append(
                    {
                        "outcome_id": str(outcome.id),
                        "odds": format_odds(outcome.current_odds),
                    },
                )
            changed_fields.append("odds")

        if changed_fields:
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
        return market, odds_deltas

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
    async def list_home_markets(session: AsyncSession) -> list[Market]:
        """Return house markets first (by created_at desc), then Polymarket by
        volume_24hr desc (D-01). Home page endpoint — no pagination.
        """
        # Query 1: house markets, OPEN, ordered by created_at desc, bounded
        house_stmt = (
            select(Market)
            .where(Market.source == MarketSourceEnum.HOUSE.value)
            .where(Market.status == MarketStatus.OPEN.value)
            .options(selectinload(Market.outcomes))
            .order_by(Market.created_at.desc())
            .limit(50)
        )
        house_result = await session.execute(house_stmt)
        house_markets = list(house_result.scalars().all())

        # Query 2: Polymarket markets, OPEN, ordered by volume_24hr desc, limit 25
        pm_stmt = (
            select(Market)
            .where(Market.source == MarketSourceEnum.POLYMARKET.value)
            .where(Market.status == MarketStatus.OPEN.value)
            .options(selectinload(Market.outcomes))
            .order_by(Market.volume_24hr.desc())
            .limit(25)
        )
        pm_result = await session.execute(pm_stmt)
        pm_markets = list(pm_result.scalars().all())

        return house_markets + pm_markets

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
        session: AsyncSession,
        market_id: UUID,
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
        session: AsyncSession,
        slug: str,
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

    @staticmethod
    async def price_history(
        session: AsyncSession,
        slug: str,
        window: str,
    ) -> PriceHistoryResponse:
        """Return the YES outcome's price-history series for ``window`` (MKT-03).

        24h / 7d → RAW ``OddsSnapshot`` rows (5-min cadence) for the YES outcome,
        ascending by ``snapshot_at``. 30d → DOWNSAMPLED server-side to ~hourly
        buckets (T-09-07): one representative snapshot per ``date_trunc('hour', …)``
        bucket (the latest in each), so the browser never receives ~8640 raw points.

        ``window`` is the validated allowlist value (the caller / router enforces the
        allowlist, T-09-08); the cutoff is derived from it, never interpolated.
        Raises ``HTTPException(404)`` for an unknown / non-public market.

        A market with <2 snapshots in-window yields an empty / single-point payload
        the frontend renders as the friendly 'not enough history' placeholder.
        """
        cutoff = datetime.now(UTC) - _WINDOW_CUTOFFS[window]

        # Resolve market by slug (mirror get_market_by_slug; only the id + status are
        # needed here so no eager-load of relationships).
        market_stmt = select(Market.id, Market.status).where(Market.slug == slug)
        market_row = (await session.execute(market_stmt)).first()
        if market_row is None or market_row.status not in (
            MarketStatus.OPEN.value,
            MarketStatus.CLOSED.value,
        ):
            raise HTTPException(status_code=404, detail="Market not found")
        market_id = market_row.id

        # The YES outcome for this market. Compare case-insensitively (IN-01):
        # house markets seed the label as "YES", but the Polymarket adapter stores
        # the Gamma API's title-case "Yes" verbatim (adapter.py: label[:50], never
        # normalized). A case-sensitive ``== "YES"`` silently returned NULL for
        # Polymarket-mirrored markets, so their price-history chart rendered empty.
        yes_stmt = select(Outcome.id).where(
            Outcome.market_id == market_id,
            func.upper(Outcome.label) == "YES",
        )
        yes_outcome_id = (await session.execute(yes_stmt)).scalar_one_or_none()
        if yes_outcome_id is None:
            return PriceHistoryResponse(window=window, points=[])

        if window in _RAW_WINDOWS:
            raw_stmt = (
                select(OddsSnapshot.snapshot_at, OddsSnapshot.probability)
                .where(OddsSnapshot.outcome_id == yes_outcome_id)
                .where(OddsSnapshot.snapshot_at >= cutoff)
                .order_by(OddsSnapshot.snapshot_at.asc())
            )
            rows = (await session.execute(raw_stmt)).all()
            points = [PricePoint(ts=ts, probability=prob) for ts, prob in rows]
            return PriceHistoryResponse(window=window, points=points)

        # 30d → hourly downsample. DISTINCT ON (bucket) keeps the latest snapshot in
        # each hour bucket (Postgres-native, 09-RESEARCH Pattern 5). The DISTINCT ON
        # leading-column rule requires the ORDER BY to start with the bucket; a second
        # ascending pass re-orders the kept points by time for the chart.
        bucket = func.date_trunc("hour", OddsSnapshot.snapshot_at).label("bucket")
        distinct_stmt = (
            select(OddsSnapshot.snapshot_at, OddsSnapshot.probability, bucket)
            .where(OddsSnapshot.outcome_id == yes_outcome_id)
            .where(OddsSnapshot.snapshot_at >= cutoff)
            .distinct(bucket)
            .order_by(bucket, OddsSnapshot.snapshot_at.desc())
        )
        rows = (await session.execute(distinct_stmt)).all()
        points = sorted(
            (PricePoint(ts=ts, probability=prob) for ts, prob, _bucket in rows),
            key=lambda p: p.ts,
        )
        return PriceHistoryResponse(window=window, points=points)

    @staticmethod
    async def recent_activity(
        session: AsyncSession,
        slug: str,
        limit: int = 20,
    ) -> list[ActivityItem]:
        """Return the last ``limit`` bets on a market, ANONYMIZED (MKT-03, T-09-05).

        The query selects ONLY ``Bet.stake`` / ``Bet.created_at`` and the chosen
        outcome's ``label`` — joining ``outcomes`` on ``outcome_id``. It NEVER selects
        ``user_id`` / email / ``display_name``; anonymization lives in the query +
        the ``ActivityItem`` schema (which has no user field), not in the client
        (CONTEXT Area 1, 09-RESEARCH Pattern 8). Newest-first, capped at ``limit``.

        Raises ``HTTPException(404)`` for an unknown / non-public market.
        """
        market_stmt = select(Market.id, Market.status).where(Market.slug == slug)
        market_row = (await session.execute(market_stmt)).first()
        if market_row is None or market_row.status not in (
            MarketStatus.OPEN.value,
            MarketStatus.CLOSED.value,
        ):
            raise HTTPException(status_code=404, detail="Market not found")
        market_id = market_row.id

        # SELECT b.stake, b.created_at, o.label — NO user identity selected.
        activity_stmt = (
            select(Bet.stake, Bet.created_at, Outcome.label)
            .join(Outcome, Outcome.id == Bet.outcome_id)
            .where(Bet.market_id == market_id)
            .order_by(Bet.created_at.desc())
            .limit(limit)
        )
        rows = (await session.execute(activity_stmt)).all()
        return [
            ActivityItem(outcome=label, amount=stake, created_at=created_at)
            for stake, created_at, label in rows
        ]
