"""Pydantic API schemas for the wallet surface (Phase 3, Plan 03-04).

Two responsibilities live here:

1. **Money-as-string (SC#4 / PITFALLS #4).** ``MoneyStr`` is an ``Annotated``
   ``Decimal`` carrying a ``PlainSerializer`` that emits ``str(value)`` in JSON
   mode. Pydantic v2 ALREADY serializes ``Decimal`` → JSON string by default
   (``model_dump(mode="json")`` → ``{"amount": "10.0000"}``); this annotation is
   defense-in-depth so a careless future change to ``float`` cannot silently
   regress the contract (RESEARCH Pattern 4, lines 295-320). The SC#4 test
   asserts on the raw JSON text, not the parsed value.

2. **The SC#5 / WAL-09 regulatory firewall at the schema boundary.**
   ``RechargeRequest`` is ``extra="forbid"`` and has NO destination field of any
   kind — the only credit destination is the path user's own wallet, funded from
   a house source. A body carrying ``dst_user_id`` (or any user-to-user param) is
   a hard 422, making the no-user-to-user firewall observable at the wire surface
   (RESEARCH lines 499-513; PITFALLS #3).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# SC#4 / PITFALLS #4 — money is a JSON string, always. Pydantic v2 does this by
# default for Decimal; the explicit serializer is the prescribed regression guard.
MoneyStr = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
]


class RechargeRequest(BaseModel):
    """Body for ``POST /admin/wallets/{user_id}/recharge``.

    ``extra="forbid"`` is the SC#5 firewall at the schema boundary: an unknown
    field (e.g. ``dst_user_id``) is rejected with 422 — there is NO way for the
    caller to name a second/destination user. The only credit destination is the
    path ``user_id``'s own wallet; the debit source is always the house
    (``house_promo``), chosen server-side, never from the body.
    """

    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, description="Amount to credit (positive Decimal).")
    reason: str = Field(min_length=1, description="Audit reason for the recharge.")


class RechargeResponse(BaseModel):
    """Result of a recharge — money as a JSON string (SC#4).

    ``idempotent_replay`` is ``True`` when this response replays an existing
    transfer (a second POST with the same ``Idempotency-Key``): the wallet was
    NOT credited again, the same ``transfer_id`` is returned (SC#3).
    """

    transfer_id: UUID
    amount: MoneyStr
    currency: str
    idempotent_replay: bool


if __name__ == "__main__":  # pragma: no cover - import smoke for the verify step
    # ``uv run python -m app.wallet.schemas`` — a no-op import smoke so the
    # verify command can confirm the module imports and the models build.
    _req = RechargeRequest(amount=Decimal("10.0000"), reason="smoke")
    _resp = RechargeResponse(
        transfer_id=UUID("00000000-0000-0000-0000-000000000000"),
        amount=Decimal("10.0000"),
        currency="PLAY_USD",
        idempotent_replay=False,
    )
    assert _resp.model_dump(mode="json")["amount"] == "10.0000"
    print("app.wallet.schemas OK")
