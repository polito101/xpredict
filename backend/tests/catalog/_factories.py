"""Seed factories for the Phase-16 catalog + admin-event endpoint tests (Wave 0).

This is the row-shape synthesizer every Wave-1+ Phase-16 plan imports instead of
redefining its own seed logic. It builds the catalog shapes those plans assert
against:

- standalone binary markets (``make_market``),
- ``>=2``-child events (a ``market_groups`` row + N binary YES/NO children,
  ``make_event``) drivable to each of the four ``derive_event_status`` states
  (open / partially_resolved / resolved / void) via ``resolve_child`` / the
  per-state convenience helpers,
- ledger-backed bets on a child (``place_bet_on_child``) so ``EXISTS(bets)`` flips
  and the EVA-02 edit-lock returns 423.

Two transaction-boundary realities shape the helper signatures (both inherited
from the authoritative analog ``tests/settlement/test_event_service.py``):

1. **Pure ORM writes ride the caller's session.** ``make_market`` / ``make_event``
   / ``resolve_child`` only ``add`` + ``flush`` (never ``commit``), so they work on
   the rolled-back ``async_session`` fixture AND on a committed
   ``_get_session_maker()`` session — the caller owns the transaction.
2. **The ledger writer needs its OWN committed session (Pitfall 5).**
   ``WalletService.recharge`` opens its own ``async with session.begin()`` and
   commits internally; running it on the rolled-back ``async_session`` fixture
   (which already holds an open outer transaction) raises "a transaction is
   already begun". So ``place_bet_on_child`` funds the wallet on a FRESH
   ``_get_session_maker()`` session (committed, ledger-backed — keeping the
   spike-004 ``drift_count == 0`` invariant valid), then writes the ``Bet`` row on
   the caller's session. The ``session`` it receives is therefore used only for the
   bet INSERT; the recharge is deliberately out-of-band.

Every money/odds value is a ``Decimal`` (never a float) so the spike-004 ledger
reconciliation and the ``ck_outcomes_*_odds_range`` checks stay exact. Each child
is exactly a YES + NO pair — no factory path ever adds a 3rd outcome, so the
``trg_binary_outcomes_only`` (MKT-08) trigger never trips.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from sqlalchemy import func, select, text

from app.bets.constants import BET_PENDING
from app.bets.models import Bet
from app.main import app
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup, Outcome, generate_slug
from app.wallet.service import WalletService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Half-half is the canonical binary opening for a freshly-seeded market (mirrors
# markets/service.py + the sample_market fixture). Always a Decimal.
_HALF = Decimal("0.500000")
# Default child-event label sequence (binary YES/NO children of a multi-outcome
# event are titled, e.g., "Player A" / "Player B" / "Player C").
_DEFAULT_LABELS = ("Option A", "Option B", "Option C", "Option D", "Option E")


def _default_deadline() -> datetime:
    """A timezone-aware deadline 1 day out (markets/groups require a NOT-NULL deadline)."""
    return datetime.now(UTC) + timedelta(days=1)


def _add_binary_outcomes(
    session: AsyncSession,
    market_id: UUID,
    *,
    odds_yes: Decimal = _HALF,
) -> tuple[Outcome, Outcome]:
    """Add the YES + NO outcome pair for ``market_id`` (mirror markets/service.py:71-85).

    Returns ``(yes_outcome, no_outcome)`` (not yet flushed — the caller flushes).
    Exactly two outcomes: the binary-only trigger forbids a 3rd.
    """
    odds_no = Decimal("1") - odds_yes
    yes_outcome = Outcome(
        market_id=market_id,
        label="YES",
        initial_odds=odds_yes,
        current_odds=odds_yes,
    )
    no_outcome = Outcome(
        market_id=market_id,
        label="NO",
        initial_odds=odds_no,
        current_odds=odds_no,
    )
    session.add_all([yes_outcome, no_outcome])
    return yes_outcome, no_outcome


async def make_market(
    session: AsyncSession,
    *,
    question: str,
    category: str | None = None,
    status: str = MarketStatus.OPEN.value,
    source: str = MarketSourceEnum.HOUSE.value,
    deadline: datetime | None = None,
    volume: Decimal = Decimal("0"),
) -> Market:
    """Insert a STANDALONE binary market (``group_id=None``) + its YES/NO outcomes.

    Mirrors the ``MarketService.create_market`` body (markets/service.py:46-85): a
    ``markets`` row plus exactly one YES + one NO ``Outcome`` (never a 3rd —
    ``trg_binary_outcomes_only``). Writes ride the caller's session (``flush`` only,
    no ``commit``). ``status`` accepts a ``MarketStatus`` value (defaults OPEN);
    ``volume`` is a ``Decimal`` money value. Returns the flushed ``Market``.
    """
    market = Market(
        question=question,
        slug=generate_slug(question),
        resolution_criteria="Seed market resolution criteria",
        category=category,
        source=source,
        status=status,
        deadline=deadline or _default_deadline(),
        group_id=None,
        volume=volume,
    )
    session.add(market)
    await session.flush()

    _add_binary_outcomes(session, market.id)
    await session.flush()
    return market


async def make_event(
    session: AsyncSession,
    *,
    title: str,
    category: str | None = None,
    n_outcomes: int = 3,
    labels: list[str] | None = None,
    deadline: datetime | None = None,
    source: str = MarketSourceEnum.HOUSE.value,
) -> tuple[MarketGroup, list[Market]]:
    """Insert one ``market_groups`` row + ``n_outcomes`` binary YES/NO child markets.

    The group carries ``slug=generate_slug(title)`` and ``source`` (HOUSE by
    default — EVT-06 stores NO status/winner column). Each child is a real
    ``markets`` row stamped ``group_id`` + ``group_item_title`` with a YES + NO
    ``Outcome`` pair (exactly two — the binary trigger never trips). Writes ride the
    caller's session (``flush`` only). Returns ``(group, children)``.

    ``labels`` (one per child, used as ``group_item_title``) defaults to a short
    "Option A/B/C..." sequence; ``n_outcomes`` must be ``>= 2`` for a real event.
    """
    if n_outcomes < 2:
        raise ValueError("an event needs at least 2 child markets")
    chosen_labels = labels if labels is not None else list(_DEFAULT_LABELS)
    event_deadline = deadline or _default_deadline()

    group = MarketGroup(
        title=title,
        slug=generate_slug(title),
        source=source,
        category=category,
    )
    session.add(group)
    await session.flush()

    children: list[Market] = []
    for i in range(n_outcomes):
        item_title = chosen_labels[i] if i < len(chosen_labels) else f"Option {i + 1}"
        child = Market(
            question=f"{title} — {item_title}?",
            slug=generate_slug(f"{title} {item_title}"),
            resolution_criteria="Seed event child resolution criteria",
            category=category,
            source=source,
            status=MarketStatus.OPEN.value,
            deadline=event_deadline,
            group_id=group.id,
            group_item_title=item_title,
        )
        session.add(child)
        await session.flush()
        _add_binary_outcomes(session, child.id)
        await session.flush()
        children.append(child)

    return group, children


async def make_single_child_group(
    session: AsyncSession,
    *,
    title: str,
    category: str | None = None,
    deadline: datetime | None = None,
    source: str = MarketSourceEnum.HOUSE.value,
) -> tuple[MarketGroup, Market]:
    """Insert a ``market_groups`` row with EXACTLY ONE binary child (the EVT-07 edge).

    A single-outcome group must stay on the standalone ``/markets`` path: the catalog
    excludes it as an event item and ``/events/{slug}`` 404s it. ``make_event``
    forbids ``n_outcomes < 2``, so this dedicated helper builds the 1-child shape for
    the exclusion / 404 tests. Writes ride the caller's session (``flush`` only);
    exactly YES + NO on the child (binary trigger safe). Returns ``(group, child)``.
    """
    group = MarketGroup(
        title=title,
        slug=generate_slug(title),
        source=source,
        category=category,
    )
    session.add(group)
    await session.flush()

    child = Market(
        question=f"{title} — sole outcome?",
        slug=generate_slug(f"{title} sole"),
        resolution_criteria="Seed single-child resolution criteria",
        category=category,
        source=source,
        status=MarketStatus.OPEN.value,
        deadline=deadline or _default_deadline(),
        group_id=group.id,
        group_item_title="Only",
    )
    session.add(child)
    await session.flush()
    _add_binary_outcomes(session, child.id)
    await session.flush()
    return group, child


async def _yes_outcome_id(session: AsyncSession, market_id: UUID) -> UUID:
    """The child's YES outcome id, matched case-insensitively (IN-01 / event_service.py:146)."""
    return (
        await session.execute(
            select(Outcome.id).where(
                Outcome.market_id == market_id,
                func.upper(Outcome.label) == "YES",
            )
        )
    ).scalar_one()


