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
from app.core.audit.service import AuditService
from app.db.session import get_async_session
from app.integrations.polymarket.client import GammaClient
from app.markets.enums import MarketSourceEnum
from app.markets.models import Market
from app.settlement.adapters import HouseMarketResolveAdapter
from app.settlement.market_port import MarketResolvePort
from app.settlement.schemas import (
    ForceSettleRequest,
    ForceSettleResponse,
    ResolveMarketRequest,
    ResolveMarketResponse,
    ReverseSettlementRequest,
    ReverseSettlementResponse,
)
from app.settlement.service import SettlementService

settlement_admin_router = APIRouter(prefix="/admin/markets", tags=["admin-settlement"])


def get_market_resolver() -> MarketResolvePort:
    """The market write port used to flip market status during settle/reverse.

    Wired (integration) to Phase 4's market domain via :class:`HouseMarketResolveAdapter`,
    which writes on the SETTLEMENT session so the status flip commits atomically with the
    payouts + audit. Tests override it with a fake via ``app.dependency_overrides``.
    """
    return HouseMarketResolveAdapter()


@settlement_admin_router.post("/{market_id}/resolve", response_model=ResolveMarketResponse)
async def resolve_market(
    market_id: UUID,
    body: ResolveMarketRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolver: Annotated[MarketResolvePort, Depends(get_market_resolver)],
) -> ResolveMarketResponse:
    """Resolve ``market_id`` on the confirmed winning outcome (admin-only, SC#5)."""
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
    resolver: Annotated[MarketResolvePort, Depends(get_market_resolver)],
) -> ReverseSettlementResponse:
    """Reverse ``market_id``'s settlement via compensating entries (admin-only, SC#8)."""
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


def get_gamma_client() -> GammaClient:
    """Dependency providing a GammaClient for the force-settle endpoint."""
    return GammaClient()


@settlement_admin_router.post("/{market_id}/force-settle", response_model=ForceSettleResponse)
async def force_settle_polymarket_market(
    market_id: UUID,
    body: ForceSettleRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolver: Annotated[MarketResolvePort, Depends(get_market_resolver)],
    gamma_client: Annotated[GammaClient, Depends(get_gamma_client)],
) -> ForceSettleResponse:
    """Force-settle a stuck Polymarket-mirrored market (admin-only, ADM-06).

    Distinct from /resolve: writes a polymarket_admin_override audit entry
    capturing the live Gamma umaResolutionStatus at override time.
    """
    # Capture admin id before rollback expiry and clear the autobegun read tx.
    admin_id = admin.id
    await session.rollback()

    market = await session.get(Market, market_id)
    if market is None or market.source != MarketSourceEnum.POLYMARKET.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found or not a Polymarket market.",
        )

    # Snapshot the current Gamma UMA status for the audit record (T-07-10).
    current = await gamma_client.fetch_market_by_id(market.source_market_id or "")
    await gamma_client.close()
    uma_status_at_override: str | None = (current or {}).get("umaResolutionStatus")  # type: ignore[assignment]

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market or its ledger account not found.",
        ) from exc

    # Write the override audit row in a SEPARATE transaction AFTER settlement commits
    # (action-THEN-audit, T-07-10 / constraint 14).
    async with session.begin():
        await AuditService.record(
            session,
            actor=f"user:{admin_id}",
            event_type="polymarket_admin_override",
            payload={
                "market_id": str(market_id),
                "winning_outcome_id": str(body.winning_outcome_id),
                "justification": body.justification,
                "uma_status_at_override_time": uma_status_at_override,
                "admin_id": str(admin_id),
            },
        )

    return ForceSettleResponse(
        market_id=market_id,
        winning_outcome_id=plan.winning_outcome_id,
        bets_settled=len(plan.settled),
        total_payout=plan.total_payout,
        total_loser_stake=plan.total_loser_stake,
        uma_status_at_override=uma_status_at_override,
    )


__all__ = ["get_market_resolver", "settlement_admin_router"]
