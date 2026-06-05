"""Pure unit tests for the EVT-06 derived event-status projection (Phase 15).

NO database, NO Docker, NO fixtures — mirrors ``test_plan.py``'s
direct-construct-and-assert style. ``derive_event_status`` is a pure free
function over a sequence of :class:`ChildStatus` scalars, so these tests
construct inputs directly and assert the returned status literal.

Covers the four-state contract ``{open, partially_resolved, resolved, void}``
plus the empty event and the void edge (all children resolved with no
YES-winner). The ``void`` vs ``resolved`` disambiguation is the load-bearing
case (threat T-15-01: never mask a void as a resolved event).
"""

from __future__ import annotations

from app.markets.enums import MarketStatus
from app.settlement.event_service import ChildStatus, derive_event_status

_RESOLVED = MarketStatus.RESOLVED.value
_OPEN = MarketStatus.OPEN.value


def _child(status: str, *, is_yes_winner: bool = False) -> ChildStatus:
    return ChildStatus(status=status, is_yes_winner=is_yes_winner)


# --------------------------------------------------------------------------- #
# open: empty event, or no child resolved.
# --------------------------------------------------------------------------- #
def test_empty_event_is_open() -> None:
    assert derive_event_status([]) == "open"


def test_no_resolved_children_is_open() -> None:
    children = [_child(_OPEN), _child(_OPEN), _child(_OPEN)]
    assert derive_event_status(children) == "open"


# --------------------------------------------------------------------------- #
# partially_resolved: >=1 resolved AND >=1 unresolved.
# --------------------------------------------------------------------------- #
def test_partial_resolution_is_partially_resolved() -> None:
    children = [
        _child(_RESOLVED, is_yes_winner=False),
        _child(_OPEN),
        _child(_OPEN),
    ]
    assert derive_event_status(children) == "partially_resolved"


def test_partial_resolution_with_winner_still_partially_resolved() -> None:
    # Even the eventual YES winner being resolved does not make the EVENT
    # resolved while a sibling is still open.
    children = [
        _child(_RESOLVED, is_yes_winner=True),
        _child(_OPEN),
    ]
    assert derive_event_status(children) == "partially_resolved"


# --------------------------------------------------------------------------- #
# resolved: all children resolved with exactly one YES winner.
# --------------------------------------------------------------------------- #
def test_all_resolved_one_yes_winner_is_resolved() -> None:
    children = [
        _child(_RESOLVED, is_yes_winner=True),
        _child(_RESOLVED, is_yes_winner=False),
        _child(_RESOLVED, is_yes_winner=False),
    ]
    assert derive_event_status(children) == "resolved"


def test_single_resolved_yes_winner_is_resolved() -> None:
    # A one-child event resolved on its YES leg.
    children = [_child(_RESOLVED, is_yes_winner=True)]
    assert derive_event_status(children) == "resolved"


# --------------------------------------------------------------------------- #
# void (the void edge): all children resolved, none won YES.
# --------------------------------------------------------------------------- #
def test_all_resolved_no_yes_winner_is_void() -> None:
    children = [
        _child(_RESOLVED, is_yes_winner=False),
        _child(_RESOLVED, is_yes_winner=False),
        _child(_RESOLVED, is_yes_winner=False),
    ]
    assert derive_event_status(children) == "void"


def test_single_resolved_no_yes_winner_is_void() -> None:
    children = [_child(_RESOLVED, is_yes_winner=False)]
    assert derive_event_status(children) == "void"
