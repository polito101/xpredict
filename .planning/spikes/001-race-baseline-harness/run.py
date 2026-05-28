r"""Spike 001 — race-baseline-harness.

Proves the wallet race is real on the actual Phase 3 stack (SQLAlchemy 2.0 async +
asyncpg + Postgres 16) and builds the reusable concurrent-load harness the other
spikes share.

Scenario: 20 concurrent "spend 20 from a wallet of 100" transfers. Only 5 are
affordable, so a correct system ends at balance 0 with exactly 5 succeeded and zero
drift. We run three NAIVE (unguarded) variants to see how it breaks:

  A. naive_lost_update, CHECK off -> Python-computed write (last-writer-wins)
        => DRIFT: balance and ledger disagree; money is created from nothing.
  B. naive_overdraw,    CHECK off -> atomic SQL decrement, no guard
        => NEGATIVE balance: the wallet goes below zero.
  C. naive_overdraw,    CHECK on  -> atomic decrement + CHECK (balance >= 0)
        => the DB's CHECK + single-statement decrement happens to save THIS
           single-row case (instructive nuance for the locking discussion).

Run:  <repo>\backend\.venv\Scripts\python.exe .planning\spikes\001-race-baseline-harness\run.py
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
N = 20


async def main(dsn: str) -> None:
    print(f"\nSpike 001 — race baseline (N={N} concurrent spend {AMOUNT} from {OPENING}; affordable=5)\n")

    async with provision(dsn, balance_check=False, opening_balance=OPENING) as ledger:
        print_result(
            await run_load(
                ledger, label="A naive_lost_update (CHECK off)", n=N,
                per_amount=AMOUNT, opening=OPENING, strategy="naive_lost_update", read_delay=0.10,
            )
        )
    async with provision(dsn, balance_check=False, opening_balance=OPENING) as ledger:
        print_result(
            await run_load(
                ledger, label="B naive_overdraw (CHECK off)", n=N,
                per_amount=AMOUNT, opening=OPENING, strategy="naive_overdraw", read_delay=0.05,
            )
        )
    async with provision(dsn, balance_check=True, opening_balance=OPENING) as ledger:
        print_result(
            await run_load(
                ledger, label="C naive_overdraw (CHECK on)", n=N,
                per_amount=AMOUNT, opening=OPENING, strategy="naive_overdraw", read_delay=0.05,
            )
        )
    print("\nExpectation: A and B are FAIL (corruption); C may pass for this single-row case.\n")


if __name__ == "__main__":
    with postgres_container() as dsn:
        asyncio.run(main(dsn))
