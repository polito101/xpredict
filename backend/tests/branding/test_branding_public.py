"""Public branding endpoint integration tests (Phase 10, Plan 10-01).

ADD-06 (backend half): ``GET /branding/current`` is public (no auth) and returns
exactly {brand_name, primary_hex, secondary_hex, logo_url} — no bytes, no
tenant_id, no timestamps (Pitfall 7 / T-10-06). ``GET /branding/logo`` serves the
stored bytes with the stored Content-Type + ``X-Content-Type-Options: nosniff``
when a logo is set, or 404 when none is set (T-10-02).

The migration seeds a default singleton row (XPredict / #4f46e5 / #0ea5e9, no
logo), so these public reads work against a fresh DB with no admin write.
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

_ADMIN_EMAIL = "branding-public-admin@test.com"

_EXPECTED_PUBLIC_FIELDS = {"brand_name", "primary_hex", "secondary_hex", "logo_url"}

_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_branding_current_is_public_and_minimal(engine: AsyncEngine) -> None:
    # No auth header — the endpoint is intentionally public (D-12).
    async with await client() as c:
        resp = await c.get("/branding/current")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # EXACT field set — no sensitive/extra fields leaked (T-10-06).
    assert set(body.keys()) == _EXPECTED_PUBLIC_FIELDS, body.keys()
    assert isinstance(body["brand_name"], str)
    assert isinstance(body["primary_hex"], str)
    assert isinstance(body["secondary_hex"], str)
    # No bytes inlined into the JSON payload (Pitfall 7).
    assert "logo_bytes" not in body


async def test_branding_logo_serves_bytes_with_nosniff(engine: AsyncEngine) -> None:
    await seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            login = await c.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            token = login.json()["access_token"]
            # Set a logo via the admin PUT so the public logo route has bytes.
            put = await c.put(
                "/api/v1/admin/tenant-config",
                data={
                    "brand_name": "Logo Co",
                    "primary_hex": "#123456",
                    "secondary_hex": "#654321",
                },
                files={"logo": ("logo.png", _PNG_BYTES, "image/png")},
                headers=auth(token),
            )
            assert put.status_code == 200, put.text

            # Public, unauthenticated logo fetch.
            resp = await c.get("/branding/logo")
        assert resp.status_code == 200, resp.text
        assert resp.content == _PNG_BYTES
        assert resp.headers["content-type"].startswith("image/png")
        assert resp.headers.get("x-content-type-options") == "nosniff"

        # /current now advertises a logo_url.
        async with await client() as c:
            cur = await c.get("/branding/current")
        assert cur.json()["logo_url"] is not None
    finally:
        await cleanup_user(engine, _ADMIN_EMAIL)
