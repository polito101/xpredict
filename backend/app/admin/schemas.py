"""Admin CRM Pydantic schemas (Phase 8, Plan 08-01).

Reuses the established Phase 4/3 contracts rather than duplicating them:

- ``PaginatedResponse`` / ``paginated_response`` come from ``app.markets.schemas``
  (the offset-limit pagination envelope every list endpoint in the project uses).
- ``MoneyStr`` comes from ``app.wallet.schemas`` — the money-as-JSON-string
  contract (SC#4 discipline): every Decimal balance / amount / stake / pnl field
  serializes to a string, never a float.

D-01: a user is *banned* when ``banned_at IS NOT NULL``; the nullable timestamp
doubles as the state flag and the audit trail of when the ban happened. The
``status`` computed property exposes that as ``"active"`` / ``"banned"`` for the
table UI without a separate enum column.

D-04: ``BanRequest.reason`` is mandatory (``min_length=1``); ``UnbanRequest.reason``
is optional. Both are ``extra="forbid"`` so a stray field is a hard 422 — the
same firewall discipline as ``RechargeRequest``.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

# Reuse the project's pagination envelope + money-string contract — do NOT
# duplicate (PATTERNS.md "Pagination" / "Money Serialization").
from app.markets.schemas import PaginatedResponse, paginated_response
from app.wallet.schemas import MoneyStr

__all__ = [
    "BanRequest",
    "PaginatedResponse",
    "UnbanRequest",
    "UserBetItem",
    "UserDetail",
    "UserListItem",
    "UserTransactionItem",
    "paginated_response",
]


class UserListItem(BaseModel):
    """One row of the admin user list (D-05).

    Built from a ``(User, balance)`` projection — ``balance`` is the user's
    ``user_wallet`` account balance fetched via a LEFT JOIN (no N+1), defaulting
    to ``0`` when the user somehow has no wallet (registration guarantees one).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None = None
    banned_at: datetime | None = None
    created_at: datetime
    last_activity: datetime | None = None
    balance: MoneyStr

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        """``"banned"`` when ``banned_at`` is set, else ``"active"`` (D-01)."""
        return "banned" if self.banned_at is not None else "active"


class UserDetail(UserListItem):
    """Full user detail (D-07) — list fields + verification + aggregate counts.

    ``transaction_count`` is the number of ledger entries against the user's
    wallet; ``bet_count`` is the number of bets the user has placed.
    """

    is_verified: bool = False
    email_verified_at: datetime | None = None
    transaction_count: int = 0
    bet_count: int = 0


class BanRequest(BaseModel):
    """Body for ``POST /admin/users/{user_id}/ban`` (D-04).

    ``reason`` is mandatory — the admin must justify a ban (it lands in the
    ``admin.user_banned`` audit payload). ``extra="forbid"`` rejects any stray
    field with a 422.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, description="Mandatory audit reason for the ban.")


class UnbanRequest(BaseModel):
    """Body for ``POST /admin/users/{user_id}/unban`` (D-04).

    ``reason`` is OPTIONAL on unban (it still lands in the
    ``admin.user_unbanned`` audit payload when supplied). ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, description="Optional audit reason for the unban.")


class UserTransactionItem(BaseModel):
    """One row of a user's wallet history (admin view).

    Derived from an ``entries`` leg joined to its parent ``transfer``: ``kind``
    from ``transfer.kind``, ``amount`` the entry amount (JSON string), ``reason``
    from ``transfer.transfer_metadata->>'reason'`` (may be NULL).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    amount: MoneyStr
    created_at: datetime
    reason: str | None = None


class UserBetItem(BaseModel):
    """One row of a user's bets (admin view).

    ``market_question`` / ``outcome_label`` are LEFT-JOINed from the markets /
    outcomes tables (the bet stores plain UUIDs; the FK is added by integration
    migration 0005). ``pnl`` is the realized P&L for a settled bet (winner
    positive, loser ``-stake``) and ``None`` while the bet is still pending.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_question: str
    outcome_label: str
    stake: MoneyStr
    status: str
    pnl: MoneyStr | None = None
    created_at: datetime
