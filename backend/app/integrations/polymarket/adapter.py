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
from uuid import UUID, uuid4

import structlog
from pydantic import ValidationError
from slugify import slugify as _slugify
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.market_source import ResolutionResult
from app.integrations.polymarket.client import GammaClient
from app.integrations.polymarket.schemas import GammaEvent, GammaMarket
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup, Outcome, generate_slug
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

    async def _upsert_one_market(
        self,
        session: AsyncSession,
        parsed: GammaMarket,
        *,
        group_id: UUID | None,
        category: str | None,
    ) -> bool:
        """Upsert ONE binary market + its YES/NO outcomes. Returns True on success.

        This is the EXACT per-market body lifted out of ``sync_top25``, plus three
        writes: ``group_id``, ``category``, and ``group_item_title`` (only present
        on ``GammaEventMarket`` children — ``getattr`` keeps the legacy
        ``GammaMarket`` path working). Records ``self.changed_markets`` for the
        real-time publish identically to before. Returns ``False`` (after a
        rollback) on the ``IntegrityError`` conflict path; the caller decides
        whether to continue.
        """
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

        # --- DB upsert (IntegrityError handled separately) ---
        # CR-01: run THIS child's upsert inside a SAVEPOINT. A conflict on one
        # child must roll back only its own work — NEVER the parent market_groups
        # row or prior siblings already written in the outer transaction. A bare
        # ``session.rollback()`` here discarded the whole per-category transaction,
        # orphaning the group row and FK-violating the per-category commit. (14-REVIEW CR-01)
        market_deltas: list[dict[str, str]] = []
        market: Market | None = None
        nested = await session.begin_nested()
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
                "category": category,  # CAT-04 — first populated by the curated sync
                "group_id": group_id,  # EVT-01 child stamp (NULL = standalone)
                "group_item_title": getattr(parsed, "group_item_title", None),
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
                    "category": stmt.excluded.category,
                    "group_id": stmt.excluded.group_id,
                    "group_item_title": stmt.excluded.group_item_title,
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
                await nested.rollback()
                return False

            # Upsert YES and NO outcomes with current odds.
            # Track per-market odds CHANGES for the real-time publish: only an
            # existing outcome whose current_odds actually differs from the
            # synced price counts (Pitfall 4 — no publish on an unchanged tick).
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
            await nested.commit()
        except IntegrityError:
            # Roll back ONLY this child's SAVEPOINT — the parent group row and
            # prior siblings in the outer transaction survive (CR-01).
            await nested.rollback()
            log.warning(
                "gamma.upsert_conflict",
                source_market_id=parsed.id,
            )
            return False

        # Record deltas only AFTER the SAVEPOINT commits — published state ==
        # committed state. A child that hit IntegrityError returned above and
        # never reaches here, so its deltas are never published (Pitfall 4).
        if market_deltas:
            self.changed_markets.append((str(market.id), market_deltas))
        log.info(
            "market.synced",
            source_market_id=parsed.id,
            status=parsed.internal_status.value,
        )
        return True

    async def _upsert_market_group(
        self,
        session: AsyncSession,
        ev: GammaEvent,
        category: str,
    ) -> UUID:
        """Upsert the parent ``market_groups`` row for a multi-outcome event.

        Idempotent on the Phase-13 partial-unique ``(source, source_event_id)``
        (``ix_market_groups_source_source_event_id``) — replaying the same event
        updates the existing row instead of inserting a duplicate. Writes ONLY the
        columns ``market_groups`` actually has (``source``, ``source_event_id``,
        ``title``, ``slug``, ``category``); the table deliberately stores no
        volume/status column (EVT-06). Returns the group's UUID.

        ``MarketGroup.slug`` is ``String(100) UNIQUE`` but the ON CONFLICT target
        is ``(source, source_event_id)`` — a slug clash across *different* events
        is therefore not absorbed by the upsert and raises ``IntegrityError``. We
        retry once inside a SAVEPOINT with a uuid-suffixed slug (Pitfall 6) so one
        event's slug collision can never abort its siblings.
        """
        base_slug = f"pm-evt-{_slugify(ev.title, max_length=80)}"
        slug = base_slug[:100] if base_slug != "pm-evt-" else generate_slug(ev.title)

        async def _do_upsert(slug_value: str) -> None:
            values = {
                "source": MarketSourceEnum.POLYMARKET.value,
                "source_event_id": ev.id,  # Gamma event id (CONTEXT discretion)
                "title": ev.title,
                "slug": slug_value,
                "category": category,  # CAT-04
            }
            stmt = pg_insert(MarketGroup).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "source_event_id"],
                index_where=MarketGroup.source_event_id.isnot(None),
                set_={
                    "title": stmt.excluded.title,
                    "category": stmt.excluded.category,
                    "updated_at": datetime.now(UTC),
                },
            )
            await session.execute(stmt)
            await session.flush()

        try:
            async with session.begin_nested():
                await _do_upsert(slug)
        except IntegrityError:
            # Slug collision across a DIFFERENT event (ON CONFLICT is on
            # source_event_id, not slug). The failed SAVEPOINT is already rolled
            # back by the context manager; retry once with a uuid-suffixed slug in
            # a FRESH SAVEPOINT (WR-04 — never re-issue _do_upsert against an
            # already-aborted SAVEPOINT).
            log.warning(
                "gamma.group_slug_collision",
                source_event_id=ev.id,
                slug=slug,
            )
            slug = f"{base_slug[:93]}-{uuid4().hex[:6]}"
            async with session.begin_nested():
                await _do_upsert(slug)

        row = await session.execute(
            select(MarketGroup.id).where(
                MarketGroup.source == MarketSourceEnum.POLYMARKET.value,
                MarketGroup.source_event_id == ev.id,
            ),
        )
        return row.scalar_one()

    async def sync_events(
        self,
        session: AsyncSession,
        events: list[GammaEvent],
        *,
        category: str,
    ) -> int:
        """Upsert curated events: 1 ``market_groups`` row + N stamped children.

        Per event: dedup children within the event by ``condition_id`` (drop
        falsy/duplicate ids — CAT-02 market grain). A ``len == 1`` event (after
        dedup) stays on the standalone binary path — ``_upsert_one_market`` with
        ``group_id=None``, NO ``market_groups`` row (EVT-07). Otherwise upsert the
        parent group once, then stamp every child with that ``group_id`` +
        ``category``. Returns the count of child markets successfully upserted.

        ``sync_events`` is only ever called with a non-empty curated list per
        category (CAT-06: never persist an empty category — suppression is a
        Phase-16 read). Every child's status flows through the inherited
        ``GammaMarket._derive_status``; this path writes status only, never
        settles (spike-002 / Phase 15).
        """
        synced = 0
        for ev in events:
            # Dedup children by their Gamma market id (= source_market_id, the
            # ON CONFLICT persistence key — always present on a parsed market).
            # Keying on condition_id was wrong (14-AUDIT C-2): Gamma leaves
            # conditionId="" on not-yet-deployed markets, so a blank/duplicate
            # conditionId could silently drop a real child, collapse a multi-outcome
            # event to the standalone path, or (all-blank) drop the event entirely.
            # id-grain dedup removes only true duplicate markets and never an outcome.
            seen: set[str] = set()
            children: list[GammaMarket] = []
            for m in ev.markets:
                if not m.id or m.id in seen:
                    continue
                seen.add(m.id)
                children.append(m)

            if not children:
                continue

            if len(children) == 1:  # EVT-07 — standalone, NO group row
                if await self._upsert_one_market(
                    session,
                    children[0],
                    group_id=None,
                    category=category,
                ):
                    synced += 1
                continue

            # Multi-outcome event → 1 parent group + N children. Guard against a
            # "widowed" group: if EVERY child fails to upsert (e.g. all child slugs
            # collide), roll the whole event back in a SAVEPOINT so we never persist a
            # childless market_groups row (which Phase-16 browse would mis-render and a
            # later sync would have to repopulate). A pre-existing group is unharmed —
            # the rollback only discards THIS cycle's no-op ON CONFLICT DO UPDATE.
            synced_before = synced
            event_sp = await session.begin_nested()
            try:
                group_id = await self._upsert_market_group(session, ev, category)
                for child in children:
                    if await self._upsert_one_market(
                        session,
                        child,
                        group_id=group_id,
                        category=category,
                    ):
                        synced += 1
                if synced == synced_before:
                    await event_sp.rollback()
                    log.warning(
                        "gamma.event_all_children_failed",
                        source_event_id=ev.id,
                        category=category,
                    )
                else:
                    await event_sp.commit()
            except Exception:
                await event_sp.rollback()
                raise

        return synced

    async def sync_top25(
        self,
        session: AsyncSession,
        raw_markets: list[dict[str, object]],
    ) -> int:
        """Upsert raw Gamma API markets into the local DB.

        Uses INSERT ... ON CONFLICT (source, source_market_id) DO UPDATE
        to avoid duplicates. Returns count of markets synced. Delegates the
        per-market DB body to ``_upsert_one_market`` with ``group_id=None`` and
        ``category=None`` so the legacy top-25 path stays byte-equivalent.
        """
        synced = 0
        for raw in raw_markets:
            # --- Parse (ValidationError only) ---
            try:
                parsed = GammaMarket.model_validate(raw)
            except ValidationError:
                log.warning("gamma.parse_failed", raw_id=raw.get("id"))
                continue

            if await self._upsert_one_market(
                session,
                parsed,
                group_id=None,
                category=None,
            ):
                synced += 1

        return synced
