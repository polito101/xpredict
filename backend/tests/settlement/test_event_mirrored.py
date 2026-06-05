"""EVA-06 — mirrored (Polymarket) event verify: the UNCHANGED detect path settles
a mirrored ``market_group``'s children, and ``EventService`` refuses mirrored groups.

**This is a VERIFY-ONLY module.** It proves two things WITHOUT writing any new
settlement code and WITHOUT modifying ``app/integrations/polymarket/tasks.py`` (an
acceptance criterion of Plan 15-03 is that ``tasks.py`` has NO diff):

  1. A ``source=POLYMARKET`` :class:`~app.markets.models.MarketGroup` whose child
     :class:`~app.markets.models.Market` rows are stamped ``group_id`` auto-settle
     INDIVIDUALLY through the EXISTING ``detect_polymarket_resolutions`` UMA path —
     driven here via its ``_run_detect_resolutions(session_override=, redis_override=)``
     test seam (the same idiom as ``tests/polymarket/test_detect_resolution.py``).
     ``EventService`` is NEVER invoked on the mirrored path; the children settle
     one at a time inside the detect task exactly as production does on the 60s beat.
  2. ``EventService.reverse_event`` REJECTS a mirrored group (admin read-only,
     EVA-06) — complementing the Plan-02 resolve/void mirrored-reject tests so all
     three ``EventService`` mutations refuse ``source=POLYMARKET`` groups.

Mechanism notes (mirrors ``test_detect_resolution.py``):
  - The detect candidate query is ``source=POLYMARKET`` + ``status in (OPEN, CLOSED)``
    + ``deadline < now`` + ``source_market_id IS NOT NULL``; each child is seeded to
    match. ``GammaClient.fetch_market_by_id`` is patched to return a RESOLVED Gamma
    payload (``closed=true`` + ``umaResolutionStatus="resolved"`` + a clear winner).
  - The Redis detect-lock is an ``AsyncMock`` (the established detect-test idiom — the
    in-repo ``fakeredis`` build has no Lua ``eval`` for the owner-checked lock release);
    the lock plumbing is not what EVA-06 verifies, the settle path is.
  - The event children's grace gate (``uma_resolved_at``) is PRE-SET to > the grace
    window ago (same as the tick-2 setup in ``test_grace_period_triggers_resolution``).
    A standalone grace-PRIMER market (``uma_resolved_at IS NULL``, committed first) is
    also seeded: the detect loop grace-starts it (a conditional UPDATE + ``commit()``)
    BEFORE the settle-ready children, which closes the candidate-SELECT read tx so each
    child's ``resolve_market`` can open its own ``session.begin()`` on the shared
    ``session_override`` (a real session forbids ``begin()`` while a read tx is open).
    This reproduces a real mixed-stage 60s tick; ``tasks.py`` is unchanged.
  - Child outcome labels are TITLE-CASE ``"Yes"``/``"No"`` (real Gamma data, Pitfall 2)
    so ``_map_winning_outcome_id`` (exact Gamma-label match) maps the winner correctly.
  - Committed ``_get_session_maker()`` sessions (Pitfall 5) + the spike-004
    ``drift_count == 0`` integrity gate after the mirrored settle.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text

import app.wallet.reconcile as reconcile
from app.bets.constants import BET_SETTLED_LOST, BET_SETTLED_WON
from app.bets.market_port import MARKET_OPEN, MarketView, OutcomeView
from app.bets.models import Bet
from app.bets.service import BetService
from app.db.session import _get_session_maker
from app.integrations.polymarket.tasks import _run_detect_resolutions
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup, Outcome
from app.settlement.event_service import EventService
from app.wallet.constants import (
    KIND_USER_WALLET,
    OWNER_USER,
    PLAY_USD,
)
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
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors the settlement tests."""
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    """Create the ``bets`` table (DDL ships in migration 0005; created here for tests)."""
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


