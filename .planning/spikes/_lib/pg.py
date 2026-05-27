"""Throwaway Postgres 16 for the spikes, via testcontainers — the same mechanism
Phase 1 integration tests already use. Yields a SQLAlchemy *asyncpg* DSN.

Requires a running Docker daemon. One container is started per run.py and reused
across that script's scenarios (each scenario re-creates the schema).
"""

from __future__ import annotations

from contextlib import contextmanager

from testcontainers.postgres import PostgresContainer


@contextmanager
def postgres_container(image: str = "postgres:16-alpine"):
    with PostgresContainer(image) as pg:
        url = pg.get_connection_url()
        # Normalize whatever sync driver testcontainers picked (psycopg2/psycopg)
        # to asyncpg, and drop libpq query params (e.g. sslmode) asyncpg rejects.
        rest = url.split("://", 1)[1].split("?", 1)[0]
        dsn = "postgresql+asyncpg://" + rest
        print(f"[pg] Postgres 16 ready at {rest.rsplit('@', 1)[-1]}")
        yield dsn
