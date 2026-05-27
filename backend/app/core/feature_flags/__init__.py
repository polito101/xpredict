"""Feature-flag infrastructure (D-37, D-38, PLT-06).

Schema is in models.py, the read API in service.py. Phase 1 ships the simplest
version — no cache; query every call. Plan 01-03's migration seeds the three
default flags (``stripe_recharge_enabled``, ``polymarket_sync_enabled``,
``admin_2fa_required``) — all ``false`` in v1.
"""
