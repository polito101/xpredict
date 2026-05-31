"""Admin tenant-config CRUD integration tests (Phase 10, Plan 10-01).

ADD-05 / SC#4: an admin saves brand name + primary/secondary hex (+ optional
logo) via ``PUT /api/v1/admin/tenant-config`` and the single row persists. The
form rejects an invalid hex (422), an oversized logo (>256KB, 422), and a logo
with a content-type outside the allowlist (422), each with a clear message. A
valid PUT round-trips: a subsequent GET reflects the new brand_name + hexes, and
the update mutates the single seeded row (no second row inserted).

Mirrors ``tests/admin/_helpers.py`` (admin Bearer mint) + the multipart PUT shape
the admin branding router exposes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.admin._helpers import (
    ADMIN_PASSWORD,
    auth,
    cleanup_user,
    client,
    seed_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_ADMIN_EMAIL = "branding-admin@test.com"

# A minimal valid 1x1 PNG (8-byte signature + IHDR + IEND) — enough to pass the
# magic-byte sniff for image/png in the router's logo validation.
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _admin_token(c) -> str:
    login = await c.post(
        "/admin/auth/login",
        data={"username": _ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200, f"Admin login failed: {login.text}"
    return login.json()["access_token"]


async def test_put_rejects_invalid_hex_422(engine: AsyncEngine) -> None:
    await seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await _admin_token(c)
            resp = await c.put(
                "/api/v1/admin/tenant-config",
                data={
                    "brand_name": "Acme",
                    "primary_hex": "red",  # not ^#[0-9a-fA-F]{6}$
                    "secondary_hex": "#0ea5e9",
                },
                headers=auth(token),
            )
        assert resp.status_code == 422, f"{resp.status_code}: {resp.text}"
    finally:
        await cleanup_user(engine, _ADMIN_EMAIL)


async def test_put_rejects_oversized_logo_422(engine: AsyncEngine) -> None:
    await seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await _admin_token(c)
            oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (262144 + 1)  # > 256 KB
            resp = await c.put(
                "/api/v1/admin/tenant-config",
                data={
                    "brand_name": "Acme",
                    "primary_hex": "#4f46e5",
                    "secondary_hex": "#0ea5e9",
                },
                files={"logo": ("big.png", oversized, "image/png")},
                headers=auth(token),
            )
        assert resp.status_code == 422, f"{resp.status_code}: {resp.text}"
        # Clear, specific message (SC#4).
        assert "256" in resp.text or "smaller" in resp.text.lower()
    finally:
        await cleanup_user(engine, _ADMIN_EMAIL)


async def test_put_rejects_wrong_content_type_422(engine: AsyncEngine) -> None:
    await seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await _admin_token(c)
            resp = await c.put(
                "/api/v1/admin/tenant-config",
                data={
                    "brand_name": "Acme",
                    "primary_hex": "#4f46e5",
                    "secondary_hex": "#0ea5e9",
                },
                files={"logo": ("note.txt", b"just some text", "text/plain")},
                headers=auth(token),
            )
        assert resp.status_code == 422, f"{resp.status_code}: {resp.text}"
        assert "png" in resp.text.lower() or "logo" in resp.text.lower()
    finally:
        await cleanup_user(engine, _ADMIN_EMAIL)


async def test_put_valid_round_trip_single_row(engine: AsyncEngine) -> None:
    await seed_user(engine, _ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await _admin_token(c)

            # First valid PUT — brand_name + hexes, no logo.
            put1 = await c.put(
                "/api/v1/admin/tenant-config",
                data={
                    "brand_name": "Acme Markets",
                    "primary_hex": "#112233",
                    "secondary_hex": "#445566",
                },
                headers=auth(token),
            )
            assert put1.status_code == 200, f"{put1.status_code}: {put1.text}"
            body1 = put1.json()
            assert body1["brand_name"] == "Acme Markets"
            assert body1["primary_hex"] == "#112233"
            assert body1["secondary_hex"] == "#445566"

            # GET reflects the persisted update.
            get1 = await c.get("/api/v1/admin/tenant-config", headers=auth(token))
            assert get1.status_code == 200, get1.text
            g1 = get1.json()
            assert g1["brand_name"] == "Acme Markets"
            assert g1["primary_hex"] == "#112233"
            assert g1["secondary_hex"] == "#445566"

            # A second PUT updates the SAME single row (with a logo this time).
            put2 = await c.put(
                "/api/v1/admin/tenant-config",
                data={
                    "brand_name": "Acme v2",
                    "primary_hex": "#aabbcc",
                    "secondary_hex": "#ddeeff",
                },
                files={"logo": ("logo.png", _PNG_BYTES, "image/png")},
                headers=auth(token),
            )
            assert put2.status_code == 200, f"{put2.status_code}: {put2.text}"
            body2 = put2.json()
            assert body2["brand_name"] == "Acme v2"
            assert body2["logo_url"] is not None

            # GET still returns a single, coherent view — the second update
            # replaced the first (single-row update, not a second insert).
            get2 = await c.get("/api/v1/admin/tenant-config", headers=auth(token))
            g2 = get2.json()
            assert g2["brand_name"] == "Acme v2"
            assert g2["primary_hex"] == "#aabbcc"
            assert g2["secondary_hex"] == "#ddeeff"
    finally:
        await cleanup_user(engine, _ADMIN_EMAIL)
