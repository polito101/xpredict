"""Phase 2 Settings(BaseSettings) tests — AUTH-01 / D-09 / PATTERNS §Settings Extension.

Verify the 12 new Phase 2 env vars are exposed, defaults are correct, and
``extra="ignore"`` is preserved. Pattern source: backend/tests/test_settings.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_VALID_URLS = {
    "DATABASE_URL": "postgresql+asyncpg://xpredict:xpredict@db:5432/xpredict",
    "DATABASE_URL_SYNC": "postgresql+psycopg2://xpredict:xpredict@db:5432/xpredict",
    "REDIS_URL": "redis://redis:6379/0",
}


def _seed_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the minimal env vars required for ``Settings()`` to validate."""
    for key, value in _VALID_URLS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SECRET_KEY", "x" * 32)


def test_phase2_keys_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    """All 12 new Phase 2 keys are attributes on the Settings instance."""
    _seed_required(monkeypatch)
    s = Settings()

    # All Phase 2 keys must be present on the model (some optional, some
    # with defaults). hasattr is the lightest existence check.
    expected_keys = {
        "SECRET_KEY",
        "JWT_ALGORITHM",
        "ACCESS_TOKEN_LIFETIME_SECONDS",
        "REFRESH_TOKEN_LIFETIME_SECONDS",
        "RESEND_API_KEY",
        "RESEND_FROM_ADDRESS",
        "SMTP_HOST",
        "SMTP_PORT",
        "FIRST_ADMIN_EMAIL",
        "FIRST_ADMIN_PASSWORD",
        "FRONTEND_BASE_URL",
        "ADMIN_JWT_PUBLIC_SECRET",
    }
    for key in expected_keys:
        assert hasattr(s, key), f"Settings missing Phase 2 key: {key}"

    # SECRET_KEY took the env-supplied 32-char value.
    assert s.SECRET_KEY == "x" * 32


def test_jwt_algorithm_literal_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWT_ALGORITHM defaults to 'HS256' and is restricted to that literal (A8)."""
    _seed_required(monkeypatch)
    s = Settings()
    assert s.JWT_ALGORITHM == "HS256"


def test_phase2_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default values match PLAN spec verbatim."""
    _seed_required(monkeypatch)
    s = Settings()

    assert s.ACCESS_TOKEN_LIFETIME_SECONDS == 900
    assert s.REFRESH_TOKEN_LIFETIME_SECONDS == 2_592_000
    assert s.SMTP_HOST == "mailpit"
    assert s.SMTP_PORT == 1025
    assert s.RESEND_FROM_ADDRESS == "noreply@xpredict.local"
    assert s.FRONTEND_BASE_URL == "http://localhost:3000"


def test_optional_secrets_accept_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Optional secrets default to None when env var absent (dev-friendly)."""
    _seed_required(monkeypatch)
    # Explicitly unset the optional vars in case the host env has them
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("FIRST_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("FIRST_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_JWT_PUBLIC_SECRET", raising=False)

    s = Settings()
    assert s.RESEND_API_KEY is None
    assert s.FIRST_ADMIN_EMAIL is None
    assert s.FIRST_ADMIN_PASSWORD is None
    assert s.ADMIN_JWT_PUBLIC_SECRET is None


def test_extra_ignore_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding an unknown env var must NOT raise — extra='ignore' (Pitfall 3 carryover)."""
    _seed_required(monkeypatch)
    monkeypatch.setenv("UNKNOWN_PHASE_3_VAR", "future-value")

    # Should not raise
    s = Settings()
    assert not hasattr(s, "UNKNOWN_PHASE_3_VAR")


def test_secret_key_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """SECRET_KEY has no default — must be set in env or instantiation fails."""
    for key, value in _VALID_URLS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_phase1_settings_still_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 1 fields (TENANT_ID_DEFAULT, ENVIRONMENT, etc.) are not regressed."""
    _seed_required(monkeypatch)
    s = Settings()

    # Sanity-check a few Phase 1 attributes still exist
    assert hasattr(s, "DATABASE_URL")
    assert hasattr(s, "REDIS_URL")
    assert hasattr(s, "TENANT_ID_DEFAULT")
    assert hasattr(s, "is_dev")
    assert hasattr(s, "is_prod")