async def _no_outcome_id(session: AsyncSession, market_id: UUID) -> UUID:
    """The child's NO outcome id (the other binary leg — ``!= "YES"``)."""
    return (
        await session.execute(
            select(Outcome.id).where(
                Outcome.market_id == market_id,
                func.upper(Outcome.label) != "YES",
            )
        )
    ).scalar_one()


async def place_bet_on_child(
    session: AsyncSession,
    child: Market,
    user_id: UUID,
    *,
    outcome: str = "YES",
    stake: Decimal = Decimal("10"),
) -> Bet:
    """Seed a ledger-backed wallet, then a ``Bet`` row on ``child`` so ``EXISTS(bets)`` flips.

    Two-session, per the Pitfall-5 boundary documented at module top:

    1. **Ledger (own committed session).** Insert ``user_id``'s ``user_wallet`` at
       balance 0 (so ``SUM(entries) == balance == 0`` initially) on a FRESH
       ``_get_session_maker()`` session, then fund it to ``stake`` via the REAL
       ``WalletService.recharge`` (a ``house_promo -> wallet`` credit with a proper
       ledger entry). This keeps the wallet fully ledger-backed so the spike-004
       ``drift_count == 0`` gate stays clean (a raw balance write would register as
       drift). ``recharge`` owns its own ``session.begin()`` + commit, so it CANNOT
       run on the caller's (possibly rolled-back) session — hence the fresh session.
    2. **Bet (caller's session).** Insert the ``Bet`` row on the caller's
       ``session`` (``flush`` only) so the edit-lock ``EXISTS(bets)`` predicate the
       EVA-02 423 path checks now returns true.

    The bet is written directly (not via ``BetService.place_bet``) because the
    edit-lock only needs a row to EXIST — no market-source view / liability movement
    is required for the catalog/edit-lock tests. ``outcome`` selects the YES (default)
    or NO leg; ``stake`` is a positive ``Decimal``. Returns the flushed ``Bet``.
    """
    from app.db.session import _get_session_maker
    from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD

    if stake <= 0:
        raise ValueError("stake must be > 0")

    wallet_id = uuid4()
    session_maker = _get_session_maker()
    # 1a. Open the wallet at balance 0 on its own committed session.
    async with session_maker() as ledger_session, ledger_session.begin():
        await ledger_session.execute(
            text(
                "INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) "
                "VALUES (:id, :ot, :oid, :kind, :cur, :bal)"
            ),
            {
                "id": wallet_id,
                "ot": OWNER_USER,
                "oid": user_id,
                "kind": KIND_USER_WALLET,
                "cur": PLAY_USD,
                "bal": Decimal("0"),
            },
        )
    # 1b. Fund it to ``stake`` via the real ledger writer (own begin()+commit).
    async with session_maker() as fund_session:
        await WalletService.recharge(
            fund_session,
            user_id=user_id,
            amount=stake,
            reason="catalog test seed",
            idempotency_key=f"catalog-seed:{wallet_id}",
        )

    # 2. The chosen leg + a Bet row on the caller's session (EXISTS(bets) flips).
    if outcome.upper() == "YES":
        outcome_id = await _yes_outcome_id(session, child.id)
    else:
        outcome_id = await _no_outcome_id(session, child.id)

    bet = Bet(
        user_id=user_id,
        market_id=child.id,
        outcome_id=outcome_id,
        stake=stake,
        odds_at_placement=_HALF,
        status=BET_PENDING,
    )
    session.add(bet)
    await session.flush()
    return bet


