"""Player-authed live-bets surface (v1.3, LB-A) — routes under ``/api/live``.

Mirrors ``app/bets/router.py``: cookie-gated routes that mint a live-bets session,
list tables, and mirror placed/settled bets into the XPredict ledger via
``LiveBetsBridge``. Every route depends on ``current_active_player`` (401 when
unauthenticated, 403 when unverified) — the same gate as the bets surface (T-LBA-03).

# Note on ``from __future__ import annotations`` (intentionally ABSENT): FastAPI's
# dependency resolver on Python 3.13 mis-reads ``Annotated[T, Depends(...)]`` as a
# query param when annotations are forward-ref strings -> 422. ``User`` /
# ``AsyncSession`` MUST be runtime imports. Same constraint documented in
# ``app/bets/router.py`` + ``app/wallet/router.py``.

A ``get_livebets_client()`` dependency returns the ``LiveBetsClient`` so tests
override it via ``app.dependency_overrides`` (mirrors ``get_market_source`` in the
bets router) and never hit the network.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_player
from app.auth.models import User
from app.core.config import get_settings
from app.db.session import get_async_session
from app.integrations.livebets.client import LiveBetsClient
from app.integrations.livebets.schemas import (
    MirrorResult,
    SessionResponse,
    TableItem,
    TablesResponse,
)
from app.integrations.livebets.service import (
    LiveBetsBridge,
    LiveBetsOwnershipError,
    LiveBetsVerificationError,
)

livebets_router = APIRouter(prefix="/api/live", tags=["livebets"])


class SessionRequest(BaseModel):
    """Body for ``POST /api/live/session`` — optional table override."""

    table_id: str | None = None


def get_livebets_client() -> LiveBetsClient:
    """The live-bets client used by the routes.

    Tests override this with a fake via ``app.dependency_overrides`` (mirrors
    ``get_market_source`` in the bets router) so they never hit the network.
    """
    return LiveBetsClient()


@livebets_router.post("/session", response_model=SessionResponse)
async def mint_session(
    body: SessionRequest,
    player: Annotated[User, Depends(current_active_player)],
    client: Annotated[LiveBetsClient, Depends(get_livebets_client)],
) -> SessionResponse:
    """Mint (or renew) a live-bets session for the current player.

    ``player_ref`` is the XPredict user id (design §7). The table defaults to
    ``settings.LIVEBETS_DEFAULT_TABLE_ID`` when the body omits one; 400 if both unset.
    """
    table_id = body.table_id or get_settings().LIVEBETS_DEFAULT_TABLE_ID
    if not table_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No table_id supplied and LIVEBETS_DEFAULT_TABLE_ID is not configured.",
        )
    result = await client.mint_session(player_ref=str(player.id), table_id=table_id)
    return SessionResponse(
        session_token=str(result["session_token"]),
        expires_at=str(result["expires_at"]),
    )


@livebets_router.get("/tables", response_model=TablesResponse)
async def list_tables(
    player: Annotated[User, Depends(current_active_player)],
    client: Annotated[LiveBetsClient, Depends(get_livebets_client)],
) -> TablesResponse:
    """List the live-bets catalog tables available for the demo."""
    raw = await client.list_tables()
    return TablesResponse(tables=[TableItem.model_validate(t) for t in raw])


@livebets_router.post("/bets/{bet_id}/placed", response_model=MirrorResult)
async def record_placed(
    bet_id: UUID,
    player: Annotated[User, Depends(current_active_player)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    client: Annotated[LiveBetsClient, Depends(get_livebets_client)],
) -> MirrorResult:
    """Mirror a placed live-bets bet — debit the player's wallet into escrow (stake).

    Server-side verified + idempotent (``LiveBetsBridge.record_placed``). A
    verification failure maps to 409; an ownership mismatch and a missing wallet both
    map to 404 (mirrors the bets router's exception mapping; 404 for ownership keeps
    a foreign bet's existence hidden — IDOR-safe, BL-01).
    """
    try:
        return await LiveBetsBridge.record_placed(
            session, user=player, bet_id=bet_id, client=client
        )
    except LiveBetsOwnershipError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bet not found.") from exc
    except LiveBetsVerificationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except NoResultFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found.") from exc


@livebets_router.post("/bets/{bet_id}/settled", response_model=MirrorResult)
async def record_settled(
    bet_id: UUID,
    player: Annotated[User, Depends(current_active_player)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    client: Annotated[LiveBetsClient, Depends(get_livebets_client)],
) -> MirrorResult:
    """Mirror a settled live-bets bet (WON/LOST/REFUNDED/VOIDED) into the ledger.

    Server-side verified + idempotent (``LiveBetsBridge.record_settled``). Same
    exception mapping as the placed route: an ownership mismatch maps to 404 (a
    non-owner settling a bet is treated as not-found to avoid leaking the bet's
    existence — IDOR-safe, BL-01), a verification failure to 409, a missing wallet
    to 404.
    """
    try:
        return await LiveBetsBridge.record_settled(
            session, user=player, bet_id=bet_id, client=client
        )
    except LiveBetsOwnershipError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bet not found.") from exc
    except LiveBetsVerificationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except NoResultFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found.") from exc


__all__ = ["get_livebets_client", "livebets_router"]
