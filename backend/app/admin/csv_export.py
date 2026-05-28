"""CSV export utilities for the admin CRM (Phase 8, Plan 08-02, ADU-06).

Pure, app-independent helpers: a formula-injection sanitizer and three CSV
builder functions (users / transactions / bets). The HTTP layer lives in
``app/admin/export_router.py`` — this module only turns rows of dicts into a
CSV string, so it is trivially unit-testable without a FastAPI app or a DB.

Design choices (CONTEXT D-08..D-10):

- **Batch, not streaming (D-10).** Each builder loads all filtered rows and
  writes the whole CSV in memory with ``csv.DictWriter`` + ``io.StringIO``. For
  v1 user counts (<10k) streaming is unnecessary complexity; if it ever matters
  the endpoint contract (``text/csv`` attachment) stays the same and only the
  builder swaps to a row-by-row ``StreamingResponse`` yield.
- **Formula-injection protection (D-09 / T-08-05).** Every cell is passed
  through :func:`sanitize_csv_cell`, which prefixes a single quote ``'`` to any
  value beginning with a formula-trigger character (``= + - @`` TAB CR). This
  is the OWASP-recommended mitigation so a malicious ``=cmd|'/c ...'`` cell can
  never auto-execute when the export is opened in Excel / Google Sheets.
- **Money as plain strings (D-09).** Decimal amounts/balances/stakes are
  rendered with ``str(Decimal)`` — no currency symbol, no float — matching the
  ``MoneyStr`` JSON contract used everywhere else.
- **Timestamps in ISO 8601 UTC (D-09).** :func:`_iso_utc` normalises naive
  datetimes to UTC and emits ``.isoformat()``.
- **DoS cap (T-08-09 / RESEARCH Pitfall 5).** ``MAX_EXPORT_ROWS = 10000``; a
  builder given more rows truncates to the cap and logs a structlog warning.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# D-09 / T-08-05: a cell whose first character is one of these is a spreadsheet
# formula trigger and must be defused with a leading single quote.
FORMULA_TRIGGERS: frozenset[str] = frozenset({"=", "+", "-", "@", "\t", "\r"})

# T-08-09 / RESEARCH Pitfall 5: never build an unbounded CSV in memory.
MAX_EXPORT_ROWS = 10000

# Column orders (Claude's discretion per CONTEXT) — header == dict key.
USERS_COLUMNS = ["email", "display_name", "status", "signup_date", "last_activity", "balance"]
TRANSACTIONS_COLUMNS = ["id", "user_email", "kind", "amount", "reason", "created_at"]
BETS_COLUMNS = [
    "id",
    "user_email",
    "market_question",
    "outcome",
    "stake",
    "status",
    "pnl",
    "created_at",
]


def sanitize_csv_cell(value: str) -> str:
    """Defuse spreadsheet formula injection (D-09 / T-08-05).

    Prefix a single quote ``'`` to any value whose first character is a
    formula-trigger (``= + - @`` TAB CR) so Excel / Google Sheets treats the
    cell as literal text rather than evaluating it. Empty strings and values
    starting with any other character pass through unchanged.

    >>> sanitize_csv_cell("=SUM(A1:A2)")
    "'=SUM(A1:A2)"
    >>> sanitize_csv_cell("normal text")
    'normal text'
    >>> sanitize_csv_cell("")
    ''
    """
    if value and value[0] in FORMULA_TRIGGERS:
        return "'" + value
    return value


def _iso_utc(value: datetime | None) -> str:
    """Render a datetime as ISO 8601 UTC (D-09). ``None`` -> empty string.

    A naive datetime is assumed to be UTC (the whole stack stores
    ``TIMESTAMPTZ`` and serializes UTC); an aware datetime is converted to UTC.
    """
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _money(value: Any) -> str:
    """Render a money value as a plain string (D-09). ``None`` -> empty string.

    No currency symbol, no float — ``str(Decimal)`` exactly like ``MoneyStr``.
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    # Coerce ints/strings defensively to a canonical Decimal string.
    return str(Decimal(str(value)))


def _cell(value: Any) -> str:
    """Stringify + sanitize an arbitrary cell value for CSV output."""
    if value is None:
        return ""
    return sanitize_csv_cell(value if isinstance(value, str) else str(value))


