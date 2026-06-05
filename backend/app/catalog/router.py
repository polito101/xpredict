"""Public catalog read endpoints (BRW-01..05) under ``/api/v1``.

``GET /catalog`` (bounded browse/search/filter/sort), ``GET /events/{slug}``
(event detail, ≥2-child gate), ``GET /categories`` (non-empty union). All reads are
intentionally UNAUTHENTICATED — no admin-auth dependency on these routes.

IMPORTANT — this module deliberately OMITS the PEP 563 ``__future__`` annotations import.
With PEP 563 future annotations enabled, FastAPI 3.13 sees the ``Depends()`` /
``Query()`` markers inside ``Annotated[...]`` as bare strings and fails to resolve
the dependency at startup. The settlement admin router omits it for the same reason
(app/settlement/router.py). Do NOT add the future-import to this file.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import CatalogItem, EventDetail
from app.catalog.service import (
    CatalogService,
    child_status_of,
    event_deadline,
    event_outcome_rows,
)
from app.db.session import get_async_session
from app.settlement.event_service import derive_event_status

public_catalog_router = APIRouter(prefix="/api/v1", tags=["catalog"])


@public_catalog_router.get("/catalog", response_model=list[CatalogItem])
async def list_catalog(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[Literal["open", "closing_soon", "resolved"] | None, Query()] = None,
    sort: Annotated[Literal["volume", "closing_soonest", "newest"], Query()] = "volume",
) -> list[CatalogItem]:
    """Bounded (LIMIT 100) catalog browse — local search, category/status filters, sort.

    Bad ``status`` / ``sort`` values fail FastAPI ``Literal`` validation (422) before
    the service runs; every accepted filter combination returns 200 + a (possibly
    empty) list, never an error.
    """
    return await CatalogService.list_catalog(
        session, q=q, category=category, status=status, sort=sort
    )


@public_catalog_router.get("/events/{slug}", response_model=EventDetail)
async def get_event_detail(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventDetail:
    """Event detail by slug — per-outcome YES rows + derived status. ≥2-child only.

    A 1-child group (EVT-07: stays on /markets/{slug}) or a missing slug → 404.
    """
    group = await CatalogService.get_event(session, slug)
    children = list(group.markets) if group is not None else []
    if group is None or len(children) < 2:
        raise HTTPException(status_code=404, detail="Event not found")
    derived = derive_event_status([child_status_of(c) for c in children])
    return EventDetail(
        id=group.id,
        slug=group.slug,
        title=group.title,
        category=group.category,
        source=group.source,
        status=derived,
        deadline=event_deadline(children),
        created_at=group.created_at,
        outcomes=event_outcome_rows(children),
    )


@public_catalog_router.get("/categories", response_model=list[str])
async def list_categories(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[str]:
    """The sorted, non-empty DISTINCT category union over markets + events (CAT-06)."""
    return await CatalogService.list_categories(session)


__all__ = ["public_catalog_router"]
