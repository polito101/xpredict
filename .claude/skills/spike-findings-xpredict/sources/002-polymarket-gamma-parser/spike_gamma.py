"""
Spike 002: polymarket-gamma-parser

Tests the Pydantic v2 parser against fixtures AND live Gamma API data.

Validates:
  1. String-encoded decimals parse to Decimal correctly
  2. Mixed numeric types (string volume vs float volume24hr) handled
  3. Optional fields (endDate, umaResolutionStatus) don't crash
  4. State machine: closed=true + proposed -> CLOSED (NOT RESOLVED)
  5. State machine: closed=true + resolved + clear winner -> RESOLVED
  6. State machine: disputed market -> DISPUTED
  7. Live API parsing: top 10 active + 5 closed markets parse without error
  8. Extra fields don't crash (extra='allow')
  9. Winning outcome extraction only on RESOLVED markets

Usage:
    cd backend
    uv run python ../.planning/spikes/002-polymarket-gamma-parser/spike_gamma.py
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import httpx

# Add spike dir to path so we can import the parser
spike_dir = Path(__file__).parent
sys.path.insert(0, str(spike_dir))

from gamma_parser import GammaMarket, InternalMarketStatus  # noqa: E402

GAMMA_BASE = "https://gamma-api.polymarket.com"
FIXTURES_DIR = spike_dir / "fixtures"


@dataclass
class TestResult:
    name: str
    passed: bool = False
    details: str = ""


def run_tests() -> list[TestResult]:
    results: list[TestResult] = []

    # --- Fixture Tests ---

    results.append(test_active_market())
    results.append(test_disputed_market())
    results.append(test_resolved_market())
    results.append(test_closed_not_resolved())
    results.append(test_missing_optional_fields())
    results.append(test_winning_outcome_only_on_resolved())
    results.append(test_decimal_precision())
    results.append(test_extra_fields_allowed())

    # --- Live API Tests ---

    results.append(test_live_active_markets())
    results.append(test_live_closed_markets())
    results.append(test_live_state_machine_consistency())

    return results


# ===== Fixture Tests =====

def test_active_market() -> TestResult:
    t = TestResult(name="1. Active market (no UMA) -> OPEN")
    data = _load_fixture("active_market.json")
    m = GammaMarket.model_validate(data)

    checks = [
        (m.internal_status == InternalMarketStatus.OPEN, f"status={m.internal_status}"),
        (m.closed is False, f"closed={m.closed}"),
        (m.volume == Decimal("57367327.83401454"), f"volume={m.volume}"),
        (m.liquidity == Decimal("595820.0548"), f"liquidity={m.liquidity}"),
        (len(m.parsed_outcomes) == 2, f"outcomes={len(m.parsed_outcomes)}"),
        (m.parsed_outcomes[0].price == Decimal("0.225"), f"price0={m.parsed_outcomes[0].price}"),
        (m.parsed_outcomes[1].price == Decimal("0.775"), f"price1={m.parsed_outcomes[1].price}"),
        (m.is_safe_to_settle() is False, "should NOT be safe to settle"),
        (m.winning_outcome() is None, "no winner yet"),
    ]
    t.passed = all(c[0] for c in checks)
    t.details = "; ".join(c[1] for c in checks if not c[0]) or "all checks passed"
    return t


def test_disputed_market() -> TestResult:
    t = TestResult(name="2. Disputed market (active, under UMA dispute) -> DISPUTED")
    data = _load_fixture("disputed_market.json")
    m = GammaMarket.model_validate(data)

    checks = [
        (m.internal_status == InternalMarketStatus.DISPUTED, f"status={m.internal_status}"),
        (m.uma_resolution_status == "disputed", f"uma={m.uma_resolution_status}"),
        (len(m.uma_resolution_statuses) == 4, f"history_len={len(m.uma_resolution_statuses)}"),
        (m.is_safe_to_settle() is False, "should NOT be safe to settle under dispute"),
        (m.winning_outcome() is None, "no winner during dispute"),
    ]
    t.passed = all(c[0] for c in checks)
    t.details = "; ".join(c[1] for c in checks if not c[0]) or "all checks passed"
    return t


def test_resolved_market() -> TestResult:
    t = TestResult(name="3. Resolved market (closed + resolved + winner) -> RESOLVED")
    data = _load_fixture("resolved_market.json")
    m = GammaMarket.model_validate(data)

    checks = [
        (m.internal_status == InternalMarketStatus.RESOLVED, f"status={m.internal_status}"),
        (m.closed is True, f"closed={m.closed}"),
        (m.uma_resolution_status == "resolved", f"uma={m.uma_resolution_status}"),
        (m.is_safe_to_settle() is True, "SHOULD be safe to settle"),
        (m.winning_outcome() == "Thunder", f"winner={m.winning_outcome()}"),
        (m.parsed_outcomes[0].price == Decimal("0"), f"loser_price={m.parsed_outcomes[0].price}"),
        (m.parsed_outcomes[1].price == Decimal("1"), f"winner_price={m.parsed_outcomes[1].price}"),
    ]
    t.passed = all(c[0] for c in checks)
    t.details = "; ".join(c[1] for c in checks if not c[0]) or "all checks passed"
    return t


def test_closed_not_resolved() -> TestResult:
    """THE CRITICAL TEST: closed=true but umaResolutionStatus=proposed -> CLOSED, NOT RESOLVED."""
    t = TestResult(name="4. CRITICAL: closed=true + proposed -> CLOSED (NOT RESOLVED)")
    data = _load_fixture("closed_not_resolved.json")
    m = GammaMarket.model_validate(data)

    checks = [
        (m.internal_status == InternalMarketStatus.CLOSED, f"status={m.internal_status}"),
        (m.internal_status != InternalMarketStatus.RESOLVED, "MUST NOT be RESOLVED"),
        (m.is_safe_to_settle() is False, "MUST NOT be safe to settle"),
        (m.winning_outcome() is None, "MUST NOT have a winner"),
        (m.closed is True, "closed=true"),
        (m.uma_resolution_status == "proposed", f"uma={m.uma_resolution_status}"),
    ]
    t.passed = all(c[0] for c in checks)
    t.details = "; ".join(c[1] for c in checks if not c[0]) or "all checks passed — PITFALL #2 mitigated"
    return t


def test_missing_optional_fields() -> TestResult:
    t = TestResult(name="5. Missing optional fields don't crash")
    data = {
        "id": "test-minimal",
        "question": "Minimal market",
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.5", "0.5"],
        "volume": "100",
        "active": True,
        "closed": False,
    }
    try:
        m = GammaMarket.model_validate(data)
        checks = [
            (m.end_date is None, "endDate missing -> None"),
            (m.uma_resolution_status is None, "umaResolutionStatus missing -> None"),
            (m.volume == Decimal("100"), f"volume={m.volume}"),
            (m.internal_status == InternalMarketStatus.OPEN, f"status={m.internal_status}"),
        ]
        t.passed = all(c[0] for c in checks)
        t.details = "; ".join(c[1] for c in checks if not c[0]) or "all checks passed"
    except Exception as e:
        t.passed = False
        t.details = f"CRASHED: {e}"
    return t


def test_winning_outcome_only_on_resolved() -> TestResult:
    t = TestResult(name="6. winning_outcome() returns None for non-RESOLVED")
    results = []
    for fixture in ["active_market.json", "disputed_market.json", "closed_not_resolved.json"]:
        data = _load_fixture(fixture)
        m = GammaMarket.model_validate(data)
        results.append((m.winning_outcome() is None, f"{fixture}: winner={m.winning_outcome()}"))

    t.passed = all(r[0] for r in results)
    t.details = "; ".join(r[1] for r in results if not r[0]) or "all non-resolved return None"
    return t


def test_decimal_precision() -> TestResult:
    t = TestResult(name="7. Decimal precision (no float contamination)")
    data = _load_fixture("active_market.json")
    m = GammaMarket.model_validate(data)

    checks = [
        (isinstance(m.volume, Decimal), f"volume type={type(m.volume).__name__}"),
        (isinstance(m.liquidity, Decimal), f"liquidity type={type(m.liquidity).__name__}"),
        (isinstance(m.parsed_outcomes[0].price, Decimal), f"price type={type(m.parsed_outcomes[0].price).__name__}"),
        (str(m.volume) == "57367327.83401454", f"volume repr={m.volume}"),
        (str(m.parsed_outcomes[0].price) == "0.225", f"price repr={m.parsed_outcomes[0].price}"),
    ]
    t.passed = all(c[0] for c in checks)
    t.details = "; ".join(c[1] for c in checks if not c[0]) or "all Decimal, no float"
    return t


def test_extra_fields_allowed() -> TestResult:
    t = TestResult(name="8. Extra/unknown fields don't crash (schema drift safe)")
    data = _load_fixture("active_market.json")
    data["brand_new_field_2026"] = "surprise!"
    data["nested_surprise"] = {"a": 1, "b": [2, 3]}
    try:
        m = GammaMarket.model_validate(data)
        t.passed = True
        t.details = "extra fields silently accepted"
    except Exception as e:
        t.passed = False
        t.details = f"CRASHED on unknown field: {e}"
    return t


# ===== Live API Tests =====

def test_live_active_markets() -> TestResult:
    t = TestResult(name="9. LIVE: Parse top 10 active markets from Gamma API")
    try:
        resp = httpx.get(
            f"{GAMMA_BASE}/markets",
            params={"active": "true", "closed": "false", "limit": 10, "order": "volume24hr", "ascending": "false"},
            timeout=15,
        )
        resp.raise_for_status()
        raw_markets = resp.json()

        parsed = []
        errors = []
        for raw in raw_markets:
            try:
                m = GammaMarket.model_validate(raw)
                parsed.append(m)
            except Exception as e:
                errors.append(f"id={raw.get('id')}: {e}")

        t.passed = len(errors) == 0 and len(parsed) > 0
        t.details = f"parsed {len(parsed)}/{len(raw_markets)} markets, {len(errors)} errors"
        if errors:
            t.details += f" — ERRORS: {'; '.join(errors[:3])}"
    except httpx.HTTPError as e:
        t.passed = False
        t.details = f"HTTP error: {e}"
    except Exception as e:
        t.passed = False
        t.details = f"Unexpected error: {e}"
    return t


def test_live_closed_markets() -> TestResult:
    t = TestResult(name="10. LIVE: Parse 5 closed/resolved markets from Gamma API")
    try:
        resp = httpx.get(
            f"{GAMMA_BASE}/markets",
            params={"closed": "true", "limit": 5, "order": "volume24hr", "ascending": "false"},
            timeout=15,
        )
        resp.raise_for_status()
        raw_markets = resp.json()

        parsed = []
        errors = []
        for raw in raw_markets:
            try:
                m = GammaMarket.model_validate(raw)
                parsed.append(m)
            except Exception as e:
                errors.append(f"id={raw.get('id')}: {e}")

        resolved_count = sum(1 for m in parsed if m.internal_status == InternalMarketStatus.RESOLVED)
        t.passed = len(errors) == 0 and resolved_count > 0
        t.details = (
            f"parsed {len(parsed)}/{len(raw_markets)}, "
            f"{resolved_count} RESOLVED, {len(errors)} errors"
        )
        if errors:
            t.details += f" — ERRORS: {'; '.join(errors[:3])}"
    except httpx.HTTPError as e:
        t.passed = False
        t.details = f"HTTP error: {e}"
    except Exception as e:
        t.passed = False
        t.details = f"Unexpected error: {e}"
    return t


def test_live_state_machine_consistency() -> TestResult:
    """Verify: no live closed market with proposed/disputed status is marked RESOLVED."""
    t = TestResult(name="11. LIVE: State machine consistency (no premature RESOLVED)")
    try:
        resp = httpx.get(
            f"{GAMMA_BASE}/markets",
            params={"limit": 25, "order": "volume24hr", "ascending": "false"},
            timeout=15,
        )
        resp.raise_for_status()
        raw_markets = resp.json()

        violations = []
        for raw in raw_markets:
            m = GammaMarket.model_validate(raw)
            if m.closed and m.uma_resolution_status in ("proposed", "disputed"):
                if m.internal_status == InternalMarketStatus.RESOLVED:
                    violations.append(
                        f"id={m.id}: closed+{m.uma_resolution_status} -> RESOLVED (DANGEROUS)"
                    )

        t.passed = len(violations) == 0
        t.details = (
            f"checked {len(raw_markets)} markets, {len(violations)} violations"
            if not violations
            else f"VIOLATIONS: {'; '.join(violations)}"
        )
    except httpx.HTTPError as e:
        t.passed = False
        t.details = f"HTTP error: {e}"
    except Exception as e:
        t.passed = False
        t.details = f"Unexpected error: {e}"
    return t


# ===== Helpers =====

def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    with open(path) as f:
        return json.load(f)


def print_report(results: list[TestResult]) -> None:
    print()
    print("=" * 70)
    print("  SPIKE 002: polymarket-gamma-parser — RESULTS")
    print("=" * 70)

    for r in results:
        icon = "+" if r.passed else "!"
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{icon}] {r.name}")
        print(f"      {status}: {r.details}")

    print()
    print("-" * 70)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    all_passed = passed == total
    print(f"  OVERALL: {passed}/{total} tests passed — {'ALL PASSED' if all_passed else 'FAILURES DETECTED'}")
    print("-" * 70)

    if all_passed:
        print()
        print("  Key takeaways for XPredict Phase 6:")
        print("    1. outcomes/outcomePrices ARE stringified JSON in real API -- STACK.md was right")
        print("    2. Numeric fields have dual encoding: volume (string) + volumeNum (float)")
        print("    3. Use string fields (volume, liquidity) -> Decimal for precision")
        print("    4. umaResolutionStatus is OPTIONAL (absent when no UMA process)")
        print("    5. umaResolutionStatuses (plural) gives full UMA history")
        print("    6. CRITICAL: closed=true + proposed/disputed -> CLOSED, NOT RESOLVED")
        print("    7. Only closed=true + resolved + clear winner -> safe to settle")
        print("    8. extra='allow' handles schema drift without crashing")
    print()


if __name__ == "__main__":
    t0 = time.perf_counter()
    results = run_tests()
    elapsed = (time.perf_counter() - t0) * 1000
    print_report(results)
    print(f"  Total time: {elapsed:.0f}ms")
    print()
