"""Pydantic v2 schemas for the live-bets bridge (v1.3, LB-A).

Two groups:
  - ROUTER response/request models (``SessionResponse``, ``TableItem`` /
    ``TablesResponse``, ``MirrorResult``) — the shapes the ``/api/live/*`` routes
    expose, NOT the raw live-bets payloads.
  - A small internal parser (``VerifiedBet`` + :func:`parse_verified_bet`) for the
    live-bets ``GET /v2/bets/{id}`` response, so the service has ONE typed object to
    reason about. All monetary values are ``Decimal`` (never ``float``), parsed via
    ``_safe_decimal`` exactly like the polymarket parser.

OPEN-QUESTION HANDLING (design §12 / risks): the integration guide documents
``potential_payout`` for a PENDING bet but does NOT explicitly document the settled
``payout`` field name. :func:`parse_verified_bet` parses defensively — it prefers
``payout``, falls back to ``potential_payout``, and leaves ``payout=None`` when
neither is present. ``record_settled`` treats an absent payout on a WON bet as a
verification failure (it raises rather than guessing).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, ConfigDict


def _safe_decimal(value: object) -> Decimal | None:
    """Convert a value to ``Decimal`` safely; return ``None`` for missing/garbage.

    Mirrors the polymarket ``_safe_decimal`` idea but returns ``None`` (not
    ``Decimal('0')``) on absence, so the caller can distinguish "no stake/payout
    supplied" (a verification failure) from a legitimate zero.
    """
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return None
    # Reject NaN / Infinity (WR-01): ``Decimal(str(float('nan')))`` yields
    # ``Decimal('NaN')`` without raising, and a non-finite stake/payout would slip
    # past the ``is None`` guards and corrupt the winnings math (``NaN > 0`` is False,
    # so a winner would be silently shorted). Returning ``None`` makes a non-finite
    # value the intended verification failure instead of a money bug.
    if not d.is_finite():
        return None
    return d


def _safe_uuid(value: object) -> UUID | None:
    """Parse a UUID from a string/UUID; return ``None`` for missing/garbage."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
# Router request/response models.
# --------------------------------------------------------------------------- #
class SessionResponse(BaseModel):
    """Response for ``POST /api/live/session`` — the minted live-bets session."""

    session_token: str
    expires_at: str


class TableItem(BaseModel):
    """One catalog table — only the fields the demo needs.

    ``extra="ignore"`` drops the many other live-bets table fields (mirrors the
    polymarket parser's dev-mode ``extra="ignore"``).
    """

    model_config = ConfigDict(extra="ignore")

    table_id: str
    name: str | None = None


class TablesResponse(BaseModel):
    """Response for ``GET /api/live/tables``."""

    tables: list[TableItem]


class MirrorResult(BaseModel):
    """Response for the placed/settled routes.

    ``applied=False`` signals the call was an idempotent no-op (the bet was already
    mirrored / already settled), so no ledger move was posted.
    """

    bet_id: str
    status: str
    applied: bool


# --------------------------------------------------------------------------- #
# Internal verified-bet parser (the live-bets GET /v2/bets/{id} shape).
# --------------------------------------------------------------------------- #
class VerifiedBet(BaseModel):
    """The server-side truth read from live-bets ``GET /v2/bets/{id}``.

    Money is ``Decimal``; ``payout`` is optional (see the defensive parse in
    :func:`parse_verified_bet`). ``stake`` is required — a bet with no parseable
    stake is a verification failure raised at parse time.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bet_id: UUID
    status: str
    stake: Decimal
    market_id: UUID | None = None
    table_id: UUID | None = None
    payout: Decimal | None = None


def parse_verified_bet(raw: dict[str, object]) -> VerifiedBet:
    """Parse the raw ``GET /v2/bets/{id}`` JSON into a typed :class:`VerifiedBet`.

    - ``bet_id`` and ``status`` are required.
    - ``stake`` is required and parsed as ``Decimal`` (never ``float``); a missing
      or unparseable stake raises ``ValueError`` — a verification failure, never a
      silent zero.
    - ``payout`` prefers the settled ``payout`` field, falls back to
      ``potential_payout``, and stays ``None`` when neither is present (the service
      decides whether that is fatal — it is, for a WON bet).
    """
    bet_id = _safe_uuid(raw.get("bet_id"))
    if bet_id is None:
        raise ValueError("live-bets bet response missing/invalid 'bet_id'")

    status = raw.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError("live-bets bet response missing 'status'")

    stake = _safe_decimal(raw.get("stake"))
    if stake is None:
        raise ValueError("live-bets bet response missing/invalid 'stake'")

    # Settled payout field name is not explicitly documented — prefer `payout`,
    # fall back to `potential_payout`, else leave None (fatal only for WON).
    payout_raw = raw.get("payout")
    if payout_raw is None:
        payout_raw = raw.get("potential_payout")
    payout = _safe_decimal(payout_raw)

    return VerifiedBet(
        bet_id=bet_id,
        status=status,
        stake=stake,
        market_id=_safe_uuid(raw.get("market_id")),
        table_id=_safe_uuid(raw.get("table_id")),
        payout=payout,
    )
