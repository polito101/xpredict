"""Pydantic v2 schemas for the live-bets bridge (v1.3, LB-A).

Two groups:
  - ROUTER response/request models (``SessionResponse``, ``TableItem`` /
    ``TablesResponse``, ``MirrorResult``) — the shapes the ``/api/live/*`` routes
    expose, NOT the raw live-bets payloads.
  - A small internal parser (``VerifiedBet`` + :func:`parse_verified_bet`) for the
    live-bets ``GET /v2/bets/{id}`` response, so the service has ONE typed object to
    reason about. All monetary values are ``Decimal`` (never ``float``), parsed via
    ``_safe_decimal`` exactly like the polymarket parser.

REAL BetView CONTRACT (``live-bets/live_bets/api/routes/bets.py`` ``BetView``):
``{id, round_id, market_id, selection, stake(str), locked_odds(str), status,
payout(str|None), placed_at, settled_at}``. The bet id field is ``id`` (NOT
``bet_id``); there is NO ``table_id`` in BetView (the mirror row keeps the
``table_id`` captured at placement / ``None``). ``payout`` is always present as a key
(``str`` when settled, ``None`` while pending); :func:`parse_verified_bet` reads it as
``str|None`` and leaves ``payout=None`` when absent — ``record_settled`` treats an
absent payout on a WON bet as a verification failure (it raises rather than guessing).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    """Response for ``POST /api/live/session`` — the minted live-bets session.

    ``table_id`` echoes the table the session was minted for (the request's
    ``body.table_id`` or ``settings.LIVEBETS_DEFAULT_TABLE_ID``). The frontend uses
    it for the widget's ``table-id`` attribute: the live-bets ``GET /tables`` route
    is JWT-gated (player session), so XPredict's operator-key ``/api/live/tables``
    cannot list tables — returning the resolved id here is the demo's source of the
    table id.
    """

    session_token: str
    expires_at: str
    table_id: str


class TableItem(BaseModel):
    """One catalog table — only the fields the demo needs.

    Parses the REAL live-bets ``TableView`` (``GET /tables`` →
    ``TableListResponse.tables[]``), whose id field is ``id`` (NOT ``table_id``):
    the ``id`` alias maps live-bets ``id`` onto our outward ``table_id`` so the
    ``/api/live/tables`` response keeps returning ``{tables:[{table_id, name}]}`` to
    the frontend. ``name`` is mapped through unchanged. ``extra="ignore"`` drops the
    other ``TableView`` fields (``source_id``, ``status``, the ``*_duration_seconds``)
    — mirrors the polymarket parser's dev-mode ``extra="ignore"``.

    ``populate_by_name=True`` keeps the field tolerant of an already-mapped
    ``table_id`` key too (so the bridge/router can construct it either way).
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    table_id: str = Field(validation_alias="id")
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
    stake is a verification failure raised at parse time. ``bet_id`` holds the
    BetView ``id`` (the field name is internal — the service never compares it).
    ``table_id`` is always ``None`` (BetView has no ``table_id``); it is retained so
    the placement path can still carry the table id captured elsewhere.
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

    Matches the REAL live-bets ``BetView`` shape:
    - The bet id is read from ``id`` (NOT ``bet_id``); a missing/invalid ``id``
      raises ``ValueError``. (Stored on ``VerifiedBet.bet_id`` — the service
      cross-checks nothing against it, so the field name is internal.)
    - ``status`` is required.
    - ``stake`` is required and parsed as ``Decimal`` (never ``float``); a missing
      or unparseable stake raises ``ValueError`` — a verification failure, never a
      silent zero.
    - ``market_id`` is parsed when present.
    - ``payout`` is the settled ``payout`` field (``str|None`` in BetView), parsed to
      ``Decimal`` and left ``None`` when absent (the service decides whether that is
      fatal — it is, for a WON bet).
    - ``table_id`` is deliberately NOT read: BetView has no ``table_id`` field, so it
      stays ``None`` here (the mirror row keeps the ``table_id`` captured at placement).
    """
    bet_id = _safe_uuid(raw.get("id"))
    if bet_id is None:
        raise ValueError("live-bets bet response missing/invalid 'id'")

    status = raw.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError("live-bets bet response missing 'status'")

    stake = _safe_decimal(raw.get("stake"))
    if stake is None:
        raise ValueError("live-bets bet response missing/invalid 'stake'")

    # Real BetView exposes the settled amount as `payout` (str|None) — no
    # `potential_payout`. None while pending => the service treats a WON bet with no
    # payout as a verification failure (it will not guess winnings).
    payout = _safe_decimal(raw.get("payout"))

    return VerifiedBet(
        bet_id=bet_id,
        status=status,
        stake=stake,
        market_id=_safe_uuid(raw.get("market_id")),
        table_id=None,  # BetView has no table_id; mirror keeps the placement value.
        payout=payout,
    )
