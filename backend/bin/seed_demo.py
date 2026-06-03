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

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from pwdlib import PasswordHash
from sqlalchemy import insert, select

from app.auth.models import User
from app.bets.adapters import HouseMarketReadAdapter
from app.bets.service import BetService
from app.core.config import get_settings
from app.db.session import _get_session_maker
from app.markets.models import OddsSnapshot, Outcome
from app.markets.schemas import MarketCreate
from app.markets.service import MarketService
from app.settlement.adapters import HouseMarketResolveAdapter
from app.settlement.service import SettlementService
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from collections.abc import Sequence
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
    n_markets: int = 15
    n_resolved_markets: int = 4
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


# --------------------------------------------------------------------------- #
# Bloque 2 — house markets (OPEN). The demo spine: home, market-detail, charts.
# --------------------------------------------------------------------------- #

# Believable binary prediction markets for the demo home. Each tuple is
# (question, resolution_criteria, category, initial_odds_yes, deadline_offset_days).
# Odds are Decimal-from-string in (0, 1); offsets are strictly future. Kept long
# enough that the medium volume (15) never repeats a question.
_MARKET_TEMPLATES: tuple[tuple[str, str, str, Decimal, int], ...] = (
    (
        "Will Bitcoin close above $100,000 by the deadline?",
        "Resolves YES if the BTC/USD daily close on a major exchange is above "
        "$100,000 on or before the deadline.",
        "Crypto",
        Decimal("0.62"),
        45,
    ),
    (
        "Will the central bank cut interest rates at its next meeting?",
        "Resolves YES if the policy rate is lowered at the next scheduled meeting "
        "per the official statement.",
        "Economy",
        Decimal("0.55"),
        30,
    ),
    (
        "Will a crewed lunar flyby launch this year?",
        "Resolves YES if a crewed mission performs a lunar flyby on or before the "
        "deadline, per the operator's confirmation.",
        "Space",
        Decimal("0.28"),
        120,
    ),
    (
        "Will the home team win the national championship final?",
        "Resolves YES if the home team is the official champion of the final.",
        "Sports",
        Decimal("0.48"),
        21,
    ),
    (
        "Will a major lab release a model topping the public leaderboard?",
        "Resolves YES if a new model takes the #1 spot on the agreed public "
        "benchmark leaderboard before the deadline.",
        "Tech",
        Decimal("0.70"),
        60,
    ),
    (
        "Will this season set a new monthly temperature record?",
        "Resolves YES if an official agency reports a record monthly global mean "
        "temperature within the window.",
        "Climate",
        Decimal("0.66"),
        40,
    ),
    (
        "Will the incumbent party win the upcoming election?",
        "Resolves YES if the incumbent party wins per the certified result.",
        "Politics",
        Decimal("0.52"),
        90,
    ),
    (
        "Will Ethereum set a new all-time high this year?",
        "Resolves YES if ETH/USD prints a new all-time high on a major exchange "
        "before the deadline.",
        "Crypto",
        Decimal("0.34"),
        75,
    ),
    (
        "Will the summer blockbuster gross over $1B worldwide?",
        "Resolves YES if reported worldwide box office exceeds $1B before the " "deadline.",
        "Entertainment",
        Decimal("0.40"),
        50,
    ),
    (
        "Will unemployment fall below 4% in the next report?",
        "Resolves YES if the headline unemployment rate is below 4.0% in the next "
        "official jobs report.",
        "Economy",
        Decimal("0.45"),
        25,
    ),
    (
        "Will the new flagship phone ship on-device AI features?",
        "Resolves YES if the announced flagship ships with the advertised "
        "on-device AI features by the deadline.",
        "Tech",
        Decimal("0.58"),
        35,
    ),
    (
        "Will the league MVP be a first-time winner this season?",
        "Resolves YES if the official MVP has never previously won the award.",
        "Sports",
        Decimal("0.50"),
        28,
    ),
    (
        "Will oil close above $90 a barrel by month end?",
        "Resolves YES if the front-month crude benchmark settles above $90 on the "
        "last trading day of the month.",
        "Commodities",
        Decimal("0.43"),
        18,
    ),
    (
        "Will a Category 5 hurricane form this season?",
        "Resolves YES if an official agency classifies any storm as Category 5 "
        "within the window.",
        "Climate",
        Decimal("0.37"),
        70,
    ),
    (
        "Will the tech IPO price above its target range?",
        "Resolves YES if the final IPO price is above the stated target range.",
        "Finance",
        Decimal("0.60"),
        33,
    ),
    (
        "Will the streaming series top the global chart three weeks running?",
        "Resolves YES if the series holds the #1 global chart spot for three "
        "consecutive weeks before the deadline.",
        "Entertainment",
        Decimal("0.31"),
        22,
    ),
    (
        "Will the central bank hold rates steady through the period?",
        "Resolves YES if the policy rate is unchanged at every scheduled meeting "
        "within the window.",
        "Economy",
        Decimal("0.47"),
        110,
    ),
    (
        "Will the rover confirm subsurface water at its new site?",
        "Resolves YES if the mission team officially confirms subsurface water at "
        "the new site before the deadline.",
        "Space",
        Decimal("0.36"),
        95,
    ),
)


