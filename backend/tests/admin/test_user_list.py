"""Integration tests for GET /api/v1/admin/users (Phase 8, Plan 08-01).

Covers D-05: pagination envelope, ILIKE search (email + display_name), status
filter, sort, balance via LEFT JOIN (no N+1), and ILIKE wildcard escaping
(T-08-03 / Pitfall 3).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from tests.admin._helpers import (
    ADMIN_EMAIL,
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


async def test_list_users_paginated_envelope(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/users?page=1&page_size=5", headers=auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("items", "total", "page", "page_size", "pages"):
            assert key in body, f"missing {key}"
        assert body["page"] == 1
        assert body["page_size"] == 5
        assert isinstance(body["items"], list)
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_search_by_email(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    await seed_user(engine, "alice-crm@test.com", display_name="Alice")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/users?search=alice-crm", headers=auth(token))
        assert resp.status_code == 200, resp.text
        emails = {item["email"] for item in resp.json()["items"]}
        assert "alice-crm@test.com" in emails
        assert ADMIN_EMAIL not in emails
    finally:
        await cleanup_user(engine, "alice-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_search_by_display_name(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    await seed_user(engine, "bob-crm@test.com", display_name="Bobby Unique Name")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(
                "/api/v1/admin/users?search=Bobby Unique", headers=auth(token)
            )
        assert resp.status_code == 200, resp.text
        emails = {item["email"] for item in resp.json()["items"]}
        assert "bob-crm@test.com" in emails
    finally:
        await cleanup_user(engine, "bob-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_status_filter_banned(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    await seed_user(engine, "banned-crm@test.com", banned=True)
    await seed_user(engine, "active-crm@test.com", banned=False)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/users?status=banned", headers=auth(token))
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert all(item["status"] == "banned" for item in items)
        emails = {item["email"] for item in items}
        assert "banned-crm@test.com" in emails
        assert "active-crm@test.com" not in emails
    finally:
        await cleanup_user(engine, "banned-crm@test.com")
        await cleanup_user(engine, "active-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_status_filter_active(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    await seed_user(engine, "banned2-crm@test.com", banned=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/users?status=active", headers=auth(token))
        assert resp.status_code == 200, resp.text
        emails = {item["email"] for item in resp.json()["items"]}
        assert "banned2-crm@test.com" not in emails
    finally:
        await cleanup_user(engine, "banned2-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_sort_by_email_asc(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(
                "/api/v1/admin/users?sort_by=email&sort_order=asc&page_size=100",
                headers=auth(token),
            )
        assert resp.status_code == 200, resp.text
        emails = [item["email"] for item in resp.json()["items"]]
        assert emails == sorted(emails)
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_includes_balance(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, "rich-crm@test.com")
    await seed_wallet(engine, uid, balance=Decimal("123.4500"))
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/users?search=rich-crm", headers=auth(token))
        assert resp.status_code == 200, resp.text
        item = next(i for i in resp.json()["items"] if i["email"] == "rich-crm@test.com")
        # Money is a JSON string, never a float (SC#4 discipline).
        assert isinstance(item["balance"], str)
        assert Decimal(item["balance"]) == Decimal("123.4500")
    finally:
        await cleanup_user(engine, "rich-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_balance_defaults_zero_without_wallet(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    await seed_user(engine, "nowallet-crm@test.com")  # no wallet seeded
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/users?search=nowallet-crm", headers=auth(token))
        assert resp.status_code == 200, resp.text
        item = next(i for i in resp.json()["items"] if i["email"] == "nowallet-crm@test.com")
        assert Decimal(item["balance"]) == Decimal("0")
    finally:
        await cleanup_user(engine, "nowallet-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_list_users_ilike_wildcard_escaped(engine: AsyncEngine) -> None:
    """A search containing % must not behave as a wildcard (T-08-03)."""
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    await seed_user(engine, "literal-crm@test.com", display_name="NoPercentHere")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            # "%" would match everything if unescaped; escaped it matches nothing.
            resp = await c.get("/api/v1/admin/users?search=%25", headers=auth(token))
        assert resp.status_code == 200, resp.text
        emails = {item["email"] for item in resp.json()["items"]}
        # The literal user (no "%" in email/display_name) must NOT be returned.
        assert "literal-crm@test.com" not in emails
    finally:
        await cleanup_user(engine, "literal-crm@test.com")
        await cleanup_user(engine, ADMIN_EMAIL)
