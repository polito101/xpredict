# DEBUG HANDOFF — live-bets widget stuck "connecting…" + can't bet

**Date:** 2026-06-08 · **For:** a fresh session (clear context) to debug with subagents.
**Read first**, then open DevTools per **STEP 1**.

---

## ✅ RESOLVED — 2026-06-08 (root cause was NOT membership)

**Root cause = auth-routing MISROUTE in `live-bets/live_bets/api/ws.py` (~L120).** The `/ws`
gateway verified the **legacy** player JWT (`verify_token`) **before** the **session** JWT
(`verify_session_token`). `verify_token` accepts ANY UUID-shaped `sub`, and the bridge mints
session tokens whose `sub` (player_ref) is the XPredict user UUID (e.g. `dbc14fc0-…`). So the
session token was wrongly accepted by `verify_token` → took the **legacy branch** →
`is_member(table, that_uuid)` → **False** (operator player_refs can never be rows in
`live_bets.users` — FK; INSERT is impossible by design) → `websocket.close(4403)` **BEFORE
`accept()`**. A pre-accept close in ASGI/uvicorn is emitted as an **HTTP 403 handshake
rejection**, not a WS close frame → the browser sees close code **1006** and the widget loops
on "connecting…". The widget's `if (e.code===4401)` branch never fires. **The PRIME HYPOTHESIS
(4403 = not a member, seed membership) was WRONG** — membership is correctly *skipped* for
session tokens once the session branch is reached ("the JWT IS the proof"); the bug was that
the session branch was never reached.

**Why HLS worked but WS didn't:** `/stream/*` and `POST /v2/bets` auth via
`get_session_or_operator` (operators/auth.py), which branches on token **prefix** (`eyJ` →
`verify_session_token` FIRST) and skips `is_member`. `/ws` reimplemented auth inline with the
opposite order. Caddy was fully EXONERATED (direct-to-livebets reproduced the identical 403).

**Fix (1 file):** reorder `ws.py` to try `verify_session_token` FIRST, legacy `verify_token` as
fallback. Safe because a legacy token lacks the `table_id` claim → `verify_session_token`
KeyErrors → `None` → falls through to the legacy branch unchanged. Committed on live-bets branch
`fix/ws-session-jwt-first` (commit `8bcd789`) + regression test
`tests/integration/test_ws_session_auth.py::test_ws_session_jwt_uuid_player_ref_takes_session_path`
(the old tests used a non-UUID player_ref so never caught this).

**Verified live on the VM:** after rebuild+recreate of the `livebets` container, the direct-to-
livebets AND through-Caddy `/ws` handshakes both return **`101 Switching Protocols`** and emit
`subscription_ready`/`pdt_anchor`/`hello`. A `BETTING_OPEN` round is live on bangkok so bet
options appear; `/v2/bets` was confirmed (subagent sweep) to NOT share the misroute.

**Remaining:** (1) browser confirm at `app.xprediction.online/live`; (2) merge/PR
`fix/ws-session-jwt-first` into live-bets master + fold into the VM-deploy branch
`gsd/live-bets-vm-deploy`; (3) optional hardening — make `verify_token`/`get_current_user_id`
reject tokens carrying `table_id`/`scope` claims so session tokens can't masquerade on legacy
REST routes; (4) extract a shared session-decode helper so `/ws` and `get_session_or_operator`
can't drift again. **Rollback** if needed: VM has `/tmp/ws.py.vm-orig`; restore + rebuild.

*Everything below is the original (pre-fix) handoff, kept for history.*

---

## Symptom (reproducible)
On `https://app.xprediction.online/live` logged in as a demo player: the **real Bangkok
traffic video plays** (HLS, with the red detection line), BUT the widget is stuck on
**"connecting…"** and **no bet options appear / can't bet**.

## What WORKS (ruled out — don't re-litigate)
- **F1 bridge + money path (server-side, PROVEN):** `POST /api/live/session` → 200 `{session_token, table_id}`; placed/settled mirror debits/credits the XPredict wallet (verified live on the demo table: 867.73→857.73 then settle).
- **F2 HLS video:** `master.m3u8`/`media.m3u8` + `seg-*.m4s` served; **video plays in the browser**.
- **Caddy same-origin proxy on `app.`** for the widget's relative paths — VERIFIED: `app./time`→200, `app./stream/{tid}/master.m3u8`+Bearer→playlist, `app./v2/bets`→401 (from live-bets, not a frontend 404), `app./`→200, `app./live`→307. So `/ws /stream/* /v2/* /time` reach `livebets:8000` same-origin (no CORS).
- **Video element fix:** `<video slot="video">` added to the host (`live-table.tsx`) — the earlier `'<video slot="video"> missing'` is gone.

## THE BUG = the WebSocket (round state)
The widget shows "connecting" until the **WS** (`/ws`) delivers round state; the betting
options come from the round pushed over the WS. No round state → "connecting" + nothing to bet.

- Widget connects to `/ws?token=<session_token>` — `live-bets/live_bets/static/widget.js:~635-640`. Now proxied `app.`→`livebets` (same matcher as `/time`, which works).
- **live-bets `ws.py` PRE-ACCEPT GATES** (`live-bets/live_bets/api/ws.py`, ~L101-180), in order:
  1. `token: str = Query(...)` → `verify_token` / `verify_session_token` → **close 4401** on failure.
  2. **`TablesRepo.is_member`** membership check → **close 4403** on failure.
  3. rate limit → **close 4429**. Then `accept()` → `subscription_ready` frame → round "hello" frame.

