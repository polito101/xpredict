---
phase: LB-A-backend-bridge
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/alembic/versions/0011_livebets_bridge.py
  - backend/app/integrations/livebets/__init__.py
  - backend/app/integrations/livebets/constants.py
  - backend/app/integrations/livebets/models.py
  - backend/app/integrations/livebets/client.py
  - backend/app/integrations/livebets/schemas.py
  - backend/app/integrations/livebets/service.py
  - backend/app/integrations/livebets/router.py
  - backend/app/core/config.py
  - backend/app/main.py
  - .env.example
autonomous: true
requirements:
  - LB-A-SC1   # module exists (client/service/router), routes mounted under player auth, unauth rejected
  - LB-A-SC2   # additive reversible migration: livebets_escrow singleton + livebets_bets table, zero behavior change
  - LB-A-SC3   # ledger mirror correct (placed/won/lost/void) via WalletService._post_transfer in one owned TX
  - LB-A-SC4   # idempotent: replay is a no-op; escrow nets to zero
  - LB-A-SC5   # server-side verified: stake/status/payout always read from GET /v2/bets/{id}; mismatch rejected

must_haves:
  truths:
    - "Running `alembic upgrade head` creates the livebets_escrow singleton account and the livebets_bets table with zero change to existing tables; `alembic downgrade -1` removes both cleanly."
    - "LiveBetsBridge.record_placed debits user_wallet -> livebets_escrow for the stake read from GET /v2/bets/{id}, idempotency_key livebets:{bet_id}:placed, in one owned transaction."
    - "LiveBetsBridge.record_settled credits per outcome (WON: escrow->wallet stake + house_promo->wallet payout-stake; LOST: escrow->house_revenue stake; REFUNDED/VOIDED: escrow->wallet stake), idempotency_key livebets:{bet_id}:settled (WON legs suffixed :stake/:winnings)."
    - "The bridge reads stake/status/payout from live-bets before posting and never trusts a client-supplied amount; a status/stake mismatch raises without posting."
    - "Routes POST /api/live/session, GET /api/live/tables, POST /api/live/bets/{bet_id}/placed, POST /api/live/bets/{bet_id}/settled are mounted and require current_active_player (401 when unauthenticated)."
  artifacts:
    - path: "backend/alembic/versions/0011_livebets_bridge.py"
      provides: "Additive reversible migration: livebets_escrow singleton + livebets_bets mirror table"
      contains: "livebets_bets"
    - path: "backend/app/integrations/livebets/client.py"
      provides: "Async httpx client to live-bets (mint_session, get_bet, list_tables) with X-API-Key"
      exports: ["LiveBetsClient"]
    - path: "backend/app/integrations/livebets/service.py"
      provides: "LiveBetsBridge.record_placed / record_settled — idempotent, server-side verified ledger mirror"
      exports: ["LiveBetsBridge"]
    - path: "backend/app/integrations/livebets/router.py"
      provides: "Player-authed FastAPI routes under /api/live"
      exports: ["livebets_router"]
    - path: "backend/app/integrations/livebets/models.py"
      provides: "LiveBetsBet ORM model (livebets_bets table)"
      contains: "class LiveBetsBet"
    - path: "backend/app/integrations/livebets/constants.py"
      provides: "Account/transfer-kind literals + LIVEBETS_ESCROW_ACCOUNT_ID fixed UUID + idempotency-key helpers"
      contains: "LIVEBETS_ESCROW_ACCOUNT_ID"
  key_links:
    - from: "backend/app/integrations/livebets/service.py"
      to: "app.wallet.service.WalletService._post_transfer"
      via: "the sole double-entry writer (WAL-07), inside one session.begin() with canonical UUID lock order"
      pattern: "WalletService\\._post_transfer"
    - from: "backend/app/integrations/livebets/service.py"
      to: "app.integrations.livebets.client.LiveBetsClient.get_bet"
      via: "server-side verification before any ledger post"
      pattern: "get_bet"
    - from: "backend/app/main.py"
      to: "app.integrations.livebets.router.livebets_router"
      via: "app.include_router"
      pattern: "include_router\\(livebets_router\\)"
    - from: "backend/app/integrations/livebets/service.py"
      to: "app.wallet.constants.HOUSE_REVENUE_ACCOUNT_ID"
      via: "loss sink (distinct house P&L account, mirrors settlement's loser sweep)"
      pattern: "HOUSE_REVENUE_ACCOUNT_ID"
---

