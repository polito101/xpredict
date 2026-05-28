# Phase 7: Polymarket Auto-Resolution & Admin Override - Research

**Researched:** 2026-05-28
**Domain:** Celery Beat auto-resolution, UMA oracle grace-period gating, admin force-settle override
**Confidence:** HIGH

---

## Summary

Phase 7 has the narrowest addition surface of any phase so far: it wires an already-proven
`SettlementService` (Phase 5) to an already-running Polymarket sync loop (Phase 6) via a new
Beat task and one new admin endpoint. The architectural payoff promised in STATE.md and ROADMAP.md
("same service reused unchanged") is fully achievable — the research confirms it.

The two primary technical risks are (1) grace-period state surviving Celery at-least-once
delivery and service restarts, and (2) outcome-winner lookup by label from `outcomePrices`
index position. Both have clean solutions derived from the existing codebase. No new external
dependencies are required; the entire phase is additive.

The critical correctness invariant — NEVER settle on `closed=true` alone, only on
`umaResolutionStatus='resolved'` + grace-period satisfied — is already encoded in
`_derive_status()` in `schemas.py` and the Phase 6 VCR fixtures prove the guard. Phase 7
must **delegate to `_derive_status()` rather than re-implementing the state machine**.

**Primary recommendation:** Implement `detect_resolution()` in `PolymarketAdapter` using
`GammaClient.fetch_market_by_id()` + `_derive_status()` for correctness, store grace-period
state in a DB column (not Redis) for crash-safety and testability, and add a new
`/admin/markets/{id}/force-settle` endpoint (distinct from `/resolve`) to keep the audit
trail semantically clean.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| UMA resolution detection | Backend Beat worker | Gamma API (external) | Polling is server-side; DB owns the state; Beat owns the schedule |
| Grace-period tracking | Database / Storage | — | Must survive restarts; Redis is volatile; DB column is the safe primitive |
| Auto-settlement trigger | API / Backend | — | Calls SettlementService which owns the ACID transaction |
| Admin force-settle UI | Frontend Server (SSR) | Admin API | Two-step confirm is a client UX concern; API executes and audits |
| Audit attribution display | API / Backend | Frontend (render) | Backend stores resolver source; frontend renders attribution label |
| Reversal flow (Phase 5 reuse) | API / Backend | — | Already implemented; Phase 7 exercises the existing path |

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STL-01 | Polymarket mirrored market auto-settles via SettlementService after UMA confirmed + grace period | Beat task `detect_polymarket_resolutions` (60s) calls `fetch_market_by_id` → `_derive_status` → grace check → `resolve_market`; DB column tracks grace start |
| ADM-06 | Admin can force-settle a stuck Polymarket-mirrored market via two-step confirm + mandatory justification, distinct audit event_type | New `/admin/markets/{id}/force-settle` endpoint; `polymarket_admin_override` audit entry with `umaResolutionStatus` captured at override time |
</phase_requirements>

---

## Standard Stack

### Core (no new packages — all already in pyproject.toml)

| Component | Already Present | Purpose in Phase 7 |
|-----------|----------------|---------------------|
| Celery + RedBeat | `celery_app.py` | Beat schedule entry for `detect_polymarket_resolutions` (60s) |
| `GammaClient.fetch_market_by_id` | `client.py` | Per-market Gamma API call for current UMA status |
| `GammaMarket._derive_status` | `schemas.py` | Canonical state machine — DO NOT re-implement |
| `SettlementService.resolve_market` | `service.py` | Called unchanged when grace check clears |
| `HouseMarketResolveAdapter` | `adapters.py` | Reused as `MarketResolvePort` in Beat task |
| `AuditService.record` | `core/audit/service.py` | Audit row for force-settle with `polymarket_admin_override` event_type |
| `settlement_admin_router` | `settlement/router.py` | Existing admin resolve/reverse; force-settle is a NEW endpoint added here |
| SQLAlchemy `Mapped` + Alembic | already in use | DB column for grace-period tracking if schema change chosen |

