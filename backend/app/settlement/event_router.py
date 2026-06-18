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

from datetime import datetime
from decimal import Decimal
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup
from app.settlement.event_schemas import (
    CreateEventRequest,
    EventActionResponse,
    EventChildRead,
    EventCreatedResponse,
    EventDetailResponse,
    ResolveEventRequest,
    ReverseEventRequest,
    UpdateEventRequest,
    VoidEventRequest,
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


_ResponseT = TypeVar("_ResponseT", EventCreatedResponse, EventDetailResponse)


def _event_deadline(group: MarketGroup) -> datetime | None:
    children = list(group.markets)
    return children[0].deadline if children else None


def _to_response(group: MarketGroup, response_cls: type[_ResponseT]) -> _ResponseT:
    return response_cls(
        id=group.id,
        title=group.title,
        slug=group.slug,
        category=group.category,
        source=group.source,
        deadline=_event_deadline(group),
        outcomes=_child_rows(group),
    )


def _map_event_value_error(exc: ValueError, group_id: UUID) -> HTTPException:
    """Map an ``EventService`` ``ValueError`` to its HTTP status (the EVA error contract).

    mirrored (Polymarket) → 409 · blank justification → 422 · bad winning-outcome → 422
    · missing group → 404 · anything else → 400 (defensive). Matches the exact messages
    raised in ``event_service.py`` (``_reject_if_mirrored`` / ``_require_justification`` /
    the winning-outcome guards / the missing-group raise).
    """
    message = str(exc)
    if "Mirrored" in message:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    if "No market group" in message:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if "winning_outcome_id" in message:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)
    if "justification" in message:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


async def _load_for_settle(
    session: AsyncSession, group_id: UUID
) -> tuple[MarketGroup, list[Market]]:
    """Read-only load for a preview branch: 404 if missing, 409 if mirrored (Polymarket).

    Mirrors the service guards (``event_service.py`` ``_reject_if_mirrored`` /
    missing-group raise) so the preview returns the SAME 409/404 the execute branch
    would — without touching the mutating service.
    """
    group = await _load_group_with_children(session, group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No market group {group_id}."
        )
    if group.source == MarketSourceEnum.POLYMARKET.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mirrored (Polymarket) events are admin read-only; use force-settle (ADM-06).",
        )
    return group, list(group.markets)


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


# --------------------------------------------------------------------------- #
# Settle surface (EVA-03..05 over HTTP) — resolve / void / reverse with the
# stateless two-step confirm. The preview branch is read-only; the execute branch
# captures admin_id, rolls back the request session's read tx (MissingGreenlet +
# 23505 choreography), then calls the Phase-15 EventService (which owns its own
# per-child fresh sessions). The endpoints NEVER loop children to settle.
# --------------------------------------------------------------------------- #
@event_admin_router.post("/{group_id}/resolve", response_model=EventActionResponse)
async def resolve_event(
    group_id: UUID,
    body: ResolveEventRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventActionResponse:
    """Resolve a house event on the winning outcome (EVA-03) — two-step confirm."""
    if not body.confirm:
        _group, children = await _load_for_settle(session, group_id)
        # Pre-validate the winner is a child's YES leg (mirror the service guard) → 422.
        yes_ids = {
            yes
            for child in children
            if (yes := next((o.id for o in child.outcomes if o.label.upper() == "YES"), None))
            is not None
        }
        if body.winning_outcome_id not in yes_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"winning_outcome_id {body.winning_outcome_id} is not the YES outcome "
                    f"of a child of group {group_id}."
                ),
            )
        return EventActionResponse(
            preview=True,
            group_id=group_id,
            child_count=len(children),
            winners=1,
            losers=len(children) - 1,
            projected_status="resolved",
        )

    admin_id = admin.id
    await session.rollback()
    try:
        result = await EventService.resolve_event(
            group_id=group_id,
            winning_outcome_id=body.winning_outcome_id,
            justification=body.justification,
            actor_user_id=admin_id,
        )
    except ValueError as exc:
        raise _map_event_value_error(exc, group_id) from exc
    return EventActionResponse(
        preview=False,
        group_id=group_id,
        child_count=result.child_count,
        children_settled=result.children_settled,
        children_failed=[str(x) for x in result.children_failed],
        projected_status=result.status,
    )


@event_admin_router.post("/{group_id}/void", response_model=EventActionResponse)
async def void_event(
    group_id: UUID,
    body: VoidEventRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventActionResponse:
    """Void a house event — every child settles on NO (EVA-04) — two-step confirm."""
    if not body.confirm:
        _group, children = await _load_for_settle(session, group_id)
        return EventActionResponse(
            preview=True,
            group_id=group_id,
            child_count=len(children),
            winners=0,
            losers=len(children),
            projected_status="void",
        )

    admin_id = admin.id
    await session.rollback()
    try:
        result = await EventService.void_event(
            group_id=group_id,
            justification=body.justification,
            actor_user_id=admin_id,
        )
    except ValueError as exc:
        raise _map_event_value_error(exc, group_id) from exc
    return EventActionResponse(
        preview=False,
        group_id=group_id,
        child_count=result.child_count,
        children_settled=result.children_settled,
        children_failed=[str(x) for x in result.children_failed],
        projected_status=result.status,
    )


@event_admin_router.post("/{group_id}/reverse", response_model=EventActionResponse)
async def reverse_event(
    group_id: UUID,
    body: ReverseEventRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventActionResponse:
    """Reverse a house event's settlement via compensating entries (EVA-05) — two-step."""
    if not body.confirm:
        _group, children = await _load_for_settle(session, group_id)
        settled = sum(1 for c in children if c.status == MarketStatus.RESOLVED.value)
        return EventActionResponse(
            preview=True,
            group_id=group_id,
            child_count=len(children),
            settled_children_to_reverse=settled,
            projected_status="open",
        )

    admin_id = admin.id
    await session.rollback()
    try:
        result = await EventService.reverse_event(
            group_id=group_id,
            justification=body.justification,
            actor_user_id=admin_id,
        )
    except ValueError as exc:
        raise _map_event_value_error(exc, group_id) from exc
    return EventActionResponse(
        preview=False,
        group_id=group_id,
        child_count=result.child_count,
        children_settled=result.children_settled,
        children_failed=[str(x) for x in result.children_failed],
        projected_status=result.status,
    )


__all__ = ["event_admin_router"]
