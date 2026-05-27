"""POST /auth/forgot-password + /auth/reset-password — AUTH-06 + token_version bump."""

from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi_users.jwt import generate_jwt
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


async def _register_and_verify(
    client: httpx.AsyncClient,
    engine: "AsyncEngine",
    email: str,
    password: str,
) -> None:
    await client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE users SET is_verified = TRUE WHERE email = :em"),
            {"em": email},
        )
        await conn.commit()


async def _mint_reset_token(email: str) -> str:
    """Generate a JWT in the shape fastapi-users expects for reset."""
    sm = _get_session_maker()
    async with sm() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        user = await manager.get_by_email(email)
        # fastapi-users encodes the current password_fgpt; we use the same path.
        password_helper = manager.password_helper
        token_data = {
            "sub": str(user.id),
            "password_fgpt": password_helper.hash(user.hashed_password),
            "aud": "fastapi-users:reset",
        }
        return generate_jwt(
            data=token_data,
            secret=manager.reset_password_token_secret,
            lifetime_seconds=3600,
        )


async def test_reset_invalidates_sessions(engine: "AsyncEngine") -> None:
    """After reset, prior token_version is invalid + refresh_tokens revoked."""
    email = "reset-invalidates@example.com"
    password = "Valid-Pass-1234"
    new_password = "Brand-New-Pass-1!"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        await _register_and_verify(client, engine, email, password)
        await client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        # Snapshot token_version (=0) BEFORE reset.
        async with engine.connect() as conn:
            tv_before = (
                await conn.execute(
                    text("SELECT token_version FROM users WHERE email = :em"),
                    {"em": email},
                )
            ).scalar()
            assert tv_before == 0
            active_before = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM refresh_tokens rt "
                        "JOIN users u ON u.id = rt.user_id "
                        "WHERE u.email = :em AND rt.revoked_at IS NULL"
                    ),
                    {"em": email},
                )
            ).scalar()
            assert active_before == 1

        # Request reset (triggers forgot-password flow + audit row).
        fp = await client.post("/auth/forgot-password", json={"email": email})
        assert fp.status_code == 202

        # Mint a reset token (matches what would arrive via email).
        reset_token = await _mint_reset_token(email)

        rp = await client.post(
            "/auth/reset-password",
            json={"token": reset_token, "password": new_password},
        )
        assert rp.status_code == 200, rp.text

        # Post-reset: token_version bumped + active refresh_tokens revoked.
        async with engine.connect() as conn:
            tv_after = (
                await conn.execute(
                    text("SELECT token_version FROM users WHERE email = :em"),
                    {"em": email},
                )
            ).scalar()
            assert tv_after == tv_before + 1
            active_after = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM refresh_tokens rt "
                        "JOIN users u ON u.id = rt.user_id "
                        "WHERE u.email = :em AND rt.revoked_at IS NULL"
                    ),
                    {"em": email},
                )
            ).scalar()
            assert active_after == 0

    await _cleanup_user(engine, email)


async def test_audit_trail_on_reset(engine: "AsyncEngine") -> None:
    """Both auth.password_reset_requested + auth.password_reset_completed audit rows exist."""
    email = "reset-audit@example.com"
    password = "Valid-Pass-1234"
    new_password = "Audit-Pass-1!ABC"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        await _register_and_verify(client, engine, email, password)
        await client.post("/auth/forgot-password", json={"email": email})
        token = await _mint_reset_token(email)
        rp = await client.post(
            "/auth/reset-password",
            json={"token": token, "password": new_password},
        )
        assert rp.status_code == 200, rp.text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT event_type FROM audit_log "
                    "WHERE event_type IN "
                    "  ('auth.password_reset_requested', 'auth.password_reset_completed') "
                    "AND payload->>'email' = :em "
                    "ORDER BY occurred_at"
                ),
                {"em": email},
            )
        ).all()
        types = [r.event_type for r in rows]
        assert "auth.password_reset_requested" in types
        assert "auth.password_reset_completed" in types
    await _cleanup_user(engine, email)
