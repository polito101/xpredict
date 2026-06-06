# Phase 13 — Deferred / Out-of-Scope Discoveries

Logged during execution of plan 13-01. These are NOT introduced by Phase 13 and
were NOT fixed (scope boundary: only auto-fix issues directly caused by this
plan's changes).

## Pre-existing ORM ↔ migration autogenerate drift (NOT Phase 13)

While verifying that the Phase 13 objects are drift-free, `alembic.autogenerate.
compare_metadata(MigrationContext, Base.metadata)` reported 9 diffs that all
predate Phase 13 and involve other subsystems. The Phase 13 objects
(`market_groups`, `markets.group_id`, `markets.group_item_title`,
`fk_markets_group_id`, and all 6 new indexes) produce **zero** drift — they were
explicitly verified byte-identical between migration 0011 and the ORM
`__table_args__`.

Observed pre-existing diffs (for a future cleanup pass, e.g. a dedicated
autogenerate-hygiene chore — out of scope for EVT-01):

- `remove_table tenant_config` — its model is not imported into this metadata
  view (Phase 10); not a real drop.
- `remove_index ix_audit_log_actor`, `ix_audit_log_event_type`,
  `ix_audit_log_occurred_at` — Phase 1 audit_log indexes declared in migration
  but not in the ORM `__table_args__`.
- `add_index ix_bets_market_id`, `ix_bets_user_id`, `ix_entries_account_id` —
  ORM-declared (`index=True`) but the migration created them under different
  names / not introspected here (Phases 3/5).
- `modify_nullable feature_flags.tenant_id` — server_default/nullable mismatch
  (Phase 1).
- `remove_index ix_markets_source_source_market_id` — the EXISTING Phase 6
  partial-unique index (migration 0004); not declared in `Market.__table_args__`.
  (Distinct from the new Phase 13 `ix_market_groups_source_source_event_id`.)

None of these affect Phase 13 correctness; the migration chain applies and
reverses cleanly and the binary read/bet/settle path is unchanged.
