"""Integration tests for the admin user-detail surface (Phase 8, Plan 08-01).

Covers D-07: GET /users/{id} (profile + balance + transaction_count + bet_count),
404 for a missing user, and the paginated /transactions + /bets sub-resources.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from tests.admin._helpers import (
    ADMIN_EMAIL,
    auth,
    cleanup_user,
    client,
    get_admin_token,
    seed_bet,
    seed_transaction,
    seed_user,
    seed_wallet,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_user_detail_profile_balance_counts(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "detail-crm@test.com", display_name="Detail User")
    wallet_id = await seed_wallet(engine, uid, balance=Decimal("50.0000"))
    await seed_transaction(engine, wallet_id, amount=Decimal("50.0000"))
    await seed_bet(engine, uid, stake=Decimal("10.0000"))
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(f"/api/v1/admin/users/{uid}", headers=auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["email"] == "detail-crm@test.com"
        assert body["display_name"] == "Detail User"
        assert body["status"] == "active"
        assert isinstance(body["balance"], str)
        assert Decimal(body["balance"]) == Decimal("50.0000")
        assert body["transaction_count"] == 1
        assert body["bet_count"] == 1
        assert body["is_verified"] is True
    finally:
        await cleanup_user(engine, "detail-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_user_detail_404_for_missing_user(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(f"/api/v1/admin/users/{uuid4()}", headers=auth(token))
        assert resp.status_code == 404, resp.text
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_user_transactions_paginated(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "tx-crm@test.com")
    wallet_id = await seed_wallet(engine, uid, balance=Decimal("100.0000"))
    await seed_transaction(engine, wallet_id, amount=Decimal("40.0000"), reason="first")
    await seed_transaction(engine, wallet_id, amount=Decimal("60.0000"), reason="second")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(
                f"/api/v1/admin/users/{uid}/transactions?page=1&page_size=10",
                headers=auth(token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        item = body["items"][0]
        assert isinstance(item["amount"], str)
        assert item["kind"] == "recharge"
        assert item["reason"] in {"first", "second"}
    finally:
        await cleanup_user(engine, "tx-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_user_transactions_empty_without_wallet(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "notx-crm@test.com")  # no wallet
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(f"/api/v1/admin/users/{uid}/transactions", headers=auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
    finally:
        await cleanup_user(engine, "notx-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_user_bets_paginated(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "bets-crm@test.com")
    await seed_bet(engine, uid, stake=Decimal("10.0000"), status="PENDING")
    await seed_bet(
        engine, uid, stake=Decimal("20.0000"), odds=Decimal("0.500000"), status="SETTLED_WON"
    )
    await seed_bet(engine, uid, stake=Decimal("30.0000"), status="SETTLED_LOST")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(
                f"/api/v1/admin/users/{uid}/bets?page=1&page_size=10", headers=auth(token)
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
        by_status = {item["status"]: item for item in body["items"]}
        # Pending bet has no realized P&L.
        assert by_status["PENDING"]["pnl"] is None
        # Won bet: 20 / 0.5 = 40 payout -> pnl = +20.
        assert Decimal(by_status["SETTLED_WON"]["pnl"]) == Decimal("20.0000")
        # Lost bet: pnl = -stake.
        assert Decimal(by_status["SETTLED_LOST"]["pnl"]) == Decimal("-30.0000")
        # Money is a JSON string.
        assert isinstance(by_status["PENDING"]["stake"], str)
    finally:
        await cleanup_user(engine, "bets-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)
