"""Seed the first admin user idempotently (D-11, AUTH-07).

Read ``FIRST_ADMIN_EMAIL`` + ``FIRST_ADMIN_PASSWORD`` from the
environment, hash with Argon2id via ``pwdlib`` (the same hasher
fastapi-users picks under the hood — RESEARCH line 1350), then INSERT
one row in ``users`` with ``is_superuser=True, is_active=True,
is_verified=True``. Re-running is a NO-OP — the script returns 0 with a
clear stdout message when the admin already exists.

# Filename deviation from CONTEXT D-11

CONTEXT D-11 (and the PATTERNS doc) say ``bin/create-admin.py``. Python
module names cannot contain hyphens, which would break the ability to
``import bin.create_admin`` from tests. The file therefore lives at
``bin/create_admin.py`` (underscore) and the README documents
``uv run python bin/create_admin.py`` as the invocation. Functionally
identical to the hyphen form — only the filename / module-name differs.

# Why this BYPASSES ``UserManager.validate_password``

The 12-char + complexity rules in ``UserManager.validate_password``
(Plan 02-02) exist to protect users-who-self-register from picking weak
passwords. The first admin is seeded directly by the OPERATOR from
``.env.local`` — the operator is trusted; password strength is the
operator's responsibility (gated by what they put in the env file).
Going through fastapi-users' register flow would also reject ``.local``
TLDs via ``EmailStr`` validation, which is the wrong gate for a
container-internal bootstrap. So we INSERT directly through SQLAlchemy.

# Invocation

    cd backend
    uv run python bin/create_admin.py
"""

from __future__ import annotations

import asyncio
import sys
from uuid import uuid4

from pwdlib import PasswordHash
from sqlalchemy import select

from app.auth.models import User
from app.core.config import get_settings
from app.db.session import _get_session_maker


async def main() -> int:
    """Run the seeding loop. Return 0 on success/no-op, 1 on usage error."""
    settings = get_settings()
    email = settings.FIRST_ADMIN_EMAIL
    password = settings.FIRST_ADMIN_PASSWORD
    if not email or not password:
        print(
            "FIRST_ADMIN_EMAIL and FIRST_ADMIN_PASSWORD must be set "
            "in the environment (e.g. via .env.local).",
            file=sys.stderr,
        )
        return 1

    session_maker = _get_session_maker()
    async with session_maker() as session:
        # ``User.email`` comes from SQLAlchemyBaseUserTableUUID without
        # ColumnElement typing — mypy treats ``==`` as returning bool. The
        # ``type: ignore`` is the documented escape; runtime is correct.
        existing = (
            await session.execute(
                select(User).where(User.email == email)  # type: ignore[arg-type]
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(
                f"Admin {email} already exists (id={existing.id}). No-op."
            )
            return 0

        helper = PasswordHash.recommended()
        admin = User(
            id=uuid4(),
            email=email,
            hashed_password=helper.hash(password),
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
        session.add(admin)
        # Capture admin.id BEFORE commit so we don't rely on the ORM
        # re-loading the attribute after the session closes.  With
        # expire_on_commit=True (the default), accessing admin.id after
        # commit would trigger a SELECT on a closed session (MissingGreenlet).
        # admin.id was set explicitly via uuid4(), so it is always available
        # before the flush — this is purely defensive.
        admin_id = admin.id
        await session.commit()
        print(f"Created admin {email} (id={admin_id})")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
