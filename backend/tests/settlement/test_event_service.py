"""EventService.resolve_event / void_event — the event-level settlement orchestration (Phase 15).

Integration tests (testcontainers). Mirrors ``test_resolve_market.py``: the ``bets`` table is
created via a fixture and the **committed-session** pattern (own ``_get_session_maker()`` sessions)
is used because ``SettlementService`` — and therefore ``EventService`` — owns its own
``session.begin()`` and commits internally (Pitfall 5: the rolled-back ``async_session`` fixture
CANNOT host the act). The ``house_promo`` / ``house_revenue`` singletons come from migration 0003.

Because the testcontainer is session-scoped, committed writes persist across tests; the SHARED
house singletons therefore use before/after DELTAS, while per-test wallets and the per-market
liability use fresh UUIDs and assert absolute values.

``EventService`` uses the REAL ``HouseMarketResolveAdapter`` internally (it does NOT accept an
injected resolver), so every child MUST exist as a real ``markets`` row — ``_seed_house_event``
builds a ``market_groups`` row + N HOUSE child markets (each with a ``"YES"``/``"NO"`` outcome) +
placed bets (no house-event seed exists pre-Phase-18).

Covered (EVA-03 / EVA-04 / EVA-06 + EVT-06 projection):
  - resolve happy path: winner child paid, loser children swept, every liability drained, bets flip,
    spike-004 ``drift_count == 0``.
  - idempotent replay (the 23505 dangling-tx canary): a second ``resolve_event`` over the same group
    moves no money; ``drift_count == 0``.
  - void: every child settles on its NO leg (YES bettors lose, NO bettors win) — not a refund;
    ``drift_count == 0``.
  - partial failure: one child's settle raises -> settled siblings intact, failed child surfaced,
    event derives ``partially_resolved``; re-run finishes (no double-credit); ``drift_count == 0``.
  - mirrored (source=POLYMARKET) reject -> raises.
  - blank/whitespace justification -> raises.

NOT covered (deliberately — the deferred Pitfall-6 gap): resolve -> reverse -> RE-resolve. Reverse
lives in Plan 03 and is scoped to restore + audit only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

import app.wallet.reconcile as reconcile
from app.bets.constants import (
    BET_PENDING,
    BET_SETTLED_LOST,
    BET_SETTLED_WON,
    KIND_MARKET_LIABILITY,
)
from app.bets.market_port import MARKET_OPEN, MarketView, OutcomeView
from app.bets.models import Bet
from app.bets.service import BetService
from app.core.audit.models import AuditLog
from app.db.session import _get_session_maker
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup, Outcome
from app.settlement.event_service import EventService
from app.settlement.service import SettlementService
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
    KIND_USER_WALLET,
    OWNER_MARKET,
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
    """Depend on ``engine`` (container, migrate, env rewrite) — mirrors test_resolve_market.py."""
    return engine


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _bets_table(engine: AsyncEngine):
    """Create the ``bets`` table (DDL ships in migration 0005; created here for tests)."""
    async with engine.begin() as conn:
        await conn.run_sync(Bet.__table__.create, checkfirst=True)
    yield


# --------------------------------------------------------------------------- #
# Stub market source (for placement) — mirrors test_resolve_market.py.
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
# Committed-session helpers (assert against committed state).
# --------------------------------------------------------------------------- #
async def _seed_wallet(balance: Decimal) -> tuple[UUID, UUID]:
    """Create a LEDGER-BACKED user_wallet at ``balance`` (committed); return (user_id, wallet_id).

    The wallet is INSERTed at balance 0 (so ``SUM(entries) == balance == 0`` initially), then
    funded to ``balance`` via the real ``WalletService.recharge`` (a ``house_promo -> wallet``
    credit with a proper ledger entry). This keeps the wallet fully ledger-backed, so the
    spike-004 ``_reconcile_async`` gate stays clean (``house_promo``, the funding source, is the
    one deliberately non-ledger-backed singleton, excluded by design). A raw balance INSERT with
    NO opening entry — the older ``test_resolve_market.py`` shortcut — would register as drift the
    moment ``_reconcile_async`` runs, which this suite asserts after every path.
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


