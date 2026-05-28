r"""Spike 003 — atomicity + idempotency.

Part 1 — atomicity (PITFALLS #10): run the full double-entry move (transfer + 2
entries + balance updates) then raise BEFORE commit. Assert NOTHING persisted —
no transfer, no entries, balance unchanged. Proves `AsyncSession.begin()` gives
all-or-nothing, the property bet placement in Phase 5 will reuse.

Part 2 — idempotency (ROADMAP SC#3): fire K concurrent transfers with the SAME
Idempotency-Key. Assert exactly one applies and the rest dedupe via the
`transfers.idempotency_key` UNIQUE constraint — wallet debited exactly once.

Run:  <repo>\backend\.venv\Scripts\python.exe .planning\spikes\003-atomic-transfer-idempotency\run.py
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from collections import Counter
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))

from harness import (  # noqa: E402
    FaultInjected,
    attempt_with_fault,
    count_rows,
    provision,
    spend,
    wallet_balance,
)
from pg import postgres_container  # noqa: E402

OPENING = Decimal("100.0000")
AMOUNT = Decimal("20.0000")
K = 10  # concurrent calls sharing one Idempotency-Key


async def main(dsn: str) -> None:
    print("\nSpike 003 — atomicity + idempotency\n")

    # --- Part 1: atomicity (fault injected mid-transaction) ---
    async with provision(dsn, balance_check=True, opening_balance=OPENING) as ledger:
        before = await count_rows(ledger)  # seed = {transfers:1, entries:2}
        bal0 = await wallet_balance(ledger)
        try:
            await attempt_with_fault(ledger, AMOUNT)
        except FaultInjected:
            pass
        after = await count_rows(ledger)
        bal1 = await wallet_balance(ledger)
        ok = after == before and bal1 == bal0
        print(
            f"  [{'OK  ' if ok else 'FAIL'}] atomicity   : rows before={before} after={after}; "
            f"balance {bal0} -> {bal1}  (fault fully rolled back)"
        )

    # --- Part 2: idempotency (concurrent identical Idempotency-Key) ---
    async with provision(dsn, balance_check=True, opening_balance=OPENING) as ledger:
        tags = await asyncio.gather(
            *(
                spend(ledger, AMOUNT, strategy="for_update", idempotency_key="charge:req-42")
                for _ in range(K)
            )
        )
        c = Counter(tags)
        bal = await wallet_balance(ledger)
        rows = await count_rows(ledger)
        ok = (
            c["ok"] == 1
            and c["idempotent_dup"] == K - 1
            and bal == OPENING - AMOUNT
            and rows == {"transfers": 2, "entries": 4}  # seed(1,2) + exactly one spend(1,2)
        )
        print(
            f"  [{'OK  ' if ok else 'FAIL'}] idempotency : outcomes={dict(c)}; balance={bal}; "
            f"rows={rows}  (exactly one of {K} applied)"
        )
    print()


if __name__ == "__main__":
    with postgres_container() as dsn:
        asyncio.run(main(dsn))
