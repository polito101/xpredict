# Phase 13: Multi-outcome Model & Catalog Indexes - Research

**Researched:** 2026-06-05
**Domain:** Python 3.12 · FastAPI · SQLAlchemy 2.0.50 async · Alembic 1.18.4 · Postgres 16 — additive schema, ORM, and indexes
**Confidence:** HIGH

## Summary

Phase 13 is a pure additive database seam: a new `market_groups` table, two nullable columns on
`markets` (`group_id` FK + `group_item_title`), the `pg_trgm` extension, six indexes, and a
`MarketGroup` ORM model with a `MarketGroup ↔ Market` relationship — all in one reversible Alembic
migration `0011_phase13_market_groups`. There is **no application logic, no API, no UI**. Every
unknown the planner needs is resolvable from in-repo precedent plus two official-doc confirmations,
and **every key pattern already exists in this codebase** (Phase 6's partial-unique index, Phase 4's
table-creation style, Phase 2/3's migration-introspection tests).

The single most important verified fact: `alembic heads` returns **exactly one head** today —
revision id `0010_phase12_resolution_stakes` (NOT the filename `0010_phase12_resolution_and_stake_limits`).
The branched history (two `0004_*`) was already merged at `0006_merge_phase5_phase6`. So `0011`'s
`down_revision` is `"0010_phase12_resolution_stakes"`. No merge revision is needed.

The second most important fact: the `MKT-08` binary-only enforcement is a **trigger on the `outcomes`
table** (`trg_binary_outcomes_only`, max 2 outcomes per `market_id`) — it is **untouched and fully
compatible** with the event-of-binaries design, because each child market still has exactly two
outcomes. Grouping happens one level up (`market_groups`), never inside a market's outcome set.

**Primary recommendation:** Author one migration mirroring `0004_phase6_polymarket_sync.py`'s style
(raw `op.execute` for the extension, `op.create_index(..., postgresql_using="gin", postgresql_ops=...,
postgresql_where=...)` for the indexes). Declare the indexes in BOTH the migration AND the ORM
`__table_args__` (so autogenerate/metadata stay in sync, matching the existing `Market`/`Outcome`
pattern). Keep `lazy="raise"` on the new relationship; the round-trip test uses
`selectinload(MarketGroup.markets)`. Set `Market.group_id` FK to `ondelete="SET NULL"`. Keep the
revision id ≤ 32 chars.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `market_groups` table + indexes (DDL) | Database / Storage | — | Schema is owned by the migration; Postgres enforces uniqueness, FK, GIN search |
| `MarketGroup` ORM + relationship | API / Backend (ORM layer) | Database | SQLAlchemy mapping is the seam later phases (14 sync, 16 API) read through |
| `pg_trgm` extension | Database / Storage | — | Bundled Postgres extension; enabled in-migration, not a Python dependency |
| Zero-behavior-change guarantee | Database / Storage | API / Backend | Proven by introspection + a regression test on the unchanged standalone-market read path |

**Note:** No browser/frontend/CDN tier is involved in Phase 13. All four capabilities live in the
backend data layer. This is correct for a schema-gate phase.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.50 | ORM model + relationship + `Index()` declarative DDL | [VERIFIED: `uv run python -c "import sqlalchemy"`] — already the project ORM; 2.0 async `Mapped[...]` style is locked |
| Alembic | 1.18.4 | The reversible migration `0011` | [VERIFIED: `uv run python -c "import alembic"`] — sync-engine migration runner (CONVENTIONS §5) |
| Postgres | 16 | `pg_trgm`, GIN indexes, partial-unique, FK | [VERIFIED: testcontainers `postgres:16-alpine` in `tests/conftest.py`] |
| `pg_trgm` | bundled w/ PG 16 | GIN-accelerated infix `ILIKE` substring search | [CITED: postgresql.org/docs — pgtrgm.html; .planning/research/STACK.md] — the ONLY infra addition, enabled via `CREATE EXTENSION IF NOT EXISTS pg_trgm` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-slugify` (`slugify`) | already locked | `MarketGroup.slug` generation (mirrors `Market.generate_slug`) | Only if you generate group slugs in-phase; Phase 16 owns `/events/{slug}`. The column must exist now; population is later |
| testcontainers | already locked | Run the real migration + introspect schema against PG 16 | All migration/ORM round-trip tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pg_trgm` GIN + `ILIKE` | `tsvector` FTS + `websearch_to_tsquery` | [CITED: .planning/research/STACK.md Decision 1] tsvector does NOT match arbitrary substrings/typos, needs a generated column + GIN, and is over-engineering for short titles. **Rejected upstream.** |
| `pg_trgm` GIN | External engine (Meilisearch/Elastic) | A whole search service for a bounded curated catalog — massive over-engineering. **Rejected upstream.** |
| `sqlalchemy-utils` `TSVectorType` | plain `func.to_tsvector` + raw GIN | Only on the FTS path (not taken); even then a new dep is avoidable. **Not applicable.** |

**Installation:** None. `pg_trgm` is bundled with Postgres 16 and enabled inside the migration. **Zero
new Python packages.** (CONTEXT.md: "Zero new dependencies".)

## Package Legitimacy Audit

> **N/A — this phase installs no external packages.** The only infrastructure addition is the
> Postgres-bundled `pg_trgm` extension (`CREATE EXTENSION IF NOT EXISTS pg_trgm`), which is not a
> package-registry artifact. `slopcheck` was unavailable in this session, but no `npm`/`pip`/`crates`
> install occurs, so the legitimacy gate does not apply. All ORM/migration work uses already-locked
> dependencies (SQLAlchemy 2.0.50, Alembic 1.18.4) verified present via `uv run`.

## Architecture Patterns

### System Architecture Diagram

```
                    Alembic migration 0011_phase13_market_groups
                    (sync engine, DATABASE_URL_SYNC — CONVENTIONS §5)
                                      │
            ┌─────────────────────────┼──────────────────────────────┐
            │ upgrade()               │                              │ downgrade()
            ▼                         ▼                              ▼ (exact reverse order)
   CREATE EXTENSION            CREATE TABLE market_groups      DROP TABLE market_groups
   IF NOT EXISTS pg_trgm   ──▶ (id, title, source,            DROP COLUMN markets.group_item_title
   (MUST run first —            source_event_id, category,    DROP COLUMN markets.group_id
    GIN indexes depend          slug UNIQUE, created_at,       DROP INDEX (all 6)
    on it)                      updated_at, tenant_id)         (leave pg_trgm — see Pitfall 3)
            │                         │
            │                  ALTER TABLE markets
            │                  ADD group_id UUID NULL
            │                      FK→market_groups.id ON DELETE SET NULL
            │                  ADD group_item_title TEXT NULL  (no backfill)
            ▼                         ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ Indexes (6):                                                  │
   │  • GIN trgm market_groups.title    (gin_trgm_ops)            │
   │  • GIN trgm markets.question       (gin_trgm_ops)            │
   │  • partial-UNIQUE market_groups (source, source_event_id)    │
   │       WHERE source_event_id IS NOT NULL                       │
   │  • market_groups (category)                                   │
   │  • markets (category)                                         │
   │  • markets (status, volume_24hr)                              │
   │  • odds_snapshots (outcome_id, snapshot_at)                   │
   └──────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
              ORM layer (app/markets/models.py + __init__.py + alembic/env.py)
   ┌──────────────────────────────────────────────────────────────┐
   │  MarketGroup(Base)  ──1:N──▶  Market.group_id (nullable)      │
   │    .markets  (lazy="raise")     .group  (lazy="raise")        │
   │                                                               │
   │  Read paths (UNCHANGED — SC#2):                               │
   │    group_id IS NULL standalone market                         │
   │      → get_market_by_slug → selectinload(outcomes, snapshots) │
   │      → bet path → SettlementService   (byte-for-byte same)    │
   └──────────────────────────────────────────────────────────────┘

  MKT-08 trigger trg_binary_outcomes_only lives on OUTCOMES (max 2 / market) —
  NOT TOUCHED. Each child market is still a 2-outcome binary. Grouping is one level up.
```

### Component Responsibilities

| File | Change | Notes |
|------|--------|-------|
| `backend/alembic/versions/0011_phase13_market_groups.py` | NEW | The reversible migration. `down_revision = "0010_phase12_resolution_stakes"` |
| `backend/app/markets/models.py` | EXTEND | Add `MarketGroup` class; add `group_id` + `group_item_title` + `group` relationship to `Market`; add `__table_args__` indexes |
| `backend/app/markets/__init__.py` | EXTEND | Export `MarketGroup` in `__all__` (currently exports `Market, OddsSnapshot, Outcome`) |
| `backend/alembic/env.py` | EXTEND | Import `MarketGroup` on line 32 so autogenerate sees it (`from app.markets.models import Market, MarketGroup, OddsSnapshot, Outcome`) |
| `backend/tests/markets/test_migration_0011.py` (or similar) | NEW | Migration introspection + reversibility + round-trip + zero-change regression |

### Pattern 1: Reversible migration mirroring 0004_phase6
**What:** The whole `0011` migration. The closest in-repo template is `0004_phase6_polymarket_sync.py`
(partial-unique index) + `0009_phase10_tenant_config.py` (CREATE TABLE with tenant_id + timestamps).
**When to use:** This is the canonical form for THIS phase — copy its structure exactly.
**Example:**
```python
# Source: backend/alembic/versions/0004_phase6_polymarket_sync.py (partial unique, lines 68-74)
#       + backend/alembic/versions/0009_phase10_tenant_config.py (create_table, lines 38-70)
#       + SQLAlchemy 2.0 docs (postgresql_using="gin" / postgresql_ops / postgresql_where)
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_phase13_market_groups"          # 26 chars — safe (< varchar(32), see Pitfall 1)
down_revision: str | None = "0010_phase12_resolution_stakes"   # the REVISION ID, not the filename
branch_labels: str | None = None
depends_on: str | None = None

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"   # same literal as 0001/0002/0003/0004/0009


def upgrade() -> None:
    # 1) pg_trgm FIRST — the GIN indexes below depend on gin_trgm_ops existing.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2) market_groups table
    op.create_table(
        "market_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'HOUSE'")),
        sa.Column("source_event_id", sa.String(200), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'OPEN'")),  # see Note A
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True,
                  server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid")),
        sa.CheckConstraint("source IN ('HOUSE', 'POLYMARKET')", name="ck_market_groups_source"),
    )
    op.create_index("ix_market_groups_slug", "market_groups", ["slug"], unique=True)

    # 3) nullable Market columns — additive, NO backfill
    op.add_column("markets", sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("markets", sa.Column("group_item_title", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_markets_group_id", "markets", "market_groups",
        ["group_id"], ["id"], ondelete="SET NULL",      # children survive group deletion (additive seam)
    )
    op.create_index("ix_markets_group_id", "markets", ["group_id"])

    # 4) GIN trigram indexes (pg_trgm — infix ILIKE search)
    op.create_index(
        "ix_market_groups_title_trgm", "market_groups", ["title"],
        postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_markets_question_trgm", "markets", ["question"],
        postgresql_using="gin", postgresql_ops={"question": "gin_trgm_ops"},
    )

    # 5) partial-unique on (source, source_event_id) — mirrors 0004's markets index
    op.create_index(
        "ix_market_groups_source_source_event_id", "market_groups",
        ["source", "source_event_id"], unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )

    # 6) catalog filter/sort indexes
    op.create_index("ix_market_groups_category", "market_groups", ["category"])
    op.create_index("ix_markets_category", "markets", ["category"])
    op.create_index("ix_markets_status_volume_24hr", "markets", ["status", "volume_24hr"])
    op.create_index("ix_odds_snapshots_outcome_id_snapshot_at", "odds_snapshots",
                    ["outcome_id", "snapshot_at"])


def downgrade() -> None:
    # Exact reverse order. Indexes → FK/column → table. Leave pg_trgm (Pitfall 3).
    op.drop_index("ix_odds_snapshots_outcome_id_snapshot_at", table_name="odds_snapshots")
    op.drop_index("ix_markets_status_volume_24hr", table_name="markets")
    op.drop_index("ix_markets_category", table_name="markets")
    op.drop_index("ix_market_groups_category", table_name="market_groups")
    op.drop_index("ix_market_groups_source_source_event_id", table_name="market_groups")
    op.drop_index("ix_markets_question_trgm", table_name="markets")
    op.drop_index("ix_market_groups_title_trgm", table_name="market_groups")
    op.drop_index("ix_markets_group_id", table_name="markets")
    op.drop_constraint("fk_markets_group_id", "markets", type_="foreignkey")
    op.drop_column("markets", "group_item_title")
    op.drop_column("markets", "group_id")
    op.drop_index("ix_market_groups_slug", table_name="market_groups")
    op.drop_table("market_groups")
    # Deliberately NOT dropping pg_trgm — see Pitfall 3 (data-safety: another object may use it).
```
**Note A (`status` on `market_groups`):** CONTEXT.md's required column set does not include `status`,
and EVT-06 says event status is **derived** from constituent markets, "never stored as an
authoritative winning-outcome column." The `(status, volume_24hr)` index in the spec is on **`markets`**,
not `market_groups`. **Recommendation:** do NOT add a `status` column to `market_groups` (it would
invite a stored-status anti-pattern that Phase 15 explicitly forbids). The example above shows it only
to flag the decision — drop it unless the planner has a concrete catalog-sort need that can't derive.
This is an `[ASSUMED]` recommendation (A3) — confirm with the planner.

### Pattern 2: ORM model + relationship (lazy="raise" discipline)
**What:** The `MarketGroup` class and the bidirectional relationship.
**When to use:** SC#4 round-trip. Mirrors the existing `Market.outcomes` / `Outcome.market` pair.
**Example:**
```python
# Source: backend/app/markets/models.py (existing Market/Outcome style + lazy="raise" discipline)
#       + SQLAlchemy 2.0 docs (Index in __table_args__ with postgresql_using/ops/where)
from sqlalchemy import ForeignKey, Index, Text, String, func, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class MarketGroup(Base):
    __tablename__ = "market_groups"
    __table_args__ = (
        CheckConstraint(
            f"source IN ({', '.join(repr(s.value) for s in MarketSourceEnum)})",
            name="ck_market_groups_source",
        ),
        # Declared here too so Base.metadata matches the migration (existing-codebase convention).
        Index("ix_market_groups_title_trgm", "title",
              postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_market_groups_source_source_event_id", "source", "source_event_id",
              unique=True, postgresql_where=text("source_event_id IS NOT NULL")),
        Index("ix_market_groups_category", "category"),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="HOUSE")
    source_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,    # CONVENTIONS §2 ghost column
    )

    markets: Mapped[list[Market]] = relationship(
        back_populates="group",
        lazy="raise",            # existing discipline — explicit eager-load at call sites
        # NOTE: do NOT use cascade="all, delete-orphan" here. The FK is ON DELETE SET NULL;
        # deleting a group must orphan (not delete) its children (additive seam). See Pitfall 5.
    )


# --- additions to the existing Market class ------------------------------------
class Market(Base):
    # ... existing columns ...
    group_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    group_item_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    group: Mapped[MarketGroup | None] = relationship(
        back_populates="markets", lazy="raise",
    )
    # ... existing relationships (outcomes, odds_snapshots) unchanged ...
    # Add the two GIN/sort indexes to Market.__table_args__:
    #   Index("ix_markets_question_trgm", "question",
    #         postgresql_using="gin", postgresql_ops={"question": "gin_trgm_ops"}),
    #   Index("ix_markets_category", "category"),
    #   Index("ix_markets_status_volume_24hr", "status", "volume_24hr"),
```

### Pattern 3: Migration test via schema introspection
**What:** Prove the migration applied (table, columns, FK ondelete, indexes incl. GIN + partial).
**When to use:** SC#1, SC#3. Direct precedent: `tests/auth/test_migration_0002.py`,
`tests/wallet/test_migration_0003.py`.
**Example:**
```python
# Source: backend/tests/auth/test_migration_0002.py (inspect via conn.run_sync) — VERBATIM pattern
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Inspector
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_market_groups_table_columns(engine: AsyncEngine) -> None:
    def _cols(sync_conn):
        insp: Inspector = inspect(sync_conn)
        return {c["name"] for c in insp.get_columns("market_groups")}
    async with engine.connect() as conn:
        cols = await conn.run_sync(_cols)
    assert {"id", "title", "source", "source_event_id", "category",
            "slug", "created_at", "updated_at", "tenant_id"}.issubset(cols)


async def test_markets_group_id_fk_set_null(engine: AsyncEngine) -> None:
    def _fks(sync_conn):
        return list(inspect(sync_conn).get_foreign_keys("markets"))
    async with engine.connect() as conn:
        fks = await conn.run_sync(_fks)
    fk = next(f for f in fks if "group_id" in f.get("constrained_columns", []))
    assert fk["referred_table"] == "market_groups"
    assert fk.get("options", {}).get("ondelete") == "SET NULL"


async def test_pg_trgm_and_gin_indexes_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        ext = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
        assert ext.scalar_one_or_none() == 1
        # GIN trigram index presence (pg_indexes.indexdef contains 'gin' + 'gin_trgm_ops')
        idx = await conn.execute(text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ix_markets_question_trgm'"))
        ddl = idx.scalar_one()
        assert "gin" in ddl.lower() and "gin_trgm_ops" in ddl


async def test_partial_unique_has_where_clause(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        idx = await conn.execute(text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ix_market_groups_source_source_event_id'"))
        ddl = idx.scalar_one()
        assert "unique" in ddl.lower()
        assert "where" in ddl.lower() and "source_event_id" in ddl.lower()
```
> **GIN/partial introspection caveat:** SQLAlchemy's `inspect(...).get_indexes()` does NOT always
> surface the `gin_trgm_ops` opclass or the partial `WHERE` predicate in a structured field across
> dialects. The robust check is to read `pg_indexes.indexdef` (the raw DDL string) via `text()`, as
> shown above — that is the source of truth and avoids dialect-introspection gaps. [ASSUMED A4]

### Pattern 4: ORM round-trip + reversibility test
**What:** SC#4 (parent + ≥2 children via async session) and SC#1 (real `downgrade()`).
**Example:**
```python
# Source: backend/tests/markets/test_models.py (selectinload round-trip + lazy='raise' assertion)
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import sqlalchemy.exc

async def test_market_group_round_trips_two_children(async_session) -> None:
    from app.markets.models import Market, MarketGroup, generate_slug
    grp = MarketGroup(title="2028 Presidential Election", source="HOUSE",
                      slug=generate_slug("2028 Presidential Election"))
    async_session.add(grp)
    await async_session.flush()
    m1 = Market(question="Will A win?", slug=generate_slug("A"),
                resolution_criteria="...", deadline=..., group_id=grp.id,
                group_item_title="Candidate A")
    m2 = Market(question="Will B win?", slug=generate_slug("B"),
                resolution_criteria="...", deadline=..., group_id=grp.id,
                group_item_title="Candidate B")
    async_session.add_all([m1, m2])
    await async_session.flush()

    stmt = (select(MarketGroup).where(MarketGroup.id == grp.id)
            .options(selectinload(MarketGroup.markets)))
    loaded = (await async_session.execute(stmt)).scalar_one()
    assert len(loaded.markets) == 2
    assert {m.group_item_title for m in loaded.markets} == {"Candidate A", "Candidate B"}

async def test_markets_group_lazy_raise(async_session) -> None:
    # mirror TestLazyRaise in test_models.py — accessing .group without eager-load raises
    ...
```
For the **reversibility** test, use the Alembic API to run `downgrade("0010_phase12_resolution_stakes")`
then `upgrade("head")` against a throwaway connection, OR assert the migration file defines a non-empty
`downgrade()` that drops exactly what `upgrade()` created. The lightest reliable proof is a dedicated
test that runs `command.downgrade(cfg, "-1")` then `command.upgrade(cfg, "head")` against the
testcontainer — but note the session `engine` fixture is already at head; isolate this on its own
connection/transaction to avoid disturbing the shared session schema. [ASSUMED A5 — planner picks the
exact harness]

### Anti-Patterns to Avoid
- **Using the filename as `down_revision`** — it is `"0010_phase12_resolution_stakes"` (the in-file
  `revision` id), NOT `"0010_phase12_resolution_and_stake_limits"`. Using the filename silently breaks
  the chain (Alembic resolves by revision id).
- **Branching the head** — do NOT create a second head. `0011` chains off the single existing head.
- **`cascade="all, delete-orphan"` on `MarketGroup.markets`** — would delete child markets when a group
  is removed, contradicting the `ON DELETE SET NULL` additive seam and risking financial data loss
  (markets carry bets/ledger). Children must orphan, not cascade.
- **Creating GIN index before `pg_trgm`** — `gin_trgm_ops` does not exist until the extension is
  created; ordering matters within `upgrade()`.
- **Adding a stored `status`/`winning_outcome` to `market_groups`** — EVT-06 forbids it; event status
  is derived in Phase 15.
- **A money-named column on `market_groups`** — would trip `scripts/lint_money_columns.py` (it walks
  `**/versions/*.py` too). `market_groups` has no money columns; keep it that way.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Infix substring search | Custom `LIKE '%...%'` seq-scan + manual ranking | `pg_trgm` GIN + `ILIKE` | Bundled, indexed, typo-tolerant via `similarity()`; B-tree/tsvector can't do infix |
| Idempotent event upsert key | App-level "does this event exist" SELECT-then-INSERT | partial-unique `(source, source_event_id) WHERE source_event_id IS NOT NULL` | Exact precedent: 0004's `(source, source_market_id)` partial-unique; lets Phase 14 use `ON CONFLICT` |
| Migration ↔ ORM index drift | Hand-syncing two definitions by memory | Declare indexes in BOTH `__table_args__` and the migration (matching existing pattern) | The repo's convention; keeps `Base.metadata` truthful for future autogenerate |
| Binary-only enforcement | New CHECK/trigger for "events" | Reuse existing `trg_binary_outcomes_only` on `outcomes` (unchanged) | Each child is still a 2-outcome binary; grouping is one level up |
| Schema introspection in tests | Parsing `\d` output / regexing DDL by hand | `inspect(conn).get_columns/indexes/foreign_keys` + `pg_indexes.indexdef` for GIN/partial | Established test pattern (`test_migration_0002/0003`) |

**Key insight:** Almost nothing here is novel — every primitive (partial-unique index, tenant_id ghost
column, UUID PK with `gen_random_uuid()`, `selectinload` round-trip, migration-introspection test) has
a working precedent in this codebase. The phase's risk is in **chaining and ordering correctness**
(revision id, extension-before-index, FK ondelete, no cascade), not in inventing patterns.

## Common Pitfalls

### Pitfall 1: Revision-id length truncation (varchar(32))
**What goes wrong:** A descriptive `revision` id longer than 32 chars fails to APPLY with
`StringDataRightTruncation` — `alembic_version.version_num` is `varchar(32)`.
**Why it happens:** Documented in `0010`'s own header: the filename `0010_phase12_resolution_and_stake_limits`
(40 chars) was shortened to the revision id `0010_phase12_resolution_stakes` (30 chars).
**How to avoid:** Keep the `revision` id ≤ 32 chars. `"0011_phase13_market_groups"` is 26 chars — safe.
The FILENAME may be longer (Alembic decouples filename from id), but keep them equal here for clarity.
**Warning signs:** Migration applies fine locally on a fresh DB but you chose a long id "to be
descriptive."

### Pitfall 2: Wrong `down_revision` (filename vs revision id)
**What goes wrong:** Setting `down_revision = "0010_phase12_resolution_and_stake_limits"` (the filename
stem) makes Alembic unable to find the parent → `alembic upgrade head` errors or creates a detached
revision.
**Why it happens:** The filename and the in-file `revision` string differ for 0010 specifically.
**How to avoid:** `down_revision = "0010_phase12_resolution_stakes"`. [VERIFIED: `uv run alembic heads`
returned `0010_phase12_resolution_stakes (head)`; `alembic history` shows it as the lone head.]
**Warning signs:** `alembic heads` shows two heads after authoring, or `upgrade` complains about a
missing revision.

### Pitfall 3: Dropping `pg_trgm` in downgrade
**What goes wrong:** `DROP EXTENSION pg_trgm` in `downgrade()` can fail (other objects depend on it) or
unexpectedly remove functionality another migration/feature relies on.
**Why it happens:** Extensions are database-global, not migration-scoped. Once `CREATE EXTENSION IF NOT
EXISTS` runs, you can't know it was THIS migration that first created it.
**How to avoid:** **Do NOT drop `pg_trgm` in `downgrade()`.** Drop only the indexes/columns/table this
migration created. Document the choice in the migration docstring. (CONTEXT.md explicitly flags this as
a documented decision: "prefer dropping what the migration created" — but `pg_trgm` is the safe
exception because it's idempotent and shared.) The GIN indexes are dropped; the extension is harmless
to leave. [ASSUMED A1 — but strongly recommended; flag for planner confirmation.]
**Warning signs:** `downgrade()` errors with "cannot drop extension pg_trgm because other objects
depend on it."

### Pitfall 4: Savepoint discipline in integration tests
**What goes wrong:** A test that asserts an `IntegrityError` (e.g., duplicate partial-unique key) leaves
the session-scoped outer transaction in an aborted state → every subsequent test fails with
`InFailedSQLTransactionError`.
**Why it happens:** `async_session` is one connection + outer transaction rolled back at teardown
(`tests/conftest.py` lines 187-210), shared across a test via `loop_scope="session"`.
**How to avoid:** Wrap each statement-expected-to-raise in `async with async_session.begin_nested()`
(savepoint). Direct precedent: `test_migration_0003.py` and `test_models.py::TestCheckConstraints`.
**Warning signs:** One failing assertion cascades into many `current transaction is aborted` failures.

### Pitfall 5: FK ondelete cascade vs SET NULL (financial-data safety)
**What goes wrong:** If `Market.group_id` were `ON DELETE CASCADE` (or the relationship had
`delete-orphan`), deleting a `market_groups` row would delete child markets — which carry bets, odds
snapshots, and ledger-linked settlement state. Catastrophic data loss.
**Why it happens:** Copy-paste from `Outcome.market_id` (which IS `CASCADE`, correctly — outcomes are
owned by their market).
**How to avoid:** `Market.group_id` FK = `ondelete="SET NULL"`; relationship has NO cascade. Deleting a
group orphans its children back to standalone. CONTEXT.md §specifics confirms: "likely `SET NULL` so
deleting a group doesn't cascade-delete child markets." [VERIFIED against CONTEXT.md intent.]
**Warning signs:** A group-deletion test removes child markets.

### Pitfall 6: `alembic` run inside container vs host URL (CONVENTIONS §5)
**What goes wrong:** Running `alembic upgrade head` with a `localhost` `DATABASE_URL_SYNC` from inside
a container hits the wrong host.
**Why it happens:** `env.py` reads `DATABASE_URL_SYNC` (psycopg2) — host-side it's `localhost`,
container-side it must be the service name.
**How to avoid:** Run via `docker compose exec backend uv run alembic upgrade head` (CONVENTIONS §5),
or rely on the testcontainers `engine` fixture which rewrites both URLs before `command.upgrade`
(`tests/conftest.py` lines 152-178). Tests are unaffected; only manual/CI invocation needs care.

### Pitfall 7: `slug` NOT NULL with no value source in-phase
**What goes wrong:** Declaring `market_groups.slug` `NOT NULL` is correct for the final schema, but
since Phase 13 writes no rows, ensure no migration data-seed tries to insert a group without a slug.
Phase 14 (sync) and Phase 16 (admin create) populate it.
**Why it happens:** Phase 9's `tenant_config` migration seeds a singleton row — a tempting pattern to
copy. **Do NOT seed `market_groups`** (CONTEXT.md: "Phase 13 writes no application logic... no seed
data").
**How to avoid:** No `INSERT` in `0011`. The round-trip TEST creates rows with explicit slugs via
`generate_slug`.

## Runtime State Inventory

> This is a greenfield additive-schema phase (new table + nullable columns), not a rename/refactor.
> A lightweight inventory is included for completeness because the phase touches an existing table
> (`markets`) and a live migration chain.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None requiring migration.** No backfill — `markets.group_id`/`group_item_title` default NULL for all existing rows; existing markets remain standalone. Verified by CONTEXT.md "No backfill" + SC#1. | None (additive nullable) |
| Live service config | **None.** No Celery beat schedule, no external service config changes in Phase 13. The Gamma `/events` sync that writes groups is Phase 14. | None |
| OS-registered state | **None.** No Task Scheduler / systemd / pm2 registrations involve this phase. | None |
| Secrets/env vars | **None.** No new env vars. `DATABASE_URL`/`DATABASE_URL_SYNC` already exist. `pg_trgm` needs no secret. | None |
| Build artifacts | **None.** Pure Python ORM + SQL migration; no compiled artifacts, no package rename. `app/markets/__init__.py` export list and `alembic/env.py` import list must be updated (code edits, not artifacts). | Update `__all__` + env.py import |

**Migration-chain state (the one live "runtime" concern):** `alembic_version.version_num` currently
holds `0010_phase12_resolution_stakes` on any migrated DB. After `0011`, it becomes
`0011_phase13_market_groups`. The testcontainer `engine` fixture runs `upgrade head` fresh each
session, so existing test DBs are not a concern; only a long-lived dev/staging DB advances its
`version_num` on first `upgrade`.

## Code Examples

All actionable code is in **Architecture Patterns** above (Patterns 1-4), sourced from in-repo
precedent + official SQLAlchemy docs. No additional examples needed.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Multi-outcome deferred to v2 (v1.0 `MKT-08` deferral) | Event-of-binaries: N binary markets under one `market_groups` row | 2026-06-04 (STATE.md decision) | Reuses binary model + settlement unchanged; this phase is the schema gate |
| `markets`-only catalog with global top-25 `/markets` poll | `market_groups` + per-category curated catalog (later phases) | v1.2 | Phase 13 lays the indexes; Phase 14 fills them |
| Unindexed `ILIKE` (or none) | `pg_trgm` GIN + infix `ILIKE` | v1.2 (this migration) | Indexed substring + typo-tolerant search at curated scale |

**Deprecated/outdated:** Nothing deprecated by this phase. The binary-only `trg_binary_outcomes_only`
trigger and all existing CHECK constraints are explicitly retained.

## Assumptions Log

> Claims tagged `[ASSUMED]` — the planner / discuss-phase should confirm these before locking.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `downgrade()` should NOT drop `pg_trgm` (leave it; drop only this migration's indexes/table) | Pitfall 3 | Low — leaving a bundled extension is harmless; dropping it could break a future feature. Reversibility (SC#1) is still satisfied by restoring the pre-0011 *schema objects*. If reviewer insists on literal "exact pre-state," wrap `DROP EXTENSION IF EXISTS pg_trgm` in a guarded check — but recommended NOT to. |
| A2 | `MarketGroup` column set = id, title, source, source_event_id, category, slug, created_at, updated_at, tenant_id (no `status`, no money) | Pattern 1/2 | Low — CONTEXT.md grants column set to Claude's discretion as long as required ones exist. Adding/removing optional columns is a future additive migration. |
| A3 | Do NOT add a stored `status` column to `market_groups` (EVT-06 derives event status) | Pattern 1 Note A | Medium — if Phase 16 catalog sort genuinely needs a denormalized group status that can't derive cheaply, a later additive column is fine. But storing an authoritative status now risks the EVT-06 anti-pattern. |
| A4 | GIN opclass + partial WHERE are best verified via `pg_indexes.indexdef` raw DDL, not `get_indexes()` structured fields | Pattern 3 | Low — purely a test-implementation detail; raw DDL check is strictly more reliable. |
| A5 | Reversibility proof runs `downgrade -1` → `upgrade head` on an isolated connection (not the shared session engine) | Pattern 4 | Low — alternative is a static assertion that `downgrade()` is non-empty + mirrors `upgrade()`. Planner picks the harness. |
| A6 | Index names follow the existing `ix_<table>_<cols>` convention (e.g. `ix_markets_question_trgm`) | Pattern 1 | None — naming is cosmetic; CONTEXT.md grants index naming to Claude's discretion. |

## Open Questions (RESOLVED)

> Both resolved by plan decisions (13-01 / 13-02): (1) `market_groups.category` IS included and
> indexed (`ix_market_groups_category`), leaving Phase 16 to choose its read shape; (2) the SC#1
> reversibility test does a true `command.downgrade` → `command.upgrade` cycle, with a static
> "downgrade mirrors upgrade" assertion as the documented fallback if the shared session loop is flaky.

1. **Should `market_groups` carry a denormalized `category` AND should the catalog sort use it?**
   - What we know: CONTEXT.md requires a `category` index on `market_groups` AND on `markets`. EVT-06
     says event *status* is derived, but says nothing forbidding a denormalized *category* on the
     group (category is a stable attribute, not a settlement-derived state).
   - What's unclear: whether Phase 16's catalog browse reads category from the group row or aggregates
     from children.
   - Recommendation: include `market_groups.category` (cheap, indexed, spec-required) and let Phase 16
     decide its read shape. Already in the recommended column set.

2. **Exact reversibility-test harness (live downgrade vs static assertion).**
   - What we know: `command.downgrade`/`command.upgrade` work against the testcontainer; the session
     `engine` fixture is already at head.
   - What's unclear: whether to spin a second isolated DB/connection for a true down→up cycle, or
     assert the `downgrade()` body statically.
   - Recommendation: a true down→up cycle on its own connection is the strongest SC#1 proof; if that
     proves flaky under the shared session loop, fall back to a static "downgrade mirrors upgrade"
     assertion plus the offline-SQL render (`alembic upgrade --sql 0010:0011`). Planner's call.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 16 | migration apply + all tests | ✓ (testcontainers `postgres:16-alpine`) | 16 | — |
| `pg_trgm` | GIN trigram indexes | ✓ (bundled in PG 16; enabled by the migration) | bundled | — |
| Docker | testcontainers + `docker compose exec` alembic | ✓ (repo convention; `cd backend && uv run pytest` uses it) | — | — |
| SQLAlchemy | ORM + `Index()` DDL | ✓ | 2.0.50 | — |
| Alembic | migration runner | ✓ | 1.18.4 | — |
| uv | dependency/venv management | ✓ (`uv run` verified working) | — | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — all phase dependencies are present and verified.

## Project Constraints (from CLAUDE.md + CONVENTIONS.md)

| Constraint | Source | Phase 13 application |
|------------|--------|----------------------|
| Work on `gsd/phase-13-{slug}` branch, never `main`; 1 PR/phase; only Pol merges | CLAUDE.md | Branch + single PR for this phase |
| Product/code/commits in English; conversation Spanish | CLAUDE.md | All identifiers/docstrings English |
| Money columns use `Mapped[Money]` (Numeric(18,4)); lint walks `**/models.py` + `**/versions/*.py` | CONVENTIONS §1 | `market_groups` has NO money columns → trivially green; verify no money-named column slips in |
| `tenant_id` ghost column on every market table, default `TENANT_ID_DEFAULT` | CONVENTIONS §2 | `market_groups` IS a market table → carries `tenant_id` |
| Alembic runs via sync engine (`DATABASE_URL_SYNC`); real `upgrade()` + `downgrade()` | CONVENTIONS §5 | Migration is reversible (SC#1); run via `docker compose exec` |
| UUID PKs via `gen_random_uuid()` server_default; timestamps via `func.now()` | CONVENTIONS §5 | `market_groups.id` + created_at/updated_at follow the pattern |
| `Settings()` only — never `os.getenv`; `get_settings()` for defaults | CONVENTIONS §7 | `tenant_id` default via `get_settings().TENANT_ID_DEFAULT` (existing models' pattern) |
| structlog only, no `print()` | CONVENTIONS §8 | N/A — migration has no logging; if any, use Alembic's logger |
| `lazy="raise"` relationship discipline | models.py established pattern | New `MarketGroup.markets` + `Market.group` use `lazy="raise"` |

## Validation Architecture

> `workflow.nyquist_validation` was not found set to `false` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + testcontainers (Postgres 16) |
| Config file | `backend/pyproject.toml` / `backend/pytest.ini` (existing); fixtures in `backend/tests/conftest.py` |
| Quick run command | `cd backend && uv run pytest tests/markets/ -x` |
| Full suite command | `cd backend && uv run pytest` |
| Money lint gate | `cd backend && uv run python scripts/lint_money_columns.py` (must stay green) |

### Phase Requirements → Test Map
| Req / SC | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| SC#1 (migration applies + reversible) | `0011` upgrades clean; `downgrade()` restores pre-0011 schema | integration (migration) | `cd backend && uv run pytest tests/markets/test_migration_0011.py -x` | ❌ Wave 0 |
| SC#1 (single head, correct down_revision) | `0011.down_revision == "0010_phase12_resolution_stakes"`; one head | unit/integration | `cd backend && uv run pytest tests/markets/test_migration_0011.py -k chain -x` | ❌ Wave 0 |
| SC#2 (zero behavior change) | standalone `group_id IS NULL` market reads/bets/settles unchanged | integration (regression) | `cd backend && uv run pytest tests/markets/test_models.py tests/bets/ tests/settlement/ -x` | ✅ (existing suites — lean on them) + 1 new assertion |
| SC#3 (pg_trgm + 6 indexes) | extension present; all named indexes incl. GIN opclass + partial WHERE | integration (introspection) | `cd backend && uv run pytest tests/markets/test_migration_0011.py -k index -x` | ❌ Wave 0 |
| SC#4 (ORM round-trip ≥2 children) | parent group loads 2 children via `selectinload`; `lazy="raise"` enforced | integration (ORM) | `cd backend && uv run pytest tests/markets/test_models.py -k group -x` | ❌ Wave 0 |
| EVT-01 (additive, binary model unchanged) | `MKT-08` trigger still fires; existing market columns/CHECKs intact | integration (regression) | `cd backend && uv run pytest tests/markets/test_models.py -x` | ✅ (existing `TestBinaryOnlyTrigger`, `TestCheckConstraints`) |
| Lint | no money-named column on `market_groups`; lint green | static | `cd backend && uv run python scripts/lint_money_columns.py` | ✅ (`tests/test_money_lint.py`) |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/markets/ -x` + `uv run python scripts/lint_money_columns.py`
- **Per wave merge:** `cd backend && uv run pytest tests/markets/ tests/bets/ tests/settlement/`
- **Phase gate:** Full suite (`cd backend && uv run pytest`) green + money-lint green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/markets/test_migration_0011.py` — covers SC#1 (apply + reversibility + chain) and
      SC#3 (pg_trgm + all 6 indexes via `pg_indexes.indexdef` introspection).
- [ ] Add to `backend/tests/markets/test_models.py` — a `MarketGroup` round-trip test (SC#4) + a
      `Market.group` `lazy="raise"` assertion + a `group_id IS NULL` standalone-unchanged regression
      assertion (SC#2).
- [ ] (Optional) A focused SC#2 regression that places a bet + settles a standalone `group_id IS NULL`
      market end-to-end — but the existing `tests/bets/` + `tests/settlement/` suites already exercise
      these paths; a fresh-table-add does not alter them, so re-running them green IS the proof. Prefer
      leaning on existing suites over duplicating.
- Framework install: none — testcontainers + pytest-asyncio already wired (`tests/conftest.py`).

*Existing test infrastructure covers SC#2/EVT-01 regression almost entirely; the only NEW test files
are the `0011` migration introspection + the `MarketGroup` ORM round-trip.*

## Security Domain

> `security_enforcement` not set to `false` — section included. This is a schema-only phase with no
> auth/session/input-handling surface, so most ASVS categories are N/A.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface added |
| V3 Session Management | no | No session surface |
| V4 Access Control | no | No new endpoint/authorization in Phase 13 (admin event ops are Phase 16) |
| V5 Input Validation | partial | No HTTP input in-phase. The one injection-adjacent concern: NEVER interpolate a search term into SQL — Phase 16 must use `Market.question.ilike("%" || :q || "%")` parameterized (the GIN index this phase creates supports it). Documented here as a forward constraint. |
| V6 Cryptography | no | No crypto; no secrets touched |

### Known Threat Patterns for {Postgres + SQLAlchemy schema}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via future search term (Phase 16 consumer) | Tampering | Parameterized `ilike` / bound params — never f-string the term. The price-history window allowlist (`service.py` lines 27-33) is the in-repo precedent for "validate, don't interpolate." |
| Accidental data loss via FK cascade | Tampering / DoS | `ON DELETE SET NULL` on `Market.group_id` (Pitfall 5) — children orphan, never delete |
| Migration applied with session-level GUC leak | Info disclosure (v2) | `SET LOCAL` only doctrine (CONVENTIONS §4) — dormant in v1, no GUC use in this migration |
| Tenant isolation regression | Info disclosure (v2) | `tenant_id` ghost column present on `market_groups` (CONVENTIONS §2) — the v2 RLS seam |

## Sources

### Primary (HIGH confidence)
- **In-repo precedent (VERIFIED via Read):**
  - `backend/alembic/versions/0004_phase6_polymarket_sync.py` — partial-unique index pattern (`postgresql_where`)
  - `backend/alembic/versions/0003_phase4_markets.py` — `MKT-08` binary trigger (on `outcomes`), table-creation style
  - `backend/alembic/versions/0009_phase10_tenant_config.py` — `create_table` with tenant_id + timestamps
  - `backend/alembic/versions/0010_phase12_resolution_and_stake_limits.py` — revision-id-length landmine; style template
  - `backend/app/markets/models.py` — ORM `Mapped[...]` style, `lazy="raise"`, tenant_id ghost column
  - `backend/app/markets/service.py` — `get_market_by_slug` (SC#2 read path), parameterized-window precedent
  - `backend/tests/conftest.py` — testcontainers engine fixture (runs `upgrade head`), `async_session` savepoint discipline
  - `backend/tests/auth/test_migration_0002.py`, `backend/tests/wallet/test_migration_0003.py` — migration-introspection test pattern
  - `backend/tests/markets/test_models.py` — `selectinload` round-trip + `lazy="raise"` assertion pattern
  - `backend/scripts/lint_money_columns.py` — money-lint walks `**/versions/*.py`
- **`uv run alembic heads` / `alembic history` (VERIFIED):** single head = `0010_phase12_resolution_stakes`; branched `0004_*` already merged at `0006_merge_phase5_phase6`.
- **`uv run python -c "import sqlalchemy, alembic"` (VERIFIED):** SQLAlchemy 2.0.50, Alembic 1.18.4.
- **SQLAlchemy 2.0 PostgreSQL dialect docs** (docs.sqlalchemy.org/en/20/dialects/postgresql.html) — `Index(..., postgresql_using="gin", postgresql_ops={"col": "gin_trgm_ops"})`, `postgresql_where=...`, `postgresql_ops` keys are column `.key` names. [CITED]

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` + `.planning/research/SUMMARY.md` — prior v1.2 research; confirms the
  exact `op.create_index(..., postgresql_using="gin", postgresql_ops={"question": "gin_trgm_ops"})`
  form and cites Postgres pgtrgm.html. Same-file-style reference to `0004_phase6_polymarket_sync.py`.
- `.planning/STATE.md` (2026-06-04) — "event-of-binaries" decision; binary-only DB CHECK does NOT change.
- `.planning/REQUIREMENTS.md` — EVT-01 scope; Phase 13 owns exactly one requirement.

### Tertiary (LOW confidence)
- None — all claims are backed by in-repo verification or official docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified via `uv run`; pg_trgm is bundled; zero new deps confirmed by CONTEXT.md.
- Architecture / migration chain: HIGH — `alembic heads` verified the single head and exact down_revision; every DDL pattern has in-repo precedent.
- Index syntax: HIGH — confirmed against official SQLAlchemy 2.0 docs AND existing `0004` migration.
- Pitfalls: HIGH — revision-length, down_revision-id, FK-cascade, savepoint, and trigger-compatibility pitfalls are all derived from concrete in-repo evidence (0010 docstring, alembic CLI, 0003 trigger, conftest).
- Test patterns: HIGH — direct precedent in `test_migration_0002/0003` and `test_models.py`.
- The `pg_trgm`-drop and column-set choices are `[ASSUMED]` (A1, A2, A3) — recommended with rationale, flagged for planner confirmation.

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (stable — pinned SQLAlchemy 2.0.50 / Alembic 1.18.4 / PG 16; in-repo patterns won't drift within the milestone)