async def _liability_id(market_id: UUID) -> UUID | None:
    sm = _get_session_maker()
    async with sm() as s:
        return (
            await s.execute(
                select(Account.id).where(
                    Account.owner_type == OWNER_MARKET,
                    Account.owner_id == market_id,
                    Account.kind == KIND_MARKET_LIABILITY,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one_or_none()


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


async def _audit_for_group(event_type: str, group_id: UUID) -> list[AuditLog]:
    """Event-level audit rows of ``event_type`` whose payload ``group_id`` matches."""
    sm = _get_session_maker()
    async with sm() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.event_type == event_type,
                        AuditLog.payload["group_id"].astext == str(group_id),
                    )
                )
            )
            .scalars()
            .all()
        )


async def _assert_ledger_clean() -> None:
    """The literal spike-004 integrity gate — ``drift_count == 0`` (house_promo excluded).

    Reuses the production drift detector (``_reconcile_async``) on a fresh committed session.
    ``balance == SUM(credit) - SUM(debit)`` must hold for every ledger-backed account.
    """
    sm = _get_session_maker()
    async with sm() as s:
        summary = await reconcile._reconcile_async(s)
    assert summary["drift_count"] == 0


# --------------------------------------------------------------------------- #
# House-event synthesizer — a market_groups row + N HOUSE child markets, each with
# a YES/NO outcome (committed). No house-event seed exists pre-Phase-18, so build one.
# --------------------------------------------------------------------------- #
class _Child:
    """A seeded house-event child: its market id + YES/NO outcome ids + the placement view."""

    def __init__(self, view: MarketView, yes_id: UUID, no_id: UUID) -> None:
        self.view = view
        self.market_id = view.id
        self.yes_id = yes_id
        self.no_id = no_id


async def _seed_house_event(
    n_children: int,
    *,
    source: str = MarketSourceEnum.HOUSE.value,
    src: StubMarketSource | None = None,
) -> tuple[UUID, list[_Child], StubMarketSource]:
    """Build a ``market_groups`` row + ``n_children`` HOUSE child markets (committed).

    Each child is a real ``markets`` row (so the REAL ``HouseMarketResolveAdapter`` can
    persist its STL-06 resolution columns) with a ``"YES"`` and a ``"NO"`` ``Outcome``, stamped
    ``group_id``/``group_item_title``. A matching in-memory ``MarketView`` is registered on the
    returned ``StubMarketSource`` so ``BetService.place_bet`` validates + creates the per-market
    liability. Returns ``(group_id, [_Child, ...], src)``.
    """
    src = src or StubMarketSource()
    children: list[_Child] = []
    sm = _get_session_maker()
    async with sm() as s, s.begin():
        group = MarketGroup(
            id=uuid4(),
            title=f"House event {uuid4().hex[:8]}",
            slug=f"evt-{uuid4().hex[:8]}",
            source=source,
        )
        s.add(group)
        await s.flush()

        deadline = datetime.now(UTC) + timedelta(days=1)
        for i in range(n_children):
            market_id = uuid4()
            yes_id = uuid4()
            no_id = uuid4()
            mkt = Market(
                id=market_id,
                question=f"Will outcome {i} happen? {market_id.hex[:8]}",
                slug=f"evt-child-{market_id.hex[:8]}",
                resolution_criteria="test",
                source=source,
                status=MarketStatus.OPEN.value,
                deadline=deadline,
                group_id=group.id,
                group_item_title=f"Outcome {i}",
            )
            s.add(mkt)
            await s.flush()
            s.add(
                Outcome(
                    id=yes_id,
                    market_id=market_id,
                    label="YES",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                )
            )
            s.add(
                Outcome(
                    id=no_id,
                    market_id=market_id,
                    label="NO",
                    initial_odds=Decimal("0.5"),
                    current_odds=Decimal("0.5"),
                )
            )
            view = MarketView(
                id=market_id,
                status=MARKET_OPEN,
                deadline=deadline,
                outcomes=(
                    OutcomeView(id=yes_id, label="YES", price=Decimal("0.5")),
                    OutcomeView(id=no_id, label="NO", price=Decimal("0.5")),
                ),
            )
            src.add(view)
            children.append(_Child(view, yes_id, no_id))

    group_id = group.id
    return group_id, children, src


