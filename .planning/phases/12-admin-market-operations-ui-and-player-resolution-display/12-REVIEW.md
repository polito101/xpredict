---
phase: 12-admin-market-operations-ui-and-player-resolution-display
reviewed: 2026-06-03T00:00:00Z
depth: standard
files_reviewed: 47
files_reviewed_list:
  - backend/alembic/versions/0010_phase12_resolution_and_stake_limits.py
  - backend/app/bets/adapters.py
  - backend/app/bets/exceptions.py
  - backend/app/bets/market_port.py
  - backend/app/bets/router.py
  - backend/app/bets/service.py
  - backend/app/markets/models.py
  - backend/app/markets/router.py
  - backend/app/markets/schemas.py
  - backend/app/settlement/adapters.py
  - backend/app/settlement/market_port.py
  - backend/app/settlement/service.py
  - backend/tests/admin/test_kpi.py
  - backend/tests/bets/test_bet_router.py
  - backend/tests/bets/test_place_bet.py
  - backend/tests/markets/test_public_router.py
  - backend/tests/settlement/test_force_settle.py
  - backend/tests/settlement/test_market_resolve_port.py
  - backend/tests/settlement/test_resolve_market.py
  - backend/tests/settlement/test_settlement_router.py
  - frontend/src/app/admin/markets/[id]/page.tsx
  - frontend/src/app/admin/markets/new/page.tsx
  - frontend/src/app/admin/markets/page.tsx
  - frontend/src/app/markets/[slug]/page.tsx
  - frontend/src/components/__tests__/market-resolution-panel.test.tsx
  - frontend/src/components/admin/__tests__/market-form.test.tsx
  - frontend/src/components/admin/__tests__/market-status-badge.test.tsx
  - frontend/src/components/admin/__tests__/settlement-dialogs.test.tsx
  - frontend/src/components/admin/admin-nav.tsx
  - frontend/src/components/admin/close-market-dialog.tsx
  - frontend/src/components/admin/force-settle-dialog.tsx
  - frontend/src/components/admin/kpi-card.tsx
  - frontend/src/components/admin/market-detail-actions.tsx
  - frontend/src/components/admin/market-form.tsx
  - frontend/src/components/admin/market-status-badge.tsx
  - frontend/src/components/admin/markets-data-table.tsx
  - frontend/src/components/admin/resolve-market-dialog.tsx
  - frontend/src/components/admin/reverse-settlement-dialog.tsx
  - frontend/src/components/admin/settlement-dialog-utils.ts
  - frontend/src/components/market-resolution-panel.tsx
  - frontend/src/components/order-entry-form.test.tsx
  - frontend/src/components/order-entry-form.tsx
  - frontend/src/lib/__tests__/admin-markets-api.test.ts
  - frontend/src/lib/admin-markets-api.ts
  - frontend/src/lib/admin-markets-types.ts
  - frontend/src/lib/api.ts
  - frontend/src/lib/bet-schemas.ts
findings:
  critical: 1
  warning: 2
  info: 2
  total: 5
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-06-03
**Depth:** standard
**Files Reviewed:** 47
**Status:** issues_found

## Summary

Phase 12 is the v1.0 closure phase: the admin market-operations UI (create / edit / close /
resolve / reverse / force-settle) plus the player-facing resolution display, backed by five
additive nullable `markets` columns (migration 0010) for the STL-06 resolution projection and
the BET-06 per-market stake limits.

The settlement core and the security-sensitive surfaces are in good shape:

- **Settlement ACID & idempotency (STL-06):** `SettlementService.resolve_market` /
  `reverse_settlement` keep the winner-persistence, payouts, status flip, and audit row inside
  one `session.begin()`; lock ordering is canonical-UUID-sorted; idempotency keys are
  deterministic; the atomicity / reversal-nets-to-zero tests are thorough.
- **Money on the wire (SP-1):** every money/odds field serializes as a string
  (`DecimalStr`, `field_serializer`), the TS types are `string`, and the UI derives sign from
  the leading "-" rather than `parseFloat` for storage.
- **Admin authorization & the two-prefix landmine:** the settlement wrappers correctly target
  the BARE `/admin/markets/{id}/...` prefix while CRUD keeps `/api/v1`; `admin-markets-api.test.ts`
  locks it; every wrapper forwards the `admin_jwt` Bearer; the backend routes are all
  `current_active_admin`-gated.
- **XSS:** the operator-authored justification and the resolution criteria render as escaped
  React text — no `dangerouslySetInnerHTML` anywhere — and the panel test asserts a literal
  `<b>` is not injected.
