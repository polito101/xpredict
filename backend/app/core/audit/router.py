"""Audit-log viewer router (Phase 8, Plan 08-02, ADD-04).

A strictly READ-ONLY admin surface over the append-only ``audit_log`` table
(D-11) — the operator's "everything is recorded and immutable" trust signal
(PITFALL #6). Only GET endpoints exist here (T-08-07); there is deliberately no
POST/PUT/PATCH/DELETE. Immutability is also enforced at the DB layer (BEFORE
UPDATE/DELETE trigger + REVOKE from Phase 1), so even a future bug cannot mutate
a row through this service.

Endpoints (admin-Bearer-gated — no Bearer 401, player Bearer 403):

  - ``GET /``             paginated, filterable audit entries (newest first)
  - ``GET /event-types``  the D-13 known-event-type list for the filter dropdown

Filters on ``GET /`` (D-11): ``event_type`` (exact match), ``actor`` (ILIKE
substring with wildcard escape — T-08-08, same guard as the user search),
``date_from`` / ``date_to`` (``occurred_at`` range). Default ``page_size`` is 50
(audit logs are inspected in detail — CONTEXT discretion).

# ``from __future__ import annotations`` is intentionally ABSENT — same FastAPI
# + Python 3.13 ``Annotated[T, Depends(...)]`` constraint documented in
# ``app/admin/router.py`` / ``app/markets/router.py``.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import PaginatedResponse, paginated_response
from app.admin.service import _escape_like
from app.auth.deps import current_active_admin
from app.auth.models import User
from app.core.audit.models import AuditLog
from app.core.audit.schemas import KNOWN_EVENT_TYPES, AuditLogItem
from app.db.session import get_async_session

audit_admin_router = APIRouter(prefix="/api/v1/admin/audit-log", tags=["admin-audit"])


@audit_admin_router.get("", response_model=PaginatedResponse[AuditLogItem])
async def list_audit_log(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    event_type: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> PaginatedResponse[AuditLogItem]:
    """Return one page of audit entries, newest first (D-11).

    ``event_type`` is an exact match; ``actor`` is a wildcard-escaped ILIKE
    substring (T-08-08); ``date_from`` / ``date_to`` bound ``occurred_at``.
    """
    base = select(AuditLog)
    if event_type:
        base = base.where(AuditLog.event_type == event_type)
    if actor:
        pattern = f"%{_escape_like(actor)}%"
        base = base.where(AuditLog.actor.ilike(pattern, escape="\\"))
    if date_from is not None:
        base = base.where(AuditLog.occurred_at >= date_from)
    if date_to is not None:
        base = base.where(AuditLog.occurred_at <= date_to)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    items_stmt = (
        base.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(items_stmt)).scalars().all()

    items = [
        AuditLogItem(
            id=row.id,
            occurred_at=row.occurred_at,
            event_type=row.event_type,
            actor=row.actor,
            payload=row.payload,
            # ``ip`` is an INET column — asyncpg may hand back an ipaddress
            # object; normalise to a plain string for the JSON contract.
            ip=str(row.ip) if row.ip is not None else None,
        )
        for row in rows
    ]
    return paginated_response(items, int(total), page, page_size)


@audit_admin_router.get("/event-types", response_model=list[str])
async def list_event_types(
    admin: Annotated[User, Depends(current_active_admin)],
) -> list[str]:
    """Return the D-13 known event types for the frontend filter dropdown."""
    return KNOWN_EVENT_TYPES


__all__ = ["audit_admin_router"]
