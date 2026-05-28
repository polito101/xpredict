"""Admin recharge endpoint integration tests (Phase 3, Plan 03-04).

Proves ``POST /admin/wallets/{user_id}/recharge`` is:
  - **Correct (SC#3 part 1):** a recharge credits the path user's wallet by the
    amount, books exactly one transfer + one debit/credit entry-pair, and debits
    ``house_promo`` by the same amount.
  - **Idempotent (SC#3):** a second POST with the same ``Idempotency-Key`` returns
    the SAME ``transfer_id``, credits the wallet ONCE, and leaves a single transfer
    row (no double-credit). A DIFFERENT key produces a second transfer.
  - **Admin-only (T-03-13 / AUTH-07):** no Bearer (or a player cookie) → 401/403.
  - **A3:** a missing ``Idempotency-Key`` header → 400.
  - **Money-as-string (SC#4):** the response ``amount`` is a JSON string.

These drive the app over its OWN request session (the ``get_async_session``
dependency commits to the real testcontainer DB), so — exactly like
``test_wallet_creation.py`` — assertions run against committed state via fresh
``_get_session_maker()`` sessions, and isolation comes from a UNIQUE email +
UNIQUE idempotency key per test (the immutable ledger is never deleted; the
03-02 discipline of scoping assertions to the run's own wallet / key applies).
"""

from __future__ import annotations

import contextlib
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import func, select, text

