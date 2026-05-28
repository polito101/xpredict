"""AdminUserService — the admin CRM read/write service (Phase 8, Plan 08-01).

Static-method service mirroring ``MarketService`` (PATTERNS.md "service, CRUD").
Owns the user-list aggregation, the user-detail aggregation, the wallet/bet
history reads, and the ban/unban state machine.

Performance (RESEARCH Pitfall 4): ``list_users`` resolves each user's wallet
balance with a single LEFT JOIN to ``accounts`` — never a per-row balance query
(no N+1). ``last_activity`` is the user's most-recent bet timestamp, LEFT-JOINed
from a grouped subquery (NULL when the user has never bet).

Security (RESEARCH Pitfall 3 / T-08-03): the free-text ``search`` is passed to
SQL ``ILIKE``; ``%`` / ``_`` / ``\\`` in the user input are escaped via
``_escape_like`` before being wrapped in ``%...%`` so a search for ``50%`` does
not turn into a wildcard match.

Ban/unban (D-01..D-04): a user is banned when ``banned_at IS NOT NULL``. Ban sets
it to ``now(UTC)`` (409 if already banned); unban clears it (409 if already
active). Both write an ``admin.user_banned`` / ``admin.user_unbanned`` audit row
via ``AuditService.record`` and capture the plain values they return BEFORE the
caller's commit (MissingGreenlet prevention — PATTERNS.md).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, asc, desc, func, select

from app.auth.models import User
from app.bets.models import Bet
from app.core.audit.service import AuditService
from app.markets.models import Market, Outcome
from app.wallet.constants import KIND_USER_WALLET, OWNER_USER, PLAY_USD
from app.wallet.models import Account, Entry, Transfer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Whitelist of sortable columns (RESEARCH: never interpolate a raw sort column).
_SORTABLE: dict[str, Any] = {
    "created_at": User.created_at,
    "email": User.email,
    "display_name": User.display_name,
    "banned_at": User.banned_at,
}


def _escape_like(term: str) -> str:
    r"""Escape LIKE/ILIKE wildcards in user input (T-08-03 / Pitfall 3).

    Order matters: escape the backslash FIRST (it is the escape char itself),
    then ``%`` and ``_``. The caller wraps the result in ``%...%`` and passes
    ``escape="\\"`` to ``.ilike()`` so these become literal characters.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class AdminUserService:
    """Admin CRM service — user list/detail/history reads + ban/unban writes."""

    # ------------------------------------------------------------------ #
    # User list — paginated, searchable, filterable (D-05).
    # ------------------------------------------------------------------ #
    @staticmethod
    async def list_users(
        session: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: str | None = None,
        signup_after: datetime | None = None,
        signup_before: datetime | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of users + the total count (D-05).

        Each item is a dict with the user fields plus ``balance`` (the
        ``user_wallet`` balance via LEFT JOIN, defaulting to ``0``) and
        ``last_activity`` (the user's most-recent bet timestamp, or ``None``).
        """
        # Wallet-balance LEFT JOIN (no N+1): one account row per user.
        wallet = (
            select(Account.owner_id.label("uid"), Account.balance.label("balance"))
            .where(
                Account.owner_type == OWNER_USER,
                Account.kind == KIND_USER_WALLET,
                Account.currency == PLAY_USD,
            )
            .subquery()
        )
        # Last-activity LEFT JOIN: most-recent bet per user.
        last_bet = (
            select(
                Bet.user_id.label("uid"),
                func.max(Bet.created_at).label("last_activity"),
            )
            .group_by(Bet.user_id)
            .subquery()
        )

        base: Select[Any] = (
            select(
                User,
                func.coalesce(wallet.c.balance, 0).label("balance"),
                last_bet.c.last_activity.label("last_activity"),
            )
            .select_from(User)
            .outerjoin(wallet, wallet.c.uid == User.id)
            .outerjoin(last_bet, last_bet.c.uid == User.id)
        )

        base = AdminUserService._apply_user_filters(
            base,
            search=search,
            status=status,
            signup_after=signup_after,
            signup_before=signup_before,
        )

        # Count over the filtered set (subquery wraps the SELECT incl. joins).
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        # Whitelisted sort column + direction (defensive defaults).
        sort_col = _SORTABLE.get(sort_by, User.created_at)
        direction = asc if sort_order == "asc" else desc

        items_stmt = (
            base.order_by(direction(sort_col))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(items_stmt)).all()

        items = [
            AdminUserService._user_row_to_dict(
                user, balance=balance, last_activity=last_activity
            )
            for (user, balance, last_activity) in rows
        ]
        return items, int(total)

    @staticmethod
    def _apply_user_filters(
        stmt: Select[Any],
        *,
        search: str | None,
        status: str | None,
        signup_after: datetime | None,
        signup_before: datetime | None,
    ) -> Select[Any]:
        """Apply search / status / signup-date filters to the user SELECT."""
        if search:
            pattern = f"%{_escape_like(search)}%"
            # ``User.email`` / ``User.id`` come from the fastapi-users base table,
            # which mypy sees as plain ``str`` / ``UUID`` (not InstrumentedAttribute)
            # — same ``type: ignore`` convention as ``app/auth/manager.py``.
            stmt = stmt.where(
                User.email.ilike(pattern, escape="\\")  # type: ignore[attr-defined]
                | User.display_name.ilike(pattern, escape="\\")
            )
        if status == "banned":
            stmt = stmt.where(User.banned_at.is_not(None))
        elif status == "active":
            stmt = stmt.where(User.banned_at.is_(None))
        if signup_after is not None:
            stmt = stmt.where(User.created_at >= signup_after)
        if signup_before is not None:
            stmt = stmt.where(User.created_at <= signup_before)
        return stmt

    @staticmethod
    def _user_row_to_dict(
        user: User, *, balance: Any, last_activity: datetime | None
    ) -> dict[str, Any]:
        """Flatten a ``(User, balance, last_activity)`` row into a plain dict."""
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "banned_at": user.banned_at,
            "created_at": user.created_at,
            "last_activity": last_activity,
            "balance": balance,
            "is_verified": user.is_verified,
        }

    # ------------------------------------------------------------------ #
    # User detail — profile + balance + counts (D-07).
    # ------------------------------------------------------------------ #
    @staticmethod
    async def get_user_detail(
        session: AsyncSession, user_id: UUID
    ) -> dict[str, Any] | None:
        """Return the user's profile + balance + transaction/bet counts, or None."""
        user = (
            await session.execute(
                select(User).where(User.id == user_id)  # type: ignore[arg-type]
            )
        ).scalar_one_or_none()
        if user is None:
            return None

        # Resolve the user's wallet id (may be absent — defensive default 0/0).
        wallet_id = (
            await session.execute(
                select(Account.id).where(
                    Account.owner_type == OWNER_USER,
                    Account.owner_id == user_id,
                    Account.kind == KIND_USER_WALLET,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one_or_none()

        balance: Any = 0
        transaction_count = 0
        if wallet_id is not None:
            balance = (
                await session.execute(
                    select(Account.balance).where(Account.id == wallet_id)
                )
            ).scalar_one()
            transaction_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Entry)
                    .where(Entry.account_id == wallet_id)
                )
            ).scalar_one()

        bet_count = (
            await session.execute(
                select(func.count()).select_from(Bet).where(Bet.user_id == user_id)
            )
        ).scalar_one()

        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "banned_at": user.banned_at,
            "created_at": user.created_at,
            "last_activity": None,
            "balance": balance,
            "is_verified": user.is_verified,
            "email_verified_at": None,
            "transaction_count": int(transaction_count),
            "bet_count": int(bet_count),
        }

    # ------------------------------------------------------------------ #
    # User transactions — paginated wallet history (admin view).
    # ------------------------------------------------------------------ #
    @staticmethod
    async def get_user_transactions(
        session: AsyncSession,
        user_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of ``user_id``'s wallet entries + total (newest first)."""
        wallet_id = (
            await session.execute(
                select(Account.id).where(
                    Account.owner_type == OWNER_USER,
                    Account.owner_id == user_id,
                    Account.kind == KIND_USER_WALLET,
                    Account.currency == PLAY_USD,
                )
            )
        ).scalar_one_or_none()
        if wallet_id is None:
            return [], 0

        total = (
            await session.execute(
                select(func.count()).select_from(Entry).where(Entry.account_id == wallet_id)
            )
        ).scalar_one()

        rows = (
            await session.execute(
                select(
                    Entry.id.label("id"),
                    Transfer.kind.label("kind"),
                    Entry.amount.label("amount"),
                    Entry.created_at.label("created_at"),
                    Transfer.transfer_metadata.label("metadata"),
                )
                .join(Transfer, Entry.transfer_id == Transfer.id)
                .where(Entry.account_id == wallet_id)
                .order_by(Entry.created_at.desc(), Entry.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()

        items = [
            {
                "id": row.id,
                "kind": row.kind,
                "amount": row.amount,
                "created_at": row.created_at,
                "reason": (row.metadata or {}).get("reason"),
            }
            for row in rows
        ]
        return items, int(total)

    # ------------------------------------------------------------------ #
    # User bets — paginated bets list (admin view).
    # ------------------------------------------------------------------ #
    @staticmethod
    async def get_user_bets(
        session: AsyncSession,
        user_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of ``user_id``'s bets + total (newest first).

        ``market_question`` / ``outcome_label`` are LEFT-JOINed (the bet stores
        plain UUIDs). ``pnl`` is the realized P&L for a settled bet, ``None``
        while pending.
        """
        total = (
            await session.execute(
                select(func.count()).select_from(Bet).where(Bet.user_id == user_id)
            )
        ).scalar_one()

        rows = (
            await session.execute(
                select(
                    Bet.id.label("id"),
                    Market.question.label("market_question"),
                    Outcome.label.label("outcome_label"),
                    Bet.stake.label("stake"),
                    Bet.status.label("status"),
                    Bet.odds_at_placement.label("odds_at_placement"),
                    Bet.created_at.label("created_at"),
                )
                .select_from(Bet)
                .outerjoin(Market, Market.id == Bet.market_id)
                .outerjoin(Outcome, Outcome.id == Bet.outcome_id)
                .where(Bet.user_id == user_id)
                .order_by(Bet.created_at.desc(), Bet.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()

        # Local import avoids a circular import at module load (settlement -> bets).
        from decimal import Decimal

        from app.bets.constants import BET_PENDING, BET_SETTLED_WON
        from app.settlement.payout import compute_payout, profit_or_loss, quantize_money

        items: list[dict[str, Any]] = []
        for row in rows:
            pnl: Any = None
            if row.status != BET_PENDING:
                # Realized P&L mirrors the portfolio read (app/bets/portfolio.py):
                # a winner's payout is stake / odds, a loser's payout is 0.
                won = row.status == BET_SETTLED_WON
                payout = (
                    compute_payout(row.stake, row.odds_at_placement)
                    if won
                    else quantize_money(Decimal("0"))
                )
                pnl = profit_or_loss(row.stake, payout)
            items.append(
                {
                    "id": row.id,
                    "market_question": row.market_question or "(unknown market)",
                    "outcome_label": row.outcome_label or "(unknown outcome)",
                    "stake": row.stake,
                    "status": row.status,
                    "pnl": pnl,
                    "created_at": row.created_at,
                }
            )
        return items, int(total)

    # ------------------------------------------------------------------ #
    # Ban / unban state machine (D-01..D-04).
    # ------------------------------------------------------------------ #
    @staticmethod
    async def ban_user(
        session: AsyncSession,
        user_id: UUID,
        *,
        reason: str,
        admin: User,
        ip: str | None = None,
    ) -> User:
        """Set ``banned_at = now(UTC)`` (409 if already banned) + audit (D-04).

        Frozen-balance semantics (D-03): the wallet balance is NEVER touched here
        — only the ``banned_at`` flag flips. Enforcement of the freeze lives at
        the login / bet / recharge paths.
        """
        user = await AdminUserService._load_user_or_404(session, user_id)
        if user.banned_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="User is already banned"
            )

        user.banned_at = datetime.now(UTC)
        # Capture the admin id as a plain value BEFORE flush/commit churn
        # (MissingGreenlet prevention — PATTERNS.md).
        admin_id = admin.id
        await session.flush()
        await AuditService.record(
            session,
            actor=f"user:{admin_id}",
            event_type="admin.user_banned",
            payload={"target_user_id": str(user_id), "reason": reason},
            ip=ip,
        )
        return user

    @staticmethod
    async def unban_user(
        session: AsyncSession,
        user_id: UUID,
        *,
        reason: str | None,
        admin: User,
        ip: str | None = None,
    ) -> User:
        """Clear ``banned_at`` (409 if already active) + audit (D-04).

        Frozen-balance semantics (D-03): the balance persists exactly as-is across
        the ban -> unban cycle — this method only clears the flag.
        """
        user = await AdminUserService._load_user_or_404(session, user_id)
        if user.banned_at is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is not banned")

        user.banned_at = None
        admin_id = admin.id
        await session.flush()
        await AuditService.record(
            session,
            actor=f"user:{admin_id}",
            event_type="admin.user_unbanned",
            payload={"target_user_id": str(user_id), "reason": reason},
            ip=ip,
        )
        return user

    @staticmethod
    async def _load_user_or_404(session: AsyncSession, user_id: UUID) -> User:
        user = (
            await session.execute(
                select(User).where(User.id == user_id)  # type: ignore[arg-type]
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