async def resolve_child(
    session: AsyncSession,
    child: Market,
    *,
    winner_label: str,
) -> Market:
    """Drive ONE child to RESOLVED with ``winner_label`` (YES/NO) as its winner.

    Non-financial state setup (the plan's allowed "direct status set +
    ``winning_outcome_id``" path): sets ``Market.status = RESOLVED`` and
    ``winning_outcome_id`` to the matching outcome's id, consistent with
    ``event_service._derive_status`` (which computes ``is_yes_winner`` as
    ``winning_outcome_id == <the YES outcome id>``, case-insensitive). This does NOT
    move money — it shapes the row state ``derive_event_status`` reads. Writes ride
    the caller's session (``flush`` only). Returns the (refreshed) child.
    """
    if winner_label.upper() == "YES":
        winner_id = await _yes_outcome_id(session, child.id)
    else:
        winner_id = await _no_outcome_id(session, child.id)

    child.status = MarketStatus.RESOLVED.value
    child.winning_outcome_id = winner_id
    child.resolved_at = datetime.now(UTC)
    session.add(child)
    await session.flush()
    await session.refresh(child)
    return child


async def resolve_child_yes(session: AsyncSession, child: Market) -> Market:
    """RESOLVE ``child`` with its YES outcome as winner (event-of-binaries winner leg)."""
    return await resolve_child(session, child, winner_label="YES")


async def resolve_child_no(session: AsyncSession, child: Market) -> Market:
    """RESOLVE ``child`` with its NO outcome as winner (loser/void leg)."""
    return await resolve_child(session, child, winner_label="NO")


