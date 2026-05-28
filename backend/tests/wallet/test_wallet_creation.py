"""SC#1 / WAL-01 — registration creates the wallet in the SAME transaction.

Proves the load-bearing atomicity guarantee of ``UserManager.create`` (Plan
03-03): a successful ``POST /auth/register`` leaves EXACTLY ONE ``user_wallet``
account (``PLAY_USD``, balance 0) owned by the new user, committed in the same
transaction as the user row — and a wallet-creation failure rolls the user
INSERT back too, so there is never an orphaned user (RESEARCH Pitfall 1: the
stock fastapi-users adapter commits the user BEFORE the hook fires, which is
why the wallet is co-inserted inside ``create()`` before a single commit).

The register request runs in its OWN request session (FastAPI's
``get_async_session`` dependency), NOT the rollback ``async_session`` — so we
assert against the real committed state via fresh sessions from the production
``_get_session_maker()`` (mirroring ``test_atomicity.py`` / ``harness.count_rows``)
and clean up by email so re-runs stay idempotent (mirroring ``test_register.py``).

No Mailpit dependency: ``on_after_register`` sends the verification email inside
a try/except (Phase 2 Pitfall 5), so an unreachable SMTP/Resend never blocks the
register flow or these assertions. ``RESEND_API_KEY=""`` is seeded by the auth
conftest; the send fails fast and is swallowed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select, text

from app.auth.models import User
from app.db.session import _get_session_maker
from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD
from app.wallet.models import Account
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` so the testcontainer is up + ``DATABASE_URL`` rewritten.

    These tests drive the app over its own request session (via the ``client``
    transport) and assert against committed state with their own
    ``_get_session_maker()`` sessions, so they do not use the rollback
    ``async_session`` — but they still need the ``engine`` fixture's side effects
    (container start, ``alembic upgrade head``, env rewrite, lazy-cache clear)
    before the production engine factory is first used.
    """
    return engine


def _client() -> httpx.AsyncClient:
    """An httpx client wired to the FastAPI app under test.

    ``raise_app_exceptions=False`` so an intentionally-failing register (the
    rollback test injects a fault) surfaces as a real 5xx response instead of
    re-raising the exception out of the transport.
    """
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _cleanup_user(email: str) -> None:
    """Best-effort delete of the user (and its wallet) by email, for idempotent re-runs.

    Deletes the wallet account first (no immutable ``entries`` exist for a
    freshly-registered wallet, so the row is removable) then the user row.
    Uses its own committed session — these rows were committed by the request.
    """
    session_maker = _get_session_maker()
    async with session_maker() as s, s.begin():
        user_id = (
            await s.execute(select(User.id).where(User.email == email))
        ).scalar_one_or_none()
        if user_id is not None:
            await s.execute(
                text(
                    "DELETE FROM accounts WHERE owner_type = :ot "
                    "AND owner_id = :oid AND kind = :kind"
                ),
                {"ot": OWNER_USER, "oid": user_id, "kind": KIND_USER_WALLET},
            )
        await s.execute(text("DELETE FROM users WHERE email = :em"), {"em": email})


async def _wallets_for_user(user_id) -> list[Account]:
    """Return every ``user_wallet`` account owned by ``user_id`` (own committed session)."""
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return list(
            (
                await s.execute(
                    select(Account).where(
                        Account.owner_type == OWNER_USER,
                        Account.owner_id == user_id,
                        Account.kind == KIND_USER_WALLET,
                    )
                )
            )
            .scalars()
            .all()
        )


async def _user_exists(email: str) -> bool:
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return (
            await s.execute(select(User.id).where(User.email == email))
        ).scalar_one_or_none() is not None


