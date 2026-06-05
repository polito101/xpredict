"""GammaMarket Pydantic v2 parser — spike-002-validated state machine.

Parses raw JSON from the Gamma API (gamma-api.polymarket.com) into
typed, validated Python objects. Key design decisions:

- Stringified JSON fields (outcomes, outcomePrices, clobTokenIds) are
  decoded via a field_validator in ``mode="before"``.
- All monetary amounts are Decimal (never float) — parsed from string
  fields (volume, liquidity), never from float variants (volumeNum).
- The _derive_status state machine maps Gamma closed/UMA state to our
  MarketStatus enum. CRITICAL: closed=true alone NEVER maps to RESOLVED.
- model_config.extra = "forbid" in dev (catches injected fields early),
  "allow" in prod (API has 50+ fields and adds new ones without notice).
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.markets.enums import MarketStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.config import CategoryEntry

log = structlog.get_logger()


def _gamma_model_config() -> ConfigDict:
    """Build ConfigDict based on ENVIRONMENT — ignore extras in dev, allow in prod.

    Dev mode uses ``extra="ignore"`` (silently drops unknown fields) rather than
    ``"forbid"`` because VCR fixtures and real API responses contain 50+ fields
    not modelled here.  Prod uses ``"allow"`` to preserve full API payload for
    debugging/logging without raising.  Both modes satisfy T-06-01: injected
    fields never reach business logic.
    """
    try:
        from app.core.config import get_settings

        is_dev = get_settings().is_dev
    except Exception:
        # During test collection or when env vars aren't set, default to
        # stricter mode (ignore) — unknown environments should not silently
        # propagate unexpected API fields into business logic.
        is_dev = True
    extra_mode: str = "ignore" if is_dev else "allow"
    return ConfigDict(extra=extra_mode, populate_by_name=True)  # type: ignore[typeddict-item]


def _safe_decimal(value: object) -> Decimal:
    """Convert any value to Decimal safely — fallback to Decimal('0')."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _derive_status(
    closed: bool,
    uma_status: str | None,
    outcome_prices: list[str],
) -> MarketStatus:
    """State machine mapping Gamma API state to MarketStatus.

    Truth table (spike-002 validated):
      closed=false, uma=None        -> OPEN
      closed=false, uma=proposed     -> OPEN  (still trading)
      closed=false, uma=disputed     -> OPEN  (still trading)
      closed=false, uma=resolved     -> RESOLVED
      closed=true,  uma=resolved + clear winner -> RESOLVED
      closed=true,  uma=resolved + NO winner    -> CLOSED
      closed=true,  uma=proposed     -> CLOSED (NOT resolved!)
      closed=true,  uma=disputed     -> CLOSED
      closed=true,  uma=None         -> CLOSED

    CRITICAL: closed=true + uma=proposed MUST map to CLOSED, never RESOLVED.
    Settling on proposed status would pay out based on unconfirmed resolution.
    """
    if not closed and uma_status is None:
        return MarketStatus.OPEN
    if not closed and uma_status == "proposed":
        return MarketStatus.OPEN
    if not closed and uma_status == "disputed":
        return MarketStatus.OPEN
    if not closed and uma_status == "resolved":
        return MarketStatus.RESOLVED
    if closed and uma_status == "resolved":
        has_winner = any(p in ("0", "1", "0.0", "1.0") for p in outcome_prices)
        if has_winner:
            return MarketStatus.RESOLVED
        return MarketStatus.CLOSED
    if closed and uma_status in ("proposed", "disputed", None):
        return MarketStatus.CLOSED
    # Fallback — should not be reached with valid Gamma data.
    return MarketStatus.OPEN


