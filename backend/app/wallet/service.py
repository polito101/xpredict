"""WalletService — the ONLY writer to the double-entry ledger (Phase 3, WAL-07).

A direct port of the empirically-validated spike harness
(``.planning/spikes/_lib/harness.py``) to the production ORM. The harness proved
(against real Postgres 16 via testcontainers) the four concurrency/atomicity
properties this service guarantees:

  - **Race-safe debit** — pessimistic ``SELECT ... FOR UPDATE`` on the contended
    account row, inside one ``AsyncSession.begin()`` unit of work (Spike 002:
    1.00x retry amplification — the winning strategy; ``harness._spend_once``).
  - **Atomic double-entry** — a transfer inserts the transfer row + exactly two
    entries (debit + credit, both positive, netting to zero) + both balance-cache
    updates in ONE transaction; any failure rolls EVERYTHING back (Spike 003
    part 1; ``harness.attempt_with_fault``).
  - **Idempotent recharge** — a duplicate ``idempotency_key`` raises Postgres
    ``23505`` on the ``transfers`` INSERT; we catch ``IntegrityError``, read
    ``.orig.sqlstate``, and return the EXISTING transfer (a true idempotent
    response — never a double-credit, never a 500). Spike 003 part 2: 10
    concurrent same-key → 1 applied + 9 deduped. (RESEARCH Pitfall 2: ORM inserts
    raise ``IntegrityError``, a ``DBAPIError`` subclass — catch the subclass.)
  - **Deadlock-free multi-account locks** — recharge touches two accounts
    (``house_promo`` source + ``user_wallet`` destination). Both ``FOR UPDATE``
    locks are acquired in CANONICAL UUID ORDER (``sorted(ids, key=str)``) so no
    lock-ordering cycle can form (Spike 004: unordered → ``40P01``, ordered → 0;
    ``harness.locked_transfer``).

Transaction-boundary contract (mirrors ``AuditService.record``): the methods that
participate in a larger unit of work — namely ``create_wallet`` — take the
caller's ``AsyncSession`` and only ``add`` + ``flush``, NEVER ``commit``. The
registration override (Plan 03-03) creates the wallet on the SAME session as the
user INSERT so the two commit atomically (SC#1). ``recharge`` is a self-contained
operation, so it owns its own ``session.begin()`` block.

``CHECK (balance >= 0)`` (migration 0003) is the DB-level last line of defense
(WAL-08), NOT the primary concurrency guard — ``FOR UPDATE`` is. The service also
raises :class:`InsufficientBalance` *before* the DB write so callers get a domain
error rather than a raw 23514 (LOCKING-ATOMICITY §3 nuance; RESEARCH Anti-Patterns).

SQLAlchemy-2.0 caveat (harness comment): ``SERIALIZABLE`` is engine-wide, so the
chosen strategy is plain READ COMMITTED + ``FOR UPDATE`` — the validated winner.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.wallet.constants import (
    DIRECTION_CREDIT,
    DIRECTION_DEBIT,
    HOUSE_PROMO_ACCOUNT_ID,
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
    TRANSFER_RECHARGE,
)
from app.wallet.exceptions import InsufficientBalance
from app.wallet.models import Account, Entry, Transfer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User

# Postgres SQLSTATE for a unique-constraint violation — the idempotency signal.
# Identical to the harness ``SQLSTATE_UNIQUE_VIOLATION`` (harness line 78).
SQLSTATE_UNIQUE_VIOLATION = "23505"

# Recharge payment providers. v1 only funds from the house; "stripe" is a v2 stub
# so the method signature is final now and never needs a breaking change later.
PROVIDER_HOUSE = "house"
PROVIDER_STRIPE = "stripe"


class WalletService:
    """The single ledger writer. Mirrors ``AuditService`` — stateless static methods.

    No other code path may ``INSERT INTO transfers``/``entries`` or mutate
    ``accounts.balance``; every value movement goes through this class so the
    FOR UPDATE / double-entry / idempotency / lock-ordering invariants hold in
    exactly one place (WAL-07).
    """

    # ------------------------------------------------------------------ #
    # Wallet provisioning — caller-owned transaction (SC#1).
    # ------------------------------------------------------------------ #
    @staticmethod
    async def create_wallet(session: AsyncSession, *, user: User) -> Account:
        """Create the user's ``user_wallet`` account on the CALLER's transaction.

        ``add`` + ``flush`` ONLY — never ``commit`` (mirrors
        ``AuditService.record``). The registration override (Plan 03-03) calls
        this between the user INSERT and its single commit so the user row and
        the wallet row land in ONE transaction (SC#1); committing here would
        split that unit of work and a later failure would leave a committed user
        with no wallet (RESEARCH Pitfall 1 / Anti-Patterns line 367).

        Opens at ``balance = 0`` — funding (if any) is a subsequent recharge, not
        an opening grant, so the ledger truth ``SUM(entries)`` stays consistent.
        """
        account = Account(
            owner_type=OWNER_USER,
            owner_id=user.id,
            kind=KIND_USER_WALLET,
            currency=PLAY_USD,
            balance=Decimal("0"),
        )
        session.add(account)
        await session.flush()  # populate server-defaulted id; NO commit (caller owns it)
        return account

    # ------------------------------------------------------------------ #
    # Internal: the double-entry move. Assumes locks are already held.
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _post_transfer(
        session: AsyncSession,
        *,
        kind: str,
        idempotency_key: str | None,
        actor_user_id: UUID | None,
        debit_account_id: UUID,
        credit_account_id: UUID,
        amount: Decimal,
        metadata: dict[str, Any] | None = None,
    ) -> Transfer:
        """Insert a transfer + its two balancing entries + both balance updates.

        Caller MUST already hold the ``FOR UPDATE`` row locks on both accounts and
        be inside a ``session.begin()`` block. Ports ``harness._spend_once`` lines
        237-283: one transfer, a debit + a credit entry (both ``amount`` > 0,
        netting to zero), then the debit account decrement (with ``version + 1``)
        and the credit account increment — all via the ORM ``update(Account)``
        construct (RESEARCH Pattern 1 lines 234-246).
        """
        transfer = Transfer(
            kind=kind,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            transfer_metadata=metadata or {},
        )
        session.add(transfer)
        await session.flush()  # get transfer.id for the entries' FK

        session.add_all(
            [
                Entry(
                    transfer_id=transfer.id,
                    account_id=debit_account_id,
                    direction=DIRECTION_DEBIT,
                    amount=amount,
                ),
                Entry(
                    transfer_id=transfer.id,
                    account_id=credit_account_id,
                    direction=DIRECTION_CREDIT,
                    amount=amount,
                ),
            ]
        )

        # Debit the source: decrement the cache + bump the optimistic version.
        await session.execute(
            update(Account)
            .where(Account.id == debit_account_id)
            .values(balance=Account.balance - amount, version=Account.version + 1)
        )
        # Credit the destination.
        await session.execute(
            update(Account)
            .where(Account.id == credit_account_id)
            .values(balance=Account.balance + amount)
        )
        # Surface server-defaulted columns (e.g. created_at) without expiring.
        await session.flush()
        return transfer

    # ------------------------------------------------------------------ #
    # Recharge — fund a user wallet from the house, race-safe + idempotent.
    # ------------------------------------------------------------------ #
    @classmethod
    async def recharge(
        cls,
        session: AsyncSession,
        *,
        user_id: UUID,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
        payment_provider: str = PROVIDER_HOUSE,
    ) -> Transfer:
        """Credit ``user_id``'s wallet by ``amount`` from ``house_promo``.

        Self-contained operation: owns its ``session.begin()`` unit of work.

        - ``payment_provider="stripe"`` raises :class:`NotImplementedError` — a v2
          stub so this signature is final and 03-04/03-05 need no later refactor
          (SC#6).
        - Acquires BOTH ``FOR UPDATE`` locks in canonical UUID order
          (``sorted((src, dst), key=str)``) BEFORE mutating (Spike 004 / Pitfall 3).
        - A duplicate ``idempotency_key`` raises ``IntegrityError`` / sqlstate
          ``23505``; we SELECT and return the EXISTING transfer — a true idempotent
          response, no double-credit (Spike 003 part 2 / Pitfall 2). Any other
          IntegrityError re-raises.

        ``amount`` must be a positive ``Decimal`` (``ValueError`` otherwise —
        defense-in-depth alongside the DB ``CHECK (amount > 0)``).
        """
        if payment_provider == PROVIDER_STRIPE:
            raise NotImplementedError("stripe recharge is a v2 stub")
        if payment_provider != PROVIDER_HOUSE:
            raise ValueError(f"unknown payment_provider: {payment_provider!r}")
        if amount <= 0:
            raise ValueError("recharge amount must be > 0")

        src_id = HOUSE_PROMO_ACCOUNT_ID

        try:
            async with session.begin():
                # Resolve the target wallet INSIDE the unit of work — issuing it
                # before ``session.begin()`` would autobegin an implicit tx and
                # make ``begin()`` raise "a transaction is already begun".
                dst_id = await cls._resolve_user_wallet_id(session, user_id=user_id)

                # Canonical UUID lock order (Spike 004): sort the two account ids
                # by their string form and FOR UPDATE in that order so no two
                # transfer types can form a lock-ordering cycle (Pitfall 3).
                first_id, second_id = sorted((src_id, dst_id), key=str)
                await session.execute(
                    select(Account.id).where(Account.id == first_id).with_for_update()
                )
                await session.execute(
                    select(Account.id).where(Account.id == second_id).with_for_update()
                )

                return await cls._post_transfer(
                    session,
                    kind=TRANSFER_RECHARGE,
                    idempotency_key=idempotency_key,
                    actor_user_id=None,  # admin/system-initiated (RESEARCH OQ2)
                    debit_account_id=src_id,
                    credit_account_id=dst_id,
                    amount=amount,
                    metadata={"reason": reason},
                )
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == SQLSTATE_UNIQUE_VIOLATION:
                # The begin() block already rolled back; read the winner's transfer
                # on a fresh statement and return it (idempotent 200 — no re-apply).
                existing = (
                    await session.execute(
                        select(Transfer).where(
                            Transfer.idempotency_key == idempotency_key
                        )
                    )
                ).scalar_one()
                return existing
            raise

    # ------------------------------------------------------------------ #
    # Transfer — the race-safe, balance-checked debit->credit primitive.
    # ------------------------------------------------------------------ #
    @classmethod
    async def transfer(
        cls,
        session: AsyncSession,
        *,
        kind: str,
        debit_account_id: UUID,
        credit_account_id: UUID,
        amount: Decimal,
        actor_user_id: UUID | None = None,
        idempotency_key: str | None = None,
        reason: str | None = None,
    ) -> Transfer:
        """Move ``amount`` from ``debit_account_id`` to ``credit_account_id``.

        The general race-safe primitive that ``recharge`` is a specialization of
        and that Phase 5 bet-placement reuses. Owns its own ``session.begin()``
        unit of work and is a faithful port of ``harness._spend_once`` (the
        ``for_update`` strategy) + ``harness.locked_transfer`` (canonical order):

        - Acquires BOTH ``FOR UPDATE`` locks in canonical UUID order
          (``sorted(ids, key=str)``) BEFORE the balance read — Spike 004, so no
          two transfer types can deadlock (40P01).
        - Re-reads the locked debit balance and raises :class:`InsufficientBalance`
          if it cannot cover ``amount`` — the domain-level guard in FRONT of the
          DB ``CHECK (balance >= 0)`` (WAL-08, defense-in-depth). FOR UPDATE is the
          PRIMARY concurrency control; the CHECK is the net (RESEARCH Anti-Patterns).
        - Posts the double-entry move atomically; any failure rolls everything back.

        ``amount`` must be a positive ``Decimal`` (``ValueError`` otherwise).
        """
        if amount <= 0:
            raise ValueError("transfer amount must be > 0")

        async with session.begin():
            # Canonical UUID lock order (Spike 004 / Pitfall 3) BEFORE any mutate.
            first_id, second_id = sorted((debit_account_id, credit_account_id), key=str)
            await session.execute(
                select(Account.id).where(Account.id == first_id).with_for_update()
            )
            await session.execute(
                select(Account.id).where(Account.id == second_id).with_for_update()
            )

            # Now that the debit row is locked, read its balance and reject an
            # overdraw with a domain error (not a raw 23514). The lock guarantees
            # no concurrent debit can race between this read and the write.
            debit_balance = (
                await session.execute(
                    select(Account.balance).where(Account.id == debit_account_id)
                )
            ).scalar_one()
            if debit_balance < amount:
                raise InsufficientBalance(
                    f"account {debit_account_id} balance {debit_balance} "
                    f"< requested {amount}"
                )

            return await cls._post_transfer(
                session,
                kind=kind,
                idempotency_key=idempotency_key,
                actor_user_id=actor_user_id,
                debit_account_id=debit_account_id,
                credit_account_id=credit_account_id,
                amount=amount,
                metadata={"reason": reason} if reason is not None else None,
            )

    # ------------------------------------------------------------------ #
    # Read helpers (minimal — full read shaping is Plan 03-05).
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _resolve_user_wallet_id(
        session: AsyncSession, *, user_id: UUID
    ) -> UUID:
        """Return the ``user_wallet`` account id for ``user_id`` (read-only)."""
        return (
            await session.execute(
                select(Account.id).where(
                    Account.owner_type == OWNER_USER,
                    Account.owner_id == user_id,
                    Account.kind == KIND_USER_WALLET,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one()

    @classmethod
    async def get_balance(cls, session: AsyncSession, *, user_id: UUID) -> Decimal:
        """Return the user's wallet balance cache (read-only; full reads are 03-05)."""
        wallet_id = await cls._resolve_user_wallet_id(session, user_id=user_id)
        return (
            await session.execute(
                select(Account.balance).where(Account.id == wallet_id)
            )
        ).scalar_one()
