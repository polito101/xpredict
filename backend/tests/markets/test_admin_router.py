from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_ADMIN_EMAIL = "market-admin-router@test.com"
_ADMIN_PASSWORD = "Admin-Test-Pass-1!"
_PLAYER_EMAIL = "market-player-router@test.com"


async def _client() -> httpx.AsyncClient:
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _seed_user(
    engine: AsyncEngine,
    email: str,
    *,
    is_superuser: bool = False,
) -> None:
    hashed = PasswordHash.recommended().hash(_ADMIN_PASSWORD)
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.execute(
            text(
                "INSERT INTO users "
                "(email, hashed_password, is_active, is_superuser, "
                " is_verified, display_name, token_version) "
                "VALUES (:em, :pw, TRUE, :su, TRUE, 'Test', 0)"
            ),
            {"em": email, "pw": hashed, "su": is_superuser},
        )
        await conn.commit()


async def _cleanup_user(engine: AsyncEngine, email: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()


async def _get_admin_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        "/admin/auth/login",
        data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _market_body(**overrides: object) -> dict:
    base = {
        "question": "Will it rain tomorrow?",
        "resolution_criteria": "Rain recorded at station X by 23:59",
        "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "initial_odds_yes": "0.5",
        "category": "weather",
    }
    base.update(overrides)
    return base


async def test_create_market(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["question"] == "Will it rain tomorrow?"
        assert body["status"] == "OPEN"
        assert body["source"] == "HOUSE"
        assert len(body["outcomes"]) == 2
        labels = {o["label"] for o in body["outcomes"]}
        assert labels == {"YES", "NO"}
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_create_market_generates_slug(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(question="Will Bitcoin hit 100k?"),
                headers=_auth(token),
            )
        assert resp.status_code == 201
        assert resp.json()["slug"].startswith("will-bitcoin-hit-100k")
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_create_market_no_auth_returns_401(engine: AsyncEngine) -> None:
    async with await _client() as c:
        resp = await c.post("/api/v1/admin/markets", json=_market_body())
    assert resp.status_code == 401


async def test_create_market_non_admin_returns_403(engine: AsyncEngine) -> None:
    await _seed_user(engine, _PLAYER_EMAIL, is_superuser=False)
    try:
        async with await _client() as c:
            resp = await c.post(
                "/admin/auth/login",
                data={"username": _PLAYER_EMAIL, "password": _ADMIN_PASSWORD},
            )
            if resp.status_code == 200:
                token = resp.json()["access_token"]
                resp2 = await c.post(
                    "/api/v1/admin/markets",
                    json=_market_body(),
                    headers=_auth(token),
                )
                assert resp2.status_code == 403
            else:
                assert resp.status_code in (400, 401)
    finally:
        await _cleanup_user(engine, _PLAYER_EMAIL)


async def test_list_markets_admin(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            resp = await c.get("/api/v1/admin/markets", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] >= 1
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_list_markets_filter_by_source(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            resp = await c.get(
                "/api/v1/admin/markets?source=HOUSE",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["source"] == "HOUSE"
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_update_market_no_bets(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]
            resp = await c.patch(
                f"/api/v1/admin/markets/{market_id}",
                json={"resolution_criteria": "Updated criteria"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["resolution_criteria"] == "Updated criteria"
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_update_criteria_locked_with_bets(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]

        async with engine.connect() as conn:
            await conn.execute(
                text("UPDATE markets SET bet_count = 1 WHERE id = :mid"),
                {"mid": market_id},
            )
            await conn.commit()

        async with await _client() as c:
            token = await _get_admin_token(c)
            resp = await c.patch(
                f"/api/v1/admin/markets/{market_id}",
                json={"resolution_criteria": "Try to change"},
                headers=_auth(token),
            )
        assert resp.status_code == 423
        assert resp.json()["detail"]["code"] == "CRITERIA_LOCKED"
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_update_odds_allowed_with_bets(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]

        async with engine.connect() as conn:
            await conn.execute(
                text("UPDATE markets SET bet_count = 1 WHERE id = :mid"),
                {"mid": market_id},
            )
            await conn.commit()

        async with await _client() as c:
            token = await _get_admin_token(c)
            resp = await c.patch(
                f"/api/v1/admin/markets/{market_id}",
                json={"odds_yes": "0.7"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_close_market(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]
            resp = await c.post(
                f"/api/v1/admin/markets/{market_id}/close",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "CLOSED"
        assert resp.json()["closed_at"] is not None
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_close_already_closed_returns_409(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]
            await c.post(
                f"/api/v1/admin/markets/{market_id}/close",
                headers=_auth(token),
            )
            resp = await c.post(
                f"/api/v1/admin/markets/{market_id}/close",
                headers=_auth(token),
            )
        assert resp.status_code == 409
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


# ---------------------------------------------------------------------------
# BET-06 per-market stake limits — REAL create/update path (CR-01/WR-01/WR-02)
#
# These deliberately round-trip stake limits through the actual MarketService
# create/update path (POST/PATCH /api/v1/admin/markets -> service -> DB -> read
# back via MarketRead). The original BET-06 tests drove an in-memory MarketView
# stub that bypassed MarketService, so the limits-are-never-persisted bug (CR-01)
# shipped green. Asserting the read-back here is what catches the regression.
# ---------------------------------------------------------------------------


async def test_create_persists_stake_limits(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(min_stake="5", max_stake="500"),
                headers=_auth(token),
            )
            assert create_resp.status_code == 201, create_resp.text
            market_id = create_resp.json()["id"]
            # The create response itself must already carry the persisted bounds.
            # Compare by Decimal value, not exact string: the Numeric(18,4) column
            # round-trips "5" as "5.0000" — the load-bearing assertion is "persisted,
            # not NULL" (CR-01), not the trailing-zero form.
            assert Decimal(create_resp.json()["min_stake"]) == Decimal("5")
            assert Decimal(create_resp.json()["max_stake"]) == Decimal("500")
            # ...and an independent read-back must agree (not NULL — CR-01).
            read_resp = await c.get(
                f"/api/v1/admin/markets/{market_id}",
                headers=_auth(token),
            )
        assert read_resp.status_code == 200, read_resp.text
        body = read_resp.json()
        assert body["min_stake"] is not None
        assert body["max_stake"] is not None
        assert Decimal(body["min_stake"]) == Decimal("5")
        assert Decimal(body["max_stake"]) == Decimal("500")
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_create_without_stake_limits_persists_null(engine: AsyncEngine) -> None:
    # Omitting the bounds keeps them NULL (global-default fallback) — the create
    # path must not invent a value.
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            assert create_resp.status_code == 201, create_resp.text
            market_id = create_resp.json()["id"]
            read_resp = await c.get(
                f"/api/v1/admin/markets/{market_id}",
                headers=_auth(token),
            )
        assert read_resp.status_code == 200, read_resp.text
        body = read_resp.json()
        assert body["min_stake"] is None
        assert body["max_stake"] is None
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_update_persists_stake_limits(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]
            patch_resp = await c.patch(
                f"/api/v1/admin/markets/{market_id}",
                json={"min_stake": "10", "max_stake": "1000"},
                headers=_auth(token),
            )
            assert patch_resp.status_code == 200, patch_resp.text
            assert Decimal(patch_resp.json()["min_stake"]) == Decimal("10")
            assert Decimal(patch_resp.json()["max_stake"]) == Decimal("1000")
            # Independent read-back confirms the PATCH actually persisted (CR-01).
            read_resp = await c.get(
                f"/api/v1/admin/markets/{market_id}",
                headers=_auth(token),
            )
        assert read_resp.status_code == 200, read_resp.text
        body = read_resp.json()
        assert body["min_stake"] is not None
        assert body["max_stake"] is not None
        assert Decimal(body["min_stake"]) == Decimal("10")
        assert Decimal(body["max_stake"]) == Decimal("1000")
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_update_can_clear_stake_limit_to_null(engine: AsyncEngine) -> None:
    # Explicitly sending null reverts a bound to the global default (PATCH uses
    # model_fields_set, not `is not None`), and an omitted bound is left untouched.
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(min_stake="5", max_stake="500"),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]
            # Clear only min_stake; leave max_stake unmentioned.
            patch_resp = await c.patch(
                f"/api/v1/admin/markets/{market_id}",
                json={"min_stake": None},
                headers=_auth(token),
            )
            assert patch_resp.status_code == 200, patch_resp.text
            read_resp = await c.get(
                f"/api/v1/admin/markets/{market_id}",
                headers=_auth(token),
            )
        assert read_resp.status_code == 200, read_resp.text
        body = read_resp.json()
        assert body["min_stake"] is None  # explicitly cleared
        assert body["max_stake"] is not None  # omitted -> untouched
        assert Decimal(body["max_stake"]) == Decimal("500")
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_create_inverted_stake_range_returns_422(engine: AsyncEngine) -> None:
    # WR-01: min_stake > max_stake is rejected server-side (a direct API caller
    # can bypass the client refine).
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(min_stake="500", max_stake="5"),
                headers=_auth(token),
            )
        assert resp.status_code == 422, resp.text
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_update_inverted_stake_range_returns_422(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]
            resp = await c.patch(
                f"/api/v1/admin/markets/{market_id}",
                json={"min_stake": "500", "max_stake": "5"},
                headers=_auth(token),
            )
        assert resp.status_code == 422, resp.text
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_create_zero_stake_bound_returns_422(engine: AsyncEngine) -> None:
    # WR-02: a bound of 0 is out of domain (stake must be > 0).
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(min_stake="0", max_stake="500"),
                headers=_auth(token),
            )
        assert resp.status_code == 422, resp.text
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)


async def test_update_zero_stake_bound_returns_422(engine: AsyncEngine) -> None:
    await _seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await _client() as c:
            token = await _get_admin_token(c)
            create_resp = await c.post(
                "/api/v1/admin/markets",
                json=_market_body(),
                headers=_auth(token),
            )
            market_id = create_resp.json()["id"]
            resp = await c.patch(
                f"/api/v1/admin/markets/{market_id}",
                json={"max_stake": "0"},
                headers=_auth(token),
            )
        assert resp.status_code == 422, resp.text
    finally:
        await _cleanup_user(engine, _ADMIN_EMAIL)
