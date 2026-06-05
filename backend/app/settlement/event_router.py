"""Admin house-event surface (EVA-01, EVA-02) — create + pre-bet edit.

``POST /admin/events`` creates one HOUSE ``MarketGroup`` + N binary YES/NO children;
``PATCH /admin/events/{group_id}`` edits metadata/outcomes ONLY while no child has a
bet — after the first bet the edit-lock returns HTTP 423 (the predicate is
``EXISTS(bets)`` over the children, NOT the dead denormalised counter column). Both
endpoints require an admin Bearer. The resolve/void/reverse routes are added to THIS
router by plan 16-04; router registration in ``app.main`` is plan 16-05.

# The PEP 563 future-annotations import is intentionally ABSENT — FastAPI 3.13 evaluates
# the Annotated/Depends markers at startup, and stringised annotations break that
# resolution (mirror app/settlement/router.py). ``User`` / ``AsyncSession`` are runtime
# imports.
"""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session
from app.markets.models import MarketGroup
from app.settlement.event_schemas import (
    CreateEventRequest,
    EventChildRead,
    EventCreatedResponse,
    EventDetailResponse,
    UpdateEventRequest,
)
from app.settlement.event_service import (
    EventService,
    _load_group_with_children,
    event_has_bets,
)

event_admin_router = APIRouter(prefix="/admin/events", tags=["admin-events"])


def _child_rows(group: MarketGroup) -> list[EventChildRead]:
    """Per-child outcome rows from an eager-loaded group (YES leg + status)."""
    rows: list[EventChildRead] = []
    for child in group.markets:
        yes = next((o for o in child.outcomes if o.label.upper() == "YES"), None)
        rows.append(
            EventChildRead(
                market_id=child.id,
                label=child.group_item_title or child.question,
                slug=child.slug,
                status=child.status,
                yes_outcome_id=(yes.id if yes else None),
                yes_price=(yes.current_odds if yes else Decimal("0")),
            )
        )
    return rows


def _event_deadline(group: MarketGroup):  # noqa: ANN202 — datetime | None, kept loose for response build
    children = list(group.markets)
    return children[0].deadline if children else None


def _to_response(group: MarketGroup, response_cls):  # noqa: ANN001, ANN202
    return response_cls(
        id=group.id,
        title=group.title,
        slug=group.slug,
        category=group.category,
        source=group.source,
        deadline=_event_deadline(group),
        outcomes=_child_rows(group),
    )


@event_admin_router.post("", response_model=EventCreatedResponse, status_code=201)
async def create_event(
    body: CreateEventRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventCreatedResponse:
    """Create a house multi-outcome event (EVA-01, admin-only)."""
    admin_id = admin.id  # capture before the service's commit churns the session
    group = await EventService.create_house_event(session, admin_id=admin_id, body=body)
    return _to_response(group, EventCreatedResponse)


@event_admin_router.patch("/{group_id}", response_model=EventDetailResponse)
async def update_event(
    group_id: UUID,
    body: UpdateEventRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventDetailResponse:
    """Edit a house event's metadata/outcomes pre-bet; HTTP 423 after the first bet (EVA-02)."""
    existing = await _load_group_with_children(session, group_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if await event_has_bets(session, group_id):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "code": "EVENT_LOCKED",
                "reason": "Event outcomes/metadata cannot be changed after a bet has been placed",
            },
        )
    updated = await EventService.update_house_event(session, group_id=group_id, body=body)
    return _to_response(updated, EventDetailResponse)


__all__ = ["event_admin_router"]
