"""Admin settlement surface (Phase 5, SC#5 + SC#8) — resolve & reverse a market.

Two admin-Bearer-gated endpoints that drive the transactional ``SettlementService``:

- ``POST /admin/markets/{market_id}/resolve`` — settle a market on a winning outcome with a
  mandatory justification (SC#5). The two-step "propose + confirm" flow is a client concern;
  this endpoint receives the CONFIRMED resolution and runs ``resolve_market`` (one ACID tx:
  payouts + market RESOLVED + audit).
- ``POST /admin/markets/{market_id}/reverse`` — reverse a settlement via compensating entries
  with a mandatory justification (SC#8).

Phase 4's market write side is consumed ONLY through ``MarketResolvePort``, injected via
``get_market_resolver`` (``None`` until the Phase 4 adapter is wired at integration -> 503;
tests override it with a fake).

# ``from __future__ import annotations`` intentionally ABSENT — FastAPI 3.13 Annotated-Depends
# gotcha (see app/wallet/admin_router.py). ``User`` / ``AsyncSession`` are runtime imports.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session
from app.settlement.market_port import MarketResolvePort
from app.settlement.schemas import (
    ResolveMarketRequest,
    ResolveMarketResponse,
    ReverseSettlementRequest,
    ReverseSettlementResponse,
)
from app.settlement.service import SettlementService

settlement_admin_router = APIRouter(prefix="/admin/markets", tags=["admin-settlement"])


def get_market_resolver() -> MarketResolvePort | None:
    """The market write port used to flip market status during settle/reverse.

    Returns ``None`` until Phase 4's market service is wired here at integration (then this
    returns the adapter); the endpoints respond 503 while unwired. Tests override it.
    """
    return None


@settlement_admin_router.post("/{market_id}/resolve", response_model=ResolveMarketResponse)
async def resolve_market(
    market_id: UUID,
    body: ResolveMarketRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolver: Annotated[MarketResolvePort | None, Depends(get_market_resolver)],
) -> ResolveMarketResponse:
    """Resolve ``market_id`` on the confirmed winning outcome (admin-only, SC#5)."""
    if resolver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Settlement is not available yet.",
        )
    # Capture the admin id as a plain value BEFORE the service's begin()/commit churns the
    # session (would expire the dependency-loaded admin -> MissingGreenlet). Then clear any
    # autobegun read tx (the admin lookup) so resolve_market can open its own unit of work.
    admin_id = admin.id
    await session.rollback()

    try:
        plan = await SettlementService.resolve_market(
            session,
            market_id=market_id,
            winning_outcome_id=body.winning_outcome_id,
            market_resolver=resolver,
            justification=body.justification,
            actor_user_id=admin_id,
        )
    except NoResultFound as exc:
        # A market with pending bets but no liability account cannot occur; defensive.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market or its ledger account not found.",
        ) from exc

    return ResolveMarketResponse(
        market_id=market_id,
        winning_outcome_id=body.winning_outcome_id,
        bets_settled=len(plan.settled),
        total_payout=plan.total_payout,
        total_loser_stake=plan.total_loser_stake,
    )


@settlement_admin_router.post("/{market_id}/reverse", response_model=ReverseSettlementResponse)
async def reverse_settlement(
    market_id: UUID,
    body: ReverseSettlementRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolver: Annotated[MarketResolvePort | None, Depends(get_market_resolver)],
) -> ReverseSettlementResponse:
    """Reverse ``market_id``'s settlement via compensating entries (admin-only, SC#8)."""
    if resolver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Settlement is not available yet.",
        )
    admin_id = admin.id
    await session.rollback()

    try:
        reversed_count = await SettlementService.reverse_settlement(
            session,
            market_id=market_id,
            market_resolver=resolver,
            justification=body.justification,
            actor_user_id=admin_id,
        )
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market or its ledger account not found.",
        ) from exc

    return ReverseSettlementResponse(market_id=market_id, bets_reversed=reversed_count)


__all__ = ["get_market_resolver", "settlement_admin_router"]
