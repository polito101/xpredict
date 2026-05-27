---
spike: 002
name: polymarket-gamma-parser
type: standard
validates: "Given real Gamma API responses, when parsed with Pydantic v2, then stringified JSON fields decode correctly, mixed numerics normalize to Decimal, and the closed/umaResolutionStatus state machine produces correct internal status"
verdict: VALIDATED
related: [001-async-wallet-concurrency]
tags: [polymarket, gamma-api, pydantic, parsing, state-machine, phase-6]
---

# Spike 002: polymarket-gamma-parser

## What This Validates
Given real Polymarket Gamma API `/markets` responses, when parsed with a Pydantic v2 model,
then stringified JSON fields (`outcomes`, `outcomePrices`, `clobTokenIds`) decode correctly,
mixed numeric types normalize to `Decimal`, and the `closed`/`umaResolutionStatus` state machine
produces correct internal market status — including the critical distinction between `closed=true`
and truly `resolved`.

## Research

| Approach | Tool/Library | Pros | Cons | Verdict |
|----------|-------------|------|------|---------|
| Pydantic v2 `model_validate()` | pydantic 2.10+ | Type coercion, validators, `extra='allow'` | Need custom validators for stringified JSON | **Chosen** |
| Manual dict parsing | stdlib json | Full control | No validation, no type safety | Rejected |
| dataclasses + cattrs | cattrs | Lightweight | Less flexible coercion than Pydantic | Rejected |

Sources: Polymarket Gamma API (live data), docs.polymarket.com, STACK.md, PITFALLS.md #2/#9.

**Critical finding during research:** The WebFetch tool pre-parsed the Gamma API response, making stringified JSON fields appear as native arrays. Only live httpx requests revealed the TRUE format — STACK.md was correct all along.

## How to Run
```bash
cd backend
uv run python ../.planning/spikes/002-polymarket-gamma-parser/spike_gamma.py
```

Requires internet access for live Gamma API tests (tests 9-11). Fixture tests (1-8) work offline.

## What to Expect
11 tests: 8 fixture-based + 3 live API. All should report PASS.

## Investigation Trail

### Iteration 1: Initial research
Fetched live Gamma API data via WebFetch. Initial observation: `outcomes` and `outcomePrices` appeared as native JSON arrays. Conclusion: STACK.md was wrong about stringified JSON.

### Iteration 2: Live API test failure
Running httpx against the real API revealed the truth: those fields ARE stringified JSON strings. WebFetch's HTML-to-markdown conversion had pre-parsed them. Added `field_validator` with `json.loads()` fallback that handles both formats (string and pre-parsed list).

### Iteration 3: State machine validation
Built 4 fixture-based state machine tests covering all critical paths:
- OPEN: active, no UMA process
- DISPUTED: active, under UMA dispute (with history)
- RESOLVED: closed + resolved + clear winner (outcomePrices = ["0", "1"])
- CLOSED (NOT RESOLVED): closed + proposed (THE PITFALL #2 CASE)

### Key discovery: Dual field encoding
The API returns BOTH string and float versions of numeric fields:
- `volume` (string: "57367327.83") + `volumeNum` (float: 57367327.83)
- `liquidity` (string: "595820.05") + `liquidityNum` (float: 595820.05)

Use the STRING versions and parse to Decimal for precision. The `*Num` float variants lose precision.

### Key discovery: umaResolutionStatuses (plural) is a history
The `umaResolutionStatuses` (plural, with 'es') field contains the full UMA lifecycle history as an array: `["proposed", "disputed", "proposed", "disputed"]`. The singular `umaResolutionStatus` contains only the current state. Both can be absent (not null) when no UMA process has started.

## Results

**Verdict: VALIDATED**

All 11 tests passed (8 fixture + 3 live API):

| Test | Category | Result |
|------|----------|--------|
| 1. Active market -> OPEN | Fixture | PASS |
| 2. Disputed market -> DISPUTED | Fixture | PASS |
| 3. Resolved market -> RESOLVED | Fixture | PASS |
| 4. CRITICAL: closed+proposed -> CLOSED | Fixture | PASS |
| 5. Missing optional fields | Fixture | PASS |
| 6. winning_outcome() guard | Fixture | PASS |
| 7. Decimal precision | Fixture | PASS |
| 8. Extra fields (schema drift) | Fixture | PASS |
| 9. Live top 10 active markets | Live API | PASS (10/10) |
| 10. Live 5 closed markets | Live API | PASS (5/5, 5 RESOLVED) |
| 11. Live state machine consistency | Live API | PASS (25 markets, 0 violations) |

### Non-negotiable patterns for Phase 6:

1. **Stringified JSON validator is mandatory** — `outcomes`, `outcomePrices`, `clobTokenIds`, `umaResolutionStatuses` arrive as JSON strings in the real API
2. **Use string numeric fields, not float variants** — `volume` (string) -> Decimal, NOT `volumeNum` (float)
3. **`umaResolutionStatus` is optional** — absent (not null) when no UMA process; check for `None`
4. **NEVER settle on `closed=true` alone** — only `closed=true + umaResolutionStatus="resolved" + clear winner` = safe to settle
5. **`extra='allow'`** — the API has 50+ fields; new ones appear without notice
6. **Validator must handle both formats** — stringified JSON from the API AND pre-parsed lists from fixtures/tests
7. **`umaResolutionStatuses` (plural)** gives the full UMA history; useful for audit trail in Phase 7

### Gamma API schema quirks documented:

| Field | Type in API | Actual content | Notes |
|-------|-------------|----------------|-------|
| `outcomes` | string | Stringified JSON array: `'["Yes","No"]'` | Parse with `json.loads()` |
| `outcomePrices` | string | Stringified array of decimal strings: `'["0.225","0.775"]'` | Parse, then each element to Decimal |
| `clobTokenIds` | string | Stringified array of very long number strings | Parse with `json.loads()` |
| `volume` | string | Decimal string: `"57367327.83"` | -> Decimal |
| `volumeNum` | float | Same value as float: `57367327.83` | DO NOT USE (precision loss) |
| `volume24hr` | float | `4091121.72` | Use for sorting only, not for display |
| `liquidity` | string | Decimal string: `"595820.05"` | -> Decimal |
| `endDate` | string/null | ISO 8601: `"2026-05-31T00:00:00Z"` | Can be absent |
| `umaResolutionStatus` | string/absent | `"proposed"`, `"disputed"`, `"resolved"` | Absent when no UMA process |
| `umaResolutionStatuses` | string | Stringified history array: `'["proposed","disputed"]'` | Full UMA lifecycle |
| `automaticallyResolved` | boolean | Only on resolved markets | Absent on active markets |

### VCR fixtures captured:
- `fixtures/active_market.json` — normal active market, no UMA
- `fixtures/disputed_market.json` — active market under UMA dispute
- `fixtures/resolved_market.json` — fully resolved with clear winner
- `fixtures/closed_not_resolved.json` — CRITICAL: closed but only proposed (synthetic)
