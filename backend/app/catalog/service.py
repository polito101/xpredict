"""CatalogService — the player-facing catalog read layer (BRW-01..05).

**Approach B** (16-RESEARCH §Pattern 1): the catalog mixes standalone ``markets``
with multi-outcome ``market_groups`` (events). Rather than a SQL ``UNION``, this
runs TWO bounded (``LIMIT 100``) queries — one per table — and merges/sorts/slices
them in Python, because an event's status is a Python projection
(:func:`~app.settlement.event_service.derive_event_status`) and its volume is
``SUM(children)`` (``market_groups`` stores neither), so both sort/filter-critical
signals require the child rows regardless. Each sub-query is itself capped at
``CATALOG_LIMIT`` and the merged result is sliced ``[:CATALOG_LIMIT]`` — provably
bounded, no pagination.

Search is LOCAL ``pg_trgm`` only: ``Market.question.ilike`` / ``MarketGroup.title.ilike``
bound params against the Phase-13 GIN trigram indexes — NEVER proxied to Gamma
``/public-search`` (the documented anti-feature). The derived event status is
IMPORTED UNCHANGED from Phase 15 — this module defines no new status logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.catalog.schemas import CatalogItem, CatalogOutcome, EventOutcomeRead
from app.markets.enums import MarketStatus
from app.markets.models import Market, MarketGroup
from app.settlement.event_service import ChildStatus, derive_event_status

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Bounded, curated catalog (BRW-05): a hard cap, no pagination / infinite scroll.
CATALOG_LIMIT = 100
# An OPEN item is "closing soon" when its deadline falls within this window.
CLOSING_SOON_WINDOW = timedelta(hours=48)

# Stored market statuses surfaced in the catalog (DRAFT / CANCELLED are hidden).
_VISIBLE_MARKET_STATUSES = (
    MarketStatus.OPEN.value,
    MarketStatus.CLOSED.value,
    MarketStatus.RESOLVED.value,
)


# --------------------------------------------------------------------------- #
# Pure projection helpers (also imported by the router for event detail).
# --------------------------------------------------------------------------- #
def yes_leg(market: Market) -> tuple[UUID | None, Decimal]:
    """The market's YES outcome id + current odds, matched case-insensitively.

    House labels are ``"YES"``, mirrored Polymarket ``"Yes"`` — match
    ``label.upper() == "YES"`` (the convention in ``event_service._yes_outcome_id``).
    Falls back to ``(None, 0)`` for a malformed market with no YES leg.
    """
    for outcome in market.outcomes:
        if outcome.label.upper() == "YES":
            return outcome.id, outcome.current_odds
    return None, Decimal("0")


def child_status_of(child: Market) -> ChildStatus:
    """Build the :class:`ChildStatus` ``derive_event_status`` reads from a child market."""
    yes_id, _ = yes_leg(child)
    is_yes_winner = child.winning_outcome_id is not None and child.winning_outcome_id == yes_id
    return ChildStatus(status=child.status, is_yes_winner=is_yes_winner)


def event_deadline(children: list[Market]) -> datetime | None:
    """The event's effective deadline = the earliest OPEN child's deadline (None if none open)."""
    open_deadlines = [
        c.deadline
        for c in children
        if c.status == MarketStatus.OPEN.value and c.deadline is not None
    ]
    return min(open_deadlines) if open_deadlines else None


def _market_public_status(market: Market, now: datetime) -> str:
    """Map a stored market status into the public {open, closing_soon, resolved} set."""
    if market.status in (MarketStatus.RESOLVED.value, MarketStatus.CLOSED.value):
        return "resolved"
    # OPEN: "closing_soon" when the deadline is within the window, else "open".
    if market.deadline is not None and market.deadline <= now + CLOSING_SOON_WINDOW:
        return "closing_soon"
    return "open"


def _event_public_status(derived: str, deadline: datetime | None, now: datetime) -> str:
    """Map a derived event status into the public set (partially_resolved→open, void→resolved)."""
    if derived in ("resolved", "void"):
        return "resolved"
    # open / partially_resolved -> "closing_soon" when soon, else "open".
    if deadline is not None and deadline <= now + CLOSING_SOON_WINDOW:
        return "closing_soon"
    return "open"


def _market_matches_status(market: Market, status_filter: str | None, now: datetime) -> bool:
    if status_filter is None:
        return True
    if status_filter == "open":
        return market.status == MarketStatus.OPEN.value
    if status_filter == "closing_soon":
        return market.status == MarketStatus.OPEN.value and (
            market.deadline is not None and market.deadline <= now + CLOSING_SOON_WINDOW
        )
    if status_filter == "resolved":
        return market.status in (MarketStatus.RESOLVED.value, MarketStatus.CLOSED.value)
    return True


def _event_matches_status(
    derived: str, deadline: datetime | None, status_filter: str | None, now: datetime
) -> bool:
    if status_filter is None:
        return True
    if status_filter == "open":
        return derived in ("open", "partially_resolved")
    if status_filter == "closing_soon":
        return derived in ("open", "partially_resolved") and (
            deadline is not None and deadline <= now + CLOSING_SOON_WINDOW
        )
    if status_filter == "resolved":
        return derived in ("resolved", "void")
    return True


def _market_to_item(market: Market, now: datetime) -> CatalogItem:
    yes_id, yes_price = yes_leg(market)
    return CatalogItem(
        type="market",
        id=market.id,
        slug=market.slug,
        title=market.question,
        category=market.category,
        source=market.source,
        status=_market_public_status(market, now),
        deadline=market.deadline,
        volume=market.volume,
        created_at=market.created_at,
        outcomes=[CatalogOutcome(label="YES", yes_outcome_id=yes_id, yes_price=yes_price)],
    )


def _event_to_item(
    group: MarketGroup, children: list[Market], derived: str, now: datetime
) -> CatalogItem:
    deadline = event_deadline(children)
    volume = sum((c.volume for c in children), Decimal("0"))
    outcomes: list[CatalogOutcome] = []
    for child in children:
        yes_id, yes_price = yes_leg(child)
        outcomes.append(
            CatalogOutcome(
                label=child.group_item_title or child.question,
                yes_outcome_id=yes_id,
                yes_price=yes_price,
            )
        )
    return CatalogItem(
        type="event",
        id=group.id,
        slug=group.slug,
        title=group.title,
        category=group.category,
        source=group.source,
        status=_event_public_status(derived, deadline, now),
        deadline=deadline,
        volume=volume,
        created_at=group.created_at,
        outcomes=outcomes,
    )


def event_outcome_rows(children: list[Market]) -> list[EventOutcomeRead]:
    """Per-outcome detail rows for an event (one per child market — its YES leg)."""
    rows: list[EventOutcomeRead] = []
    for child in children:
        yes_id, yes_price = yes_leg(child)
        rows.append(
            EventOutcomeRead(
                label=child.group_item_title or child.question,
                yes_outcome_id=yes_id,
                yes_price=yes_price,
                market_id=child.id,
                child_slug=child.slug,
                child_status=child.status,
            )
        )
    return rows


class CatalogService:
    """Read-only catalog queries: browse/search/filter/sort + event detail + categories."""

    @staticmethod
    async def list_catalog(
        session: AsyncSession,
        *,
        q: str | None = None,
        category: str | None = None,
        status: str | None = None,
        sort: str = "volume",
    ) -> list[CatalogItem]:
        """Approach B: two bounded queries (markets + ≥2-child events) merged in Python.

        Every filter combination yields an explicit (possibly empty) list — never an
        error (BRW-05). Search ``q`` is a LOCAL ILIKE bound param; ``category`` is an
        exact match; ``status`` ∈ {open, closing_soon, resolved}; ``sort`` ∈
        {volume, closing_soonest, newest}. Result is bounded to ``CATALOG_LIMIT``.
        """
        now = datetime.now(UTC)
        items: list[CatalogItem] = []

        # --- Query A: standalone binary markets (group_id IS NULL) ----------------
        market_stmt = (
            select(Market)
            .where(Market.group_id.is_(None))
            .options(selectinload(Market.outcomes))
        )
        if status == "open":
            market_stmt = market_stmt.where(Market.status == MarketStatus.OPEN.value)
        elif status == "closing_soon":
            market_stmt = market_stmt.where(
                Market.status == MarketStatus.OPEN.value,
                Market.deadline <= now + CLOSING_SOON_WINDOW,
            )
        elif status == "resolved":
            market_stmt = market_stmt.where(
                Market.status.in_(
                    (MarketStatus.RESOLVED.value, MarketStatus.CLOSED.value)
                )
            )
        else:
            market_stmt = market_stmt.where(Market.status.in_(_VISIBLE_MARKET_STATUSES))
        if q:
            market_stmt = market_stmt.where(Market.question.ilike(f"%{q}%"))
        if category:
            market_stmt = market_stmt.where(Market.category == category)
        market_stmt = market_stmt.limit(CATALOG_LIMIT)

        markets = (await session.execute(market_stmt)).scalars().all()
        for market in markets:
            items.append(_market_to_item(market, now))

        # --- Query B: events (market_groups with >=2 children) --------------------
        group_stmt = select(MarketGroup).options(
            selectinload(MarketGroup.markets).selectinload(Market.outcomes)
        )
        if q:
            group_stmt = group_stmt.where(MarketGroup.title.ilike(f"%{q}%"))
        if category:
            group_stmt = group_stmt.where(MarketGroup.category == category)
        group_stmt = group_stmt.limit(CATALOG_LIMIT)

        groups = (await session.execute(group_stmt)).scalars().all()
        for group in groups:
            children = list(group.markets)
            if len(children) < 2:
                # A single-outcome group stays on the standalone /markets path (EVT-07).
                continue
            derived = derive_event_status([child_status_of(c) for c in children])
            if not _event_matches_status(derived, event_deadline(children), status, now):
                continue
            items.append(_event_to_item(group, children, derived, now))

        # --- Sort in Python + bound -----------------------------------------------
        if sort == "newest":
            items.sort(key=lambda it: it.created_at, reverse=True)
        elif sort == "closing_soonest":
            _far = datetime.max.replace(tzinfo=UTC)
            items.sort(key=lambda it: (it.deadline is None, it.deadline or _far))
        else:  # "volume" (default)
            items.sort(key=lambda it: it.volume, reverse=True)

        return items[:CATALOG_LIMIT]

    @staticmethod
    async def get_event(session: AsyncSession, slug: str) -> MarketGroup | None:
        """Eager-load a group + children + outcomes by slug (None if missing)."""
        return (
            await session.execute(
                select(MarketGroup)
                .where(MarketGroup.slug == slug)
                .options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
            )
        ).scalar_one_or_none()

    @staticmethod
    async def list_categories(session: AsyncSession) -> list[str]:
        """Sorted DISTINCT non-empty categories union over standalone markets + groups (CAT-06)."""
        market_cats = (
            await session.execute(
                select(Market.category)
                .where(Market.group_id.is_(None))
                .where(Market.category.isnot(None))
                .where(Market.category != "")
                .where(Market.status.in_(_VISIBLE_MARKET_STATUSES))
                .distinct()
            )
        ).scalars().all()
        group_cats = (
            await session.execute(
                select(MarketGroup.category)
                .where(MarketGroup.category.isnot(None))
                .where(MarketGroup.category != "")
                .distinct()
            )
        ).scalars().all()
        return sorted(set(market_cats) | set(group_cats))