# --------------------------------------------------------------------------- #
# EVA-03 — resolve settles every child (winner -> YES, losers -> NO); integrity clean.
# --------------------------------------------------------------------------- #
async def test_resolve_event_settles_all_children() -> None:
    group_id, children, src = await _seed_house_event(3)
    winner = children[0]
    losers = children[1:]

    # On the winning child: a YES bettor wins. On each loser child: a YES bettor loses
    # (that child settles NO), a NO bettor wins.
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))  # YES on winner -> wins
    bob, bob_w = await _seed_wallet(Decimal("100.0000"))  # YES on loser[0] -> loses
    carol, carol_w = await _seed_wallet(Decimal("100.0000"))  # NO on loser[0] -> wins
    dave, dave_w = await _seed_wallet(Decimal("100.0000"))  # YES on loser[1] -> loses

    await _place(alice, winner.view, winner.yes_id, Decimal("40.0000"), src)
    await _place(bob, losers[0].view, losers[0].yes_id, Decimal("40.0000"), src)
    await _place(carol, losers[0].view, losers[0].no_id, Decimal("60.0000"), src)
    await _place(dave, losers[1].view, losers[1].yes_id, Decimal("30.0000"), src)

    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    result = await EventService.resolve_event(
        group_id=group_id,
        winning_outcome_id=winner.yes_id,
        justification="Outcome 0 won per the official source",
        actor_user_id=uuid4(),
    )

    assert result.child_count == 3
    assert result.children_settled == 3
    assert result.children_failed == ()
    assert result.status == "resolved"

    # Winner child: Alice (YES) paid 40 / 0.5 = 80 -> 100 - 40 + 80 = 140.
    assert await _balance(alice_w) == Decimal("140.0000")
    # loser[0] settled NO: Bob (YES) loses his 40 stake -> 60; Carol (NO) paid 60 / 0.5 = 120.
    assert await _balance(bob_w) == Decimal("60.0000")
    assert await _balance(carol_w) == Decimal("160.0000")
    # loser[1] settled NO: Dave (YES) loses his 30 stake -> 70.
    assert await _balance(dave_w) == Decimal("70.0000")

    # Every per-child liability drains to zero.
    for child in children:
        lid = await _liability_id(child.market_id)
        if lid is not None:  # children with bets have a liability; it must net to 0
            assert await _balance(lid) == Decimal("0.0000")

    # house deltas: revenue gains the two losing stakes (40 + 30 = 70); promo funds the two
    # winners' winnings (40 for Alice + 60 for Carol = 100).
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) - revenue_before == Decimal("70.0000")
    assert promo_before - await _balance(HOUSE_PROMO_ACCOUNT_ID) == Decimal("100.0000")

    # Bets flip; each child market is RESOLVED.
    assert (await _bets_for_user(alice))[0].status == BET_SETTLED_WON
    assert (await _bets_for_user(bob))[0].status == BET_SETTLED_LOST
    assert (await _bets_for_user(carol))[0].status == BET_SETTLED_WON
    for child in children:
        assert await _market_status(child.market_id) == MarketStatus.RESOLVED.value

    # The spike-004 ledger-integrity gate.
    await _assert_ledger_clean()


async def test_resolve_event_writes_event_audit() -> None:
    group_id, children, src = await _seed_house_event(2)
    winner = children[0]
    alice, _ = await _seed_wallet(Decimal("100.0000"))
    await _place(alice, winner.view, winner.yes_id, Decimal("20.0000"), src)
    admin_id = uuid4()

    await EventService.resolve_event(
        group_id=group_id,
        winning_outcome_id=winner.yes_id,
        justification="resolved for audit test",
        actor_user_id=admin_id,
    )

    rows = await _audit_for_group("event.resolved", group_id)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.actor == f"user:{admin_id}"
    payload = audit.payload
    assert payload["group_id"] == str(group_id)
    assert payload["winning_outcome_id"] == str(winner.yes_id)
    assert payload["child_count"] == 2
    assert payload["children_settled"] == 2
    assert payload["children_failed"] == []
    assert payload["justification"] == "resolved for audit test"