### Supporting

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `fakeredis` (already in test deps) | Unit-test Redis-dependent logic without Docker | For Beat task unit tests that mock the lock |
| `pytest.mock.patch` | Mock `GammaClient.fetch_market_by_id` in unit tests | All detect_resolution unit tests |
| Existing VCR fixtures in `tests/fixtures/gamma/` | Replay `resolved_market.json`, `closed_not_resolved.json` | Critical correctness tests (SC#3) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DB column for grace-period start | Redis key with TTL | Redis is simpler but volatile — a Celery restart + Redis flush would silently re-start the grace period, potentially delaying settlement. DB column survives restarts and is testable. |
| Distinct `/force-settle` endpoint | Flag on existing `/resolve` | A shared endpoint requires conditional logic and produces ambiguous audit events. Distinct endpoint is cleaner and maps 1:1 to ADM-06's distinct `event_type`. |
| `fetch_market_by_id` per market | Batch `/markets?ids=...` | Gamma API's single-market endpoint is clean and already implemented with retry. N markets × 1 req/60s = well within 300 req/10s rate limit. |

**Installation:** No new packages required. [VERIFIED: codebase inspection — all needed libraries already in `backend/pyproject.toml`]

---

## Package Legitimacy Audit

> No new external packages are introduced in Phase 7. All work reuses existing dependencies.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
[Celery Beat 60s]
      |
      v
detect_polymarket_resolutions()
      |
      +-- query DB: POLYMARKET markets WHERE status IN (OPEN, CLOSED)
      |                                 AND deadline < now()
      |
      +-- for each candidate:
      |     fetch_market_by_id(source_market_id)  -->  [Gamma API]
      |          |
      |          v
      |     GammaMarket.parse() --> _derive_status(closed, uma_status, prices)
      |          |
      |          v
      |     if internal_status != RESOLVED --> skip
      |          |
      |          v
      |     grace_period_start = market.uma_resolved_at (DB column)
      |     if None: SET uma_resolved_at = now(); flush; skip
      |     if (now - grace_period_start) < GRACE_PERIOD_MINUTES: skip
      |          |
      |          v
      |     winner_outcome_id = _map_winner(outcomePrices, market.outcomes)
      |          |
      |          v
      |     SettlementService.resolve_market(
      |         market_id, winner_outcome_id,
      |         market_resolver=HouseMarketResolveAdapter(),
      |         justification="Auto-resolved: Polymarket UMA oracle",
      |         actor_user_id=None  -- system resolution
      |     )
      |
[POST /admin/markets/{id}/force-settle]
      |
      v
admin_force_settle()
      |
      +-- validate: market.source == POLYMARKET
      +-- fetch current umaResolutionStatus from Gamma API  -->  [Gamma API]
      +-- SettlementService.resolve_market(... justification, actor_user_id=admin.id)
      +-- AuditService.record(event_type="polymarket_admin_override",
                              payload includes uma_status_at_override_time)
```

### Recommended Project Structure (additions only)

```
backend/
├── app/
│   ├── integrations/polymarket/
│   │   ├── adapter.py          # detect_resolution() UPGRADED (stub -> real impl)
│   │   └── tasks.py            # detect_polymarket_resolutions task ADDED
│   ├── settlement/
│   │   └── router.py           # /force-settle endpoint ADDED
│   └── core/config.py          # POLYMARKET_GRACE_PERIOD_MINUTES added
├── alembic/versions/
│   └── 0007_phase7_grace_period.py  # markets.uma_resolved_at column (if DB approach chosen)
└── tests/
    └── settlement/
        └── test_force_settle.py      # NEW: ADM-06 tests
    └── polymarket/
        └── test_detect_resolution.py # NEW: STL-01 tests (upgrade test_detect_resolution_returns_none)
```

### Pattern 1: Grace-Period DB Column (Recommended)

**What:** A nullable `DateTime(timezone=True)` column `uma_resolved_at` on the `markets` table
records the first time the Beat task observed `umaResolutionStatus='resolved'` for a mirrored
market. The Beat task checks `now() - uma_resolved_at >= GRACE_PERIOD_MINUTES` before calling
`SettlementService`.

**When to use:** Always — this is the canonical approach for this phase.

**Why DB over Redis:**
- Survives Celery worker/beat restart + Redis flush (at-least-once delivery safety)
- Testable without Redis mocking — set `uma_resolved_at` directly in test fixtures
- Aligns with the existing pattern of keeping audit-critical timestamps in Postgres
- The column is additive (no NOT NULL, no default required) — safe migration

```python
# Source: codebase pattern from HouseMarketResolveAdapter.mark_resolved (adapters.py)
# In the Beat task's _run_detect_resolutions():
market = await session.get(Market, internal_market_id)
if market.uma_resolved_at is None:
    market.uma_resolved_at = datetime.now(UTC)
    await session.flush()
    continue  # Start the clock; settle on next tick
elapsed = datetime.now(UTC) - market.uma_resolved_at
if elapsed < timedelta(minutes=settings.POLYMARKET_GRACE_PERIOD_MINUTES):
    continue  # Grace period not elapsed
winner_id = _map_winning_outcome(parsed.outcome_prices_raw, market.outcomes)
await SettlementService.resolve_market(
    session,
    market_id=market.id,
    winning_outcome_id=winner_id,
    market_resolver=HouseMarketResolveAdapter(),
    justification="Auto-resolved: Polymarket UMA oracle confirmed resolution",
    actor_user_id=None,
)
```

### Pattern 2: Winning Outcome Mapping by Label

**What:** Map `outcomePrices` index position (0=YES, 1=NO by Gamma convention) to internal
`Outcome` UUID by matching the label string. The `sync_top25` code in `adapter.py` already
preserves this label pairing (`idx=0 -> label[0]`). Phase 7 uses the same index-to-label
lookup in reverse.

**Why NOT use price comparison directly:** Prices like `"0"` and `"1"` are the resolved
values, but a market could settle at `"1.0"` or `"0.0"`. The `_derive_status` function
already handles this ambiguity (`has_winner = any(p in ("0", "1", "0.0", "1.0") ...)`).
Matching by label is safer and more readable.

```python
# Source: pattern from sync_top25 in adapter.py (line 152-177) — inverted
def _map_winning_outcome(
    outcome_prices: list[str],  # from GammaMarket.outcome_prices_raw
    outcomes: list[Outcome],    # from Market.outcomes (loaded with selectinload)
) -> UUID:
    """Return the UUID of the winning outcome by matching the winner-price index to label.

    Gamma convention: index 0 = first outcome (typically YES), index 1 = second (NO).
    A "winner" price is "0" or "1" (or "0.0"/"1.0") — the loser is 0, winner is 1.
    """
    winner_idx = next(
        (i for i, p in enumerate(outcome_prices) if p in ("1", "1.0")),
        None,
    )
    if winner_idx is None:
        raise ValueError(f"No clear winner in outcomePrices: {outcome_prices}")
    # Outcomes are ordered by insertion (sync_top25 inserts them in order).
    # Sort by label to match sync order (YES before NO alphabetically is not guaranteed).
    # Safer: build a label->id dict and use the Gamma outcomes_raw index to look up.
    label_to_id = {o.label.upper(): o.id for o in outcomes}
    # We need the label at winner_idx — must query GammaMarket.outcomes_raw too.
    # So caller passes (outcome_prices_raw, outcomes_raw, market.outcomes) together.
    return label_to_id[...]  # implementation detail: see Pattern 2 note below
```

**Important detail about label mapping:** `GammaMarket.outcomes_raw` (the Gamma label list,
e.g. `["Spurs", "Thunder"]` or `["Yes", "No"]`) maps index-to-label. The internal
`Outcome.label` was stored during `sync_top25` as `label[:50]` of the same list. Phase 7's
mapping function must receive BOTH `outcomes_raw` (from the fresh Gamma API response) and the
market's internal outcomes to do a safe cross-reference. The Beat task already fetches both
(it calls `fetch_market_by_id` which returns the Gamma response, and queries the DB for the
market with `selectinload(Market.outcomes)`).

**Resolved market fixture confirms this is safe:** `resolved_market.json` has
`"outcomePrices": ["0", "1"]` and `"outcomes": ["Spurs", "Thunder"]` — index 1 (Thunder)
has price "1" and is the winner. [VERIFIED: codebase inspection of `tests/fixtures/gamma/resolved_market.json`]

### Pattern 3: Beat Task Structure (follows Phase 6 pattern exactly)

**What:** The `detect_polymarket_resolutions` task follows the same
`asyncio.run(_run_detect_resolutions())` wrapper pattern as `poll_polymarket_top25`.
The async inner function accepts `session_override` and `redis_override` for testability.

```python
# Source: pattern from tasks.py poll_polymarket_top25 / _run_poll_sync
@celery_app.task(name="app.integrations.polymarket.tasks.detect_polymarket_resolutions")
def detect_polymarket_resolutions() -> None:
    """Celery task: detect and auto-settle resolved Polymarket markets."""
    asyncio.run(_run_detect_resolutions())

# Beat schedule addition in celery_app.py:
celery_app.conf.beat_schedule.update({
    "detect-polymarket-resolutions": {
        "task": "app.integrations.polymarket.tasks.detect_polymarket_resolutions",
        "schedule": 60.0,  # STL-01: 60s interval
    },
})
```

### Pattern 4: Force-Settle Endpoint (distinct from /resolve)

**What:** A new `POST /admin/markets/{market_id}/force-settle` endpoint in `settlement/router.py`
that captures the current Polymarket `umaResolutionStatus` at override time and writes a
`polymarket_admin_override` audit entry (ADM-06).

**Why distinct from `/resolve`:** The `/resolve` endpoint is for house markets (STL-02). Its
audit entry uses `event_type="settlement.resolved"`. ADM-06 requires a distinct
`event_type="polymarket_admin_override"` with extra payload fields (`uma_status_at_override`).
Sharing the endpoint would require conditional logic and produce misleading audit trails.

```python
# Source: pattern from settlement/router.py resolve_market endpoint
@settlement_admin_router.post("/{market_id}/force-settle", response_model=ForceSettleResponse)
async def force_settle_polymarket_market(
    market_id: UUID,
    body: ForceSettleRequest,
    admin: Annotated[User, Depends(current_active_admin)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolver: Annotated[MarketResolvePort, Depends(get_market_resolver)],
    gamma_client: Annotated[GammaClient, Depends(get_gamma_client)],
) -> ForceSettleResponse:
    """Force-settle a stuck Polymarket market (ADM-06). Two-step confirm is a client concern."""
    admin_id = admin.id
    await session.rollback()

    # Fetch current Polymarket status for audit snapshot
    market = await session.get(Market, market_id)
    if market is None or market.source != MarketSourceEnum.POLYMARKET.value:
        raise HTTPException(404, "Market not found or not a Polymarket market")

    current_gamma = await gamma_client.fetch_market_by_id(market.source_market_id)
    uma_status_at_override = (current_gamma or {}).get("umaResolutionStatus")

    plan = await SettlementService.resolve_market(
        session,
        market_id=market_id,
        winning_outcome_id=body.winning_outcome_id,
        market_resolver=resolver,
        justification=body.justification,
        actor_user_id=admin_id,
    )

    # Separate audit row for the override (distinct from the settlement.resolved row above)
    await AuditService.record(
        session,
        actor=f"user:{admin_id}",
        event_type="polymarket_admin_override",
        payload={
            "market_id": str(market_id),
            "winning_outcome_id": str(body.winning_outcome_id),
            "justification": body.justification,
            "uma_status_at_override_time": uma_status_at_override,
            "admin_id": str(admin_id),
        },
    )
    ...
```

**Note on audit ordering:** `SettlementService.resolve_market` already writes a
`settlement.resolved` audit entry inside its own `session.begin()`. The force-settle endpoint
must NOT open another `session.begin()` after calling `resolve_market` — instead, the
`polymarket_admin_override` audit row should be written INSIDE the same transaction or as a
subsequent committed call. The current `resolve_market` method commits internally
(`async with session.begin():`). The extra audit row must be posted in a separate
`session.begin()` block AFTER the settlement commits. This is the same pattern used in
Phase 3's recharge endpoint (documented in STATE.md: "action-THEN-audit"). [ASSUMED — the
exact transaction boundary around the additional audit row needs to be verified against
the `AuditService.record` session contract during implementation.]

### Anti-Patterns to Avoid

- **Re-implementing `_derive_status()`:** Never copy the closed/UMA truth table into the Beat
  task. Always parse the Gamma response through `GammaMarket.model_validate(raw)` and read
  `parsed.internal_status`. This keeps the single authoritative state machine.
- **Settling on `market.deadline < now()` without Gamma check:** The deadline alone is not
  sufficient. A market can have passed its `endDate` but still be in `proposed` or `disputed`
  UMA state. The Beat task MUST call `fetch_market_by_id` for every candidate before deciding.
- **Using Redis for grace-period state:** Redis key TTL does not survive a full Redis flush.
  Under Celery at-least-once delivery the grace period would silently restart, possibly
  causing a double-settle attempt (blocked by idempotency, but still wrong behavior).
- **Settling from within the Beat lock scope:** The poll lock in Phase 6 is
  `xpredict:poll:polymarket:lock`. Phase 7 must use a DIFFERENT lock key
  (`xpredict:detect:polymarket:lock`) or no lock at all (the grace-period DB column is its
  own idempotency guard). Reusing the poll lock would block sync during resolution detection.
- **Calling `session.begin()` from the force-settle handler after `resolve_market()`:** The
  service's internal `async with session.begin()` commits and ends the transaction. The
  handler must not try to reuse the same session context for an outer begin.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Closed vs resolved distinction | Custom if/elif on `closed` + `uma_status` | `_derive_status()` in `schemas.py` | State machine already spike-validated with VCR fixtures; any re-implementation risks the critical `proposed` → CLOSED guard |
| Settlement ACID transaction | Custom ledger logic | `SettlementService.resolve_market()` | Idempotency, FOR UPDATE lock ordering, audit row are all pre-built and tested |
| Market status flip | Direct `market.status = "RESOLVED"` assignment | `HouseMarketResolveAdapter.mark_resolved()` via `MarketResolvePort` | The port keeps the status flip in the same transaction as payouts |
| Winner outcome lookup | Price comparison logic | Label-index mapping derived from `outcomes_raw` + `Outcome.label` | The sync code already preserves this mapping; re-implementing creates drift |

**Key insight:** Phase 7's value is in the WIRING, not in new logic. Every piece of
infrastructure already exists. The task is assembling them correctly under the correct
invariants.

---

## Common Pitfalls

### Pitfall 1: Settling on `closed=true, umaResolutionStatus='proposed'`

**What goes wrong:** Beat task detects a market has `closed=true` and calls `resolve_market`.
Players receive payouts before UMA dispute window closes. Polymarket overturns the outcome.
Admin must reverse (expensive, trust-damaging).

**Why it happens:** Developer reads `closed=true` as "done" without checking `umaResolutionStatus`.

**How to avoid:** ALWAYS call `GammaMarket.model_validate(raw_response)` and check
`parsed.internal_status == MarketStatus.RESOLVED`. The `_derive_status()` truth table
encodes the guard. Never bypass it with raw field access.

**Warning signs:** Any code that reads `raw_response["closed"]` without also going through
`_derive_status`. SC#3 integration test (closed=true + proposed → no settlement) is the
canonical regression guard.

### Pitfall 2: Grace-Period Race Under Celery At-Least-Once Delivery

**What goes wrong:** Beat fires two overlapping tasks for the same market (restart scenario).
Both read `uma_resolved_at IS NULL`, both set it to `now()`, both check grace period, both call
`resolve_market` on the same market.

**How to avoid:** The `SettlementService.resolve_market` idempotency guard (`WHERE bets.status = PENDING`)
handles the double-settlement (second call is a no-op). However, the grace-period start could
be set twice to different timestamps. Use a DB-level `UPDATE markets SET uma_resolved_at = now() WHERE id = $1 AND uma_resolved_at IS NULL` (a conditional update) so only one writer wins.

**Warning signs:** Tests that verify idempotency under concurrent task execution.

### Pitfall 3: Missing `selectinload(Market.outcomes)` in Beat Task Query

**What goes wrong:** Beat task loads markets but outcomes are lazy-loaded (`lazy="raise"` in
`Market.outcomes` relationship). Accessing `market.outcomes` in `_map_winning_outcome` raises
`MissingGreenlet` or `InvalidRequestError`.

**How to avoid:** Use `selectinload(Market.outcomes)` in the candidate query, exactly as done
in `fetch_active_markets` in `adapter.py`.

**Warning signs:** `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called` in test logs.

### Pitfall 4: Circular Import — `tasks.py` Importing `settlement/service.py`

**What goes wrong:** `tasks.py` imports `SettlementService` which imports from `app.bets.models`
which may import from `app.celery_app` (or similar). Python raises `ImportError` at startup.

**How to avoid:** `SettlementService` does NOT import from `celery_app`. The import chain is
safe: `tasks.py` → `settlement/service.py` → `wallet/service.py` → `db/session.py`.
Confirm before writing the first import. If a circular import appears, use a lazy import
inside the async function body (pattern already used in `tasks.py` for `_get_session_maker`).

**Warning signs:** `ImportError` at `celery_app.py` module load time.

### Pitfall 5: `from __future__ import annotations` in Router File

**What goes wrong:** Phase 5's router already documents this: `from __future__ import annotations`
must be ABSENT from FastAPI router files on Python 3.13. Adding it to the new force-settle
handler causes `Annotated[Depends(...)]` to be evaluated as string annotations, breaking
FastAPI's dependency injection.

**How to avoid:** Do not add `from __future__ import annotations` to `settlement/router.py` (it
is already absent per the existing file header comment).

### Pitfall 6: Gamma API Rate Impact of Per-Market Fetches

**What goes wrong:** N mirrored markets × 1 fetch/60s = N req/min. Top-25 sync already uses
1 batch call / 30s. If Phase 7 adds 25 individual fetches every 60s, sustained rate = 25+2
req/min — well under the 300 req/10s limit, but this is a design concern if the market count
grows.

**How to avoid:** Rate math for v1 (max 25 mirrored markets): 25 req / 60s = 0.4 req/s.
Gamma limit is 300 req/10s = 30 req/s. Safety margin is 75×. [VERIFIED: docstring in
`client.py` confirms 300 req/10s limit]. For v1 this is not a problem; document the
assumption so it can be revisited if catalog grows beyond 25.

---

## Code Examples

### Candidate Market Query for Beat Task

```python
# Source: pattern from tasks.py _run_snapshot_odds + adapter.py fetch_active_markets
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.markets.enums import MarketSourceEnum, MarketStatus
from app.markets.models import Market
from datetime import UTC, datetime

async def _query_resolution_candidates(session: AsyncSession) -> list[Market]:
    """Return POLYMARKET markets that are OPEN or CLOSED with a passed deadline."""
    now = datetime.now(UTC)
    stmt = (
        select(Market)
        .where(Market.source == MarketSourceEnum.POLYMARKET.value)
        .where(Market.status.in_([MarketStatus.OPEN.value, MarketStatus.CLOSED.value]))
        .where(Market.deadline < now)
        .options(selectinload(Market.outcomes))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

### State Machine Delegation (DO THIS)

```python
# Source: schemas.py _derive_status + GammaMarket model_validator
from app.integrations.polymarket.schemas import GammaMarket
from app.markets.enums import MarketStatus

raw = await gamma_client.fetch_market_by_id(market.source_market_id)
if raw is None:
    log.warning("gamma.market_not_found", source_market_id=market.source_market_id)
    continue

try:
    parsed = GammaMarket.model_validate(raw)
except ValidationError:
    log.warning("gamma.parse_failed", source_market_id=market.source_market_id)
    continue

if parsed.internal_status != MarketStatus.RESOLVED:
    continue  # Not yet resolved — closed=proposed guard already handled by _derive_status
```

### Winning Outcome Mapping (complete implementation)

```python
# Source: adapter.py sync_top25 outcome loop (lines 151-177) — inverted
def _map_winning_outcome_id(
    outcome_prices_raw: list[str],  # from GammaMarket.outcome_prices_raw
    outcomes_raw: list[str],        # from GammaMarket.outcomes_raw (label list)
    db_outcomes: list[Outcome],     # from Market.outcomes (selectinloaded)
) -> UUID:
    """Map winner index from outcomePrices to internal Outcome UUID via label matching.

    Raises ValueError if no clear winner (should not happen when internal_status=RESOLVED).
    """
    winner_idx = next(
        (i for i, p in enumerate(outcome_prices_raw) if p in ("1", "1.0")),
        None,
    )
    if winner_idx is None:
        raise ValueError(
            f"Cannot determine winner from outcomePrices={outcome_prices_raw}"
        )
    if winner_idx >= len(outcomes_raw):
        raise ValueError(
            f"winner_idx={winner_idx} out of range for outcomes_raw={outcomes_raw}"
        )
    winner_label = outcomes_raw[winner_idx]
    # Match by label (stored as label[:50] during sync_top25)
    label_to_id = {o.label: o.id for o in db_outcomes}
    outcome_id = label_to_id.get(winner_label[:50])
    if outcome_id is None:
        raise ValueError(
            f"Label '{winner_label[:50]}' not found in DB outcomes: {list(label_to_id)}"
        )
    return outcome_id
```

### Beat Schedule Addition

```python
# Source: celery_app.py beat_schedule pattern (lines 48-59)
# Add to the existing celery_app.conf.beat_schedule.update({...}) call:
"detect-polymarket-resolutions": {
    "task": "app.integrations.polymarket.tasks.detect_polymarket_resolutions",
    "schedule": 60.0,  # STL-01: every 60 seconds
},
```

### SC#3 Correctness Test Pattern (closed=true + proposed → no settlement)

```python
# Source: test_schemas.py pattern + resolved_market.json fixture
# Uses the existing closed_not_resolved fixture
def test_detect_resolution_does_not_settle_on_closed_proposed(gamma_closed_not_resolved):
    """SC#3: closed=true + umaResolutionStatus='proposed' MUST NOT trigger settlement."""
    parsed = GammaMarket.model_validate(gamma_closed_not_resolved)
    assert parsed.internal_status != MarketStatus.RESOLVED
    # In the Beat task: if parsed.internal_status != RESOLVED: continue
    # This test verifies the guard is in place before any SettlementService call.
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 6 stub: `detect_resolution()` returns `None` | Phase 7: full implementation via `fetch_market_by_id` + `_derive_status` + grace period | Phase 7 (now) | Enables STL-01 |
| Admin manual-only Polymarket resolution (non-existent) | New `/force-settle` endpoint with audit snapshot | Phase 7 (now) | Enables ADM-06 |

**Deprecated/outdated:**
- `test_detect_resolution_returns_none` in `test_adapter.py`: This test documents the Phase 6
  stub. Phase 7 upgrades it to verify the real implementation. The test must be REPLACED, not
  just supplemented — the stub behavior is no longer correct.

---

## Runtime State Inventory

> Phase 7 is an additive phase with no renames or migrations affecting existing data.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `uma_resolved_at` column added to `markets` table (nullable) | Schema migration 0007; all existing rows get NULL (safe default — no grace period in progress) |
| Live service config | Beat schedule: `detect-polymarket-resolutions` added | celery_app.py update; RedBeat picks up new entry on next beat restart |
| OS-registered state | None | None |
| Secrets/env vars | `POLYMARKET_GRACE_PERIOD_MINUTES` new env var (default 30) | Add to `Settings` in `config.py` + `.env.example` |
| Build artifacts | None | None |

**Nothing found in category:** OS-registered state — verified by inspection (no cron/systemd/pm2 config references this phase). Build artifacts — no compiled outputs. Secrets — no existing secret key renamed.

---

## Open Questions

1. **Does `SettlementService.resolve_market` need a `source` parameter for attribution?**
   - What we know: The current audit payload includes `"resolver": str(actor_user_id) or "system"`.
     For STL-01, `actor_user_id=None` → resolver is `"system"`. The resolution display (STL-06 / SC#4)
     must attribute `Polymarket UMA` to auto-resolved markets.
   - What's unclear: Is the `justification` field sufficient for attribution ("Auto-resolved:
     Polymarket UMA oracle"), or does Phase 9's display layer need a structured `source` field?
   - Recommendation: Store source in the justification text for Phase 7; Phase 9 can parse it
     or the planner can add a `source` field to the audit payload. Keeping the service
     signature unchanged is the stated architectural constraint.

2. **Should the Beat task use a Redis lock (like Phase 6) or rely on the DB grace-period column?**
   - What we know: Phase 6 uses `SETNX` with TTL=25s to prevent overlapping 30s polls.
     Phase 7 has a 60s schedule with per-market DB state, so an overlapping run would
     hit the `uma_resolved_at IS NOT NULL` guard on the second execution.
   - What's unclear: Under heavy load, two Beat instances could both find a market with
     `uma_resolved_at IS NULL` before either has committed the update.
   - Recommendation: Add a lightweight Redis lock (key `xpredict:detect:polymarket:lock`,
     TTL=55s) for safety. The DB column remains the canonical grace-period tracker; the lock
     just prevents expensive duplicate Gamma API calls under a crash-restart scenario.

3. **Does the frontend force-settle UI need a new page or can it extend the existing admin market detail?**
   - What we know: Phase 7 is backend-only in REQUIREMENTS.md scope. ADM-06 says "via two-step
     confirm flow" but the two-step confirm is a client UX concern per the Phase 5 router pattern.
   - What's unclear: Is a frontend component required for Phase 7 or deferred to Phase 8/9?
   - Recommendation: Phase 7 delivers the API endpoint only; the frontend can stub the button.
     The planner should confirm with Pol.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All backend | ✓ | 3.12.10 | — |
| uv | Dependency management | ✓ | 0.11.16 | — |
| Docker | testcontainers Postgres | ✓ | 29.4.3 | — |
| Redis CLI | Beat task testing | ✗ (CLI only) | — | fakeredis (already in test deps) |
| Gamma API (live) | Beat task integration | ✓ (public API) | — | VCR fixtures for unit/integration tests |

**Missing dependencies with no fallback:** None — all blocked items have test doubles.
**Missing dependencies with fallback:** Redis CLI not installed on host, but fakeredis is
used for all tests (pattern established in Phase 6).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.25 |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && uv run pytest tests/polymarket/test_detect_resolution.py tests/settlement/test_force_settle.py -x -v` |
| Full suite command | `cd backend && uv run pytest -x -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STL-01 (SC#1) | Beat task queries expired POLYMARKET markets | unit | `pytest tests/polymarket/test_detect_resolution.py::test_candidate_query_returns_expired_markets` | ❌ Wave 0 |
| STL-01 (SC#2) | `resolve_market()` called when grace period elapses | unit | `pytest tests/polymarket/test_detect_resolution.py::test_grace_period_triggers_resolution` | ❌ Wave 0 |
| STL-01 (SC#3) | `closed=true + proposed` → no settlement | unit | `pytest tests/polymarket/test_detect_resolution.py::test_closed_proposed_not_settled` | ❌ Wave 0 |
| STL-01 (SC#3) | `closed=true + proposed` integration with DB | integration | `pytest tests/polymarket/test_detect_resolution.py::test_integration_proposed_not_settled` | ❌ Wave 0 |
| STL-01 (SC#6) | Reversal path: compensating entries restore balances | integration | `pytest tests/polymarket/test_detect_resolution.py::test_reversal_after_auto_settlement` | ❌ Wave 0 (reuses test_resolve_market.py pattern) |
| ADM-06 (SC#5) | Force-settle writes `polymarket_admin_override` audit entry | unit | `pytest tests/settlement/test_force_settle.py::test_force_settle_audit_entry` | ❌ Wave 0 |
| ADM-06 (SC#5) | Force-settle captures `umaResolutionStatus` at override time | unit | `pytest tests/settlement/test_force_settle.py::test_force_settle_captures_uma_status` | ❌ Wave 0 |
| STL-01 (stub retire) | `detect_resolution` no longer returns None | unit | `pytest tests/polymarket/test_adapter.py::TestProtocolConformance::test_detect_resolution_returns_none` | ✅ REPLACE |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/polymarket/test_detect_resolution.py tests/settlement/test_force_settle.py -x`
- **Per wave merge:** `uv run pytest -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/polymarket/test_detect_resolution.py` — covers STL-01 SC#1–3, SC#6
- [ ] `tests/settlement/test_force_settle.py` — covers ADM-06 SC#5
- [ ] `alembic/versions/0007_phase7_grace_period.py` — adds `uma_resolved_at` to `markets`
- [ ] `config.py` setting: `POLYMARKET_GRACE_PERIOD_MINUTES: int = 30` — new env var

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Admin-Bearer JWT already enforced on `/admin/*` (Phase 2) |
| V3 Session Management | no | Beat task is system-actor; no session involved |
| V4 Access Control | yes | Force-settle endpoint MUST enforce `current_active_admin` (same pattern as existing admin endpoints) |
| V5 Input Validation | yes | `ForceSettleRequest` with `extra="forbid"`, mandatory `justification` min_length=1 |
| V6 Cryptography | no | No new crypto; audit log immutability is already enforced |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Admin force-settle without two-step confirm | Tampering | Client-side two-step confirm UX (enforce in frontend); API validates required fields |
| Polymarket data feed manipulation at resolution time | Tampering | `umaResolutionStatus` is read-only from Gamma (public, authenticated-by-UMA); admin override exists for disputes |
| Double-settle under concurrent Beat tasks | Tampering | SettlementService idempotency (`WHERE bets.status = PENDING`) + grace-period conditional UPDATE |
| Fake `source_market_id` in force-settle payload | Spoofing | Force-settle validates `market.source == POLYMARKET` before fetching from Gamma |

---

## Sources

### Primary (HIGH confidence)

- Codebase inspection: `backend/app/integrations/polymarket/schemas.py` — `_derive_status()` truth table and `GammaMarket` model [VERIFIED: codebase]
- Codebase inspection: `backend/app/settlement/service.py` — `SettlementService.resolve_market()` signature and behavior [VERIFIED: codebase]
- Codebase inspection: `backend/app/integrations/polymarket/tasks.py` — `_run_poll_sync` pattern for Beat tasks [VERIFIED: codebase]
- Codebase inspection: `backend/app/integrations/polymarket/adapter.py` — `detect_resolution()` stub + `sync_top25` label mapping [VERIFIED: codebase]
- Codebase inspection: `backend/app/celery_app.py` — beat_schedule update pattern + Redis URL [VERIFIED: codebase]
- Codebase inspection: `backend/tests/fixtures/gamma/resolved_market.json` — `outcomePrices: ["0", "1"]` winner index convention [VERIFIED: codebase]
- Codebase inspection: `backend/tests/fixtures/gamma/closed_not_resolved.json` — SC#3 test fixture [VERIFIED: codebase]
- ROADMAP.md Phase 7 section — success criteria SC#1–6 [VERIFIED: codebase]
- `.planning/REQUIREMENTS.md` — STL-01, ADM-06 requirements [VERIFIED: codebase]

### Secondary (MEDIUM confidence)

- `client.py` docstring: "Rate limit is 300 req/10s (verified: docs.polymarket.com)" [CITED: docstring in GammaClient]
- STATE.md accumulated context — `SettlementService` reuse decision + Phase 6 spike findings [CITED: .planning/STATE.md]

### Tertiary (LOW confidence)

- None.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The additional `polymarket_admin_override` audit row should be written in a SEPARATE `session.begin()` after `resolve_market()` commits | Architecture Patterns (Pattern 4) | Wrong transaction boundary could cause audit row to be lost or the settlement to fail; must verify against `AuditService.record` session contract in implementation |
| A2 | `Market.outcomes` maintains insertion order matching `GammaMarket.outcomes_raw` index convention | Code Examples (winner mapping) | Winner could be mapped to wrong outcome; mitigated by label lookup rather than index-only matching |

**If this table contains entries:** A1 and A2 signal implementation details that need
verification during Wave 0. A1 is the higher-risk assumption — confirm the session contract
before writing the force-settle handler.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all components are existing, in-codebase, and verified
- Architecture: HIGH — derived directly from the existing Phase 5 and Phase 6 patterns
- Pitfalls: HIGH — derived from existing code docstrings, PITFALLS.md, and spike findings

**Research date:** 2026-05-28
**Valid until:** 2026-06-28 (Gamma API schema changes are the primary staleness risk; 30-day window)

---

## RESEARCH COMPLETE

**Phase:** 7 - Polymarket Auto-Resolution & Admin Override
**Confidence:** HIGH

### Key Findings

- `SettlementService.resolve_market()` requires zero changes — Phase 7 is pure wiring
- `_derive_status()` in `schemas.py` is the canonical state machine; Phase 7 MUST delegate to it, never re-implement
- Grace period state belongs in a DB column (`uma_resolved_at` on `markets`) — Redis is volatile and crash-unsafe
- Winner outcome mapping is safe via label-index lookup: `outcomes_raw[winner_idx]` → `Outcome.label` → `Outcome.id`
- Force-settle must be a DISTINCT endpoint (`/force-settle` not `/resolve`) to produce semantically clean `polymarket_admin_override` audit entries
- No new external packages required; the entire phase is additive with one Alembic migration (nullable `uma_resolved_at` column)

### File Created

`.planning/phases/07-polymarket-auto-resolution-admin-override/07-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | All components in codebase, verified by inspection |
| Architecture | HIGH | Directly derived from Phase 5+6 patterns |
| Pitfalls | HIGH | Grounded in codebase docstrings + existing spike findings |
| Grace Period Strategy | HIGH | DB column approach verified safe vs Redis; testability advantage confirmed |
| Outcome Mapping | HIGH | `resolved_market.json` fixture proves index-to-label convention |

### Open Questions

1. Does the `polymarket_admin_override` audit row share the `resolve_market` transaction or follow it? (A1 — verify during implementation)
2. Frontend scope: is a UI component required in Phase 7 or deferred to Phase 8/9? (confirm with Pol)
3. Should the Beat task use a Redis lock in addition to the DB grace-period column for crash-safety? (Recommended: yes, separate key `xpredict:detect:polymarket:lock`)

### Ready for Planning

Research complete. Planner can now create PLAN.md files.
