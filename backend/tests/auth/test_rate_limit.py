"""POST /auth/login rate-limiting — AUTH-08 (5/min per-IP AND per-email)."""

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


async def test_six_logins_returns_429(engine: "AsyncEngine") -> None:
    """5 failing logins from same IP/email pair → 6th returns 429 (AUTH-08)."""
    email = "ratelimit-ip@example.com"
    password = "Valid-Pass-1234"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        # Register so the email exists — the rate limit applies regardless.
        await client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
        # 5 failing attempts.
        for i in range(5):
            resp = await client.post(
                "/auth/login",
                data={"username": email, "password": "wrong-password"},
            )
            assert resp.status_code != 429, f"too-early 429 on attempt {i+1}: {resp.text}"
        # 6th — must return 429.
        sixth = await client.post(
            "/auth/login",
            data={"username": email, "password": "wrong-password"},
        )
        assert sixth.status_code == 429, sixth.text
        # No info leak — generic message.
        body = sixth.json()
        detail = str(body.get("detail", "")).lower()
        assert "too many" in detail
        # Must NOT mention email existence / verification.
        assert "exist" not in detail
        assert "verified" not in detail
        assert email not in detail

    await _cleanup_user(engine, email)


async def test_per_email_limit_known_vs_unknown(engine: "AsyncEngine") -> None:
    """6th attempt against an unknown email also returns 429 with identical body."""
    unknown = "nobody-here-please@example.com"
    async with await _client_for_app() as client:
        for i in range(5):
            resp = await client.post(
                "/auth/login",
                data={"username": unknown, "password": "Wrong-Pass-9999"},
            )
            assert resp.status_code != 429, f"too-early 429: attempt {i+1}"
        sixth = await client.post(
            "/auth/login",
            data={"username": unknown, "password": "Wrong-Pass-9999"},
        )
        assert sixth.status_code == 429
        # T-02-10: response shape identical to the known-email 429.
        detail = str(sixth.json().get("detail", "")).lower()
        assert "too many" in detail
        assert unknown not in detail