# --------------------------------------------------------------------------- #
# EVA-03 idempotency — the 23505 dangling-tx canary: re-resolve moves no money.
# --------------------------------------------------------------------------- #
async def test_resolve_event_is_idempotent() -> None:
    group_id, children, src = await _seed_house_event(3)
    winner = children[0]
    losers = children[1:]
    alice, alice_w = await _seed_wallet(Decimal("100.0000"))  # YES on winner -> wins
    bob, bob_w = await _seed_wallet(Decimal("100.0000"))  # YES on loser[0] -> loses
    await _place(alice, winner.view, winner.yes_id, Decimal("40.0000"), src)
    await _place(bob, losers[0].view, losers[0].yes_id, Decimal("50.0000"), src)

    await EventService.resolve_event(
        group_id=group_id,
        winning_outcome_id=winner.yes_id,
        justification="first resolve",
    )
    alice_after_first = await _balance(alice_w)
    bob_after_first = await _balance(bob_w)
    promo_after_first = await _balance(HOUSE_PROMO_ACCOUNT_ID)
    revenue_after_first = await _balance(HOUSE_REVENUE_ACCOUNT_ID)

    # Resolve AGAIN — every child's bets are already SETTLED, so the second pass is a true
    # no-op. This is the canary: a same-session 23505 dangling-tx regression raises here.
    result2 = await EventService.resolve_event(
        group_id=group_id,
        winning_outcome_id=winner.yes_id,
        justification="idempotent replay",
    )

    assert result2.children_failed == ()  # the replay raised on no child
    assert result2.status == "resolved"
    assert await _balance(alice_w) == alice_after_first  # no double-credit
    assert await _balance(bob_w) == bob_after_first
    assert await _balance(HOUSE_PROMO_ACCOUNT_ID) == promo_after_first
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) == revenue_after_first
    await _assert_ledger_clean()


# --------------------------------------------------------------------------- #
# EVA-04 — void settles EVERY child on NO (YES bettors lose, NO bettors win); not a refund.
# --------------------------------------------------------------------------- #
async def test_void_event_settles_every_child_on_no() -> None:
    group_id, children, src = await _seed_house_event(2)
    # Child 0: a YES bettor (will LOSE on void) + a NO bettor (will WIN on void).
    yes_loser, yes_loser_w = await _seed_wallet(Decimal("100.0000"))
    no_winner, no_winner_w = await _seed_wallet(Decimal("100.0000"))
    await _place(yes_loser, children[0].view, children[0].yes_id, Decimal("40.0000"), src)
    await _place(no_winner, children[0].view, children[0].no_id, Decimal("60.0000"), src)
    # Child 1: a single YES bettor (will LOSE on void).
    other_yes, other_yes_w = await _seed_wallet(Decimal("100.0000"))
    await _place(other_yes, children[1].view, children[1].yes_id, Decimal("25.0000"), src)

    revenue_before = await _balance(HOUSE_REVENUE_ACCOUNT_ID)
    promo_before = await _balance(HOUSE_PROMO_ACCOUNT_ID)

    result = await EventService.void_event(
        group_id=group_id,
        justification="event cancelled — voided on NO",
        actor_user_id=uuid4(),
    )

    assert result.child_count == 2
    assert result.children_settled == 2
    assert result.children_failed == ()
    assert result.status == "void"  # all children resolved, no YES winner

    # YES bettors LOSE their stake (NOT refunded); the NO bettor WINS.
    assert await _balance(yes_loser_w) == Decimal("60.0000")  # lost 40 stake
    assert await _balance(other_yes_w) == Decimal("75.0000")  # lost 25 stake
    # NO bettor paid 60 / 0.5 = 120 -> 100 - 60 + 120 = 160.
    assert await _balance(no_winner_w) == Decimal("160.0000")

    # house_revenue swept the two YES losers' stakes (40 + 25 = 65); promo funded the NO
    # winner's winnings (60).
    assert await _balance(HOUSE_REVENUE_ACCOUNT_ID) - revenue_before == Decimal("65.0000")
    assert promo_before - await _balance(HOUSE_PROMO_ACCOUNT_ID) == Decimal("60.0000")

    assert (await _bets_for_user(yes_loser))[0].status == BET_SETTLED_LOST
    assert (await _bets_for_user(no_winner))[0].status == BET_SETTLED_WON
    for child in children:
        assert await _market_status(child.market_id) == MarketStatus.RESOLVED.value

    rows = await _audit_for_group("event.voided", group_id)
    assert len(rows) == 1
    assert rows[0].payload["winning_outcome_id"] is None

    await _assert_ledger_clean()


