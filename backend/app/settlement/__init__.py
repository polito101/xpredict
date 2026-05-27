"""Settlement (Phase 5).

Resolution logic, payout computation, and ledger-posting orchestration for
resolved markets. The pure money math lives in :mod:`app.settlement.payout`;
the transactional ``SettlementService`` (built next) reuses the validated Phase 3
ledger writer (``WalletService._post_transfer``) to credit winners and sink
losers' stakes — and is reused UNCHANGED by Phase 7's Polymarket auto-resolution
(ARCHITECTURE.md §"settlement").
"""
