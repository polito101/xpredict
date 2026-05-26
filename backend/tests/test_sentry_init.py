"""Sentry init unit tests — D-28 / PLT-08 coverage.

Mocks ``sentry_sdk.init`` and ``sentry_sdk.set_tag`` so the tests don't hit
the actual Sentry SDK process-global state.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.sentry import init_sentry

_VALID_URLS: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://x:y@h:5432/d",
    "DATABASE_URL_SYNC": "postgresql+psycopg2://x:y@h:5432/d",
    "REDIS_URL": "redis://h:6379/0",
}


def _make_settings(monkeypatch: pytest.MonkeyPatch, *, sentry_dsn: str | None = None) -> Settings:
    for key, value in _VALID_URLS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SENTRY_DSN", sentry_dsn or "")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    return Settings()


def test_init_sentry_skips_when_no_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without SENTRY_DSN, init_sentry is a no-op — never calls sentry_sdk.init."""
    settings = _make_settings(monkeypatch, sentry_dsn=None)
    with (
        patch("app.core.sentry.sentry_sdk.init") as mock_init,
        patch("app.core.sentry.sentry_sdk.set_tag") as mock_set_tag,
    ):
        init_sentry("api", settings, integrations=[])
        mock_init.assert_not_called()
        mock_set_tag.assert_not_called()


def test_init_sentry_sets_service_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a DSN, init_sentry calls sentry_sdk.init AND sets service tag."""
    settings = _make_settings(monkeypatch, sentry_dsn="https://test@sentry.io/1")
    with (
        patch("app.core.sentry.sentry_sdk.init") as mock_init,
        patch("app.core.sentry.sentry_sdk.set_tag") as mock_set_tag,
    ):
        init_sentry("worker", settings, integrations=[])
        mock_init.assert_called_once()
        kwargs = mock_init.call_args.kwargs
        assert kwargs["dsn"] == "https://test@sentry.io/1"
        assert kwargs["environment"] == "dev"
        assert kwargs["send_default_pii"] is False
        mock_set_tag.assert_called_once_with("service", "worker")


def test_init_sentry_tags_per_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each of api/worker/beat gets its own service tag (Pitfall 5 mitigation)."""
    settings = _make_settings(monkeypatch, sentry_dsn="https://test@sentry.io/1")
    for service in ("api", "worker", "beat"):
        with (
            patch("app.core.sentry.sentry_sdk.init"),
            patch("app.core.sentry.sentry_sdk.set_tag") as mock_set_tag,
        ):
            init_sentry(service, settings, integrations=[])
            mock_set_tag.assert_called_once_with("service", service)
