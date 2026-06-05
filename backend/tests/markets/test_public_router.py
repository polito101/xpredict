from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_ADMIN_EMAIL = "market-public-router-admin@test.com"
_ADMIN_PASSWORD = "Admin-Test-Pass-1!"


async def _client() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _seed_admin(engine: AsyncEngine) -> None:
    hashed = PasswordHash.recommended().hash(_ADMIN_PASSWORD)
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": _ADMIN_EMAIL})
        await conn.execute(
            text(
                "INSERT INTO users "
                "(email, hashed_password, is_active, is_superuser, "
                " is_verified, display_name, token_version) "
                "VALUES (:em, :pw, TRUE, TRUE, TRUE, 'Admin', 0)"
            ),
            {"em": _ADMIN_EMAIL, "pw": hashed},
        )
        await conn.commit()


async def _cleanup_admin(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": _ADMIN_EMAIL})
        await conn.commit()


async def _create_market(
    client: httpx.AsyncClient,
    token: str,
    **overrides: object,
) -> dict:
    base = {
        "question": "Public test market?",
        "resolution_criteria": "TBD",
        "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "initial_odds_yes": "0.5",
        "category": "test",
    }
    base.update(overrides)
    resp = await client.post(
        "/api/v1/admin/markets",
        json=base,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


async def test_public_list_returns_open_markets(engine: AsyncEngine) -> None:
    await _seed_admin(engine)
    try:
        async with await _client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            await _create_market(c, token)

            resp = await c.get("/api/v1/markets")
        assert resp.status_code == 200
        body = resp.json()
        # Phase 6: response is now a flat list (D-01 house-first sorting)
        assert isinstance(body, list)
        assert len(body) >= 1
        for item in body:
            assert item["status"] == "OPEN"
    finally:
        await _cleanup_admin(engine)


async def test_public_list_excludes_closed_markets(engine: AsyncEngine) -> None:
    await _seed_admin(engine)
    try:
        async with await _client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            market = await _create_market(c, token)
            await c.post(
                f"/api/v1/admin/markets/{market['id']}/close",
                headers={"Authorization": f"Bearer {token}"},
            )

            resp = await c.get("/api/v1/markets")
        body = resp.json()
        # Phase 6: response is now a flat list (D-01)
        ids = {item["id"] for item in body}
        assert market["id"] not in ids
    finally:
        await _cleanup_admin(engine)


async def test_public_get_by_slug(engine: AsyncEngine) -> None:
    await _seed_admin(engine)
    try:
        async with await _client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            market = await _create_market(c, token)

            resp = await c.get(f"/api/v1/markets/{market['slug']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == market["id"]
        assert len(resp.json()["outcomes"]) == 2
    finally:
        await _cleanup_admin(engine)


async def test_bet_check_open_market(engine: AsyncEngine) -> None:
    await _seed_admin(engine)
    try:
        async with await _client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            market = await _create_market(c, token)

            resp = await c.get(f"/api/v1/markets/{market['slug']}/bet-check")
        assert resp.status_code == 200
        assert resp.json()["eligible"] is True
    finally:
        await _cleanup_admin(engine)


async def test_bet_check_expired_market_returns_400(engine: AsyncEngine) -> None:
    await _seed_admin(engine)
    try:
        async with await _client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            market = await _create_market(c, token)

        expired_deadline = datetime.now(UTC) - timedelta(hours=1)
        async with engine.connect() as conn:
            await conn.execute(
                text("UPDATE markets SET deadline = :dl WHERE id = CAST(:mid AS uuid)"),
                {"dl": expired_deadline, "mid": market["id"]},
            )
            await conn.commit()

        async with await _client() as c:
            resp = await c.get(f"/api/v1/markets/{market['slug']}/bet-check")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "MARKET_EXPIRED"
    finally:
        await _cleanup_admin(engine)


async def test_bet_check_closed_market_returns_400(engine: AsyncEngine) -> None:
    await _seed_admin(engine)
    try:
        async with await _client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            market = await _create_market(c, token)
            await c.post(
                f"/api/v1/admin/markets/{market['id']}/close",
                headers={"Authorization": f"Bearer {token}"},
            )

            resp = await c.get(f"/api/v1/markets/{market['slug']}/bet-check")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "MARKET_NOT_OPEN"
    finally:
        await _cleanup_admin(engine)


async def test_public_get_resolved_market_returns_200_with_resolution(
    engine: AsyncEngine,
) -> None:
    """STL-06: a RESOLVED market is public (no longer 404) and MarketRead carries the
    winner + source + justification (the player resolved-panel data)."""
    await _seed_admin(engine)
    try:
        async with await _client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            market = await _create_market(c, token)
            winner_outcome_id = market["outcomes"][0]["id"]

        # Drive the market to RESOLVED + populate the STL-06 columns directly (mirrors the
        # expired-deadline UPDATE pattern above; the resolve service is exercised elsewhere).
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "UPDATE markets SET status = 'RESOLVED', "
                    "winning_outcome_id = CAST(:woid AS uuid), "
                    "resolution_source = :src, resolution_justification = :just, "
                    "resolved_at = now() "
                    "WHERE id = CAST(:mid AS uuid)"
                ),
                {
                    "woid": winner_outcome_id,
                    "src": "HOUSE",
                    "just": "YES per the official source",
                    "mid": market["id"],
                },
            )
            await conn.commit()

        async with await _client() as c:
            resp = await c.get(f"/api/v1/markets/{market['slug']}")

        assert resp.status_code == 200  # no longer 404 (STL-06 root cause)
        body = resp.json()
        assert body["status"] == "RESOLVED"
        assert body["winning_outcome_id"] == winner_outcome_id
        assert body["resolution_source"] == "HOUSE"
        assert body["resolution_justification"] == "YES per the official source"
        assert body["resolved_at"] is not None
    finally:
        await _cleanup_admin(engine)


async def test_public_markets_backcompat_flat_list(engine: AsyncEngine) -> None:
    """Back-compat (Phase 16 wiring, T-16-16): GET /api/v1/markets still returns a flat
    ``list[MarketListItem]`` after the new catalog + event-admin routers were registered
    in ``main.py``. Registering the new surfaces must not change the legacy contract — an
    empty markets table returns ``200`` + ``[]`` (still a list), never a paginated object.
    """
    async with await _client() as c:
        resp = await c.get("/api/v1/markets")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
