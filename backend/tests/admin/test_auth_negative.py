"""Negative-auth tests for every admin CRM endpoint (Phase 8, Plan 08-01).

T-08-01 / T-08-04: every ``/api/v1/admin/*`` route must be 401 without a Bearer
and 403 with a non-admin (player) Bearer. Mirrors the markets negative-auth
pattern (tests/markets/test_admin_router.py lines 115-140).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from tests.admin._helpers import ADMIN_PASSWORD, auth, cleanup_user, client, seed_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_PLAYER_EMAIL = "crm-player-negative@test.com"


def _routes(user_id: str) -> list[tuple[str, str, dict | None]]:
    """(method, path, json_body) for every admin CRM endpoint."""
    return [
        ("GET", "/api/v1/admin/users", None),
        ("GET", f"/api/v1/admin/users/{user_id}", None),
        ("POST", f"/api/v1/admin/users/{user_id}/ban", {"reason": "x"}),
        ("POST", f"/api/v1/admin/users/{user_id}/unban", {}),
        ("GET", f"/api/v1/admin/users/{user_id}/transactions", None),
        ("GET", f"/api/v1/admin/users/{user_id}/bets", None),
    ]


async def _call(c, method: str, path: str, body: dict | None, headers: dict | None = None):
    if method == "GET":
        return await c.get(path, headers=headers)
    return await c.post(path, json=body, headers=headers)


async def test_all_endpoints_401_without_token() -> None:
    uid = str(uuid4())
    async with await client() as c:
        for method, path, body in _routes(uid):
            resp = await _call(c, method, path, body)
            assert resp.status_code == 401, f"{method} {path} -> {resp.status_code} (expected 401)"


async def test_all_endpoints_403_with_player_token(engine: AsyncEngine) -> None:
    await seed_user(engine, _PLAYER_EMAIL, is_superuser=False)
    uid = str(uuid4())
    try:
        async with await client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _PLAYER_EMAIL, "password": ADMIN_PASSWORD},
            )
            # A non-superuser must NOT get an admin Bearer (AUTH-07). If the
            # admin login itself rejects the player, that is the 401/400 wall.
            if login.status_code != 200:
                assert login.status_code in (400, 401)
                return
            token = login.json()["access_token"]
            for method, path, body in _routes(uid):
                resp = await _call(c, method, path, body, headers=auth(token))
                assert resp.status_code == 403, (
                    f"{method} {path} -> {resp.status_code} (expected 403)"
                )
    finally:
        await cleanup_user(engine, _PLAYER_EMAIL)
