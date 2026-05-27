"""Wallet/ledger domain exceptions (Phase 3).

Plain exceptions mirroring the lightweight style used elsewhere — routers map
them to HTTP status codes later (Plan 03-04 / 03-05). Keeping them transport-
agnostic means the service layer stays framework-free.
"""

from __future__ import annotations


class InsufficientBalance(Exception):
    """Raised when a debit would take an account below zero (WAL-08).

    The ``CHECK (balance >= 0)`` constraint is the DB-level last line of
    defense; the service raises this *before* hitting the DB so callers get a
    domain error rather than a raw ``DBAPIError`` (sqlstate 23514).
    """


class UserToUserTransferForbidden(Exception):
    """Raised if any code path attempts to move value user -> user (SC#5, WAL-09).

    The regulatory firewall: a user wallet may only transact against a
    system/house account, never another user's wallet. There is no schema FK
    and no API parameter that permits a user->user move; this exception guards
    the service layer as belt-and-suspenders against a future regression.
    """
