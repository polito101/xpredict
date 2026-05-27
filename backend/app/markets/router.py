from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.schemas import (
    MarketCreate,
    MarketListItem,
    MarketRead,
    MarketUpdate,
    PaginatedResponse,
    paginated_response,
)
from app.markets.service import MarketService

# ---------------------------------------------------------------------------
# Admin market router — requires Bearer JWT (AUTH-07)
# ---------------------------------------------------------------------------

admin_market_router = APIRouter(
    prefix="/api/v1/admin/markets",
    tags=["admin-markets"],
)


@admin_market_router.post("", status_code=201, response_model=MarketRead)
async def create_market(
    request: Request,
    body: MarketCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    ip = request.client.host if request.client else None
    market = await MarketService.create_market(session, admin, body, ip=ip)
    await session.commit()
    refreshed = await MarketService.get_market_by_id(session, market.id)
    return MarketRead.model_validate(refreshed)


@admin_market_router.get("", response_model=PaginatedResponse[MarketListItem])
async def list_markets_admin(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: MarketSourceEnum | None = Query(default=None),
    status: MarketStatus | None = Query(default=None),
    category: str | None = Query(default=None),
) -> PaginatedResponse[MarketListItem]:
    source_val = source.value if source else None
    status_val = status.value if status else None
    items, total = await MarketService.list_markets(
        session,
        page=page,
        page_size=page_size,
        source=source_val,
        status=status_val,
        category=category,
    )
    return paginated_response(
        [MarketListItem.model_validate(m) for m in items],
        total,
        page,
        page_size,
    )


@admin_market_router.get("/{market_id}", response_model=MarketRead)
async def get_market_admin(
    market_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    market = await MarketService.get_market_by_id(session, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return MarketRead.model_validate(market)


@admin_market_router.patch("/{market_id}", response_model=MarketRead)
async def update_market(
    market_id: UUID,
    body: MarketUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    market = await MarketService.get_market_by_id(session, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    ip = request.client.host if request.client else None
    updated = await MarketService.update_market(session, market, body, admin, ip=ip)
    await session.commit()
    refreshed = await MarketService.get_market_by_id(session, updated.id)
    return MarketRead.model_validate(refreshed)


@admin_market_router.post("/{market_id}/close", response_model=MarketRead)
async def close_market(
    market_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> MarketRead:
    market = await MarketService.get_market_by_id(session, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    ip = request.client.host if request.client else None
    closed = await MarketService.close_market(session, market, admin, ip=ip)
    await session.commit()
    refreshed = await MarketService.get_market_by_id(session, closed.id)
    return MarketRead.model_validate(refreshed)


# ---------------------------------------------------------------------------
# Public market router — no auth required
# ---------------------------------------------------------------------------

public_market_router = APIRouter(
    prefix="/api/v1/markets",
    tags=["markets"],
)


@public_market_router.get("", response_model=PaginatedResponse[MarketListItem])
async def list_markets_public(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[MarketListItem]:
    items, total = await MarketService.list_markets(
        session,
        page=page,
        page_size=page_size,
        status=MarketStatus.OPEN.value,
    )
    return paginated_response(
        [MarketListItem.model_validate(m) for m in items],
        total,
        page,
        page_size,
    )


@public_market_router.get("/{slug}", response_model=MarketRead)
async def get_market_public(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MarketRead:
    market = await MarketService.get_market_by_slug(session, slug)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return MarketRead.model_validate(market)


@public_market_router.get("/{slug}/bet-check")
async def bet_check(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, bool]:
    market = await MarketService.get_market_by_slug(session, slug)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    if market.status != MarketStatus.OPEN.value:
        raise HTTPException(
            status_code=400,
            detail={"code": "MARKET_NOT_OPEN", "reason": "This market is not accepting bets"},
        )
    return {"eligible": True}
