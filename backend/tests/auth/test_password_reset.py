"""POST /auth/forgot-password + /auth/reset-password — AUTH-06 + token_version bump."""

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


async def _request_reset_and_capture_token(
    client: httpx.AsyncClient,
    email: str,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Trigger forgot-password and capture the reset token via monkeypatching.

    Replaces the private-JWT-fabrication approach (which used fastapi-users'
    internal ``generate_jwt`` and double-hashed the password fingerprint) with
    a first-class path: call ``POST /auth/forgot-password``, intercept the
    token inside ``EmailService.send_reset_password_email``, and return it.

    This tests the real token minting path and remains stable across
    fastapi-users patch versions.
    """
    import app.auth.email as email_module

    captured: list[str] = []

    async def _mock_send_reset(*, to: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr(
        email_module.EmailService,
        "send_reset_password_email",
        _mock_send_reset,
    )

    fp = await client.post("/auth/forgot-password", json={"email": email})
    assert fp.status_code == 202, f"forgot-password returned {fp.status_code}: {fp.text}"
    assert captured, "send_reset_password_email was not called — token not captured"
    return captured[0]


async def test_reset_invalidates_sessions(
    engine: "AsyncEngine", monkeypatch: pytest.MonkeyPatch
) -> None:
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

        # Request reset and capture the token via the real email hook.
        reset_token = await _request_reset_and_capture_token(client, email, monkeypatch)

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


async def test_audit_trail_on_reset(engine: "AsyncEngine", monkeypatch: pytest.MonkeyPatch) -> None:
    """Both auth.password_reset_requested + auth.password_reset_completed audit rows exist."""
    email = "reset-audit@example.com"
    password = "Valid-Pass-1234"
    new_password = "Audit-Pass-1!ABC"
    await _cleanup_user(engine, email)
    async with await _client_for_app() as client:
        await _register_and_verify(client, engine, email, password)
        # Request reset and capture the token via the real email hook.
        token = await _request_reset_and_capture_token(client, email, monkeypatch)
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