# --------------------------------------------------------------------------- #
# EVA-03 partial failure — one child fails, siblings intact, event partially_resolved;
# re-run finishes (no double-credit). The failed child's tx rolls back cleanly (atomic),
# so the ledger stays consistent throughout.
# --------------------------------------------------------------------------- #
async def test_resolve_event_partial_failure_lands_partially_resolved(monkeypatch) -> None:
    group_id, children, src = await _seed_house_event(3)
    winner = children[0]
    losers = children[1:]
    failing_child = losers[0]  # this child's settle is forced to raise on the FIRST pass

    alice, alice_w = await _seed_wallet(Decimal("100.0000"))  # YES on winner -> wins
    bob, bob_w = await _seed_wallet(Decimal("100.0000"))  # YES on failing child
    carol, carol_w = await _seed_wallet(Decimal("100.0000"))  # YES on losers[1]
    await _place(alice, winner.view, winner.yes_id, Decimal("40.0000"), src)
    await _place(bob, failing_child.view, failing_child.yes_id, Decimal("50.0000"), src)
    await _place(carol, losers[1].view, losers[1].yes_id, Decimal("30.0000"), src)

    # Inject a transient failure for EXACTLY the failing child on the first pass. The real
    # SettlementService.resolve_market wraps its work in session.begin(), so raising here means
    # that child's tx never commits — its bets stay PENDING (atomic rollback). Other children
    # settle normally.
    real_resolve = SettlementService.resolve_market

    async def _flaky_resolve(session, *, market_id, **kwargs):
        if market_id == failing_child.market_id:
            raise RuntimeError("injected child settle failure")
        return await real_resolve(session, market_id=market_id, **kwargs)

    monkeypatch.setattr(SettlementService, "resolve_market", _flaky_resolve)

    result = await EventService.resolve_event(
        group_id=group_id,
        winning_outcome_id=winner.yes_id,
        justification="partial — one child fails first",
    )

    # The failed child is surfaced; the event derives partially_resolved.
    assert result.children_failed == (failing_child.market_id,)
    assert result.children_settled == 2
    assert result.status == "partially_resolved"
    # Siblings settled; the failed child's bet is still PENDING (its tx rolled back).
    assert await _balance(alice_w) == Decimal("140.0000")  # winner paid
    assert await _balance(carol_w) == Decimal("70.0000")  # losers[1] settled NO -> Carol lost 30
    assert (await _bets_for_user(bob))[0].status == BET_PENDING  # failed child untouched
    assert await _market_status(failing_child.market_id) == MarketStatus.OPEN.value
    await _assert_ledger_clean()

    # Re-run WITHOUT the injected failure — the previously-failed child now settles; the event
    # completes. The already-settled children are a true no-op (no double-credit).
    monkeypatch.setattr(SettlementService, "resolve_market", real_resolve)
    alice_before_rerun = await _balance(alice_w)
    carol_before_rerun = await _balance(carol_w)

    result2 = await EventService.resolve_event(
        group_id=group_id,
        winning_outcome_id=winner.yes_id,
        justification="re-run finishes the partial",
    )

    assert result2.children_failed == ()
    assert result2.status == "resolved"
    # The failing child finally settles: Bob bet YES on a child the event resolves NO -> loses.
    assert (await _bets_for_user(bob))[0].status == BET_SETTLED_LOST
    assert await _balance(bob_w) == Decimal("50.0000")  # lost the 50 stake
    assert await _market_status(failing_child.market_id) == MarketStatus.RESOLVED.value
    # Already-settled children unchanged (no double-credit on the re-run).
    assert await _balance(alice_w) == alice_before_rerun
    assert await _balance(carol_w) == carol_before_rerun
    await _assert_ledger_clean()


