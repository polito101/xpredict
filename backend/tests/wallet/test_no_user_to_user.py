"""SC#5 / WAL-09 — the no-user-to-user regulatory firewall (Phase 3, Plan 03-04).

Encodes PITFALLS #3 ("hard-code non-transferability; enforce at the DB level")
as a permanent regression guard. The firewall is observable at three layers, and
this module asserts each:

  1. **Schema boundary (unit, no Docker):** ``RechargeRequest`` is
     ``extra="forbid"`` and has NO destination field — a body carrying
     ``dst_user_id`` (or any user-to-user param) is a hard ``ValidationError``.
  2. **Route inventory (unit, no Docker):** no registered route exposes a
     destination-user parameter; the only wallet-mutation surface is the admin
     recharge, which credits the path user from a house source.
  3. **ORM model (unit, no Docker):** ``Entry.account_id`` is the ONLY account FK
     per entry and references ``accounts`` only — there is no column/FK that would
     let one transfer name two distinct user wallets as a user-to-user move.

Plus an **integration** variant hitting the live endpoint with an admin Bearer
and asserting the extra field is rejected ``422`` end-to-end.

The pure schema/inventory/model assertions carry NO ``pytest.mark.integration``,
so they run in the quick ``-m "not integration"`` pass — SC#5 is covered without
Docker (acceptance criterion).
"""

from __future__ import annotations

import contextlib
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.wallet.models import Entry
from app.wallet.schemas import RechargeRequest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

_ADMIN_EMAIL = "no-u2u-admin@example.com"
_ADMIN_PASSWORD = "No-U2U-Admin-1!"


# ======================================================================
# 1) Schema boundary — extra=forbid rejects dst_user_id (UNIT, no Docker)
# ======================================================================
def test_recharge_rejects_dst_user_id() -> None:
    """A RechargeRequest carrying ``dst_user_id`` is a hard ValidationError (SC#5)."""
    # A valid body (no destination field) validates fine.
    ok = RechargeRequest.model_validate({"amount": "10.0000", "reason": "promo"})
    assert ok.amount == ok.amount  # constructed

    # Any user-to-user destination field is rejected by extra="forbid".
    with pytest.raises(ValidationError) as exc_info:
        RechargeRequest.model_validate(
            {
                "amount": "10.0000",
                "reason": "promo",
                "dst_user_id": str(uuid.uuid4()),
            }
        )
    # The error is specifically an "extra fields not permitted" rejection.
    assert any(
        err["type"] in ("extra_forbidden",) for err in exc_info.value.errors()
    ), exc_info.value.errors()


def test_recharge_schema_has_no_destination_field() -> None:
    """``RechargeRequest`` declares NO destination/recipient field of any kind."""
    field_names = set(RechargeRequest.model_fields)
    # The only fields are the amount and the audit reason — no dst/recipient/to.
    assert field_names == {"amount", "reason"}, field_names
    forbidden_substrings = ("dst", "dest", "recipient", "to_user", "target", "payee")
    for name in field_names:
        lowered = name.lower()
        assert not any(
            s in lowered for s in forbidden_substrings
        ), f"unexpected destination-like field on RechargeRequest: {name}"


# ======================================================================
# 2) Route inventory — no route exposes a destination-user param (UNIT)
# ======================================================================
def test_no_user_to_user_endpoint_exists() -> None:
    """No registered route accepts a player-to-player transfer (SC#5).

    Scans every route path for a destination-user segment AND scans the recharge
    body schema for a destination field. The ONLY ``user``-bearing path segment
    permitted is the single ``{user_id}`` on the admin recharge (the credited
    party), and that surface credits from a house source — never another user.
    """
    from app.main import app

    destination_markers = (
        "dst_user",
        "dest_user",
        "recipient",
        "to_user",
        "payee",
        "from_user",
    )
    for route in app.routes:
        path = getattr(route, "path", "")
        lowered = path.lower()
        assert not any(
            marker in lowered for marker in destination_markers
        ), f"route path exposes a user-to-user destination: {path}"
        # A recharge-style path must carry at most ONE user id segment (the
        # credited path user) — never a second {..._user_id} that would name a
        # source/destination user pair.
        if "recharge" in lowered:
            assert lowered.count("user_id") <= 1, f"recharge route names more than one user: {path}"

    # The recharge body schema (the only wallet-mutation surface) has no
    # destination field — re-assert at the inventory layer for defense-in-depth.
    assert set(RechargeRequest.model_fields) == {"amount", "reason"}