@dataclass(frozen=True)
class DemoMarketSpec:
    """The deterministic description of one demo house market to seed.

    ``resolve_to`` is ``"YES"``/``"NO"`` for the subset Bloque 5 settles (so the
    portfolio shows settled P&L), else ``None`` (stays OPEN). ``deadline_offset_days``
    is added to ``now`` at seed time so the deadline is always strictly future —
    required by ``MarketCreate`` and by ``place_bet``'s ``is_open`` check.
    """

    question: str
    resolution_criteria: str
    category: str
    initial_odds_yes: Decimal
    deadline_offset_days: int
    resolve_to: str | None


def build_market_specs(cfg: SeedConfig) -> list[DemoMarketSpec]:
    """Build the deterministic demo-market list for ``cfg`` (pure; no I/O).

    The first ``n_resolved_markets`` are flagged for resolution with a
    deterministic alternating winning side (even index → YES, odd → NO); the rest
    stay OPEN. Questions stay unique past the template count via a round suffix.
    """
    n_resolved = min(cfg.n_resolved_markets, cfg.n_markets)
    specs: list[DemoMarketSpec] = []
    for i in range(cfg.n_markets):
        question, criteria, category, odds, offset = _MARKET_TEMPLATES[i % len(_MARKET_TEMPLATES)]
        if i >= len(_MARKET_TEMPLATES):
            question = f"{question} (Round {i // len(_MARKET_TEMPLATES) + 1})"
        resolve_to = ("YES" if i % 2 == 0 else "NO") if i < n_resolved else None
        specs.append(
            DemoMarketSpec(
                question=question,
                resolution_criteria=criteria,
                category=category,
                initial_odds_yes=odds,
                deadline_offset_days=offset,
                resolve_to=resolve_to,
            )
        )
    return specs


@dataclass(frozen=True)
class SeededMarket:
    """A seeded house market's ids — consumed by Bloques 3 (odds), 4 (bets), 5 (resolve)."""

    id: UUID
    slug: str
    question: str
    yes_outcome_id: UUID
    no_outcome_id: UUID
    initial_odds_yes: Decimal
    resolve_to: str | None

    @property
    def winning_outcome_id(self) -> UUID | None:
        """The outcome id Bloque 5 resolves to, or ``None`` if this market stays open."""
        if self.resolve_to == "YES":
            return self.yes_outcome_id
        if self.resolve_to == "NO":
            return self.no_outcome_id
        return None


