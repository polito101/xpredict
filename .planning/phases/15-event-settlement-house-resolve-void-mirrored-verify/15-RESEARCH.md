# Phase 15: Event Settlement (House Resolve/Void + Mirrored Verify) - Research

**Researched:** 2026-06-05
**Domain:** Backend settlement orchestration — looping the proven per-market `SettlementService` over a `MarketGroup`'s child markets (Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Postgres 16 · double-entry ledger)
**Confidence:** HIGH (every contract verified by reading current source; no external/library research needed — this phase composes in-repo primitives)

## Summary

Phase 15 is a **pure orchestration layer**. It adds one new module — `backend/app/settlement/event_service.py` with `EventService.resolve_event` / `void_event` / `reverse_event` classmethods — plus a pure `derive_event_status(children)` read-projection, and **zero new settlement primitives, zero migrations, zero new dependencies**. The hard transactional machinery (`SettlementService.resolve_market` / `reverse_settlement`, the double-entry writer, the FOR-UPDATE lock ordering, the per-bet idempotency keys, the spike-002 closed-vs-resolved guard, `detect_polymarket_resolutions`) all already exist and are validated; the phase composes them.

The single highest-risk constraint — verified in code and in operator memory — is the **dangling-transaction-on-23505 landmine**: `SettlementService.resolve_market` and `reverse_settlement` each open their OWN `async with session.begin()`, and on the idempotent-replay path a duplicate `idempotency_key` raises `23505`, whose handler leaves an open implicit transaction. Chaining a second self-committing call on the SAME session then raises `InvalidRequestError: A transaction is already begun on this Session`. Therefore the `EventService` loop **MUST open a fresh `AsyncSession` per child** (Option A — per-child ACID transaction) and never wrap two child settlements in one `with` / `begin()`. The repo's existing tasks construct sessions via `from app.db.session import _get_session_maker; session_maker = _get_session_maker(); session = session_maker()` — that is the concrete factory the planner should specify.

Event status is **truly column-free**: migration 0011 deliberately created `market_groups` with NO `status` and NO `winning_outcome` column (EVT-06), so `derive_event_status` is a pure function over the children's `Market.status` (+ which child carries the winning YES). No migration is needed and none must be added with an authoritative winner. The YES/NO-per-child mapping reuses the repo's canonical `func.upper(Outcome.label) == "YES"` case-insensitive match (house labels are `"YES"`/`"NO"`; mirrored Polymarket labels are title-case `"Yes"`/`"No"`).

**Primary recommendation:** Build `EventService` as a thin classmethod loop that (1) eager-loads the group's children + their outcomes, (2) for each child opens its own fresh session and calls the UNCHANGED `SettlementService`, (3) writes one event-level audit row in its own small transaction, and (4) exposes `derive_event_status` as a pure projection. Reject `source=POLYMARKET` groups in all three methods (EVA-06). Verify the mirrored auto-settle path against real Phase-14 data without touching `detect_polymarket_resolutions`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Event resolve/void/reverse orchestration | API/Backend service (`app/settlement/event_service.py`) | — | New service-only layer; loops the per-market settlement primitive. HTTP endpoints are Phase 16. |
| Per-child money movement + bet flips + market-status flip | API/Backend (`SettlementService`, UNCHANGED) | Database (ledger, FOR UPDATE locks) | Already built + validated (Phase 5). Phase 15 calls it, never reimplements it. |
| Derived event status | API/Backend pure function (`derive_event_status`) | Database (read of `Market.status`) | EVT-06 forbids stored status; computed at read time from constituent markets. |
| Per-child fresh-session construction | API/Backend (`_get_session_maker()` factory) | — | Mandatory to dodge the 23505 dangling-tx landmine across consecutive settle calls. |
| Mirrored (Polymarket) child auto-settlement | Celery beat task (`detect_polymarket_resolutions`, UNCHANGED) | API/Backend (`SettlementService`) | EVA-06 = VERIFY the existing UMA path, do not rebuild. |
| Event-level + per-child audit | API/Backend (`AuditService.record`) | Database (`audit_log`) | Event row added alongside the per-child rows `SettlementService` already writes. |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVT-06 | Event status (open / partially_resolved / resolved / void) is DERIVED from constituent markets — never a stored authoritative winning-outcome column. | Verified: migration 0011 created `market_groups` with NO `status`/`winning_outcome` column; `MarketGroup` ORM has no such field. `derive_event_status` is a pure function over `Market.status` + winning-child identity. No migration needed. (Architecture Patterns §Pattern 4; Code Examples §`derive_event_status`) |
| EVA-03 | Admin resolves a house event by winning outcome; loops `SettlementService` per child (winner→YES, losers→NO), idempotently. | Exact `SettlementService.resolve_market` contract mapped (Standard Stack §SettlementService). Winning-child→YES mapping via `func.upper(label)=="YES"`. Per-child fresh-session loop (Pattern 1). Justification mandatory at service layer (CONTEXT decision). |
| EVA-04 | Admin voids a house event (no winner); every child resolves on NO (YES bettors lose, NO bettors win) — NOT a stake refund. | Void = same loop calling `resolve_market(child, winning_outcome_id=<child NO outcome>)` for every child. NO outcome found via the non-YES leg (Pattern 2). No dedicated void code. |
| EVA-05 | Admin reverses an event resolution via compensating ledger entries (mirrors STL-07), audit-logged. | `SettlementService.reverse_settlement` contract mapped (returns `int` count, posts inverse transfers, flips SETTLED→PENDING, idempotent). Per-child fresh-session loop. `CHECK(balance>=0)` floor rolls back that child only (Pitfall 3). |
| EVA-06 | Mirrored (Polymarket) events read-only except emergency force-settle; mirrored children auto-settle via existing UMA detection (verify, no new settlement code). | `detect_polymarket_resolutions` mapped — calls `SettlementService.resolve_market(actor_user_id=None)` per market. `EventService` rejects `source=POLYMARKET`. Force-settle endpoint already exists (ADM-06). VERIFY against real Phase-14 `market_groups` rows. |
</phase_requirements>

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Resolution Loop & Partial-Failure Semantics**
- **Resolve = loop `SettlementService.resolve_market`** over the group's child markets, **one child per FRESH `AsyncSession`** (Option A — per-child ACID tx). NEVER chain two settlement calls inside one `session.begin()`: the `23505` idempotent-replay path leaves a dangling open tx (validated gotcha — it bit the seed harness).
- **Partial failure = best-effort + idempotent replay.** Settle every child that can settle; if a child fails, leave already-settled children intact and surface the failed child(ren); the event lands `partially_resolved`. The admin re-runs resolve to finish — a true no-op over already-settled children (their bets are no longer `PENDING`).
- **Child order = winning child FIRST, then losing children** in deterministic `market.id` order — winners are paid before any loser-child hiccup.
- **Void (EVA-04) reuses the SAME loop:** call `resolve_market(child, winning_outcome_id=<that child's NO outcome>)` for **every** child (YES bettors lose, NO bettors win). Explicitly **NOT** a stake refund. No dedicated void settlement code.
- **`justification` is mandatory and non-empty at the service layer** — `EventService` raises on a blank/whitespace justification. The EVA-03 **two-step confirm** is a UI/API concern, deferred to Phase 16/17.

