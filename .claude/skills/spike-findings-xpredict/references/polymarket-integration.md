# Polymarket Integration

## Requirements

- Polymarket `closed` vs `resolved` distinction must be enforced at the parser level
- All money amounts must be `Decimal` / `NUMERIC(18,4)` — never float
- Gamma API fields `outcomes`/`outcomePrices`/`clobTokenIds` are stringified JSON — `json.loads()` required
- Use string numeric fields (`volume`), never float variants (`volumeNum`) for Decimal precision
- `umaResolutionStatus` is absent (not null) when no UMA process — always check for `None`

## How to Build It

### 1. Pydantic v2 model with stringified JSON validators

```python
from pydantic import BaseModel, Field, field_validator, model_validator

class GammaMarket(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    question: str

    outcomes_raw: list[str] = Field(alias="outcomes", default_factory=list)
    outcome_prices_raw: list[str] = Field(alias="outcomePrices", default_factory=list)
    clob_token_ids: list[str] = Field(alias="clobTokenIds", default_factory=list)

    volume_str: str = Field(alias="volume", default="0")
    liquidity_str: str = Field(alias="liquidity", default="0")

    closed: bool = False
    uma_resolution_status: str | None = Field(alias="umaResolutionStatus", default=None)
    uma_resolution_statuses: list[str] = Field(alias="umaResolutionStatuses", default_factory=list)

    @field_validator(
        "outcomes_raw", "outcome_prices_raw", "clob_token_ids", "uma_resolution_statuses",
        mode="before",
    )
    @classmethod
    def parse_stringified_json_list(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return []
        return []
```

The validator handles both stringified JSON (from real API) and pre-parsed lists (from fixtures/tests).

### 2. State machine for market status

```python
class InternalMarketStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PROPOSED = "PROPOSED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"

def _derive_status(closed, uma_status, outcome_prices):
    if not closed and uma_status is None:
        return InternalMarketStatus.OPEN
    if not closed and uma_status == "proposed":
        return InternalMarketStatus.PROPOSED
    if not closed and uma_status == "disputed":
        return InternalMarketStatus.DISPUTED
    if closed and uma_status == "resolved":
        has_winner = any(p in ("0", "1", "0.0", "1.0") for p in outcome_prices)
        if has_winner:
            return InternalMarketStatus.RESOLVED
        return InternalMarketStatus.CLOSED
    if closed and uma_status in ("proposed", "disputed", None):
        return InternalMarketStatus.CLOSED
    if not closed and uma_status == "resolved":
        return InternalMarketStatus.RESOLVED
    return InternalMarketStatus.OPEN
```

### 3. Settlement safety check

```python
def is_safe_to_settle(self) -> bool:
    return self.internal_status == InternalMarketStatus.RESOLVED

def winning_outcome(self) -> str | None:
    if self.internal_status != InternalMarketStatus.RESOLVED:
        return None
    for o in self.parsed_outcomes:
        if o.price == Decimal("1"):
            return o.label
    return None
```

### 4. Decimal handling

```python
def _safe_decimal(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")
```

Always use `str(value)` before `Decimal()` to avoid float precision issues.

### 5. API request pattern

```python
import httpx

resp = httpx.get(
    "https://gamma-api.polymarket.com/markets",
    params={"active": "true", "closed": "false", "limit": 10},
    timeout=15,
)
raw_markets = resp.json()
for raw in raw_markets:
    market = GammaMarket.model_validate(raw)
```

## What to Avoid

1. **NEVER settle on `closed=true` alone** — only `closed=true + umaResolutionStatus="resolved" + clear winner` = safe to settle. This is the single most dangerous pitfall.
2. **NEVER use `volumeNum` / `liquidityNum` float fields** — they lose precision. Always parse string fields (`volume`, `liquidity`) to Decimal.
3. **NEVER assume `umaResolutionStatus` exists** — it's absent (not null) when no UMA process has started. Always check for `None`.
4. **NEVER trust WebFetch/tool-previewed API data for schema validation** — pre-parsing by tools obscured the stringified JSON format. Only live `httpx` requests show the true API format.
5. **NEVER hardcode the field list** — use `extra='allow'` because the API has 50+ fields and new ones appear without notice.
6. **DON'T confuse `umaResolutionStatus` (singular) with `umaResolutionStatuses` (plural)** — singular = current state, plural = full UMA lifecycle history array.

## Constraints

- Gamma API base: `https://gamma-api.polymarket.com`
- API returns both string and float versions of numeric fields — always use string versions
- `umaResolutionStatuses` (plural with 'es') is the history; singular is current state
- `automaticallyResolved` field is only present on resolved markets (absent on active)
- `endDate` can be null/absent
- No auth required for public market data
- Pydantic v2.10+ required for the validator pattern used

### Gamma API schema reference

| Field | Type in API | Actual content | Notes |
|-------|-------------|----------------|-------|
| `outcomes` | string | Stringified JSON: `'["Yes","No"]'` | `json.loads()` |
| `outcomePrices` | string | Stringified decimals: `'["0.225","0.775"]'` | Parse, then Decimal |
| `clobTokenIds` | string | Stringified long numbers | `json.loads()` |
| `volume` | string | `"57367327.83"` | -> Decimal |
| `volumeNum` | float | Same as float | DO NOT USE |
| `liquidity` | string | `"595820.05"` | -> Decimal |
| `endDate` | string/null | ISO 8601 | Can be absent |
| `umaResolutionStatus` | string/absent | proposed/disputed/resolved | Absent = no UMA |
| `umaResolutionStatuses` | string | Stringified history array | Full lifecycle |

### VCR fixtures available

- `active_market.json` — normal active market, no UMA
- `disputed_market.json` — active market under UMA dispute
- `resolved_market.json` — fully resolved with clear winner
- `closed_not_resolved.json` — CRITICAL: closed but only proposed (synthetic)

## Origin

Synthesized from spikes: 002
Source files available in: sources/002-polymarket-gamma-parser/
