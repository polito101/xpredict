"""Shared test helpers for the admin CRM integration tests (Phase 8, Plan 08-01).

Follows ``tests/markets/test_admin_router.py`` exactly: a raw-SQL seed/cleanup
for users (so we control ``is_superuser`` / ``banned_at``), an admin-login helper
that mints a Bearer, and an ``_auth`` header builder. Adds wallet + bet seeding
(raw INSERTs, committed) so the detail / transactions / bets endpoints have data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.wallet.constants import (
    DIRECTION_CREDIT,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
    TRANSFER_RECHARGE,
)

# A single admin account reused across the admin-CRM test modules.
ADMIN_EMAIL = "crm-admin@test.com"
ADMIN_PASSWORD = "Admin-Test-Pass-1!"


async def client() -> httpx.AsyncClient:
    """An httpx client wired through the FastAPI app via ASGITransport."""
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def seed_user(
    engine: AsyncEngine,
    email: str,
    *,
    is_superuser: bool = False,
    banned: bool = False,
    display_name: str = "Test User",
) -> UUID:
    """INSERT a user (committed) and return its id. Idempotent on email."""
    hashed = PasswordHash.recommended().hash(ADMIN_PASSWORD)
    banned_sql = "now()" if banned else "NULL"
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        row = (
            await conn.execute(
                text(
                    "INSERT INTO users "
                    "(email, hashed_password, is_active, is_superuser, "
                    " is_verified, display_name, banned_at, token_version) "
                    f"VALUES (:em, :pw, TRUE, :su, TRUE, :dn, {banned_sql}, 0) "
                    "RETURNING id"
                ),
                {"em": email, "pw": hashed, "su": is_superuser, "dn": display_name},
            )
        ).one()
        await conn.commit()
    return row[0]


async def seed_wallet(engine: AsyncEngine, user_id: UUID, *, balance: Decimal) -> UUID:
    """INSERT a ``user_wallet`` account for ``user_id`` (committed); return its id.

    NOTE: this writes the cached ``balance`` directly, WITHOUT a backing ledger entry. A
    non-zero ``balance`` MUST be matched by ``seed_transaction`` credit(s) summing to it,
    otherwise the account registers as drift in the DB-wide ledger reconciler
    (``app.wallet.reconcile._reconcile_async``) — and because the testcontainer Postgres is
    session-scoped, that committed orphan leaks into other suites' integrity gate (e.g.
    ``tests/settlement/test_event_*``), failing them depending on file ordering.
    """
    wallet_id = uuid4()
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :k, :c, :b)"
            ),
            {
                "id": wallet_id,
                "ot": OWNER_USER,
                "oid": user_id,
                "k": KIND_USER_WALLET,
                "c": PLAY_USD,
                "b": balance,
            },
        )
        await conn.commit()
    return wallet_id


async def seed_transaction(
    engine: AsyncEngine,
    wallet_id: UUID,
    *,
    amount: Decimal,
    reason: str = "test recharge",
) -> None:
    """INSERT a transfer + one credit entry against ``wallet_id`` (committed)."""
    transfer_id = uuid4()
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO transfers (id, kind, metadata) "
                "VALUES (:id, :k, CAST(:meta AS jsonb))"
            ),
            {"id": transfer_id, "k": TRANSFER_RECHARGE, "meta": f'{{"reason": "{reason}"}}'},
        )
        await conn.execute(
            text(
                "INSERT INTO entries (id, transfer_id, account_id, direction, amount) "
                "VALUES (:id, :tid, :aid, :dir, :amt)"
            ),
            {
                "id": uuid4(),
                "tid": transfer_id,
                "aid": wallet_id,
                "dir": DIRECTION_CREDIT,
                "amt": amount,
            },
        )
        await conn.commit()


async def seed_bet(
    engine: AsyncEngine,
    user_id: UUID,
    *,
    stake: Decimal,
    odds: Decimal = Decimal("0.500000"),
    status: str = "PENDING",
    created_at: datetime | None = None,
) -> UUID:
    """Raw-INSERT a bet for ``user_id`` (committed); return its id.

    ``created_at`` lets a test backdate a bet so the 24h / 7d / 30d KPI windows
    (volume + DAU + the 30-day chart buckets) can be exercised across days. When
    ``None`` the DB ``server_default now()`` applies (a fresh "now" bet).
    """
    bet_id = uuid4()
    cols = "id, user_id, market_id, outcome_id, stake, odds_at_placement, status"
    vals = ":id, :u, :m, :o, :st, :od, :status"
    params: dict[str, object] = {
        "id": bet_id,
        "u": user_id,
        "m": uuid4(),
        "o": uuid4(),
        "st": stake,
        "od": odds,
        "status": status,
    }
    if created_at is not None:
        cols += ", created_at"
        vals += ", :created_at"
        params["created_at"] = created_at
    async with engine.connect() as conn:
        await conn.execute(text(f"INSERT INTO bets ({cols}) VALUES ({vals})"), params)
        await conn.commit()
    return bet_id


async def seed_bet_span(
    engine: AsyncEngine,
    user_id: UUID,
    *,
    stake: Decimal,
    days: int = 30,
    per_day: int = 1,
    now: datetime | None = None,
) -> int:
    """Seed ``per_day`` bets on each of the last ``days`` days for ``user_id``.

    The 30-day synthetic fixture (CONTEXT D-06): drives the daily-volume chart
    buckets AND the volume / DAU windows. Each bet is backdated to noon on its
    day (``now - n days``) so it falls squarely inside the right ``date_trunc``
    bucket regardless of the clock at run time. Returns the count of bets seeded.
    """
    anchor = now or datetime.now(UTC)
    count = 0
    for day_offset in range(days):
        # Noon on the target day keeps the bet inside that UTC calendar day.
        day = (anchor - timedelta(days=day_offset)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        for _ in range(per_day):
            await seed_bet(engine, user_id, stake=stake, created_at=day)
            count += 1
    return count


async def seed_market(
    engine: AsyncEngine,
    *,
    status: str,
    deadline: datetime,
    question: str = "Will the KPI seam hold?",
) -> UUID:
    """Raw-INSERT a HOUSE market (committed) with a given ``status`` + ``deadline``.

    Used to build the active-markets COUNT and the pending-resolutions
    (deadline past/future) x (status) matrix. ``slug`` is uniquified per call so
    the UNIQUE(slug) constraint never collides across tests on the shared
    session-scoped container.
    """
    market_id = uuid4()
    slug = f"kpi-seam-{market_id.hex[:12]}"
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO markets "
                "(id, question, slug, resolution_criteria, source, status, deadline) "
                "VALUES (:id, :q, :slug, :rc, 'HOUSE', :status, :deadline)"
            ),
            {
                "id": market_id,
                "q": question,
                "slug": slug,
                "rc": "Resolves per the official source.",
                "status": status,
                "deadline": deadline,
            },
        )
        await conn.commit()
    return market_id


async def seed_audit(
    *,
    event_type: str,
    actor: str = "user:00000000-0000-0000-0000-000000000000",
    payload: dict[str, object] | None = None,
    ip: str | None = None,
) -> UUID:
    """Insert one audit row via ``AuditService.record()`` (committed); return its id.

    Uses the app's own session-maker (the ``engine`` fixture points it at the
    testcontainer and clears its cache), so this drives the REAL single audit
    writer (D-20/D-21) rather than a raw INSERT. ``audit_log`` is append-only
    (no cleanup is possible — WAL/PLT-02), so tests scope their assertions to a
    UNIQUE ``event_type`` / ``actor`` marker per test (the same fresh-marker
    discipline ``cleanup_user`` documents for users).
    """
    from app.core.audit.service import AuditService
    from app.db.session import _get_session_maker

    session_maker = _get_session_maker()
    async with session_maker() as session:
        row = await AuditService.record(
            session,
            actor=actor,
            event_type=event_type,
            payload=payload or {},
            ip=ip,
        )
        row_id = row.id
        await session.commit()
    return row_id


async def cleanup_user(engine: AsyncEngine, email: str) -> None:
    """DELETE a user + its bets (committed). Safe if absent.

    NOTE: ``transfers`` / ``entries`` are append-only (WAL-06 deny-trigger +
    REVOKE), so they CANNOT be deleted — and an ``accounts`` row referenced by an
    entry is therefore FK-pinned. We deliberately leave wallet accounts + ledger
    rows in place: every test seeds a FRESH user UUID (``seed_user`` RETURNING),
    so the leftover account (keyed on the unique owner_id) never collides with a
    later test. Only the user row and its bets are removed.
    """
    async with engine.connect() as conn:
        uid_row = (
            await conn.execute(text("SELECT id FROM users WHERE email = :em"), {"em": email})
        ).first()
        if uid_row is not None:
            uid = uid_row[0]
            await conn.execute(text("DELETE FROM bets WHERE user_id = :u"), {"u": uid})
        await conn.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})
        await conn.commit()


async def get_admin_token(c: httpx.AsyncClient) -> str:
    """Log the seeded admin in and return its Bearer access token."""
    resp = await c.post(
        "/admin/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    """Authorization header for a Bearer token."""
    return {"Authorization": f"Bearer {token}"}
