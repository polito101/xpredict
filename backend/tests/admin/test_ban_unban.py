"""Ban/unban state machine + 3 enforcement points (Phase 8, Plan 08-01).

Covers D-01..D-04 + the three D-02 enforcement layers:

  - Ban / unban happy paths (200, ``banned_at`` flips, audit row written).
  - 409 on already-banned / already-active; 422 on a ban with no reason.
  - Enforcement: login (403 "Account suspended"), bet placement (403 via the
    existing ``current_betting_player`` gate), admin recharge of a banned user
    (403). Frozen-balance: the wallet balance is identical across a ban+unban
    cycle (D-03 — the balance is NEVER touched).

Audit rows are asserted with a direct ``audit_log`` query (the admin audit-log
viewer endpoint is Plan 08-02). Bet enforcement overrides ``current_active_player``
with a banned stub user — the same technique as ``tests/bets/test_bet_router.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.auth.deps import current_active_player
from app.main import app
from tests.admin._helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    auth,
    cleanup_user,
    client,
    get_admin_token,
    seed_user,
    seed_wallet,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Reset FastAPI dependency overrides after every test — no cross-test leak."""
    yield
    app.dependency_overrides.clear()


class _BannedPlayer:
    """Minimal authenticated-player stand-in (banned) for the bet enforcement test."""

    def __init__(self) -> None:
        self.id = uuid4()
        self.banned_at = datetime.now(UTC)


async def _audit_count(engine: AsyncEngine, event_type: str, target_user_id: str) -> int:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE event_type = :et AND payload->>'target_user_id' = :tid"
                ),
                {"et": event_type, "tid": target_user_id},
            )
        ).one()
    return int(row[0])


# --------------------------------------------------------------------------- #
# Ban / unban happy paths + audit.
# --------------------------------------------------------------------------- #
async def test_ban_happy_path_sets_banned_at_and_audits(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "ban-me@test.com")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.post(
                f"/api/v1/admin/users/{uid}/ban",
                json={"reason": "spam"},
                headers=auth(token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["banned_at"] is not None
        assert body["status"] == "banned"
        assert await _audit_count(engine, "admin.user_banned", str(uid)) == 1
    finally:
        await cleanup_user(engine, "ban-me@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_unban_happy_path_clears_banned_at_and_audits(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "unban-me@test.com", banned=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.post(
                f"/api/v1/admin/users/{uid}/unban",
                json={"reason": "appeal granted"},
                headers=auth(token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["banned_at"] is None
        assert body["status"] == "active"
        assert await _audit_count(engine, "admin.user_unbanned", str(uid)) == 1
    finally:
        await cleanup_user(engine, "unban-me@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_ban_already_banned_returns_409(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "double-ban@test.com", banned=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.post(
                f"/api/v1/admin/users/{uid}/ban",
                json={"reason": "again"},
                headers=auth(token),
            )
        assert resp.status_code == 409, resp.text
    finally:
        await cleanup_user(engine, "double-ban@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_unban_active_user_returns_409(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "active-unban@test.com", banned=False)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.post(
                f"/api/v1/admin/users/{uid}/unban",
                json={},
                headers=auth(token),
            )
        assert resp.status_code == 409, resp.text
    finally:
        await cleanup_user(engine, "active-unban@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_ban_without_reason_returns_422(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "noreason-ban@test.com")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            # Empty body — no reason field.
            resp_empty = await c.post(
                f"/api/v1/admin/users/{uid}/ban", json={}, headers=auth(token)
            )
            # Blank reason — fails min_length=1.
            resp_blank = await c.post(
                f"/api/v1/admin/users/{uid}/ban", json={"reason": ""}, headers=auth(token)
            )
        assert resp_empty.status_code == 422, resp_empty.text
        assert resp_blank.status_code == 422, resp_blank.text
    finally:
        await cleanup_user(engine, "noreason-ban@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


# --------------------------------------------------------------------------- #
# Enforcement point 1 — login (D-02).
# --------------------------------------------------------------------------- #
async def test_banned_user_login_returns_403(engine: AsyncEngine) -> None:
    await seed_user(engine, "banned-login@test.com", banned=True)
    try:
        async with await client() as c:
            resp = await c.post(
                "/auth/login",
                data={"username": "banned-login@test.com", "password": ADMIN_PASSWORD},
            )
        assert resp.status_code == 403, resp.text
        assert "suspended" in resp.text.lower()
    finally:
        await cleanup_user(engine, "banned-login@test.com")


# --------------------------------------------------------------------------- #
# Enforcement point 2 — bet placement (D-02, existing current_betting_player).
# --------------------------------------------------------------------------- #
async def test_banned_user_bet_returns_403() -> None:
    app.dependency_overrides[current_active_player] = lambda: _BannedPlayer()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/bets",
            json={"market_id": str(uuid4()), "outcome_id": str(uuid4()), "stake": "10.0000"},
        )
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- #
# Enforcement point 3 — admin recharge of a banned user (D-02).
# --------------------------------------------------------------------------- #
async def test_recharge_banned_user_returns_403(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "recharge-banned@test.com", banned=True)
    await seed_wallet(engine, uid, balance=Decimal("0.0000"))
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.post(
                f"/admin/wallets/{uid}/recharge",
                json={"amount": "50.0000", "reason": "test"},
                headers={**auth(token), "Idempotency-Key": str(uuid4())},
            )
        assert resp.status_code == 403, resp.text
        assert "suspended" in resp.text.lower()
    finally:
        await cleanup_user(engine, "recharge-banned@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


# --------------------------------------------------------------------------- #
# Frozen-balance semantics (D-03) — balance unchanged across ban+unban.
# --------------------------------------------------------------------------- #
async def test_balance_unchanged_after_ban_unban_cycle(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "frozen-bal@test.com")
    await seed_wallet(engine, uid, balance=Decimal("77.7700"))
    try:
        async with await client() as c:
            token = await get_admin_token(c)

            before = await c.get(f"/api/v1/admin/users/{uid}", headers=auth(token))
            balance_before = before.json()["balance"]

            ban = await c.post(
                f"/api/v1/admin/users/{uid}/ban",
                json={"reason": "freeze test"},
                headers=auth(token),
            )
            assert ban.status_code == 200, ban.text
            balance_during_ban = ban.json()["balance"]

            unban = await c.post(
                f"/api/v1/admin/users/{uid}/unban",
                json={},
                headers=auth(token),
            )
            assert unban.status_code == 200, unban.text
            balance_after = unban.json()["balance"]

        assert Decimal(balance_before) == Decimal("77.7700")
        assert Decimal(balance_during_ban) == Decimal("77.7700")
        assert Decimal(balance_after) == Decimal("77.7700")
    finally:
        await cleanup_user(engine, "frozen-bal@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)
