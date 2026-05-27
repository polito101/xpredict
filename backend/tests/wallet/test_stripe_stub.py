"""SC#6 / PLT-05 — the Stripe recharge stub raises ``NotImplementedError``.

A FAST UNIT test (NO Docker, NO DB): ``WalletService.recharge`` rejects
``payment_provider="stripe"`` BEFORE it touches the session, so a dummy/None
session is sufficient. This keeps SC#6 provable in the quick non-integration
run (``pytest -m "not integration"``), per the plan's verification.

The "door is open" for v2: the method signature already accepts
``payment_provider`` so enabling real Stripe (behind the ``stripe_recharge_enabled``
feature flag, seeded ``FALSE`` in Phase 1) needs no breaking refactor — only the
``NotImplementedError`` branch is replaced.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.wallet.service import PROVIDER_STRIPE, WalletService

# Explicitly NOT marked ``integration`` — this is a pure unit test and MUST run
# in the ``-m "not integration"`` quick pass (no Docker).
pytestmark = [pytest.mark.asyncio]


async def test_recharge_stripe_raises_not_implemented() -> None:
    """``recharge(payment_provider="stripe")`` raises ``NotImplementedError`` (SC#6).

    The stripe branch is checked first in ``recharge`` — before the session is
    used — so passing ``session=None`` proves the raise happens with no DB.
    """
    with pytest.raises(NotImplementedError):
        await WalletService.recharge(
            None,  # type: ignore[arg-type]  # the stripe branch raises before touching it
            user_id=uuid4(),
            amount=Decimal("1"),
            reason="x",
            idempotency_key="k",
            payment_provider=PROVIDER_STRIPE,
        )


async def test_recharge_stripe_constant_is_stripe() -> None:
    """Guard the literal so the SC#6 stub stays wired to the documented provider."""
    assert PROVIDER_STRIPE == "stripe"