# --------------------------------------------------------------------------- #
# Stub market source (for bet placement) — mirrors test_event_service.py.
# --------------------------------------------------------------------------- #
class StubMarketSource:
    """In-memory ``MarketReadPort`` — bet placement validates the market through this."""

    def __init__(self) -> None:
        self._markets: dict[UUID, MarketView] = {}

    def add(self, market: MarketView) -> MarketView:
        self._markets[market.id] = market
        return market

    async def get_market(self, market_id: UUID) -> MarketView | None:
        return self._markets.get(market_id)


# --------------------------------------------------------------------------- #
# Committed-session helpers (assert against committed state; Pitfall 5).
# --------------------------------------------------------------------------- #
async def _seed_wallet(balance: Decimal) -> tuple[UUID, UUID]:
    """Create a LEDGER-BACKED user_wallet at ``balance`` (committed); return (user_id, wallet_id).

    INSERT at 0 (so ``SUM(entries) == balance == 0``) then fund to ``balance`` via the
    real ``WalletService.recharge`` so the wallet is fully ledger-backed and the
    spike-004 ``_reconcile_async`` gate stays clean (``house_promo`` is the one
    deliberately-excluded singleton). Same idiom as ``test_event_service.py``.
    """
    user_id = uuid4()
    wallet_id = uuid4()
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        await s.execute(
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
    if balance > 0:
        async with sm() as s:
            await WalletService.recharge(
                s,
                user_id=user_id,
                amount=balance,
                reason="test seed",
                idempotency_key=f"seed:{wallet_id}",
            )
    return user_id, wallet_id


async def _balance(account_id: UUID) -> Decimal:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(select(Account.balance).where(Account.id == account_id))
        ).scalar_one()


async def _bets_for_user(user_id: UUID) -> list[Bet]:
    sm = _get_session_maker()
    async with sm() as s:
        return list((await s.execute(select(Bet).where(Bet.user_id == user_id))).scalars().all())


async def _place(user_id: UUID, market: MarketView, outcome_id: UUID, stake: Decimal, src) -> None:
    sm = _get_session_maker()
    async with sm() as s:
        await BetService.place_bet(
            s,
            user_id=user_id,
            market_id=market.id,
            outcome_id=outcome_id,
            stake=stake,
            market_source=src,
        )


async def _market_status(market_id: UUID) -> str:
    sm = _get_session_maker()
    async with sm() as s:
        return (await s.execute(select(Market.status).where(Market.id == market_id))).scalar_one()


async def _assert_ledger_clean() -> None:
    """The literal spike-004 integrity gate — ``drift_count == 0`` (house_promo excluded)."""
    sm = _get_session_maker()
    async with sm() as s:
        summary = await reconcile._reconcile_async(s)
    assert summary["drift_count"] == 0


def _detect_redis() -> AsyncMock:
    """An ``AsyncMock`` Redis for the detect lock — the established detect-test idiom.

    ``_run_detect_resolutions`` acquires its lock with ``set(..., nx=True)`` and releases
    it with a Lua ``eval`` (owner-checked compare-and-delete). The in-memory ``fakeredis``
    build in this repo does NOT implement ``eval`` (raises ``unknown command 'eval'``), so
    the existing detect integration tests (``test_detect_resolution.py``) inject an
    ``AsyncMock`` whose ``set`` grants the lock and whose ``eval`` is a no-op. We do the
    same — the lock plumbing is not what EVA-06 verifies (the settle path is).
    """
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)  # grant the detect lock
    redis.eval = AsyncMock(return_value=1)  # owner-checked release — no-op
    redis.aclose = AsyncMock()
    return redis


# --------------------------------------------------------------------------- #
# Mirrored-event synthesizer — a source=POLYMARKET market_groups row + N child
# Market rows, each a mirror of real Gamma data: title-case "Yes"/"No" outcomes,
# a past deadline, a source_market_id, and uma_resolved_at PRE-SET past the grace
# window so the single detect call settles. Stamped group_id (the event seam).
# --------------------------------------------------------------------------- #
class _MirroredChild:
    """A seeded mirrored event child: market id + Yes/No outcome ids + the placement view."""

    def __init__(self, view: MarketView, source_market_id: str, yes_id: UUID, no_id: UUID) -> None:
        self.view = view
        self.market_id = view.id
        self.source_market_id = source_market_id
        self.yes_id = yes_id
        self.no_id = no_id