**Derived Event Status (EVT-06)**
- **Status set = `{open, partially_resolved, resolved, void}`** (exactly the roadmap's four).
- Computed by a **pure function `derive_event_status(children)`** evaluated at **read time** — **NO** persisted/authoritative status or `winning_outcome` column on `market_groups` (EVT-06).
- **`void` vs `resolved` disambiguation is derived:** all children resolved with **no YES-winner** ⟺ `void`; all children resolved with **exactly one YES-winner** ⟺ `resolved`. Sound because event outcomes are mutually exclusive (a real resolution has exactly one YES).
- **`partially_resolved`** ⟺ ≥1 child resolved AND ≥1 child still unresolved. **`open`** ⟺ no child resolved.
- Settlement **never** routes through `closed=true` alone — the spike-002 `_derive_status` guard (`closed` + `umaResolutionStatus="resolved"` + clear winner) stays the only path to a child `MarketStatus`.

**Service Placement, Audit, Reverse & Mirrored**
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

### Deferred Ideas (OUT OF SCOPE)
- Catalog/event read API + house-event CRUD endpoints (the resolve/void/reverse **HTTP** surface) — Phase 16.
- Browse UI, event detail, per-outcome rows, admin event ops UI — Phase 17.
- Seed/demo multi-outcome harness across event states — Phase 18.
- True **refund-on-cancel** (stake refund) — explicitly out of scope (EVA-04 is all-children-NO, not a refund).
</user_constraints>

## Project Constraints (from CLAUDE.md / project rules)

- **Backend stack is fixed:** Python 3.12 · FastAPI · SQLAlchemy 2.0 **async** · Postgres 16 · double-entry ledger. No new dependencies for this phase (CONTEXT).
- **All money is `Decimal` / `NUMERIC(18,4)`** — never float. (Already enforced inside `SettlementService`; the event loop adds no money math — it delegates entirely.)
- **`scripts/lint_money_columns.py` ("money-lint")** must stay green — but Phase 15 adds NO money column (event status is derived, no migration). The only DB writes are audit rows (JSON payload with money as strings, per the existing `settlement.resolved` convention).
- **Tests:** backend `cd backend && uv run pytest` (testcontainers + Docker). New tests mirror `backend/tests/settlement/`.
- **Windows worktree caveat (environmental, NOT code):** the full `uv run pytest` flakes (testcontainers contention) and `ruff check`/`format` flip-flop on this Windows worktree. **Linux CI is the source of truth** (`pytest tests/ -x` + ruff + mypy GREEN). Verify per-module locally; do NOT propose "fixing" the worktree.
- **Branch discipline:** work on `gsd/phase-15-...`, never `main`; 1 PR/phase; only Pol merges.

## Standard Stack

This phase has NO external libraries to choose — it composes in-repo primitives. The "stack" is the set of existing modules the `EventService` calls, with their EXACT verified contracts.

### Core (the primitives Phase 15 loops — all UNCHANGED)

| Module / Symbol | File | Contract (verified) | Phase 15 use |
|-----------------|------|---------------------|--------------|
| `SettlementService.resolve_market` | `backend/app/settlement/service.py` | `async classmethod resolve_market(session, *, market_id: UUID, winning_outcome_id: UUID, market_resolver: MarketResolvePort, justification: str, actor_user_id: UUID \| None = None) -> SettlementPlan`. **Opens its own `async with session.begin()`.** Idempotent via `status==PENDING` bet filter + per-bet `settle:{bet_id}:{leg}` keys. Writes a `settlement.resolved` audit row + marks the market RESOLVED via the port — all in ONE tx. `resolution_source = "POLYMARKET_UMA" if actor_user_id is None else "HOUSE"`. | Called once per child (resolve + void). |
| `SettlementService.reverse_settlement` | same | `async classmethod reverse_settlement(session, *, market_id: UUID, market_resolver: MarketResolvePort, justification: str, actor_user_id: UUID \| None = None) -> int`. **Own `session.begin()`.** Posts INVERSE transfers (append-only, never DELETE/UPDATE), flips `SETTLED_*`→`PENDING`, calls `mark_unresolved`, writes `settlement.reversed` audit. Returns count of bets reversed. Idempotent (no SETTLED bets ⇒ no-op). A winner who spent winnings ⇒ `CHECK(balance>=0)` rollback of that call. | Called once per already-settled child (reverse). |
| `SettlementPlan` | `backend/app/settlement/plan.py` | `@dataclass(frozen, slots)` — `winning_outcome_id: UUID`, `settled: tuple[SettledBet,...]`, `total_payout: Decimal`, `total_loser_stake: Decimal`. `SettledBet` has `won: bool`, `payout`, `pnl`, `status`. | Aggregate per-child returns for the event audit payload / result summary. |
| `MarketResolvePort` | `backend/app/settlement/market_port.py` | `@runtime_checkable Protocol` — `mark_resolved(session, *, market_id, winning_outcome_id, resolution_source, justification) -> None` and `mark_unresolved(session, *, market_id) -> None`. Writes on the CALLER's session, MUST NOT commit. | Pass the SAME `HouseMarketResolveAdapter()` per child. |
| `HouseMarketResolveAdapter` | `backend/app/settlement/adapters.py` | Concrete `MarketResolvePort`. `mark_resolved` sets `Market.status=RESOLVED`, `resolved_at=now`, persists `winning_outcome_id`/`resolution_source`/`resolution_justification`. `mark_unresolved` sets `status=CLOSED`, `resolved_at=None`. Raises `NoResultFound` if no market. | The resolver the event loop injects per child. |
| `AuditService.record` | `backend/app/core/audit/service.py` | `async staticmethod record(session, *, actor: str, event_type: str, payload: dict[str, Any], ip: str \| None = None, tenant_id: UUID \| None = None) -> AuditLog`. Caller owns the tx (only flushes). Actor convention: `f"user:{actor_user_id}"` or `"system"`. | Write the event-level `event.resolved`/`event.voided`/`event.reversed` row in its own small `async with session.begin()`. |
| `_get_session_maker()` | `backend/app/db/session.py` | `@lru_cache async_sessionmaker[AsyncSession]` with `expire_on_commit=False`. Used by EVERY existing task to make a fresh per-unit-of-work session: `sm = _get_session_maker(); session = sm()`. | **The fresh-session-per-child factory.** |

### Supporting (data the loop reads)

| Symbol | File | Contract (verified) | When to use |
|--------|------|---------------------|-------------|
| `MarketGroup` | `backend/app/markets/models.py` | Cols: `id`, `title`, `source` (`HOUSE`/`POLYMARKET`), `source_event_id`, `category`, `slug`, timestamps, `tenant_id`. **NO `status`, NO `winning_outcome`** (EVT-06). Relationship `markets: list[Market]` with **`lazy="raise"`**. | Identify the group, read `source` for the mirrored-reject gate, iterate children. |
| `Market` | same | Has `group_id: UUID \| None`, `group_item_title: str \| None`, `source` (HOUSE/POLYMARKET), `status: str` (DRAFT/OPEN/CLOSED/RESOLVED/CANCELLED), `winning_outcome_id: UUID \| None`. Relationships `outcomes` and `group`, both **`lazy="raise"`**. | The children; `Market.status` is `derive_event_status`'s primary input; `winning_outcome_id` tells which child won (the YES winner). |
| `Outcome` | same | Cols: `id`, `market_id`, `label: str` (e.g. `"YES"`/`"NO"` house, `"Yes"`/`"No"` Polymarket), `initial_odds`, `current_odds`. | Map winning child→its YES outcome_id; map each loser/void child→its NO outcome_id. |
| `MarketStatus` enum | `backend/app/markets/enums.py` | `DRAFT, OPEN, CLOSED, RESOLVED, CANCELLED` (str values). | `derive_event_status` checks `child.status == MarketStatus.RESOLVED.value`. |
| `MarketSourceEnum` enum | same | `HOUSE = "HOUSE"`, `POLYMARKET = "POLYMARKET"`. | Mirrored-reject gate: `group.source == MarketSourceEnum.POLYMARKET.value` ⇒ raise. |
| Bet status constants | `backend/app/bets/constants.py` | `BET_PENDING="PENDING"`, `BET_SETTLED_WON="SETTLED_WON"`, `BET_SETTLED_LOST="SETTLED_LOST"`. | Only relevant indirectly — the idempotency gate is inside `SettlementService`. |
| `_map_winning_outcome_id` | `backend/app/integrations/polymarket/adapter.py` | `(outcome_prices_raw, outcomes_raw, db_outcomes) -> UUID` — the MIRRORED winner mapping (Gamma price "1"/"1.0" → matching DB label). | Reference only — confirms how the mirrored path picks a winner. Phase 15 does NOT call it (mirrored is verify-only). |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-child fresh session (Option A) | One outer session/tx spanning all children (Option B) | **REJECTED by CONTEXT and by the 23505 landmine.** Option B would chain two self-committing `SettlementService` calls in one session ⇒ `InvalidRequestError` on the second's `begin()`, and on replay the dangling-tx bug. Option A also gives best-effort partial-failure semantics for free. |
| Loop `resolve_market` for void | A dedicated void/refund code path | **REJECTED.** EVA-04 void = all-children-NO (not a refund); the existing `resolve_market` already does exactly that when given each child's NO outcome. A refund path doesn't exist in the ledger (Future Requirements). |
| `derive_event_status` reading children via relationship | Explicit `select(Market.status).where(group_id==...)` query | Both valid (CONTEXT discretion). Relationship needs `selectinload(MarketGroup.markets)` because of `lazy="raise"`; an explicit query avoids loading full Market rows. Recommend the explicit/eager query for clarity. |

**Installation:** None. No new packages. No migration.

**Version verification:** N/A — no external packages added. (Existing stack already pinned; `npm/pip index` not applicable to this phase.)

## Package Legitimacy Audit

Not applicable — **this phase installs zero external packages and adds no dependency** (CONTEXT: "No new dependencies"). All code composes existing in-repo modules. slopcheck/registry verification is moot. No `## Package Legitimacy Audit` table rows.

## Architecture Patterns

### System Architecture Diagram

```
ADMIN ACTION (Phase 16 HTTP, not this phase)
        │  resolve_event(group_id, winning_outcome_id, justification, actor_user_id)
        ▼
┌──────────────────────────── EventService (NEW, app/settlement/event_service.py) ────────────────────────────┐
│                                                                                                              │
│  1. LOAD group + children (+ each child's outcomes)   ── reject if group.source == POLYMARKET (EVA-06) ──┐   │
│         session_0 = _get_session_maker()()  (read-only)                                                  │   │
│         eager-load MarketGroup.markets (lazy="raise" → selectinload), and Market.outcomes per child      │   │
│                                                                                                          │   │
│  2. VALIDATE justification non-blank  ── raise on whitespace ──                                           │   │
│                                                                                                          │   │
│  3. ORDER children: winning child FIRST, then losers by market.id  (winners paid before any hiccup)      │   │
│                                                                                                          │   │
│  4. FOR EACH child  ── on its OWN FRESH session (the 23505 landmine) ──                                   │   │
│         ┌─ session_k = _get_session_maker()()  ──────────────────────────────────────────────────────┐  │   │
│         │   winner-child →  SettlementService.resolve_market(session_k, child_yes_outcome_id, …)       │  │   │
│         │   loser-child  →  SettlementService.resolve_market(session_k, child_NO_outcome_id, …)        │──┼── opens its OWN begin();
│         │   reverse path →  SettlementService.reverse_settlement(session_k, …)                         │  │   posts ledger transfers,
│         └─ on child failure: record failed id, CONTINUE (best-effort; event → partially_resolved) ────┘  │   flips bets, marks market,
│                                                                                                          │   writes settlement.* audit
│  5. EVENT AUDIT  ── its own small tx ──                                                                   │   (ALL UNCHANGED)
│         session_a = _get_session_maker()();  async with session_a.begin():                               │   │
│             AuditService.record(event_type="event.resolved"|"event.voided"|"event.reversed", payload=…)  │   │
│                                                                                                          │   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘   │
                                                                                                                  │
   derive_event_status(children)  ── PURE, read-time, no DB write, no stored column (EVT-06) ───────────────────┘
        inputs: each child.status (+ which child has a winning_outcome_id / won YES)
        output: "open" | "partially_resolved" | "resolved" | "void"

MIRRORED PATH (EVA-06 — VERIFY ONLY, no new code):
   Celery beat → detect_polymarket_resolutions → SettlementService.resolve_market(actor_user_id=None) per child
   (children of a POLYMARKET market_group auto-settle individually; EventService refuses to touch them)
```

The diagram traces the primary use case (admin resolves a house event) from input to output. File-to-symbol mapping is in the Standard Stack tables above.

### Recommended Project Structure

```
backend/app/settlement/
├── event_service.py     # NEW — EventService (resolve_event/void_event/reverse_event) + derive_event_status
├── service.py           # UNCHANGED — SettlementService (looped per child)
├── market_port.py       # UNCHANGED — MarketResolvePort (passed per child)
├── adapters.py          # UNCHANGED — HouseMarketResolveAdapter (injected per child)
├── plan.py / payout.py / constants.py / schemas.py / router.py   # UNCHANGED (router endpoints are Phase 16)

backend/tests/settlement/
├── test_event_service.py     # NEW — integration (testcontainers): resolve/void/reverse/partial/replay/mirrored-reject
├── test_derive_event_status.py  # NEW — pure unit tests for the status projection (no DB)
```

`derive_event_status` MAY live in `event_service.py` (CONTEXT discretion) — recommend keeping it module-level (not a classmethod) so it is trivially unit-testable without a session, mirroring how `build_settlement_plan` is a pure free function in `plan.py`.

### Pattern 1: Loop a self-committing service on a FRESH session per item (the existing repo idiom)

**What:** Each child settlement runs in its own `with session_maker() as session:` block; the service owns the `begin()` inside it.
**When to use:** Any time you call ≥2 self-committing financial services in sequence (resolve_event, void_event, reverse_event all loop N children).
**Example:**
```python
# Source: pattern derived from app/integrations/polymarket/tasks.py (_run_detect_resolutions)
#         + tests/settlement/test_resolve_market.py (committed-session helpers)
from app.db.session import _get_session_maker
from app.settlement.adapters import HouseMarketResolveAdapter
from app.settlement.service import SettlementService

session_maker = _get_session_maker()
resolver = HouseMarketResolveAdapter()
failed: list[UUID] = []

for child_market_id, child_winning_outcome_id in ordered_children:
    # FRESH session per child — never reuse across two settle calls (23505 dangling-tx landmine).
    async with session_maker() as child_session:
        try:
            await SettlementService.resolve_market(
                child_session,
                market_id=child_market_id,
                winning_outcome_id=child_winning_outcome_id,
                market_resolver=resolver,
                justification=justification,
                actor_user_id=actor_user_id,
            )
        except Exception:        # best-effort partial failure (CONTEXT)
            failed.append(child_market_id)
            continue              # already-settled siblings stay intact
```
**Why a fresh session and not one outer tx:** `resolve_market` opens `async with session.begin()` internally; a second call on the same session after the first commits/replays hits `InvalidRequestError: A transaction is already begun on this Session` (the 23505 dangling-tx family — see Common Pitfalls §1).

### Pattern 2: Map winning outcome → child YES/NO via case-insensitive label match

**What:** The winning child gets its YES outcome settled; every losing child (and every child in a void) gets its NO outcome settled.
**When to use:** Building the `(child_market_id, winning_outcome_id)` list before the loop.
**Example:**
```python
# Source: app/markets/service.py lines 176-185 and 369-378 (the canonical IN-01 pattern)
from sqlalchemy import func, select
from app.markets.models import Outcome

async def _yes_outcome_id(session, market_id: UUID) -> UUID:
    # House labels are "YES"; mirrored Polymarket labels are title-case "Yes".
    # A case-sensitive == "YES" silently misses mirrored markets (verified IN-01 bug fix).
    return (
        await session.execute(
            select(Outcome.id).where(
                Outcome.market_id == market_id,
                func.upper(Outcome.label) == "YES",
            )
        )
    ).scalar_one()

async def _no_outcome_id(session, market_id: UUID) -> UUID:
    return (
        await session.execute(
            select(Outcome.id).where(
                Outcome.market_id == market_id,
                func.upper(Outcome.label) != "YES",   # the other binary leg
            )
        )
    ).scalar_one()
```
**Note for the planner:** in **resolve**, the admin supplies ONE `winning_outcome_id`; that outcome belongs to ONE child (the YES winner). For that child, settle with the supplied id. For every OTHER child, settle with that child's NO outcome (the event-of-binaries rule: only one child can be YES). In **void**, every child settles with its NO outcome. Validation that the supplied `winning_outcome_id` actually belongs to a child of the group is a **Phase 16** endpoint concern (CONTEXT discretion), but `EventService` should still defensively confirm it maps to exactly one child before looping.

### Pattern 3: Derived status as a pure projection (EVT-06)

**What:** `derive_event_status(children) -> str` with no DB write and no stored column.
**When to use:** Any read of an event's status (this phase ships the function; Phase 16/17 consume it).
**Example:** see Code Examples below.

### Pattern 4: Event-level audit in its own small transaction

**What:** After the per-child loop, write ONE `event.resolved`/`event.voided`/`event.reversed` row, atomic in its own tiny tx — consistent with the per-child txs and with how `force_settle` writes its override audit in a separate `async with session.begin():` AFTER settlement commits.
**Example:**
```python
# Source: app/settlement/router.py force_settle (action-THEN-audit in a separate begin())
async with session_maker() as audit_session, audit_session.begin():
    await AuditService.record(
        audit_session,
        actor=f"user:{actor_user_id}" if actor_user_id is not None else "system",
        event_type="event.resolved",          # or event.voided / event.reversed
        payload={
            "group_id": str(group_id),
            "winning_outcome_id": str(winning_outcome_id),  # omit/None for void
            "child_count": len(children),
            "children_settled": len(children) - len(failed),
            "children_failed": [str(x) for x in failed],
            "justification": justification,
        },
    )
```

### Anti-Patterns to Avoid

- **Chaining two `SettlementService` calls on one session** — the 23505 dangling-tx landmine (Pitfall 1). Fresh session per child, always.
- **Storing event status / a winning_outcome on `market_groups`** — violates EVT-06. Migration 0011 deliberately omitted these columns; do not add them.
- **Re-implementing settlement, payout, reverse, or audit logic** — all exist and are validated. The event service only orchestrates.
- **Settling a child via `closed=true` alone** — the spike-002 `_derive_status` guard (closed + `umaResolutionStatus="resolved"` + clear winner) is the ONLY path to a child `MarketStatus`; the event loop adds no status transition of its own beyond what `SettlementService`+`HouseMarketResolveAdapter` already do.
- **Touching mirrored (`source=POLYMARKET`) groups** in resolve/void/reverse — they must raise; mirrored children auto-settle via `detect_polymarket_resolutions` (EVA-06).
- **Adding FOR UPDATE / lock logic in the event loop** — the per-market locks (canonical UUID order) are already inside `SettlementService`. Per-child sessions touch disjoint per-market liability accounts (+ shared house_promo/house_revenue, which `SettlementService` already locks in order), so no cross-child deadlock surface is introduced.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-child payout / loser sweep / bet flip | A new settlement routine | `SettlementService.resolve_market` (UNCHANGED) | ACID, idempotent, lock-ordered, audited, spike-004-clean — re-deriving it risks the double-debit and deadlock bugs the spike already eliminated. |
| Reversing a resolution | DELETE/UPDATE of ledger entries | `SettlementService.reverse_settlement` (UNCHANGED) | Append-only compensating transfers (WAL-06); deleting entries breaks the double-entry invariant and the audit trail. |
| Void = refund | A stake-refund path | `resolve_market(child, NO outcome)` per child | No refund mechanism exists in the ledger (Future Requirements); EVA-04 void is defined as all-children-NO. |
| Marking a child market resolved | Direct `Market.status = "RESOLVED"` UPDATE | `HouseMarketResolveAdapter` via the port (inside `SettlementService`) | Must commit atomically with payouts + persist `winning_outcome_id`/`resolution_source`/`justification` (STL-06); a bare UPDATE would diverge status from money. |
| Idempotent replay | A "already settled?" guard of your own | The existing `status==PENDING` filter + `settle:{bet_id}:{leg}` keys inside `SettlementService` | Re-running resolve/void over already-settled children is a true no-op for free — the event loop needs no replay bookkeeping. |
| Mirrored UMA auto-settle | A new mirrored event-settlement task | `detect_polymarket_resolutions` (VERIFY only) | EVA-06 is explicit: verify, do not rebuild. The task already calls `SettlementService(actor_user_id=None)` per market. |
| Ledger-integrity assertion | A bespoke SUM check | `app.wallet.reconcile._reconcile_async(session)` | The production drift detector already computes `SUM(credit)-SUM(debit) == balance` per account; reuse it in tests. |

**Key insight:** Phase 15's entire value is *not writing settlement code*. Every transactional hazard (atomicity, idempotency, deadlocks, append-only reversal, negative-balance floor) is already solved one level down. The risk surface is purely orchestration: session-per-child discipline, correct YES/NO mapping, derived-status correctness, and the mirrored-reject gate.

## Runtime State Inventory

> This is a service-addition phase (new code looping existing primitives), NOT a rename/refactor/migration. A full runtime-state sweep is not the primary concern, but the categories are addressed for completeness since the phase reads existing Phase-13/14 data.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Real `market_groups` rows + stamped `Market.group_id` children written by Phase 14's Gamma `/events` sync (mirrored, `source=POLYMARKET`). These are the **verification fixtures** for EVA-06 (mirrored children auto-settle). HOUSE `market_groups` do not exist yet (created by Phase 16 CRUD / Phase 18 seed). | None to migrate. Phase 15 tests must SYNTHESIZE house `market_groups` + children (as the existing settlement tests synthesize markets) since no house events exist pre-Phase-16. Mirrored verification reads Phase-14 data read-only. |
| Live service config | `detect_polymarket_resolutions` runs on Celery beat (60s) with its own `DETECT_LOCK_KEY` Redis lock. Unchanged by this phase. | None — verify-only. Do not alter beat schedule or locks. |
| OS-registered state | None — no OS-level registration touches event settlement. | None — verified by reading `tasks.py` (Redis SETNX locks only, no OS state). |
| Secrets/env vars | None new. `EventService` reads no secrets; `SettlementService`/audit use existing DB session only. | None. |
| Build artifacts / installed packages | None — no new package, no migration, no compiled artifact. `market_groups` table + columns already shipped in migration 0011 (applied at `alembic upgrade head`). | None. |

**Nothing found requiring migration or re-registration** — the only "state" Phase 15 depends on (the `market_groups` schema) already exists from Phase 13's migration 0011, and the mirrored data already exists from Phase 14.

## Common Pitfalls

### Pitfall 1: Dangling open transaction when chaining two settlement calls on one session (THE landmine)
**What goes wrong:** Looping `SettlementService.resolve_market` (or `reverse_settlement`) twice on the SAME `AsyncSession` raises `sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session` — but only on the SECOND iteration, and especially on the **idempotent-replay path** where a duplicate `idempotency_key` raises Postgres `23505`; the service's `except` rolls back its `begin()` block, then a bare follow-up `SELECT` autobegins a NEW implicit transaction that is left OPEN. The next self-committing call's `begin()` then explodes.
**Why it happens:** Each `SettlementService` method owns its own `async with session.begin()`; the services are designed to be the sole owner of a session's unit of work. (Verified in `app/settlement/service.py` lines 110 and 277; documented in operator memory `xprediction-financial-services-idempotent-tx-chaining`; it bit the seed harness in real life.)
**How to avoid:** **Open a fresh `async with session_maker() as session:` for every child settlement.** Never wrap two settle calls in one `with`/`begin()`. This is the entire reason CONTEXT mandates Option A (per-child ACID tx). `_run_detect_resolutions` gets away with one session across its loop ONLY because each market it settles triggers exactly one `resolve_market` call and then continues — it never chains two settles back-to-back on the same session within one already-begun tx; the EventService DOES chain, so it MUST use fresh sessions.
**Warning signs:** Tests pass on the first resolve but fail on the idempotent-replay test (the second `resolve_event` over the same group) with `InvalidRequestError`. The replay test is the canary.

### Pitfall 2: Settling the wrong leg on mirrored vs house labels (YES/NO mapping)
**What goes wrong:** A case-sensitive `Outcome.label == "YES"` silently returns nothing for Polymarket-mirrored children (whose labels are title-case `"Yes"`), so the winning/NO leg is misidentified.
**Why it happens:** House markets seed labels `"YES"`/`"NO"`; the Polymarket adapter stores Gamma's title-case `"Yes"`/`"No"` verbatim (`label[:50]`, never normalized). Documented as the IN-01 fix in `app/markets/service.py`.
**How to avoid:** Always match `func.upper(Outcome.label) == "YES"` (Pattern 2). For Phase 15 this primarily matters for HOUSE events (which are what resolve/void operate on), but using the case-insensitive form keeps the helper correct if ever pointed at mirrored data and matches the established repo idiom.
**Warning signs:** A void or resolve appears to settle but no bets flip (the NO/YES outcome_id didn't match any bet's `outcome_id`).

### Pitfall 3: Reverse hitting the `CHECK (balance >= 0)` floor on one child
**What goes wrong:** `reverse_settlement` claws back a winner's payout; if that winner already spent the winnings, the wallet would go negative and Postgres rejects it via `CHECK (balance >= 0)`, rolling back that child's reversal.
**Why it happens:** Reversal debits the winner's wallet (inverse of the stake-return + winnings legs). This is by design (verified in `service.py` docstring + `test_reverse_settlement_is_atomic_on_failure`).
**How to avoid:** Per-child fresh sessions make this a **per-child rollback** — the failed child rolls back alone, siblings already reversed stay reversed, the event lands `partially_resolved`/partially-reversed, and the admin can retry. Do NOT wrap all child reversals in one tx (would roll back ALL of them on any one floor hit) — another reason for Option A.
**Warning signs:** A reverse test where a winner spent funds; expect that one child to raise/rollback while others succeed.

### Pitfall 4: `lazy="raise"` on `MarketGroup.markets`, `Market.outcomes`, `Market.group`
**What goes wrong:** Accessing `group.markets` or `child.outcomes` without eager-loading raises `sqlalchemy.exc.InvalidRequestError` (`'markets' is not available due to lazy='raise'`).
**Why it happens:** The repo enforces explicit eager-load discipline — every relationship is `lazy="raise"` (verified in `models.py`).
**How to avoid:** Use `selectinload(MarketGroup.markets)` (and `selectinload(Market.outcomes)`) on the load query, OR query the children/outcomes explicitly (CONTEXT discretion). The existing tasks use `selectinload(Market.outcomes)` everywhere.
**Warning signs:** `InvalidRequestError` mentioning `lazy='raise'` the moment you touch a relationship attribute.

### Pitfall 5: Integration-test session model — committed vs rolled-back
**What goes wrong:** The `async_session` fixture wraps each test in a rolled-back transaction, but `SettlementService` owns its own `begin()`/commit. The settlement tests therefore CANNOT use `async_session` for the act — they use `_get_session_maker()` (real committed sessions) and assert against committed state, then rely on the session-scoped container + per-test fresh UUIDs for isolation.
**Why it happens:** A service that commits internally can't run inside an outer rolled-back tx (verified: `test_resolve_market.py` uses `_get_session_maker()` committed helpers; `test_reconcile.py` uses `async_session` only because `_reconcile_async` is read-only and accepts an injected session).
**How to avoid:** New `EventService` integration tests MUST follow `test_resolve_market.py`: synthesize markets/groups/wallets via committed `_get_session_maker()` helpers with fresh UUIDs, run `EventService` on fresh sessions, assert committed balances/bet-status/audit rows. For the spike-004 integrity check after each path, either (a) assert per-account balances net correctly (as the existing settlement tests do — liability drains to 0, house deltas match), or (b) call `_reconcile_async(fresh_committed_session)` and assert `drift_count == 0` for the touched accounts. Option (b) is closer to the "spike-004 integrity check green" requirement; note it excludes `house_promo` by design.
**Warning signs:** Cross-test contamination (shared house singletons drift) — use before/after DELTAS on `HOUSE_PROMO_ACCOUNT_ID`/`HOUSE_REVENUE_ACCOUNT_ID`, absolute values only on per-test fresh accounts (the pattern `test_resolve_market.py` already uses).

### Pitfall 6: Re-resolve-after-reverse idempotency-key collision (known deferred limitation)
**What goes wrong:** `reverse_idempotency_key` docstring notes: re-RESOLVING a market AFTER a reversal reuses the original `settle:{bet_id}:{leg}` keys and would collide on `23505`. v1 reversal restores pre-settlement state for audit/correction; it does NOT yet support re-resolution.
**Why it happens:** No per-bet settlement epoch in the idempotency key (deferred in Phase 5).
**How to avoid:** Scope Phase 15's reverse to "restore + audit" (mirrors STL-07), NOT "reverse then re-resolve in the same lifecycle." Do not write a test that resolves → reverses → re-resolves and expects success; that's a known deferred gap, out of scope for this phase. Flag it in the plan so it isn't mistaken for a Phase-15 bug.
**Warning signs:** A test that resolves, reverses, then resolves again on the same bets failing with `23505`.

## Code Examples

### `derive_event_status` — the pure read-projection (EVT-06)
```python
# Source: synthesized from CONTEXT decisions + app/markets/enums.py (MarketStatus)
# Pure function, no I/O — unit-testable without a DB. Lives in event_service.py.
from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass
from app.markets.enums import MarketStatus

@dataclass(frozen=True, slots=True)
class ChildStatus:
    """Minimal per-child facts derive_event_status needs (decoupled from the ORM for unit tests)."""
    status: str            # Market.status value
    is_yes_winner: bool    # this child resolved with its YES outcome as the winner

def derive_event_status(children: Sequence[ChildStatus]) -> str:
    if not children:
        return "open"
    resolved = [c for c in children if c.status == MarketStatus.RESOLVED.value]
    n_resolved, n_total = len(resolved), len(children)
    if n_resolved == 0:
        return "open"
    if n_resolved < n_total:
        return "partially_resolved"
    # all children resolved → resolved (exactly one YES winner) vs void (no YES winner).
    # Event outcomes are mutually exclusive: a real resolution has exactly one YES.
    return "resolved" if any(c.is_yes_winner for c in resolved) else "void"
```
**Planner note on `is_yes_winner`:** a child "won YES" when its persisted `Market.winning_outcome_id` equals that child's YES outcome id (`func.upper(label)=="YES"`). The service computes this when projecting status from real rows; the unit test passes the boolean directly.

### Loading a group's children + outcomes (dodging `lazy="raise"`)
```python
# Source: selectinload idiom from app/integrations/polymarket/tasks.py + app/markets/models.py
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.markets.models import Market, MarketGroup

async def _load_group_with_children(session, group_id):
    group = (
        await session.execute(
            select(MarketGroup)
            .where(MarketGroup.id == group_id)
            .options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
        )
    ).scalar_one_or_none()
    return group   # group.markets and child.outcomes are now safe to access
```

### Mirrored-reject gate (EVA-06)
```python
# Source: app/markets/enums.py (MarketSourceEnum) + force_settle's POLYMARKET check in router.py
from app.markets.enums import MarketSourceEnum

if group.source == MarketSourceEnum.POLYMARKET.value:
    raise ValueError(  # Phase 16 maps this to HTTP 4xx; the service just refuses.
        "Mirrored (Polymarket) events are admin read-only; use force-settle (ADM-06)."
    )
```

### Reusing the production integrity check in a test
```python
# Source: app/wallet/reconcile.py + tests/wallet/test_reconcile.py
import app.wallet.reconcile as reconcile
from app.db.session import _get_session_maker

async def _assert_ledger_clean():
    sm = _get_session_maker()
    async with sm() as s:
        summary = await reconcile._reconcile_async(s)   # SUM(credit)-SUM(debit) == balance per account
    assert summary["drift_count"] == 0   # house_promo excluded by design
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Multi-outcome deferred to v2 (v1.0 MKT-08) | Event-of-binaries: N binary markets grouped under `market_groups` (EVT-01) | Phase 13 (migration 0011, 2026-06-05) | Phase 15 settles an event by looping the unchanged per-market settlement — no new market/bet/ledger model. |
| Settlement only via single-market admin endpoint / UMA detection | Same primitives, now also driven by an event-level loop | Phase 15 (this phase) | The composition is new; the primitives are not. |

**Deprecated/outdated:**
- Spike `settlement.md` pseudocode shows integer PKs, fixed-2x binary payout, and `markets.winning_outcome`/`settled_at` columns — that is the SPIKE prototype, NOT production. Production uses UUID PKs, `stake / odds_at_placement` payout, `MarketStatus` enum strings, and `Market.winning_outcome_id`/`resolved_at`. Read `app/settlement/service.py`, not the spike pseudocode, for the real contract.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | In **resolve**, exactly one child carries the winning (YES) outcome; every other child settles on its NO outcome (event-of-binaries: outcomes mutually exclusive). | Pattern 2, derive_event_status | If an event could legitimately have multiple YES winners, the `resolved`/`void` disambiguation and the NO-for-losers mapping would be wrong. CONTEXT explicitly asserts mutual exclusivity, so risk is low — but the planner should confirm the Phase-16 admin endpoint enforces "one winning outcome per event." |
| A2 | The spike-004 integrity check the phase must keep green is the production `app.wallet.reconcile._reconcile_async` (SUM(entries)==balance, `house_promo` excluded). No separate `verify_ledger_integrity` helper exists in the app. | Don't Hand-Roll, Code Examples, Validation Architecture | If a different/stricter integrity helper is expected, tests would target the wrong assertion. Searched the backend: only `reconcile.py` + `test_reconcile.py` implement the SUM check; the spike's `verify_ledger_integrity` is prototype-only. Low risk. |
| A3 | `derive_event_status` and the EventService loop need NO new FOR UPDATE / locking beyond what `SettlementService` already holds (per-child sessions touch disjoint liability accounts + the already-locked house singletons). | Anti-Patterns | If two concurrent event operations on overlapping groups raced, the only shared rows are house_promo/house_revenue, which `SettlementService` already locks in canonical UUID order — so deadlock risk is unchanged. Low risk; concurrency tests are optional. |
| A4 | `_get_session_maker()` is the appropriate fresh-session factory for the EventService (CONTEXT leaves the exact shape to discretion). | Standard Stack, Pattern 1 | The planner may instead inject an `async_sessionmaker` param for testability. Either satisfies "fresh session per child." No correctness risk; a style choice. |

## Open Questions

1. **Integrity-check assertion style in tests (per-account deltas vs `_reconcile_async`).**
   - What we know: existing settlement tests assert per-account balances (liability→0, house deltas) rather than calling the reconciler; `_reconcile_async` exists and accepts an injected session.
   - What's unclear: whether "spike-004 integrity check green after every path" mandates literally invoking the reconciler, or whether equivalent per-account balance assertions suffice.
   - Recommendation: do BOTH where cheap — assert the per-market liability drains to 0 and house deltas match (fast, precise) AND call `_reconcile_async(fresh_session)` asserting `drift_count == 0` at the end of each resolve/void/reverse/partial/replay test (the literal integrity gate). This is the strongest, lowest-cost reading of the requirement.

2. **Where the winning-outcome → child validation lives for `EventService` vs Phase 16.**
   - What we know: CONTEXT says the admin endpoint validates the selection in Phase 16; the service trusts a valid outcome (matching `SettlementService`'s "winning_outcome_id is trusted" contract).
   - What's unclear: how defensive `EventService` itself should be (raise if the supplied outcome maps to no child of the group?).
   - Recommendation: `EventService.resolve_event` should defensively confirm the supplied `winning_outcome_id` belongs to exactly one child of the group BEFORE looping (cheap query), and raise otherwise — this prevents a silently-misrouted resolution and is independent of the Phase-16 HTTP validation. Document as a service-layer guard, not a substitute for the endpoint check.

## Environment Availability

> Phase 15 is code + tests only — no NEW external dependency. The existing test/runtime stack is the relevant environment.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker (testcontainers Postgres 16) | Integration tests (`engine` fixture runs `alembic upgrade head`) | Assumed ✓ (CLAUDE.md: "Docker para fases backend") | postgres:16-alpine | None — integration tests require it. On Windows worktree the suite flakes; run on Linux CI. |
| Python 3.12 + uv | `cd backend && uv run pytest` | Assumed ✓ | 3.12 | None |
| Postgres 16 (`pg_trgm`) | migration 0011 (already applied) | ✓ via container | 16 | None — already shipped. |
| Migration `0011_phase13_market_groups` | `market_groups` table + `markets.group_id`/`group_item_title` | ✓ (single head off 0010) | — | None — required schema already exists. |

**Missing dependencies with no fallback:** None — all required infrastructure already exists (no new package, no new migration).
**Missing dependencies with fallback:** None.

## Validation Architecture

> `workflow.nyquist_validation: true` (config.json) — this section is included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`loop_scope="session"`) + testcontainers (Postgres 16) |
| Config file | `backend/pytest.ini` / `pyproject.toml` (markers: `integration`, `asyncio`); `backend/tests/conftest.py` provides `engine`, `async_session`, `client`, `fake_redis` |
| Quick run command (per module) | `cd backend && uv run pytest tests/settlement/test_derive_event_status.py -x` (pure unit, no Docker) |
| Full suite command | `cd backend && uv run pytest tests/ -x` (Linux CI is source of truth; Windows worktree flakes) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EVT-06 | `open`/`partially_resolved`/`resolved`/`void` derived from children + winner; no stored column | unit | `uv run pytest tests/settlement/test_derive_event_status.py -x` | ❌ Wave 0 |
| EVA-03 | Resolve house event → every child settled (winner→YES, losers→NO); idempotent replay no-op; integrity clean | integration | `uv run pytest tests/settlement/test_event_service.py -k resolve -x` | ❌ Wave 0 |
| EVA-04 | Void → every child settled on NO (YES bettors lose, NO bettors win); NOT a refund; integrity clean | integration | `uv run pytest tests/settlement/test_event_service.py -k void -x` | ❌ Wave 0 |
| EVA-05 | Reverse → compensating entries restore pre-settlement state; idempotent; per-child `balance>=0` floor rolls back that child only; audit row | integration | `uv run pytest tests/settlement/test_event_service.py -k reverse -x` | ❌ Wave 0 |
| EVA-03 | Partial failure → settled children intact, failed surfaced, event `partially_resolved`; re-run finishes (no double-credit) | integration | `uv run pytest tests/settlement/test_event_service.py -k partial -x` | ❌ Wave 0 |
| EVA-06 | `EventService` rejects `source=POLYMARKET` group; mirrored children auto-settle via `detect_polymarket_resolutions` (verify, unchanged) | integration | `uv run pytest tests/settlement/test_event_service.py -k mirrored -x` | ❌ Wave 0 |
| (cross-cut) | spike-004 double-entry integrity GREEN after resolve/void/reverse/partial/replay | integration assertion | `_reconcile_async(fresh_session) → drift_count == 0` inside each test above | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/settlement/test_derive_event_status.py tests/settlement/test_event_service.py -x` (the phase's own new tests).
- **Per wave merge:** `cd backend && uv run pytest tests/settlement/ tests/wallet/ -x` (settlement + ledger neighbours) on Linux CI.
- **Phase gate:** full `pytest tests/ -x` + ruff + mypy GREEN on Linux CI before `/gsd-verify-work`. (Do NOT gate on the Windows worktree — environmental flake.)

### Wave 0 Gaps
- [ ] `tests/settlement/test_derive_event_status.py` — pure unit tests for the status projection (open/partial/resolved/void/empty + the no-YES-winner ⇒ void edge). Covers EVT-06.
- [ ] `tests/settlement/test_event_service.py` — integration (testcontainers) for resolve / void / reverse / partial-failure / idempotent-replay / mirrored-reject. Covers EVA-03/04/05/06. Mirror `test_resolve_market.py` committed-session helpers (`_get_session_maker()`, `_seed_wallet`, `FakeMarketResolver`/`RaisingMarketResolver`, `_audit_for_*`) and add a group/children synthesizer.
- [ ] Shared fixtures: reuse existing `engine` fixture; add a `_seed_house_event(n_children, ...)` helper (committed) producing a `market_groups` row + N HOUSE child markets each with YES/NO outcomes + placed bets — there is no existing house-event seed (Phase 18), so the test file must build one.
- [ ] Framework install: none — pytest/testcontainers already in `backend` dev deps.

*Existing infrastructure (`conftest.py` `engine`/`async_session`, the `tests/settlement/` patterns, `_reconcile_async`) covers everything except the two new test files + the house-event synthesizer above.*

## Security Domain

> `security_enforcement` key absent from config.json ⇒ treated as enabled. Included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (this phase) | The HTTP/admin-Bearer gate is **Phase 16** (router). `EventService` is service-layer only; the existing `/admin/markets/*` endpoints already enforce `current_active_admin`. |
| V3 Session Management | no | No web session handling in a settlement service. |
| V4 Access Control | partial | EVA-06 mirrored-reject IS an access-control rule (mirrored events read-only to admins). Enforced in-service by raising on `source=POLYMARKET`; the admin-role gate itself is Phase 16. |
| V5 Input Validation | yes | `justification` mandatory non-blank at the service layer (raise on whitespace). Winning-outcome-belongs-to-group defensive check (Open Q2). UUID typing on all ids (Pydantic/SQLAlchemy). Money never float (delegated to `SettlementService`). |
| V6 Cryptography | no | No crypto in settlement orchestration; no secrets handled. |
| (audit / non-repudiation) | yes | Every resolve/void/reverse writes an immutable `event.*` audit row (actor, group, justification) IN ADDITION to per-child `settlement.*` rows — append-only via `AuditService.record` (D-20/D-21). |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Double-credit / double-refund via repeated resolve/reverse | Tampering | Existing per-bet idempotency keys + `status==PENDING`/`SETTLED_*` filters inside `SettlementService` (the event loop inherits idempotency for free). |
| Money drift (balance ≠ ledger) after a multi-child operation | Tampering | spike-004 integrity check (`_reconcile_async`) asserted GREEN after every path; append-only double-entry (WAL-06); `CHECK(balance>=0)`. |
| Admin mutating a mirrored (UMA-owned) event out from under the oracle | Tampering / Elevation | EVA-06 mirrored-reject gate (`source=POLYMARKET` ⇒ raise) except the audited emergency force-settle (ADM-06). |
| Repudiation of a resolution/void/reversal | Repudiation | Immutable `event.resolved`/`voided`/`reversed` audit rows with actor + justification, atomic in their own tx. |
| Partial-failure leaving inconsistent money state | Tampering / DoS | Per-child ACID transactions (Option A): a failed child rolls back alone; settled siblings stay correct; `partially_resolved` is a valid, recoverable state; idempotent re-run finishes. |
| SQL injection via outcome/group ids | Tampering | Parameterized SQLAlchemy queries throughout; ids are typed UUIDs, never string-interpolated. |

## Sources

### Primary (HIGH confidence) — all current in-repo source, read this session
- `backend/app/settlement/service.py` — `SettlementService.resolve_market` / `reverse_settlement` exact signatures, internal `session.begin()`, idempotency gates, lock ordering, audit rows.
- `backend/app/settlement/market_port.py`, `adapters.py`, `plan.py`, `constants.py`, `schemas.py`, `router.py` — port contract, `HouseMarketResolveAdapter`, `SettlementPlan`, idempotency-key namespacing + the re-resolve-after-reverse deferred note, existing resolve/reverse/force-settle endpoints (STL-07 / ADM-06).
- `backend/app/markets/models.py` — `MarketGroup` (NO status/winner col), `Market` (group_id/group_item_title/source/status/winning_outcome_id), `Outcome` (label), all `lazy="raise"`.
- `backend/app/markets/enums.py` — `MarketStatus`, `MarketSourceEnum`.
- `backend/app/markets/service.py` (lines 176-185, 369-378) — the canonical `func.upper(Outcome.label) == "YES"` IN-01 case-insensitive mapping.
- `backend/app/integrations/polymarket/tasks.py` — `detect_polymarket_resolutions` (`_run_detect_resolutions`) calling `SettlementService.resolve_market(actor_user_id=None)`; the `_get_session_maker()` per-task session idiom.
- `backend/app/integrations/polymarket/adapter.py` — `_map_winning_outcome_id`, `sync_events` (how mirrored `market_groups` + stamped children are written).
- `backend/app/core/audit/service.py` — `AuditService.record` signature + `event_type` conventions.
- `backend/app/db/session.py` — `_get_session_maker()` / `_get_engine()` factories, `expire_on_commit=False`.
- `backend/app/wallet/reconcile.py` + `backend/tests/wallet/test_reconcile.py` — production integrity check (`_reconcile_async`, SUM(entries)==balance, house_promo excluded).
- `backend/tests/settlement/test_resolve_market.py`, `test_force_settle.py` — committed-session test idiom, `FakeMarketResolver`/`RaisingMarketResolver`, audit assertion helpers, mirrored/house reject patterns.
- `backend/tests/conftest.py` — `engine` / `async_session` / `client` fixtures; testcontainers + `alembic upgrade head`.
- `backend/alembic/versions/0011_phase13_market_groups.py` — confirms `market_groups` has NO status/winning_outcome column (EVT-06); the schema already exists.
- `.planning/phases/15-.../15-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/config.json` — phase scope, requirement IDs, validation/security flags.
- `.claude/skills/spike-findings-xpredict/SKILL.md` + `references/settlement.md` — spike-004 (ACID/idempotent/double-entry) + spike-002 (closed-vs-resolved) requirements.
- Operator memory `xprediction-financial-services-idempotent-tx-chaining` — the 23505 dangling-tx landmine (verified against current `service.py`).

### Secondary (MEDIUM confidence)
- None — no WebSearch/external docs were needed; the phase is entirely in-repo composition.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack (existing contracts): HIGH — every signature, transaction boundary, and idempotency gate read directly from current source this session.
- Architecture (loop + derived status + mirrored-reject): HIGH — patterns are direct extrapolations of existing tasks/tests; CONTEXT decisions are explicit and code-consistent.
- Pitfalls: HIGH — the 23505 landmine is confirmed in both code and operator memory and is reproduced by the existing service design; YES/NO label, `lazy="raise"`, and committed-session pitfalls are all observed in current code/tests.

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (stable — in-repo contracts; re-verify only if `app/settlement/` or `app/markets/models.py` change before planning).
