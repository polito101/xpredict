# Fase LB-A: Backend bridge — CONTEXT

Part of milestone **v1.3 Live-Bets demo** (off-grid). Design contract (READ FIRST):
[`../../../docs/superpowers/specs/2026-06-05-live-bets-integration-design.md`](../../../docs/superpowers/specs/2026-06-05-live-bets-integration-design.md).
Milestone plan-of-record: [`../../milestones/v1.3-MILESTONE-CONTEXT.md`](../../milestones/v1.3-MILESTONE-CONTEXT.md).

## Goal
XPredict (as the live-bets **operator**) can mint a player session on live-bets and **mirror live-bets bets into its own double-entry ledger** — debit the player's wallet when a bet is placed, credit on win — idempotently and server-side-verified. Backend only; no UI (that is LB-B), no live-bets-side setup (that is LB-C).

## Scope — IN
- New module `backend/app/integrations/livebets/` (sibling of `app/integrations/polymarket/`):
  - `client.py` — async httpx client to live-bets, `X-API-Key` from settings: `mint_session(player_ref, table_id, ttl_seconds=None)` → `POST /v2/sessions`; `get_bet(bet_id)` → `GET /v2/bets/{id}`; `list_tables()` → `GET /v2/catalog/tables`.
  - `service.py` — `LiveBetsBridge`:
    - `record_placed(user, bet_id)`: `get_bet` → assert `status == PENDING`, read authoritative `stake` → post debit transfer → upsert `livebets_bets` row. Idempotent.
    - `record_settled(user, bet_id)`: `get_bet` → assert `WON|LOST|REFUNDED|VOIDED` (live-bets' real enum — no `VOID`), read authoritative `payout` → post settle transfer → update `livebets_bets.status/settled_at`. Idempotent.
  - `router.py` — player-authed FastAPI routes: `POST /api/live/session`, `GET /api/live/tables`, `POST /api/live/bets/{bet_id}/placed`, `POST /api/live/bets/{bet_id}/settled`. Mount it the way existing routers are mounted.
- Additive Alembic migration:
  - `livebets_escrow` system **singleton** Account (`owner_type=system`, `owner_id=NULL`, `kind='livebets_escrow'`, `currency=PLAY_USD`).
  - `livebets_bets` mirror table: `bet_id` (PK, live-bets UUID), `user_id` (FK users), `table_id`, `market_id`, `stake NUMERIC(18,4)`, `status`, `created_at`, `settled_at` nullable.
- Config (settings + `.env.example`): `LIVEBETS_API_BASE` (default `http://localhost:8080`), `LIVEBETS_API_KEY`, `LIVEBETS_DEFAULT_TABLE_ID`, `LIVEBETS_ENABLE_WEBHOOK=false`, `LIVEBETS_WEBHOOK_SECRET` (optional).
- Backend unit tests for the bridge (faked live-bets client, no network).

## Scope — OUT (do NOT build here)
- Frontend `/live` route / widget wiring → **LB-B**.
- live-bets local stack, ingest clips, run orchestrator, pre-fund, CORS, port remap → **LB-C**.
- Webhook receiver: default OFF. Optional `webhook.py` may be **stubbed** (HMAC verify + delegate to `record_settled`) but is not required for LB-A; keep `LIVEBETS_ENABLE_WEBHOOK=false`.

## Success Criteria (what must be TRUE)
1. The `app/integrations/livebets/` module exists with `client.py`, `service.py`, `router.py`; routes are mounted and reachable under player auth; unauth requests are rejected.
2. The additive migration applies cleanly and is reversible, creating the `livebets_escrow` singleton account and the `livebets_bets` table — **zero behavior change** to existing tables (existing wallet/bets/settlement tests still pass).
3. Ledger mirror is correct: `record_placed` posts `user_wallet → livebets_escrow` (stake), key `livebets:{bet_id}:placed`; `record_settled` posts — WON: `livebets_escrow → user_wallet` (stake) **+** `house_promo → user_wallet` (payout−stake); LOST: `livebets_escrow → house_revenue` (stake); REFUNDED/VOIDED: `livebets_escrow → user_wallet` (stake) — key `livebets:{bet_id}:settled` (WON uses per-leg `:stake`/`:winnings`). All via `WalletService._post_transfer` inside one owned transaction (mirrors `app/bets` + `app/settlement`).
4. **Idempotent**: replaying the same `placed`/`settled` event is a no-op (the `Transfer.idempotency_key` dedupes); `livebets_escrow` nets to zero across a full placed→settled cycle (won and lost).
5. **Server-side verified**: the bridge always reads stake/status/payout from live-bets `GET /v2/bets/{id}` before posting — it never trusts client-supplied amounts. A status/stake mismatch is rejected without posting.
6. `cd backend && uv run pytest` is green for the new module: covers placed→won, placed→lost, void/refund, duplicate-event no-op, escrow-nets-to-zero, and verification-rejects-mismatch.

## Patterns to mirror (verified — read these)
- `backend/app/bets/service.py` → `BetService.place_bet`: owns the TX, locks accounts in **canonical UUID order** before posting, calls `WalletService._post_transfer(session, debit_account_id=…, credit_account_id=…, amount=…, idempotency_key=…, kind=…, metadata=…)`. Debit `user_wallet` → credit `market_liability`. Copy this escrow shape.
- `backend/app/settlement/service.py` → `SettlementService.resolve_market`: WINNER = `market_liability → user_wallet` (stake) **+** `house_promo → user_wallet` (winnings). Confirms how winnings are funded — `livebets` win path mirrors this exactly.
- `backend/app/wallet/service.py`: `_post_transfer` (sole double-entry writer, WAL-07), `_resolve_user_wallet_id(session, user_id)`. `backend/app/wallet/models.py`: `Account(owner_type, owner_id, kind, currency, balance, version)`, `Transfer(kind, idempotency_key, actor_user_id, transfer_metadata)`, `Entry(direction, amount)`. `backend/app/wallet/constants.py`: confirm the exact house account constant (`OWNER_MARKET`, `PLAY_USD`, the house/promo kind) — do not invent names.
- `backend/app/integrations/polymarket/`: sibling integration module shape (httpx client + settings + Celery/router wiring).
- `Skill("spike-findings-xpredict")`: project ledger/locking gotchas (canonical lock order, idempotency, money columns).

## Open items for the planner to resolve (grep, don't guess)
- Exact house account constant used for winnings funding **and** the loss sink (read `app/wallet/constants.py` + `app/settlement/service.py`). If a distinct house P&L account exists, route losses there instead of `house_promo`.
- How to create the `livebets_escrow` singleton: migration data-insert vs. lazy get-or-create (compare `BetService._ensure_market_liability_account`). Prefer the project's existing convention for system accounts.
- How routers are registered (grep where `bets`/`wallet` routers are `include_router`ed) and how the current-player dependency is injected.
- Confirm the live-bets `GET /v2/bets/{id}` response fields for settled bets (`status`, `stake`, `payout`) against `live-bets/docs/INTEGRATION-GUIDE.md` (the other project, read-only).

## Test command
`cd backend && uv run pytest` (testcontainers + Docker). Keep the new tests hermetic — fake the live-bets client; no live network.
