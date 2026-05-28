"""POST /auth/verify — AUTH-03 single-use email verification."""

from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import text

from app.auth.manager import UserManager
from app.auth.models import User
from app.db.session import _get_session_maker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def _cleanup_user(engine: "AsyncEngine", email: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()


async def _client_for_app() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _mint_verify_token(engine: "AsyncEngine", email: str) -> str:
    """Mint a fastapi-users verify token directly for the given user."""
    sm = _get_session_maker()
    async with sm() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        user = await manager.get_by_email(email)
        # Reach into the manager's protected helper (same one used by
        # /auth/request-verify-token internally).
        # Use fastapi-users' generate_verification_token by calling
        # request_verify which internally writes a JWT signed with
        # verification_token_secret. Easier: call _generate_verification_token
        # directly.
        from fastapi_users.jwt import generate_jwt

        return generate_jwt(
            data={"sub": str(user.id), "email": user.email, "aud": "fastapi-users:verify"},
            secret=manager.verification_token_secret,
            lifetime_seconds=3600,
        )


async def test_verify_single_use(engine: "AsyncEngine") -> None:
    """First POST /auth/verify with valid token returns 200; second returns 400."""
    email = "verify@example.com"
    password = "Valid-Pass-1234"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        # Register (still unverified — Mailpit is not reachable in tests).
        r = await client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
        assert r.status_code == 201, r.text

        token = await _mint_verify_token(engine, email)

        # First use — should mark verified.
        v1 = await client.post("/auth/verify", json={"token": token})
        assert v1.status_code == 200, v1.text
        body = v1.json()
        assert body.get("is_verified") in (True, None)  # fastapi-users default

        # DB confirms is_verified=True.
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT is_verified FROM users WHERE email = :em"),
                    {"em": email},
                )
            ).first()
            assert row is not None
            assert row.is_verified is True

        # Second use — fastapi-users returns 400 "already verified".
        v2 = await client.post("/auth/verify", json={"token": token})
        assert v2.status_code == 400

    await _cleanup_user(engine, email)


async def test_audit_email_verified_written(engine: "AsyncEngine") -> None:
    """Successful verify writes audit_log auth.email_verified."""
    email = "verify-audit@example.com"
    password = "Valid-Pass-1234"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        await client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
        token = await _mint_verify_token(engine, email)
        r = await client.post("/auth/verify", json={"token": token})
        assert r.status_code == 200, r.text

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM audit_log "
                    "WHERE event_type = 'auth.email_verified' "
                    "AND payload->>'email' = :em LIMIT 1"
                ),
                {"em": email},
            )
        ).first()
        assert row is not None, "auth.email_verified audit row missing"
    await _cleanup_user(engine, email)
