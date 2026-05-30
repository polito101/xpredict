"""Admin CSV export router (Phase 8, Plan 08-02, ADU-06).

Three admin-Bearer-gated GET endpoints under ``/api/v1/admin/export`` that turn
the filtered admin views into downloadable CSV files (D-08):

  - ``GET /users``         filtered user list  -> ``users.csv``
  - ``GET /transactions``  wallet history      -> ``transactions.csv``
  - ``GET /bets``          bets list           -> ``bets.csv``

Every endpoint takes ``admin: Annotated[User, Depends(current_active_admin)]``
(T-08-06): no Bearer -> 401, a player Bearer -> 403. The ``/users`` endpoint
accepts the same filter query params as ``GET /api/v1/admin/users`` so the admin
exports exactly the view they are looking at; ``/transactions`` and ``/bets``
accept an optional ``user_id`` to scope the export to a single user.

Each endpoint asks ``AdminUserService`` for rows of dicts, hands them to the
matching ``csv_export`` builder (which sanitizes every cell against formula
injection — D-09 / T-08-05 — and renders money as plain strings + timestamps as
ISO 8601 UTC), and returns a ``text/csv`` ``Response`` with a
``Content-Disposition: attachment`` header.

# ``from __future__ import annotations`` is intentionally ABSENT — same FastAPI
# + Python 3.13 ``Annotated[T, Depends(...)]`` constraint documented in
# ``app/admin/router.py`` and ``app/markets/router.py`` (forward-ref strings make
# the dependency resolver mis-read params as query params -> 422).
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.csv_export import build_bets_csv, build_transactions_csv, build_users_csv
from app.admin.service import AdminUserService
from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session

admin_export_router = APIRouter(prefix="/api/v1/admin/export", tags=["admin-export"])


def _csv_response(content: str, filename: str) -> Response:
    """Build a ``text/csv`` attachment response with the given filename."""
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_export_router.get("/users")
async def export_users(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    search: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(active|banned)$"),
    signup_after: datetime | None = Query(default=None),
    signup_before: datetime | None = Query(default=None),
) -> Response:
    """Export the filtered user list as ``users.csv`` (D-08/D-09)."""
    rows = await AdminUserService.export_users(
        session,
        search=search,
        status=status,
        signup_after=signup_after,
        signup_before=signup_before,
    )
    return _csv_response(build_users_csv(rows), "users.csv")


@admin_export_router.get("/transactions")
async def export_transactions(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    user_id: UUID | None = Query(default=None),
) -> Response:
    """Export wallet transactions as ``transactions.csv`` (D-08/D-09).

    Optional ``user_id`` scopes the export to a single user's wallet.
    """
    rows = await AdminUserService.export_transactions(session, user_id=user_id)
    return _csv_response(build_transactions_csv(rows), "transactions.csv")


@admin_export_router.get("/bets")
async def export_bets(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    user_id: UUID | None = Query(default=None),
) -> Response:
    """Export bets as ``bets.csv`` (D-08/D-09).

    Optional ``user_id`` scopes the export to a single user's bets.
    """
    rows = await AdminUserService.export_bets(session, user_id=user_id)
    return _csv_response(build_bets_csv(rows), "bets.csv")


__all__ = ["admin_export_router"]
