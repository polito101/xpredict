"""Sign-up bonus is granted on email verification (Phase 5, SC#4 / WAL-02).

End-to-end wiring proof, mirroring ``test_email_verification.py``: a registered
player has a wallet at balance 0 (the bonus is NOT a registration reward); after
``POST /auth/verify`` (which fires ``UserManager.on_after_verify``), the wallet
holds exactly the configured sign-up bonus and a transfer of ``kind=signup_bonus``
with ``idempotency_key=bonus:{user_id}`` exists.
"""

from __future__ import annotations

import contextlib
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi_users.jwt import generate_jwt
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import select, text

from app.auth.manager import UserManager
from app.auth.models import User
from app.core.config import get_settings
from app.db.session import _get_session_maker
from app.wallet.constants import (
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
    TRANSFER_SIGNUP_BONUS,
)
from app.wallet.models import Account, Transfer

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _reset_rate_limit_storage():
    """Clear slowapi's in-memory rate-limit storage before each test (register is 5/min/IP)."""
    from app.auth.rate_limit import limiter

    try:
        limiter._limiter.reset()
    except Exception:
        with contextlib.suppress(Exception):
            limiter._storage.reset()
    yield


async def _client() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _cleanup_user(engine: AsyncEngine, email: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()


async def _mint_verify_token(email: str) -> str:
    """Mint a fastapi-users verify JWT directly (Mailpit is not reachable in tests)."""
    sm = _get_session_maker()
    async with sm() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        user = await manager.get_by_email(email)
        return generate_jwt(
            data={
                "sub": str(user.id),
                "email": user.email,
                "aud": "fastapi-users:verify",
            },
            secret=manager.verification_token_secret,
            lifetime_seconds=3600,
        )


async def _user_id(email: str) -> UUID:
    sm = _get_session_maker()
    async with sm() as s:
        return (await s.execute(select(User.id).where(User.email == email))).scalar_one()


async def _wallet_balance(user_id: UUID) -> Decimal:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(
                select(Account.balance).where(
                    Account.owner_type == OWNER_USER,
                    Account.owner_id == user_id,
                    Account.kind == KIND_USER_WALLET,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one()


async def test_signup_bonus_credited_on_verification(engine: AsyncEngine) -> None:
    """Wallet is 0 at registration and equals SIGNUP_BONUS_AMOUNT after verify."""
    email = f"bonus-verify-{uuid.uuid4().hex[:8]}@example.com"
    bonus = get_settings().SIGNUP_BONUS_AMOUNT
    await _cleanup_user(engine, email)
    try:
        async with await _client() as client:
            r = await client.post(
                "/auth/register",
                json={"email": email, "password": "Valid-Pass-1234"},
            )
            assert r.status_code == 201, r.text
            user_id = await _user_id(email)

            # At registration (before verify) the wallet exists at balance 0 —
            # the bonus is a VERIFICATION reward, not a registration one.
            assert await _wallet_balance(user_id) == Decimal("0")

            token = await _mint_verify_token(email)
            v = await client.post("/auth/verify", json={"token": token})
            assert v.status_code == 200, v.text

        # After verification the wallet holds exactly the configured bonus.
        assert await _wallet_balance(user_id) == bonus

        # A signup_bonus transfer with the per-user idempotency key exists.
        sm = _get_session_maker()
        async with sm() as s:
            transfer = (
                await s.execute(
                    select(Transfer).where(Transfer.idempotency_key == f"bonus:{user_id}")
                )
            ).scalar_one()
        assert transfer.kind == TRANSFER_SIGNUP_BONUS
    finally:
        await _cleanup_user(engine, email)
