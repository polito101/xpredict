"""Negative-auth tests for the admin tenant-config endpoints (Phase 10, Plan 10-01).

SC#6 / D-12: every ``/api/v1/admin/tenant-config`` route must be 401 without a
Bearer and 403 with a non-admin (player) Bearer. Mirrors the Phase 8 admin-CRM
negative-auth pattern (``tests/admin/test_auth_negative.py``) verbatim, swapping
``_routes()`` for the GET + PUT tenant-config routes and extending ``_call`` with
a PUT branch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.admin._helpers import ADMIN_PASSWORD, auth, cleanup_user, client, seed_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_PLAYER_EMAIL = "branding-player-negative@test.com"

# A valid PUT body so the 403/401 wall is reached on access control, not on
# request validation (a malformed body could short-circuit to 422 before auth).
_VALID_PUT = {
    "brand_name": "x",
    "primary_hex": "#000000",
    "secondary_hex": "#ffffff",
}


def _routes() -> list[tuple[str, str, dict | None]]:
    """(method, path, json_body) for every admin tenant-config endpoint."""
    return [
        ("GET", "/api/v1/admin/tenant-config", None),
        ("PUT", "/api/v1/admin/tenant-config", _VALID_PUT),
    ]


async def _call(c, method: str, path: str, body: dict | None, headers: dict | None = None):
    if method == "GET":
        return await c.get(path, headers=headers)
    if method == "PUT":
        # The PUT accepts multipart/form-data (brand_name/hexes + optional logo),
        # so send the body as form data, not JSON. Auth is evaluated before the
        # form is parsed, so the negative-auth wall is unaffected by the encoding.
        return await c.put(path, data=body, headers=headers)
    return await c.post(path, json=body, headers=headers)


async def test_all_endpoints_401_without_token() -> None:
    async with await client() as c:
        for method, path, body in _routes():
            resp = await _call(c, method, path, body)
            assert resp.status_code == 401, f"{method} {path} -> {resp.status_code} (expected 401)"


async def test_all_endpoints_403_with_player_token(engine: AsyncEngine) -> None:
    await seed_user(engine, _PLAYER_EMAIL, is_superuser=False)
    try:
        async with await client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _PLAYER_EMAIL, "password": ADMIN_PASSWORD},
            )
            # A non-superuser must NOT get an admin Bearer (AUTH-07). If the admin
            # login itself rejects the player, that is the 401/400 wall (the same
            # accepted branch as tests/admin/test_auth_negative.py).
            if login.status_code != 200:
                assert login.status_code in (400, 401)
                return
            token = login.json()["access_token"]
            for method, path, body in _routes():
                resp = await _call(c, method, path, body, headers=auth(token))
                assert resp.status_code == 403, (
                    f"{method} {path} -> {resp.status_code} (expected 403)"
                )
    finally:
        await cleanup_user(engine, _PLAYER_EMAIL)
