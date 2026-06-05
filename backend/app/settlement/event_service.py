"""Event-level settlement (Phase 15) — derived event-status read-projection.

This module hosts the event-of-binaries settlement layer that loops the proven
per-market :class:`~app.settlement.service.SettlementService` over a
:class:`~app.markets.models.MarketGroup`'s child markets. **Wave 1 (this plan)
ships ONLY the pure read-projection** — the ``EventService`` orchestration class
(resolve/void/reverse) arrives in Wave 2 and extends this same module.

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

from app.markets.enums import MarketStatus


@dataclass(frozen=True, slots=True)
class ChildStatus:
    """Minimal per-child facts :func:`derive_event_status` needs.

    Decoupled from the ORM (a plain pair of scalars) so the projection — and its
    unit tests — need no session. Mirrors the frozen-slots input idiom of
    :class:`~app.settlement.plan.BetToSettle`.
    """

    status: str  # a Market.status value (e.g. MarketStatus.OPEN/RESOLVED .value)
    is_yes_winner: bool  # this child resolved with its YES outcome as the winner


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