async def _seed_mirrored_event(
    n_children: int,
    *,
    settle_ready: bool = True,
) -> tuple[UUID, list[_MirroredChild], StubMarketSource]:
    """Build a ``source=POLYMARKET`` ``market_groups`` row + ``n_children`` mirrored children.

    Each child is a real POLYMARKET ``markets`` row (``status=CLOSED``, a past
    ``deadline``, a unique ``source_market_id``) with TITLE-CASE ``"Yes"``/``"No"``
    ``Outcome`` rows (real Gamma labels — Pitfall 2), stamped ``group_id`` /
    ``group_item_title``. When ``settle_ready`` the child's ``uma_resolved_at`` is
    PRE-SET to 60 minutes ago (> the 30-min grace default) so a single
    ``_run_detect_resolutions`` call settles it without the first-tick grace-start.
    A matching in-memory ``MarketView`` is registered on the returned
    ``StubMarketSource`` so ``BetService.place_bet`` validates + creates the
    per-market liability. Returns ``(group_id, [_MirroredChild, ...], src)``.
    """
    src = StubMarketSource()
    children: list[_MirroredChild] = []
    past_grace = datetime.now(UTC) - timedelta(minutes=60)
    # The DB markets row carries a PAST deadline so the detect candidate query
    # (``Market.deadline < now``) selects it. The in-memory placement view carries a
    # FUTURE deadline so ``BetService.place_bet`` (``market.is_open(now)``) accepts the
    # bet — the two are independent (the view validates placement; the detect path reads
    # the DB row). Bets are placed BEFORE the detect call settles the children.
    db_deadline = datetime(2020, 1, 1, tzinfo=UTC)  # safely < now (detect candidate gate)
    view_deadline = datetime.now(UTC) + timedelta(days=1)  # open for placement
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        group = MarketGroup(
            id=uuid4(),
            title=f"Mirrored event {uuid4().hex[:8]}",
            slug=f"mirror-evt-{uuid4().hex[:8]}",
            source=MarketSourceEnum.POLYMARKET.value,
            source_event_id=f"gamma-evt-{uuid4().hex[:8]}",
        )
        s.add(group)
        await s.flush()

        for i in range(n_children):
            market_id = uuid4()
            yes_id = uuid4()
            no_id = uuid4()
            source_market_id = f"gamma-mirror-{market_id.hex[:10]}"
            mkt = Market(
                id=market_id,
                question=f"Mirrored child {i}? {market_id.hex[:8]}",
                slug=f"mirror-child-{market_id.hex[:8]}",
                resolution_criteria="test",
                source=MarketSourceEnum.POLYMARKET.value,
                source_market_id=source_market_id,
                status=MarketStatus.CLOSED.value,
                deadline=db_deadline,
                uma_resolved_at=past_grace if settle_ready else None,
                group_id=group.id,
                group_item_title=f"Outcome {i}",
            )
            s.add(mkt)
            await s.flush()
            # Title-case Gamma labels (Pitfall 2) — _map_winning_outcome_id matches exactly.
            s.add(
                Outcome(
                    id=yes_id,
                    market_id=market_id,
                    label="Yes",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                )
            )
            s.add(
                Outcome(
                    id=no_id,
                    market_id=market_id,
                    label="No",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                )
            )
            view = MarketView(
                id=market_id,
                status=MARKET_OPEN,
                deadline=view_deadline,
                outcomes=(
                    OutcomeView(id=yes_id, label="Yes", price=Decimal("0.5")),
                    OutcomeView(id=no_id, label="No", price=Decimal("0.5")),
                ),
            )
            src.add(view)
            children.append(_MirroredChild(view, source_market_id, yes_id, no_id))

    group_id = group.id
    return group_id, children, src