from app.db.session import _get_session_maker
from app.wallet.constants import (
    DIRECTION_CREDIT,
    DIRECTION_DEBIT,
    HOUSE_PROMO_ACCOUNT_ID,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
)
from app.wallet.models import Account, Entry, Transfer

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_ADMIN_EMAIL = "recharge-admin@example.com"
_ADMIN_PASSWORD = "Recharge-Admin-1!"


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` for its side effects (container, migrate, env rewrite).

    The recharge surface uses its own request session and we assert against
    committed state with ``_get_session_maker()``, so we don't take the rollback
    ``async_session`` — but the production engine factory must see the rewritten
    ``DATABASE_URL`` first (mirrors ``test_wallet_creation.py``).
    """
    return engine


@pytest.fixture(autouse=True)
def _reset_rate_limit_storage():
    """Clear slowapi's in-memory rate-limit storage before each test.

    Each recharge test registers a player (``/auth/register``, 5/min per-IP) AND
    logs an admin in (``/admin/auth/login``, 5/min per-IP) from 127.0.0.1; without
    a per-test reset the shared ``memory://`` counter accumulates across tests and
    a later register/login trips a 429. Mirrors ``tests/auth/conftest.py``'s
    autouse reset (that conftest is not inherited by ``tests/wallet``).
    """
    from app.auth.rate_limit import limiter

    try:
        limiter._limiter.reset()
    except Exception:
        with contextlib.suppress(Exception):
            limiter._storage.reset()
    yield


def _client() -> httpx.AsyncClient:
    """An httpx client wired to the FastAPI app under test."""
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ----------------------------------------------------------------------
# Seed / lookup / cleanup helpers (own committed sessions — the rows are
# committed by the request, not the rollback async_session).
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
                "VALUES (:em, :pw, TRUE, TRUE, TRUE, 'Recharge Admin', 0)"
            ),
            {"em": _ADMIN_EMAIL, "pw": hashed},
        )


async def _delete_user(email: str) -> None:
    """Delete a user row by email (own committed session).

    ``accounts.owner_id`` is a plain column (NOT a FK to users), so deleting the
    user never cascades to / is blocked by the wallet. The wallet account and its
    immutable entries are intentionally left behind (the ledger is append-only);
    isolation is by the unique owner / idempotency key per test, per the 03-02
    discipline.
    """
    session_maker = _get_session_maker()
    async with session_maker() as s, s.begin():
        await s.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})


async def _register_player(client: httpx.AsyncClient, email: str) -> UUID:
    """Register a player via the real flow → returns the new user id (wallet auto-created)."""
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": "Valid-Pass-1234"},
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


async def _admin_bearer(client: httpx.AsyncClient) -> str:
    """Log the seeded admin in and return its Bearer access token."""
    resp = await client.post(
        "/admin/auth/login",
        data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _wallet_id_for(user_id: UUID) -> UUID:
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return (
            await s.execute(
                select(Account.id).where(
                    Account.owner_type == OWNER_USER,
                    Account.owner_id == user_id,
                    Account.kind == KIND_USER_WALLET,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one()


async def _balance(account_id: UUID) -> Decimal:
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return (
            await s.execute(select(Account.balance).where(Account.id == account_id))
        ).scalar_one()


async def _entries_for_transfer(transfer_id: UUID) -> list[Entry]:
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return list(
            (
                await s.execute(
                    select(Entry).where(Entry.transfer_id == transfer_id)
                )
            )
            .scalars()
            .all()
        )


async def _transfer_count_for_key(idempotency_key: str) -> int:
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return int(
            (
                await s.execute(
                    select(func.count())
                    .select_from(Transfer)
                    .where(Transfer.idempotency_key == idempotency_key)
                )
            ).scalar_one()
        )


# ----------------------------------------------------------------------
# 1) Recharge credits the wallet — one transfer + one entry-pair (SC#3 part 1)
# ----------------------------------------------------------------------
async def test_recharge_credits_wallet() -> None:
    """Admin recharge increases the balance by amount; one transfer, one pair; house debited."""
    email = f"recharge-credit-{uuid.uuid4().hex[:8]}@example.com"
    key = f"rc-credit-{uuid.uuid4().hex}"
    amount = Decimal("100.0000")
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_player(client, email)
            token = await _admin_bearer(client)
            wallet_id = await _wallet_id_for(user_id)

            balance_before = await _balance(wallet_id)
            house_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)

            resp = await client.post(
                f"/admin/wallets/{user_id}/recharge",
                json={"amount": "100.0000", "reason": "promo"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": key,
                },
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        transfer_id = uuid.UUID(body["transfer_id"])
        assert body["currency"] == PLAY_USD
        assert body["idempotent_replay"] is False

        # Balance credited by exactly the amount.
        assert await _balance(wallet_id) == balance_before + amount
        # House debited by the same amount.
        assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == house_before - amount

        # Exactly one transfer for this key; one debit + one credit entry.
        assert await _transfer_count_for_key(key) == 1
        entries = await _entries_for_transfer(transfer_id)
        assert len(entries) == 2
        directions = {e.direction for e in entries}
        assert directions == {DIRECTION_DEBIT, DIRECTION_CREDIT}
        for e in entries:
            assert e.amount == amount
        debit = next(e for e in entries if e.direction == DIRECTION_DEBIT)
        credit = next(e for e in entries if e.direction == DIRECTION_CREDIT)
        assert debit.account_id == HOUSE_PROMO_ACCOUNT_ID
        assert credit.account_id == wallet_id
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 2) Same Idempotency-Key → same transfer, credited once (SC#3)
# ----------------------------------------------------------------------
async def test_recharge_idempotent_same_key() -> None:
    """Two POSTs with the SAME key return the same transfer_id; credited once."""
    email = f"recharge-idem-{uuid.uuid4().hex[:8]}@example.com"
    key = f"rc-idem-{uuid.uuid4().hex}"
    amount = Decimal("50.0000")
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_player(client, email)
            token = await _admin_bearer(client)
            wallet_id = await _wallet_id_for(user_id)
            balance_before = await _balance(wallet_id)
            headers = {
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": key,
            }
            body = {"amount": "50.0000", "reason": "promo"}

            first = await client.post(
                f"/admin/wallets/{user_id}/recharge", json=body, headers=headers
            )
            second = await client.post(
                f"/admin/wallets/{user_id}/recharge", json=body, headers=headers
            )

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["transfer_id"] == second.json()["transfer_id"]
        # The first is a fresh apply, the second a replay.
        assert first.json()["idempotent_replay"] is False
        assert second.json()["idempotent_replay"] is True

        # Credited exactly ONCE despite two POSTs, and a single transfer row.
        assert await _balance(wallet_id) == balance_before + amount
        assert await _transfer_count_for_key(key) == 1
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 3) Different Idempotency-Key → a second transfer (not deduped)
# ----------------------------------------------------------------------
async def test_recharge_different_key_credits_again() -> None:
    """A different key produces a second transfer; the wallet is credited twice."""
    email = f"recharge-2key-{uuid.uuid4().hex[:8]}@example.com"
    key1 = f"rc-k1-{uuid.uuid4().hex}"
    key2 = f"rc-k2-{uuid.uuid4().hex}"
    amount = Decimal("25.0000")
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_player(client, email)
            token = await _admin_bearer(client)
            wallet_id = await _wallet_id_for(user_id)
            balance_before = await _balance(wallet_id)
            body = {"amount": "25.0000", "reason": "promo"}

            r1 = await client.post(
                f"/admin/wallets/{user_id}/recharge",
                json=body,
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key1},
            )
            r2 = await client.post(
                f"/admin/wallets/{user_id}/recharge",
                json=body,
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key2},
            )

        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert r1.json()["transfer_id"] != r2.json()["transfer_id"]
        # Two distinct keys → two transfers → credited twice.
        assert await _balance(wallet_id) == balance_before + amount + amount
        assert await _transfer_count_for_key(key1) == 1
        assert await _transfer_count_for_key(key2) == 1
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 4) Admin gate — no Bearer / player cookie rejected (T-03-13)
# ----------------------------------------------------------------------
async def test_recharge_requires_admin() -> None:
    """A request with no Bearer (and a player cookie) is rejected 401/403."""
    email = f"recharge-auth-{uuid.uuid4().hex[:8]}@example.com"
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_player(client, email)
            headers = {"Idempotency-Key": f"rc-auth-{uuid.uuid4().hex}"}
            body = {"amount": "10.0000", "reason": "promo"}

            # 4a. No auth at all.
            no_auth = await client.post(
                f"/admin/wallets/{user_id}/recharge", json=body, headers=headers
            )
            assert no_auth.status_code in (401, 403), no_auth.text

            # 4b. A player logs in (sets the player cookie) and tries the admin route.
            login = await client.post(
                "/auth/login",
                data={"username": email, "password": "Valid-Pass-1234"},
            )
            assert login.status_code in (200, 204), login.text
            with_cookie = await client.post(
                f"/admin/wallets/{user_id}/recharge", json=body, headers=headers
            )
        assert with_cookie.status_code in (401, 403), (
            f"player cookie unexpectedly authenticated the admin recharge: "
            f"{with_cookie.status_code} {with_cookie.text}"
        )
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 5) Missing Idempotency-Key → 400 (A3)
# ----------------------------------------------------------------------
async def test_recharge_missing_idempotency_key() -> None:
    """A recharge with no Idempotency-Key header returns 400."""
    email = f"recharge-nokey-{uuid.uuid4().hex[:8]}@example.com"
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_player(client, email)
            token = await _admin_bearer(client)
            resp = await client.post(
                f"/admin/wallets/{user_id}/recharge",
                json={"amount": "10.0000", "reason": "promo"},
                headers={"Authorization": f"Bearer {token}"},  # NO Idempotency-Key
            )
        assert resp.status_code == 400, resp.text
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)


# ----------------------------------------------------------------------
# 6) Money is a JSON string in the response (SC#4)
# ----------------------------------------------------------------------
async def test_recharge_amount_is_string_in_json() -> None:
    """The response body's ``amount`` is a JSON string, not a float (SC#4)."""
    email = f"recharge-str-{uuid.uuid4().hex[:8]}@example.com"
    key = f"rc-str-{uuid.uuid4().hex}"
    await _seed_admin()
    try:
        async with _client() as client:
            user_id = await _register_player(client, email)
            token = await _admin_bearer(client)
            resp = await client.post(
                f"/admin/wallets/{user_id}/recharge",
                json={"amount": "100.0000", "reason": "promo"},
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
            )
        assert resp.status_code == 200, resp.text
        # Parsed value is a str (not a float).
        assert isinstance(resp.json()["amount"], str)
        # And the raw bytes carry it quoted — a float would be unquoted.
        assert '"amount":"100.0000"' in resp.text.replace(" ", "")
    finally:
        await _delete_user(email)
        await _delete_user(_ADMIN_EMAIL)
