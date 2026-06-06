# Phase 15: Event Settlement (House Resolve/Void + Mirrored Verify) - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 15 delivers the **event-level settlement layer**: an `EventService` that resolves / voids / reverses a multi-outcome **house** event by **looping the existing per-market `SettlementService`** over the group's child markets — each child on its own fresh `AsyncSession` (Option A: per-child ACID transaction) — with a **derived** event-status read-projection (EVT-06, no authoritative `winning_outcome` column) and **verified** mirrored auto-settlement (no new settlement code).

Covers **EVT-06, EVA-03, EVA-04, EVA-05, EVA-06**. It does **NOT** touch the catalog/event read API + house-event CRUD endpoints (Phase 16), the browse/event-detail/admin UI (Phase 17), or the seed/demo harness (Phase 18). It reuses **UNCHANGED**: `SettlementService.resolve_market` / `reverse_settlement`, the `WalletService` double-entry writer, the spike-002 `_derive_status` guard, and `detect_polymarket_resolutions`. **Zero new settlement primitives; zero changes to the binary market/bet/ledger model; no new dependencies.**

</domain>

<decisions>
## Implementation Decisions

### Resolution Loop & Partial-Failure Semantics
- **Resolve = loop `SettlementService.resolve_market`** over the group's child markets, **one child per FRESH `AsyncSession`** (Option A — per-child ACID tx). NEVER chain two settlement calls inside one `session.begin()`: the `23505` idempotent-replay path leaves a dangling open tx (validated gotcha — it bit the seed harness). See [[xprediction-financial-services-idempotent-tx-chaining]].
- **Partial failure = best-effort + idempotent replay.** Settle every child that can settle; if a child fails, leave already-settled children intact and surface the failed child(ren); the event lands `partially_resolved`. The admin re-runs resolve to finish — a true no-op over already-settled children (their bets are no longer `PENDING`).
- **Child order = winning child FIRST, then losing children** in deterministic `market.id` order — winners are paid before any loser-child hiccup.
- **Void (EVA-04) reuses the SAME loop:** call `resolve_market(child, winning_outcome_id=<that child's NO outcome>)` for **every** child (YES bettors lose, NO bettors win). Explicitly **NOT** a stake refund. No dedicated void settlement code.
- **`justification` is mandatory and non-empty at the service layer** — `EventService` raises on a blank/whitespace justification. The EVA-03 **two-step confirm** is a UI/API concern, deferred to Phase 16/17.

