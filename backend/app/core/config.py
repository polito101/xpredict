"""Single Settings(BaseSettings) — every env var the backend reads (D-09).

Never call ``os.getenv`` elsewhere — always read through ``Settings()``. The
``scrub_secrets`` structlog processor (see app.core.logging) protects log output
from accidentally leaking these values.

Phase 1 settings are the keys ROADMAP Phases 2-10 inherit; downstream phases
APPEND new keys (e.g. SESSION_SIGNING_KEY, ADMIN_TOKEN) — they do not redefine
the shape.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend runtime settings — all env-driven, typed and validated.

    ``extra="ignore"`` is mandatory (Pitfall 3): new env vars added by future
    phases must not raise ValidationError on older code paths. The structlog
    secret scrubber (D-25) is the parallel mitigation for accidental log leaks.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    DATABASE_URL: PostgresDsn
    DATABASE_URL_SYNC: PostgresDsn  # Alembic uses psycopg2 — see D-16
    REDIS_URL: RedisDsn
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    TENANT_ID_DEFAULT: UUID = UUID("00000000-0000-0000-0000-000000000001")

    @property
    def is_dev(self) -> bool:
        """Drives structlog renderer, Sentry init skip, cookie Secure flag (Phase 2)."""
        return self.ENVIRONMENT == "dev"

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "prod"
