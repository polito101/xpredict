# Phase 13: Multi-outcome Model & Catalog Indexes - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning
**Mode:** Smart discuss — infrastructure phase (pure additive schema + ORM + indexes; no user-facing behavior). Grey-area questioning skipped; the ROADMAP success criteria + v1.0 schema are the spec.

<domain>
## Phase Boundary

Deliver the **database seam** for multi-outcome events as an *event-of-binaries*: a new
`market_groups` table plus nullable `Market.group_id` / `Market.group_item_title`, and **every
catalog/search index** the later v1.2 phases (14 sync, 16 API, 17 UI) will read — all in a single
reversible Alembic migration `0011_phase13_market_groups`.

**In scope:** the `MarketGroup` ORM model + `MarketGroup ↔ Market` relationship; the two new nullable
`Market` columns; the `pg_trgm` extension + all indexes listed in `<specifics>`; tests proving the
migration is reversible, the ORM round-trips, and existing standalone binary markets are byte-for-byte
unchanged.

**Explicitly OUT of scope (later phases):** any Gamma `/events` sync writing groups (Phase 14), any
`EventService`/event settlement (Phase 15), any `CatalogService`/HTTP endpoint (Phase 16), any UI
(Phase 17), any seed data (Phase 18). Phase 13 writes **no application logic** — it is the schema gate
that unblocks everything after it. Populating `Market.category` is Phase 14's job, not this one.
</domain>

<decisions>
## Implementation Decisions

### Architecture (locked upstream — not grey areas)
- **Event-of-binaries** (STATE.md decision 2026-06-04): a multi-outcome event is N independent binary
  YES/NO markets grouped under one `market_groups` row. Reuses the existing binary `Market` + `Outcome`
  + `SettlementService` unchanged.
- **Purely additive**: the binary model, the binary `CHECK` constraints, `SettlementService`, and all
  bet / odds / ledger paths stay byte-for-byte unchanged. No backfill, no data migration, no downtime.
- **Zero new dependencies**: only the Postgres-bundled `pg_trgm` extension (`CREATE EXTENSION IF NOT
  EXISTS pg_trgm`). No new Python/pip packages.
- Resolves the v1.0 `MKT-08` deferral ("multi-outcome → v2"). Requirement covered: **EVT-01**.