async def _ensure_demo_admin(
    session_maker: async_sessionmaker[AsyncSession], cfg: SeedConfig
) -> UUID:
    """Resolve (or create) the demo admin — a verified superuser, idempotent by email.

    The market author for ``create_market`` (it reads ``admin_user.id`` for the audit
    row). Namespaced by ``cfg.email_domain`` and reused on a re-run.
    """
    email = f"demo-admin@{cfg.email_domain}"
    async with session_maker() as session:
        existing = (
            await session.execute(
                select(User).where(User.email == email)  # type: ignore[arg-type]
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id

        admin = User(
            email=email,
            hashed_password=PasswordHash.recommended().hash(DEMO_USER_PASSWORD),
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.flush()
        admin_id = admin.id
        await session.commit()
        return admin_id


async def seed_markets(cfg: SeedConfig) -> list[SeededMarket]:
    """Seed OPEN house markets via ``MarketService`` (committed); return their ids.

    Creates (or reuses) the demo admin, then creates each market through
    ``MarketService.create_market`` (caller-owned: it add+flushes, we commit ONCE so
    the bet read-adapter — which reads on its own connection — sees them). YES/NO
    outcome ids are read back post-commit for the downstream blocks.

    NOT idempotent on its own — re-running adds new markets (no question UNIQUE); the
    orchestrator guards against a double-seed and ``--reset`` wipes first.
    """
    specs = build_market_specs(cfg)
    session_maker = _get_session_maker()
    admin_id = await _ensure_demo_admin(session_maker, cfg)

    created: list[tuple[UUID, str, DemoMarketSpec]] = []
    async with session_maker() as session:
        admin = await session.get(User, admin_id)
        if admin is None:  # defensive — just ensured above
            raise RuntimeError("demo admin vanished mid-seed")
        for spec in specs:
            deadline = datetime.now(UTC) + timedelta(days=spec.deadline_offset_days)
            body = MarketCreate(
                question=spec.question,
                resolution_criteria=spec.resolution_criteria,
                deadline=deadline,
                initial_odds_yes=spec.initial_odds_yes,
                category=spec.category,
            )
            market = await MarketService.create_market(session, admin, body)
            created.append((market.id, market.slug, spec))
        await session.commit()

    seeded: list[SeededMarket] = []
    async with session_maker() as session:
        for market_id, slug, spec in created:
            rows = (
                await session.execute(
                    select(Outcome.id, Outcome.label).where(Outcome.market_id == market_id)
                )
            ).all()
            yes_id = next(oid for oid, label in rows if label.upper() == "YES")
            no_id = next(oid for oid, label in rows if label.upper() == "NO")
            seeded.append(
                SeededMarket(
                    id=market_id,
                    slug=slug,
                    question=spec.question,
                    yes_outcome_id=yes_id,
                    no_outcome_id=no_id,
                    initial_odds_yes=spec.initial_odds_yes,
                    resolve_to=spec.resolve_to,
                )
            )
    return seeded


# --------------------------------------------------------------------------- #
# Bloque 3 — odds history. ~30 days of OddsSnapshot rows so the price-history
# charts render in every window (24h/7d/30d), converging to current odds.
# --------------------------------------------------------------------------- #

# A point every few hours across 30 days — every window lands well above the
# 2-point chart minimum (24h≈8, 7d≈56, 30d≈240 points).
_HISTORY_DAYS = 30
_HISTORY_INTERVAL_HOURS = 3
_HISTORY_STEPS = _HISTORY_DAYS * 24 // _HISTORY_INTERVAL_HOURS


def _odds_walk(base: Decimal, seed: int, step: int, total_steps: int) -> Decimal:
    """Deterministic YES probability at ``step`` that converges to ``base`` at the end.

    A decaying sine wobble plus a decaying start offset (both varied by ``seed`` — the
    market's position — so each chart looks distinct yet reproducible), clamped to
    (0,1) for the odds CHECK. Not money: quantized to the 6-dp Odds scale via a string
    so no binary-float artifact reaches the column.
    """
    t = step / (total_steps - 1)  # 0.0 .. 1.0
    wobble = math.sin((step + seed * 7) * 0.4) * 0.08 * (1.0 - t)
    start_offset = ((seed % 5) - 2) * 0.05  # -0.10 .. +0.10
    value = float(base) + wobble + start_offset * (1.0 - t)
    value = min(0.98, max(0.02, value))
    return Decimal(str(round(value, 6)))


async def seed_odds_history(cfg: SeedConfig, markets: Sequence[SeededMarket]) -> int:
    """Backfill ~30 days of OddsSnapshot rows per market (returns the row count).

    Direct bulk insert — odds_snapshots are NOT money (the ledger discipline covers
    transfers/entries), and there is no backfill service (``create_market`` only
    stamps a single now-snapshot). The YES series is a deterministic walk converging
    to the market's current YES odds; NO is its complement (1 - YES). Timestamps run
    from ~30 days ago up to a few hours before now, so they sit before the
    create_market now-snapshot rather than colliding with it.

    ``cfg`` is accepted for API symmetry with the other ``seed_*`` steps.
    """
    session_maker = _get_session_maker()
    tenant_id = get_settings().TENANT_ID_DEFAULT
    now = datetime.now(UTC)

    rows: list[dict[str, object]] = []
    for seed, market in enumerate(markets):
        for step in range(_HISTORY_STEPS):
            snapshot_at = now - timedelta(hours=_HISTORY_INTERVAL_HOURS * (_HISTORY_STEPS - step))
            yes_p = _odds_walk(market.initial_odds_yes, seed, step, _HISTORY_STEPS)
            no_p = Decimal("1") - yes_p
            rows.append(
                {
                    "market_id": market.id,
                    "outcome_id": market.yes_outcome_id,
                    "probability": yes_p,
                    "snapshot_at": snapshot_at,
                    "tenant_id": tenant_id,
                }
            )
            rows.append(
                {
                    "market_id": market.id,
                    "outcome_id": market.no_outcome_id,
                    "probability": no_p,
                    "snapshot_at": snapshot_at,
                    "tenant_id": tenant_id,
                }
            )

    if not rows:
        return 0
    async with session_maker() as session, session.begin():
        await session.execute(insert(OddsSnapshot), rows)
    return len(rows)


# --------------------------------------------------------------------------- #
# Bloque 4 — bets. Spread deterministically across users + markets, always
# spanning both sides so resolved markets yield winners AND losers.
# --------------------------------------------------------------------------- #

# Deterministic stake ladder (Decimal-from-string), small vs the funded balance
# so no placement overdraws the wallet.
_BET_STAKES: tuple[Decimal, ...] = (
    Decimal("25.0000"),
    Decimal("50.0000"),
    Decimal("40.0000"),
    Decimal("60.0000"),
    Decimal("30.0000"),
)


@dataclass(frozen=True)
class BetSpec:
    """One deterministic demo bet, by user/market position + side + stake."""

    user_index: int
    market_index: int
    side: str  # "YES" / "NO"
    stake: Decimal


def build_bet_specs(cfg: SeedConfig) -> list[BetSpec]:
    """Build the deterministic demo-bet list for ``cfg`` (pure; no I/O).

    Each market gets 4-7 bettors with ALTERNATING sides (k even -> YES, odd -> NO),
    so every market — resolved or not — carries at least one YES and one NO bet
    (winners and losers once settled). Bettors and stakes cycle by position so the
    spread is varied yet reproducible.
    """
    n_markets = len(build_market_specs(cfg))
    specs: list[BetSpec] = []
    for j in range(n_markets):
        n_bettors = 4 + (j % 4)  # 4..7 bettors per market
        for k in range(n_bettors):
            specs.append(
                BetSpec(
                    user_index=(j + k) % cfg.n_users,
                    market_index=j,
                    side="YES" if k % 2 == 0 else "NO",
                    stake=_BET_STAKES[(j + k) % len(_BET_STAKES)],
                )
            )
    return specs


async def seed_bets(
    cfg: SeedConfig,
    users: Sequence[SeededUser],
    markets: Sequence[SeededMarket],
) -> int:
    """Place the deterministic demo bets via ``BetService.place_bet`` (returns count).

    Each bet runs on its OWN fresh session: place_bet drives its own
    liability-account + bet transactions, so a session-per-bet keeps the
    begin()-on-open-tx hazard out of reach and isolates any rejection. Markets must
    be committed + OPEN with a future deadline (Bloques 2/3 guarantee that). Money
    moves only through the validated bet path — no hand-written ledger rows.
    """
    specs = build_bet_specs(cfg)
    session_maker = _get_session_maker()
    market_source = HouseMarketReadAdapter()
    placed = 0
    for spec in specs:
        user = users[spec.user_index]
        market = markets[spec.market_index]
        outcome_id = market.yes_outcome_id if spec.side == "YES" else market.no_outcome_id
        async with session_maker() as session:
            await BetService.place_bet(
                session,
                user_id=user.id,
                market_id=market.id,
                outcome_id=outcome_id,
                stake=spec.stake,
                market_source=market_source,
            )
        placed += 1
    return placed


# --------------------------------------------------------------------------- #
# Bloque 5 — resolution. Settle the flagged markets through SettlementService so
# the portfolio shows settled positions with realized P&L (winners + losers).
# --------------------------------------------------------------------------- #


async def seed_resolutions(cfg: SeedConfig, markets: Sequence[SeededMarket]) -> int:
    """Resolve the flagged markets via ``SettlementService.resolve_market`` (count).

    Settlement is the ONLY way state + money move here — never a hand-flipped status
    or hand-written payout (that would break ledger / P&L / audit). Each resolution
    runs on its own fresh session (resolve_market owns its begin()). We pass
    ``winning_outcome_id`` today; once Phase 12 persists the winner on the Market
    model, the same call records it with no seed change.
    """
    session_maker = _get_session_maker()
    admin_id = await _ensure_demo_admin(session_maker, cfg)
    resolver = HouseMarketResolveAdapter()
    resolved = 0
    for market in markets:
        winning_outcome_id = market.winning_outcome_id
        if winning_outcome_id is None:
            continue  # stays OPEN
        async with session_maker() as session:
            await SettlementService.resolve_market(
                session,
                market_id=market.id,
                winning_outcome_id=winning_outcome_id,
                market_resolver=resolver,
                justification=f"Demo resolution: {market.resolve_to} per the official source.",
                actor_user_id=admin_id,
            )
        resolved += 1
    return resolved
