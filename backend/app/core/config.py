"""Single Settings(BaseSettings) — every env var the backend reads (D-09).

Never call ``os.getenv`` elsewhere — always read through ``Settings()``. The
``scrub_secrets`` structlog processor (see app.core.logging) protects log output
from accidentally leaking these values.

Phase 1 settings are the keys ROADMAP Phases 2-10 inherit; downstream phases
APPEND new keys (e.g. SESSION_SIGNING_KEY, ADMIN_TOKEN) — they do not redefine
the shape.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, PostgresDsn, RedisDsn
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

    # -------------------------------------------------------------------------
    # Phase 2 — Auth & Identity (AUTH-01..09, D-09, RESEARCH §Runtime State)
    # -------------------------------------------------------------------------
    #
    # SECRET_KEY is the symmetric HS256 signing key (A8). Verification + reset
    # token secrets in UserManager read from this same value. Minimum 32 chars
    # so HS256 has at least 256 bits of entropy. No default — must be set.
    SECRET_KEY: str = Field(min_length=32)
    # JWT algorithm — Literal["HS256"] only in v1 (A8); RS256 is a Phase 11
    # hardening item (asymmetric key separation).
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    # Token lifetimes (seconds). 15 min access / 30 day refresh per RESEARCH
    # Standard Stack defaults.
    ACCESS_TOKEN_LIFETIME_SECONDS: int = 900
    REFRESH_TOKEN_LIFETIME_SECONDS: int = 2_592_000  # 30 days
    # Resend (staging/prod email). Optional in dev — Mailpit handles SMTP.
    RESEND_API_KEY: str | None = None
    RESEND_FROM_ADDRESS: str = "noreply@xpredict.local"
    # Mailpit (dev SMTP, no auth, no TLS) — D-05 + Pitfall 7 (A7).
    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    # First-admin seeding (D-11). Both must be set for bin/create-admin.py.
    FIRST_ADMIN_EMAIL: str | None = None
    FIRST_ADMIN_PASSWORD: str | None = None
    # Frontend URL for email links (verify, reset). D-12.
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    # Mirrors SECRET_KEY but exposed to Next.js middleware for HS256 verify.
    # Symmetric (A8); RS256 would split this into a public-key file in Phase 11.
    ADMIN_JWT_PUBLIC_SECRET: str | None = None

    @property
    def is_dev(self) -> bool:
        """Drives structlog renderer, Sentry init skip, cookie Secure flag (Phase 2)."""
        return self.ENVIRONMENT == "dev"

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    Use this everywhere outside of tests — it validates env vars once and
    re-uses the result, avoiding per-request pydantic-settings construction
    overhead (WR-01).  Tests that need a fresh ``Settings()`` call it directly
    or use ``monkeypatch``; the cache is transparent to callers.
    """
    return Settings()