async def _seed_grace_primer() -> str:
    """Seed a standalone POLYMARKET market whose grace clock is NOT yet started.

    Committed FIRST (its own tx, lowest physical row order), with ``uma_resolved_at
    IS NULL`` so the detect loop hits its GRACE-START branch — a conditional UPDATE +
    ``session.commit()`` — BEFORE any settle-ready candidate. That commit closes the
    candidate-SELECT's autobegun read transaction so the subsequent per-child
    ``SettlementService.resolve_market`` can open its own ``session.begin()`` cleanly
    (a real session forbids ``begin()`` while a read tx is still open — the same
    23505/dangling-tx family the whole phase guards against). This faithfully mirrors
    production, where markets sit at mixed grace stages on any given 60s tick: a
    grace-starting market commits and clears the session for the settling ones. The
    primer itself only grace-starts on this single call (it ends CLOSED, unsettled) —
    it is NOT part of the event group and is never asserted on. Returns its
    ``source_market_id`` so the Gamma stub can answer for it.

    Without this primer, a detect call whose ONLY candidates are already past-grace
    never commits the read tx, and the first ``resolve_market`` raises
    ``InvalidRequestError: A transaction is already begun`` (verified). ``tasks.py`` is
    unchanged — this is purely test seeding that reproduces the real mixed-stage tick.
    """
    market_id = uuid4()
    source_market_id = f"gamma-primer-{market_id.hex[:10]}"
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        mkt = Market(
            id=market_id,
            question=f"Grace primer {market_id.hex[:8]}",
            slug=f"mirror-primer-{market_id.hex[:8]}",
            resolution_criteria="test",
            source=MarketSourceEnum.POLYMARKET.value,
            source_market_id=source_market_id,
            status=MarketStatus.CLOSED.value,
            deadline=datetime(2020, 1, 1, tzinfo=UTC),
            uma_resolved_at=None,  # forces the grace-start commit on this call
        )
        s.add(mkt)
        await s.flush()
        s.add_all(
            [
                Outcome(
                    id=uuid4(),
                    market_id=market_id,
                    label="Yes",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                ),
                Outcome(
                    id=uuid4(),
                    market_id=market_id,
                    label="No",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                ),
            ]
        )
    return source_market_id


def _resolved_gamma_payload(source_market_id: str) -> dict[str, object]:
    """A RESOLVED Gamma market payload with a clear winner = the title-case ``"Yes"`` outcome.

    ``closed=true`` + ``umaResolutionStatus="resolved"`` + ``outcomePrices=["1","0"]``
    over ``outcomes=["Yes","No"]`` -> ``GammaMarket.internal_status == RESOLVED`` and
    ``_map_winning_outcome_id`` picks index 0 (price "1") = label ``"Yes"``.
    """
    return {
        "id": source_market_id,
        "question": "Mirrored child resolved?",
        "closed": True,
        "umaResolutionStatus": "resolved",
        "outcomePrices": '["1","0"]',
        "outcomes": '["Yes","No"]',
        "endDate": "2020-01-01T00:00:00Z",
    }