<objective>
Build the additive backend bridge that lets XPredict (as the live-bets operator) mirror live-bets bets into its own double-entry ledger: an Alembic migration (the `livebets_escrow` system singleton + the `livebets_bets` mirror table), settings + `.env.example` keys, and the `backend/app/integrations/livebets/` module (`client.py`, `schemas.py`, `models.py`, `constants.py`, `service.py`, `router.py`, `__init__.py`). The router is mounted in `app/main.py` under the existing player auth.

Purpose: Money mirrors correctly and idempotently — debit on placement, credit on win, sweep on loss, refund on void — always server-side-verified against live-bets, reusing the validated `WalletService._post_transfer` exactly as `app/bets` and `app/settlement` do, with zero behavior change to existing wallet/bets/settlement tables. Tests ship in LB-A-02.

Output: One migration, six new module files, settings + `.env.example` additions, and one `include_router` line.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/LB-A-backend-bridge/CONTEXT.md
@docs/superpowers/specs/2026-06-05-live-bets-integration-design.md

# Patterns to mirror (read the real shape; copy it — do NOT invent API)
@backend/app/bets/service.py
@backend/app/settlement/service.py
@backend/app/wallet/service.py
@backend/app/wallet/models.py
@backend/app/wallet/constants.py
@backend/app/integrations/polymarket/client.py
@backend/alembic/versions/0004_phase3_wallet_ledger.py
@backend/alembic/versions/0005_phase5_bets.py
@backend/app/bets/router.py
@backend/app/core/config.py
@backend/CONVENTIONS.md

# live-bets operator API (the OTHER project — READ-ONLY, do not modify)
@../live-bets/docs/INTEGRATION-GUIDE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Additive migration + constants + ORM model + config + .env.example</name>
  <files>backend/alembic/versions/0011_livebets_bridge.py, backend/app/integrations/livebets/constants.py, backend/app/integrations/livebets/models.py, backend/app/integrations/livebets/__init__.py, backend/app/core/config.py, .env.example</files>
  <action>
Lay the additive schema + config foundation. Nothing here changes existing tables or behavior.

1. `constants.py` — plain `str`/`UUID` literals, mirroring `app/wallet/constants.py` and `app/bets/constants.py` (no enums):
   - `KIND_LIVEBETS_ESCROW = "livebets_escrow"` (the account kind for the new singleton).
   - `LIVEBETS_ESCROW_ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")` — a fixed singleton UUID following the `house_*` convention (HOUSE_PROMO is `...00a1`, HOUSE_REVENUE `...00a2`; use the `...00b1` block to avoid collision). The migration seeds this exact id so the service references it without a runtime lookup, exactly like `HOUSE_PROMO_ACCOUNT_ID`.
   - Transfer-kind literals (all migration-free — `transfers.kind` is `Text`): `TRANSFER_LIVEBETS_PLACED = "livebets_placed"`, `TRANSFER_LIVEBETS_SETTLE_STAKE_RETURN = "livebets_settle_stake_return"`, `TRANSFER_LIVEBETS_SETTLE_WINNINGS = "livebets_settle_winnings"`, `TRANSFER_LIVEBETS_SETTLE_LOSS = "livebets_settle_loss"`, `TRANSFER_LIVEBETS_VOID_REFUND = "livebets_void_refund"`.
   - Mirror-table status literals — live-bets' REAL `BetStatus` enum (`live-bets/live_bets/models.py`) is `PENDING|WON|LOST|REFUNDED|VOIDED`; **there is NO `VOID`**: `LIVEBETS_PENDING = "PENDING"`, `LIVEBETS_WON = "WON"`, `LIVEBETS_LOST = "LOST"`, `LIVEBETS_REFUNDED = "REFUNDED"`, `LIVEBETS_VOIDED = "VOIDED"`. Plus helper sets: `LIVEBETS_REFUND_STATUSES = frozenset({LIVEBETS_REFUNDED, LIVEBETS_VOIDED})` (both take the stake-return leg) and `LIVEBETS_SETTLED_STATUSES = frozenset({LIVEBETS_WON, LIVEBETS_LOST, LIVEBETS_REFUNDED, LIVEBETS_VOIDED})`.
   - Idempotency-key helpers (mirror `settle_idempotency_key`): `placed_idempotency_key(bet_id) -> f"livebets:{bet_id}:placed"` and `settled_idempotency_key(bet_id) -> f"livebets:{bet_id}:settled"`. NOTE: both win-legs share the SAME settled key namespace — give the two won legs DISTINCT keys by suffixing the leg, e.g. `f"livebets:{bet_id}:settled:stake"` and `f"livebets:{bet_id}:settled:winnings"`, because `transfers.idempotency_key` is UNIQUE and two legs in one settle cannot share one key (this is exactly why settlement uses `settle:{bet_id}:{leg}` per-leg keys — read `app/settlement/constants.py`). LOST, REFUNDED and VOIDED each post a single leg, so they may use `f"livebets:{bet_id}:settled"` directly. Decide and centralize the exact key strings here so service + tests agree on one literal.

