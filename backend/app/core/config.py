"""Single Settings(BaseSettings) — every env var the backend reads (D-09).

Never call ``os.getenv`` elsewhere — always read through ``Settings()``. The
``scrub_secrets`` structlog processor (see app.core.logging) protects log output
from accidentally leaking these values.

Phase 1 settings are the keys ROADMAP Phases 2-10 inherit; downstream phases
APPEND new keys (e.g. SESSION_SIGNING_KEY, ADMIN_TOKEN) — they do not redefine
the shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class CategoryEntry:
    """One curated-category allow-list entry (Phase 14, CAT-03).

    A frozen, version-controlled value object — NOT an env var. ``tag_id`` is a
    STRING because Gamma tag ids compare against ``GammaTag.id: str``. The
    ordering of ``POLYMARKET_CATEGORIES`` below is the first-by-priority tie-break
    for dual-tagged events.
    """

    name: str  # human-readable, stored in Market.category ("Politics")
    slug: str  # Gamma slug ("politics")
    tag_id: str  # Gamma tag id as string ("2")


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
    # DEMO_MODE relaxes the product for a sales demo: 6-char passwords (no
    # complexity), accounts auto-verified at registration, and the sign-up bonus
    # granted at registration (no email step). Default OFF — production behavior.
    DEMO_MODE: bool = False
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

    # -------------------------------------------------------------------------
    # Phase 5 — Bets & Settlement (WAL-02 / ADU-03)
    # -------------------------------------------------------------------------
    SIGNUP_BONUS_AMOUNT: Decimal = Decimal("1000.0000")
    BET_MIN_STAKE: Decimal = Decimal("1.0000")
    BET_MAX_STAKE: Decimal = Decimal("100000.0000")

    # -------------------------------------------------------------------------
    # Phase 6 — Polymarket Sync (MKT-05, MKT-06)
    # -------------------------------------------------------------------------
    GAMMA_API_BASE_URL: str = "https://gamma-api.polymarket.com"
    POLYMARKET_POLL_INTERVAL_SECONDS: int = 30
    POLYMARKET_SNAPSHOT_INTERVAL_SECONDS: int = 300
    POLYMARKET_LOCK_TTL_SECONDS: int = 25

    # -------------------------------------------------------------------------
    # Phase 7 — Polymarket Auto-Resolution (STL-01)
    # -------------------------------------------------------------------------
    POLYMARKET_GRACE_PERIOD_MINUTES: int = 30

    # -------------------------------------------------------------------------
    # Phase 14 — Curated Per-Category Gamma Sync (CAT-01..06, EVT-07)
    # -------------------------------------------------------------------------
    POLYMARKET_EVENTS_POLL_INTERVAL_SECONDS: int = 300  # 5 min (slower than 30s odds poll)
    POLYMARKET_EVENTS_TOP_N: int = 10  # events per category (~70 curated total)
    POLYMARKET_VOLUME_FLOOR: Decimal = Decimal("10000")  # $10k/event AFTER dedup (CAT-02)
    POLYMARKET_EVENTS_LIMIT_CAP: int = 500  # Gamma /events limit ceiling (CAT-05)
    # 14-AUDIT W-1: a full cycle (7 categories x Gamma retries, up to 3 attempts x
    # ~15s timeout + backoff each) can exceed the old 280s TTL under slow upstreams,
    # expiring the lock mid-run -> two cycles overlap. Set above the worst-case
    # cycle: the happy-path release is immediate (a normal ~2s cycle never holds it),
    # and a crashed run still auto-recovers when the TTL lapses.
    POLYMARKET_EVENTS_LOCK_TTL_SECONDS: int = 600

    # Version-controlled allow-list (CAT-03), NOT env/DB. PRIORITY ORDER below is
    # first-wins on a multi-tag event (World+Politics -> Politics). tag_ids are
    # live-verified via GET /tags/slug/{slug} (HTTP 200 each, 2026-06-05).
    # Re-verify loop before relying on the pin:
    #   for slug in politics sports crypto pop-culture economy tech world; do
    #     curl -s "https://gamma-api.polymarket.com/tags/slug/$slug"; done
    POLYMARKET_CATEGORIES: list[CategoryEntry] = [
        CategoryEntry(name="Politics", slug="politics", tag_id="2"),
        CategoryEntry(name="Sports", slug="sports", tag_id="1"),
        CategoryEntry(name="Crypto", slug="crypto", tag_id="21"),
        CategoryEntry(name="Pop Culture", slug="pop-culture", tag_id="596"),
        CategoryEntry(name="Economy", slug="economy", tag_id="100328"),
        CategoryEntry(name="Tech", slug="tech", tag_id="1401"),
        CategoryEntry(name="World", slug="world", tag_id="101970"),
    ]

    # -------------------------------------------------------------------------
    # Live-bets demo (v1.3, LB-A)
    # -------------------------------------------------------------------------
    # Operator-plane integration with the live-bets API. The API key is optional
    # in dev/test so ``Settings()`` validates with no value; the client raises a
    # clear error if a call is attempted while it is unset. Never log the key
    # (CONVENTIONS §8 scrubber covers ``api_key``).
    LIVEBETS_API_BASE: str = "http://localhost:8080"
    LIVEBETS_API_KEY: str | None = None
    LIVEBETS_DEFAULT_TABLE_ID: str | None = None
    LIVEBETS_ENABLE_WEBHOOK: bool = False
    LIVEBETS_WEBHOOK_SECRET: str | None = None

    # -------------------------------------------------------------------------
    # Casino demo (SlotsLaunch) — quick task 260611-u0q (CASINO-01..03)
    # -------------------------------------------------------------------------
    # SlotsLaunch demo-slots catalog proxy. The token is DOMAIN-BOUND to
    # ``SLOTSLAUNCH_ORIGIN`` (sent as the ``Origin`` header on every upstream
    # call) and already lives in the gitignored ``.env.local`` — never hardcode
    # or commit it. ``None`` default means a deploy with no token degrades to the
    # inactive ``{status:"inactive",games:[]}`` surface (the service never calls
    # upstream when the token is unset). The catalog is Redis-cached for
    # ``SLOTSLAUNCH_CACHE_TTL_SECONDS`` (12h) so repeat ``/casino`` loads do not
    # re-hit the upstream quota. Never log the token (the structlog scrubber
    # covers token-like keys, and the client never passes it into a log event).
    SLOTSLAUNCH_TOKEN: str | None = None
    SLOTSLAUNCH_API_BASE: str = "https://slotslaunch.com"
    SLOTSLAUNCH_ORIGIN: str = "https://app.xprediction.online"
    SLOTSLAUNCH_CACHE_TTL_SECONDS: int = 43200  # 12h

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
