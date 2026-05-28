"""SC#4 / WAL-03 / WAL-04 — player wallet reads serialize money as JSON strings.

Integration tests over the live app + testcontainer Postgres. They prove the
player read surface (Plan 03-05) is:

  - **Money-as-string (SC#4):** ``GET /wallet/me/balance`` returns a body whose
    ``balance`` is a JSON STRING (both ``isinstance(..., str)`` AND a quoted
    substring in the raw response text), never a float; and every history
    ``amount`` from ``GET /wallet/me/transactions`` is likewise a string.
  - **Paginated (WAL-04):** with more entries than ``page_size``, page 1 and
    page 2 return DISJOINT slices and ``has_next`` flips correctly.
  - **Cookie-gated (T-03-18):** an unauthenticated GET returns 401.

These drive the app over its OWN request session (the ``get_async_session``
dependency commits to the real DB), so — exactly like ``test_recharge.py`` —
history is created via the real admin recharge endpoint and assertions read the
committed state. Isolation is by a UNIQUE email per test (the immutable ledger
is never deleted; the 03-02 discipline of scoping to the run's own wallet
applies). The player is registered (wallet auto-created, SC#1), marked verified
in the DB (``current_active_player`` gates ``verified=True``), then logged in so
the ``xpredict_session`` cookie rides on the same client for the reads.
"""

from __future__ import annotations

import contextlib
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import text

