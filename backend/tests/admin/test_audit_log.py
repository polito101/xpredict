"""Integration tests for the audit-log viewer (Phase 8, Plan 08-02, ADD-04).

Covers D-11/D-12/D-13: paginated read (default page_size=50), event_type exact
filter, actor ILIKE substring (with wildcard escape — T-08-08), date range,
newest-first ordering, JSONB payload returned as a raw JSON object, the
``/event-types`` dropdown list, the 401/403 auth wall (T-08-06), and the
read-only guarantee — no POST/PUT/PATCH/DELETE exists (T-08-07).

``audit_log`` is append-only (no cleanup possible), so each test seeds rows with
a UNIQUE event_type / actor marker (uuid suffix) and scopes its assertions to
those rows — they never collide with other tests' rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from app.core.audit.schemas import KNOWN_EVENT_TYPES
from tests.admin._helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    auth,
    cleanup_user,
    client,
    get_admin_token,
    seed_audit,
    seed_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_audit_log_paginated_envelope_and_default_page_size(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    marker = f"test.envelope.{uuid4().hex}"
    await seed_audit(event_type=marker, payload={"k": "v"})
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/audit-log", headers=auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("items", "total", "page", "page_size", "pages"):
            assert key in body, f"missing {key}"
        # D-11: default page_size is 50.
        assert body["page_size"] == 50
        assert body["page"] == 1
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_audit_entry_shape_includes_payload_as_json_object(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    marker = f"test.shape.{uuid4().hex}"
    payload = {"target_user_id": str(uuid4()), "reason": "spam"}
    await seed_audit(event_type=marker, actor="user:abc", payload=payload, ip="203.0.113.7")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(f"/api/v1/admin/audit-log?event_type={marker}", headers=auth(token))
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1, items
        entry = items[0]
        for key in ("id", "occurred_at", "event_type", "actor", "payload", "ip"):
            assert key in entry, f"missing {key}"
        # D-12: payload is a raw JSON object (dict), not a string.
        assert isinstance(entry["payload"], dict)
        assert entry["payload"] == payload
        assert entry["actor"] == "user:abc"
        assert entry["ip"] == "203.0.113.7"
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_audit_log_filter_by_event_type_exact(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    keep = f"test.keep.{uuid4().hex}"
    drop = f"test.drop.{uuid4().hex}"
    await seed_audit(event_type=keep, payload={})
    await seed_audit(event_type=drop, payload={})
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(f"/api/v1/admin/audit-log?event_type={keep}", headers=auth(token))
        assert resp.status_code == 200, resp.text
        types = {item["event_type"] for item in resp.json()["items"]}
        assert types == {keep}, types
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_audit_log_filter_by_actor_ilike(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    unique = uuid4().hex
    actor = f"user:ilike-{unique}"
    marker = f"test.actor.{unique}"
    await seed_audit(event_type=marker, actor=actor, payload={})
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            # Substring ILIKE: search for the unique fragment.
            resp = await c.get(f"/api/v1/admin/audit-log?actor=ilike-{unique}", headers=auth(token))
        assert resp.status_code == 200, resp.text
        actors = {item["actor"] for item in resp.json()["items"]}
        assert actor in actors, actors
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_audit_log_actor_wildcard_is_escaped(engine: AsyncEngine) -> None:
    """A literal '%' in the actor search must NOT act as a wildcard (T-08-08)."""
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    unique = uuid4().hex
    marker = f"test.escape.{unique}"
    # Seed an actor WITHOUT a percent sign.
    await seed_audit(event_type=marker, actor=f"user:plain-{unique}", payload={})
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            # Searching for a bare '%' must not match the plain actor (escaped).
            resp = await c.get(
                f"/api/v1/admin/audit-log?event_type={marker}&actor=%25",
                headers=auth(token),
            )
        assert resp.status_code == 200, resp.text
        # The plain actor has no '%', so an escaped-'%' search returns nothing.
        assert resp.json()["items"] == []
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_audit_log_date_range_filter(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    marker = f"test.daterange.{uuid4().hex}"
    await seed_audit(event_type=marker, payload={})
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            # A future-only window must exclude the just-seeded (now) row.
            resp_future = await c.get(
                f"/api/v1/admin/audit-log?event_type={marker}&date_from=2999-01-01",
                headers=auth(token),
            )
            # A wide past window must include it.
            resp_past = await c.get(
                f"/api/v1/admin/audit-log?event_type={marker}&date_from=2000-01-01",
                headers=auth(token),
            )
        assert resp_future.status_code == 200, resp_future.text
        assert resp_future.json()["items"] == []
        assert resp_past.status_code == 200, resp_past.text
        assert len(resp_past.json()["items"]) == 1
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_audit_log_ordered_newest_first(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    unique = uuid4().hex
    actor = f"user:order-{unique}"
    # Three rows sharing one actor; insertion order = chronological.
    await seed_audit(event_type=f"test.order.{uuid4().hex}", actor=actor, payload={"n": 1})
    await seed_audit(event_type=f"test.order.{uuid4().hex}", actor=actor, payload={"n": 2})
    await seed_audit(event_type=f"test.order.{uuid4().hex}", actor=actor, payload={"n": 3})
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(f"/api/v1/admin/audit-log?actor=order-{unique}", headers=auth(token))
        assert resp.status_code == 200, resp.text
        ours = [i for i in resp.json()["items"] if i["actor"] == actor]
        assert len(ours) == 3, ours
        occurred = [i["occurred_at"] for i in ours]
        # occurred_at DESC — newest first (monotonic non-increasing).
        assert occurred == sorted(occurred, reverse=True)
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


async def test_event_types_endpoint_returns_known_list(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/audit-log/event-types", headers=auth(token))
        assert resp.status_code == 200, resp.text
        types = resp.json()
        assert isinstance(types, list)
        assert len(types) >= 19
        assert types == KNOWN_EVENT_TYPES
        # Spot-check the Phase 8 ban events the viewer dropdown needs (D-13).
        assert "admin.user_banned" in types
        assert "admin.user_unbanned" in types
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


# --------------------------------------------------------------------------- #
# Read-only guarantee (T-08-07) — no mutation endpoints exist.
# --------------------------------------------------------------------------- #
async def test_audit_log_no_mutation_endpoints(engine: AsyncEngine) -> None:
    """POST/PUT/PATCH/DELETE on the audit routes must be 405 (read-only)."""
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            h = auth(token)
            for method in ("post", "put", "patch", "delete"):
                resp = await getattr(c, method)("/api/v1/admin/audit-log", headers=h)
                assert (
                    resp.status_code == 405
                ), f"{method.upper()} /audit-log -> {resp.status_code} (expected 405)"
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


# --------------------------------------------------------------------------- #
# Negative auth (T-08-06).
# --------------------------------------------------------------------------- #
_AUDIT_PATHS = [
    "/api/v1/admin/audit-log",
    "/api/v1/admin/audit-log/event-types",
]
_PLAYER_EMAIL = "audit-player@test.com"


async def test_audit_endpoints_401_without_token() -> None:
    async with await client() as c:
        for path in _AUDIT_PATHS:
            resp = await c.get(path)
            assert resp.status_code == 401, f"{path} -> {resp.status_code} (expected 401)"


async def test_audit_endpoints_403_with_player_token(engine: AsyncEngine) -> None:
    await seed_user(engine, _PLAYER_EMAIL, is_superuser=False)
    try:
        async with await client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _PLAYER_EMAIL, "password": ADMIN_PASSWORD},
            )
            if login.status_code != 200:
                assert login.status_code in (400, 401)
                return
            token = login.json()["access_token"]
            for path in _AUDIT_PATHS:
                resp = await c.get(path, headers=auth(token))
                assert resp.status_code == 403, f"{path} -> {resp.status_code} (expected 403)"
    finally:
        await cleanup_user(engine, _PLAYER_EMAIL)