2. `models.py` — the `LiveBetsBet` ORM model on `app.db.base.Base` (the `livebets_bets` mirror table). Follow the money-column and tenant-ghost conventions in `backend/CONVENTIONS.md` and the shape of `app/bets/models.py`:
   - `bet_id: Mapped[PyUUID]` PRIMARY KEY (the live-bets UUID — NOT server-defaulted; it is supplied by live-bets).
   - `user_id: Mapped[PyUUID]` not null (the owning XPredict user; plain UUID, no DB FK — match `bets.user_id` which is FK-less by project convention, see `0005` note).
   - `table_id: Mapped[PyUUID | None]`, `market_id: Mapped[PyUUID | None]` (live-bets identifiers; nullable — placed may know table, market comes from get_bet).
   - `stake: Mapped[Money]` (use the `Money` alias from `app/db/types.py` — NUMERIC(18,4), satisfies `scripts/lint_money_columns.py`).
   - `status: Mapped[str]` Text, server_default `'PENDING'`, with a CHECK in `__table_args__`: `status IN ('PENDING','WON','LOST','REFUNDED','VOIDED')`.
   - `created_at` timezone-aware `server_default=func.now()`; `settled_at: Mapped[datetime | None]` nullable.
   - `tenant_id` ghost column per CONVENTIONS §2 (nullable UUID, `default=lambda: get_settings().TENANT_ID_DEFAULT`).
   - Keep the model<->migration DDL identical (the project asserts this elsewhere; do not drift).

3. `__init__.py` — module docstring only (one line: "Live-bets operator integration — client, ledger bridge, player routes."). Do NOT register anything in a global REGISTRY (the polymarket `__init__` registers a MarketSource adapter; livebets is NOT a MarketSource, so this stays minimal). `__all__ = []` or omit.

4. `0011_livebets_bridge.py` — additive, reversible Alembic migration. Mirror `0005_phase5_bets.py` (table create) + the singleton-seed block of `0004_phase3_wallet_ledger.py` (the `house_*` INSERT ... ON CONFLICT DO NOTHING):
   - `revision = "0011_livebets_bridge"` (24 chars — under the `varchar(32)` `alembic_version.version_num` limit that `0010` documents; do NOT exceed 32). `down_revision = "0010_phase12_resolution_stakes"` (the current head — confirm with `alembic heads` before writing).
   - `upgrade()`:
     - `op.create_table("livebets_bets", ...)` matching `models.py` verbatim: `bet_id` UUID PK (NO `gen_random_uuid()` server default — it is the live-bets id), `user_id` UUID not null, `table_id`/`market_id` UUID nullable, `stake` Numeric(18,4) not null, `status` Text not null server_default `'PENDING'` + CHECK `status IN ('PENDING','WON','LOST','REFUNDED','VOIDED')`, `created_at` TIMESTAMP(tz) not null `NOW()`, `settled_at` TIMESTAMP(tz) nullable, `tenant_id` UUID nullable server_default the TENANT_DEFAULT literal (same `00000000-0000-0000-0000-000000000001` literal used in `0004`/`0005`).
     - `op.create_index("livebets_bets_user_idx", "livebets_bets", ["user_id"])`.
     - Seed the `livebets_escrow` singleton with the SAME idempotent pattern as the `house_*` seed: `INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) VALUES ('<LIVEBETS_ESCROW_ACCOUNT_ID>', 'system', NULL, 'livebets_escrow', 'PLAY_USD', 0) ON CONFLICT (owner_type, owner_id, kind, currency) DO NOTHING;`. Import the literals from `app.integrations.livebets.constants` + `app.wallet.constants` (`OWNER_SYSTEM`, `PLAY_USD`) exactly as `0004` imports its seed literals — do NOT hardcode strings that already have a constant.
   - `downgrade()`: delete the seeded escrow account by id (`DELETE FROM accounts WHERE id = '<LIVEBETS_ESCROW_ACCOUNT_ID>';`), drop the index, drop `livebets_bets`. The escrow account is balance-0 on a clean down (no entries reference it unless bets were mirrored); leave any account with entries untouched is NOT required for the demo, but the DELETE is safe because a clean downgrade implies no live data.

