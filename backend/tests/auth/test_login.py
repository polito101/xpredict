"""POST /auth/login — AUTH-04 cookie session + persistence."""

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


async def _register(
    client: httpx.AsyncClient,
    email: str,
    password: str,
    verified: bool = True,
) -> str:
    """Register a user; return its id. Optionally bump is_verified."""
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _set_verified(engine: "AsyncEngine", email: str, verified: bool = True) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE users SET is_verified = :v WHERE email = :em"),
            {"v": verified, "em": email},
        )
        await conn.commit()


async def _cleanup_user(engine: "AsyncEngine", email: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()


async def _client_for_engine() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_cookie_set_and_persists(engine: "AsyncEngine") -> None:
    """Login sets xpredict_session cookie; subsequent /auth/users/me returns the user."""
    email = "login-cookie@example.com"
    password = "Valid-Pass-1234"
    await _cleanup_user(engine, email)
    async with await _client_for_engine() as client:
        await _register(client, email, password)
        # Mark as verified so /auth/users/me (verified=True gate) accepts.
        await _set_verified(engine, email, True)

        resp = await client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        assert resp.status_code in (200, 204), resp.text
        # Pitfall 3: Secure=False in dev (is_dev=True).
        set_cookie = resp.headers.get("set-cookie", "")
        assert "xpredict_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()
        # Dev path: Secure flag MUST be absent.
        assert "Secure" not in set_cookie

        # The cookie persists — next call to /auth/users/me returns 200.
        me = await client.get("/auth/users/me")
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["email"] == email
        assert "is_superuser" not in body
    await _cleanup_user(engine, email)


async def test_unverified_user_blocked_on_protected(engine: "AsyncEngine") -> None:
    """Unverified user can login but protected routes (verified=True) return 403/401."""
    email = "unver-block@example.com"
    password = "Valid-Pass-1234"
    await _cleanup_user(engine, email)
    async with await _client_for_engine() as client:
        await _register(client, email, password)
        # Leave as unverified (fastapi-users default).
        resp = await client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        assert resp.status_code in (200, 204), resp.text
        me = await client.get("/auth/users/me")
        # Per Pitfall 10 — verified=True gate fires.
        assert me.status_code in (401, 403)
    await _cleanup_user(engine, email)


async def test_audit_session_started(engine: "AsyncEngine") -> None:
    """Successful login writes auth.session_started audit row."""
    email = "login-audit@example.com"
    password = "Valid-Pass-1234"
    await _cleanup_user(engine, email)
    async with await _client_for_engine() as client:
        await _register(client, email, password)
        await _set_verified(engine, email, True)
        resp = await client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        assert resp.status_code in (200, 204), resp.text

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT actor FROM audit_log "
                    "WHERE event_type = 'auth.session_started' "
                    "AND payload->>'email' = :em "
                    "ORDER BY occurred_at DESC LIMIT 1"
                ),
                {"em": email},
            )
        ).first()
        assert row is not None
    await _cleanup_user(engine, email)


async def test_bad_credentials_returns_400(engine: "AsyncEngine") -> None:
    """Wrong password returns 400; right email is NOT confirmed."""
    email = "login-bad@example.com"
    await _cleanup_user(engine, email)
    async with await _client_for_engine() as client:
        await _register(client, email, "Valid-Pass-1234")
        resp = await client.post(
            "/auth/login",
            data={"username": email, "password": "Wrong-Pass-9999"},
        )
        assert resp.status_code == 400
        # Generic detail — does NOT reveal whether email existed.
        detail = str(resp.json().get("detail", "")).upper()
        assert "BAD_CREDENTIALS" in detail or "INVALID" in detail
    await _cleanup_user(engine, email)
