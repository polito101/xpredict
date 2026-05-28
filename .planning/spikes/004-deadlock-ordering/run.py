r"""Spike 004 — deadlock ordering.

Two accounts, many concurrent transfers in BOTH directions. Each transfer locks
both accounts with `SELECT ... FOR UPDATE`. When lock order follows the transfer
direction (unordered), opposing transfers deadlock (Postgres kills a victim with
40P01). When every transfer locks the two rows in a canonical UUID order, no
deadlock can form — validating PITFALLS #1's "acquire locks in a consistent order".

Run:  <repo>\backend\.venv\Scripts\python.exe .planning\spikes\004-deadlock-ordering\run.py
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from collections import Counter
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))

from harness import Ledger, fund, locked_transfer, provision  # noqa: E402
from pg import postgres_container  # noqa: E402

OPENING = Decimal("1000.0000")
AMT = Decimal("10.0000")
PAIRS = 15  # => 30 concurrent transfers, half each direction


async def scenario(ledger: Ledger, *, canonical: bool) -> Counter:
    await fund(ledger, ledger.counterparty_id, OPENING)  # so neither side underflows
    tasks = []
    for _ in range(PAIRS):
        tasks.append(
            locked_transfer(ledger, ledger.wallet_id, ledger.counterparty_id, AMT, canonical_order=canonical)
        )
        tasks.append(
            locked_transfer(ledger, ledger.counterparty_id, ledger.wallet_id, AMT, canonical_order=canonical)
        )
    return Counter(await asyncio.gather(*tasks))


async def main(dsn: str) -> None:
    print(f"\nSpike 004 — deadlock ordering ({PAIRS * 2} concurrent bidirectional transfers)\n")

    async with provision(dsn, balance_check=False, opening_balance=OPENING) as ledger:
        c = await scenario(ledger, canonical=False)
        print(f"        unordered locking : outcomes={dict(c)}   (expect some 'deadlock')")

    async with provision(dsn, balance_check=False, opening_balance=OPENING) as ledger:
        c = await scenario(ledger, canonical=True)
        ok = c["deadlock"] == 0
        print(f"  [{'OK  ' if ok else 'FAIL'}] canonical order   : outcomes={dict(c)}   (expect zero 'deadlock')")
    print()


if __name__ == "__main__":
    with postgres_container() as dsn:
        asyncio.run(main(dsn))
