"""Seed a believable demo dataset for sales demos (v1.1 Demo Polish — Fase B).

Populates the DB with realistic, fully-wired data so EVERY player screen has
content: home (open house markets), market-detail (a real price-chart from odds
history), portfolio (open + settled positions with P&L) and wallet (a funded
balance with transaction history). A companion ``--reset`` mode wipes the demo
dataset back to a clean migrated schema.

Mirrors ``bin/create_admin.py``: an ``async`` core driven by ``asyncio.run`` that
opens its own sessions via ``app.db.session._get_session_maker()``. Run it with::

    cd backend
    uv run python bin/seed_demo.py            # populate
    uv run python bin/seed_demo.py --reset    # wipe + re-seed clean

PRECONDITION: ``alembic upgrade head`` — recharge and settlement debit the
Alembic-seeded ``house_promo`` / ``house_revenue`` singletons (the ledger
precondition); the demo never writes those by hand.

MONEY DISCIPLINE (it is money — non-negotiable): every amount is a ``Decimal``
built from a string, and ALL value movement flows through the validated wallet /
bet / settlement services (``grant_signup_bonus`` / ``recharge`` / ``place_bet``
/ ``resolve_market``) — never a hand-written transfer/entry, never a raw
``accounts.balance`` mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from pwdlib import PasswordHash
from sqlalchemy import select

from app.auth.models import User
from app.db.session import _get_session_maker
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Default email domain for the demo player set. Overridable per ``SeedConfig`` so
# each integration test can seed under its own namespace — the ledger is
# append-only (entries cannot be DELETEd), so tests isolate via a private domain
# rather than by row deletion.
DEMO_EMAIL_DOMAIN = "demo.xpredict"

# The one-time signup bonus every demo player receives (Decimal-from-string).
SIGNUP_BONUS = Decimal("1000.0000")

# Operator-trusted bootstrap password shared by every demo player (play-money
# demo only). Same rationale as bin/create_admin.py: the operator owns what goes
# into a demo, so we INSERT directly and bypass UserManager.validate_password.
DEMO_USER_PASSWORD = "Demo-Player-Pass-1!"  # nosec B105  # gitleaks:allow

# Deterministic recharge ladders, picked by the player's index position so wallet
# history varies: some players never recharge, some top up once, some twice.
_RECHARGE_LADDERS: tuple[tuple[Decimal, ...], ...] = (
    (),
    (Decimal("500.0000"),),
    (Decimal("250.0000"), Decimal("750.0000")),
)

# Realistic-looking display names, cycled by index (binary play-money demo).
_DISPLAY_NAMES: tuple[str, ...] = (
    "Alice Nguyen",
    "Bob Martins",
    "Carol Dasilva",
    "Dave Okafor",
    "Erin Haddad",
    "Frank Moreau",
    "Grace Liang",
    "Heidi Brandt",
    "Ivan Petrov",
    "Judy Almeida",
    "Karl Vogt",
    "Lena Sorensen",
)


@dataclass(frozen=True)
class SeedConfig:
    """Size + namespace of the demo dataset.

    ``email_domain`` is overridable so each integration test seeds under its own
    namespace (the append-only ledger means tests cannot clean up by deleting
    rows; a private domain keeps assertions scoped and collision-free).
    """

    n_users: int = 10
    email_domain: str = DEMO_EMAIL_DOMAIN


@dataclass(frozen=True)
class DemoUserSpec:
    """The deterministic description of one demo player to seed."""

    email: str
    display_name: str
    signup_bonus: Decimal
    recharges: tuple[Decimal, ...]

    @property
    def expected_balance(self) -> Decimal:
        """Funded wallet balance after the signup bonus + every recharge."""
        return self.signup_bonus + sum(self.recharges, Decimal("0"))


def build_user_specs(cfg: SeedConfig) -> list[DemoUserSpec]:
    """Build the deterministic demo-player list for ``cfg`` (pure; no I/O)."""
    return [
        DemoUserSpec(
            email=f"demo-user-{i:02d}@{cfg.email_domain}",
            display_name=_DISPLAY_NAMES[i % len(_DISPLAY_NAMES)],
            signup_bonus=SIGNUP_BONUS,
            recharges=_RECHARGE_LADDERS[i % len(_RECHARGE_LADDERS)],
        )
        for i in range(cfg.n_users)
    ]


@dataclass(frozen=True)
class SeededUser:
    """A seeded demo player's identity — returned for downstream blocks (bets)."""

    id: UUID
    email: str
    display_name: str


async def _ensure_user_with_wallet(
    session_maker: async_sessionmaker[AsyncSession],
    spec: DemoUserSpec,
    hasher: PasswordHash,
) -> UUID:
    """Resolve the demo user's id, creating user + wallet atomically if absent.

    Idempotent: an existing email is reused. Creation co-inserts the wallet in the
    SAME transaction as the user (SC#1) and commits once. The read-only
    "already exists" path leaves the session with NO open tx (the context manager
    rolls back the implicit read) so the caller's self-committing funding services
    can safely open their own ``session.begin()`` — the repo's begin()-on-open-tx
    hazard.
    """
    async with session_maker() as session:
        existing = (
            await session.execute(
                select(User).where(User.email == spec.email)  # type: ignore[arg-type]
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id

        user = User(
            email=spec.email,
            hashed_password=hasher.hash(DEMO_USER_PASSWORD),
            is_active=True,
            is_verified=True,
            display_name=spec.display_name,
        )
        session.add(user)
        await session.flush()  # autobegin + populate user.id
        await WalletService.create_wallet(session, user=user)
        user_id = user.id
        await session.commit()  # user + wallet land atomically (SC#1)
        return user_id


async def _fund_wallet(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: UUID,
    spec: DemoUserSpec,
) -> None:
    """Fund the wallet through the validated services (idempotent re-funding).

    Each service runs on its OWN fresh session. ``grant_signup_bonus`` / ``recharge``
    open their own ``session.begin()`` AND, on the idempotent 23505 replay path,
    leave a dangling implicit read tx — so chaining them on one shared session would
    trip "a transaction is already begun" on the next call (the repo's
    begin()-on-open-tx hazard). A session-per-call sidesteps it; per-user
    idempotency keys make a re-run a true no-op (never a double-credit).
    """
    async with session_maker() as session:
        await WalletService.grant_signup_bonus(session, user_id=user_id, amount=spec.signup_bonus)
    for index, amount in enumerate(spec.recharges):
        async with session_maker() as session:
            await WalletService.recharge(
                session,
                user_id=user_id,
                amount=amount,
                reason="demo_recharge",
                idempotency_key=f"demo-recharge:{user_id}:{index}",
            )


async def seed_users(cfg: SeedConfig) -> list[SeededUser]:
    """Seed verified demo players, each with a funded, ledger-backed wallet.

    Idempotent and order-independent: re-running reuses existing users and never
    double-credits (the bonus/recharge idempotency keys absorb the replay). ALL
    funding flows through the validated wallet services — no hand-written ledger
    rows, no raw balance mutation.
    """
    hasher = PasswordHash.recommended()
    session_maker = _get_session_maker()
    seeded: list[SeededUser] = []
    for spec in build_user_specs(cfg):
        user_id = await _ensure_user_with_wallet(session_maker, spec, hasher)
        await _fund_wallet(session_maker, user_id, spec)
        seeded.append(SeededUser(id=user_id, email=spec.email, display_name=spec.display_name))
    return seeded
