"""Wave-2 integration tests for migration ``0011_phase13_market_groups`` (EVT-01, SC#1 + SC#3).

Runs against testcontainers Postgres 16 (the session-scoped ``engine`` fixture in
``tests/conftest.py`` executes ``alembic upgrade head`` once for the session). These
tests then introspect the resulting schema with SQLAlchemy's ``inspect`` for columns
+ foreign keys, and read raw ``pg_indexes.indexdef`` DDL for the GIN ``gin_trgm_ops``
opclass and the partial ``WHERE`` predicate — which ``inspect(...).get_indexes()`` does
NOT reliably surface across dialects (13-RESEARCH A4).

Pattern source: ``tests/auth/test_migration_0002.py`` (``inspect`` via ``run_sync`` +
``ScriptDirectory.get_revision`` chain assertion) and ``tests/wallet/test_migration_0003.py``
(raw ``text()`` DDL introspection). First migration test under ``tests/markets/``.

Covers:
  - SC#1 (apply): ``market_groups`` table + the two new ``markets`` columns exist.
  - SC#1 (financial safety / T-13-01): ``markets.group_id`` FK is ``ON DELETE SET NULL``.
  - SC#1 (chain): ``0011.down_revision == "0010_phase12_resolution_stakes"`` + exactly
    one head named ``0011_phase13_market_groups``.
  - SC#1 (reversibility): ``downgrade()`` mirrors ``upgrade()`` — every ``create_table`` /
    ``add_column`` / ``create_index`` has a matching drop (static source-parse harness;
    see ``test_downgrade_mirrors_upgrade`` docstring for why this is preferred over a live
    cycle on the shared session engine).
  - SC#3 (pg_trgm): the extension is enabled.
  - SC#3 (indexes): both GIN trigram indexes carry ``gin_trgm_ops``; the partial-unique
    index has a ``WHERE source_event_id`` predicate; the four B-tree catalog indexes exist;
    the pre-existing single-column ``ix_odds_snapshots_outcome_id`` is STILL present
    alongside the new composite (additive, not dropped).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Inspector
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

REVISION = "0011_phase13_market_groups"
DOWN_REVISION = "0010_phase12_resolution_stakes"

# Path to the migration module under test — used by the static reversibility parse.
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0011_phase13_market_groups.py"
)


async def _indexdef(conn, name: str) -> str | None:
    """Return the raw ``pg_indexes.indexdef`` DDL for an index, or ``None`` if absent."""
    result = await conn.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
        {"name": name},
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# SC#1 — apply: market_groups table + new markets columns
# ---------------------------------------------------------------------------


async def test_market_groups_table_columns(engine: AsyncEngine) -> None:
    """``market_groups`` has the schema-locked columns (SC#1 apply)."""

    def _cols(sync_conn: object) -> set[str]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return {c["name"] for c in insp.get_columns("market_groups")}

    async with engine.connect() as conn:
        col_names = await conn.run_sync(_cols)

    required = {
        "id",
        "title",
        "source",
        "source_event_id",
        "category",
        "slug",
        "created_at",
        "updated_at",
        "tenant_id",
    }
    missing = required - col_names
    assert not missing, f"market_groups missing columns: {missing}"


async def test_markets_has_group_columns(engine: AsyncEngine) -> None:
    """``markets`` gained ``group_id`` + ``group_item_title`` (SC#1 apply, additive)."""

    def _cols(sync_conn: object) -> set[str]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return {c["name"] for c in insp.get_columns("markets")}

    async with engine.connect() as conn:
        col_names = await conn.run_sync(_cols)

    assert {"group_id", "group_item_title"}.issubset(
        col_names
    ), f"markets missing group columns; have: {sorted(col_names)}"


# ---------------------------------------------------------------------------
# SC#1 — financial safety (T-13-01): FK is ON DELETE SET NULL, never CASCADE
# ---------------------------------------------------------------------------


async def test_markets_group_id_fk_set_null(engine: AsyncEngine) -> None:
    """``markets.group_id`` FK → ``market_groups`` is ``ON DELETE SET NULL``.

    This TEST-ENFORCES the Plan 13-01 mitigation for threat T-13-01: a regression to
    CASCADE would let deleting a group cascade-destroy child markets that carry
    bets/odds/ledger state. Children must ORPHAN back to standalone, never be deleted.
    """

    def _fks(sync_conn: object) -> list[dict]:
        return list(inspect(sync_conn).get_foreign_keys("markets"))  # type: ignore[arg-type]

    async with engine.connect() as conn:
        fks = await conn.run_sync(_fks)

    group_fk = next(
        (fk for fk in fks if "group_id" in fk.get("constrained_columns", [])),
        None,
    )
    assert group_fk is not None, f"markets.group_id FK missing; fks={fks}"
    assert group_fk["referred_table"] == "market_groups"
    assert group_fk["referred_columns"] == ["id"]
    assert group_fk.get("options", {}).get("ondelete") == "SET NULL", (
        f"markets.group_id must be ON DELETE SET NULL (T-13-01), got "
        f"{group_fk.get('options', {}).get('ondelete')!r}"
    )


# ---------------------------------------------------------------------------
# SC#3 — pg_trgm extension
# ---------------------------------------------------------------------------


async def test_pg_trgm_enabled(engine: AsyncEngine) -> None:
    """The ``pg_trgm`` extension is installed (SC#3 — GIN trigram indexes depend on it)."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
        assert result.scalar_one_or_none() == 1, "pg_trgm extension not enabled"


# ---------------------------------------------------------------------------
# SC#3 — indexes: GIN gin_trgm_ops opclass + partial WHERE + B-tree catalog set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("index_name", "column"),
    [
        ("ix_market_groups_title_trgm", "title"),
        ("ix_markets_question_trgm", "question"),
    ],
)
async def test_gin_trgm_indexes_have_opclass(
    engine: AsyncEngine, index_name: str, column: str
) -> None:
    """Each GIN trigram index uses the ``gin_trgm_ops`` opclass ON ITS COLUMN (SC#3).

    Read raw ``pg_indexes.indexdef`` — ``get_indexes()`` does not reliably surface the
    opclass across dialects (13-RESEARCH A4).

    WR-01: don't just substring-match ``gin_trgm_ops`` anywhere in the DDL — tie the
    opclass to the INTENDED column. We assert ``gin_trgm_ops`` sits inside the same
    parenthesised column clause as ``title`` / ``question`` and is adjacent to that
    column (``<column> gin_trgm_ops``), so a regression that moved the opclass onto a
    different column (or dropped it) would FAIL.
    """
    async with engine.connect() as conn:
        ddl = await _indexdef(conn, index_name)

    assert ddl is not None, f"{index_name} not found in pg_indexes"
    lowered = ddl.lower()
    assert "gin" in lowered, f"{index_name} is not a GIN index: {ddl}"
    assert "gin_trgm_ops" in lowered, f"{index_name} missing gin_trgm_ops opclass: {ddl}"
    # The opclass must be bound to the intended column inside the index's
    # parenthesised column clause (e.g. ``... USING gin (title gin_trgm_ops)``),
    # collapsing internal whitespace so ``title   gin_trgm_ops`` still matches.
    paren = lowered[lowered.index("(") : lowered.rindex(")") + 1]
    assert f"{column} gin_trgm_ops" in re.sub(
        r"\s+", " ", paren
    ), f"{index_name}: gin_trgm_ops not bound to column {column!r}: {ddl}"


async def test_partial_unique_has_where_clause(engine: AsyncEngine) -> None:
    """``ix_market_groups_source_source_event_id`` is partial-UNIQUE with a WHERE (SC#3)."""
    async with engine.connect() as conn:
        ddl = await _indexdef(conn, "ix_market_groups_source_source_event_id")

    assert ddl is not None, "ix_market_groups_source_source_event_id not found"
    lowered = ddl.lower()
    assert "unique" in lowered, f"partial index is not UNIQUE: {ddl}"
    assert "where" in lowered, f"partial index missing WHERE predicate: {ddl}"
    assert (
        "source_event_id" in lowered
    ), f"partial index WHERE does not reference source_event_id: {ddl}"
    # WR-01: pin the POLARITY. The index must cover rows where source_event_id
    # IS NOT NULL (so multiple NULL-source_event_id HOUSE groups stay allowed
    # while real external event ids are deduped). The logical inverse
    # ``WHERE source_event_id IS NULL`` would satisfy the token checks above but
    # invert the constraint — assert IS NOT NULL explicitly so it cannot pass.
    assert (
        "is not null" in lowered
    ), f"partial index WHERE must be IS NOT NULL (not the inverse), got: {ddl}"


@pytest.mark.parametrize(
    "index_name",
    [
        "ix_market_groups_category",
        "ix_markets_category",
        "ix_markets_status_volume_24hr",
        "ix_odds_snapshots_outcome_id_snapshot_at",
    ],
)
async def test_btree_catalog_indexes_exist(engine: AsyncEngine, index_name: str) -> None:
    """The four B-tree catalog filter/sort indexes exist (SC#3)."""
    async with engine.connect() as conn:
        ddl = await _indexdef(conn, index_name)
    assert ddl is not None, f"catalog index {index_name} not found in pg_indexes"


async def test_composite_index_column_order(engine: AsyncEngine) -> None:
    """Composite catalog indexes pin the LEADING column (WR-01, SC#3).

    Existence alone is not enough for the two composite indexes — their whole
    point is the leading column (range-scan + sort prefix):

      - ``ix_odds_snapshots_outcome_id_snapshot_at`` = ``(outcome_id, snapshot_at)``
        so a single outcome's price history scans by outcome then orders by time.
      - ``ix_markets_status_volume_24hr`` = ``(status, volume_24hr)`` so the catalog
        filters by status then sorts by 24h volume.

    A regression that flipped either to ``(snapshot_at, outcome_id)`` /
    ``(volume_24hr, status)`` would still create an index of the same NAME and pass
    the existence test — but defeat the optimisation the composite was added for.
    The ``indexdef`` string carries the ordered column tuple, so assert the leading
    column appears before the trailing one.
    """
    async with engine.connect() as conn:
        odds = (await _indexdef(conn, "ix_odds_snapshots_outcome_id_snapshot_at")) or ""
        mkt = (await _indexdef(conn, "ix_markets_status_volume_24hr")) or ""

    odds_l = odds.lower()
    mkt_l = mkt.lower()
    assert odds_l, "ix_odds_snapshots_outcome_id_snapshot_at not found in pg_indexes"
    assert mkt_l, "ix_markets_status_volume_24hr not found in pg_indexes"
    # Leading column must come first in the indexed tuple.
    assert odds_l.index("outcome_id") < odds_l.index(
        "snapshot_at"
    ), f"composite must be (outcome_id, snapshot_at), got: {odds}"
    assert mkt_l.index("status") < mkt_l.index(
        "volume_24hr"
    ), f"composite must be (status, volume_24hr), got: {mkt}"


async def test_existing_odds_outcome_id_index_retained(engine: AsyncEngine) -> None:
    """The pre-existing single-column ``ix_odds_snapshots_outcome_id`` is STILL present.

    The new composite ``(outcome_id, snapshot_at)`` index is ADDITIVE (SC#3 regression
    guard) — migration 0011 must NOT drop the single-column index created in 0003.
    """
    async with engine.connect() as conn:
        single = await _indexdef(conn, "ix_odds_snapshots_outcome_id")
        composite = await _indexdef(conn, "ix_odds_snapshots_outcome_id_snapshot_at")

    assert (
        single is not None
    ), "pre-existing ix_odds_snapshots_outcome_id was dropped — composite must be additive"
    assert composite is not None, "new composite ix_odds_snapshots_outcome_id_snapshot_at missing"


# ---------------------------------------------------------------------------
# SC#1 — chain: down_revision + single head
# ---------------------------------------------------------------------------


async def test_chain_down_revision_and_single_head(engine: AsyncEngine) -> None:
    """``0011`` chains off ``0010_phase12_resolution_stakes`` and is the lone head (SC#1).

    Asserts the Pitfall-2 guard: ``down_revision`` is the in-table REVISION ID of 0010
    (``0010_phase12_resolution_stakes``), NOT the filename stem
    ``0010_phase12_resolution_and_stake_limits``. Also asserts there is exactly one head
    (no branch was introduced) and it is ``0011_phase13_market_groups``.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    s = ScriptDirectory.from_config(cfg)

    rev = s.get_revision(REVISION)
    assert rev is not None, f"Revision {REVISION} missing from script directory"
    assert rev.down_revision == DOWN_REVISION, (
        f"0011.down_revision must be {DOWN_REVISION!r} (the revision id, not the "
        f"filename stem), got {rev.down_revision!r}"
    )

    heads = s.get_heads()
    assert len(heads) == 1, f"expected exactly one head, got {heads}"
    assert heads[0] == REVISION, f"head should be {REVISION!r}, got {heads[0]!r}"


# ---------------------------------------------------------------------------
# SC#1 — reversibility: downgrade() mirrors upgrade()
# ---------------------------------------------------------------------------


async def test_downgrade_mirrors_upgrade() -> None:
    """``downgrade()`` reverses every object ``upgrade()`` created (SC#1 reversibility).

    Declared ``async`` only to satisfy the module-level ``pytestmark`` asyncio mark
    (the suite runs under ``filterwarnings=error``, which turns "asyncio mark on a sync
    function" into a failure). The body is pure source-text parsing — no I/O, no DB.

    Harness choice (13-RESEARCH A5): a STATIC source-parse assertion, NOT a live
    ``command.downgrade("-1")`` → ``command.upgrade("head")`` cycle. The ``engine``
    fixture is session-scoped and already at head; a live downgrade would briefly DROP
    ``market_groups`` out from under every other session-scoped markets test, and if the
    cycle failed mid-way it would leave the whole session schema broken
    (``InFailedSQLTransactionError`` cascade). The static parse is deterministic, never
    disturbs the shared schema, and proves the contract that matters: ``downgrade()`` is
    non-empty and drops exactly what ``upgrade()`` creates.

    (The live upgrade→downgrade→upgrade round-trip WAS exercised against a real
    ``postgres:16-alpine`` while authoring 13-01 — see 13-01-SUMMARY "Decisions Made";
    here we lock it as a committed, deterministic, side-effect-free regression.)
    """
    source = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "def upgrade()" in source and "def downgrade()" in source

    up_start = source.index("def upgrade()")
    down_start = source.index("def downgrade()")
    upgrade_body = source[up_start:down_start]
    downgrade_body = source[down_start:]

    # downgrade() must be non-empty (more than just its signature/docstring/comments).
    assert "op." in downgrade_body, "downgrade() body performs no operations"

    # 1) Table: every created table is dropped.
    created_tables = set(re.findall(r'op\.create_table\(\s*["\']([^"\']+)["\']', upgrade_body))
    dropped_tables = set(re.findall(r'op\.drop_table\(\s*["\']([^"\']+)["\']', downgrade_body))
    assert created_tables, "expected at least one create_table in upgrade()"
    assert (
        created_tables <= dropped_tables
    ), f"tables created but not dropped: {created_tables - dropped_tables}"

    # 2) Columns: every added column is dropped.
    created_cols = set(
        re.findall(
            r'op\.add_column\(\s*["\'][^"\']+["\']\s*,\s*sa\.Column\(\s*["\']([^"\']+)["\']',
            upgrade_body,
        )
    )
    dropped_cols = set(
        re.findall(
            r'op\.drop_column\(\s*["\'][^"\']+["\']\s*,\s*["\']([^"\']+)["\']',
            downgrade_body,
        )
    )
    assert created_cols == {
        "group_id",
        "group_item_title",
    }, f"unexpected added-column set: {created_cols}"
    assert (
        created_cols <= dropped_cols
    ), f"columns added but not dropped: {created_cols - dropped_cols}"

    # 3) Indexes: every created index is dropped (the 6 phase-13 indexes + slug + group_id).
    created_idx = set(re.findall(r'op\.create_index\(\s*["\']([^"\']+)["\']', upgrade_body))
    dropped_idx = set(re.findall(r'op\.drop_index\(\s*["\']([^"\']+)["\']', downgrade_body))
    assert created_idx, "expected create_index calls in upgrade()"
    assert (
        created_idx <= dropped_idx
    ), f"indexes created but not dropped: {created_idx - dropped_idx}"

    # 4) The FK constraint is dropped.
    created_fk = set(re.findall(r'op\.create_foreign_key\(\s*["\']([^"\']+)["\']', upgrade_body))
    dropped_fk = set(re.findall(r'op\.drop_constraint\(\s*["\']([^"\']+)["\']', downgrade_body))
    assert (
        created_fk <= dropped_fk
    ), f"FK constraints created but not dropped: {created_fk - dropped_fk}"

    # 5) pg_trgm is DELIBERATELY left in place (RESEARCH A1 / Pitfall 3) — assert the
    #    downgrade does NOT drop the extension.
    assert (
        "DROP EXTENSION" not in downgrade_body.upper()
    ), "downgrade() must NOT drop pg_trgm (DB-global, may be shared; RESEARCH A1)"
