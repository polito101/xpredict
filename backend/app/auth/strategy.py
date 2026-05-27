"""Custom DatabaseStrategy with refresh-token rotation + reuse detection (D-04, AUTH-09).

Implements the three-method ``Strategy`` Protocol from fastapi-users 15.0.5
(``read_token``, ``write_token``, ``destroy_token``).

# Pitfall 9 mitigation (RESEARCH lines 1042-1048)
Instead of taking the request-scoped ``AsyncSession`` and calling
``session.commit()`` (which would prematurely terminate the caller's
transaction — e.g. the register transaction that ALSO writes a user row +
audit row), this Strategy takes an ``async_sessionmaker`` and opens its
OWN short-lived session per token operation. The token write/read/destroy
therefore commits independently of the request's transaction. A register
failure can roll back the user row without leaking a half-committed
refresh_token row.

# Hash-only storage (T-02-05, T-02-16)
``token_hash`` stores ``sha256(raw_token).hexdigest()``; the raw token is
returned to the caller (set as cookie) but never persisted. A DB breach
does NOT leak active tokens. ``test_token_hash_is_sha256`` asserts this.

# Reuse detection (AUTH-09, T-02-12)
Presenting a ``revoked_at IS NOT NULL`` token = OWASP "scorched earth":
every active token for that user is revoked, ``reuse_count`` increments.
This is the AUTH-09 critical test surface (RESEARCH line 1465).

# token_version gate (AUTH-06, Pitfall 6, T-02-19)
Every token row snapshots the user's ``token_version`` at issue time.
``read_token`` rejects rows whose snapshot is below the user's current
version — so password reset (which bumps ``user.token_version``)
invalidates every cookie issued prior. Belt-and-suspenders: the manager
also revokes the rows directly (so the DB cleanly reflects state).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends
from fastapi_users.authentication.strategy import Strategy
from fastapi_users.manager import BaseUserManager
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import RefreshToken, User
from app.core.config import get_settings
from app.db.session import _get_session_maker


def _hash(token: str) -> str:
    """Compute SHA256 hexdigest. Tokens are stored hashed only."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DatabaseStrategy(Strategy[User, UUID]):
    """Persistent token store with rotation + reuse detection (AUTH-09)."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        lifetime_seconds: int,
    ) -> None:
        """Initialise with a sessionmaker so each op owns its transaction (Pitfall 9)."""
        self.sessionmaker = sessionmaker
        self.lifetime_seconds = lifetime_seconds

    async def read_token(
        self,
        token: str | None,
        user_manager: BaseUserManager[User, UUID],
    ) -> User | None:
        """Return the user iff the token is valid + active + version-current."""
        if token is None:
            return None

        token_hash = _hash(token)
        async with self.sessionmaker() as session:
            stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None

            # REUSE DETECTION — presenting a revoked token = attack signal,
            # nuke every active token for this user (AUTH-09, T-02-12).
            if row.revoked_at is not None:
                await session.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.user_id == row.user_id,
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(
                        revoked_at=datetime.now(UTC),
                        reuse_count=RefreshToken.reuse_count + 1,
                    )
                )
                # Also increment on the original revoked row so the test can
                # observe the reuse count on the originally-revoked entry.
                await session.execute(
                    update(RefreshToken)
                    .where(RefreshToken.id == row.id)
                    .values(reuse_count=RefreshToken.reuse_count + 1)
                )
                await session.commit()
                return None

            # Expiry — NOT a reuse signal; just deny.
            if row.expires_at < datetime.now(UTC):
                return None

            # AUTH-06 token_version gate.
            row_token_version = row.token_version
            row_user_id = row.user_id

        # Re-resolve user via user_manager (uses its own session via user_db).
        try:
            user = await user_manager.get(row_user_id)
        except Exception:
            return None

        if user.token_version > row_token_version:
            return None

        return user

    async def write_token(self, user: User) -> str:
        """Issue a fresh refresh token; persist only its SHA256 hash."""
        token = secrets.token_urlsafe(48)  # 64 chars ≈ 384 bits entropy
        async with self.sessionmaker() as session:
            row = RefreshToken(
                token_hash=_hash(token),
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(seconds=self.lifetime_seconds),
                token_version=user.token_version,
            )
            session.add(row)
            await session.commit()
        return token

    async def destroy_token(self, token: str, user: User) -> None:
        """Mark the row corresponding to this token as revoked (AUTH-05)."""
        async with self.sessionmaker() as session:
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.token_hash == _hash(token),
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
            await session.commit()


def get_database_strategy() -> DatabaseStrategy:
    """FastAPI dependency producing a per-request Strategy.

    The Strategy owns its own session lifetime via the module-level
    sessionmaker (Pitfall 9 mitigation).
    """
    settings = get_settings()
    return DatabaseStrategy(
        sessionmaker=_get_session_maker(),
        lifetime_seconds=settings.REFRESH_TOKEN_LIFETIME_SECONDS,
    )


# Used by deps.py to keep API consistent — currently no extra param needed,
# but Phase 3+ may inject something.
__all__ = ["DatabaseStrategy", "_hash", "get_database_strategy"]


# Suppress mypy false positive on Depends pattern compatibility — Depends is
# the FastAPI idiom but here we don't take a session injection. Keep import
# in case future deps require it without breaking signature.
_ = Depends
