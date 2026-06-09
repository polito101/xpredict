"""Tests for the admin CSV export (Phase 8, Plan 08-02, ADU-06).

Two layers:

1. **Unit tests** for ``sanitize_csv_cell`` and the three builders — pure, no
   app / DB. They cover every formula trigger (``= + - @`` TAB CR), normal +
   empty text, money-as-string, and ISO-8601-UTC timestamps (D-09).
2. **Integration tests** that drive the live FastAPI app through
   ``ASGITransport``: ``text/csv`` + ``Content-Disposition`` headers, header +
   data rows, the ``status`` filter, a ``=``-prefixed email getting sanitized
   on the wire, and the 401/403 auth wall on all three endpoints (T-08-06).
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from app.admin.csv_export import (
    FORMULA_TRIGGERS,
    MAX_EXPORT_ROWS,
    build_bets_csv,
    build_transactions_csv,
    build_users_csv,
    sanitize_csv_cell,
)
from tests.admin._helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
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

# NOTE: this module mixes SYNC unit tests with ASYNC integration tests, so we do
# NOT use a module-level ``pytestmark`` with ``asyncio`` (it would mark the sync
# unit tests with @asyncio and trip the pytest-asyncio "not an async function"
# warning, which ``filterwarnings=["error"]`` turns into a failure). Instead each
# async integration test carries ``@pytest.mark.integration`` +
# ``@pytest.mark.asyncio(loop_scope="session")`` explicitly.


# --------------------------------------------------------------------------- #
# Unit tests — sanitize_csv_cell (D-09 / T-08-05). No app, no DB.
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("=SUM(A1:A2)", "'=SUM(A1:A2)"),
        ("+cmd", "'+cmd"),
        ("-alert", "'-alert"),
        ("@import", "'@import"),
        ("\tcmd", "'\tcmd"),
        ("\rcmd", "'\rcmd"),
        ("normal text", "normal text"),
        ("", ""),
    ],
)
def test_sanitize_csv_cell(raw: str, expected: str) -> None:
    assert sanitize_csv_cell(raw) == expected


@pytest.mark.unit
def test_formula_triggers_exact_set() -> None:
    """FORMULA_TRIGGERS is exactly the D-09 set — no more, no less."""
    assert set(FORMULA_TRIGGERS) == {"=", "+", "-", "@", "\t", "\r"}


@pytest.mark.unit
def test_sanitize_only_first_char_matters() -> None:
    """A trigger char NOT at position 0 is left untouched."""
    assert sanitize_csv_cell("a=b") == "a=b"
    assert sanitize_csv_cell("text+more") == "text+more"


# --------------------------------------------------------------------------- #
# Unit tests — builders (D-09): money as string, ISO 8601 UTC, sanitized cells.
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_build_users_csv_header_and_money_and_iso() -> None:
    rows = [
        {
            "email": "alice@test.com",
            "display_name": "Alice",
            "banned_at": None,
            "created_at": datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC),
            "last_activity": None,
            "balance": Decimal("1234.5600"),
        }
    ]
    out = build_users_csv(rows)
    reader = list(csv.reader(io.StringIO(out)))
    assert reader[0] == [
        "email",
        "display_name",
        "status",
        "signup_date",
        "last_activity",
        "balance",
    ]
    data = reader[1]
    assert data[0] == "alice@test.com"
    assert data[2] == "active"  # status derived from banned_at
    assert data[3] == "2026-05-28T12:00:00+00:00"  # ISO 8601 UTC
    assert data[5] == "1234.5600"  # money as plain Decimal string, no symbol
    # No float artefacts.
    assert "." in data[5] and "e" not in data[5].lower()


@pytest.mark.unit
def test_build_users_csv_status_banned_and_naive_datetime_assumed_utc() -> None:
    rows = [
        {
            "email": "bob@test.com",
            "display_name": None,
            "banned_at": datetime(2026, 5, 1, tzinfo=UTC),
            "created_at": datetime(2026, 5, 28, 9, 30, 0),  # naive -> assume UTC
            "last_activity": datetime(2026, 5, 28, 10, 0, 0, tzinfo=UTC),
            "balance": Decimal("0.0000"),
        }
    ]
    reader = list(csv.reader(io.StringIO(build_users_csv(rows))))
    data = reader[1]
    assert data[2] == "banned"
    assert data[3] == "2026-05-28T09:30:00+00:00"


@pytest.mark.unit
def test_build_users_csv_sanitizes_formula_email() -> None:
    rows = [
        {
            "email": "=malicious@evil.com",
            "display_name": "@danger",
            "banned_at": None,
            "created_at": datetime(2026, 5, 28, tzinfo=UTC),
            "last_activity": None,
            "balance": Decimal("0"),
        }
    ]
    # Parse with the csv module so the leading quote is in the *field value*.
    reader = list(csv.reader(io.StringIO(build_users_csv(rows))))
    data = reader[1]
    assert data[0] == "'=malicious@evil.com"
    assert data[1] == "'@danger"


@pytest.mark.unit
def test_build_transactions_csv() -> None:
    rows = [
        {
            "id": uuid4(),
            "user_email": "alice@test.com",
            "kind": "recharge",
            "amount": Decimal("50.0000"),
            "reason": "promo",
            "created_at": datetime(2026, 5, 28, 8, 0, 0, tzinfo=UTC),
        }
    ]
    reader = list(csv.reader(io.StringIO(build_transactions_csv(rows))))
    assert reader[0] == ["id", "user_email", "kind", "amount", "reason", "created_at"]
    assert reader[1][3] == "50.0000"
    assert reader[1][5] == "2026-05-28T08:00:00+00:00"


@pytest.mark.unit
def test_build_bets_csv_pnl_empty_when_none() -> None:
    rows = [
        {
            "id": uuid4(),
            "user_email": "alice@test.com",
            "market_question": "Will it rain?",
            "outcome": "YES",
            "stake": Decimal("10.0000"),
            "status": "PENDING",
            "pnl": None,
            "created_at": datetime(2026, 5, 28, 7, 0, 0, tzinfo=UTC),
        }
    ]
    reader = list(csv.reader(io.StringIO(build_bets_csv(rows))))
    assert reader[0] == [
        "id",
        "user_email",
        "market_question",
        "outcome",
        "stake",
        "status",
        "pnl",
        "created_at",
    ]
    assert reader[1][4] == "10.0000"
    assert reader[1][6] == ""  # pnl empty while pending


@pytest.mark.unit
def test_build_users_csv_caps_at_max_rows() -> None:
    """A builder given > MAX_EXPORT_ROWS truncates to the cap (T-08-09)."""
    rows = [
        {
            "email": f"u{i}@test.com",
            "display_name": None,
            "banned_at": None,
            "created_at": datetime(2026, 5, 28, tzinfo=UTC),
            "last_activity": None,
            "balance": Decimal("0"),
        }
        for i in range(MAX_EXPORT_ROWS + 5)
    ]
    reader = list(csv.reader(io.StringIO(build_users_csv(rows))))
    # header + exactly MAX_EXPORT_ROWS data rows
    assert len(reader) == MAX_EXPORT_ROWS + 1


# --------------------------------------------------------------------------- #
# Integration tests — live app through ASGITransport.
# --------------------------------------------------------------------------- #
_EXPORT_USER = "csv-export-user@test.com"


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_users_returns_csv_with_attachment_header(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/export/users", headers=auth(token))
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert "users.csv" in resp.headers["content-disposition"]
        # Header row present.
        first_line = resp.text.splitlines()[0]
        assert "email" in first_line and "balance" in first_line
    finally:
        await cleanup_user(engine, ADMIN_EMAIL)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_users_includes_data_rows(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, _EXPORT_USER, display_name="Exported")
    wallet_id = await seed_wallet(engine, uid, balance=Decimal("99.0000"))
    await seed_transaction(engine, wallet_id, amount=Decimal("99.0000"), reason="opening")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(
                f"/api/v1/admin/export/users?search={_EXPORT_USER}", headers=auth(token)
            )
        assert resp.status_code == 200, resp.text
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        match = [r for r in rows if r["email"] == _EXPORT_USER]
        assert match, f"exported user not in CSV: {resp.text}"
        assert match[0]["balance"] == "99.0000"  # money as string
    finally:
        await cleanup_user(engine, _EXPORT_USER)
        await cleanup_user(engine, ADMIN_EMAIL)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_users_status_filter_only_banned(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    banned_email = "csv-banned@test.com"
    active_email = "csv-active@test.com"
    await seed_user(engine, banned_email, banned=True)
    await seed_user(engine, active_email, banned=False)
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get("/api/v1/admin/export/users?status=banned", headers=auth(token))
        assert resp.status_code == 200, resp.text
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        emails = {r["email"] for r in rows}
        assert banned_email in emails
        assert active_email not in emails
        # Every exported row must have status == banned.
        assert all(r["status"] == "banned" for r in rows)
    finally:
        await cleanup_user(engine, banned_email)
        await cleanup_user(engine, active_email)
        await cleanup_user(engine, ADMIN_EMAIL)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_users_sanitizes_formula_email_on_wire(engine: AsyncEngine) -> None:
    """A user whose email starts with '=' must be sanitized in the CSV (T-08-05)."""
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    evil_email = "=cmd@evil.com"
    await seed_user(engine, evil_email, display_name="evil")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(
                "/api/v1/admin/export/users?search=cmd@evil.com", headers=auth(token)
            )
        assert resp.status_code == 200, resp.text
        # Parse with csv so we inspect the actual field value (quote is in-field).
        rows = list(csv.reader(io.StringIO(resp.text)))
        evil_rows = [r for r in rows if r and r[0] == "'=cmd@evil.com"]
        assert evil_rows, f"sanitized email not found in CSV: {resp.text!r}"
    finally:
        await cleanup_user(engine, evil_email)
        await cleanup_user(engine, ADMIN_EMAIL)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_transactions_returns_csv(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, _EXPORT_USER, display_name="Tx User")
    wallet_id = await seed_wallet(engine, uid, balance=Decimal("25.0000"))
    await seed_transaction(engine, wallet_id, amount=Decimal("25.0000"), reason="topup")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(
                f"/api/v1/admin/export/transactions?user_id={uid}", headers=auth(token)
            )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert "transactions.csv" in resp.headers["content-disposition"]
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        assert rows, "no transaction rows exported"
        assert rows[0]["user_email"] == _EXPORT_USER
        assert rows[0]["amount"] == "25.0000"
    finally:
        await cleanup_user(engine, _EXPORT_USER)
        await cleanup_user(engine, ADMIN_EMAIL)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_bets_returns_csv(engine: AsyncEngine) -> None:
    await seed_user(engine, ADMIN_EMAIL, is_superuser=True)
    uid = await seed_user(engine, _EXPORT_USER, display_name="Bet User")
    await seed_bet(engine, uid, stake=Decimal("15.0000"), status="PENDING")
    try:
        async with await client() as c:
            token = await get_admin_token(c)
            resp = await c.get(f"/api/v1/admin/export/bets?user_id={uid}", headers=auth(token))
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert "bets.csv" in resp.headers["content-disposition"]
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        assert rows, "no bet rows exported"
        assert rows[0]["user_email"] == _EXPORT_USER
        assert rows[0]["stake"] == "15.0000"
    finally:
        await cleanup_user(engine, _EXPORT_USER)
        await cleanup_user(engine, ADMIN_EMAIL)


# --------------------------------------------------------------------------- #
# Negative auth (T-08-06) — 401 without Bearer, 403 with a player Bearer.
# --------------------------------------------------------------------------- #
_EXPORT_PATHS = [
    "/api/v1/admin/export/users",
    "/api/v1/admin/export/transactions",
    "/api/v1/admin/export/bets",
]
_PLAYER_EMAIL = "csv-export-player@test.com"


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_endpoints_401_without_token() -> None:
    async with await client() as c:
        for path in _EXPORT_PATHS:
            resp = await c.get(path)
            assert resp.status_code == 401, f"{path} -> {resp.status_code} (expected 401)"


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_export_endpoints_403_with_player_token(engine: AsyncEngine) -> None:
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
            for path in _EXPORT_PATHS:
                resp = await c.get(path, headers=auth(token))
                assert resp.status_code == 403, f"{path} -> {resp.status_code} (expected 403)"
    finally:
        await cleanup_user(engine, _PLAYER_EMAIL)