async def _user_wallet_count() -> int:
    """Total ``user_wallet`` account count across the DB (own committed session).

    Used as a before/after snapshot in the rollback test: a wallet that
    committed despite the user rollback would bump this count. Counting the
    delta (not a global ``NOT EXISTS`` scan) keeps the assertion immune to the
    unrelated direct-seeded accounts other ``tests/wallet`` modules commit
    (random ``owner_id`` with no matching user) — the 03-02 isolation
    discipline: scope assertions to this scenario, never the whole ledger.
    """
    session_maker = _get_session_maker()
    async with session_maker() as s:
        return int(
            (
                await s.execute(
                    text("SELECT count(*) FROM accounts WHERE kind = :kind"),
                    {"kind": KIND_USER_WALLET},
                )
            ).scalar_one()
        )


async def test_wallet_created_on_registration() -> None:
    """POST /auth/register → exactly one user_wallet (PLAY_USD, balance 0) — SC#1/WAL-01."""
    email = "wallet-create@example.com"
    await _cleanup_user(email)
    try:
        async with _client() as client:
            resp = await client.post(
                "/auth/register",
                json={"email": email, "password": "Valid-Pass-1234"},
            )
            assert resp.status_code == 201, resp.text
            user_id = resp.json()["id"]

        wallets = await _wallets_for_user(user_id)
        assert len(wallets) == 1, f"expected exactly one wallet, got {len(wallets)}"
        wallet = wallets[0]
        assert wallet.currency == PLAY_USD
        assert wallet.kind == KIND_USER_WALLET
        assert wallet.balance == Decimal("0")
    finally:
        await _cleanup_user(email)


async def test_wallet_creation_failure_rolls_back_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inject a fault into wallet creation → neither user NOR wallet committed.

    The load-bearing SC#1 atomicity proof (RESEARCH Pitfall 1 warning sign): a
    failure in ``create_wallet`` must roll back the user INSERT in the same
    request transaction, so no orphaned user survives. ``create()`` calls
    ``WalletService.create_wallet`` via class access, so patching the class
    attribute redirects the call.
    """
    email = "wallet-rollback@example.com"
    await _cleanup_user(email)

    class _InjectedWalletError(Exception):
        pass

    async def _raising_create_wallet(*_args, **_kwargs):
        raise _InjectedWalletError("injected wallet-creation fault")

    monkeypatch.setattr(
        WalletService,
        "create_wallet",
        staticmethod(_raising_create_wallet),
    )

    # Snapshot the wallet count BEFORE: a wallet committed despite the user
    # rollback would bump this by one. (Sibling tests/wallet modules seed
    # unrelated user_wallet rows, so an absolute count is meaningless — the
    # DELTA across this register attempt is the precise, isolation-safe proof.)
    wallets_before = await _user_wallet_count()

    try:
        async with _client() as client:
            resp = await client.post(
                "/auth/register",
                json={"email": email, "password": "Valid-Pass-1234"},
            )
            # The injected fault propagates out of the request → a 5xx; the
            # request session never reaches commit, so it rolls back wholesale.
            assert resp.status_code >= 400, resp.text
            assert resp.status_code != 201

        # Atomicity (SC#1): NEITHER the user NOR a wallet was committed.
        assert not await _user_exists(email), (
            "user leaked despite wallet fault (no rollback)"
        )
        wallets_after = await _user_wallet_count()
        assert wallets_after == wallets_before, (
            f"a wallet committed despite the user rollback "
            f"(before={wallets_before}, after={wallets_after})"
        )
    finally:
        await _cleanup_user(email)


async def test_no_duplicate_wallet() -> None:
    """Registering creates exactly ONE wallet — no second wallet for the same user.

    The unique ``(owner_type, owner_id, kind, currency)`` constraint shapes this;
    a single register must yield a single wallet (not two), which the count below
    asserts directly.
    """
    email = "wallet-single@example.com"
    await _cleanup_user(email)
    try:
        async with _client() as client:
            resp = await client.post(
                "/auth/register",
                json={"email": email, "password": "Valid-Pass-1234"},
            )
            assert resp.status_code == 201, resp.text
            user_id = resp.json()["id"]

        wallets = await _wallets_for_user(user_id)
        assert len(wallets) == 1, (
            f"expected a single wallet for the user, got {len(wallets)}"
        )
    finally:
        await _cleanup_user(email)