5. `app/core/config.py` — APPEND new keys to `Settings` (never redefine the shape; `extra="ignore"` already tolerates them — CONVENTIONS §7). Add a `# Live-bets demo (v1.3, LB-A)` section after the Phase 7 block:
   - `LIVEBETS_API_BASE: str = "http://localhost:8080"`
   - `LIVEBETS_API_KEY: str | None = None` (optional in dev/test so `Settings()` validates with no value; the client raises a clear error if it is needed and unset)
   - `LIVEBETS_DEFAULT_TABLE_ID: str | None = None`
   - `LIVEBETS_ENABLE_WEBHOOK: bool = False`
   - `LIVEBETS_WEBHOOK_SECRET: str | None = None`

6. `.env.example` (repo root — NOT `backend/`) — append a `# Live-bets demo (v1.3, LB-A)` block with the same keys + placeholder values and a one-line comment each (`LIVEBETS_API_KEY=lbk_sandbox_...`, `LIVEBETS_DEFAULT_TABLE_ID=`, `LIVEBETS_ENABLE_WEBHOOK=false`, `LIVEBETS_WEBHOOK_SECRET=`). Placeholders only — never a real key (gitleaks-clean, mirror the existing placeholder style).

LOCKED DECISION — loss sink: losses sweep to `HOUSE_REVENUE_ACCOUNT_ID` (kind `house_revenue`), NOT `house_promo`. The design-contract table (§8) shows losses -> `house_promo`, but the CONTEXT open item says "If a distinct house P&L account exists, route losses there", and grepping `app/settlement/service.py` confirms the existing loser sweep is `market_liability -> house_revenue`. The livebets loss path mirrors settlement's loser sweep exactly: `livebets_escrow -> house_revenue`. Record this in the migration/service docstring. (This is consumed in Task 2; it is stated here because the constant choice belongs with the foundation.)
  </action>
  <verify>
    <automated>cd backend && uv run python -c "import ast,sys; ast.parse(open('alembic/versions/0011_livebets_bridge.py').read()); ast.parse(open('app/integrations/livebets/constants.py').read()); ast.parse(open('app/integrations/livebets/models.py').read()); print('parse-ok')"</automated>
    <automated>cd backend && uv run python -c "from app.core.config import Settings; s=Settings(); assert s.LIVEBETS_API_BASE=='http://localhost:8080'; assert s.LIVEBETS_ENABLE_WEBHOOK is False; print('settings-ok')"</automated>
    <automated>cd backend && uv run python scripts/lint_money_columns.py</automated>
  </verify>
  <done>Migration parses and chains off `0010_phase12_resolution_stakes` with a <=32-char revision id; `livebets_bets` DDL + `livebets_escrow` idempotent seed present and reversible; `LiveBetsBet` model uses `Mapped[Money]` for `stake` and passes the money-column lint; new `LIVEBETS_*` settings load with documented defaults; `.env.example` has the LIVEBETS block with placeholders only.</done>
</task>

<task type="auto">
  <name>Task 2: live-bets client + schemas + LiveBetsBridge service + router (mounted)</name>
  <files>backend/app/integrations/livebets/client.py, backend/app/integrations/livebets/schemas.py, backend/app/integrations/livebets/service.py, backend/app/integrations/livebets/router.py, backend/app/main.py</files>
  <action>
Build the client, the verified idempotent ledger bridge, and the player-authed router; mount it.

