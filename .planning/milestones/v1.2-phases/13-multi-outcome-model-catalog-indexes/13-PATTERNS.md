# Phase 13: Multi-outcome Model & Catalog Indexes - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 5 (2 NEW, 3 MODIFY)
**Analogs found:** 5 / 5 (every file has an exact in-repo analog — confirmed against the codebase, not just RESEARCH.md)

> This is a pure-additive Postgres/SQLAlchemy/Alembic backend phase: **no UI, no API, no service logic.**
> Every pattern already exists in this repo. The risk is **chaining/ordering correctness**
> (revision id ≤ 32 chars, `pg_trgm` before GIN, FK `SET NULL` not CASCADE, no relationship cascade),
> not inventing patterns. All excerpts below are copied from the live files with verified line numbers.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/alembic/versions/0011_phase13_market_groups.py` | migration | transform (DDL) | `0009_phase10_tenant_config.py` (create_table+tenant_id) + `0004_phase6_polymarket_sync.py` (partial-unique index) + `0010_phase12_resolution_and_stake_limits.py` (style/revision-id) | exact (composite) |
| `backend/app/markets/models.py` | model (ORM) | CRUD | same-file `Market`/`Outcome` classes (`lazy="raise"`, tenant_id ghost, UUID PK) | exact |
| `backend/app/markets/__init__.py` | config (barrel export) | n/a | same-file existing `__all__` | exact |
| `backend/alembic/env.py` | config (model registration) | n/a | same-file line 32 import | exact |
| `backend/tests/markets/test_migration_0011.py` (NEW) | test (introspection) | request-response | `tests/auth/test_migration_0002.py` (inspect via `run_sync`) + `tests/wallet/test_migration_0003.py` (savepoint + raw `text()` DDL introspection) | exact |
| `backend/tests/markets/test_models.py` (MODIFY) | test (ORM round-trip) | CRUD | same-file `TestMarketCreation` (`selectinload`) + `TestLazyRaise` + `TestCheckConstraints` (`begin_nested`) | exact |

> **Analog location note:** the migration-introspection precedent lives in `tests/auth/` and
> `tests/wallet/` — there is NO `tests/markets/test_migration_*.py` yet. The NEW file
> `tests/markets/test_migration_0011.py` is the first migration test under `tests/markets/`;
> copy the *pattern* from the auth/wallet files, place it in `tests/markets/`.

---

## Pattern Assignments

### `backend/alembic/versions/0011_phase13_market_groups.py` (NEW — migration, DDL transform)

Three analogs compose this one migration. Copy each section from its source.

#### Source A — header + revision-id discipline: `0010_phase12_resolution_and_stake_limits.py`

**Revision-id landmine** (lines 22-44) — the single most important copy-target. The revision id MUST
be ≤ 32 chars (`alembic_version.version_num` is `varchar(32)`), and `down_revision` MUST be the
**revision id** `"0010_phase12_resolution_stakes"`, NOT the filename stem:

```python
# Source: backend/alembic/versions/0010_phase12_resolution_and_stake_limits.py:26-44
# NOTE: the ``revision`` identifier is ``0010_phase12_resolution_stakes`` (30 chars) — the
# ``alembic_version.version_num`` column is ``varchar(32)``, so the longer descriptive name
# ``0010_phase12_resolution_and_stake_limits`` (40 chars) would fail to APPLY with a
# ``StringDataRightTruncation``. The FILENAME keeps the descriptive form (alembic decouples the
# filename from the revision id); only the in-table id is shortened.

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_phase12_resolution_stakes"
down_revision: Union[str, Sequence[str], None] = "0009_phase10_tenant_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

**Adaptation for 0011:**
- `revision = "0011_phase13_market_groups"` (26 chars — safe).
- `down_revision = "0010_phase12_resolution_stakes"` (the REVISION ID — verified the single head;
  do NOT use the filename `0010_phase12_resolution_and_stake_limits`).
- Keep `from __future__ import annotations` first; import `sqlalchemy as sa`, `from alembic import op`,
  `from sqlalchemy.dialects import postgresql`.

#### Source B — `create_table` with UUID PK + timestamps + tenant_id ghost: `0009_phase10_tenant_config.py`