from app.db.session import _get_session_maker

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_ADMIN_EMAIL = "wallet-read-admin@example.com"
_ADMIN_PASSWORD = "Wallet-Read-Admin-1!"
_PLAYER_PASSWORD = "Valid-Pass-1234"


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` for its side effects (container, migrate, env rewrite).

    The read surface uses its own request session and we assert against committed
    state, so we don't take the rollback ``async_session`` — but the production
    engine factory must see the rewritten ``DATABASE_URL`` first (mirrors
    ``test_recharge.py``).
    """
    return engine


@pytest.fixture(autouse=True)
def _reset_rate_limit_storage():
    """Clear slowapi's in-memory rate-limit storage before each test.

    Each test registers a player (``/auth/register``, 5/min per-IP), logs the
    player in (``/auth/login``), and logs an admin in (``/admin/auth/login``,
    5/min per-IP) from 127.0.0.1; without a per-test reset the shared
    ``memory://`` counter accumulates and a later call trips a 429. Mirrors
    ``tests/wallet/test_recharge.py``'s autouse reset.
    """
    from app.auth.rate_limit import limiter

    try:
        limiter._limiter.reset()
    except Exception:
        with contextlib.suppress(Exception):
            limiter._storage.reset()
    yield


def _client() -> httpx.AsyncClient:
    """An httpx client wired to the FastAPI app under test (cookies persist on it)."""
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ----------------------------------------------------------------------
# Seed / setup / cleanup helpers (own committed sessions).
# ----------------------------------------------------------------------
async def _seed_admin() -> None:
    """Idempotently UPSERT the recharge admin (is_superuser=True, is_verified=True)."""
    from pwdlib import PasswordHash

    hashed = PasswordHash.recommended().hash(_ADMIN_PASSWORD)
    session_maker = _get_session_maker()
    async with session_maker() as s, s.begin():
        await s.execute(
            text("DELETE FROM users WHERE email = :em"), {"em": _ADMIN_EMAIL}
        )
        await s.execute(
            text(
                "INSERT INTO users "
                "(email, hashed_password, is_active, is_superuser, "
                " is_verified, display_name, token_version) "
                "VALUES (:em, :pw, TRUE, TRUE, TRUE, 'Wallet Read Admin', 0)"
            ),
            {"em": _ADMIN_EMAIL, "pw": hashed},
        )


async def _delete_user(email: str) -> None:
    """Delete a user row by email (own committed session).

    ``accounts.owner_id`` is a plain column (NOT a FK to users), so deleting the
    user never cascades to / is blocked by the wallet; the immutable wallet +
    entries are intentionally left behind. Isolation is by the unique email per
    test, per the 03-02 discipline.
    """
    session_maker = _get_session_maker()
    async with session_maker() as s, s.begin():
        await s.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})


async def _set_verified(email: str) -> None:
    """Mark a player verified so ``current_active_player`` (verified=True) accepts."""
    session_maker = _get_session_maker()
    async with session_maker() as s, s.begin():
        await s.execute(
            text("UPDATE users SET is_verified = TRUE WHERE email = :em"),
            {"em": email},
        )


async def _register_verified_player(client: httpx.AsyncClient, email: str) -> UUID:
    """Register a player (wallet auto-created, SC#1), then mark verified."""
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": _PLAYER_PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    await _set_verified(email)
    return uuid.UUID(resp.json()["id"])


async def _login_player(client: httpx.AsyncClient, email: str) -> None:
    """Log the player in so the ``xpredict_session`` cookie rides on ``client``."""
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _PLAYER_PASSWORD},
    )
    assert resp.status_code in (200, 204), resp.text


async def _admin_bearer(client: httpx.AsyncClient) -> str:
    """Log the seeded admin in and return its Bearer access token."""
    resp = await client.post(
        "/admin/auth/login",
        data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _recharge(
    client: httpx.AsyncClient,
    *,
    user_id: UUID,
    token: str,
    amount: str,
    key: str,
) -> None:
    """Create one history entry on the player's wallet via the admin recharge endpoint."""
    resp = await client.post(
        f"/admin/wallets/{user_id}/recharge",
        json={"amount": amount, "reason": "promo"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )
    assert resp.status_code == 200, resp.text


# ----------------------------------------------------------------------
# 1) Balance is a JSON string (SC#4 / WAL-03)
# ----------------------------------------------------------------------
async def test_balance_is_json_string() -> None:
    """``GET /wallet/me/balance`` returns ``balance`` as a JSON string, not a float."""
    email = f"wallet-bal-{uuid.uuid4().hex[:8]}@example.com"
    key = f"wr-bal-{uuid.uuid4().hex}"
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_verified_player(client, email)
            token = await _admin_bearer(client)
            await _recharge(
                client, user_id=user_id, token=token, amount="100.0000", key=key
            )
            await _login_player(client, email)

            resp = await client.get("/wallet/me/balance")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Parsed value is a str (not a float).
        assert isinstance(body["balance"], str)
        assert body["currency"] == "PLAY_USD"
        # The recharge credited 100.0000 — value is exact (Decimal end-to-end).
        assert Decimal(body["balance"]) == Decimal("100.0000")
        # And the raw bytes carry it quoted — a float would be unquoted.
        assert '"balance":"100.0000"' in resp.text.replace(" ", "")
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 2) Every transaction amount is a JSON string (SC#4 / WAL-04)
# ----------------------------------------------------------------------
async def test_transaction_amounts_are_json_strings() -> None:
    """``GET /wallet/me/transactions`` items each carry ``amount`` as a JSON string."""
    email = f"wallet-tx-{uuid.uuid4().hex[:8]}@example.com"
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_verified_player(client, email)
            token = await _admin_bearer(client)
            await _recharge(
                client,
                user_id=user_id,
                token=token,
                amount="40.0000",
                key=f"wr-tx-{uuid.uuid4().hex}",
            )
            await _recharge(
                client,
                user_id=user_id,
                token=token,
                amount="60.0000",
                key=f"wr-tx-{uuid.uuid4().hex}",
            )
            await _login_player(client, email)

            resp = await client.get("/wallet/me/transactions")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 2
        assert len(body["items"]) >= 2
        for item in body["items"]:
            assert isinstance(item["amount"], str), item
            assert item["direction"] in ("debit", "credit")
            assert item["kind"] == "recharge"
            assert item["reason"] == "promo"
        # No bare-float amount anywhere in the raw response.
        compact = resp.text.replace(" ", "")
        assert '"amount":"40.0000"' in compact
        assert '"amount":"60.0000"' in compact
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 3) Pagination — disjoint pages + correct has_next (WAL-04)
# ----------------------------------------------------------------------
async def test_transactions_paginated() -> None:
    """With > page_size entries, page 1 / page 2 are disjoint; has_next is correct."""
    email = f"wallet-pg-{uuid.uuid4().hex[:8]}@example.com"
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_verified_player(client, email)
            token = await _admin_bearer(client)
            # Three distinct recharges → three credit entries on the wallet.
            for amt in ("11.0000", "22.0000", "33.0000"):
                await _recharge(
                    client,
                    user_id=user_id,
                    token=token,
                    amount=amt,
                    key=f"wr-pg-{uuid.uuid4().hex}",
                )
            await _login_player(client, email)

            p1 = await client.get("/wallet/me/transactions?page=1&page_size=2")
            p2 = await client.get("/wallet/me/transactions?page=2&page_size=2")
        assert p1.status_code == 200, p1.text
        assert p2.status_code == 200, p2.text
        b1, b2 = p1.json(), p2.json()

        # total counts all three entries.
        assert b1["total"] == 3
        assert b2["total"] == 3
        # page 1 = 2 items + has_next; page 2 = 1 item + no has_next.
        assert len(b1["items"]) == 2
        assert b1["page"] == 1
        assert b1["page_size"] == 2
        assert b1["has_next"] is True
        assert len(b2["items"]) == 1
        assert b2["page"] == 2
        assert b2["has_next"] is False

        # The two pages are disjoint: page-1 amounts and page-2 amount don't overlap.
        p1_amounts = [i["amount"] for i in b1["items"]]
        p2_amounts = [i["amount"] for i in b2["items"]]
        assert set(p1_amounts).isdisjoint(p2_amounts)
        # All three amounts are accounted for across the two pages.
        assert sorted(p1_amounts + p2_amounts) == ["11.0000", "22.0000", "33.0000"]
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 4) Unauthenticated read → 401 (T-03-18 — no cross-user / no anon read)
# ----------------------------------------------------------------------
async def test_player_cannot_read_without_auth() -> None:
    """A GET with no session cookie returns 401 on both read endpoints."""
    async with _client() as client:
        bal = await client.get("/wallet/me/balance")
        txs = await client.get("/wallet/me/transactions")
    assert bal.status_code == 401, bal.text
    assert txs.status_code == 401, txs.text
