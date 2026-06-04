"""Bloque 1 (v1.1 Demo Polish — Fase B seed harness): demo user specs.

The seed dataset is a *sales demo*, so the user list must be DETERMINISTIC
(reproduced identically on every run — no RNG), every demo user funded with the
$1000 signup bonus plus zero-or-more recharges (so wallet history is non-empty),
and every email unique under the demo domain (no ``users.email`` UNIQUE clash).

This module covers the pure spec builder only; the DB-touching ``seed_users``
(verified users + ledger-backed wallets) is covered in ``test_seed_users_db.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from bin.seed_demo import SeedConfig, build_user_specs

pytestmark = pytest.mark.unit


def test_build_user_specs_is_deterministic_and_funded() -> None:
    """Same config → identical, unique, funded specs under the demo domain."""
    cfg = SeedConfig(n_users=4)

    specs = build_user_specs(cfg)
    # Deterministic: a second call yields identical specs (no RNG → reproducible).
    assert build_user_specs(cfg) == specs

    assert len(specs) == 4
    # Unique emails under the demo domain (avoid the users.email UNIQUE clash).
    assert len({s.email for s in specs}) == 4
    for s in specs:
        assert s.email.endswith(f"@{cfg.email_domain}")
        assert s.signup_bonus == Decimal("1000.0000")
        # expected_balance is the bonus plus every recharge; always funded.
        assert s.expected_balance == s.signup_bonus + sum(s.recharges, Decimal("0"))
        assert s.expected_balance >= Decimal("1000.0000")
