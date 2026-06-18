"""Critical #1 (audit) — the Argon2id KDF must run OFF the asyncio event loop.

The password KDF costs ~65-73 ms of blocking CPU + a 64 MiB transient allocation per
call. It ran synchronously *inside* the async login / register / demo-login coroutines,
so every hash/verify froze the worker's single event-loop thread — stalling healthz,
catalog reads, bet placement and WS heartbeats, and collapsing login throughput under a
burst. These tests pin the fix: ``hash`` / ``verify_and_update`` execute in a worker
thread (``anyio.to_thread``), never the loop thread.

Pure unit tests — no DB, no SMTP. A recording ``PasswordHelperProtocol`` stub captures the
thread each KDF call ran on; the assertion is simply "not the event-loop thread".
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.auth.manager import UserManager

pytestmark = pytest.mark.unit


class _RecordingPasswordHelper:
    """A ``PasswordHelperProtocol`` stub that records the thread each KDF call ran on.

    The real helper does ~70 ms of blocking work here; the stub returns instantly so the
    test stays fast, but it still proves *where* (which thread) the call was dispatched.
    """

    def __init__(self) -> None:
        self.hash_thread: int | None = None
        self.verify_thread: int | None = None

    def hash(self, password: str) -> str:
        self.hash_thread = threading.get_ident()
        return f"hashed:{password}"

    def verify_and_update(self, password: str, hashed: str) -> tuple[bool, str | None]:
        self.verify_thread = threading.get_ident()
        return True, None

    def verify(self, password: str, hashed: str) -> bool:  # protocol completeness
        return True


class _FakeUserDB:
    """Minimal user_db: ``get_by_email`` returns the seeded user (or ``None``)."""

    def __init__(self, user: object | None) -> None:
        self._user = user
        self.updated: dict | None = None

    async def get_by_email(self, email: str) -> object | None:
        return self._user

    async def update(self, user: object, update_dict: dict) -> object:
        self.updated = update_dict
        return user


def _manager(user: object | None, helper: _RecordingPasswordHelper) -> UserManager:
    # email_service stubbed (SimpleNamespace) so no EmailService/SMTP build in a unit test.
    return UserManager(_FakeUserDB(user), helper, email_service=SimpleNamespace())


async def test_authenticate_verifies_off_event_loop() -> None:
    """A known-email login runs ``verify_and_update`` in a worker thread, not the loop."""
    loop_thread = threading.get_ident()
    user = SimpleNamespace(id=uuid4(), email="p@example.com", hashed_password="x")
    helper = _RecordingPasswordHelper()
    manager = _manager(user, helper)

    result = await manager.authenticate(
        SimpleNamespace(username="p@example.com", password="secret")
    )

    assert result is user  # credentials accepted (verify returned True)
    assert helper.verify_thread is not None  # verify actually ran
    assert helper.verify_thread != loop_thread  # ...and OFF the event-loop thread


async def test_authenticate_unknown_email_dummy_hash_off_event_loop() -> None:
    """The timing-attack dummy hash on an unknown email also runs off the loop."""
    loop_thread = threading.get_ident()
    helper = _RecordingPasswordHelper()
    manager = _manager(None, helper)  # get_by_email -> None -> UserNotExists -> dummy hash

    result = await manager.authenticate(
        SimpleNamespace(username="ghost@example.com", password="secret")
    )

    assert result is None
    assert helper.hash_thread is not None  # dummy hash ran (timing mitigation preserved)
    assert helper.hash_thread != loop_thread  # ...off the event-loop thread


async def test_create_hashes_off_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register hashes the new password in a worker thread, not the loop thread."""
    import app.auth.manager as mgr_mod

    loop_thread = threading.get_ident()
    helper = _RecordingPasswordHelper()

    class _FakeSession:
        def add(self, obj: object) -> None: ...
        async def flush(self) -> None: ...
        async def commit(self) -> None: ...
        async def refresh(self, obj: object) -> None: ...

    class _CreateUserDB:
        session = _FakeSession()

        def user_table(self, **kw: object) -> SimpleNamespace:
            return SimpleNamespace(**kw)

        async def get_by_email(self, email: str) -> None:
            return None  # no existing user

    manager = UserManager(_CreateUserDB(), helper, email_service=SimpleNamespace())
    # Neutralize the DB-touching side effects (wallet co-insert + post-register hook).
    monkeypatch.setattr(mgr_mod.WalletService, "create_wallet", AsyncMock())
    monkeypatch.setattr(UserManager, "on_after_register", AsyncMock())

    pwd = "Valid-Pass-123!"  # 12+, upper/lower/digit, no email substring -> passes validate
    user_create = SimpleNamespace(
        password=pwd,
        email="new@example.com",
        create_update_dict=lambda: {"email": "new@example.com", "password": pwd},
        create_update_dict_superuser=lambda: {"email": "new@example.com", "password": pwd},
    )

    await manager.create(user_create, safe=True)

    assert helper.hash_thread is not None  # the new password was hashed
    assert helper.hash_thread != loop_thread  # ...off the event-loop thread