class GammaMarket(BaseModel):
    """Pydantic v2 model for a single Gamma API market response."""

    model_config = _gamma_model_config()

    id: str
    question: str
    slug: str = ""
    condition_id: str = Field(alias="conditionId", default="")
    outcomes_raw: list[str] = Field(alias="outcomes", default_factory=list)
    outcome_prices_raw: list[str] = Field(alias="outcomePrices", default_factory=list)
    clob_token_ids: list[str] = Field(alias="clobTokenIds", default_factory=list)
    volume_str: str = Field(alias="volume", default="0")
    liquidity_str: str = Field(alias="liquidity", default="0")
    volume_24hr: float | None = Field(alias="volume24hr", default=None)
    closed: bool = False
    uma_resolution_status: str | None = Field(
        alias="umaResolutionStatus",
        default=None,
    )
    end_date_raw: str | None = Field(alias="endDate", default=None)
    description: str = ""

    # Internal state — set by model_validator
    internal_status: MarketStatus = MarketStatus.OPEN

    @field_validator(
        "outcomes_raw",
        "outcome_prices_raw",
        "clob_token_ids",
        mode="before",
    )
    @classmethod
    def parse_stringified_json_list(cls, v: object) -> list[str]:
        """Handle both stringified JSON and pre-parsed lists from API."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return []
        return []

    @model_validator(mode="after")
    def set_internal_status(self) -> GammaMarket:
        """Derive and store internal_status from closed + UMA state."""
        self.internal_status = _derive_status(
            self.closed,
            self.uma_resolution_status,
            self.outcome_prices_raw,
        )
        return self

    @property
    def volume(self) -> Decimal:
        """Total volume as Decimal — never float."""
        return _safe_decimal(self.volume_str)

    @property
    def liquidity(self) -> Decimal:
        """Liquidity as Decimal — never float."""
        return _safe_decimal(self.liquidity_str)

    @property
    def volume_24hr_decimal(self) -> Decimal:
        """24h volume as Decimal — never float."""
        if self.volume_24hr is None:
            return Decimal("0")
        return _safe_decimal(self.volume_24hr)


class GammaEventMarket(GammaMarket):
    """A nested ``/events`` child market — ``GammaMarket`` plus the per-outcome label.

    Inherits the spike-002 stringified-JSON validators, ``_derive_status`` truth
    table, Decimal discipline, and the env-based ``extra`` policy VERBATIM. The
    only addition is ``groupItemTitle``, the per-outcome display label used to
    stamp ``Market.group_item_title`` (e.g. "64,000" on a Bitcoin-ladder child).
    It is ``""`` on single-market events (EVT-07 standalone path).
    """

    group_item_title: str = Field(alias="groupItemTitle", default="")


class GammaTag(BaseModel):
    """Pydantic v2 model for one Gamma ``tags[]`` element on an event.

    Only the fields the curated sync needs (``id`` drives category resolution;
    ``label``/``slug`` are kept for drift logging). The env-based ``extra`` policy
    swallows the rest of Gamma's tag fields (``forceShow`` etc.).
    """

    model_config = _gamma_model_config()

    id: str
    label: str = ""
    slug: str = ""


class GammaEvent(BaseModel):
    """Pydantic v2 model for one Gamma ``/events`` array element.

    CRITICAL DIVERGENCE FROM ``GammaMarket`` (Pitfall 1): event-level
    ``volume``/``volume24hr`` are raw FLOATS in ``/events`` (not stringified
    JSON), so they are typed ``float | None`` and converted via ``_safe_decimal``
    in the ``*_decimal`` properties. The stringified-JSON list validator is NOT
    applied here — it stays on the nested children (``GammaEventMarket``).
    """

    model_config = _gamma_model_config()

    id: str
    slug: str = ""
    title: str = ""
    description: str = ""
    closed: bool = False
    end_date_raw: str | None = Field(alias="endDate", default=None)
    # ⚠️ event-level volume is FLOAT (not stringified) — NO list validator here.
    volume_24hr: float | None = Field(alias="volume24hr", default=None)
    volume_total: float | None = Field(alias="volume", default=None)
    markets: list[GammaEventMarket] = Field(default_factory=list)
    tags: list[GammaTag] = Field(default_factory=list)

    @property
    def volume_24hr_decimal(self) -> Decimal:
        """Event 24h volume as Decimal — converts the raw float safely."""
        return _safe_decimal(self.volume_24hr)

    @property
    def volume_total_decimal(self) -> Decimal:
        """Event total volume as Decimal — converts the raw float safely."""
        return _safe_decimal(self.volume_total)


def resolve_category(
    event: GammaEvent,
    allow_list: Sequence[CategoryEntry],
) -> str | None:
    """Return the human-readable category for an event (first-by-priority, CAT-03).

    ``allow_list`` is the priority-ordered ``POLYMARKET_CATEGORIES`` constant. The
    FIRST allow-listed tag whose ``tag_id`` appears on the event wins, so a
    dual-tagged event (e.g. World + Politics) resolves to the higher-priority
    category (Politics). Returns ``None`` when the event carries no allow-listed
    tag (caller skips it).

    Tags present on the event but absent from every allow-list entry are logged
    via ``gamma.unmapped_tag`` for drift visibility — they are NEVER auto-added
    to the allow-list (CAT-03: "logged, never auto-added").
    """
    tag_ids = {t.id for t in event.tags}
    allow_listed_ids = {entry.tag_id for entry in allow_list}

    resolved: str | None = None
    for entry in allow_list:  # allow_list is priority-ordered
        if entry.tag_id in tag_ids:
            resolved = entry.name
            break

    # Drift logging: surface every event tag not in any allow-list entry.
    for tag in event.tags:
        if tag.id not in allow_listed_ids:
            log.warning(
                "gamma.unmapped_tag",
                event_id=event.id,
                tag_id=tag.id,
                label=tag.label,
            )

    return resolved
