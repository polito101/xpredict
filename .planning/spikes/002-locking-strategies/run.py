r"""Spike 002 — locking strategy comparison (the core Phase 3 decision).

FOR UPDATE (pessimistic) vs version-CAS (optimistic) vs SERIALIZABLE + retry,
all guarding the SAME read->decide->write pattern. 50 concurrent "spend 20 from a
wallet of 100" (ROADMAP SC#2 says "50 simultaneous"). Only 5 are affordable.

All three MUST be correct (balance >= 0, drift 0, exactly 5 succeed). The
differentiator is wall time + retry amplification under maximum contention.

Run:  <repo>\backend\.venv\Scripts\python.exe .planning\spikes\002-locking-strategies\run.py
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))

from harness import provision, print_result, run_load  # noqa: E402
from pg import postgres_container  # noqa: E402

OPENING = Decimal("100.0000")
AMOUNT = Decimal("20.0000")
N = 50

# (strategy, label, engine isolation level)
STRATEGIES = [
    ("for_update", "FOR UPDATE (pessimistic)", None),
    ("optimistic", "version CAS (optimistic)", None),
    ("serializable", "SERIALIZABLE + retry", "SERIALIZABLE"),
]


async def main(dsn: str) -> None:
    print(f"\nSpike 002 — locking comparison (N={N} concurrent spend {AMOUNT} from {OPENING}; affordable=5)\n")
    results = []
    for strategy, label, isolation in STRATEGIES:
        async with provision(
            dsn, balance_check=True, opening_balance=OPENING, isolation_level=isolation
        ) as ledger:
            r = await run_load(
                ledger, label=label, n=N, per_amount=AMOUNT, opening=OPENING, strategy=strategy
            )
            print_result(r)
            results.append((label, r))

    print("\n  Head-to-head")
    print(f"  {'strategy':<28}{'correct':<9}{'ok':<5}{'wall ms':<10}{'attempts':<10}{'amplification':<14}")
    for label, r in results:
        print(
            f"  {label:<28}{('YES' if r.correct else 'NO'):<9}{r.outcomes['ok']:<5}"
            f"{r.wall_seconds * 1000:<10.0f}{r.total_attempts:<10}{r.total_attempts / r.n:<.2f}x"
        )
    print()


if __name__ == "__main__":
    with postgres_container() as dsn:
        asyncio.run(main(dsn))
