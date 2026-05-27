"""POST /auth/logout — AUTH-05 token revocation."""

from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import text

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


async def test_logout_revokes_token(engine: "AsyncEngine") -> None:
    """POST /auth/logout sets revoked_at on the matching refresh_tokens row."""
    email = "logout@example.com"
    password = "Valid-Pass-1234"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        await _register_and_verify(client, engine, email, password)
        login = await client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        assert login.status_code in (200, 204), login.text

        # One active refresh_tokens row.
        async with engine.connect() as conn:
            uid_row = (
                await conn.execute(
                    text("SELECT id FROM users WHERE email = :em"),
                    {"em": email},
                )
            ).first()
            assert uid_row is not None
            uid = uid_row[0]
            active = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM refresh_tokens "
                        "WHERE user_id = :uid AND revoked_at IS NULL"
                    ),
                    {"uid": uid},
                )
            ).scalar()
            assert active == 1

        # Confirm authenticated before logout.
        me = await client.get("/auth/users/me")
        assert me.status_code == 200

        # POST /auth/logout.
        out = await client.post("/auth/logout")
        assert out.status_code in (200, 204), out.text

        # Token row is revoked.
        async with engine.connect() as conn:
            still_active = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM refresh_tokens "
                        "WHERE user_id = :uid AND revoked_at IS NULL"
                    ),
                    {"uid": uid},
                )
            ).scalar()
            assert still_active == 0

        # Next API call with stale cookie returns 401.
        me_after = await client.get("/auth/users/me")
        assert me_after.status_code == 401

    await _cleanup_user(engine, email)
