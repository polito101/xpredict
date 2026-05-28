"""Sign-up bonus service tests (Phase 5, SC#4 / WAL-02 / ADU-03).

Proves ``WalletService.grant_signup_bonus`` is:
  - **Correct:** credits the user's wallet by the bonus amount, books exactly one
    transfer (``kind=signup_bonus``) + one debit/credit entry-pair, and debits
    ``house_promo`` by the same amount.
  - **Idempotent per user:** a second grant for the same ``user_id`` (the key is
    ``bonus:{user_id}``) returns the same transfer, credits ONCE, and leaves a
    single transfer row — so re-running email verification never double-credits.
  - **Guarded:** a non-positive amount raises ``ValueError`` (defense-in-depth
    alongside the DB ``CHECK (amount > 0)``).

Uses the committed-session pattern (own ``_get_session_maker()`` sessions) like
``test_recharge.py``, because ``grant_signup_bonus`` owns its own
``session.begin()`` unit of work and cannot nest inside the rollback
``async_session`` fixture's transaction.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

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
    TRANSFER_SIGNUP_BONUS,
)
from app.wallet.models import Account, Entry, Transfer
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# Bonus amount used by the service tests (the verify-hook default is config-driven;
# the service takes ``amount`` as a parameter, so the tests pin it explicitly).
BONUS = Decimal("1000.0000")


@pytest.fixture(autouse=True)
def _require_testcontainer(engine: AsyncEngine) -> AsyncEngine:
    """Depend on ``engine`` for its side effects (container, migrate, env rewrite).

    The grant uses its own ``session.begin()`` and we assert against committed
    state with ``_get_session_maker()``, so we don't take the rollback
    ``async_session`` — but the production engine factory must see the rewritten
    ``DATABASE_URL`` first (mirrors ``test_recharge.py``).
    """
    return engine


async def _seed_user_wallet(user_id: UUID) -> UUID:
    """INSERT a ``user_wallet`` account at balance 0 (committed) and return its id."""
    wallet_id = uuid.uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :kind, :cur, 0)"
            ),
            {
                "id": wallet_id,
                "ot": OWNER_USER,
                "oid": user_id,
                "kind": KIND_USER_WALLET,
                "cur": PLAY_USD,
            },
        )
    return wallet_id


async def _balance(account_id: UUID) -> Decimal:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(Account.balance).where(Account.id == account_id))
        ).scalar_one()


async def _transfer_by_key(key: str) -> Transfer | None:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(Transfer).where(Transfer.idempotency_key == key))
        ).scalar_one_or_none()


async def _transfer_count_for_key(key: str) -> int:
    sm = _get_session_maker()
    async with sm() as s:
        return int(
            (
                await s.execute(
                    select(func.count())
                    .select_from(Transfer)
                    .where(Transfer.idempotency_key == key)
                )
            ).scalar_one()
        )


async def _entries_for_transfer(transfer_id: UUID) -> list[Entry]:
    sm = _get_session_maker()
    async with sm() as s:
        return list(
            (await s.execute(select(Entry).where(Entry.transfer_id == transfer_id))).scalars().all()
        )


# ----------------------------------------------------------------------
# 1) Grant credits the wallet — one transfer (signup_bonus) + one pair
# ----------------------------------------------------------------------
async def test_grant_signup_bonus_credits_wallet() -> None:
    """A grant credits the wallet by the bonus; one transfer + pair; house debited."""
    user_id = uuid.uuid4()
    wallet_id = await _seed_user_wallet(user_id)
    key = f"bonus:{user_id}"

    balance_before = await _balance(wallet_id)
    house_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)

    sm = _get_session_maker()
    async with sm() as session:
        await WalletService.grant_signup_bonus(session, user_id=user_id, amount=BONUS)

    # Wallet credited by exactly the bonus; house debited by the same.
    assert await _balance(wallet_id) == balance_before + BONUS
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == house_before - BONUS

    # Exactly one transfer for this user's key, kind=signup_bonus.
    transfer = await _transfer_by_key(key)
    assert transfer is not None
    assert transfer.kind == TRANSFER_SIGNUP_BONUS
    assert await _transfer_count_for_key(key) == 1

    # One debit (house) + one credit (wallet) entry, both for the bonus amount.
    entries = await _entries_for_transfer(transfer.id)
    assert len(entries) == 2
    assert {e.direction for e in entries} == {DIRECTION_DEBIT, DIRECTION_CREDIT}
    debit = next(e for e in entries if e.direction == DIRECTION_DEBIT)
    credit = next(e for e in entries if e.direction == DIRECTION_CREDIT)
    assert debit.account_id == HOUSE_PROMO_ACCOUNT_ID
    assert credit.account_id == wallet_id
    assert debit.amount == BONUS
    assert credit.amount == BONUS


# ----------------------------------------------------------------------
# 2) Same user → idempotent (key bonus:{user_id}); credited ONCE
# ----------------------------------------------------------------------
async def test_grant_signup_bonus_idempotent_same_user() -> None:
    """Two grants for the same user return the same transfer; credited once."""
    user_id = uuid.uuid4()
    wallet_id = await _seed_user_wallet(user_id)
    key = f"bonus:{user_id}"
    balance_before = await _balance(wallet_id)

    sm = _get_session_maker()
    async with sm() as s1:
        await WalletService.grant_signup_bonus(s1, user_id=user_id, amount=BONUS)
    first = await _transfer_by_key(key)
    async with sm() as s2:
        await WalletService.grant_signup_bonus(s2, user_id=user_id, amount=BONUS)
    second = await _transfer_by_key(key)

    assert first is not None
    assert second is not None
    assert first.id == second.id  # same transfer row — no second insert
    assert await _transfer_count_for_key(key) == 1
    assert await _balance(wallet_id) == balance_before + BONUS  # credited ONCE


# ----------------------------------------------------------------------
# 3) Non-positive amount → ValueError (defense-in-depth)
# ----------------------------------------------------------------------
async def test_grant_signup_bonus_rejects_nonpositive() -> None:
    """A non-positive bonus amount raises ValueError before any DB write."""
    user_id = uuid.uuid4()
    await _seed_user_wallet(user_id)
    sm = _get_session_maker()
    with pytest.raises(ValueError):
        async with sm() as session:
            await WalletService.grant_signup_bonus(session, user_id=user_id, amount=Decimal("0"))
