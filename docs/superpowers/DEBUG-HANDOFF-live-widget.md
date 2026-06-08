# DEBUG HANDOFF — live-bets widget stuck "connecting…" + can't bet

**Date:** 2026-06-08 · **For:** a fresh session (clear context) to debug with subagents.
**Read first**, then open DevTools per **STEP 1**.

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
