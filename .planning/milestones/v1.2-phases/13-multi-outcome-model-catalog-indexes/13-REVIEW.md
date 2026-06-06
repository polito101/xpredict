---
phase: 13-multi-outcome-model-catalog-indexes
reviewed: 2026-06-05T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/alembic/versions/0011_phase13_market_groups.py
  - backend/app/markets/models.py
  - backend/app/markets/__init__.py
  - backend/alembic/env.py
  - backend/tests/markets/test_migration_0011.py
  - backend/tests/markets/test_models.py
findings:
  critical: 0
  blocker: 0
  warning: 2
  info: 4
  total: 6
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-06-05
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 13 is a pure-additive Postgres/SQLAlchemy 2.0 + Alembic schema seam for v1.2 multi-outcome
events: migration `0011_phase13_market_groups` (new `market_groups` table, two nullable `markets`
columns, `pg_trgm`, and six catalog/search indexes), the `MarketGroup` ORM model, and tests. I
traced every claim in the phase brief against the actual pre-existing migrations (`0003`, `0004`,
`0010`), the `Money`/`Odds` types, the money-lint AST rules, the test fixtures, and the existing
markets `service.py`/`schemas.py` read paths.

**The core contract holds and is well-engineered.** All of the high-risk invariants verify true:

- `down_revision = "0010_phase12_resolution_stakes"` is the **revision id** inside `0010`
  (filename stem is `0010_phase12_resolution_and_stake_limits` — confirmed decoupled), so the
  chain is correct and the test asserts the right thing.
- `CREATE EXTENSION IF NOT EXISTS pg_trgm` is ordered FIRST, before the GIN `gin_trgm_ops` indexes.
- The FK `fk_markets_group_id` is `ON DELETE SET NULL` in the migration, mirrored on the ORM
  column, and the `MarketGroup.markets` relationship carries **no** cascade — children orphan,
  never cascade-delete financial rows (T-13-01 mitigation genuinely enforced, and test-enforced).
- The `odds_snapshots (outcome_id, snapshot_at)` composite is purely additive; `0003`'s
  single-column `ix_odds_snapshots_outcome_id` is not dropped, and a test guards its survival.
- `downgrade()` drops exactly what `upgrade()` creates (verified object-by-object) and
  deliberately retains `pg_trgm`.
- Index names are byte-identical between the migration and the ORM `__table_args__`; the
  enum-generated `ck_market_groups_source` CHECK renders byte-identical to the migration literal
  `source IN ('HOUSE', 'POLYMARKET')`.
- No concurrency landmines: no `begin()`-on-open-transaction, no async-session misuse, no
  `MissingGreenlet` pattern in the new code. The new `Market.group` relationship is `lazy="raise"`
  and is NOT touched by any existing `service.py` query or `from_attributes` response schema, so
  the standalone-market read path is genuinely unchanged (SC#2 holds at the API layer, not just in
  the DB).

No BLOCKER or Critical defects. The findings below are two robustness WARNINGs (a real
introspection-test soundness gap that lets a regression pass silently, and a missing standalone
DB-level FK-orphan test) plus four minor INFO items.

## Warnings

### WR-01: Composite-index column ORDER is never asserted — a (snapshot_at, outcome_id) regression would pass

**File:** `backend/tests/markets/test_migration_0011.py:197-212` (`test_btree_catalog_indexes_exist`)
**Issue:** The brief calls out "real `pg_indexes.indexdef` checks, not tautologies." Two index
tests fall short of that bar on the dimension that actually matters for these indexes — **column
order**:

- `test_btree_catalog_indexes_exist` only asserts `ddl is not None` for
  `ix_markets_status_volume_24hr` and `ix_odds_snapshots_outcome_id_snapshot_at`. It never checks
  the column order. The whole point of `(outcome_id, snapshot_at)` and `(status, volume_24hr)` is
  the **leading column** (range-scan + sort prefix). If a future edit flipped the order to
  `(snapshot_at, outcome_id)` or `(volume_24hr, status)`, the migration would still create *an*
  index of that name and this test would stay green — the regression that the composite was added
  to prevent would ship undetected.