### Derived Event Status (EVT-06)
- **Status set = `{open, partially_resolved, resolved, void}`** (exactly the roadmap's four).
- Computed by a **pure function `derive_event_status(children)`** evaluated at **read time** — **NO** persisted/authoritative status or `winning_outcome` column on `market_groups` (EVT-06).
- **`void` vs `resolved` disambiguation is derived:** all children resolved with **no YES-winner** ⟺ `void`; all children resolved with **exactly one YES-winner** ⟺ `resolved`. Sound because event outcomes are mutually exclusive (a real resolution has exactly one YES).
- **`partially_resolved`** ⟺ ≥1 child resolved AND ≥1 child still unresolved. **`open`** ⟺ no child resolved.
- Settlement **never** routes through `closed=true` alone — the spike-002 `_derive_status` guard (`closed` + `umaResolutionStatus="resolved"` + clear winner) stays the only path to a child `MarketStatus`.

### Service Placement, Audit, Reverse & Mirrored
- **`EventService` lives in `backend/app/settlement/event_service.py`** — classmethods `resolve_event` / `void_event` / `reverse_event`, mirroring `SettlementService`'s classmethod + `MarketResolvePort` style. The HTTP router/endpoints are **Phase 16**; this phase is **service + tests only**.
- **Event-level audit:** write one `event.resolved` / `event.voided` / `event.reversed` row (group_id, winning outcome where applicable, child count, justification, actor) **IN ADDITION** to the per-child `settlement.resolved` / `settlement.reversed` rows that `SettlementService` already writes. The event audit row is its own small tx (consistent with the per-child txs).
- **Reverse (EVA-05) = loop `SettlementService.reverse_settlement`** over every already-settled child (fresh session per child), idempotent, audit-logged — mirrors **STL-07**. A child whose winner already spent the winnings can hit the `CHECK (balance >= 0)` floor and rolls back **that child only**.
- **Mirrored events (`source=POLYMARKET`) are admin read-only:** `resolve_event` / `void_event` / `reverse_event` **REJECT** a mirrored group (raise) except the existing emergency **force-settle** path (ADM-06). Mirrored children auto-settle through the existing `detect_polymarket_resolutions` task — **VERIFIED** against real Phase-14 data, **NOT rebuilt** (EVA-06). No new settlement code on the mirrored path.

### Claude's Discretion
- The exact shape of the per-child **fresh-session factory** (injected `async_sessionmaker` / session-factory param vs. the app's session dependency) — at Claude's discretion, provided each child settlement runs on its own session and the `23505` dangling-tx gotcha is respected.
- Whether `derive_event_status` reads children via the `MarketGroup.markets` relationship or an explicit query — discretion, provided it stays a pure read-projection.
- How the **winning outcome → child YES/NO** mapping is resolved at the service boundary (the group stores child markets + `group_item_title`; the admin endpoint validates the selection in Phase 16).
- Event-level audit payload field names (consistent with existing `AuditService.record` `event_type` conventions).
- Test layout: unit tests for `derive_event_status` + integration tests (testcontainers) for resolve / void / reverse / partial-failure / idempotent-replay / mirrored-verify.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/settlement/service.py` — `SettlementService.resolve_market(session, *, market_id, winning_outcome_id, market_resolver, justification, actor_user_id=None) -> SettlementPlan` and `reverse_settlement(...) -> int`. **Each wraps its own `async with session.begin()`**; idempotent via the `PENDING`-bet filter + per-bet `settle:{bet_id}:{leg}` / `reverse_idempotency_key` keys; writes `settlement.resolved` / `settlement.reversed` audit rows; `resolution_source = "HOUSE"` (admin actor) vs `"POLYMARKET_UMA"` (system). **LOOP THIS — do not reimplement.**
- `backend/app/settlement/market_port.py` — `MarketResolvePort` (`mark_resolved` / `mark_unresolved`). The event loop passes the same port per child.
- `backend/app/core/audit/service.py` — `AuditService.record(session, *, actor, event_type, payload)` (immutable rows). Reuse for the event-level rows.
- `backend/app/integrations/polymarket/tasks.py` — `detect_polymarket_resolutions` (mirrored UMA auto-settle; calls SettlementService with `actor_user_id=None`). **Verify, do not rebuild (EVA-06).**
- `MarketGroup` ORM (Phase 13, migration 0011) + `Market.group` / `MarketGroup.markets` relationship; `Market.group_id`, `group_item_title`, and the `source` discriminator (HOUSE vs POLYMARKET). Phase 14 now writes real `market_groups` rows (mirrored data for verification).

### Established Patterns
- **Per-bet idempotency keys + `PENDING`/`SETTLED` status filters are THE replay gate** — re-running resolve/reverse is a true no-op (no double-credit / double-refund).
- **Append-only double-entry:** reverse posts compensating **inverse** transfers, never `DELETE`/`UPDATE` (WAL-06).
- **FOR UPDATE locks in canonical UUID order** before posting (spike-004 / Pitfall 3) — already inside `SettlementService`; the event loop adds none.
- **Each financial service call runs on its OWN fresh session**; never chain two in one `with` ([[xprediction-financial-services-idempotent-tx-chaining]]).
- The **spike-004 double-entry integrity check** must pass green after **every** resolution path (resolve, void, reverse, partial, replay).

### Integration Points
- `market_groups` (Phase 13) + each child's `Market.status` — the read inputs for `derive_event_status`.
- `SettlementService` (Phase 5) — looped per child, unchanged.
- `AuditService` — the event-level audit rows.
- `detect_polymarket_resolutions` (Phase 7) — the mirrored auto-settle path, verified end-to-end.
- The admin force-settle / resolve surface (ADM-06) — the mirrored exception path; HTTP endpoints arrive in Phase 16.

</code_context>

<specifics>
## Specific Ideas

- Watch-outs carried from the Phase-14 closeout (HANDOFF): run the **spike-004 integrity check green after EVERY resolution path**; **never settle on `closed=true` alone** (spike-002); **per-child transactions (Option A) + idempotent replay**; **mirrored events stay admin-read-only** except emergency force-settle.
- The **Windows worktree is unreliable** for the full backend suite (testcontainers contention flake + ruff `check`/`format` flip-flop) — verify **per-module** locally, trust **Linux CI** ([[xprediction-backend-fullsuite-testcontainers-flake]]).
- **No new dependencies.** No DB migration is expected (status is **derived**, not stored). If any column is added it must NOT be an authoritative `winning_outcome` (EVT-06).

</specifics>

<deferred>
## Deferred Ideas

- Catalog/event read API + house-event CRUD endpoints (the resolve/void/reverse **HTTP** surface) — Phase 16.
- Browse UI, event detail, per-outcome rows, admin event ops UI — Phase 17.
- Seed/demo multi-outcome harness across event states — Phase 18.
- True **refund-on-cancel** (stake refund) — explicitly out of scope (EVA-04 is all-children-NO, not a refund).

</deferred>
