"""Bloque 1 — DB-backed demo user seeding (verified users + funded wallets).

Against testcontainers Postgres 16: the ``engine`` fixture migrates head (so the
house accounts exist) and repoints ``_get_session_maker()`` at the container. The
seed commits through its OWN sessions, so — like ``test_signup_bonus.py`` /
``test_create_admin_script.py`` — we do NOT take the rollback ``async_session``;
we assert against committed state via fresh sessions and isolate each test under
its OWN ``email_domain`` (the append-only ledger means we cannot DELETE-clean).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import case, func, select

from app.auth.models import User
from app.db.session import _get_session_maker
from app.wallet.constants import (
    DIRECTION_CREDIT,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
    TRANSFER_RECHARGE,
    TRANSFER_SIGNUP_BONUS,
)
from app.wallet.models import Account, Entry, Transfer
from bin.seed_demo import SeedConfig, build_user_specs, seed_users

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Start the container + migrate head + repoint the production engine factory."""
    return engine


async def _users_by_domain(domain: str) -> list[User]:
    sm = _get_session_maker()
    async with sm() as s:
        return list(
            (
                await s.execute(
                    select(User)
                    .where(User.email.like(f"%@{domain}"))  # type: ignore[attr-defined]
                    .order_by(User.email)
                )
            )
            .scalars()
            .all()
        )


async def _wallet_for_user(user_id: UUID) -> Account | None:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(
                select(Account).where(
                    Account.owner_type == OWNER_USER,
                    Account.owner_id == user_id,
                    Account.kind == KIND_USER_WALLET,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one_or_none()


async def _ledger_sum(account_id: UUID) -> Decimal:
    """SUM(credit) - SUM(debit) over the account's entries — the reconcile truth."""
    sm = _get_session_maker()
    async with sm() as s:
        signed = func.coalesce(
            func.sum(
                case((Entry.direction == DIRECTION_CREDIT, Entry.amount), else_=-Entry.amount)
            ),
            0,
        )
        value = (await s.execute(select(signed).where(Entry.account_id == account_id))).scalar_one()
        return Decimal(value)


async def _transfer_kinds_for_wallet(wallet_id: UUID) -> list[str]:
    """The transfer kinds of every entry posted against ``wallet_id`` (history)."""
    sm = _get_session_maker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(Transfer.kind)
                .join(Entry, Entry.transfer_id == Transfer.id)
                .where(Entry.account_id == wallet_id)
            )
        ).all()
        return [kind for (kind,) in rows]


async def test_seed_users_creates_verified_ledger_backed_wallets() -> None:
    """Each demo user is verified + active with exactly one wallet funded to its
    expected balance, and that balance is LEDGER-BACKED (zero drift) — proving the
    money moved through the services, not a shortcut."""
    cfg = SeedConfig(n_users=3, email_domain="seed-users-core.demo.xpredict")
    specs = build_user_specs(cfg)

    seeded = await seed_users(cfg)

    assert len(seeded) == 3
    users = await _users_by_domain(cfg.email_domain)
    assert len(users) == 3
    by_email = {u.email: u for u in users}

    for spec in specs:
        user = by_email[spec.email]
        assert user.is_verified is True
        assert user.is_active is True
        assert user.display_name == spec.display_name

        wallet = await _wallet_for_user(user.id)
        assert wallet is not None
        assert wallet.currency == PLAY_USD
        # Funded to exactly bonus + recharges...
        assert wallet.balance == spec.expected_balance
        # ...and that cache is backed by the immutable ledger (no shortcut):
        # balance == SUM(credit) - SUM(debit) → zero drift on this wallet.
        assert await _ledger_sum(wallet.id) == wallet.balance


async def test_seed_users_wallet_history_uses_services() -> None:
    """Wallet history is exactly one signup_bonus plus one recharge per ladder
    step — i.e. the funding flowed through grant_signup_bonus / recharge."""
    cfg = SeedConfig(n_users=3, email_domain="seed-users-history.demo.xpredict")
    specs = build_user_specs(cfg)

    await seed_users(cfg)

    users = {u.email: u for u in await _users_by_domain(cfg.email_domain)}
    for spec in specs:
        wallet = await _wallet_for_user(users[spec.email].id)
        assert wallet is not None
        kinds = await _transfer_kinds_for_wallet(wallet.id)
        # Exactly one signup bonus + one recharge entry per recharge in the ladder.
        assert kinds.count(TRANSFER_SIGNUP_BONUS) == 1
        assert kinds.count(TRANSFER_RECHARGE) == len(spec.recharges)


async def test_seed_users_is_idempotent() -> None:
    """Re-running the seed does not duplicate users or double-credit wallets."""
    cfg = SeedConfig(n_users=2, email_domain="seed-users-idem.demo.xpredict")
    specs = build_user_specs(cfg)

    await seed_users(cfg)
    await seed_users(cfg)  # second run must be a no-op

    users = await _users_by_domain(cfg.email_domain)
    assert len(users) == 2  # not 4 — no duplicate users
    by_email = {u.email: u for u in users}
    for spec in specs:
        wallet = await _wallet_for_user(by_email[spec.email].id)
        assert wallet is not None
        assert wallet.balance == spec.expected_balance  # credited once, not twice