# --------------------------------------------------------------------------- #
# EVA-06 — a mirrored (source=POLYMARKET) group is admin read-only: resolve/void raise.
# --------------------------------------------------------------------------- #
async def test_resolve_event_rejects_mirrored_group() -> None:
    group_id, children, _src = await _seed_house_event(2, source=MarketSourceEnum.POLYMARKET.value)
    with pytest.raises(ValueError, match="(?i)mirrored"):
        await EventService.resolve_event(
            group_id=group_id,
            winning_outcome_id=children[0].yes_id,
            justification="should be rejected",
        )


async def test_void_event_rejects_mirrored_group() -> None:
    group_id, _children, _src = await _seed_house_event(2, source=MarketSourceEnum.POLYMARKET.value)
    with pytest.raises(ValueError, match="(?i)mirrored"):
        await EventService.void_event(group_id=group_id, justification="should be rejected")


# --------------------------------------------------------------------------- #
# V5 — a blank / whitespace justification raises (the non-repudiation guard).
# --------------------------------------------------------------------------- #
async def test_resolve_event_rejects_blank_justification() -> None:
    group_id, children, _src = await _seed_house_event(2)
    with pytest.raises(ValueError, match="(?i)justification"):
        await EventService.resolve_event(
            group_id=group_id,
            winning_outcome_id=children[0].yes_id,
            justification="   ",
        )


async def test_void_event_rejects_blank_justification() -> None:
    group_id, _children, _src = await _seed_house_event(2)
    with pytest.raises(ValueError, match="(?i)justification"):
        await EventService.void_event(group_id=group_id, justification="")


# --------------------------------------------------------------------------- #
# Defensive winning-outcome guard (Open Q2) — an outcome not in the group raises.
# --------------------------------------------------------------------------- #
async def test_resolve_event_rejects_foreign_winning_outcome() -> None:
    group_id, _children, _src = await _seed_house_event(2)
    with pytest.raises(ValueError, match="(?i)does not map"):
        await EventService.resolve_event(
            group_id=group_id,
            winning_outcome_id=uuid4(),  # belongs to no child of this group
            justification="winner not in group",
        )


# --------------------------------------------------------------------------- #
# Unknown group id raises (not silently a no-op).
# --------------------------------------------------------------------------- #
async def test_resolve_event_rejects_unknown_group() -> None:
    with pytest.raises(ValueError, match="(?i)no market group"):
        await EventService.resolve_event(
            group_id=uuid4(),
            winning_outcome_id=uuid4(),
            justification="no such group",
        )


# --------------------------------------------------------------------------- #
# Belt-and-braces — the YES/NO mapping is case-insensitive (no bet flips silently missed).
# A quick sanity check that resolving touches the expected per-child outcomes.
# --------------------------------------------------------------------------- #
async def test_resolve_event_loser_child_settled_on_no_outcome() -> None:
    group_id, children, src = await _seed_house_event(2)
    winner = children[0]
    loser = children[1]
    # A NO bettor on the LOSING child must WIN (the child resolves NO).
    no_better, no_better_w = await _seed_wallet(Decimal("100.0000"))
    await _place(no_better, loser.view, loser.no_id, Decimal("20.0000"), src)
    # A token YES bet on the winner so the winning child has a liability too.
    yes_better, _ = await _seed_wallet(Decimal("100.0000"))
    await _place(yes_better, winner.view, winner.yes_id, Decimal("10.0000"), src)

    await EventService.resolve_event(
        group_id=group_id,
        winning_outcome_id=winner.yes_id,
        justification="loser child must settle NO",
    )

    # The loser child resolved on its NO outcome, so the NO bettor won (paid 20 / 0.5 = 40).
    assert await _balance(no_better_w) == Decimal("120.0000")
    assert (await _bets_for_user(no_better))[0].status == BET_SETTLED_WON
    # Confirm the loser child's persisted winner is its NO outcome (case-insensitive mapping).
    sm = _get_session_maker()
    async with sm() as s:
        winner_id = (
            await s.execute(select(Market.winning_outcome_id).where(Market.id == loser.market_id))
        ).scalar_one()
        no_label = (
            await s.execute(select(func.upper(Outcome.label)).where(Outcome.id == winner_id))
        ).scalar_one()
    assert no_label == "NO"
    await _assert_ledger_clean()
