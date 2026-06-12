"""Admin surface for live-bets bridge operations (BL-01 recovery).

Provides the operator a recovery endpoint for orphaned PENDING mirror rows —
bets that are stuck because an attacker claimed them first (ownership mismatch).
"""

import types
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.db.session import get_async_session
from app.integrations.livebets.client import LiveBetsClient
from app.integrations.livebets.constants import LIVEBETS_PENDING
from app.integrations.livebets.models import LiveBetsBet
from app.integrations.livebets.router import (
    _handle_bet_mirror_errors,
    _handle_bridge_errors,
    get_livebets_client,
)
from app.integrations.livebets.schemas import MirrorResult, parse_verified_bet
from app.integrations.livebets.service import LiveBetsVerificationError, LiveBetsBridge

log = structlog.get_logger()

livebets_admin_router = APIRouter(prefix="/api/admin/livebets", tags=["livebets-admin"])


@livebets_admin_router.post(
    "/bets/{bet_id}/reconcile",
    response_model=MirrorResult,
)
async def reconcile_bet(
    bet_id: UUID,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    client: Annotated[LiveBetsClient, Depends(get_livebets_client)],
) -> MirrorResult:
    """Force-settle an orphaned PENDING mirror row (BL-01 recovery).

    An orphaned row occurs when an attacker claims a bet by calling record_placed
    first, binding user_id to their account. The legitimate owner then gets 404 on
    record_settled. Ops calls this endpoint to unlock the stuck bet.

    Workflow:
      1. Read the mirror row — 404 if absent.
      2. If already settled (non-PENDING), return current status (idempotent).
      3. Call live-bets GET /v2/bets/{id} to get the authoritative status.
      4. If live-bets says PENDING — 409 (cannot settle a still-pending bet).
      5. Otherwise force-settle through the normal bridge logic, using the mirror
         row's own user_id so the ownership check passes.
    """
    # 1. Read mirror row — 404 if absent.
    async with session.begin():
        mirror = (
            await session.execute(select(LiveBetsBet).where(LiveBetsBet.bet_id == bet_id))
        ).scalar_one_or_none()
    if mirror is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No mirror row found for this bet.")

    # 2. Already settled — idempotent no-op.
    if mirror.status != LIVEBETS_PENDING:
        log.info("livebets.reconcile.already_settled", bet_id=str(bet_id), status=mirror.status)
        return MirrorResult(bet_id=str(bet_id), status=mirror.status, applied=False)

    # 3. Get authoritative status from live-bets.
    try:
        raw = await client.get_bet(str(bet_id))
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Could not fetch bet status from live-bets.",
        ) from exc
    try:
        verified = parse_verified_bet(raw)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Live-bets returned malformed bet data.",
        ) from exc

    # 4. Still PENDING in live-bets — cannot settle yet.
    if verified.status == LIVEBETS_PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bet is still PENDING in live-bets; cannot reconcile yet.",
        )

    # 5. Force-settle using the mirror row's owner so the ownership check passes.
    log.warning(
        "livebets.reconcile.force_settle",
        bet_id=str(bet_id),
        mirror_owner=str(mirror.user_id),
        admin=str(admin.id),
        live_status=verified.status,
    )
    # Reuse record_settled with a minimal user stub that satisfies user.id check.
    # The type ignore is intentional: LiveBetsBridge uses only user.id at runtime.
    fake_user = types.SimpleNamespace(id=mirror.user_id)
    with _handle_bridge_errors(), _handle_bet_mirror_errors(bet_id):
        return await LiveBetsBridge.record_settled(
            session,
            user=fake_user,  # type: ignore[arg-type]
            bet_id=bet_id,
            client=client,
        )
