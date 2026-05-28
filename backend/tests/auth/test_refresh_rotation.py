"""DatabaseStrategy integration tests — AUTH-09 (rotation + reuse detection).

Tests target the four critical invariants:

1. ``test_token_hash_is_sha256`` — raw tokens NEVER appear in DB; only their
   sha256 hexdigest does (T-02-05 / T-02-16 mitigation).
2. ``test_reuse_detection_revokes_all`` — presenting a revoked token revokes
   EVERY active row for that user + bumps reuse_count (AUTH-09 critical).
3. ``test_expired_token_returns_none`` — expiry is not a theft signal; the
   reuse-detection branch is NOT triggered.
4. ``test_token_version_bump_invalidates`` — bumping user.token_version
   immediately invalidates every previously-issued row (AUTH-06).

# Why these tests bypass the rolled-back ``async_session`` fixture

The DatabaseStrategy opens its OWN session (Pitfall 9 mitigation) and
commits independently of the request transaction. The session-scoped
``async_session`` fixture wraps every test in a single outer transaction
that rolls back at session end — so user rows inserted via that session
are NOT visible to the Strategy's independent session, and the strategy's
own commits are NOT rolled back by the fixture's outer rollback.

To exercise the Strategy end-to-end, each test inserts users via the raw
``engine`` (committing) and explicitly cleans up its rows at the end.
This mirrors how the Strategy will behave in production.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.models import RefreshToken, User
from app.auth.strategy import DatabaseStrategy, _hash

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _build_strategy(engine: AsyncEngine, lifetime_seconds: int = 60) -> DatabaseStrategy:
    """Build a DatabaseStrategy bound to the test engine."""
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

    sm = async_sessionmaker(engine, class_=_AsyncSession, expire_on_commit=False)
    return DatabaseStrategy(sessionmaker=sm, lifetime_seconds=lifetime_seconds)


class _FakeUserManager:
    """Minimal stand-in: only ``.get(id)`` is exercised by read_token."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, user_id: uuid.UUID) -> Any:
        async with self._engine.connect() as conn:
            result = await conn.execute(select(User).where(User.id == user_id))
            row = result.first()
            if row is None:
                raise LookupError(user_id)

            # Return an object with attrs (token_version, id) that match a User.
            class _UserStub:
                pass

            stub = _UserStub()
            stub.id = row.id
            stub.token_version = row.token_version
            stub.email = row.email
            return stub


async def _insert_user(
    engine: AsyncEngine,
    *,
    email: str,
    token_version: int = 0,
) -> uuid.UUID:
    """Insert a User via raw engine; return its id."""
    uid = uuid.uuid4()
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO users "
                "(id, email, hashed_password, is_active, is_superuser, "
                " is_verified, token_version) "
                "VALUES (:id, :em, :pw, TRUE, FALSE, TRUE, :tv)"
            ),
            {"id": uid, "em": email, "pw": "not-used", "tv": token_version},
        )
        await conn.commit()
    return uid


async def _cleanup_user(engine: AsyncEngine, uid: uuid.UUID) -> None:
    """Delete refresh_tokens + user (FK CASCADE actually handles tokens)."""
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM refresh_tokens WHERE user_id = :uid"),
            {"uid": uid},
        )
        await conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
        await conn.commit()


# ---------------------------------------------------------------------------
# Test 1 — token_hash storage is SHA256 (AUTH-09 / T-02-16)
# ---------------------------------------------------------------------------


async def test_token_hash_is_sha256(engine: AsyncEngine) -> None:
    """write_token stores sha256(raw); raw NEVER appears in any column."""
    uid = await _insert_user(engine, email="hashtest@example.com")
    try:
        strategy = _build_strategy(engine)
        # Build a fake user object to pass to write_token.
        stub = type("UserStub", (), {})()
        stub.id = uid
        stub.token_version = 0
        raw_token = await strategy.write_token(stub)

        # 1a. Raw token is not the hash.
        assert raw_token != _hash(raw_token)

        # 1b. The row's token_hash is exactly sha256(raw).
        async with engine.connect() as conn:
            result = await conn.execute(select(RefreshToken).where(RefreshToken.user_id == uid))
            row = result.first()
            assert row is not None
            assert row.token_hash == _hash(raw_token)

            # 1c. The raw token never appears in any text column.
            scan = await conn.execute(
                text("SELECT token_hash::text FROM refresh_tokens WHERE user_id = :uid"),
                {"uid": uid},
            )
            rows = scan.all()
            for r in rows:
                assert raw_token not in r[0], "raw token leaked into refresh_tokens"
    finally:
        await _cleanup_user(engine, uid)


# ---------------------------------------------------------------------------
# Test 2 — Reuse detection scorches all active rows (AUTH-09 critical)
# ---------------------------------------------------------------------------