- `test_gin_trgm_indexes_have_opclass` substring-matches `"gin"` and `"gin_trgm_ops"` anywhere in
  the lowercased DDL but never ties the opclass to the intended column, and
  `test_partial_unique_has_where_clause` only checks that the tokens `unique`, `where`, and
  `source_event_id` each appear somewhere — it would pass on `WHERE source_event_id IS NULL` (the
  logical inverse) just as readily as the correct `IS NOT NULL`.

These assertions confirm the objects exist but under-verify their semantics, which is exactly the
soft-review failure mode the introspection tests were meant to avoid.

**Fix:** Tighten the DDL assertions to pin the load-bearing detail. The `indexdef` string already
contains the ordered column list, so:
```python
# In test_btree_catalog_indexes_exist (or a dedicated test):
async def test_composite_index_column_order(engine):
    async with engine.connect() as conn:
        odds = (await _indexdef(conn, "ix_odds_snapshots_outcome_id_snapshot_at")).lower()
        mkt = (await _indexdef(conn, "ix_markets_status_volume_24hr")).lower()
    # leading column must come first in the indexed tuple
    assert odds.index("outcome_id") < odds.index("snapshot_at"), odds
    assert mkt.index("status") < mkt.index("volume_24hr"), mkt

# In test_partial_unique_has_where_clause, pin the polarity:
assert "is not null" in lowered, f"WHERE must be IS NOT NULL, got: {ddl}"
```
Optionally assert `gin_trgm_ops` appears in the same parenthesised column clause as `title` /
`question` rather than merely somewhere in the string.

### WR-02: The FK's actual ON DELETE SET NULL *behavior* is never exercised — only the catalog metadata is checked

**File:** `backend/tests/markets/test_migration_0011.py:116-140` (`test_markets_group_id_fk_set_null`)
and `backend/tests/markets/test_models.py:237-283` (`TestMarketGroup`)
**Issue:** T-13-01 ("deleting a group must ORPHAN children, never cascade-delete bets/odds/ledger")
is the single most financially important invariant in this phase, yet no test performs the
operation it protects against. `test_markets_group_id_fk_set_null` reads
`get_foreign_keys(...)["options"]["ondelete"]` from the catalog — that proves the DDL says
`SET NULL`, but it relies entirely on SQLAlchemy's introspection mapping and never observes a real
`DELETE FROM market_groups` actually nulling `markets.group_id` (vs. cascading or raising). A
behavioral test would catch failure modes the metadata check cannot: e.g. a trigger, a second
conflicting constraint, or a future ORM `cascade=` regression on the relationship that would
delete children even though the DB-level FK still says `SET NULL`.

**Fix:** Add one behavioral test on `async_session` (savepoint-scoped, matching the repo's
`begin_nested()` discipline so the abort/rollback stays isolated):
```python
async def test_deleting_group_orphans_children_not_cascade(async_session):
    grp = MarketGroup(title="Orphan test", source="HOUSE",
                      slug=generate_slug("orphan-test"))
    async_session.add(grp); await async_session.flush()
    child = _child_market("Orphan child", grp.id)
    async_session.add(child); await async_session.flush()
    child_id = child.id

    await async_session.execute(delete(MarketGroup).where(MarketGroup.id == grp.id))
    await async_session.flush()
    async_session.expire(child)
    reloaded = (await async_session.execute(
        select(Market).where(Market.id == child_id))).scalar_one_or_none()
    assert reloaded is not None, "child market was cascade-deleted — T-13-01 violated"
    assert reloaded.group_id is None, "group_id was not nulled on group delete"
```
This converts T-13-01 from a metadata assertion into an enforced behavioral guarantee.

## Info

### IN-01: `test_market_has_expected_columns` was not extended for the two new columns

