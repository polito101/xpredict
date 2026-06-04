"""Player bet surface (Phase 5, SC#1 + SC#2) — ``POST /bets``.

One cookie-gated endpoint that places a bet via the ACID ``BetService.place_bet``.

**SC#2 — 403 on unverified OR banned.** The route depends on ``current_betting_player``,
which layers a NOT-banned check on top of the Phase 2 ``current_active_player`` gate
(``active=True, verified=True``): an unauthenticated request is 401, an authenticated but
unverified one is 403 (fastapi-users), and a banned one (``banned_at`` set) is 403 here.

**The market seam.** Bet validation needs Phase 4's market domain, consumed ONLY through the
``MarketReadPort`` (``app/bets/market_port.py``). The concrete adapter (Phase 4 HouseAdapter)
is injected via ``get_market_source`` at integration; until then it returns ``None`` and the
endpoint responds 503. Tests override ``get_market_source`` with a stub.

# Note on ``from __future__ import annotations`` (intentionally ABSENT): FastAPI's
# ``inspect.signature`` dependency resolver on Python 3.13 mis-resolves
# ``Annotated[T, Depends(...)]`` when annotations are forward-ref strings (params get read as
# query params -> 422). ``User`` / ``AsyncSession`` must be RUNTIME imports. Same constraint
# documented in ``app/wallet/router.py`` + ``app/wallet/admin_router.py``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_player
from app.auth.models import User
from app.bets.adapters import HouseMarketReadAdapter
from app.bets.exceptions import InvalidOutcome, MarketClosed, MarketNotFound, StakeOutOfRange
from app.bets.market_port import MarketReadPort
from app.bets.schemas import (
    BetResponse,
    OpenPositionItem,
    PlaceBetRequest,
    PortfolioResponse,
    SettledPositionItem,
)
from app.bets.service import BetService
from app.db.session import get_async_session
from app.wallet.exceptions import InsufficientBalance

bets_router = APIRouter(prefix="/bets", tags=["bets"])


async def current_betting_player(
    player: Annotated[User, Depends(current_active_player)],
) -> User:
    """The Phase 2 active+verified cookie gate PLUS a not-banned check (SC#2).

    ``current_active_player`` already 401s an unauthenticated request and 403s an
    unverified one (fastapi-users ``verified=True``). A banned player can browse markets
    but is 403 here — they cannot place bets.
    """
    if player.banned_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is banned from placing bets.",
        )
    return player


def get_market_source() -> MarketReadPort:
    """The market read port used to validate the bet's market.

    Wired (integration) to Phase 4's market domain via :class:`HouseMarketReadAdapter`, which
    reads on its OWN session (the port contract — place_bet validates BEFORE its
    ``session.begin()``). Tests override this with an in-memory stub via
    ``app.dependency_overrides``.
    """
    return HouseMarketReadAdapter()


@bets_router.post("", response_model=BetResponse, status_code=status.HTTP_201_CREATED)
async def place_bet(
    body: PlaceBetRequest,
    player: Annotated[User, Depends(current_betting_player)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    market_source: Annotated[MarketReadPort, Depends(get_market_source)],
) -> BetResponse:
    """Place ``body.stake`` on ``body.outcome_id`` of ``body.market_id`` for the player.

    Gated to verified, non-banned players (SC#2). The placement is one ACID transaction
    (``BetService.place_bet``); domain errors map to 4xx (never a raw 500), and money/odds
    serialize as JSON strings (SC#4).

    Stake limits (BET-06) are enforced INSIDE ``place_bet`` (where the validated market is
    in hand) — it prefers the per-market ``min_stake`` / ``max_stake`` and falls back to the
    global ``BET_MIN_STAKE`` / ``BET_MAX_STAKE`` config; a violation surfaces as
    :class:`StakeOutOfRange` mapped to 422 here. (The former router-level global-only check
    is superseded — RESEARCH A4 — because the router does not load the market.)
    """
    try:
        bet = await BetService.place_bet(
            session,
            user_id=player.id,
            market_id=body.market_id,
            outcome_id=body.outcome_id,
            stake=body.stake,
            market_source=market_source,
        )
    except MarketNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except MarketClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidOutcome as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except StakeOutOfRange as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except InsufficientBalance as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc
    except NoResultFound as exc:
        # Defensive: the player has no wallet (registration guarantees one, SC#1).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found.") from exc

    # expire_on_commit=False (app session maker) keeps these populated post-commit.
    return BetResponse(
        bet_id=bet.id,
        market_id=bet.market_id,
        outcome_id=bet.outcome_id,
        stake=bet.stake,
        odds_at_placement=bet.odds_at_placement,
        status=bet.status,
    )


@bets_router.get("/me/portfolio", response_model=PortfolioResponse)
async def read_portfolio(
    player: Annotated[User, Depends(current_active_player)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PortfolioResponse:
    """Return the authenticated player's portfolio — open + settled positions (SC#7).

    Self-scoped by ``player.id`` (no ``user_id`` parameter). Open positions show the
    potential payout at the LOCKED odds; settled positions show the realized P&L. Money +
    odds serialize as JSON strings (SC#4). Read-only.
    """
    pf = await BetService.get_portfolio(session, user_id=player.id)
    return PortfolioResponse(
        open=[OpenPositionItem.model_validate(o) for o in pf.open],
        settled=[SettledPositionItem.model_validate(s) for s in pf.settled],
    )


@bets_router.post("/{bet_id}/sell")
async def sell_position(
    bet_id: UUID,
    player: Annotated[User, Depends(current_active_player)],
) -> None:
    """Selling a position is NOT supported in v1 (SC#3) — always 405.

    A bet is settled at market resolution; there is no secondary market / cash-out. The
    endpoint exists so the contract is explicit (405 Method Not Allowed) rather than a 404.
    """
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Selling a position is not supported; a bet is settled at market resolution.",
    )


__all__ = ["bets_router", "current_betting_player", "get_market_source"]
