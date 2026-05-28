"""Player wallet read surface (Phase 3, Plan 03-05) — WAL-03 balance, WAL-04 history.

Two cookie-gated, strictly self-scoped read endpoints:

- ``GET /wallet/me/balance``      → the caller's wallet balance (WAL-03).
- ``GET /wallet/me/transactions`` → a page of the caller's history (WAL-04).

**T-03-18 (cross-user read) — structurally impossible.** Both routes depend on
``current_active_player`` (the Phase 2 cookie gate: ``active=True, verified=True``)
and there is **no ``user_id`` path/query parameter**. The wallet read is always
``player.id``'s own wallet — a client cannot name another user's wallet on the
wire, and the service queries are scoped by the authenticated id. An
unauthenticated request never reaches the handler (the dependency returns 401).

**SC#4 — money is a JSON string.** ``BalanceResponse`` / ``TransactionItem`` use
``MoneyStr`` (``Annotated[Decimal, PlainSerializer(str)]``), so ``balance`` and
every ``amount`` serialize as quoted strings, never floats.

The reads delegate to ``WalletService.get_balance`` / ``get_transactions`` (the
read-only seam established in 03-02 + extended here). If a player somehow has no
wallet (registration guarantees one, SC#1), the handlers return a defensive
balance ``"0"`` / an empty page rather than a 500.

# Note on ``from __future__ import annotations`` (intentionally absent):
# FastAPI's ``inspect.signature`` dependency resolver on Python 3.13 breaks when
# ``Annotated[T, Depends(...)]`` annotations become forward-ref strings — the
# injected ``player`` / ``session`` params get mis-resolved as query params (422
# "Field required"). ``User`` / ``AsyncSession`` must therefore be RUNTIME
# imports, not ``TYPE_CHECKING``-only. Same constraint as ``admin_router.py``
# (Plan 02-02 D-C / 03-04).
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_player
from app.auth.models import User
from app.db.session import get_async_session
from app.wallet.constants import PLAY_USD
from app.wallet.schemas import (
    BalanceResponse,
    TransactionItem,
    TransactionPage,
)
from app.wallet.service import WalletService

wallet_router = APIRouter(prefix="/wallet/me", tags=["wallet"])


@wallet_router.get("/balance", response_model=BalanceResponse)
async def read_balance(
    player: Annotated[User, Depends(current_active_player)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BalanceResponse:
    """Return the authenticated player's own wallet balance (WAL-03 / SC#4).

    Self-scoped by ``player.id`` — there is NO ``user_id`` parameter, so a
    cross-user read is impossible (T-03-18). Money serializes as a JSON string.
    """
    try:
        balance: Decimal = await WalletService.get_balance(
            session, user_id=player.id
        )
    except NoResultFound:
        # Defensive: registration co-creates the wallet (SC#1), so this should
        # not happen; surface a zero balance rather than a 500.
        balance = Decimal("0")
    return BalanceResponse(balance=balance, currency=PLAY_USD)


@wallet_router.get("/transactions", response_model=TransactionPage)
async def read_transactions(
    player: Annotated[User, Depends(current_active_player)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TransactionPage:
    """Return a page of the authenticated player's own history (WAL-04 / SC#4).

    Offset pagination (newest first) over the caller's wallet entries. Strictly
    self-scoped by ``player.id`` (no ``user_id`` parameter — T-03-18). Each
    item's ``amount`` is a JSON string (SC#4); ``reason`` comes from the
    transfer metadata (may be ``null``).
    """
    try:
        rows, total = await WalletService.get_transactions(
            session, user_id=player.id, page=page, page_size=page_size
        )
    except NoResultFound:
        # Defensive empty page — see read_balance.
        rows, total = [], 0

    items = [
        TransactionItem(
            kind=row.kind,
            amount=row.amount,
            direction=row.direction,
            created_at=row.created_at,
            reason=(row.metadata or {}).get("reason"),
        )
        for row in rows
    ]
    has_next = page * page_size < total
    return TransactionPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        has_next=has_next,
    )
