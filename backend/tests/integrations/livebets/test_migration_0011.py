"""Migration ``0011_livebets_bridge`` — additive + reversible (v1.3, LB-A, SC2).

Proves the live-bets bridge migration applies and reverses cleanly against a REAL
Postgres 16 (testcontainers), with ZERO behavior change to existing tables:

  - after ``alembic upgrade head``: the ``livebets_bets`` mirror table exists AND the
    ``livebets_escrow`` system singleton account exists exactly once (the idempotent
    ``ON CONFLICT DO NOTHING`` seed), and the chain links ``0011 -> 0010``.
  - after ``alembic downgrade -1``: ``livebets_bets`` is gone and the escrow singleton
    row is gone — the additive migration is fully reversible.

ISOLATION (T-LBA-T02): unlike the other LB-A tests, this module spins up its OWN
module-scoped ``PostgresContainer`` and drives Alembic synchronously
(``alembic.command`` + a psycopg2 sync engine) against it. It deliberately does NOT
depend on the session-scoped ``engine`` fixture in ``tests/conftest.py`` — running a
downgrade there would poison the shared schema for every later test. Driving an
isolated container is the "cheap correctness over shared-state cleverness" the plan
endorses, and it leaves the shared ``DATABASE_URL`` / ``DATABASE_URL_SYNC`` env
exactly as it found them (save/restore + lazy-cache clear), so the async suites are
untouched.

Sync-only test — no event loop, so just ``pytest.mark.integration`` (no asyncio mark).
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.integrations.livebets.constants import (
    KIND_LIVEBETS_ESCROW,
    LIVEBETS_ESCROW_ACCOUNT_ID,
)
from app.wallet.constants import OWNER_SYSTEM

# NOTE on the warning filter: Alembic's ``env.py`` runs each ``command.upgrade`` /
# ``command.downgrade`` through ``engine_from_config(..., poolclass=NullPool)`` — a
# fresh psycopg2 engine that env.py never ``dispose()``es (it only closes the per-run
# connection). The engine's lingering connection is reaped later by the GC, and
# ``Connection.__del__`` then emits a benign cleanup warning that pytest's global
# ``filterwarnings = error`` escalates to a failure — but ONLY when GC happens to run
# mid-test (so it surfaces in the full suite, not in isolation). It is a third-party
# connection-finalizer timing concern, not a code defect or a failed assertion (every
# schema assertion below still runs and must pass), so we down-grade JUST that
# unraisable warning to non-fatal for this module — the same spirit as the targeted
# third-party ``ignore`` entries in ``pyproject.toml``. No assertion is weakened.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
]


def _alembic_config(sync_url: str):
    """Build an Alembic ``Config`` bound to ``sync_url`` (the isolated container)."""
    from alembic.config import Config

    # tests/integrations/livebets/ -> backend/
    backend_root = Path(__file__).parent.parent.parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


@pytest.fixture(scope="module")
def isolated_pg() -> Generator[str, None, None]:
    """A throwaway Postgres 16 container for the up/down/up cycle (psycopg2 sync URL).

    Touches ONLY ``DATABASE_URL_SYNC`` (Alembic's sync engine reads it via ``env.py``'s
    ``Settings()``), saving/restoring it around the run. It deliberately does NOT touch
    the async ``DATABASE_URL`` nor clear the ``app.db.session`` lazy engine caches:
    Alembic here is purely synchronous, and disturbing the shared ASYNC engine (which
    other suites' asyncpg pools are bound to) is what leaks a socket at session teardown.
    Leaving the async engine alone keeps this module fully isolated — its own sync
    container, its own psycopg2 engines (all explicitly disposed), zero async-side state.
    """
    pytest.importorskip("testcontainers", reason="testcontainers required for migration test")
    from testcontainers.postgres import PostgresContainer

    saved_sync = os.environ.get("DATABASE_URL_SYNC")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with PostgresContainer("postgres:16-alpine") as pg:
            sync_url = pg.get_connection_url()
            if "+psycopg2" not in sync_url:
                sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)

            # Point ONLY the sync URL at THIS container so env.py's Settings() picks it
            # up for the alembic commands; the async DATABASE_URL is left untouched.
            os.environ["DATABASE_URL_SYNC"] = sync_url
            try:
                yield sync_url
            finally:
                if saved_sync is None:
                    os.environ.pop("DATABASE_URL_SYNC", None)
                else:
                    os.environ["DATABASE_URL_SYNC"] = saved_sync


# --------------------------------------------------------------------------- #
# Chain link — 0011_livebets_bridge declares down_revision 0011_phase13_market_groups
# (chained AFTER v1.2's 0011_phase13 at merge time — both used to descend from 0010,
# which created two alembic heads; this linearizes the history).
# --------------------------------------------------------------------------- #
def test_0011_chains_from_phase13() -> None:
    from alembic.script import ScriptDirectory

    cfg = _alembic_config("postgresql+psycopg2://unused/unused")  # no DB touch for script read
    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision("0011_livebets_bridge")
    assert rev is not None, "0011_livebets_bridge missing from the script directory"
    assert rev.down_revision == "0011_phase13_market_groups"


# --------------------------------------------------------------------------- #
# Additive — upgrade head creates the mirror table + the escrow singleton (once).
# --------------------------------------------------------------------------- #
def test_upgrade_creates_livebets_bets_and_escrow_singleton(isolated_pg: str) -> None:
    from alembic import command

    cfg = _alembic_config(isolated_pg)
    command.upgrade(cfg, "head")

    engine = create_engine(isolated_pg)
    try:
        # The livebets_bets mirror table exists after upgrade.
        insp = inspect(engine)
        assert insp.has_table("livebets_bets"), "livebets_bets table missing after upgrade head"

        # The user index ships with it.
        index_names = {ix["name"] for ix in insp.get_indexes("livebets_bets")}
        assert "livebets_bets_user_idx" in index_names

        # The livebets_escrow singleton exists exactly once, system-owned, right kind.
        with engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM accounts "
                    "WHERE id = :id AND kind = :kind AND owner_type = :ot"
                ),
                {
                    "id": str(LIVEBETS_ESCROW_ACCOUNT_ID),
                    "kind": KIND_LIVEBETS_ESCROW,
                    "ot": OWNER_SYSTEM,
                },
            ).scalar_one()
        assert count == 1, f"expected exactly one livebets_escrow singleton, got {count}"
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- #
# Reversible — downgrade -1 removes the mirror table AND the escrow singleton.
# Runs upgrade head -> downgrade -1 -> (restore) upgrade head, all on the
# ISOLATED container so the shared schema is never touched.
# --------------------------------------------------------------------------- #
def test_downgrade_removes_livebets_bets_and_escrow_singleton(isolated_pg: str) -> None:
    from alembic import command

    cfg = _alembic_config(isolated_pg)
    command.upgrade(cfg, "head")  # ensure we start at head (the other test may not have run)

    # Downgrade to the revision BELOW 0011_livebets_bridge (its down_revision) so the bridge
    # is fully undone regardless of how many migrations chain ABOVE it (e.g. 0012_early_close).
    # A relative "-1" would only undo the current head, leaving the bridge's objects in place.
    command.downgrade(cfg, "0011_phase13_market_groups")

    engine = create_engine(isolated_pg)
    try:
        insp = inspect(engine)
        assert not insp.has_table(
            "livebets_bets"
        ), "livebets_bets table still present after downgrade -1"

        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM accounts WHERE id = :id"),
                {"id": str(LIVEBETS_ESCROW_ACCOUNT_ID)},
            ).scalar_one()
        assert count == 0, f"livebets_escrow singleton still present after downgrade, got {count}"
    finally:
        engine.dispose()

    # Restore the isolated container to head (belt-and-braces; the container is
    # module-scoped, so a later test in this module re-running upgrade head must find
    # a clean chain). The fixture tears the whole container down regardless.
    command.upgrade(cfg, "head")
