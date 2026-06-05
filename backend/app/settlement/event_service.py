"""Event-level settlement (Phase 15) — derived status + the resolve/void orchestration.

This module hosts the event-of-binaries settlement layer that loops the proven
per-market :class:`~app.settlement.service.SettlementService` over a
:class:`~app.markets.models.MarketGroup`'s child markets.

**Wave 1** ships the pure read-projection (``derive_event_status`` /
``ChildStatus``); **Wave 2 (this plan)** extends the SAME module with
:class:`EventService` — ``resolve_event`` / ``void_event`` classmethods that
COMPOSE the UNCHANGED ``SettlementService`` over a group's children, one child
per FRESH ``AsyncSession`` (Option A — per-child ACID transaction). This phase
reinvents NO settlement: the payouts, loser sweep, bet flips, market-status
flip, per-bet idempotency keys, FOR-UPDATE lock ordering, and per-child
``settlement.resolved`` audit rows all live inside ``SettlementService`` and stay
byte-for-byte unchanged. The event service only orchestrates the loop, maps the
winning outcome to each child's YES/NO leg, rejects mirrored (Polymarket) groups,
enforces a non-blank justification, and writes ONE additional event-level audit
row.

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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.audit.service import AuditService
from app.db.session import _get_session_maker
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, MarketGroup, Outcome
from app.settlement.adapters import HouseMarketResolveAdapter
from app.settlement.service import SettlementService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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

    # ----------------------------------------------------------------------- #
    # Internals.
    # ----------------------------------------------------------------------- #
    @staticmethod
    async def _settle_children(
        session_maker,
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
                    failed.append(child_market_id)
                    continue  # siblings intact -> the event derives partially_resolved
        return failed

    @staticmethod
    async def _record_event_audit(
        session_maker,
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
        async with session_maker() as audit_session, audit_session.begin():
            await AuditService.record(
                audit_session,
                actor=f"user:{actor_user_id}" if actor_user_id is not None else "system",
                event_type=event_type,
                payload=payload,
            )

    @staticmethod
    async def _derive_status(session_maker, group_id: UUID) -> str:
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