def _cap_rows(rows: list[dict[str, Any]], *, kind: str) -> list[dict[str, Any]]:
    """Truncate ``rows`` to ``MAX_EXPORT_ROWS`` (T-08-09), logging if it bites."""
    if len(rows) > MAX_EXPORT_ROWS:
        log.warning(
            "csv_export.truncated",
            kind=kind,
            requested=len(rows),
            cap=MAX_EXPORT_ROWS,
        )
        return rows[:MAX_EXPORT_ROWS]
    return rows


def _write_csv(columns: list[str], records: list[dict[str, str]]) -> str:
    r"""Write ``records`` (already-stringified cells) to a CSV string.

    Uses ``csv.DictWriter`` so quoting/escaping of commas, quotes and embedded
    newlines is handled by the stdlib. ``\r\n`` line terminator is the CSV
    (RFC 4180) standard; ``newline=""`` on the buffer prevents the double-CR
    that ``StringIO`` + the default terminator would otherwise produce.
    """
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()


def build_users_csv(rows: list[dict[str, Any]]) -> str:
    """Build the users CSV (D-08/D-09).

    Columns: ``email, display_name, status, signup_date, last_activity,
    balance``. Each ``row`` is the admin user-list dict (``email``,
    ``display_name``, ``banned_at``, ``created_at``, ``last_activity``,
    ``balance``); ``status`` is derived from ``banned_at`` (D-01), money is a
    plain string, timestamps are ISO 8601 UTC, and every cell is sanitized.
    """
    capped = _cap_rows(rows, kind="users")
    records: list[dict[str, str]] = []
    for row in capped:
        status = "banned" if row.get("banned_at") is not None else "active"
        records.append(
            {
                "email": _cell(row.get("email")),
                "display_name": _cell(row.get("display_name")),
                "status": _cell(status),
                "signup_date": _cell(_iso_utc(row.get("created_at"))),
                "last_activity": _cell(_iso_utc(row.get("last_activity"))),
                "balance": _cell(_money(row.get("balance"))),
            }
        )
    return _write_csv(USERS_COLUMNS, records)


def build_transactions_csv(rows: list[dict[str, Any]]) -> str:
    """Build the transactions CSV (D-08/D-09).

    Columns: ``id, user_email, kind, amount, reason, created_at``. ``amount``
    is a plain Decimal string, ``created_at`` is ISO 8601 UTC, every cell is
    sanitized.
    """
    capped = _cap_rows(rows, kind="transactions")
    records: list[dict[str, str]] = []
    for row in capped:
        records.append(
            {
                "id": _cell(row.get("id")),
                "user_email": _cell(row.get("user_email")),
                "kind": _cell(row.get("kind")),
                "amount": _cell(_money(row.get("amount"))),
                "reason": _cell(row.get("reason")),
                "created_at": _cell(_iso_utc(row.get("created_at"))),
            }
        )
    return _write_csv(TRANSACTIONS_COLUMNS, records)


def build_bets_csv(rows: list[dict[str, Any]]) -> str:
    """Build the bets CSV (D-08/D-09).

    Columns: ``id, user_email, market_question, outcome, stake, status, pnl,
    created_at``. ``stake`` / ``pnl`` are plain Decimal strings (``pnl`` empty
    while pending), ``created_at`` is ISO 8601 UTC, every cell is sanitized.
    """
    capped = _cap_rows(rows, kind="bets")
    records: list[dict[str, str]] = []
    for row in capped:
        records.append(
            {
                "id": _cell(row.get("id")),
                "user_email": _cell(row.get("user_email")),
                "market_question": _cell(row.get("market_question")),
                "outcome": _cell(row.get("outcome")),
                "stake": _cell(_money(row.get("stake"))),
                "status": _cell(row.get("status")),
                "pnl": _cell(_money(row.get("pnl"))),
                "created_at": _cell(_iso_utc(row.get("created_at"))),
            }
        )
    return _write_csv(BETS_COLUMNS, records)


__all__ = [
    "FORMULA_TRIGGERS",
    "MAX_EXPORT_ROWS",
    "build_bets_csv",
    "build_transactions_csv",
    "build_users_csv",
    "sanitize_csv_cell",
]
