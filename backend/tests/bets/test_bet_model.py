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
        "created_at",
        "tenant_id",
    } <= cols


def test_stake_is_numeric_18_4() -> None:
    """``stake`` is the canonical Money type (NUMERIC(18,4)) — never float."""
    stake_type = Bet.__table__.c.stake.type
    assert isinstance(stake_type, Numeric)
    assert stake_type.precision == 18
    assert stake_type.scale == 4


def test_status_server_default_is_pending() -> None:
    server_default = Bet.__table__.c.status.server_default
    assert server_default is not None
    assert str(server_default.arg) == BET_PENDING


def test_no_fk_to_markets_yet() -> None:
    """Parallel-safe: the Bet has NO FK (added at integration migration 0005)."""
    assert len(Bet.__table__.foreign_keys) == 0