### PRIME HYPOTHESIS
**The WS closes with 4403 — the bridge-minted session is NOT a "member" of the bangkok table.**
Rationale: the SAME token works for HLS (it streamed), so 4401 (bad token) is unlikely; and
**membership is checked for the WS but NOT for HLS** — that asymmetry exactly explains "video
works, WS doesn't". (F1 never tested the widget in-browser, so this was latent.)

Secondary: 4401 (token kind), WS not upgrading through Caddy, or round-state not broadcasting.

## STEP 1 — do this FIRST (pinpoints it in 30s)
Open DevTools → **Network → WS** → the `/ws?token=…` row → check the **close code**:
- **4403 = not a member** → see Thread A (the likely fix).
- **4401 = token** → Thread B. · **4429** = rate limit. · **4500** = server error (check live-bets logs at that timestamp). · **4408** = hard boot.
- Also read **Console** for the `live-bets-error` detail and any WS error.
- Confirm whether the WS even reaches 101 (upgraded) or fails earlier (Caddy/proxy).

## Investigation threads (good for parallel subagents)
**A. Membership (top suspect).** In `live-bets`: `TablesRepo.is_member` (`repositories/tables.py`?) + the `*member*` table/schema + **how a player becomes a member** (on `POST /v2/sessions`? on first bet? seeded?). Does the new **bangkok** table need member rows? Did the (synthetic) demo table get them some other way? If membership must be seeded/created, either (a) the bridge's session-mint must register membership, or (b) seed membership for the table, or (c) the WS gate is too strict for this embed model.
**B. The bridge session.** Does `xpredict` `POST /api/live/session` (→ live-bets `POST /v2/sessions`, see `xpredict/backend/app/integrations/livebets/client.py` + `service.py`/`router.py`) establish membership / the right token kind for the WS? Compare the token claims the WS expects (`verify_session_token`) vs what the bridge mints.
**C. WS through Caddy.** Confirm the `/ws` upgrade proxies (app.→livebets). A raw WS test: `wscat`/python-websockets to `wss://app.xprediction.online/ws?token=<TOK>` and observe the close code (this isolates Caddy vs live-bets).
**D. Round delivery.** After `accept()`, does the **bangkok** round push to the WS (bus subscribe + the round "hello")? Is a round actually OPEN on f90e010d at test time?

## Access & key facts
- **VM:** `ssh -i ~/.ssh/xpredict_demo_ed25519 ubuntu@82.70.90.222` (STATIC IP). Repos: `~/xpredict` (branch `gsd/live-bets-vm-deploy`), `~/live-bets` (source, NO .git — git source is `C:\Users\pobom\ProyectosClaude\live-bets` on `master`).
- **Ops:** `cd ~/xpredict; C="docker compose --env-file .env.prod -f docker-compose.prod.yml"`. DB: `$C exec -T livebets-db psql -U live_bets -d live_bets -c "…" </dev/null`.
- **Bangkok table:** `f90e010d-4540-42d2-8c7f-bade3543fe3e` (ACTIVE, source `bangkok-soi11`, 6 real clips, live=30s). Demo table `c4138d9f-…` PAUSED. `LIVEBETS_DEFAULT_TABLE_ID`=bangkok in `.env.prod`.
- **Demo player:** `demo-user-02@demo.xpredict` / `Demo-Player-Pass-1!` (01 used in F1 tests).
- **Repro a session (server-side):** `POST https://api.xprediction.online/auth/login` (form username/password) → cookie; `POST .../api/live/session` {} → `{session_token, table_id, expires_at}`. The `session_token` is what the widget puts in `?token=`.
- live-bets operator key in `~/xpredict/.env.prod` `LIVEBETS_API_KEY`; admin pw `~/.livebets-admin-pw.txt`.

## Files
- WS server: `live-bets/live_bets/api/ws.py` (the 4401/4403/4429 gates).
- Widget: `live-bets/live_bets/static/widget.js` (WS ~635, HLS ~580, status/`_emitError` ~520-535; `observedAttributes` = session-token/table-id/theme only — **no configurable API base**, assumes same-origin).
- Membership repo: `live-bets/live_bets/repositories/tables.py` (look for `is_member`).
- Sessions route: `live-bets/live_bets/api/routes/` (sessions) + `live-bets/live_bets/auth.py` (`verify_session_token`).
- Bridge (xpredict): `backend/app/integrations/livebets/{client,service,router}.py`; host: `frontend/src/app/live/live-table.tsx`; page: `frontend/src/app/live/page.tsx`.
- Caddy: `xpredict/deploy/Caddyfile` (`@livebets` app-proxy). Compose: `xpredict/docker-compose.prod.yml`.

## Gotchas (carried — will bite again)
- **`docker compose exec -T …` EATS the surrounding heredoc stdin** → ALWAYS add `</dev/null` (or `< file.sql`).
- **`caddy reload` did NOT apply config changes here** → use `$C up -d --force-recreate caddy`.
- argon2 `LIVE_BETS_ADMIN_PASSWORD` in `.env.prod` needs `$`→`$$` (compose interpolates env-file values).
- The widget uses RELATIVE URLs (same-origin assumption) — that's why its paths are proxied on `app.`.
- Detector (YOLO) is offline-only; the vehicle count is decoupled from the video (`clips.result.total` → round → settlement).

## Suggested first move
Spawn subagents on Threads A + B + C in parallel after STEP 1 gives the close code. If 4403:
A is the fix path (membership). The whole live-bets↔xpredict context is in memory `livebets-xpredict-integration` + spec `docs/superpowers/specs/2026-06-07-live-bets-vm-deploy-design.md`.