# ======================================================================
# 3) ORM model — Entry.account_id is the only account FK (UNIT, no Docker)
# ======================================================================
def test_entry_schema_has_no_user_to_user_fk() -> None:
    """``Entry.account_id`` references ``accounts`` only; no second user-account FK.

    A user-to-user move would require a single entry (or transfer) to name two
    distinct user wallets. The ledger's shape forbids it: each ``Entry`` has
    exactly ONE ``account_id`` FK (to ``accounts``), so a transfer's legs are
    independent rows — there is no column coupling two user wallets in one move
    (PITFALLS #3, enforced at the DB level).
    """
    account_fks = list(Entry.__table__.foreign_keys)
    # Exactly one FK column on entries, and it targets accounts.
    fk_columns = {fk.parent.name for fk in account_fks}
    fk_targets = {fk.column.table.name for fk in account_fks}

    assert "account_id" in fk_columns, fk_columns
    # The account-referencing FK targets the accounts table.
    account_referencing = [fk for fk in account_fks if fk.column.table.name == "accounts"]
    assert (
        len(account_referencing) == 1
    ), f"expected exactly one accounts FK on entries, got {len(account_referencing)}"
    assert account_referencing[0].parent.name == "account_id"
    # No FK on entries points to a users table (a user-to-user coupling).
    assert (
        "users" not in fk_targets
    ), f"entries must not FK a user table (user-to-user coupling): {fk_targets}"
    # Sanity: there is no second distinct account-referencing column that could
    # name a destination user wallet on the same entry row.
    account_cols_on_entry = {
        fk.parent.name for fk in account_fks if fk.column.table.name == "accounts"
    }
    assert account_cols_on_entry == {"account_id"}, account_cols_on_entry


# ======================================================================
# 4) Integration — the live endpoint rejects dst_user_id 422 (DOCKER)
# ======================================================================
@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_recharge_rejects_dst_user_id_live(engine: AsyncEngine) -> None:
    """End-to-end: POSTing a recharge body with ``dst_user_id`` returns 422 (SC#5).

    Uses a real admin Bearer so the request passes the auth gate and reaches the
    body validation — proving the firewall is enforced at the live wire surface,
    not just in an isolated schema test.
    """
    from pwdlib import PasswordHash

    from app.auth.rate_limit import limiter
    from app.db.session import _get_session_maker

    # Reset the shared rate-limit storage (tests/auth conftest is not inherited).
    with contextlib.suppress(Exception):
        limiter._limiter.reset()

    # Seed the admin + a target player directly (committed session).
    hashed = PasswordHash.recommended().hash(_ADMIN_PASSWORD)
    player_email = f"no-u2u-player-{uuid.uuid4().hex[:8]}@example.com"
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(text("DELETE FROM users WHERE email = :em"), {"em": _ADMIN_EMAIL})
        await s.execute(
            text(
                "INSERT INTO users "
                "(email, hashed_password, is_active, is_superuser, "
                " is_verified, display_name, token_version) "
                "VALUES (:em, :pw, TRUE, TRUE, TRUE, 'No-U2U Admin', 0)"
            ),
            {"em": _ADMIN_EMAIL, "pw": hashed},
        )

    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post(
                "/auth/register",
                json={"email": player_email, "password": "Valid-Pass-1234"},
            )
            assert reg.status_code == 201, reg.text
            victim_id = reg.json()["id"]

            login = await client.post(
                "/admin/auth/login",
                data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]

            resp = await client.post(
                f"/admin/wallets/{victim_id}/recharge",
                json={
                    "amount": "10.0000",
                    "reason": "promo",
                    "dst_user_id": str(uuid.uuid4()),  # bogus user-to-user param
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": f"no-u2u-{uuid.uuid4().hex}",
                },
            )
        # extra="forbid" → FastAPI body validation rejects the unknown field 422.
        assert resp.status_code == 422, resp.text
    finally:
        async with sm() as s, s.begin():
            await s.execute(text("DELETE FROM users WHERE email = :em"), {"em": _ADMIN_EMAIL})
            await s.execute(text("DELETE FROM users WHERE email = :em"), {"em": player_email})