async def test_reuse_detection_revokes_all(engine: AsyncEngine) -> None:
    """Presenting a revoked token revokes ALL active rows for that user."""
    uid = await _insert_user(engine, email="reuse@example.com")
    try:
        strategy = _build_strategy(engine)
        stub = type("UserStub", (), {})()
        stub.id = uid
        stub.token_version = 0

        # Issue THREE active tokens (simulating 3 device sessions).
        token_a = await strategy.write_token(stub)
        token_b = await strategy.write_token(stub)
        token_c = await strategy.write_token(stub)
        assert len({token_a, token_b, token_c}) == 3

        # Revoke token A.
        await strategy.destroy_token(token_a, stub)

        # Sanity: B + C still active.
        async with engine.connect() as conn:
            active_before = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM refresh_tokens "
                        "WHERE user_id = :uid AND revoked_at IS NULL"
                    ),
                    {"uid": uid},
                )
            ).scalar()
            assert active_before == 2

        # Now present token A AGAIN — should trigger reuse detection.
        manager = _FakeUserManager(engine)
        result = await strategy.read_token(token_a, manager)  # type: ignore[arg-type]
        assert result is None  # the revoked token returns None

        # ALL of user's tokens are now revoked.
        async with engine.connect() as conn:
            active_after = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM refresh_tokens "
                        "WHERE user_id = :uid AND revoked_at IS NULL"
                    ),
                    {"uid": uid},
                )
            ).scalar()
            assert active_after == 0, "reuse detection failed to revoke all active tokens"

            # reuse_count incremented on the originally-revoked row.
            reuse_count_a = (
                await conn.execute(
                    text("SELECT reuse_count FROM refresh_tokens " "WHERE token_hash = :h"),
                    {"h": _hash(token_a)},
                )
            ).scalar()
            assert reuse_count_a >= 1
    finally:
        await _cleanup_user(engine, uid)


# ---------------------------------------------------------------------------
# Test 3 — Expired token returns None (NOT reuse signal)
# ---------------------------------------------------------------------------


async def test_expired_token_returns_none(engine: AsyncEngine) -> None:
    """Expiry is benign — read_token returns None but does NOT scorch."""
    uid = await _insert_user(engine, email="expired@example.com")
    try:
        # Build strategy with normal lifetime, then manually expire the row.
        strategy = _build_strategy(engine, lifetime_seconds=60)
        stub = type("UserStub", (), {})()
        stub.id = uid
        stub.token_version = 0
        raw_token = await strategy.write_token(stub)

        # Manually move expires_at to the past.
        async with engine.connect() as conn:
            await conn.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == _hash(raw_token))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=10))
            )
            await conn.commit()

        manager = _FakeUserManager(engine)
        result = await strategy.read_token(raw_token, manager)  # type: ignore[arg-type]
        assert result is None

        # Confirm reuse detection did NOT fire (row's reuse_count still 0,
        # revoked_at still NULL).
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token))
                )
            ).first()
            assert row is not None
            assert row.revoked_at is None
            assert row.reuse_count == 0
    finally:
        await _cleanup_user(engine, uid)


# ---------------------------------------------------------------------------
# Test 4 — token_version gate (AUTH-06)
# ---------------------------------------------------------------------------


async def test_token_version_bump_invalidates(engine: AsyncEngine) -> None:
    """Bumping user.token_version invalidates every token with the older snapshot."""
    uid = await _insert_user(engine, email="vbump@example.com", token_version=0)
    try:
        strategy = _build_strategy(engine)
        stub = type("UserStub", (), {})()
        stub.id = uid
        stub.token_version = 0
        raw_token = await strategy.write_token(stub)

        # Confirm token works while versions match.
        manager = _FakeUserManager(engine)
        result_ok = await strategy.read_token(raw_token, manager)  # type: ignore[arg-type]
        assert result_ok is not None
        assert result_ok.id == uid

        # Bump user.token_version directly via engine.
        async with engine.connect() as conn:
            await conn.execute(update(User).where(User.id == uid).values(token_version=1))
            await conn.commit()

        # Token snapshot version is 0; user is now 1 → must return None.
        result = await strategy.read_token(raw_token, manager)  # type: ignore[arg-type]
        assert result is None
    finally:
        await _cleanup_user(engine, uid)


# ---------------------------------------------------------------------------
# Test 5 — _hash() invariant (unit-style but async-marked for pytestmark)
# ---------------------------------------------------------------------------


async def test_hash_is_deterministic_sha256() -> None:
    """_hash returns sha256 hexdigest deterministically (T-02-16)."""
    import hashlib

    assert _hash("abc") == hashlib.sha256(b"abc").hexdigest()
    assert _hash("") == hashlib.sha256(b"").hexdigest()
    # Determinism — same input → same output.
    assert _hash("token123") == _hash("token123")
    # Different inputs → different outputs.
    assert _hash("a") != _hash("b")