1. `client.py` — `LiveBetsClient`, an async httpx client mirroring `app/integrations/polymarket/client.py` (lazy `httpx.AsyncClient` singleton via `_get_client()`, bounded `httpx.Limits`, `httpx.Timeout`, `tenacity` retry on `(httpx.NetworkError, httpx.TimeoutException)` with `reraise=True`). Differences from Gamma: live-bets requires auth, so every request carries `X-API-Key` from `settings.LIVEBETS_API_KEY` (set it as a default header on the `AsyncClient`; raise a clear `RuntimeError("LIVEBETS_API_KEY is not configured")` from `_get_client()` if it is `None`). `base_url = settings.LIVEBETS_API_BASE`. Methods (verified against `live-bets/docs/INTEGRATION-GUIDE.md` §Step 2 + §Scopes):
   - `async def mint_session(self, player_ref: str, table_id: str, ttl_seconds: int | None = None) -> dict` -> `POST /v2/sessions` with JSON body `{player_ref, table_id, ttl_seconds?}` (omit `ttl_seconds` when None); returns the parsed JSON (`{session_token, expires_at}`). `raise_for_status()`.
   - `async def get_bet(self, bet_id: str) -> dict` -> `GET /v2/bets/{bet_id}`; returns parsed JSON. `raise_for_status()`. This is the server-side verification source (requires the operator key's `bets:read` scope). **Cross-phase dependency (M1):** sandbox keys are pre-scoped `bets:place`+`catalog:read` ONLY — the demo operator key MUST be issued WITH `bets:read` (provisioned in LB-C); without it live-bets returns `403 SCOPE_MISMATCH` and every `record_placed`/`record_settled` verification fails. Map a live-bets `403` from `get_bet`/`mint_session` to a clear configuration error (e.g. `RuntimeError("live-bets key missing required scope (need bets:read) — see LB-C")`), NOT a generic 500.
   - `async def list_tables(self) -> list[dict]` -> `GET /v2/catalog/tables`; returns the parsed list (`catalog:read` scope).
   - `async def close(self)` — close the underlying client (mirror Gamma's `close()`).
   - Do NOT log the API key (CONVENTIONS §8 scrubber covers `api_key`, but never pass it into a log event yourself).

2. `schemas.py` — Pydantic v2 response/request models for the ROUTER (not the raw live-bets shapes). Keep them small:
   - `SessionResponse(session_token: str, expires_at: str)`.
   - `TableItem(...)` — only the fields the demo needs (e.g. `table_id: str`, `name: str | None`); use `model_config = ConfigDict(extra="ignore")` so unknown live-bets fields are dropped (mirror the polymarket parser's dev-mode `extra="ignore"`).
   - `TablesResponse(tables: list[TableItem])`.
   - `MirrorResult(bet_id: str, status: str, applied: bool)` — the response for placed/settled (`applied=False` when the call was an idempotent no-op).
   - A small internal parser for the live-bets `GET /v2/bets/{id}` shape: parse `bet_id`, `status` (PENDING|WON|LOST|REFUNDED|VOIDED — the real enum, no `VOID`), `market_id`, `stake` (Decimal — parse from string/number, NEVER float; reuse the `_safe_decimal` idea from the polymarket parser), and the settled `payout`. OPEN-QUESTION HANDLING (see risks): the integration guide documents `potential_payout` for a PENDING bet but does not explicitly document the settled `payout` field name. Parse defensively: prefer `payout`, fall back to `potential_payout`, and treat absence on a WON bet as a verification failure (raise) rather than guessing. Centralize this so the service has one typed `VerifiedBet` to work with.

3. `service.py` — `LiveBetsBridge` with two classmethods. This is the heart of the plan. It OWNS its transaction and reuses `WalletService._post_transfer` exactly like `BetService.place_bet` and `SettlementService.resolve_market` (read both before writing this). Inject the client so tests can fake it: `record_placed(cls, session, *, user, bet_id, client)` and `record_settled(cls, session, *, user, bet_id, client)` (or accept a `LiveBetsClient`-shaped object; a Protocol is fine). Use `user.id` for the wallet and the mirror row's `user_id`.

   `record_placed(session, *, user, bet_id, client)`:
   - VERIFY FIRST (read-only, BEFORE `session.begin()` — mirrors `place_bet` validating the market before its tx): `verified = parse(await client.get_bet(bet_id))`. Assert `verified.status == LIVEBETS_PENDING`; if not, raise a domain error (`LiveBetsVerificationError`) — do NOT post. Read the authoritative `verified.stake` (never a client-supplied amount).
   - Then `async with session.begin():` (the owned unit of work):
     - Resolve the player wallet: `wallet_id = await WalletService._resolve_user_wallet_id(session, user_id=user.id)`.
     - Canonical UUID lock order (Spike 004 / Pitfall 3) on `(wallet_id, LIVEBETS_ESCROW_ACCOUNT_ID)` BEFORE posting — `sorted((a, b), key=str)`, each `select(Account.id).where(...).with_for_update()`. Copy the exact two-line lock idiom from `place_bet`.
     - Upsert the `livebets_bets` mirror row (PRIMARY guard for idempotency, analogous to the bet-status filter in settlement): use `pg_insert(LiveBetsBet).values(bet_id=..., user_id=user.id, table_id=verified.table_id, market_id=verified.market_id, stake=verified.stake, status=LIVEBETS_PENDING).on_conflict_do_nothing(index_elements=["bet_id"])` and check the rowcount / RETURNING. If the row already existed (conflict), this is a replay — return `MirrorResult(applied=False)` WITHOUT posting (no double-debit). Mirror the spirit of `_ensure_market_liability_account`'s `pg_insert ... on_conflict` but here a conflict means "already mirrored", so skip the transfer.
     - Post the debit via the sole writer: `await WalletService._post_transfer(session, kind=TRANSFER_LIVEBETS_PLACED, idempotency_key=placed_idempotency_key(bet_id), actor_user_id=user.id, debit_account_id=wallet_id, credit_account_id=LIVEBETS_ESCROW_ACCOUNT_ID, amount=verified.stake, metadata={"bet_id": str(bet_id), "table_id": str(verified.table_id) if verified.table_id else None})`.
     - SECONDARY idempotency guard: wrap the post (or the whole begin block, mirroring `recharge`) to catch `IntegrityError` with `getattr(exc.orig, "sqlstate", None) == "23505"` (the `transfers.idempotency_key` UNIQUE) and return `MirrorResult(applied=False)`. `_post_transfer` itself does NOT catch 23505 (only `recharge`/`transfer`/`grant_signup_bonus` do — read `wallet/service.py`), so the bridge MUST catch it here. Re-raise any other IntegrityError.
     - Return `MirrorResult(bet_id=str(bet_id), status=LIVEBETS_PENDING, applied=True)`.

   `record_settled(session, *, user, bet_id, client)`:
   - VERIFY FIRST (before `session.begin()`): `verified = parse(await client.get_bet(bet_id))`. Assert `verified.status in LIVEBETS_SETTLED_STATUSES` (WON/LOST/REFUNDED/VOIDED); else raise `LiveBetsVerificationError`. For WON, read the authoritative `verified.payout` (raise if absent — see schemas parser). Read the mirrored `stake` from the `livebets_bets` row (the server-side truth captured at placement) rather than trusting the client; if no mirror row exists, the settle arrived before placed — raise a domain error (the demo's placed event always precedes settled; webhook backstop is out of scope per CONTEXT).
   - PRIMARY idempotency guard: if the mirror row's `status != LIVEBETS_PENDING`, this is a replay -> return `MirrorResult(applied=False)` (mirrors settlement's "only PENDING bets settle" status filter).
   - Then `async with session.begin():`. Derive the leg specs by outcome (LOCKED ledger, mirroring `SettlementService.resolve_market`'s winner/loser legs):
     - WON: leg1 `livebets_escrow -> user_wallet` for `stake` (kind `TRANSFER_LIVEBETS_SETTLE_STAKE_RETURN`, key `livebets:{bet_id}:settled:stake`); leg2 `house_promo -> user_wallet` for `payout - stake` (kind `TRANSFER_LIVEBETS_SETTLE_WINNINGS`, key `livebets:{bet_id}:settled:winnings`) — SKIP leg2 when `payout - stake <= 0` (mirror settlement's `if sb.pnl > 0` guard so no zero-amount entry hits `CHECK (amount > 0)`).
     - LOST: one leg `livebets_escrow -> house_revenue` for `stake` (kind `TRANSFER_LIVEBETS_SETTLE_LOSS`, key `livebets:{bet_id}:settled`). LOSS SINK IS `house_revenue` (locked decision, Task 1).
     - REFUNDED or VOIDED (`verified.status in LIVEBETS_REFUND_STATUSES`): one leg `livebets_escrow -> user_wallet` for `stake` (kind `TRANSFER_LIVEBETS_VOID_REFUND`, key `livebets:{bet_id}:settled`). Both refund statuses take this same stake-return leg.
     - Lock EVERY touched account in canonical UUID order BEFORE posting (collect `{debit, credit}` across all legs, `sorted(..., key=str)`, `with_for_update()` each) — copy the `touched = {...}; for account_id in sorted(touched, key=str):` idiom from `resolve_market`.
     - Post each leg via `WalletService._post_transfer` with its per-leg key + `metadata={"bet_id": str(bet_id)}`.
     - Flip the mirror row: `status = verified.status`, `settled_at = func.now()` (within this tx).
     - SECONDARY guard: catch `IntegrityError`/23505 (per-leg keys collide on a concurrent double-settle) and return `MirrorResult(applied=False)`; re-raise others.
   - Return `MirrorResult(bet_id=str(bet_id), status=verified.status, applied=True)`.

   Define `LiveBetsVerificationError(Exception)` and any other domain errors in a small `exceptions.py` OR inline at the top of `service.py` (a sibling `exceptions.py` matches `app/bets/exceptions.py` — prefer it for the router mapping). Whichever you pick, the router imports them.

   ESCROW-NETS-TO-ZERO invariant (state in the docstring): placed credits escrow +stake; WON debits escrow -stake (winnings come from house_promo, not escrow); LOST debits escrow -stake (to house_revenue); REFUNDED/VOIDED debit escrow -stake (to wallet). So escrow returns to its prior balance across any full placed->settled cycle — exactly the per-market-liability "nets to zero" property in `app/settlement`.

4. `router.py` — `livebets_router = APIRouter(prefix="/api/live", tags=["livebets"])`, player-authed, mirroring `app/bets/router.py`. CRITICAL: do NOT add `from __future__ import annotations` (the bets/wallet routers document that FastAPI's dependency resolver mis-reads `Annotated[T, Depends(...)]` as query params under forward-ref strings on 3.13 -> 422; `User`/`AsyncSession` must be runtime imports). Use `current_active_player` from `app.auth.deps` and `get_async_session` from `app.db.session`. Provide a `get_livebets_client()` dependency returning a `LiveBetsClient` (so tests override it via `app.dependency_overrides`, mirroring `get_market_source` in the bets router). Routes:
   - `POST /session` — body `{table_id?: str}` (optional; default to `settings.LIVEBETS_DEFAULT_TABLE_ID`, 422/400 if both unset). Call `client.mint_session(player_ref=str(player.id), table_id=...)`; return `SessionResponse`. `player_ref` is the XPredict user id (design §7).
   - `GET /tables` — `client.list_tables()` -> `TablesResponse`.
   - `POST /bets/{bet_id}/placed` — `await LiveBetsBridge.record_placed(session, user=player, bet_id=bet_id, client=client)` -> `MirrorResult`. Map `LiveBetsVerificationError` -> HTTP 409 (or 422) and `NoResultFound` (no wallet) -> 404, mirroring the bets router's exception mapping. Use `bet_id: UUID` path param.
   - `POST /bets/{bet_id}/settled` — `await LiveBetsBridge.record_settled(...)` -> `MirrorResult`, same exception mapping.
   - `__all__ = ["livebets_router", "get_livebets_client"]`.

5. `app/main.py` — add `from app.integrations.livebets.router import livebets_router` to the top-level imports (next to `from app.bets.router import bets_router`) and `app.include_router(livebets_router)` alongside the other `include_router` calls (after `bets_router` is a natural spot). No other change to `main.py`.

Do NOT build `webhook.py` (CONTEXT scopes it OUT; `LIVEBETS_ENABLE_WEBHOOK` stays False). Do NOT touch any existing wallet/bets/settlement file — this plan is purely additive.
  </action>
  <verify>
    <automated>cd backend && uv run python -c "import ast; [ast.parse(open(f).read()) for f in ['app/integrations/livebets/client.py','app/integrations/livebets/schemas.py','app/integrations/livebets/service.py','app/integrations/livebets/router.py']]; print('parse-ok')"</automated>
    <automated>cd backend && uv run python -c "from app.main import app; paths={r.path for r in app.routes}; need={'/api/live/session','/api/live/tables','/api/live/bets/{bet_id}/placed','/api/live/bets/{bet_id}/settled'}; missing=need-paths; assert not missing, missing; print('routes-mounted')"</automated>
    <automated>cd backend && uv run python -c "from app.integrations.livebets.service import LiveBetsBridge; from app.integrations.livebets.client import LiveBetsClient; assert hasattr(LiveBetsBridge,'record_placed') and hasattr(LiveBetsBridge,'record_settled'); assert all(hasattr(LiveBetsClient,m) for m in ('mint_session','get_bet','list_tables')); print('contracts-ok')"</automated>
    <automated>cd backend && uv run ruff check app/integrations/livebets/</automated>
  </verify>
  <done>`LiveBetsClient` exposes `mint_session`/`get_bet`/`list_tables` with `X-API-Key` auth; `LiveBetsBridge.record_placed`/`record_settled` verify via `get_bet`, post through `WalletService._post_transfer` in one owned transaction with canonical lock order, are idempotent (mirror-row primary guard + 23505 secondary guard), and route losses to `house_revenue` / winnings from `house_promo`; the four `/api/live/*` routes are mounted under `current_active_player`; `ruff` is clean and the app imports without error.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser/frontend -> XPredict `/api/live/*` | Player-authenticated but the request body/path (`bet_id`, `table_id`) is untrusted; the player could replay or forge a `bet_id`. |
| XPredict backend -> live-bets `:8080` | Outbound, authenticated with the operator `X-API-Key`; live-bets is the authority for bet status/stake/payout. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-LBA-01 | Spoofing/Tampering | `POST /api/live/bets/{bet_id}/placed` client-supplied amount | mitigate | Bridge NEVER trusts a client amount — it reads stake/status from live-bets `GET /v2/bets/{id}` before posting (server-side verification, SC#5). A status mismatch raises without posting. |
| T-LBA-02 | Tampering (double-spend) | replayed placed/settled event | mitigate | Two-layer idempotency: `livebets_bets.status` primary guard + UNIQUE `transfers.idempotency_key` (`livebets:{bet_id}:placed` / `:settled[:leg]`) catching 23505 -> no-op. Escrow nets to zero across a full cycle. |
| T-LBA-03 | Elevation of privilege | unauthenticated access to `/api/live/*` | mitigate | Every route depends on `current_active_player` (401 unauthenticated, 403 unverified) — same gate as the bets surface. |
| T-LBA-04 | Information disclosure | operator `X-API-Key` leaking to logs/client | mitigate | Key lives server-side in `Settings` only, never sent to the browser, never passed into a structlog event (CONVENTIONS §8 scrubber covers `api_key`). |
| T-LBA-05 | Denial of service | live-bets slow/unreachable | accept | Demo-grade: bounded httpx timeout + tenacity retry (mirrors Gamma client); a hard outage surfaces as a 5xx to the player. No DLQ/circuit-breaker (non-goal §2). |
| T-LBA-SC | Tampering | npm/pip/cargo installs | mitigate | No new third-party packages are installed by this plan (httpx, tenacity, pydantic, sqlalchemy, alembic, fastapi-users are already in `pyproject.toml`). No package-legitimacy checkpoint required. |
</threat_model>

<verification>
- Module imports cleanly: `cd backend && uv run python -c "import app.integrations.livebets.client, app.integrations.livebets.service, app.integrations.livebets.router, app.integrations.livebets.models, app.integrations.livebets.constants"`.
- App boots with routes mounted (route-presence assertion in Task 2 verify).
- Migration chains correctly and is the new head: `cd backend && uv run alembic heads` shows `0011_livebets_bridge`; `uv run alembic history | head` shows it chained off `0010_phase12_resolution_stakes`. (Container/Docker-applied up/down is exercised by the LB-A-02 migration test.)
- No new third-party dependency added (`git diff --stat backend/pyproject.toml backend/uv.lock` is empty).
- No existing wallet/bets/settlement source file modified (`git diff --name-only` lists only the files in `files_modified`).
- Money-column lint green (Task 1 verify) and `ruff` clean (Task 2 verify).
</verification>

<success_criteria>
- Additive Alembic migration creates the `livebets_escrow` system singleton (fixed UUID, idempotent seed) + `livebets_bets` mirror table, reversible, with zero behavior change to existing tables (LB-A-SC2).
- `backend/app/integrations/livebets/` exists with `client.py`, `schemas.py`, `models.py`, `constants.py`, `service.py`, `router.py`, `__init__.py`; the four `/api/live/*` routes are mounted under `current_active_player` (LB-A-SC1).
- `record_placed`/`record_settled` post the exact locked ledger flows (placed: `user_wallet->livebets_escrow`; WON: `escrow->wallet` stake + `house_promo->wallet` payout-stake; LOST: `escrow->house_revenue` stake; REFUNDED/VOIDED: `escrow->wallet` stake) via `WalletService._post_transfer` in one owned transaction with canonical UUID lock order (LB-A-SC3).
- The bridge is idempotent (mirror-row + `transfers.idempotency_key` 23505) and escrow nets to zero (LB-A-SC4); it is server-side-verified via `get_bet` and rejects status/stake mismatches without posting (LB-A-SC5).
- Config + `.env.example` carry `LIVEBETS_API_BASE`, `LIVEBETS_API_KEY`, `LIVEBETS_DEFAULT_TABLE_ID`, `LIVEBETS_ENABLE_WEBHOOK=false`, `LIVEBETS_WEBHOOK_SECRET`.
</success_criteria>

<output>
Create `.planning/phases/LB-A-backend-bridge/LB-A-01-SUMMARY.md` when done.
</output>
