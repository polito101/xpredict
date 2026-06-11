"""Bet ORM model shape (Phase 5).

Migration-free during parallel development: the ``bets`` table DDL ships with the
integration migration ``0005`` (off Phase 4's ``0004``). These pure-unit tests pin the
model's columns, money typing, status default, and the deliberate ABSENCE of a FK to
``markets``/``outcomes`` (the FK is added at integration, not here).
"""

from __future__ import annotations

from sqlalchemy import Numeric

from app.bets.constants import BET_PENDING
from app.bets.models import Bet


def test_bet_has_expected_columns() -> None:
    cols = set(Bet.__table__.columns.keys())
    assert {
        "id",
        "user_id",
        "market_id",
        "outcome_id",
        "stake",
        "status",
        "closed_at",
        "exit_odds",
        "created_at",
        "tenant_id",
    } <= cols


def test_stake_is_numeric_18_4() -> None:
    """``stake`` is the canonical Money type (NUMERIC(18,4)) — never float."""
    stake_type = Bet.__table__.c.stake.type
    assert isinstance(stake_type, Numeric)
    assert stake_type.precision == 18
    assert stake_type.scale == 4


def test_odds_at_placement_is_numeric_8_6() -> None:
    """``odds_at_placement`` is the probability locked at placement — Numeric(8,6).

    It mirrors Phase 4's ``Outcome.current_odds`` precision (a probability in (0,1],
    NOT money) so the locked price is captured faithfully and ``scripts/lint_money_columns.py``
    stays green via the dedicated ``Odds`` type alias (not the money ``Numeric(18,4)``).
    """
    col = Bet.__table__.c.odds_at_placement
    assert isinstance(col.type, Numeric)
    assert col.type.precision == 8
    assert col.type.scale == 6
    assert col.nullable is False


def test_status_server_default_is_pending() -> None:
    server_default = Bet.__table__.c.status.server_default
    assert server_default is not None
    assert str(server_default.arg) == BET_PENDING


def test_no_fk_to_markets_yet() -> None:
    """Parallel-safe: the Bet has NO FK (added at integration migration 0005)."""
    assert len(Bet.__table__.foreign_keys) == 0


def test_exit_odds_is_numeric_8_6_nullable() -> None:
    """``exit_odds`` (price captured at early close) is a nullable Numeric(8,6)."""
    col = Bet.__table__.c.exit_odds
    assert isinstance(col.type, Numeric)
    assert col.type.precision == 8
    assert col.type.scale == 6
    assert col.nullable is True


def test_closed_at_is_nullable_timezone_datetime() -> None:
    from sqlalchemy import DateTime

    col = Bet.__table__.c.closed_at
    assert isinstance(col.type, DateTime)
    assert col.type.timezone is True
    assert col.nullable is True


def test_status_check_allows_closed() -> None:
    """The widened bets_status_check CHECK admits the CLOSED terminal status."""
    from sqlalchemy import CheckConstraint

    checks = [
        c
        for c in Bet.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "bets_status_check"
    ]
    assert len(checks) == 1
    assert "CLOSED" in str(checks[0].sqltext)
