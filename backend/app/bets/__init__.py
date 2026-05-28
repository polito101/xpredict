"""Bets domain (Phase 5) — bet placement + (later) settlement.

Depends on the market domain (Phase 4) ONLY through the narrow ``market_port``
Protocol, so this package develops in parallel with Phase 4 without importing its
concrete models. The ``bets`` table's FK to ``markets``/``outcomes`` is added by the
integration migration ``0005`` (off Phase 4's ``0004``), not during parallel work.
"""
