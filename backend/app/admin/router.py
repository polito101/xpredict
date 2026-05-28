"""Admin CRM router (Phase 8, Plan 08-01) — user management surface.

Six admin-Bearer-gated endpoints under ``/api/v1/admin``:

  - ``GET  /users``                     paginated list (search / status / date / sort)
  - ``GET  /users/{user_id}``           detail (profile + balance + counts)
  - ``POST /users/{user_id}/ban``       ban (mandatory reason) -> updated detail
  - ``POST /users/{user_id}/unban``     unban (optional reason) -> updated detail
  - ``GET  /users/{user_id}/transactions`` paginated wallet history
  - ``GET  /users/{user_id}/bets``      paginated bets list

Every endpoint takes ``admin: Annotated[User, Depends(current_active_admin)]``
(T-08-01 / AUTH-07) — a player cookie or no auth is 401/403. The pattern follows
``app/markets/router.py`` verbatim (admin auth + session deps, paginated GET,
state-change POST that commits then returns the refreshed entity).

# Note on ``from __future__ import annotations`` (intentionally ABSENT): FastAPI's
# ``inspect.signature`` dependency resolver on Python 3.13 mis-resolves
# ``Annotated[T, Depends(...)]`` when annotations are forward-ref strings (params
# get read as query params -> 422). Same constraint as ``app/markets/router.py``
# and ``app/wallet/admin_router.py``.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    BanRequest,
    PaginatedResponse,
    UnbanRequest,
    UserBetItem,
    UserDetail,
    UserListItem,
    UserTransactionItem,
    paginated_response,
)
from app.admin.service import AdminUserService
from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session

admin_crm_router = APIRouter(prefix="/api/v1/admin", tags=["admin-crm"])


@admin_crm_router.get("/users", response_model=PaginatedResponse[UserListItem])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(active|banned)$"),
    signup_after: datetime | None = Query(default=None),
    signup_before: datetime | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> PaginatedResponse[UserListItem]:
    items, total = await AdminUserService.list_users(
        session,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        signup_after=signup_after,
        signup_before=signup_before,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return paginated_response(
        [UserListItem.model_validate(i) for i in items],
        total,
        page,
        page_size,
    )


@admin_crm_router.get("/users/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> UserDetail:
    detail = await AdminUserService.get_user_detail(session, user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserDetail.model_validate(detail)


@admin_crm_router.post("/users/{user_id}/ban", response_model=UserDetail)
async def ban_user(
    user_id: UUID,
    body: BanRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> UserDetail:
    ip = request.client.host if request.client else None
    await AdminUserService.ban_user(session, user_id, reason=body.reason, admin=admin, ip=ip)
    await session.commit()
    detail = await AdminUserService.get_user_detail(session, user_id)
    if detail is None:  # pragma: no cover - defensive; the user was just banned
        raise HTTPException(status_code=404, detail="User not found")
    return UserDetail.model_validate(detail)


@admin_crm_router.post("/users/{user_id}/unban", response_model=UserDetail)
async def unban_user(
    user_id: UUID,
    body: UnbanRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> UserDetail:
    ip = request.client.host if request.client else None
    await AdminUserService.unban_user(session, user_id, reason=body.reason, admin=admin, ip=ip)
    await session.commit()
    detail = await AdminUserService.get_user_detail(session, user_id)
    if detail is None:  # pragma: no cover - defensive; the user was just unbanned
        raise HTTPException(status_code=404, detail="User not found")
    return UserDetail.model_validate(detail)


@admin_crm_router.get(
    "/users/{user_id}/transactions",
    response_model=PaginatedResponse[UserTransactionItem],
)
async def list_user_transactions(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[UserTransactionItem]:
    items, total = await AdminUserService.get_user_transactions(
        session, user_id, page=page, page_size=page_size
    )
    return paginated_response(
        [UserTransactionItem.model_validate(i) for i in items],
        total,
        page,
        page_size,
    )


@admin_crm_router.get(
    "/users/{user_id}/bets",
    response_model=PaginatedResponse[UserBetItem],
)
async def list_user_bets(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[UserBetItem]:
    items, total = await AdminUserService.get_user_bets(
        session, user_id, page=page, page_size=page_size
    )
    return paginated_response(
        [UserBetItem.model_validate(i) for i in items],
        total,
        page,
        page_size,
    )


__all__ = ["admin_crm_router"]
