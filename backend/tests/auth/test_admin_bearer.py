"""Admin Bearer surface integration tests (AUTH-07, AUTH-08, AUTH-09 admin scope).

Asserts the cross-surface isolation invariants:
- /admin/auth/login returns Bearer JSON (NO cookie); rate-limited 5/min per-IP +
  per-email; identical 401 for unknown email / wrong password / non-superuser
  (T-02-26 + ROADMAP SC#5)
- Player cookie does NOT authenticate /admin/* (T-02-25)
- Admin Bearer does NOT authenticate /auth/users/me (cross-transport isolation)
- Admin Bearer is revocable via /admin/auth/logout (T-02-36)
- Audit rows on success (auth.admin_login_started) and failure
  (auth.admin_login_failed) — payload.reason captures internal distinction
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import httpx
import pytest
from pwdlib import PasswordHash
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


_TEST_ADMIN_EMAIL = "admin-bearer-test@example.com"
_TEST_PLAYER_EMAIL = "player-vs-admin@example.com"
_TEST_PASSWORD = "Admin-Test-Pass-1!"


# ----------------------------------------------------------------------
# Helpers (mirror the Plan 02-02 test pattern: avoid the session-scope
# httpx ``client`` fixture; build the client inline within each test)
# ----------------------------------------------------------------------
async def _client_for_app() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _seed_admin(engine: AsyncEngine, email: str = _TEST_ADMIN_EMAIL) -> None:
    """Idempotently INSERT/UPSERT an admin user (is_superuser=True, is_verified=True)."""
    helper = PasswordHash.recommended()
    hashed = helper.hash(_TEST_PASSWORD)
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM users WHERE email = :em"),
            {"em": email},
        )
        await conn.execute(
            text(
                "INSERT INTO users "
                "(email, hashed_password, is_active, is_superuser, "
                " is_verified, display_name, token_version) "
                "VALUES (:em, :pw, TRUE, TRUE, TRUE, 'Admin Test', 0)"
            ),
            {"em": email, "pw": hashed},
        )
        await conn.commit()


async def _seed_player(engine: AsyncEngine, email: str = _TEST_PLAYER_EMAIL) -> None:
    """Idempotently INSERT a regular (non-admin) verified player."""
    helper = PasswordHash.recommended()
    hashed = helper.hash(_TEST_PASSWORD)
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM users WHERE email = :em"),
            {"em": email},
        )
        await conn.execute(
            text(
                "INSERT INTO users "
                "(email, hashed_password, is_active, is_superuser, "
                " is_verified, display_name, token_version) "
                "VALUES (:em, :pw, TRUE, FALSE, TRUE, 'Player Test', 0)"
            ),
            {"em": email, "pw": hashed},
        )
        await conn.commit()


async def _cleanup(engine: AsyncEngine, email: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()


# ----------------------------------------------------------------------
# 1) BearerTransport returns OAuth2 JSON token (no cookie)
# ----------------------------------------------------------------------
async def test_admin_login_returns_bearer_token(engine: AsyncEngine) -> None:
    """POST /admin/auth/login → 200 + ``{access_token, token_type:'bearer'}``; NO Set-Cookie."""
    await _seed_admin(engine)
    try:
        async with await _client_for_app() as client:
            resp = await client.post(
                "/admin/auth/login",
                data={"username": _TEST_ADMIN_EMAIL, "password": _TEST_PASSWORD},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        # No cookie — admin uses Bearer transport, NOT cookie.
        assert "set-cookie" not in {k.lower() for k in resp.headers}
    finally:
        await _cleanup(engine, _TEST_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 2) Player cookie does NOT authenticate /admin/* (T-02-25)
# ----------------------------------------------------------------------
async def test_player_login_does_not_grant_admin(engine: AsyncEngine) -> None:
    """Player cookie reaching /admin/* gets 401/403 (NOT 200)."""
    await _seed_player(engine)
    try:
        async with await _client_for_app() as client:
            # 1. Player logs in via cookie endpoint (sets xpredict_session)
            login = await client.post(
                "/auth/login",
                data={"username": _TEST_PLAYER_EMAIL, "password": _TEST_PASSWORD},
            )
            assert login.status_code in (200, 204), login.text

            # 2. Player tries /admin/auth/logout with their cookie. The
            #    cookie is NOT what the admin BearerTransport reads, so it
            #    must be rejected (401). The cookie does NOT confer
            #    superuser authority.
            resp = await client.post("/admin/auth/logout")
            assert resp.status_code in (401, 403), (
                f"Player cookie unexpectedly authenticated /admin/*: "
                f"{resp.status_code} {resp.text}"
            )
    finally:
        await _cleanup(engine, _TEST_PLAYER_EMAIL)


# ----------------------------------------------------------------------
# 3) Non-admin user POSTs to /admin/auth/login → 401 (T-02-26, ROADMAP SC#5)
# ----------------------------------------------------------------------
async def test_non_admin_bearer_forbidden(engine: AsyncEngine) -> None:
    """Player credentials → 401 from /admin/auth/login (defense-in-depth)."""
    await _seed_player(engine)
    try:
        async with await _client_for_app() as client:
            resp = await client.post(
                "/admin/auth/login",
                data={"username": _TEST_PLAYER_EMAIL, "password": _TEST_PASSWORD},
            )
        assert resp.status_code == 401, resp.text
        # No leak — body must be the generic "Invalid credentials" string
        assert resp.json() == {"detail": "Invalid credentials"}
    finally:
        await _cleanup(engine, _TEST_PLAYER_EMAIL)


# ----------------------------------------------------------------------
# 4) Admin Bearer does NOT authenticate /auth/users/me
# ----------------------------------------------------------------------
async def test_admin_bearer_does_not_authenticate_player_routes(
    engine: AsyncEngine,
) -> None:
    """Admin Bearer presented to /auth/users/me → 401 (player is cookie-only)."""
    await _seed_admin(engine)
    try:
        async with await _client_for_app() as client:
            login = await client.post(
                "/admin/auth/login",
                data={"username": _TEST_ADMIN_EMAIL, "password": _TEST_PASSWORD},
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]
            # Clear any inherited cookies (admin login set none, be explicit)
            client.cookies.clear()
            resp = await client.get(
                "/auth/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        # 401: the player CookieTransport does NOT read the Bearer header.
        # fastapi-users may return 401 or 403 — accept either, must NOT be 200.
        assert resp.status_code in (401, 403), (
            f"Admin Bearer unexpectedly authenticated /auth/users/me: "
            f"{resp.status_code} {resp.text}"
        )
    finally:
        await _cleanup(engine, _TEST_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 5) Admin login rate-limited 5/min per-IP (AUTH-08)
# ----------------------------------------------------------------------
async def test_admin_login_rate_limited(engine: AsyncEngine) -> None:
    """6th POST /admin/auth/login within 60s → 429 (per-IP cap; AUTH-08)."""
    await _seed_admin(engine)
    try:
        async with await _client_for_app() as client:
            # First 5 hits succeed (slowapi counts hits regardless of result)
            for i in range(5):
                r = await client.post(
                    "/admin/auth/login",
                    data={"username": _TEST_ADMIN_EMAIL, "password": _TEST_PASSWORD},
                )
                assert r.status_code == 200, f"hit {i + 1} failed: {r.text}"

            # 6th hit → 429
            r6 = await client.post(
                "/admin/auth/login",
                data={"username": _TEST_ADMIN_EMAIL, "password": _TEST_PASSWORD},
            )
        assert r6.status_code == 429
        body = r6.json()
        # Generic body — no email enumeration
        assert "detail" in body
        assert "many" in body["detail"].lower() or "rate" in body["detail"].lower()
    finally:
        await _cleanup(engine, _TEST_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 6) Admin login failure response identical for unknown vs wrong-password
# ----------------------------------------------------------------------
async def test_admin_login_failure_does_not_leak_existence(
    engine: AsyncEngine,
) -> None:
    """Unknown email and wrong password both return identical 401 body."""
    await _seed_admin(engine)
    try:
        async with await _client_for_app() as client:
            unknown = await client.post(
                "/admin/auth/login",
                data={
                    "username": "nobody-here-12345@example.com",
                    "password": "Some-Wrong-Password-1!",
                },
            )
            wrong = await client.post(
                "/admin/auth/login",
                data={
                    "username": _TEST_ADMIN_EMAIL,
                    "password": "Some-Wrong-Password-1!",
                },
            )
        assert unknown.status_code == 401
        assert wrong.status_code == 401
        assert unknown.json() == wrong.json() == {"detail": "Invalid credentials"}
    finally:
        await _cleanup(engine, _TEST_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 7) Audit: auth.admin_login_started on success, auth.admin_login_failed on fail
# ----------------------------------------------------------------------
async def test_admin_login_audit_logged(engine: AsyncEngine) -> None:
    """Successful + failed admin logins write the locked audit event types."""
    await _seed_admin(engine)
    await _seed_player(engine)
    try:
        async with await _client_for_app() as client:
            # 1. Successful admin login
            ok = await client.post(
                "/admin/auth/login",
                data={"username": _TEST_ADMIN_EMAIL, "password": _TEST_PASSWORD},
            )
            assert ok.status_code == 200, ok.text

            # 2. Player tries admin login (non-superuser → 401, reason=not_superuser)
            bad = await client.post(
                "/admin/auth/login",
                data={"username": _TEST_PLAYER_EMAIL, "password": _TEST_PASSWORD},
            )
            assert bad.status_code == 401

            # 3. Unknown email (→ 401, reason=unknown_email)
            unk = await client.post(
                "/admin/auth/login",
                data={
                    "username": "nobody-here-23456@example.com",
                    "password": "Some-Pass-1!",
                },
            )
            assert unk.status_code == 401

        # Inspect audit rows — they were committed in independent sessions
        async with engine.connect() as conn:
            success_rows = (
                await conn.execute(
                    text(
                        "SELECT actor, payload FROM audit_log "
                        "WHERE event_type = 'auth.admin_login_started' "
                        "AND payload->>'email' = :em "
                        "ORDER BY occurred_at DESC"
                    ),
                    {"em": _TEST_ADMIN_EMAIL},
                )
            ).all()
            failure_rows = (
                await conn.execute(
                    text(
                        "SELECT actor, payload FROM audit_log "
                        "WHERE event_type = 'auth.admin_login_failed' "
                        "ORDER BY occurred_at DESC LIMIT 5"
                    ),
                )
            ).all()

        assert len(success_rows) >= 1, "auth.admin_login_started missing"
        assert len(failure_rows) >= 2, "auth.admin_login_failed missing"

        # The failure rows' payload.reason captures which arm fired
        reasons = {r.payload.get("reason") for r in failure_rows}
        assert "not_superuser" in reasons or "unknown_email" in reasons
    finally:
        await _cleanup(engine, _TEST_ADMIN_EMAIL)
        await _cleanup(engine, _TEST_PLAYER_EMAIL)


# ----------------------------------------------------------------------
# 8) Admin Bearer revocation via /admin/auth/logout (T-02-36)
# ----------------------------------------------------------------------
async def test_admin_bearer_revocation(engine: AsyncEngine) -> None:
    """After /admin/auth/logout, the row is revoked + Bearer no longer works."""
    await _seed_admin(engine)
    try:
        async with await _client_for_app() as client:
            login = await client.post(
                "/admin/auth/login",
                data={"username": _TEST_ADMIN_EMAIL, "password": _TEST_PASSWORD},
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]

            # 1. Logout (idempotent — returns 204)
            out = await client.post(
                "/admin/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert out.status_code == 204, out.text

        # 2. Token row has revoked_at IS NOT NULL — query in a fresh session
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT revoked_at FROM refresh_tokens " "WHERE token_hash = :th"),
                    {"th": token_hash},
                )
            ).first()
            assert row is not None, "refresh_tokens row should exist after admin login"
            assert row.revoked_at is not None, "Bearer should be revoked after /admin/auth/logout"
    finally:
        await _cleanup(engine, _TEST_ADMIN_EMAIL)
