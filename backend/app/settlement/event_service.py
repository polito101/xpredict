"""Event-level settlement (Phase 15) — derived status + the resolve/void orchestration.

This module hosts the event-of-binaries settlement layer that loops the proven
per-market :class:`~app.settlement.service.SettlementService` over a
:class:`~app.markets.models.MarketGroup`'s child markets.

**Wave 1** ships the pure read-projection (``derive_event_status`` /
``ChildStatus``); **Wave 2** extends the SAME module with :class:`EventService` —
``resolve_event`` / ``void_event`` classmethods; **Wave 3 (this plan)** adds
``reverse_event`` (EVA-05). All three COMPOSE the UNCHANGED ``SettlementService``
(``resolve_market`` for resolve/void, ``reverse_settlement`` for reverse) over a
group's children, one child per FRESH ``AsyncSession`` (Option A — per-child ACID
transaction). This phase reinvents NO settlement: the payouts, loser sweep, bet
flips, market-status flip, the append-only compensating (inverse) reverse
transfers, per-bet idempotency keys, FOR-UPDATE lock ordering, and per-child
``settlement.resolved`` / ``settlement.reversed`` audit rows all live inside
``SettlementService`` and stay byte-for-byte unchanged. The event service only
orchestrates the loop, maps the winning outcome to each child's YES/NO leg
(resolve/void only — reverse needs no mapping), rejects mirrored (Polymarket)
groups, enforces a non-blank justification, and writes ONE additional event-level
audit row.

The single load-bearing constraint is the **23505 dangling-tx landmine**:
``SettlementService.resolve_market`` opens its OWN ``async with session.begin()``,
and on the idempotent-replay path a duplicate idempotency key raises Postgres
``23505`` whose handler leaves an open implicit transaction. Chaining a second
self-committing settle on the SAME session then raises
``InvalidRequestError: A transaction is already begun on this Session``. Therefore
the loop opens a fresh ``async with session_maker() as child_session:`` per child
and NEVER wraps two settle calls in one ``with`` / ``begin()``.

``derive_event_status`` is a pure, stdlib-only free function — the canonical
``build_settlement_plan`` pure-projection idiom (``plan.py``): no I/O, no ORM, no
DB session. Per **EVT-06** an event's status is *derived at read time* from
its constituent markets' states — there is deliberately NO authoritative
``status``/``winning_outcome`` column on ``market_groups`` (migration 0011 omitted
them), so this function — not a stored column — is the source of truth.

Status set is EXACTLY ``{open, partially_resolved, resolved, void}`` (the
roadmap's four). ``void`` vs ``resolved`` is itself derived: event outcomes are
mutually exclusive, so all children resolved with no YES-winner ⟺ ``void`` and
all children resolved with exactly one YES-winner ⟺ ``resolved``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.audit.service import AuditService
from app.db.session import _get_session_maker
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup, Outcome, generate_slug
from app.settlement.adapters import HouseMarketResolveAdapter
from app.settlement.service import SettlementService

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.settlement.event_schemas import CreateEventRequest, UpdateEventRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChildStatus:
    """Minimal per-child facts :func:`derive_event_status` needs.

    Decoupled from the ORM (a plain pair of scalars) so the projection — and its
    unit tests — need no session. Mirrors the frozen-slots input idiom of
    :class:`~app.settlement.plan.BetToSettle`.
    """

    status: str  # a Market.status value (e.g. MarketStatus.OPEN/RESOLVED .value)
    is_yes_winner: bool  # this child resolved with its YES outcome as the winner


@dataclass(frozen=True, slots=True)
class EventSettleResult:
    """The summary :class:`EventService` returns after a resolve/void pass.

    Carries the derived event ``status`` (via :func:`derive_event_status`) plus the
    failed-child list so a caller can surface a partial failure. No money — the
    per-child payouts are owned (and audited) by ``SettlementService``.
    """

    group_id: UUID
    child_count: int
    children_settled: int
    children_failed: tuple[UUID, ...]  # ids of children whose settle raised (best-effort)
    status: str  # one of {"open", "partially_resolved", "resolved", "void"}


def derive_event_status(children: Sequence[ChildStatus]) -> str:
    """Project an event's status from its child markets (EVT-06).

    Pure and total — an empty event yields ``"open"`` and never raises:

    - no children / no child ``RESOLVED`` -> ``"open"``
    - ``>=1`` child ``RESOLVED`` and ``>=1`` still unresolved -> ``"partially_resolved"``
    - all children ``RESOLVED`` with exactly one YES winner -> ``"resolved"``
    - all children ``RESOLVED`` with no YES winner -> ``"void"``

    The returned value is always one of the four status literals
    ``{"open", "partially_resolved", "resolved", "void"}``.
    """
    if not children:
        return "open"
    resolved = [c for c in children if c.status == MarketStatus.RESOLVED.value]
    n_resolved, n_total = len(resolved), len(children)
    if n_resolved == 0:
        return "open"
    if n_resolved < n_total:
        return "partially_resolved"
    # all children resolved -> resolved (exactly one YES winner) vs void (no YES
    # winner). Event outcomes are mutually exclusive: a real resolution has
    # exactly one YES.
    return "resolved" if any(c.is_yes_winner for c in resolved) else "void"


# --------------------------------------------------------------------------- #
# Shared private helpers (load + YES/NO mapping). All read-only; the per-child
# settle owns its own session inside SettlementService.
# --------------------------------------------------------------------------- #
async def _load_group_with_children(session: AsyncSession, group_id: UUID) -> MarketGroup | None:
    """Eager-load a group + its children + each child's outcomes.

    ``MarketGroup.markets`` and ``Market.outcomes`` are ``lazy="raise"`` (models.py
    :184/:272), so a bare relationship access would raise. ``selectinload`` chains
    the eager load exactly as the Polymarket task does for ``Market.outcomes``.
    Returns ``None`` if no such group exists (the caller raises).
    """
    return (
        await session.execute(
            select(MarketGroup)
            .where(MarketGroup.id == group_id)
            .options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
        )
    ).scalar_one_or_none()


async def _yes_outcome_id(session: AsyncSession, market_id: UUID) -> UUID:
    """The child's YES outcome id (case-insensitive — IN-01).

    House labels are ``"YES"``; mirrored Polymarket labels are title-case ``"Yes"``.
    A case-sensitive ``== "YES"`` silently misses mirrored data, so match
    ``func.upper(Outcome.label) == "YES"`` (markets/service.py:182/:374-378).
    """
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


def _require_justification(justification: str) -> None:
    """Raise on a blank/whitespace justification (V5 input-validation; CONTEXT).

    The EVA-03 two-step confirm is a Phase-16 UI/API concern; the service just
    refuses an empty resolution reason so the non-repudiation audit row is never
    blank.
    """
    if not justification or not justification.strip():
        raise ValueError("A non-empty justification is required to resolve/void an event.")


def _reject_if_mirrored(group: MarketGroup) -> None:
    """Raise if ``group`` is mirrored (Polymarket) — admin read-only (EVA-06).

    Mirrored children auto-settle through the existing ``detect_polymarket_resolutions``
    UMA path; the only admin mutation of a mirrored event is the audited emergency
    force-settle (ADM-06, Phase 16). Phase 16 maps this raise to an HTTP 4xx.
    """
    if group.source == MarketSourceEnum.POLYMARKET.value:
        raise ValueError(
            "Mirrored (Polymarket) events are admin read-only; use force-settle (ADM-06)."
        )


class EventService:
    """Orchestrates house-event resolve/void by looping ``SettlementService`` per child.

    Each child settles on its OWN fresh ``AsyncSession`` (the 23505 dangling-tx
    landmine forbids chaining two self-committing settle calls on one session).
    Idempotency, atomicity, lock-ordering, payouts, and per-child audit are ALL
    inherited from the UNCHANGED ``SettlementService``; this class adds only the
    loop, the YES/NO mapping, the mirrored-reject gate, the justification guard,
    and one event-level audit row.
    """

    @classmethod
    async def resolve_event(
        cls,
        *,
        group_id: UUID,
        winning_outcome_id: UUID,
        justification: str,
        actor_user_id: UUID | None = None,
    ) -> EventSettleResult:
        """Resolve a house event: winner child on YES, every other child on NO (EVA-03).

        Loops ``SettlementService.resolve_market`` over the group's children, one
        child per fresh session, winning child FIRST then losers by ``market.id``
        (winners are paid before any loser-child hiccup). Best-effort: a child
        whose settle raises is recorded and the loop continues — already-settled
        siblings stay intact, the event derives ``partially_resolved``, and an
        idempotent re-run finishes (already-settled children are a no-op because
        their bets are no longer PENDING). Writes ONE ``event.resolved`` audit row.

        Raises ``ValueError`` on a mirrored (Polymarket) group, a blank
        justification, or a ``winning_outcome_id`` that does not map to exactly one
        child of the group (a defensive service-layer guard — the authoritative
        validation is the Phase-16 admin endpoint).
        """
        _require_justification(justification)

        session_maker = _get_session_maker()

        # 1. Read pass: load the group + children + outcomes; reject mirrored; build
        #    the (child_market_id, child_winning_outcome_id) settle list.
        async with session_maker() as read_session:
            group = await _load_group_with_children(read_session, group_id)
            if group is None:
                raise ValueError(f"No market group {group_id}.")
            _reject_if_mirrored(group)

            children = list(group.markets)
            child_ids = {m.id for m in children}

            # Defensive winning-outcome guard (Open Q2): the supplied outcome must
            # belong to exactly one child of THIS group.
            winner_market_ids = (
                (
                    await read_session.execute(
                        select(Outcome.market_id).where(
                            Outcome.id == winning_outcome_id,
                            Outcome.market_id.in_(child_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if len(winner_market_ids) != 1:
                raise ValueError(
                    f"winning_outcome_id {winning_outcome_id} does not map to exactly "
                    f"one child of group {group_id}."
                )
            winner_market_id = winner_market_ids[0]

            # CR-01: resolve settles the winner on its YES leg, so the supplied
            # outcome MUST be that child's YES outcome. Without this guard a caller
            # passing the child's NO leg would settle EVERY child on NO (deriving
            # "void") while the audit row still claims "event.resolved" — an
            # inconsistent, financially wrong state (the intended winner's YES
            # bettors would lose). Use void_event to settle every child on NO.
            winner_yes_id = await _yes_outcome_id(read_session, winner_market_id)
            if winning_outcome_id != winner_yes_id:
                raise ValueError(
                    f"winning_outcome_id {winning_outcome_id} is not the YES outcome of "
                    f"its child market {winner_market_id}; resolve_event settles the winner "
                    f"on YES (use void_event to settle every child on NO)."
                )

            # The winning child settles on the supplied YES; every other child on
            # its NO leg (event-of-binaries: exactly one child can be YES — A1).
            loser_children = sorted(
                (m for m in children if m.id != winner_market_id), key=lambda m: str(m.id)
            )
            ordered_children: list[tuple[UUID, UUID]] = [(winner_market_id, winning_outcome_id)]
            for m in loser_children:
                ordered_children.append((m.id, await _no_outcome_id(read_session, m.id)))

        # 2. Settle each child on its OWN fresh session (the 23505 landmine).
        failed = await cls._settle_children(
            session_maker, ordered_children, justification, actor_user_id
        )

        # 3. One event-level audit row in its own tx.
        await cls._record_event_audit(
            session_maker,
            event_type="event.resolved",
            group_id=group_id,
            winning_outcome_id=winning_outcome_id,
            child_count=len(ordered_children),
            failed=failed,
            justification=justification,
            actor_user_id=actor_user_id,
        )

        # 4. Project the final derived status from the (now committed) child rows.
        status = await cls._derive_status(session_maker, group_id)
        return EventSettleResult(
            group_id=group_id,
            child_count=len(ordered_children),
            children_settled=len(ordered_children) - len(failed),
            children_failed=tuple(failed),
            status=status,
        )

    @classmethod
    async def void_event(
        cls,
        *,
        group_id: UUID,
        justification: str,
        actor_user_id: UUID | None = None,
    ) -> EventSettleResult:
        """Void a house event: EVERY child settles on its NO outcome (EVA-04).

        Same fresh-session-per-child loop as :meth:`resolve_event`, but with no
        winner — every child resolves on its NO leg (YES bettors lose, NO bettors
        win). This is explicitly NOT a stake refund (no refund path exists in the
        ledger). Writes ONE ``event.voided`` audit row. All-children-NO all-resolved
        derives to ``"void"``.

        Raises ``ValueError`` on a mirrored (Polymarket) group or a blank
        justification.
        """
        _require_justification(justification)

        session_maker = _get_session_maker()

        # 1. Read pass: load + reject mirrored + map EVERY child to its NO leg.
        async with session_maker() as read_session:
            group = await _load_group_with_children(read_session, group_id)
            if group is None:
                raise ValueError(f"No market group {group_id}.")
            _reject_if_mirrored(group)

            children = sorted(group.markets, key=lambda m: str(m.id))
            ordered_children: list[tuple[UUID, UUID]] = [
                (m.id, await _no_outcome_id(read_session, m.id)) for m in children
            ]

        # 2. Settle each child (its NO outcome) on its OWN fresh session.
        failed = await cls._settle_children(
            session_maker, ordered_children, justification, actor_user_id
        )

        # 3. One event-level audit row (event.voided; no winning_outcome_id).
        await cls._record_event_audit(
            session_maker,
            event_type="event.voided",
            group_id=group_id,
            winning_outcome_id=None,
            child_count=len(ordered_children),
            failed=failed,
            justification=justification,
            actor_user_id=actor_user_id,
        )

        # 4. Project the derived status (all-children-NO all-resolved -> "void").
        status = await cls._derive_status(session_maker, group_id)
        return EventSettleResult(
            group_id=group_id,
            child_count=len(ordered_children),
            children_settled=len(ordered_children) - len(failed),
            children_failed=tuple(failed),
            status=status,
        )

    @classmethod
    async def reverse_event(
        cls,
        *,
        group_id: UUID,
        justification: str,
        actor_user_id: UUID | None = None,
    ) -> EventSettleResult:
        """Reverse a house event's settlement: loop ``reverse_settlement`` per child (EVA-05).

        Mirrors :meth:`resolve_event`/:meth:`void_event` but composes the UNCHANGED
        ``SettlementService.reverse_settlement`` over every already-settled child,
        ONE FRESH session per child. Each child's compensating (inverse) transfers
        restore its pre-settlement balances, flip its ``SETTLED`` bets back to
        ``PENDING``, and reopen it (``CLOSED``) — so after a FULL reverse the event
        derives back to ``"open"``. No ``winning_outcome_id``: ``reverse_settlement``
        finds the ``SETTLED`` bets by status, not by winner.

        Idempotent: a second ``reverse_event`` over the same group finds no
        ``SETTLED`` bets per child and is a no-op (no double-refund). Best-effort and
        per-child isolated: a child whose winner already spent the winnings hits
        ``CHECK (balance >= 0)`` and that child's reversal rolls back ALONE — siblings
        already reversed stay reversed (Pitfall 3; another reason for Option A's
        per-child fresh sessions). Writes ONE ``event.reversed`` audit row.

        Raises ``ValueError`` on a mirrored (Polymarket) group (admin read-only,
        EVA-06) or a blank justification.

        DEFERRED (Pitfall 6 — known limitation, NOT a Phase-15 bug): this reverse is
        "restore pre-settlement state + audit" ONLY (mirrors STL-07). It does NOT
        support re-RESOLVING a child after a reverse — that would reuse the original
        ``settle:{bet_id}:{leg}`` idempotency keys and collide on Postgres ``23505``
        (``constants.py`` ``reverse_idempotency_key`` note). Re-resolution-after-reverse
        needs a per-bet settlement epoch in the key (deferred, out of scope here).
        """
        _require_justification(justification)

        session_maker = _get_session_maker()

        # 1. Read pass: load the group + children; reject mirrored. Reverse needs no
        #    YES/NO mapping — ``reverse_settlement`` reads SETTLED bets directly — so
        #    the ordered list is just the child ids (deterministic ``market.id`` order).
        async with session_maker() as read_session:
            group = await _load_group_with_children(read_session, group_id)
            if group is None:
                raise ValueError(f"No market group {group_id}.")
            _reject_if_mirrored(group)

            ordered_children: list[UUID] = sorted((m.id for m in group.markets), key=str)

        # 2. Reverse each child on its OWN fresh session (the 23505 landmine + the
        #    per-child balance-floor isolation of Pitfall 3).
        failed = await cls._reverse_children(
            session_maker, ordered_children, justification, actor_user_id
        )

        # 3. One event-level audit row in its own tx (mirrors resolve/void + STL-07).
        await cls._record_event_audit(
            session_maker,
            event_type="event.reversed",
            group_id=group_id,
            winning_outcome_id=None,
            child_count=len(ordered_children),
            failed=failed,
            justification=justification,
            actor_user_id=actor_user_id,
        )

        # 4. Project the derived status from the (now reopened) child rows. A full
        #    reverse reopens every child to CLOSED -> the event derives back to "open".
        status = await cls._derive_status(session_maker, group_id)
        return EventSettleResult(
            group_id=group_id,
            child_count=len(ordered_children),
            children_settled=len(ordered_children) - len(failed),
            children_failed=tuple(failed),
            status=status,
        )

    # ----------------------------------------------------------------------- #
    # Internals.
    # ----------------------------------------------------------------------- #
    @staticmethod
    async def _settle_children(
        session_maker: async_sessionmaker[AsyncSession],
        ordered_children: Sequence[tuple[UUID, UUID]],
        justification: str,
        actor_user_id: UUID | None,
    ) -> list[UUID]:
        """Loop ``SettlementService.resolve_market`` per child on a FRESH session.

        THE core idiom: one ``async with session_maker() as child_session:`` per
        child — never two settle calls in one ``with``/``begin()`` (the 23505
        dangling-tx landmine). Best-effort: a child whose settle raises is appended
        to ``failed`` and the loop continues (already-settled siblings stay intact).
        """
        resolver = HouseMarketResolveAdapter()  # same port instance per child
        failed: list[UUID] = []
        for child_market_id, child_winning_outcome_id in ordered_children:
            async with session_maker() as child_session:  # FRESH session per child
                try:
                    await SettlementService.resolve_market(
                        child_session,
                        market_id=child_market_id,
                        winning_outcome_id=child_winning_outcome_id,
                        market_resolver=resolver,
                        justification=justification,
                        actor_user_id=actor_user_id,
                    )
                except Exception:  # best-effort partial failure (CONTEXT)
                    # WR-01: financial code — never swallow silently. Log with full
                    # traceback so a child-settle failure is diagnosable; the child is
                    # recorded as failed and the loop continues (siblings intact).
                    logger.exception(
                        "event resolve: child %s failed (best-effort; continuing)",
                        child_market_id,
                    )
                    failed.append(child_market_id)
                    continue  # siblings intact -> the event derives partially_resolved
        return failed

    @staticmethod
    async def _reverse_children(
        session_maker: async_sessionmaker[AsyncSession],
        ordered_children: Sequence[UUID],
        justification: str,
        actor_user_id: UUID | None,
    ) -> list[UUID]:
        """Loop ``SettlementService.reverse_settlement`` per child on a FRESH session.

        The reverse twin of :meth:`_settle_children`: one
        ``async with session_maker() as child_session:`` per already-settled child —
        never two reverse calls in one ``with``/``begin()`` (the 23505 dangling-tx
        landmine, the same reason resolve uses fresh sessions). Best-effort and
        per-child isolated: a winner who already spent the winnings hits
        ``CHECK (balance >= 0)`` and THAT child's reversal rolls back alone (Pitfall 3);
        the id is appended to ``failed`` and the loop continues — siblings already
        reversed stay reversed. A re-reverse over an already-reversed child finds no
        ``SETTLED`` bets and is a no-op (idempotent — no double-refund).
        """
        resolver = HouseMarketResolveAdapter()  # same port instance per child
        failed: list[UUID] = []
        for child_market_id in ordered_children:
            async with session_maker() as child_session:  # FRESH session per child
                try:
                    await SettlementService.reverse_settlement(
                        child_session,
                        market_id=child_market_id,
                        market_resolver=resolver,
                        justification=justification,
                        actor_user_id=actor_user_id,
                    )
                except Exception:  # CHECK(balance>=0) floor / best-effort (Pitfall 3)
                    # WR-01: log with traceback (e.g. the CHECK(balance>=0) floor when a
                    # winner already spent winnings) so the per-child reversal failure is
                    # diagnosable; that child rolls back alone and the loop continues.
                    logger.exception(
                        "event reverse: child %s failed (best-effort; continuing)",
                        child_market_id,
                    )
                    failed.append(child_market_id)
                    continue  # siblings already reversed stay reversed
        return failed

    @staticmethod
    async def _record_event_audit(
        session_maker: async_sessionmaker[AsyncSession],
        *,
        event_type: str,
        group_id: UUID,
        winning_outcome_id: UUID | None,
        child_count: int,
        failed: Sequence[UUID],
        justification: str,
        actor_user_id: UUID | None,
    ) -> None:
        """Write ONE event-level audit row in its own small tx.

        Mirrors ``force_settle``'s action-THEN-audit "separate begin()" idiom
        (router.py:185-199) and the per-child ``settlement.resolved`` actor/payload
        convention (service.py:235-248). ``AuditService.record`` only flushes, so it
        runs INSIDE ``audit_session.begin()``. The payload carries only ids + counts
        (no money); every string field stays a str.
        """
        payload: dict[str, object] = {
            "group_id": str(group_id),
            "winning_outcome_id": (
                str(winning_outcome_id) if winning_outcome_id is not None else None
            ),
            "child_count": child_count,
            "children_settled": child_count - len(failed),
            "children_failed": [str(x) for x in failed],
            "justification": justification,
        }
        # WR-04: this event-level summary row is written AFTER the per-child sessions
        # have each committed, so the children cannot be rolled back if it fails. The
        # authoritative audit trail is the per-child settlement.resolved/reversed rows
        # SettlementService already committed; this row is an aggregate convenience.
        # Log with traceback before re-raising so an audit-write failure is never silent.
        async with session_maker() as audit_session, audit_session.begin():
            try:
                await AuditService.record(
                    audit_session,
                    actor=f"user:{actor_user_id}" if actor_user_id is not None else "system",
                    event_type=event_type,
                    payload=payload,
                )
            except Exception:
                logger.exception(
                    "event audit %s for group %s failed AFTER children settled; the "
                    "per-child settlement.* rows remain the authoritative audit trail",
                    event_type,
                    group_id,
                )
                raise

    @staticmethod
    async def _derive_status(
        session_maker: async_sessionmaker[AsyncSession], group_id: UUID
    ) -> str:
        """Project the event's derived status from its (committed) child rows (EVT-06).

        Re-loads each child's ``status`` + ``winning_outcome_id`` and computes
        ``is_yes_winner`` (its persisted winner == its YES outcome), then defers to
        the pure :func:`derive_event_status`. No stored column is read or written.
        """
        async with session_maker() as s:
            group = await _load_group_with_children(s, group_id)
            if group is None:  # pragma: no cover — guarded by the caller's load
                return "open"
            child_statuses: list[ChildStatus] = []
            for child in group.markets:
                yes_id = next((o.id for o in child.outcomes if o.label.upper() == "YES"), None)
                is_yes_winner = (
                    child.winning_outcome_id is not None and child.winning_outcome_id == yes_id
                )
                child_statuses.append(ChildStatus(status=child.status, is_yes_winner=is_yes_winner))
        return derive_event_status(child_statuses)

    # --------------------------------------------------------------------- #
    # EVA-01 / EVA-02 — house-event create + pre-bet edit (Phase 16 service path).
    # Plain ORM inserts on the REQUEST session (NOT a settle loop -> no 23505
    # dangling-tx landmine), one commit. Mirrors MarketService.create_market's
    # slug-retry + YES/NO seeding; does NOT touch resolve/void/reverse above.
    # --------------------------------------------------------------------- #
    @classmethod
    async def create_house_event(
        cls,
        session: AsyncSession,
        *,
        admin_id: UUID,
        body: CreateEventRequest,
    ) -> MarketGroup:
        """Create one HOUSE ``MarketGroup`` + N binary YES/NO children (EVA-01).

        Inserts the group (unique slug via the ``begin_nested()`` + IntegrityError
        retry copied from ``MarketService.create_market``), then per outcome a child
        ``Market`` (``group_id`` set, ``group_item_title=label``, OPEN, shared
        ``deadline``) with exactly a YES (seeded at ``initial_odds``) + NO pair, writes
        one ``event.created`` audit row, commits once, and returns the group.
        """
        for _attempt in range(3):
            group = MarketGroup(
                title=body.title,
                source=MarketSourceEnum.HOUSE.value,
                category=body.category,
                slug=body.slug or generate_slug(body.title),
            )
            session.add(group)
            try:
                nested = await session.begin_nested()
                await session.flush()
                break
            except IntegrityError:
                await nested.rollback()
                session.expunge(group)
        else:
            raise HTTPException(status_code=409, detail="Slug collision — try again")

        for outcome in body.outcomes:
            await _add_event_child(
                session,
                group=group,
                label=outcome.label,
                initial_odds=outcome.initial_odds,
                deadline=body.deadline,
                category=body.category,
                resolution_criteria=body.resolution_criteria,
            )

        # Capture the id BEFORE commit so a later read survives expire-on-commit
        # (re-touching an expired ORM attribute in async would raise MissingGreenlet).
        new_group_id = group.id
        await AuditService.record(
            session,
            actor=f"user:{admin_id}",
            event_type="event.created",
            payload={
                "group_id": str(new_group_id),
                "title": body.title,
                "child_count": len(body.outcomes),
            },
        )
        await session.commit()
        reloaded = await _load_group_with_children(session, new_group_id)
        assert reloaded is not None  # noqa: S101 — just committed above
        return reloaded

    @classmethod
    async def update_house_event(
        cls,
        session: AsyncSession,
        *,
        group_id: UUID,
        body: UpdateEventRequest,
    ) -> MarketGroup:
        """Pre-bet edit of a house event (EVA-02). The 423 edit-lock is enforced upstream.

        Mutates ``title`` (group + each child's derived ``question``), ``category``
        (group + children), and ``deadline`` (children — the group has none). When
        ``body.outcomes`` is supplied it REPLACES the children wholesale — the old
        children are deleted (their ``Outcome`` rows cascade via the DB-level
        ``outcomes.market_id`` ``ON DELETE CASCADE`` FK) and rebuilt from the new list.
        Commits and returns the reloaded group.
        """
        group = await _load_group_with_children(session, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Event not found")

        children = list(group.markets)
        existing_deadline = children[0].deadline if children else None

        if body.title is not None:
            group.title = body.title
        if body.category is not None:
            group.category = body.category

        if body.outcomes is not None:
            # Whole-list REPLACE. ``synchronize_session=False`` because we discard the
            # in-session children immediately and re-query at the end — no need for the
            # ORM to evaluate the criterion against the identity map. The to-be-deleted
            # children are NOT mutated above (the metadata branch below is skipped), so
            # there is no dirty-then-deleted flush hazard.
            await session.execute(
                delete(Market)
                .where(Market.group_id == group_id)
                .execution_options(synchronize_session=False)
            )
            await session.flush()
            new_deadline = body.deadline or existing_deadline
            new_category = body.category if body.category is not None else group.category
            for outcome in body.outcomes:
                await _add_event_child(
                    session,
                    group=group,
                    label=outcome.label,
                    initial_odds=outcome.initial_odds,
                    deadline=new_deadline,
                    category=new_category,
                    resolution_criteria=None,
                )
        else:
            # Metadata-only edit — propagate to the existing children. A title change
            # re-derives each child's ``question`` so it does not bear the stale title.
            for child in children:
                if body.category is not None:
                    child.category = body.category
                if body.deadline is not None:
                    child.deadline = body.deadline
                if body.title is not None:
                    child.question = f"{body.title} — {child.group_item_title}?"

        await session.commit()
        # The replace path deletes the old children with synchronize_session=False, so the
        # group's already-loaded `markets` collection is stale; expunge the identity map so
        # the reload reflects the committed DB rows (the new children) rather than the cache.
        session.expunge_all()
        refreshed = await _load_group_with_children(session, group_id)
        assert refreshed is not None  # noqa: S101 — just committed above
        return refreshed


# Synthesized child resolution criteria — ``Market.resolution_criteria`` is NOT NULL
# even when the admin supplies none for the event.
_DEFAULT_EVENT_CHILD_CRITERIA = (
    "Resolves YES if this outcome occurs, per the event's official source."
)


async def _add_event_child(
    session: AsyncSession,
    *,
    group: MarketGroup,
    label: str,
    initial_odds: Decimal,
    deadline: datetime,
    category: str | None,
    resolution_criteria: str | None = None,
) -> Market:
    """Insert ONE binary YES/NO child market under ``group`` (binary-trigger-safe).

    Exactly a YES (seeded at ``initial_odds``) + NO (``1 - initial_odds``) pair — never
    a 3rd outcome (``trg_binary_outcomes_only``). ``group_item_title`` carries the
    label; writes ride the caller's session (``flush`` only). Returns the child.
    """
    child = Market(
        question=f"{group.title} — {label}?",
        slug=generate_slug(f"{group.title} {label}"),
        resolution_criteria=resolution_criteria or _DEFAULT_EVENT_CHILD_CRITERIA,
        category=category,
        source=MarketSourceEnum.HOUSE.value,
        status=MarketStatus.OPEN.value,
        deadline=deadline,
        group_id=group.id,
        group_item_title=label,
    )
    session.add(child)
    await session.flush()

    odds_no = Decimal("1") - initial_odds
    session.add_all(
        [
            Outcome(
                market_id=child.id,
                label="YES",
                initial_odds=initial_odds,
                current_odds=initial_odds,
            ),
            Outcome(
                market_id=child.id,
                label="NO",
                initial_odds=odds_no,
                current_odds=odds_no,
            ),
        ]
    )
    await session.flush()
    return child


async def event_has_bets(session: AsyncSession, group_id: UUID) -> bool:
    """True if ANY child market of ``group_id`` has a bet (the EVA-02 edit-lock signal).

    ``EXISTS(SELECT 1 FROM bets WHERE market_id IN (children))`` — the real per-child
    bet signal, NOT the dead denormalised counter column (never incremented in app
    code). ``Bet`` is imported lazily to avoid any settlement<->bets import cycle.
    """
    from app.bets.models import Bet

    child_ids = select(Market.id).where(Market.group_id == group_id)
    return bool(await session.scalar(select(exists().where(Bet.market_id.in_(child_ids)))))
