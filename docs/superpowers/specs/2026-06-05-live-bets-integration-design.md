# Live-bets ↔ XPredict integration — Design (demo)

- **Date:** 2026-06-05
- **Status:** Approved design — ready for implementation planning
- **Scope:** **Demo only.** Play-money, single-tenant, local. No real money, no production hardening.
- **Author:** Pol (PM/Tech Lead) + Claude (brainstorming)
- **Worktree / branch:** `xpredict-livebets` / `gsd/livebets-demo` (off `main`) — isolated from Agus's in-flight v1.2 work.

---

## 1. Context

Two existing projects, both play-money, both Python/FastAPI:

- **XPredict** (`ProyectosClaude/xpredict`) — white-label prediction-market platform. FastAPI + SQLAlchemy 2.0 async + Postgres 16 + Redis + Celery; Next.js 15 player/admin UI. Has its own **double-entry ledger** (`app/wallet`), bets/settlement, and a `app/integrations/polymarket` integration as a pattern to copy. Backend `:8000`, frontend `:3000`.
- **Live-bets** (`ProyectosClaude/live-bets`) — B2B betting API. Multi-player vehicle-traffic betting on pre-recorded clips, **HLS-synchronised tables** (everyone watches the same clip, bets in the same round window). FastAPI + asyncpg + Postgres 15 + Redis 7. **Stateless cashflow — never touches operator money**; it is designed to be embedded by an *operator* via API keys + webhooks + an embeddable widget. App `:8000` by default.

Live-bets is explicitly built for exactly this: an operator (XPredict) mints a per-player session token, embeds the `<live-bets-table>` web component, and mirrors settlement back into its own ledger.

## 2. Goal & non-goals

**Goal:** An authenticated XPredict player opens a new route **`/live`**, sees the real live-bets multi-player table embedded (HLS sync + round timer), places a bet, and **their single XPredict wallet balance is debited on placement and credited on win** — one balance, no real money. XPredict acts as the live-bets **operator**.

**Non-goals (this is a demo):** real money / PSP, OAuth `client_credentials`, OTEL passthrough, production webhook hardening (HTTPS/DLQ), bulletproof cross-DB reconciliation, a multi-table lobby / live-bets catalog browse, production CORS/CSP.

## 3. Key decisions (locked)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Money/identity | **Unified wallet** | One balance in XPredict; XPredict is operator and mirrors money. Most convincing white-label demo ("same login, same balance, another product inside"). |
| 2 | Betting surface | **Embed the widget** `<live-bets-table>` in a new XPredict route, wrapped in XPredict chrome | Brings the real-time multi-player HLS experience for free; minimal frontend; faithful to the product. |
| 3 | Money-sync approach | **A — Mirror by events** (DOM-event-driven, server-side verified, idempotent) | live-bets is authoritative for the game; XPredict mirrors. Uses the widget as-is; no widget fork; demo-grade integrity via idempotent transfers. |

## 4. Architecture / topology

Two services running side by side, XPredict = operator.

```
Browser
  └─ XPredict frontend :3000  ──/api/live/*──►  XPredict backend :8000 ──HTTP (X-API-Key)──► live-bets API :8080
        │  <live-bets-table>                          │  mint session, verify bet,            │  /v2/sessions, /v2/bets,
        │  widget.js (live-bets origin)               │  mirror ledger                        │  /v2/catalog, /v2/bets/{id},
        └────── widget → /v2/bets, HLS, WS ───────────┴──── HLS /stream, WS /ws ──────────────┘  HLS, rounds orchestrator
```

- **Port remap:** live-bets API moves to `:8080` (its Postgres/Redis to free ports) to avoid the `:8000` clash with XPredict backend. XPredict stays `:8000`/`:3000`.
- **Widget served locally:** `<script src="http://localhost:8080/static/widget.js">` (no jsDelivr, drop SRI `integrity` in dev).
- **CORS:** live-bets must allow origin `http://localhost:3000` (widget posts bets, pulls HLS, opens WS cross-origin from the XPredict page).

## 5. Integration contract (live-bets operator plane — verified against `docs/INTEGRATION-GUIDE.md`)

**Operator endpoints XPredict backend calls (auth: `X-API-Key: lbk_...`):**

