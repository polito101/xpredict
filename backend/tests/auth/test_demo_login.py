"""POST /auth/demo-login — one-click demo access (DEMO-01).

The demo-login endpoint is gated behind ``DEMO_MODE`` (default off): hidden (404)
in white-label / production, and in demo mode it mints an ephemeral
already-verified + bonus-funded player per click, issues the player session
cookie, and is rate-limited per IP.

Tests toggle ``DEMO_MODE`` via the codebase pattern (monkeypatch the env var +
``get_settings.cache_clear()``) — both the route and the UserManager read
``get_settings().DEMO_MODE`` dynamically at request time, so clearing the LRU
cache after setting the env is what makes the flag take effect.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.session import _get_session_maker
from app.wallet.constants import (
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.models import Account

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_DEMO_EMAIL_LIKE = "demo-%@demo.example.com"


@pytest.fixture
def demo_mode_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Turn DEMO_MODE on for the duration of a test.

    Both the demo-login route and ``UserManager`` read
    ``get_settings().DEMO_MODE`` dynamically, and ``get_settings`` is
    ``lru_cached``; setting the env var + clearing the cache reloads Settings
    with the flag on. Teardown removes the env var + clears the cache again so
    the default-off behaviour is restored for the next test.
    """
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        yield
    finally:
        monkeypatch.delenv("DEMO_MODE", raising=False)
        get_settings.cache_clear()


async def _client_for_engine() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _cleanup_demo_users(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM users WHERE email LIKE :pat"),
            {"pat": _DEMO_EMAIL_LIKE},
        )
        await conn.commit()


async def _latest_demo_user_id(engine: AsyncEngine) -> UUID:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id FROM users WHERE email LIKE :pat " "ORDER BY created_at DESC LIMIT 1"
                ),
                {"pat": _DEMO_EMAIL_LIKE},
            )
        ).first()
        assert row is not None, "no demo user was created"
        return row[0]


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


async def test_demo_login_404_when_flag_off(engine: AsyncEngine) -> None:
    """With DEMO_MODE off (default), POST /auth/demo-login returns 404."""
    await _cleanup_demo_users(engine)
    # Ensure the cache reflects the default-off env (no DEMO_MODE set).
    get_settings.cache_clear()
    try:
        async with await _client_for_engine() as client:
            resp = await client.post("/auth/demo-login")
            assert resp.status_code == 404, resp.text
    finally:
        get_settings.cache_clear()
    await _cleanup_demo_users(engine)


async def test_demo_login_creates_verified_funded_user_when_on(
    engine: AsyncEngine, demo_mode_on: None
) -> None:
    """DEMO_MODE on: 200 + session cookie; the new user is verified (can hit /me)."""
    await _cleanup_demo_users(engine)
    try:
        async with await _client_for_engine() as client:
            resp = await client.post("/auth/demo-login")
            assert resp.status_code in (200, 204), resp.text

            set_cookie = resp.headers.get("set-cookie", "")
            assert "xpredict_session=" in set_cookie
            assert "HttpOnly" in set_cookie
            assert "samesite=lax" in set_cookie.lower()

            # The cookie persists AND the user is verified — /auth/users/me
            # (verified=True gate) returns 200 with a demo-*@demo.example.com email.
            me = await client.get("/auth/users/me")
            assert me.status_code == 200, me.text
            body = me.json()
            assert body["email"].startswith("demo-")
            assert body["email"].endswith("@demo.example.com")
            # Player surface must never leak the superuser flag.
            assert "is_superuser" not in body
    finally:
        await _cleanup_demo_users(engine)


async def test_demo_login_grants_signup_bonus(engine: AsyncEngine, demo_mode_on: None) -> None:
    """DEMO_MODE on: the new demo user's wallet equals SIGNUP_BONUS_AMOUNT."""
    await _cleanup_demo_users(engine)
    bonus = get_settings().SIGNUP_BONUS_AMOUNT
    try:
        async with await _client_for_engine() as client:
            resp = await client.post("/auth/demo-login")
            assert resp.status_code in (200, 204), resp.text

        user_id = await _latest_demo_user_id(engine)
        assert await _wallet_balance(user_id) == bonus
    finally:
        await _cleanup_demo_users(engine)


async def test_demo_login_rate_limited(engine: AsyncEngine, demo_mode_on: None) -> None:
    """DEMO_MODE on: 5 calls do NOT 429; the 6th from the same IP returns 429."""
    await _cleanup_demo_users(engine)
    try:
        async with await _client_for_engine() as client:
            for i in range(5):
                resp = await client.post("/auth/demo-login")
                assert resp.status_code != 429, f"too-early 429 on attempt {i + 1}: {resp.text}"
            sixth = await client.post("/auth/demo-login")
            assert sixth.status_code == 429, sixth.text
            detail = str(sixth.json().get("detail", "")).lower()
            assert "too many" in detail
    finally:
        await _cleanup_demo_users(engine)
