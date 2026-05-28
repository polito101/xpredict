"""Tests for bin/create_admin.py — first-admin seeding CLI (D-11).

Asserts:
- Fresh DB: creates one row with is_superuser=True, is_active=True,
  is_verified=True; the password is verifiable via pwdlib (Argon2id hash).
- Idempotent: a second invocation returns 0 with a "already exists" message
  and leaves the DB row count unchanged.
- Refuses empty FIRST_ADMIN_EMAIL or FIRST_ADMIN_PASSWORD with exit code 1.
- Does NOT route through ``UserManager.validate_password`` — the bootstrap
  path is operator-trusted (passwords come from .env.local; strength is
  the operator's responsibility).

The script uses ``app.db.session._get_session_maker()`` (lru_cache), so
tests share the testcontainer engine via the ``engine`` fixture; we
clear caches between scenarios to pick up changed env vars.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pwdlib import PasswordHash
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


_TEST_EMAIL = "test-admin-bootstrap@example.com"
_TEST_PASSWORD = "Test-Admin-Pass-1!"


async def _cleanup(engine: AsyncEngine, email: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()


async def _count_admins(engine: AsyncEngine, email: str) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM users WHERE email = :em"),
            {"em": email},
        )
        return result.scalar() or 0


def _reset_settings_cache() -> None:
    """Clear ``get_settings`` LRU cache so a Settings() reload picks up the
    monkeypatched env vars set in the test.
    """
    from app.core.config import get_settings

    get_settings.cache_clear()


async def test_seeds_admin_on_fresh_db(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """First run on a clean DB inserts one admin row with the right flags."""
    await _cleanup(engine, _TEST_EMAIL)
    monkeypatch.setenv("FIRST_ADMIN_EMAIL", _TEST_EMAIL)
    monkeypatch.setenv("FIRST_ADMIN_PASSWORD", _TEST_PASSWORD)
    _reset_settings_cache()

    from bin.create_admin import main

    try:
        rc = await main()
        assert rc == 0

        out = capsys.readouterr().out
        assert "Created admin" in out
        # T-02-33 — stdout must NOT contain the plaintext password
        assert _TEST_PASSWORD not in out

        # DB has exactly one row + flags as documented
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT email, is_active, is_superuser, is_verified, "
                        "       hashed_password "
                        "FROM users WHERE email = :em"
                    ),
                    {"em": _TEST_EMAIL},
                )
            ).first()
            assert row is not None
            assert row.is_active is True
            assert row.is_superuser is True
            assert row.is_verified is True
            # pwdlib should be able to verify the password against the hash
            helper = PasswordHash.recommended()
            assert helper.verify(_TEST_PASSWORD, row.hashed_password)
    finally:
        await _cleanup(engine, _TEST_EMAIL)
        _reset_settings_cache()


async def test_idempotent_on_existing_admin(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Second call returns 0 with 'already exists' message; row count unchanged."""
    await _cleanup(engine, _TEST_EMAIL)
    monkeypatch.setenv("FIRST_ADMIN_EMAIL", _TEST_EMAIL)
    monkeypatch.setenv("FIRST_ADMIN_PASSWORD", _TEST_PASSWORD)
    _reset_settings_cache()

    from bin.create_admin import main

    try:
        # First run creates
        rc1 = await main()
        assert rc1 == 0
        assert await _count_admins(engine, _TEST_EMAIL) == 1
        capsys.readouterr()  # clear

        # Second run is a no-op
        rc2 = await main()
        assert rc2 == 0
        out2 = capsys.readouterr().out
        assert "already exists" in out2.lower()
        assert await _count_admins(engine, _TEST_EMAIL) == 1
    finally:
        await _cleanup(engine, _TEST_EMAIL)
        _reset_settings_cache()


async def test_refuses_empty_env(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empty FIRST_ADMIN_EMAIL → exit 1 with stderr mentioning the required vars."""
    monkeypatch.setenv("FIRST_ADMIN_EMAIL", "")
    monkeypatch.setenv("FIRST_ADMIN_PASSWORD", "")
    _reset_settings_cache()

    from bin.create_admin import main

    try:
        rc = await main()
        assert rc == 1
        captured = capsys.readouterr()
        assert "FIRST_ADMIN_EMAIL" in captured.err and "FIRST_ADMIN_PASSWORD" in captured.err
    finally:
        _reset_settings_cache()


async def test_password_bypasses_validate_password(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A weak password is ACCEPTED by the script (operator-trusted bootstrap path).

    ``UserManager.validate_password`` would reject ``short`` (8-char min,
    classes); the script directly INSERTs through SQLAlchemy, bypassing
    that check. This is documented behaviour (the operator chose what
    goes into .env.local; we trust them).
    """
    await _cleanup(engine, _TEST_EMAIL)
    monkeypatch.setenv("FIRST_ADMIN_EMAIL", _TEST_EMAIL)
    monkeypatch.setenv("FIRST_ADMIN_PASSWORD", "short")  # would fail validate_password
    _reset_settings_cache()

    from bin.create_admin import main

    try:
        rc = await main()
        assert rc == 0
        # Row exists
        assert await _count_admins(engine, _TEST_EMAIL) == 1
        # And the hash matches the weak password
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT hashed_password FROM users WHERE email = :em"),
                    {"em": _TEST_EMAIL},
                )
            ).first()
            assert row is not None
            helper = PasswordHash.recommended()
            assert helper.verify("short", row.hashed_password)
    finally:
        await _cleanup(engine, _TEST_EMAIL)
        _reset_settings_cache()
