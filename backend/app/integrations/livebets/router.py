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

from collections.abc import AsyncIterator, Generator
from contextlib import contextmanager
from typing import Annotated, cast
from uuid import UUID

import structlog
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_player
from app.auth.models import User
from app.core.config import get_settings
from app.wallet.exceptions import InsufficientBalance
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

log = structlog.get_logger()

livebets_router = APIRouter(prefix="/api/live", tags=["livebets"])


@contextmanager
def _handle_bridge_errors() -> Generator[None, None, None]:
    """Map live-bets bridge/network errors to HTTP exceptions.

    RuntimeError       → 503 (service not configured)
    HTTPStatusError    → 502 (upstream returned an error response)
    NetworkError /
    TimeoutException   → 504 (service unreachable / timed out)
    """
    try:
        yield
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Live-bets service is not configured.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Live-bets upstream error ({exc.response.status_code}).") from exc
    except (httpx.NetworkError, httpx.TimeoutException) as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Live-bets service unavailable.") from exc


@contextmanager
def _handle_bet_mirror_errors(bet_id: UUID) -> Generator[None, None, None]:
    """Map bet-mirror bridge errors to HTTP exceptions.

    LiveBetsOwnershipError    → 404 (IDOR-safe, hides existence of foreign bets)
    LiveBetsVerificationError → 409 (bet in wrong state, generic message)
    ValueError                → 409 (malformed upstream response, generic message)
    NoResultFound             → 404 (wallet not found)
    InsufficientBalance       → 402
    """
    try:
        yield
    except LiveBetsOwnershipError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bet not found.") from exc
    except LiveBetsVerificationError as exc:
        log.warning("livebets.verification_error", detail=str(exc))
        raise HTTPException(status.HTTP_409_CONFLICT, "Bet cannot be mirrored in its current state.") from exc
    except ValueError as exc:
        log.warning("livebets.parse_error", bet_id=str(bet_id))
        raise HTTPException(status.HTTP_409_CONFLICT, "Bet cannot be verified.") from exc
    except NoResultFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found.") from exc
    except InsufficientBalance as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc


class SessionRequest(BaseModel):
    """Body for ``POST /api/live/session`` — optional table override."""

    table_id: str | None = None


async def get_livebets_client() -> AsyncIterator[LiveBetsClient]:
    """The live-bets client used by the routes.

    Tests override this with a fake via ``app.dependency_overrides`` (mirrors
    ``get_market_source`` in the bets router) so they never hit the network.
    """
    client = LiveBetsClient()
    try:
        yield client
    finally:
        await client.close()


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
    with _handle_bridge_errors():
        result = await client.mint_session(player_ref=str(player.id), table_id=table_id)
    session_token = result.get("session_token")
    expires_at = result.get("expires_at")
    if session_token is None or expires_at is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Live-bets returned an invalid session response.",
        )
    # Echo the resolved table_id back: the live-bets GET /tables route is JWT-gated
    # (player session), so XPredict's operator-key /api/live/tables can't list
    # tables — the frontend reads the widget's table-id from this field instead.
    return SessionResponse(
        session_token=str(session_token),
        expires_at=str(expires_at),
        table_id=table_id,
    )


@livebets_router.get("/tables", response_model=TablesResponse)
async def list_tables(
    player: Annotated[User, Depends(current_active_player)],
    client: Annotated[LiveBetsClient, Depends(get_livebets_client)],
) -> TablesResponse:
    """List the live-bets catalog tables available for the demo.

    The REAL ``GET /tables`` returns the envelope ``TableListResponse {tables:[...]}``
    (NOT a bare list), so unwrap the ``tables`` key before parsing. Each entry is a
    ``TableView`` whose id field is ``id``; ``TableItem`` maps it onto our outward
    ``table_id`` (the ``/api/live/tables`` contract to the frontend is unchanged).
    """
    with _handle_bridge_errors():
        raw = await client.list_tables()
    items = (raw.get("tables") or []) if isinstance(raw, dict) else raw
    try:
        return TablesResponse(tables=[TableItem.model_validate(t) for t in cast("list[object]", items)])
    except ValidationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Live-bets returned malformed table data.") from exc


@livebets_router.post("/bets/{bet_id}/placed", response_model=MirrorResult)
async def record_placed(
    bet_id: UUID,
    player: Annotated[User, Depends(current_active_player)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    client: Annotated[LiveBetsClient, Depends(get_livebets_client)],
    table_id: UUID | None = None,
) -> MirrorResult:
    """Mirror a placed live-bets bet — debit the player's wallet into escrow (stake).

    Server-side verified + idempotent (``LiveBetsBridge.record_placed``). A
    verification failure maps to 409; an ownership mismatch and a missing wallet both
    map to 404 (mirrors the bets router's exception mapping; 404 for ownership keeps
    a foreign bet's existence hidden — IDOR-safe, BL-01).

    ``table_id`` is an optional query parameter — the frontend passes the value it
    received from ``POST /api/live/session`` so the mirror row captures which table
    the bet was placed on (BetView has no ``table_id`` field, so it cannot be read
    from the live-bets verification response).
    """
    with _handle_bridge_errors(), _handle_bet_mirror_errors(bet_id):
        return await LiveBetsBridge.record_placed(
            session, user=player, bet_id=bet_id, client=client, table_id=table_id
        )


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
    with _handle_bridge_errors(), _handle_bet_mirror_errors(bet_id):
        return await LiveBetsBridge.record_settled(
            session, user=player, bet_id=bet_id, client=client
        )


__all__ = ["get_livebets_client", "livebets_router"]
