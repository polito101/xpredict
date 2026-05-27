"""Admin wallet surface — the recharge primitive (Phase 3, Plan 03-04).

``POST /admin/wallets/{user_id}/recharge`` is the FIRST money-moving endpoint:
it debits ``house_promo`` and credits the path user's wallet via
``WalletService.recharge`` (the validated race-safe / idempotent engine from
Plan 03-02), behind the Phase 2 admin Bearer gate (``current_active_admin``).

Key invariants this surface enforces:
  - **Admin-only (T-03-13 / AUTH-07):** ``Depends(current_active_admin)`` — a
    valid Bearer for a ``is_superuser`` user. A player cookie or no auth → 401/403.
  - **Idempotent (SC#3 / T-03-14):** the client supplies an ``Idempotency-Key``
    header (a missing key is a 400 — Assumption A3). ``WalletService.recharge``
    dedups a replayed key via the ``transfers.idempotency_key`` UNIQUE / 23505
    path and returns the existing transfer — no double-credit. We detect the
    replay with a pre-read so the response can flag ``idempotent_replay``.
  - **No user-to-user (SC#5 / WAL-09):** the only credit destination is the path
    user's own wallet; the debit source is the house, chosen server-side. The
    ``RechargeRequest`` schema (``extra="forbid"``) rejects any ``dst_user_id``.
  - **Audited (T-03-17):** every admin money action writes a ``wallet.recharge``
    audit row (PITFALLS admin-actions checklist).

# Note on ``from __future__ import annotations`` (intentionally absent):
# FastAPI's ``inspect.signature`` dependency resolver on Python 3.13 breaks when
# ``Annotated[T, Depends(...)]`` / ``Header()`` annotations become forward-ref
# strings. Same constraint as ``app/auth/admin_router.py`` (Plan 02-02 D-C).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.core.audit.service import AuditService
from app.db.session import get_async_session
from app.wallet.constants import PLAY_USD
from app.wallet.exceptions import InsufficientBalance
from app.wallet.models import Transfer
from app.wallet.schemas import RechargeRequest, RechargeResponse
from app.wallet.service import PROVIDER_HOUSE, WalletService

wallet_admin_router = APIRouter(prefix="/admin/wallets", tags=["admin-wallet"])


@wallet_admin_router.post("/{user_id}/recharge", response_model=RechargeResponse)
async def recharge_wallet(
    user_id: UUID,
    body: RechargeRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> RechargeResponse:
    """Credit ``user_id``'s wallet by ``body.amount`` from the house (admin-only).

    Returns 200 with the transfer id + ``amount`` as a JSON string. A second call
    with the same ``Idempotency-Key`` returns the SAME transfer id with
    ``idempotent_replay=True`` and no double-credit (SC#3).
    """
    # A3 — the client MUST supply the idempotency key (we don't server-generate).
    if idempotency_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )

    # Capture the admin id as a plain value NOW. The pre-read ``rollback()`` and
    # ``recharge``'s own ``begin()``/commit churn the request session's
    # transaction state, which expires ORM instances loaded earlier (the
    # ``admin`` object came from the ``current_active_admin`` dependency on this
    # same session). Touching ``admin.id`` after that would trigger a lazy reload
    # — IO outside the async greenlet → ``MissingGreenlet``. Read it once, up front.
    admin_id = admin.id

    # Detect a replay BEFORE the write so the response can flag it. The service
    # itself is the source of truth for dedup (23505 → return existing); this
    # read only shapes the ``idempotent_replay`` boolean.
    #
    # IMPORTANT: this SELECT autobegins an implicit transaction on the request
    # session. ``WalletService.recharge`` opens its OWN ``session.begin()`` unit
    # of work, which raises ``InvalidRequestError`` if a transaction is already
    # open — so we ``rollback()`` the (read-only, data-free) autobegun tx to hand
    # ``recharge`` a clean session. Same autobegin nuance the 03-02 service hit.
    pre_existing = (
        await session.execute(
            select(Transfer.id).where(Transfer.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    await session.rollback()

    try:
        # ``recharge`` owns its own ``session.begin()`` unit of work: the transfer
        # row + both entries + both balance updates commit atomically (the
        # money-correctness invariant). It debits ``house_promo`` and credits the
        # path user's wallet — there is no user-to-user path.
        transfer = await WalletService.recharge(
            session,
            user_id=user_id,
            amount=body.amount,
            reason=body.reason,
            idempotency_key=idempotency_key,
            payment_provider=PROVIDER_HOUSE,
        )
    except NoResultFound as exc:
        # The target user has no wallet (or no such user).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user wallet not found.",
        ) from exc
    except InsufficientBalance as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        # Defense-in-depth: a non-positive / invalid amount that slips past the
        # schema, or an unknown payment provider.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    idempotent_replay = pre_existing is not None
    # Capture the transfer id as a plain value before the audit commit — the
    # commit below would otherwise force a lazy reload of the (post-begin)
    # ``transfer`` instance during response construction (same MissingGreenlet
    # trap as ``admin.id`` above).
    transfer_id = transfer.id

    # Audit every admin money action (T-03-17 / PITFALLS admin-actions). The
    # transfer is already committed by ``recharge``; this audit row is written on
    # the request session and committed here — mirroring the auth surface's
    # action-then-audit pattern (``app/auth/admin_router.py``). A replay still
    # records the (idempotent) admin intent.
    await AuditService.record(
        session,
        actor=f"user:{admin_id}",
        event_type="wallet.recharge",
        payload={
            "target_user_id": str(user_id),
            "amount": str(body.amount),
            "idempotency_key": idempotency_key,
            "idempotent_replay": idempotent_replay,
        },
    )
    await session.commit()

    return RechargeResponse(
        transfer_id=transfer_id,
        amount=body.amount,
        currency=PLAY_USD,
        idempotent_replay=idempotent_replay,
    )


__all__ = ["wallet_admin_router"]