- `POST /v2/sessions` — body `{player_ref, table_id, ttl_seconds?}` → `{session_token (JWT, 1h default), expires_at}`. `player_ref` is opaque to live-bets (≤128 chars) → we pass the XPredict user id.
- `GET /v2/catalog/tables` (scope `catalog:read`) — list tables.
- `GET /v2/bets/{id}` (scope `bets:read`) — **server-side verification** of a bet's status/stake/payout before moving the ledger. Returns `{bet_id, status: PENDING|WON|LOST|REFUNDED|VOIDED, market_id, side, stake, odds, potential_payout, ...}`.
- *(optional backstop)* `PUT /admin/operators/{op_id}/webhook` (scope `webhooks:manage`) — register `{url, signing_kid, status:ACTIVE}`. Webhook events: `bet.settled` / `bet.voided` / `bet.refunded` (**no `bet.placed` webhook exists**). Signing = Svix-style HMAC-SHA256 headers `webhook-id` / `webhook-timestamp` / `webhook-signature` (`v1,<base64(hmac)>`), reject if `|now − ts| > 300s`, dedupe by `webhook-id`.

**Widget (placed by the frontend; the widget itself calls `POST /v2/bets` with the session token):**

- Element: `<live-bets-table session-token="..." table-id="...">`.
- DOM events the XPredict page listens to:
  - `live-bets-bet-placed` → **debit trigger** (no webhook equivalent exists).
  - `live-bets-result` `{bet_id, status: WON|LOST, payout}` → **credit/settle trigger**.
  - `live-bets-session-expired` → renew the session token via the backend.
  - `live-bets-error` → surface a non-silent error.

Market types (for reference): `over_under` (`over`/`under`), `between` (`yes`/`no`), `exact_count` (`yes`/`no`).

## 6. New components (all additive; copy existing patterns)

### Backend — `backend/app/integrations/livebets/` (sibling of `polymarket/`)
- `client.py` — httpx client to live-bets: `mint_session(player_ref, table_id)`, `get_bet(bet_id)`, `list_tables()`. Operator API key + base URL from settings.
- `service.py` — `LiveBetsBridge`:
  - `record_placed(user, bet_id)` → `get_bet` (assert PENDING + read stake) → post the debit transfer. Idempotent.
  - `record_settled(user, bet_id)` → `get_bet` (assert WON/LOST/REFUNDED/VOIDED + read payout) → post the credit/loss/refund transfer. Idempotent.
  - Reuses `WalletService._post_transfer` (the sole double-entry writer, WAL-07) inside a single owned transaction, exactly like `app/bets/service.py` and `app/settlement/service.py` do.
- `router.py` — FastAPI routes consumed by the frontend (auth: existing player session):
  - `POST /api/live/session` → mint/renew a live-bets session for the current player.
  - `GET  /api/live/tables` → table(s) for the demo.
  - `POST /api/live/bets/{bet_id}/placed` → `LiveBetsBridge.record_placed`.
  - `POST /api/live/bets/{bet_id}/settled` → `LiveBetsBridge.record_settled`.
- `webhook.py` *(optional, default OFF)* — `POST /webhooks/live-bets`: verify HMAC, call the same `record_settled`. Backstop for missed DOM events.
- **Migration (additive):**
  - System singleton account `livebets_escrow` (mirrors the per-market liability pattern; `owner_type=system`, `kind=livebets_escrow`, `currency=PLAY_USD`).
  - Mirror table `livebets_bets(bet_id PK, user_id, table_id, market_id, stake, status, created_at, settled_at)` — lets the settled handler resolve the owning user and stake without trusting the client.
- **Config (`app/core` settings + `.env.local`):** `LIVEBETS_API_BASE` (`http://localhost:8080`), `LIVEBETS_API_KEY`, `LIVEBETS_DEFAULT_TABLE_ID`, `LIVEBETS_WEBHOOK_SECRET` (only if webhook enabled), `LIVEBETS_ENABLE_WEBHOOK=false`.

### Frontend — `frontend/src/app/live/`
- `page.tsx` (server component) — fetch session token + table id from `POST /api/live/session`, render chrome (header/nav + **XPredict wallet balance**).
- `live-table.tsx` (client component) — load `widget.js`, render `<live-bets-table>`, wire DOM events → call the backend via `src/lib/api.ts`:
  - `live-bets-bet-placed` → `POST /api/live/bets/{id}/placed`, then refresh wallet balance.
  - `live-bets-result` → `POST /api/live/bets/{id}/settled`, then refresh wallet balance + toast WON/LOST.
  - `live-bets-session-expired` → `POST /api/live/session`, set new `session-token` attribute.
  - `live-bets-error` → non-silent error UI.
- Add a **"Live"** entry to the header nav.

## 7. Identity / session flow

1. Player opens `/live` (already authenticated in XPredict).
2. XPredict backend → `POST /v2/sessions` with `player_ref = <xpredict user id>` + `table_id`. Returns `session_token`.
3. Frontend renders the widget with that token. On `live-bets-session-expired`, renew via the backend.

## 8. Money flow (ledger mirror — Approach A)

Event-driven, **verified server-side** against live-bets, **idempotent** by `bet_id`. Mirrors XPredict's existing house-market escrow model (`app/bets` + `app/settlement`).

