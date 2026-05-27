"""POST /auth/register — AUTH-01 + AUTH-02 integration tests."""

import re
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select, text

from app.auth.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def _cleanup_user(engine: "AsyncEngine", email: str) -> None:
    """Best-effort delete by email so re-runs don't fail with unique violations."""
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM users WHERE email = :em"), {"em": email}
        )
        await conn.commit()


async def _client_for_engine(engine: "AsyncEngine") -> httpx.AsyncClient:
    """Build an httpx client wired to the FastAPI app under test."""
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_register_success(engine: "AsyncEngine") -> None:
    """POST /auth/register with a valid payload returns 201 + creates a user row."""
    email = "reg-success@example.com"
    await _cleanup_user(engine, email)
    async with await _client_for_engine(engine) as client:
        resp = await client.post(
            "/auth/register",
            json={"email": email, "password": "Valid-Pass-1234"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        # Defense-in-depth: is_superuser is NEVER on the wire (T-02-06).
        assert "is_superuser" not in body
        assert body["email"] == email
        assert body["is_admin"] is False

    # The user row exists with a hashed password (not the plaintext).
    async with engine.connect() as conn:
        row = (
            await conn.execute(select(User).where(User.email == email))
        ).first()
        assert row is not None
        assert row.hashed_password != "Valid-Pass-1234"
        # pwdlib default = Argon2id → hash starts with $argon2id$ (or $2b$ bcrypt fallback).
        hp = row.hashed_password
        assert hp.startswith("$argon2id$") or hp.startswith("$2b$")

    await _cleanup_user(engine, email)


async def test_weak_password_rejected(engine: "AsyncEngine") -> None:
    """POST /auth/register with too-short password returns 400 + no user created."""
    email = "weak-pass@example.com"
    await _cleanup_user(engine, email)
    async with await _client_for_engine(engine) as client:
        resp = await client.post(
            "/auth/register",
            json={"email": email, "password": "short"},
        )
        assert resp.status_code == 400
        body = resp.json()
        # Surfaces a code + reason discriminator.
        detail = body.get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "REGISTER_INVALID_PASSWORD"
            assert "12 characters" in detail.get("reason", "")
        # No user row.
        async with engine.connect() as conn:
            row = (
                await conn.execute(select(User).where(User.email == email))
            ).first()
            assert row is None


async def test_password_with_email_substring_rejected(engine: "AsyncEngine") -> None:
    """Password containing the email local-part is rejected."""
    email = "subtest@example.com"
    await _cleanup_user(engine, email)
    async with await _client_for_engine(engine) as client:
        # Password contains "subtest" — the email local-part substring.
        resp = await client.post(
            "/auth/register",
            json={"email": email, "password": "Subtest-Word-1234"},
        )
        assert resp.status_code == 400, resp.text


async def test_duplicate_email_rejected(engine: "AsyncEngine") -> None:
    """Second registration with the same email returns 400 USER_ALREADY_EXISTS."""
    email = "dup@example.com"
    await _cleanup_user(engine, email)
    async with await _client_for_engine(engine) as client:
        r1 = await client.post(
            "/auth/register",
            json={"email": email, "password": "Valid-Pass-1234"},
        )
        assert r1.status_code == 201, r1.text
        r2 = await client.post(
            "/auth/register",
            json={"email": email, "password": "Different-Pass-1234"},
        )
        assert r2.status_code == 400
        assert "ALREADY_EXISTS" in str(r2.json().get("detail", "")).upper()
    await _cleanup_user(engine, email)


async def test_audit_log_written_on_register(engine: "AsyncEngine") -> None:
    """Registration writes an audit_log row with event_type=auth.guest_created."""
    email = "auditcheck@example.com"
    await _cleanup_user(engine, email)
    async with await _client_for_engine(engine) as client:
        resp = await client.post(
            "/auth/register",
            json={"email": email, "password": "Valid-Pass-1234"},
        )
        assert resp.status_code == 201, resp.text

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT event_type, actor FROM audit_log "
                "WHERE event_type = 'auth.guest_created' "
                "AND payload->>'email' = :em "
                "ORDER BY occurred_at DESC LIMIT 1"
            ),
            {"em": email},
        )
        row = result.first()
        assert row is not None, "auth.guest_created audit row missing"
        assert re.match(r"^user:", row.actor)

    await _cleanup_user(engine, email)