# --------------------------------------------------------------------------- #
# EVA-06 CORE VERIFY — a mirrored event's children auto-settle via the UNCHANGED
# detect_polymarket_resolutions path, with ZERO new settlement code and WITHOUT
# invoking EventService. (tasks.py is verified, not modified — no diff.)
# --------------------------------------------------------------------------- #
async def test_mirrored_event_children_auto_settle_via_detect() -> None:
    # A grace primer (committed first, lowest physical row) grace-starts + commits in the
    # detect loop, clearing the candidate-SELECT read tx so the event children can settle
    # on the same call (mirrors a real mixed-stage 60s tick). Not part of the event group.
    primer_smid = await _seed_grace_primer()

    # A 2-child mirrored event (group children, plural) proves the event-child path.
    group_id, children, src = await _seed_mirrored_event(2)
    child_a, child_b = children

    # Bet on each child: a "Yes" bettor (will WIN — the payload resolves Yes) and a
    # "No" bettor (will LOSE) on child_a; a single "Yes" bettor on child_b.
    yes_a, yes_a_w = await _seed_wallet(Decimal("100.0000"))
    no_a, no_a_w = await _seed_wallet(Decimal("100.0000"))
    yes_b, yes_b_w = await _seed_wallet(Decimal("100.0000"))
    await _place(yes_a, child_a.view, child_a.yes_id, Decimal("40.0000"), src)
    await _place(no_a, child_a.view, child_a.no_id, Decimal("20.0000"), src)
    await _place(yes_b, child_b.view, child_b.yes_id, Decimal("30.0000"), src)

    # Drive the UNCHANGED detect task over the mirrored children via its test seam.
    # GammaClient.fetch_market_by_id returns a resolved payload for each source_market_id
    # (the primer + both children); the children's grace clock is already past
    # (uma_resolved_at pre-set), so this single call settles them after the primer's
    # grace-start commit. EventService is NEVER called on this path.
    payloads = {c.source_market_id: _resolved_gamma_payload(c.source_market_id) for c in children}
    payloads[primer_smid] = _resolved_gamma_payload(primer_smid)

    async def _fake_fetch(self, source_market_id):  # patched GammaClient.fetch_market_by_id
        return payloads.get(source_market_id)

    sm = _get_session_maker()
    async with sm() as detect_session:
        with (
            patch(
                "app.integrations.polymarket.tasks.GammaClient.fetch_market_by_id",
                new=_fake_fetch,
            ),
            patch("app.integrations.polymarket.tasks.GammaClient.close", new=AsyncMock()),
        ):
            # session_override / redis_override = the documented test seam (unchanged task).
            await _run_detect_resolutions(
                redis_override=_detect_redis(),
                session_override=detect_session,
            )

    # Both mirrored children settled through the UMA path — markets RESOLVED, bets flipped —
    # with NO EventService involvement and no new settlement code.
    assert await _market_status(child_a.market_id) == MarketStatus.RESOLVED.value
    assert await _market_status(child_b.market_id) == MarketStatus.RESOLVED.value

    # child_a resolved Yes: the Yes bettor won (40 / 0.5 = 80 -> 60 + 80 = 140), No bettor lost.
    assert (await _bets_for_user(yes_a))[0].status == BET_SETTLED_WON
    assert (await _bets_for_user(no_a))[0].status == BET_SETTLED_LOST
    assert await _balance(yes_a_w) == Decimal("140.0000")
    assert await _balance(no_a_w) == Decimal("80.0000")  # lost the 20 stake
    # child_b resolved Yes: its Yes bettor won (30 / 0.5 = 60 -> 70 + 60 = 130).
    assert (await _bets_for_user(yes_b))[0].status == BET_SETTLED_WON
    assert await _balance(yes_b_w) == Decimal("130.0000")

    # The resolution_source is the auto/UMA token (actor_user_id=None on the detect path).
    sm = _get_session_maker()
    async with sm() as s:
        rsource = (
            await s.execute(select(Market.resolution_source).where(Market.id == child_a.market_id))
        ).scalar_one()
    assert rsource == "POLYMARKET_UMA"

    # spike-004 ledger integrity holds after the mirrored auto-settle.
    await _assert_ledger_clean()


# --------------------------------------------------------------------------- #
# EVA-06 — EventService.reverse_event REJECTS a mirrored (source=POLYMARKET) group.
# Together with the Plan-02 resolve/void mirrored-reject tests, all three EventService
# mutations refuse mirrored groups (admin read-only; mirrored settles ONLY via UMA).
# --------------------------------------------------------------------------- #
async def test_event_service_rejects_mirrored_reverse() -> None:
    group_id, _children, _src = await _seed_mirrored_event(2, settle_ready=False)
    with pytest.raises(ValueError, match="(?i)mirrored"):
        await EventService.reverse_event(group_id=group_id, justification="should be rejected")
