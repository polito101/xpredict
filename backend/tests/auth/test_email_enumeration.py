"""Email enumeration mitigations — AUTH-08, T-02-10, T-02-11."""

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


async def test_forgot_password_returns_202_for_unknown_email(engine: "AsyncEngine") -> None:
    """Forgot-password to unknown email returns 202 (matches known-email response)."""
    async with await _client_for_app() as client:
        resp_unknown = await client.post(
            "/auth/forgot-password",
            json={"email": "nobody-here@example.com"},
        )
        assert resp_unknown.status_code == 202
        body_unknown = resp_unknown.json()
        assert body_unknown == {"status": "accepted"}


async def test_forgot_password_same_response_for_known_email(engine: "AsyncEngine") -> None:
    """Known-email response shape matches unknown-email — no enumeration leak."""
    email = "known@example.com"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        await client.post(
            "/auth/register",
            json={"email": email, "password": "Valid-Pass-1234"},
        )
        resp_known = await client.post(
            "/auth/forgot-password",
            json={"email": email},
        )
        assert resp_known.status_code == 202
        assert resp_known.json() == {"status": "accepted"}
    await _cleanup_user(engine, email)


async def test_login_does_not_leak_email_existence(engine: "AsyncEngine") -> None:
    """Login with unknown email + login with known email both return 400 with same shape."""
    known_email = "loginleak-known@example.com"
    unknown_email = "loginleak-nobody@example.com"
    await _cleanup_user(engine, known_email)
    async with await _client_for_app() as client:
        await client.post(
            "/auth/register",
            json={"email": known_email, "password": "Valid-Pass-1234"},
        )
        r_unknown = await client.post(
            "/auth/login",
            data={"username": unknown_email, "password": "Wrong-Pass-9999"},
        )
        r_known = await client.post(
            "/auth/login",
            data={"username": known_email, "password": "Wrong-Pass-9999"},
        )
        assert (
            r_unknown.status_code == r_known.status_code
        ), "status codes diverge — enumeration leak"
        # Detail body shape MUST match.
        assert r_unknown.json() == r_known.json(), "response bodies diverge — enumeration leak"
    await _cleanup_user(engine, known_email)