- **Migration 0010:** purely additive, five nullable columns, clean reversible `downgrade()`,
  single head off `0009`, with the documented revision-id-length workaround.

The blocker below is an **integration gap created by this phase**: the BET-06 request and
response schemas (and the entire admin form / order-form mirror) were added, but the
persistence step in `MarketService` that would write the submitted limits onto the market row
was never wired. The feature is settable in the UI and validated, yet silently dropped — and
no test exercises the real create/update path with stake limits, so it slipped through green.

## Critical Issues

### CR-01: Per-market stake limits (BET-06) are never persisted — the feature is dead through the admin UI

**File:** `backend/app/markets/service.py:46-54` (create), `backend/app/markets/service.py:146-182` (update)
**(contract introduced by this phase:** `backend/app/markets/schemas.py:45-46, 64-65`; `backend/app/components/admin/market-form.tsx` sends the values)

This phase added `min_stake` / `max_stake` to `MarketCreate` and `MarketUpdate`
(`schemas.py:45-46`, `64-65`), exposed them on `MarketRead` (`schemas.py:117-118`), wired the
admin `market-form.tsx` to collect and send them, and made `BetService.place_bet` read them
off the market (`bets/service.py:98-101`). But the write side is missing:

- `MarketService.create_market` builds the `Market(...)` row from `question` / `slug` /
  `resolution_criteria` / `deadline` / `category` / `source` / `status` ONLY — it never reads
  `body.min_stake` / `body.max_stake`, so a market created with stake limits persists them as
  `NULL`.
- `MarketService.update_market` patches `resolution_criteria` / `deadline` / `category` /
  `odds_yes` ONLY — it never reads `body.min_stake` / `body.max_stake`, so editing the limits
  is a silent no-op.

A repo-wide search confirms NO code path anywhere writes `body.min_stake` / `body.max_stake`
into the `Market` model:

```
$ grep -rn "min_stake\|max_stake" backend/app --include=*.py | grep -v schemas.py
backend/app/bets/adapters.py:42:    min_stake=market.min_stake,   # reads the (always-NULL) column
backend/app/bets/adapters.py:43:    max_stake=market.max_stake,
backend/app/bets/service.py:98:    min_stake = market.min_stake if market.min_stake is not None else settings.BET_MIN_STAKE
backend/app/bets/service.py:99:    max_stake = market.max_stake if market.max_stake is not None else settings.BET_MAX_STAKE
```

Net effect: an operator can fill in Min/Max stake in the create/edit form, pass client zod,
POST the body, get a 201/200 — and the market always falls back to the GLOBAL
`BET_MIN_STAKE` / `BET_MAX_STAKE`. The edit form even pre-fills from `MarketRead`
(`market-detail-actions.tsx:67-68`), so the field reads back blank after every "save",
silently discarding the operator's input. BET-06 ("server-side check must be authoritative;
NULL columns fall back to global config") is non-functional for every HOUSE market created or
edited through the API.

Why it shipped green: the BET-06 backend tests
(`test_place_bet.py` / `test_bet_router.py`) drive an in-memory `StubMarketSource`/`MarketView`
that takes `min_stake`/`max_stake` directly (never through `MarketService`), and
`test_public_router.py::_create_market` never sends stake limits. No test round-trips the
limits through `create_market`/`update_market` → DB → `place_bet`.

**Fix:** persist the two fields in the service (the migration column, the model attribute, and
both schemas already exist). Create:

```python
# create_market — add to the Market(...) constructor (markets/service.py:46)
market = Market(
    question=body.question,
    slug=slug,
    resolution_criteria=body.resolution_criteria,
    deadline=body.deadline,
    category=body.category,
    source=MarketSourceEnum.HOUSE.value,
    status=MarketStatus.OPEN.value,
    min_stake=body.min_stake,   # BET-06: persist the per-market limits (NULL = global)
    max_stake=body.max_stake,
)
```

Update (mirror the `category` `model_fields_set` pattern so an explicit `null` clears the
limit and an omitted field leaves it untouched):

```python
# update_market — after the existing category block (markets/service.py:154)
if "min_stake" in body.model_fields_set:
    market.min_stake = body.min_stake
    changed_fields.append("min_stake")
if "max_stake" in body.model_fields_set:
    market.max_stake = body.max_stake
    changed_fields.append("max_stake")
```

Add an integration test that creates a market with `min_stake`/`max_stake` via
`POST /api/v1/admin/markets`, then asserts a sub-min stake is rejected through the real
`place_bet` path (and that `MarketRead` returns the persisted values, not `null`).

## Warnings

### WR-01: No server-side `min_stake <= max_stake` validation — an inverted range bricks all bets on a market