| Moment | DOM event | Backend verifies (`GET /v2/bets/{id}`) | Ledger transfer (double-entry) | `idempotency_key` |
|--------|-----------|----------------------------------------|--------------------------------|-------------------|
| Bet accepted | `live-bets-bet-placed` | status PENDING, read `stake` | `user_wallet → livebets_escrow` (stake) | `livebets:{bet_id}:placed` |
| Win | `live-bets-result {WON, payout}` | status WON, read `payout` | `livebets_escrow → user_wallet` (stake) **+** `house_promo → user_wallet` (payout − stake) | `livebets:{bet_id}:settled` |
| Loss | `live-bets-result {LOST}` | status LOST | `livebets_escrow → house_revenue` (stake) | `livebets:{bet_id}:settled` |
| Refund / void | webhook / reconcile | status REFUNDED/VOIDED | `livebets_escrow → user_wallet` (stake) | `livebets:{bet_id}:settled` |

- The player only ever sees the **XPredict** balance; the live-bets internal paper balance is pre-funded generously and is decorative.
- **Idempotency:** the `idempotency_key` on `Transfer` makes the DOM event and the optional `bet.settled` webhook converge without ever double-posting (the two-leg WON settle uses distinct `:settled:stake` / `:settled:winnings` keys). Winnings are funded from `house_promo`, and losses sweep to `house_revenue` — exactly as house-market settlement does (so the escrow account nets to zero across placed→settled). **Note:** live-bets' real `BetStatus` enum is `PENDING|WON|LOST|REFUNDED|VOIDED` (there is no `VOID`); both `REFUNDED` and `VOIDED` take the stake-return leg.
- **Demo-grade caveat (documented):** placement debit is triggered by a client DOM event; the server *verifies* against live-bets before posting, but a controlled demo does not need cross-DB two-phase guarantees. The optional webhook/`GET /events?since=` reconcile closes the "player closed the tab mid-round" gap.

## 9. live-bets demo setup (prerequisites)

- Create an operator + API key with scopes `catalog:read` + `bets:read` (+ `webhooks:manage` only if the webhook backstop is enabled). Locally we control the live-bets admin, so this is a seed/admin step.
- `ingest-batch` a set of clips and run the orchestrator (`run-orchestrator`) so **one table** has live rounds. Its `table_id` → `LIVEBETS_DEFAULT_TABLE_ID`.
- Pre-fund the live-bets internal user mapped to the `player_ref` (admin top-up) so live-bets never rejects a bet for insufficient internal balance.
- Remap ports, enable CORS for `:3000`, serve `widget.js` from the local static.

## 10. Coordination with Agus / where the work lives

- Treated as a new milestone (e.g. **`v1.3 Live-Bets demo`**), **purely additive**: new `app/integrations/livebets/`, new migration, new `frontend/src/app/live/` route, one nav entry. **Does not touch** `markets` / `catalog` / `settlement` or any v1.2 file Agus is executing.
- Developed in a **separate git worktree** (`xpredict-livebets`, branch `gsd/livebets-demo`, off `main`) so it is fully isolated from Agus's `gsd/phase-14-…` working tree.
- **Do not** mutate `.planning/ROADMAP.md` programmatically (known GSD Windows CRLF truncation bug). If a milestone entry is wanted, edit it by hand and verify.

## 11. Testing (demo-grade)

- **Backend unit:** `LiveBetsBridge` idempotency with a faked live-bets client — `placed→won` and `placed→lost` post the correct double-entry; duplicate DOM/webhook events are no-ops; `livebets_escrow` nets to zero across a full placed→settled cycle.
- **Frontend:** light component test that each DOM event triggers the right backend call (mocked).
- **E2E:** a **manual demo script** (place a bet → win → watch the XPredict balance move). Full automated multi-player/HLS E2E is out of scope for the demo.

## 12. Open questions (verify during planning)

1. Does `POST /v2/sessions` auto-provision the internal live-bets user for a new `player_ref` (and with what initial balance), or must we create/top-up it ourselves first?
2. Webhook backstop for the demo: **default OFF** (DOM events + server-side verification only). Enable only if we want robustness against a closed tab mid-round.
3. Exact session scope required by `POST /v2/sessions` (confirm the operator key carries it).

## 13. Rough phase breakdown (seeds GSD planning — not binding)

1. **Backend bridge** — `livebets` module (client + `LiveBetsBridge` + router), migration (escrow account + `livebets_bets`), config; backend unit tests.
2. **Frontend surface** — `/live` route + `live-table.tsx` widget wiring + nav entry; component test.
3. **Demo harness** — live-bets local stack (port remap, CORS, operator key, ingest clips, run orchestrator, pre-fund) + end-to-end manual demo script.