**File:** `backend/tests/markets/test_models.py:53-73`
**Issue:** The pre-existing `expected` column set was not updated to include `group_id` /
`group_item_title`. Because it uses `expected.issubset(columns)`, the test still passes, but it no
longer reflects the full Market column surface at the ORM-metadata level. (The new columns ARE
covered at the DB level by `test_markets_has_group_columns` and via round-trip, so this is a
completeness nit, not a coverage hole.)
**Fix:** Add `"group_id"` and `"group_item_title"` to the `expected` set for documentation value
and metadata-level coverage.

### IN-02: `test_downgrade_mirrors_upgrade` carries the `integration` mark despite doing zero I/O

**File:** `backend/tests/markets/test_migration_0011.py:267-349`
**Issue:** The test body is pure source-text parsing (no DB, no Docker) but inherits the module
`pytestmark = [pytest.mark.integration, pytest.mark.asyncio(...)]`, so it only runs when the
integration suite (Docker) runs. The docstring honestly explains the `async def` workaround for
`filterwarnings=error`, but the `integration` mark needlessly gates a fast, deterministic,
side-effect-free check behind a Docker daemon. This reduces how often the reversibility guard
actually executes (e.g. it won't run in a fast unit-only CI lane).
**Fix:** Move this test to a non-integration module (or override its mark) so the static
reversibility parse runs in the unit lane too. Lowest-risk: keep it here but add a comment that
it could be promoted; ideal: relocate to a `tests/markets/test_migration_0011_static.py` without
the `integration`/`asyncio` marks (then it can be a plain `def`).

### IN-03: Reversibility parse is regex-on-source — brittle to formatting, and proves names not symmetry

**File:** `backend/tests/markets/test_migration_0011.py:298-343`
**Issue:** The mirror check regex-scans the migration source for `op.create_*` / `op.drop_*` name
literals. It is a reasonable, deterministic proxy (and the docstring justifies avoiding a live
cycle on the shared session engine), but it is brittle: it would silently weaken if a future
migration used `op.execute("CREATE INDEX ...")`, a multi-line call with the name on a continuation
line, an f-string name, or a `with op.batch_alter_table()` block — none of which the regex
captures. It also only proves "every created name is dropped," not that the drops would actually
succeed or run in dependency-safe order.
**Fix:** Acceptable as-is for this all-`op.create_*`/`op.drop_*` migration. If you want a stronger
guarantee without disturbing the shared schema, run the live `upgrade→downgrade→upgrade` cycle
against a **dedicated throwaway** testcontainer in a `function`-scoped fixture (the
13-01-SUMMARY notes this was done manually while authoring — promoting it to a committed,
isolated test would lock it permanently). At minimum, add a comment that the regex assumes the
`op.<verb>("name", ...)` form.

### IN-04: money-lint does not cover `alembic/versions/` under its default invocation

**File:** `backend/scripts/lint_money_columns.py:256, 291` (context for this phase's migration)
**Issue:** The lint's `lint()` globs include `**/versions/*.py`, but `__main__` calls
`lint(Path("app"))`, so migrations under `alembic/versions/` are never scanned by the default
`python scripts/lint_money_columns.py` run. This phase's migration is clean (no money-named
column is added — `title`, `source`, `source_event_id`, `category`, `slug`, `group_id`,
`group_item_title`, `tenant_id` are all outside `MONEY_NAMES`), so there is **no** violation here.
Flagging only because the migration's own docstring claims a money-named column "would trip
`scripts/lint_money_columns.py`" — under the default invocation it would not, since migrations
aren't in scope. Pre-existing tooling gap, not introduced by this phase.
**Fix:** Out of scope for Phase 13. If the claim is to hold, invoke the lint over the repo root
(or add `alembic` to the `__main__` path) in CI/pre-commit, or soften the docstring to note that
the migration's money-safety rests on the ORM-model lint, not the migration scan.

---

_Reviewed: 2026-06-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