### Claude's Discretion (HOW — infrastructure phase)
All implementation mechanics are at Claude's discretion, guided by `backend/CONVENTIONS.md`, the
existing `backend/app/markets/models.py` patterns, and the success criteria. This includes: exact
`MarketGroup` column set beyond the required ones, nullable-column ordering, index naming, whether to
split into multiple plans, and test structure (testcontainers + Postgres 16, per repo convention).
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/markets/models.py` — `Market`, `Outcome`, `OddsSnapshot` ORM. Extend `Market` here with
  `group_id` (nullable FK) + `group_item_title` (nullable str); add the `MarketGroup` class. Follow the
  established `mapped_column` + `Mapped[...]` style and the `lazy="raise"` relationship discipline.
- `backend/app/db/types.py` — `Money` (`Numeric(18,4)`) and `Odds` (`Numeric(8,6)`) aliases. MarketGroup
  has **no money columns**, so neither alias is needed there; do not invent a money column.
- `backend/app/db/base.py` — declarative `Base` all models inherit.
- `backend/alembic/versions/` — migration home. Use `0010_phase12_resolution_and_stake_limits.py` as the
  style template (sync engine, `op.create_index`, `op.add_column`).
- `Market.category` **already exists** (`String(100)` nullable) — the `(category)` index targets it
  directly; no column add needed. `Market.volume_24hr` exists (`Money`) for the `(status, volume_24hr)`
  index. `OddsSnapshot.outcome_id` exists with a single index — add the `(outcome_id, snapshot_at)`
  composite.

### Established Patterns (from CONVENTIONS.md — MUST follow)
- **tenant_id ghost column** (§2): every market table declares
  `tenant_id: Mapped[PyUUID | None]` defaulting to `Settings().TENANT_ID_DEFAULT`. `market_groups` is a
  market table → it carries `tenant_id`.
- **Money lint** (§1): `scripts/lint_money_columns.py` AST-walks `*models.py`. MarketGroup avoids
  money-named columns, so it stays trivially green.
- **Alembic via sync engine** (§5): `env.py` uses `DATABASE_URL_SYNC`; run with
  `docker compose exec backend uv run alembic upgrade head`. Migration must define both `upgrade()` and a
  real `downgrade()` (reversibility is SC#1).
- UUID PKs via `gen_random_uuid()` server_default; `created_at`/`updated_at` via `func.now()`.

### Integration Points / Risks
- **Alembic head**: history is branched (two `0004_*`, a `0006_merge_phase5_phase6`). Current single head
  should be `0010_phase12_resolution_and_stake_limits`. **Verify `alembic heads` returns exactly one head**
  before authoring; set `0011`'s `down_revision` to that head. If `alembic heads` shows >1, a merge
  revision is needed first.
- **No behavior change proof**: SC#2 requires an existing `group_id IS NULL` market to read / bet / settle
  exactly as before. Cover with a regression test asserting standalone-market paths are untouched.
- GIN trigram indexes require `pg_trgm` created **before** the `CREATE INDEX ... USING gin (... gin_trgm_ops)`
  statements in the same migration.
</code_context>

<specifics>
## Specific Ideas — the exact schema deliverables (SC-mapped, locked)

Migration `0011_phase13_market_groups` must, in one reversible unit:

1. **`market_groups` table** (SC#1, SC#4): `id` UUID PK (`gen_random_uuid`), `title` Text NOT NULL,
   `source` (HOUSE/POLYMARKET, mirrors `Market.source`), `source_event_id` (nullable str — Polymarket
   event id), `category` (nullable, mirrors markets), `slug` (unique, for `/events/{slug}` in Phase 16),
   `created_at`/`updated_at`, `tenant_id` ghost column. Final column set at Claude's discretion as long as
   the required ones exist.
2. **Nullable `Market` columns** (SC#1): `group_id` UUID nullable FK → `market_groups.id`
   (`ondelete` sensible — likely `SET NULL` so deleting a group doesn't cascade-delete child markets),
   and `group_item_title` nullable str (the per-outcome label, e.g. candidate name). **No backfill.**
3. **`pg_trgm`** (SC#3): `CREATE EXTENSION IF NOT EXISTS pg_trgm`.
4. **Indexes** (SC#3) — all of:
   - GIN trigram on `market_groups.title` (`gin_trgm_ops`)
   - GIN trigram on `markets.question` (`gin_trgm_ops`)
   - **partial-unique** on `market_groups (source, source_event_id) WHERE source_event_id IS NOT NULL`
   - `market_groups`/`markets` `(category)` index (catalog category filter)
   - `(status, volume_24hr)` on `markets` (status filter + volume sort)
   - composite `(outcome_id, snapshot_at)` on `odds_snapshots` (per-outcome price history)
5. **`MarketGroup` ORM model** (SC#4) + `MarketGroup.markets` ↔ `Market.group` relationship loading via the
   async session, round-tripping a parent group with ≥2 children. Keep the `lazy="raise"` discipline used
   by the existing relationships (explicit eager-load at call sites).

**Reversibility (SC#1):** `downgrade()` drops indexes, columns, extension (only if safe / leave `pg_trgm`?
— prefer dropping what the migration created; document the choice), and the table, restoring the exact
pre-0011 schema.
</specifics>

<deferred>
## Deferred Ideas

- Gamma `/events` ingestion that actually writes `market_groups` rows and stamps `group_id` → **Phase 14**.
- Populating `Market.category` on mirrored rows → **Phase 14**.
- Event settlement (resolve/void/reverse, derived status) → **Phase 15**.
- `CatalogService.browse()` + event/category/admin endpoints → **Phase 16**.
- Catalog browse UI + event detail + admin event forms → **Phase 17**.
- Multi-outcome seed/demo harness → **Phase 18**.

None of the above is implemented in Phase 13 — this phase is the additive schema seam only.
</deferred>