**File:** `backend/app/markets/schemas.py:38-46` (`MarketCreate`), `backend/app/markets/schemas.py:58-65` (`MarketUpdate`)
**Issue:** `min_stake` and `max_stake` are each validated independently (`Field(ge=0)`), but
there is no cross-field check that `min_stake <= max_stake`. The client form enforces it
(`market-form.tsx:117-127` refine → "Min stake cannot exceed max stake."), but the focus
contract is explicit that the client mirror is convenience-only and the server must be
authoritative. A direct API call (curl / script / compromised client) with
`{"min_stake": "100", "max_stake": "10"}` is accepted; once CR-01 is fixed and those values
persist, `place_bet`'s `min_stake <= stake <= max_stake` (`bets/service.py:100`) can NEVER be
satisfied — every bet on that market is rejected with `StakeOutOfRange`, an operator-induced
denial of service on the market with no server-side guard. (This is latent today only because
CR-01 means the values are dropped; it becomes live the moment CR-01 is fixed, so fix both
together.)
**Fix:** add a `model_validator(mode="after")` to both schemas:

```python
from pydantic import model_validator

@model_validator(mode="after")
def _check_stake_bounds(self) -> "MarketCreate":  # and MarketUpdate
    if (
        self.min_stake is not None
        and self.max_stake is not None
        and self.min_stake > self.max_stake
    ):
        raise ValueError("min_stake cannot exceed max_stake")
    return self
```

This surfaces as a 422 (matching the client copy) instead of silently creating an unbettable
market.

### WR-02: `min_stake` / `max_stake` accept `0`, an out-of-domain bound for a stake the ledger requires to be `> 0`

**File:** `backend/app/markets/schemas.py:45-46`, `backend/app/markets/schemas.py:64-65`
**Issue:** both stake limits use `Field(ge=0)`, so `min_stake=0` / `max_stake=0` are valid
inputs. A stake is required to be strictly positive (`bets/service.py:80` raises `ValueError`
on `stake <= 0`; `PlaceBetRequest.stake` is `Field(gt=0)`). A `max_stake=0` (once persisted
per CR-01) produces a market where `place_bet`'s `stake <= 0` floor and the
`stake <= max_stake (=0)` bound are mutually exclusive — no valid stake exists — yet it passes
schema validation. `min_stake=0` is a meaningless lower bound (it can never bind below the
positivity floor). The client form is stricter than the server here too
(`market-form.tsx:63` requires `Number(v) > 0`), re-confirming the server is the looser,
non-authoritative layer.
**Fix:** tighten the constraint to `Field(gt=0)` for both fields on `MarketCreate` and
`MarketUpdate` so a non-positive limit is a 422, consistent with the `stake > 0` invariant and
the client mirror.

## Info

### IN-01: Category filter fires a backend round-trip on every keystroke (no debounce)

**File:** `frontend/src/components/admin/markets-data-table.tsx:294-307` (input) → `:197-229` (effect)
**Issue:** the category `<Input>` calls `setCategory` + `resetToFirstPage` on every `onChange`,
which mutates `currentFilters` (`:197-206`) and re-runs the fetch effect (`:208-229`) — so
typing "weather" issues seven `fetchMarkets` calls in sequence. The in-flight `cancelled`
guard prevents a stale-response correctness bug, so this is a quality/efficiency wrinkle, not a
defect (and raw performance is out of v1 review scope). Worth noting because it is an admin
Server-Action round-trip per character, unlike the other two filters which are discrete
`<Select>`s.
**Fix:** debounce the category input (e.g. a ~300ms `useDebouncedValue`) before it feeds
`currentFilters`, matching the discrete-change cadence of the source/status selects.

### IN-02: `isSessionExpiredError` substring-matches "401"/"403" anywhere in the error message

**File:** `frontend/src/components/admin/settlement-dialog-utils.ts:13-16`
**Issue:** the helper branches the session-expired toast on `/\b(401|403)\b/` against the
thrown `Error("API error: <status>")` string. It is correct for the current wrapper (the only
3-digit token in the message is the status), but it is a string-sniff: any future error message
that happens to contain a word-boundaried "401"/"403" (e.g. an amount, an id fragment, or a
backend detail echoed into the message) would be misclassified as a session expiry. Low risk
given the fixed `"API error: <status>"` format, but brittle.
**Fix:** have the wrapper throw a typed error carrying a numeric `status` field (or prefix-anchor
the regex to the known `"API error: "` format) so the branch keys on structured data rather than
a free-text substring.

---

_Reviewed: 2026-06-03_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
