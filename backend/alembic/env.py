"""Alembic env.py — sync engine via psycopg2 over DATABASE_URL_SYNC (D-16, Pattern 2).

The app uses asyncpg (DATABASE_URL); Alembic's runtime is sync by design
(Pitfall 2 — running alembic against an async engine would deadlock under
``-x dry_run`` / autogenerate). We read both URLs from ``Settings`` so a
single source of truth governs everything; ``DATABASE_URL_SYNC`` is the
psycopg2 variant.

Imports below register every Phase 1 ORM model against ``Base.metadata`` so
``alembic revision --autogenerate`` (Phase 2+) sees the tables. Phase 1's
0001 baseline is hand-authored — autogenerate is the convenience the imports
support, not what we used to create the baseline.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Register every ORM model against Base.metadata BEFORE reading
# `target_metadata`. The
# imports are pure side-effect registrations.
from app.auth.models import RefreshToken, User  # noqa: F401  (Plan 02-01)
from app.markets.models import Market, OddsSnapshot, Outcome  # noqa: F401  (Plan 04-01)
from app.core.audit.models import AuditLog  # noqa: F401
from app.core.config import Settings
from app.core.feature_flags.models import FeatureFlag  # noqa: F401
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL_SYNC))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode (emits SQL, no live connection)."""
    context.configure(
        url=str(settings.DATABASE_URL_SYNC),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live psycopg2 connection (the common path)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