**Table-creation form** (lines 32-70) — copy the column scaffolding (UUID PK `gen_random_uuid()`,
`TIMESTAMP(timezone=True)` + `NOW()`, the **`tenant_id` ghost column**, the `TENANT_DEFAULT` literal):

```python
# Source: backend/alembic/versions/0009_phase10_tenant_config.py:32-70
# Pitfall 10: same literal as 0001/0002/0004 — single source of truth for the v1 default tenant UUID.
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"

def upgrade() -> None:
    op.create_table(
        "tenant_config",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("brand_name", sa.Text, nullable=False),
        # ... domain columns ...
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
        sa.UniqueConstraint("tenant_id", name="tenant_config_tenant_id_key"),
    )
```

> The `markets` CHECK-constraint literal form is identical in `0003_phase4_markets.py:88-95`
> (`sa.CheckConstraint("source IN ('HOUSE', 'POLYMARKET')", name="ck_markets_source")`) and its
> `source` column uses `server_default=sa.text("'HOUSE'")` (`0003:47-52`). Mirror these for
> `market_groups.source` + `ck_market_groups_source`.

**Adaptation for 0011 `market_groups`:** required columns = `id` (UUID PK, `gen_random_uuid()`),
`title` (`sa.Text`, NOT NULL), `source` (`sa.String(20)`, NOT NULL, `server_default=sa.text("'HOUSE'")`),
`source_event_id` (`sa.String(200)`, nullable), `category` (`sa.String(100)`, nullable), `slug`
(`sa.String(100)`, NOT NULL — unique via a dedicated index, mirroring `ix_markets_slug` at `0003:97`),
`created_at`/`updated_at` (`TIMESTAMP(tz=True)` + `NOW()`), `tenant_id` ghost column, and
`sa.CheckConstraint("source IN ('HOUSE', 'POLYMARKET')", name="ck_market_groups_source")`.
**Do NOT add a `status` or any `winning_outcome` column** (EVT-06 — event status is derived in Phase 15;
RESEARCH A3). **Do NOT add any money-named column** (would trip `scripts/lint_money_columns.py`).
**Do NOT seed a row** (unlike `0009:74-80`'s singleton seed — Phase 13 writes no data; Pitfall 7).
Then `op.create_index("ix_market_groups_slug", "market_groups", ["slug"], unique=True)`.

#### Source C — partial-unique index + add_column + downgrade reverse-order: `0004_phase6_polymarket_sync.py`

**Partial-unique index** (lines 68-74) — the exact precedent for `(source, source_event_id)`:

```python
# Source: backend/alembic/versions/0004_phase6_polymarket_sync.py:68-74
op.create_index(
    "ix_markets_source_source_market_id",
    "markets",
    ["source", "source_market_id"],
    unique=True,
    postgresql_where=sa.text("source_market_id IS NOT NULL"),
)
```

**`add_column` (additive, nullable)** (lines 31-39 / 54-61) — copy for the two new `markets` columns:

```python
# Source: backend/alembic/versions/0004_phase6_polymarket_sync.py:54-61
op.add_column(
    "markets",
    sa.Column(
        "polymarket_slug",
        sa.String(300),
        nullable=True,
    ),
)
```

**`downgrade()` exact-reverse order** (lines 96-107) — drop indexes → constraints → columns:

```python
# Source: backend/alembic/versions/0004_phase6_polymarket_sync.py:96-107
def downgrade() -> None:
    op.drop_constraint("ck_odds_snapshots_probability_range", "odds_snapshots")
    # ...
    op.drop_index("ix_markets_source_source_market_id", table_name="markets")
    op.drop_column("markets", "polymarket_slug")
    op.drop_column("markets", "volume_24hr")
    op.drop_column("markets", "volume")
```

**Adaptation for 0011 — the two `markets` columns + FK + partial-unique:**
- `op.add_column("markets", sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True))`
- `op.add_column("markets", sa.Column("group_item_title", sa.Text(), nullable=True))`
- `op.create_foreign_key("fk_markets_group_id", "markets", "market_groups", ["group_id"], ["id"],
  ondelete="SET NULL")` — **`SET NULL`, never CASCADE** (Pitfall 5: child markets carry bets/ledger;
  deleting a group must orphan, not delete).
- `op.create_index("ix_markets_group_id", "markets", ["group_id"])`
- partial-unique: `op.create_index("ix_market_groups_source_source_event_id", "market_groups",
  ["source", "source_event_id"], unique=True, postgresql_where=sa.text("source_event_id IS NOT NULL"))`

#### Source D — GIN trigram + `pg_trgm` extension (NO in-repo GIN precedent; form from SQLAlchemy 2.0 docs)

There is **no existing GIN index in this codebase** — confirmed by scanning every migration. The
`postgresql_using="gin"` / `postgresql_ops` form comes from the SQLAlchemy 2.0 PostgreSQL-dialect docs
(cited in RESEARCH lines 199-207, 714). The `op.execute(...)` raw-DDL idiom for the extension matches
`0003`'s trigger creation (`op.execute("""CREATE ... """)` at `0003:171`) and `0009`'s seed
(`0009:74`):

```python
# Form: SQLAlchemy 2.0 PostgreSQL dialect docs (RESEARCH §Pattern 1, lines 199-221)
#       op.execute idiom matches 0003_phase4_markets.py:171 + 0009_phase10_tenant_config.py:74
def upgrade() -> None:
    # 1) pg_trgm FIRST — the GIN indexes below depend on gin_trgm_ops existing (Pitfall: ordering).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # ... table + columns + FK ...
    # GIN trigram (infix ILIKE search)
    op.create_index(
        "ix_market_groups_title_trgm", "market_groups", ["title"],
        postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_markets_question_trgm", "markets", ["question"],
        postgresql_using="gin", postgresql_ops={"question": "gin_trgm_ops"},
    )
    # catalog filter/sort indexes (plain B-tree)
    op.create_index("ix_market_groups_category", "market_groups", ["category"])
    op.create_index("ix_markets_category", "markets", ["category"])
    op.create_index("ix_markets_status_volume_24hr", "markets", ["status", "volume_24hr"])
    op.create_index("ix_odds_snapshots_outcome_id_snapshot_at", "odds_snapshots",
                    ["outcome_id", "snapshot_at"])
```

> **`odds_snapshots` composite is purely additive:** the single-column `ix_odds_snapshots_outcome_id`
> already exists (created at `0003_phase4_markets.py:198` in its downgrade-drop, i.e. created in
> `0003`'s upgrade) and `OddsSnapshot.outcome_id` already has `index=True`
> (`models.py:230-235`). The new `(outcome_id, snapshot_at)` composite sits alongside it — do NOT
> drop the existing single-column index.

**Adaptation for 0011 `downgrade()`:** drop all six indexes + `ix_markets_group_id` + `ix_market_groups_slug`
in exact reverse order, then `op.drop_constraint("fk_markets_group_id", "markets", type_="foreignkey")`,
then `op.drop_column("markets", "group_item_title")`, `op.drop_column("markets", "group_id")`, then
`op.drop_table("market_groups")`. **Do NOT drop `pg_trgm`** (Pitfall 3 / RESEARCH A1 — extensions are
DB-global and may be shared; leaving an idempotent bundled extension is harmless and reversibility
SC#1 is satisfied by restoring the schema objects). Document this choice in the migration docstring.

---

### `backend/app/markets/models.py` (MODIFY — model, CRUD)

**Analog:** the SAME file's `Market` / `Outcome` / `OddsSnapshot` classes. Copy the established
`Mapped[...]` + `mapped_column` style, the UUID PK, the tenant_id ghost column, and `lazy="raise"`.

**Imports already present** (lines 1-28) — extend, do not re-import. `Text`, `String`, `ForeignKey`,
`func`, `CheckConstraint` are already imported from `sqlalchemy`; `UUID` from
`sqlalchemy.dialects.postgresql`; `Mapped`, `mapped_column`, `relationship` from `sqlalchemy.orm`;
`get_settings` from `app.core.config`; `MarketSourceEnum` from `app.markets.enums`.
**You must ADD `Index`** to the `from sqlalchemy import (...)` block (lines 9-18) — it is not yet imported.

**UUID PK + tenant_id ghost + `lazy="raise"` relationship** — the exact template to clone
(`models.py:50-55`, `154-169`):

```python
# Source: backend/app/markets/models.py:50-55 (UUID PK), 154-169 (tenant_id ghost + lazy="raise")
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    # ...
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,   # CONVENTIONS §2 ghost column
    )

    outcomes: Mapped[list[Outcome]] = relationship(
        back_populates="market",
        cascade="all, delete-orphan",   # <-- DO NOT copy cascade onto MarketGroup.markets!
        lazy="raise",
    )
```

**CHECK-constraint-from-enum idiom** (`models.py:39-48`) — clone for `ck_market_groups_source`:

```python
# Source: backend/app/markets/models.py:44-47
        CheckConstraint(
            f"source IN ({', '.join(repr(s.value) for s in MarketSourceEnum)})",
            name="ck_markets_source",
        ),
```

**FK column with `index=True`** (`models.py:191-196`, on `Outcome.market_id`) — clone shape for
`Market.group_id`, but change `ondelete`:

```python
# Source: backend/app/markets/models.py:191-196 (NOTE: this one is CASCADE — group_id must be SET NULL)
    market_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
```

**Adaptation for 0011:**
1. **New `MarketGroup(Base)` class** with `__tablename__ = "market_groups"`, the
   `ck_market_groups_source` CHECK (enum idiom above), and `__table_args__` that **also declare the
   indexes** (`ix_market_groups_title_trgm` GIN, `ix_market_groups_source_source_event_id`
   partial-unique, `ix_market_groups_category`) so `Base.metadata` matches the migration — this is the
   repo's drift-avoidance convention (RESEARCH §Don't Hand-Roll). Columns mirror the migration's
   `market_groups` set. The `markets` relationship MUST use `lazy="raise"` and **MUST NOT** carry
   `cascade="all, delete-orphan"` (Pitfall 5 / anti-pattern — orphan, never delete).
2. **Extend `Market`:** add `group_id` (UUID FK → `market_groups.id`, `ondelete="SET NULL"`, nullable,
   `index=True`), `group_item_title` (`Text`, nullable), and a `group: Mapped[MarketGroup | None] =
   relationship(back_populates="markets", lazy="raise")`. Add the GIN/sort indexes to
   `Market.__table_args__`: `Index("ix_markets_question_trgm", "question", postgresql_using="gin",
   postgresql_ops={"question": "gin_trgm_ops"})`, `Index("ix_markets_category", "category")`,
   `Index("ix_markets_status_volume_24hr", "status", "volume_24hr")`. (`Index` requires `text()` from
   `sqlalchemy` if you use `postgresql_where` in `__table_args__` — import it if needed.)
3. `MarketGroup` has **no money column** and **no `status` column** (RESEARCH A2/A3).

---

### `backend/app/markets/__init__.py` (MODIFY — barrel export)

**Analog:** the SAME file (lines 1-10). Add `MarketGroup` to both the import and `__all__`:

```python
# Source: backend/app/markets/__init__.py:1-10 (current state)
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market, OddsSnapshot, Outcome

__all__ = [
    "Market",
    "MarketSourceEnum",
    "MarketStatus",
    "OddsSnapshot",
    "Outcome",
]
```

**Adaptation:** import `MarketGroup` (`from app.markets.models import Market, MarketGroup, OddsSnapshot,
Outcome`) and add `"MarketGroup"` to `__all__` (alphabetical position: after `MarketStatus`).

---

### `backend/alembic/env.py` (MODIFY — model registration for autogenerate)

**Analog:** the SAME file, line 32. The migration import block registers ORM models against
`Base.metadata` so autogenerate sees them:

```python
# Source: backend/alembic/env.py:32 (current state)
from app.markets.models import Market, OddsSnapshot, Outcome  # noqa: F401  (Plan 04-01)
```

**Adaptation:** add `MarketGroup`:
`from app.markets.models import Market, MarketGroup, OddsSnapshot, Outcome  # noqa: F401`.

---

### `backend/tests/markets/test_migration_0011.py` (NEW — migration introspection test)

**Analog A — `tests/auth/test_migration_0002.py`** (schema introspection via `inspect` +
`conn.run_sync`). The pytestmark, the `engine` fixture usage, and the column/FK/index assertions:

```python
# Source: backend/tests/auth/test_migration_0002.py:12-22, 58-66, 180-194
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Inspector
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

async def test_users_table_exists_with_expected_columns(engine: AsyncEngine) -> None:
    def _get_columns(sync_conn: object) -> set[str]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return {c["name"] for c in insp.get_columns("users")}
    async with engine.connect() as conn:
        column_names = await conn.run_sync(_get_columns)
    # assert required.issubset(column_names)

# FK ondelete assertion (the SET NULL check for Market.group_id):
async def test_refresh_tokens_user_id_fk_cascade(engine: AsyncEngine) -> None:
    def _get_fks(sync_conn: object) -> list[dict]:
        return list(inspect(sync_conn).get_foreign_keys("refresh_tokens"))
    async with engine.connect() as conn:
        fks = await conn.run_sync(_get_fks)
    user_fk = next((fk for fk in fks if "user_id" in fk.get("constrained_columns", [])), None)
    assert user_fk["referred_table"] == "users"
    assert user_fk.get("options", {}).get("ondelete") == "CASCADE"   # <-- 0011 asserts "SET NULL"
```

**Migration-chain assertion** (`test_migration_0002.py:41-50`) — copy for the
`down_revision == "0010_phase12_resolution_stakes"` + single-head check:

```python
# Source: backend/tests/auth/test_migration_0002.py:41-50
async def test_down_revision_chains_from_0001(engine: AsyncEngine) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config("alembic.ini")
    s = ScriptDirectory.from_config(cfg)
    rev = s.get_revision("0002_phase2_auth")
    assert rev.down_revision == "0001_phase1_foundations"
```

**Analog B — `tests/wallet/test_migration_0003.py`** (raw `text()` DDL + savepoint discipline). Use
`pg_indexes.indexdef` raw-DDL introspection for the GIN opclass + partial `WHERE` (which
`get_indexes()` does NOT reliably surface — RESEARCH A4), and `begin_nested()` for any
expected-to-raise statement (e.g. duplicate partial-unique key → 23505):

```python
# Source: backend/tests/wallet/test_migration_0003.py:38-40, 173-196 (savepoint + SQLSTATE)
def _sqlstate(err: DBAPIError) -> str | None:
    return getattr(err.orig, "sqlstate", None)

async def test_idempotency_key_unique(async_session: AsyncSession) -> None:
    key = f"test-idem-{uuid4()}"
    async with async_session.begin_nested():            # <-- savepoint, Pitfall 4
        await async_session.execute(text("INSERT INTO transfers ..."), {...})
    with pytest.raises(DBAPIError) as exc_info:
        async with async_session.begin_nested():         # <-- each raising stmt in its own savepoint
            await async_session.execute(text("INSERT INTO transfers ..."), {...})
    assert _sqlstate(exc_info.value) == "23505"
```

**Adaptation for `test_migration_0011.py`** — assert:
- `market_groups` has columns `{id, title, source, source_event_id, category, slug, created_at,
  updated_at, tenant_id}` (`get_columns` via `run_sync`).
- `markets` now has `group_id` + `group_item_title` (`get_columns`).
- `markets.group_id` FK → `market_groups`, `options.ondelete == "SET NULL"` (`get_foreign_keys`).
- `pg_trgm` present: `SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'` via `text()`.
- GIN trigram index DDL: `SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_markets_question_trgm'`
  → assert `"gin"` and `"gin_trgm_ops"` in `indexdef.lower()`.
- partial-unique DDL: `indexdef` for `ix_market_groups_source_source_event_id` contains `"unique"`
  and `"where"` + `"source_event_id"`.
- the four B-tree indexes (`ix_market_groups_category`, `ix_markets_category`,
  `ix_markets_status_volume_24hr`, `ix_odds_snapshots_outcome_id_snapshot_at`) present.
- chain: `ScriptDirectory.get_revision("0011_phase13_market_groups").down_revision ==
  "0010_phase12_resolution_stakes"`.
- **(optional) reversibility** (SC#1): `command.downgrade(cfg, "-1")` → `command.upgrade(cfg, "head")`
  on an isolated connection (RESEARCH A5 — the shared session `engine` is already at head; isolate so
  you don't disturb it), OR a static assertion that `downgrade()` mirrors `upgrade()`.

---

### `backend/tests/markets/test_models.py` (MODIFY — ORM round-trip test)

**Analog:** the SAME file. Copy `TestMarketCreation` (`selectinload` round-trip), `TestLazyRaise`
(`lazy='raise'` assertion), and `TestCheckConstraints` (`begin_nested` savepoint).

**`selectinload` round-trip** (`test_models.py:106-119`):

```python
# Source: backend/tests/markets/test_models.py:106-119
@_async
class TestMarketCreation:
    async def test_create_market_with_outcomes(self, async_session, sample_market):
        stmt = (
            select(Market)
            .where(Market.id == sample_market.id)
            .options(selectinload(Market.outcomes))
        )
        result = await async_session.execute(stmt)
        market = result.scalar_one()
        assert len(market.outcomes) == 2
        labels = {o.label for o in market.outcomes}
        assert labels == {"YES", "NO"}
```

**`lazy="raise"` enforcement** (`test_models.py:192-202`):

```python
# Source: backend/tests/markets/test_models.py:192-202
@_async
class TestLazyRaise:
    async def test_outcomes_lazy_raise(self, async_session, sample_market):
        stmt = select(Market).where(Market.id == sample_market.id)
        result = await async_session.execute(stmt)
        market = result.scalar_one()
        with pytest.raises(
            sqlalchemy.exc.InvalidRequestError,
            match="lazy='raise'",
        ):
            _ = market.outcomes
```

**`begin_nested()` for expected IntegrityError** (`test_models.py:137-152`) — the savepoint pattern:

```python
# Source: backend/tests/markets/test_models.py:139-152
    async def test_invalid_status_rejected(self, async_session):
        nested = await async_session.begin_nested()
        market = Market(question="Bad status", slug=generate_slug("Bad status"),
                        resolution_criteria="N/A", source=MarketSourceEnum.HOUSE.value,
                        status="INVALID", deadline=datetime.now(UTC) + timedelta(days=1))
        async_session.add(market)
        with pytest.raises(IntegrityError):
            await async_session.flush()
        await nested.rollback()
```

**Construction kwargs for a valid `Market`** (from the `sample_market` fixture,
`tests/markets/conftest.py:61-69`) — required fields when building children in the round-trip:

```python
# Source: backend/tests/markets/conftest.py:61-69
market = Market(
    question="Will it rain tomorrow?",
    slug=generate_slug("Will it rain tomorrow?"),
    resolution_criteria="Rain recorded at station X by 23:59 UTC",
    category="weather",
    source=MarketSourceEnum.HOUSE.value,
    status=MarketStatus.OPEN.value,
    deadline=datetime.now(UTC) + timedelta(days=1),
)
```

**Adaptation for `test_models.py` additions:**
- Import `MarketGroup` from `app.markets.models` (extend the existing line-14 import).
- **`MarketGroup` round-trip (SC#4):** create one `MarketGroup` + ≥2 child `Market`s (set
  `group_id=grp.id`, `group_item_title=...`), `flush()`, then `select(MarketGroup).where(...).options(
  selectinload(MarketGroup.markets))` and assert `len(loaded.markets) == 2` and the
  `group_item_title` set. Build children with the full required kwargs above.
- **`Market.group` `lazy="raise"` (SC#4):** mirror `TestLazyRaise` — load a `Market`, access
  `.group` without eager-load, assert `InvalidRequestError match="lazy='raise'"`.
- **`group_id IS NULL` regression (SC#2):** assert an existing standalone market (the `sample_market`
  fixture) has `group_id is None` and still reads/round-trips its `outcomes` unchanged — proving the
  additive columns did not alter the standalone path.
- Use `begin_nested()` for any expected IntegrityError (e.g. duplicate slug or partial-unique).

---

## Shared Patterns

### tenant_id ghost column (CONVENTIONS §2)
**Source — ORM:** `backend/app/markets/models.py:154-158` ·
**Source — migration:** `backend/alembic/versions/0009_phase10_tenant_config.py:63-68`
**Apply to:** `market_groups` (it IS a market table → carries `tenant_id`).
```python
# ORM (models.py:154-158)
tenant_id: Mapped[PyUUID | None] = mapped_column(
    UUID(as_uuid=True), nullable=True,
    default=lambda: get_settings().TENANT_ID_DEFAULT,
)
# Migration (0009:63-68) — TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"
sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True,
          server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid")),
```

### UUID PK + `gen_random_uuid()` server_default (CONVENTIONS §5)
**Source — ORM:** `backend/app/markets/models.py:50-55` ·
**Source — migration:** `backend/alembic/versions/0009_phase10_tenant_config.py:40-45`
**Apply to:** every new table/PK (`market_groups.id`).
```python
# ORM
id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
    default=uuid4, server_default=func.gen_random_uuid())
# Migration
sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
          server_default=sa.text("gen_random_uuid()")),
```

### CHECK-constraint-from-enum
**Source:** `backend/app/markets/models.py:44-47` (ORM) + `0003_phase4_markets.py:92-95` (migration)
**Apply to:** `market_groups.source` (`ck_market_groups_source`).
```python
CheckConstraint(f"source IN ({', '.join(repr(s.value) for s in MarketSourceEnum)})",
                name="ck_market_groups_source"),   # renders: source IN ('HOUSE', 'POLYMARKET')
```

### Index declared in BOTH migration AND `__table_args__` (drift avoidance)
**Source:** existing `Market`/`Outcome` declare CHECKs in `__table_args__` while `0003`/`0004`
emit them in the migration — the repo's convention is to keep `Base.metadata` truthful.
**Apply to:** all six new indexes — declare each in the `0011` migration AND in the relevant model's
`__table_args__` (`MarketGroup` for the 3 group indexes; `Market` for the 3 market indexes).

### Savepoint discipline for expected-to-raise statements (Pitfall 4)
**Source:** `backend/tests/wallet/test_migration_0003.py:8-14, 54-62` +
`backend/tests/markets/test_models.py:139-152`
**Apply to:** every test assertion that expects an `IntegrityError`/`DBAPIError` under the
session-scoped `async_session` (else one abort cascades into `InFailedSQLTransactionError`).
```python
with pytest.raises(IntegrityError):
    async with async_session.begin_nested():   # or: nested = await ...begin_nested(); ...; await nested.rollback()
        await async_session.flush()
```

### Migration `op.execute(...)` raw-DDL idiom (extension / trigger)
**Source:** `backend/alembic/versions/0003_phase4_markets.py:171-191` (trigger),
`0009_phase10_tenant_config.py:74-80` (seed).
**Apply to:** `op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")` — **first statement in
`upgrade()`** (GIN indexes depend on `gin_trgm_ops`).

---

## No Analog Found

| Capability | Status | Resolution |
|------------|--------|-----------|
| GIN trigram index (`postgresql_using="gin"`, `postgresql_ops={"col": "gin_trgm_ops"}`) | **No in-repo precedent** — zero existing GIN indexes (verified by scanning all 11 migrations) | Use the SQLAlchemy 2.0 PostgreSQL-dialect docs form (RESEARCH §Pattern 1 lines 199-221, cited line 714). The `op.create_index(...)` call site + the `op.execute` extension idiom DO have in-repo analogs; only the `gin`/`gin_trgm_ops` kwargs are doc-sourced. |

> Everything else — partial-unique index, tenant_id ghost, UUID PK + `gen_random_uuid()`,
> `selectinload` round-trip, `lazy="raise"`, savepoint introspection, `create_table` with
> timestamps, CHECK-from-enum, FK with `ondelete`, migration-chain test — has a verified working
> precedent in this codebase. No RESEARCH-only fallback is needed for any of them.

---

## Metadata

**Analog search scope:** `backend/alembic/versions/` (all 11 migrations), `backend/app/markets/`
(models, enums, `__init__`), `backend/tests/markets/` + `backend/tests/auth/` + `backend/tests/wallet/`
(test patterns), `backend/alembic/env.py`.
**Files scanned (read in full or targeted):** 11 (models.py, enums.py, markets/__init__.py, env.py,
0003/0004/0009/0010 migrations, test_migration_0002.py, test_migration_0003.py, test_models.py,
markets/conftest.py).
**Verified facts re-confirmed against code (not just RESEARCH):**
- `0010` revision id = `0010_phase12_resolution_stakes` (30 chars) — `0010:41`. ✓ down_revision target.
- `pg_trgm`/GIN: **no existing GIN index in the repo** — confirmed by scan. ✓ (doc-sourced form).
- `Market.category` (`String(100)`, nullable) exists — `models.py:64`; `Market.volume_24hr` (`Money`)
  exists — `models.py:86-89`; `OddsSnapshot.outcome_id` has `index=True` — `models.py:230-235`. ✓
  (no column adds needed for the index targets).
- MKT-08 trigger `trg_binary_outcomes_only` lives on `outcomes` — `0003:169-191`; untouched. ✓
- migration-introspection test precedent is in `tests/auth/` + `tests/wallet/`, NOT `tests/markets/`. ✓
**Pattern extraction date:** 2026-06-05
