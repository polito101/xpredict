"""Settings(BaseSettings) unit tests — D-09 / PLT-03 coverage."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_VALID_URLS = {
    "DATABASE_URL": "postgresql+asyncpg://xpredict:xpredict@db:5432/xpredict",
    "DATABASE_URL_SYNC": "postgresql+psycopg2://xpredict:xpredict@db:5432/xpredict",
    "REDIS_URL": "redis://redis:6379/0",
}


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings instantiates with valid URLs; is_dev defaults to True; TENANT_ID_DEFAULT correct."""
    for key, value in _VALID_URLS.items():
        monkeypatch.setenv(key, value)
    # Remove ENVIRONMENT so it falls back to the dev default
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    settings = Settings()
    assert settings.is_dev is True
    assert settings.is_prod is False
    assert UUID("00000000-0000-0000-0000-000000000001") == settings.TENANT_ID_DEFAULT
    assert settings.SENTRY_TRACES_SAMPLE_RATE == 0.1


def test_settings_rejects_malformed_url() -> None:
    """A malformed DATABASE_URL raises ValidationError (Pydantic v2 PostgresDsn)."""
    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="not-a-url",  # type: ignore[arg-type]
            DATABASE_URL_SYNC=_VALID_URLS["DATABASE_URL_SYNC"],  # type: ignore[arg-type]
            REDIS_URL=_VALID_URLS["REDIS_URL"],  # type: ignore[arg-type]
        )


def test_settings_ignores_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown env vars must NOT raise — extra='ignore' per Pitfall 3."""
    for key, value in _VALID_URLS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("FOO_BAR", "baz-unknown-future-phase-var")
    monkeypatch.setenv("ANOTHER_UNKNOWN", "true")

    # If extra='forbid' was set by mistake, this would raise ValidationError
    settings = Settings()
    # The unknown vars must NOT be visible on the model
    assert not hasattr(settings, "FOO_BAR")
    assert not hasattr(settings, "ANOTHER_UNKNOWN")


def test_settings_is_prod_when_environment_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_dev/is_prod flip with ENVIRONMENT — drives Sentry/structlog renderer choice."""
    for key, value in _VALID_URLS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", "prod")

    settings = Settings()
    assert settings.is_dev is False
    assert settings.is_prod is True