# --------------------------------------------------------------------------- #
# Per-state event convenience helpers. Each takes the ``children`` list from
# ``make_event`` and drives the GROUP to one of the four ``derive_event_status``
# states. They mutate child ``Market.status`` + ``winning_outcome_id`` only (no
# money) — the pure projection ``derive_event_status`` is the source of truth.
# --------------------------------------------------------------------------- #
async def drive_event_open(session: AsyncSession, children: list[Market]) -> None:
    """OPEN: no child resolved (``derive_event_status`` -> "open"). A no-op by design.

    ``make_event`` already leaves every child OPEN, so this exists for symmetry /
    self-documentation at the call site (and to assert the precondition).
    """
    for child in children:
        if child.status == MarketStatus.RESOLVED.value:
            raise ValueError("drive_event_open expects all children still unresolved")


async def drive_event_partial(session: AsyncSession, children: list[Market]) -> None:
    """PARTIALLY_RESOLVED: resolve the FIRST child (YES), leave the rest open.

    ``>=1`` resolved + ``>=1`` open -> ``derive_event_status`` returns
    "partially_resolved". Requires ``>=2`` children (so one stays open).
    """
    if len(children) < 2:
        raise ValueError("partially_resolved needs >= 2 children (one resolved, one open)")
    await resolve_child(session, children[0], winner_label="YES")


async def drive_event_resolved(session: AsyncSession, children: list[Market]) -> None:
    """RESOLVED: resolve EVERY child — the first on YES (the winner), the rest on NO.

    All children resolved with exactly one YES winner -> ``derive_event_status``
    returns "resolved" (event-of-binaries: exactly one child can win on YES).
    """
    if not children:
        raise ValueError("resolved needs >= 1 child")
    await resolve_child(session, children[0], winner_label="YES")
    for child in children[1:]:
        await resolve_child(session, child, winner_label="NO")


async def drive_event_void(session: AsyncSession, children: list[Market]) -> None:
    """VOID: resolve EVERY child on NO (no YES winner) -> ``derive_event_status`` "void".

    All children resolved with no YES winner ⟺ void (mutually-exclusive event
    outcomes, all settled against).
    """
    if not children:
        raise ValueError("void needs >= 1 child")
    for child in children:
        await resolve_child(session, child, winner_label="NO")


# --------------------------------------------------------------------------- #
# Admin auth helpers — override the real ``current_active_admin`` Bearer gate, OR
# seed a real superuser row for the cases that want a genuine Bearer token.
# --------------------------------------------------------------------------- #
class _Admin:
    """A minimal stand-in for the admin principal (mirror test_settlement_router.py:99).

    ``current_active_admin`` consumers read only ``.id`` (e.g. for the audit actor
    ``f"user:{admin.id}"``), so an object exposing just ``id`` is a faithful override.
    """

    def __init__(self, user_id: UUID) -> None:
        self.id = user_id


def admin_override(user_id: UUID) -> None:
    """Override ``current_active_admin`` with ``_Admin(user_id)`` (the autouse fixture clears it).

    Mirrors ``test_settlement_router.py:_admin`` (line 158). The catalog conftest's
    autouse ``_clear_overrides`` wipes ``app.dependency_overrides`` after each test,
    so the real 401/403 admin gate is restored for the negative auth tests
    (threat T-16-00b — no leaked override).
    """
    from app.auth.deps import current_active_admin

    app.dependency_overrides[current_active_admin] = lambda: _Admin(user_id)


async def seed_admin(
    session: AsyncSession,
    *,
    email: str = "catalog-admin@test.com",
    password: str = "Admin-Test-Pass-1!",
) -> UUID:
    """Insert a REAL superuser row (committed) for tests wanting a genuine Bearer.

    Mirrors ``tests/markets/test_public_router.py:_seed_admin`` (lines 27-40): hash
    the password with ``pwdlib.PasswordHash.recommended()`` and INSERT a verified,
    active superuser on a FRESH committed ``_get_session_maker()`` session (a real
    login needs the row visible across the request's own session, so it must be
    committed — the rolled-back ``async_session`` fixture would hide it). Idempotent
    on ``email`` (deletes any prior row first). Returns the new user's id.
    """
    from app.db.session import _get_session_maker

    hashed = PasswordHash.recommended().hash(password)
    session_maker = _get_session_maker()
    async with session_maker() as admin_session, admin_session.begin():
        await admin_session.execute(
            text("DELETE FROM users WHERE email = :em"),
            {"em": email},
        )
        row = (
            await admin_session.execute(
                text(
                    "INSERT INTO users "
                    "(email, hashed_password, is_active, is_superuser, "
                    " is_verified, display_name, token_version) "
                    "VALUES (:em, :pw, TRUE, TRUE, TRUE, 'Catalog Admin', 0) "
                    "RETURNING id"
                ),
                {"em": email, "pw": hashed},
            )
        ).one()
    return UUID(str(row[0]))
