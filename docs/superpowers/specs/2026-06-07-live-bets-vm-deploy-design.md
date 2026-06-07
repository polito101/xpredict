# Design — live-bets co-located on the XPredict OCI VM (always-on, HLS demo)

**Date:** 2026-06-07
**Author:** Pol + Claude
**Status:** DRAFT — pending Pol's review
**Related:** `2026-06-05-live-bets-integration-design.md` (the LB-A/B/C integration), `DEMO-RUNBOOK-live-bets.md` (the LOCAL demo), memory `xprediction-demo-oracle-deploy`, `livebets-xpredict-integration`, `live-bets-staging-deploy`.

## Problem

XPredict's live sales demo runs 24/7 on an Oracle Cloud VM (`app.xprediction.online`, `docker-compose.prod.yml`). The `/live` page shows **"No live table configured yet"** because no live-bets backend/table is wired into that environment — the integration code is merged, but the live-bets *service* + its config aren't deployed there. The only running live-bets is the **Render staging** instance, which has a **~40s free-tier cold start** — unacceptable for a live sales meeting.

## Goal

live-bets runs **on the same VM** as XPredict, behind the same Caddy (own TLS subdomain), with **zero cold start** and no Render dependency. A logged-in demo player on `app.xprediction.online/live` bets on a live-bets table and their **XPredict wallet reacts** to every bet. Real **HLS traffic video** in the widget, delivered in a second phase so a video issue can never block the core demo.

## Locked decisions (from discussion 2026-06-07)

| # | Decision | Choice |
|---|---|---|
| 1 | Video | **Real HLS**, but **phased**: F1 betting-UI live + solid, F2 video on top |
| 2 | live-bets CORS branch | **Cherry-pick** `c379ef8` onto `master` (branch diverged, not FF) |
| 3 | Ephemeral IP | **Reserve a static OCI public IP**, re-point all 3 A-records once |
| 4 | Code → VM | **Push live-bets `master` to origin** (accepts Render staging auto-redeploy); VM builds from GitHub |

## Target architecture

```
                         Caddy (auto-TLS, deploy/Caddyfile)
  app.xprediction.online  ─►  frontend:3000
  api.xprediction.online  ─►  backend:8000  ──(internal docker net)──►  livebets:8000
  live.xprediction.online ─►  livebets:8000  ◄──(browser: widget.js + /v2 API + /ws + /stream HLS)
                                   │
                          livebets-db (Postgres, vol)   livebets-redis
                          clips volume (persistent)   ·   hls_out volume
```

**Why this shape (verified against the code):**
- live-bets serves API + WS + HLS `/stream/{table}/*.m3u8|*.m4s` all on **one port (8000)** → a single `reverse_proxy livebets:8000` covers everything; no separate static/HLS server.
- HLS ffmpeg runs `-c copy -an` (**remux to fMP4, no transcode**) → ~zero CPU per table; fine on 1 OCPU.
- Backend↔live-bets stays **server-side on the internal docker network** (`http://livebets:8000`); the operator API key never leaves the box.
- Browser↔live-bets is **cross-origin** (`app.` → `live.`): needs `LIVE_BETS_CORS_ORIGINS` for the JSON/WS calls. (HLS routes already emit `Access-Control-Allow-Origin: *` unconditionally.)
- live-bets gets its **own Postgres + Redis** (isolated from XPredict's), matching how its compose is structured.

## Components & changes by repo

### A. `xpredict` repo (the bulk; committed, reproducible)
1. **`docker-compose.prod.yml`** — add 3 services on the existing network: `livebets`, `livebets-db` (postgres:15-alpine + `livebets_pgdata` vol), `livebets-redis` (redis:7-alpine). The `livebets` service:
   - image built from the live-bets repo (pinned), `restart: unless-stopped`, no host ports.
   - F1 command: default (`migrate && serve-all … --no-hls --bus in-memory`).
   - F2 command override: `… serve-all --host 0.0.0.0 --port 8000 --bus in-memory --hls --hls-out /app/var/hls`.
   - env: `LIVE_BETS_ENV=prod`, `LIVE_BETS_SERVER_KEY` (real ≥32B), `LIVE_BETS_SERVER_KEY_ID`, `LIVE_BETS_ADMIN_PASSWORD` (argon2id), `LIVE_BETS_CORS_ORIGINS=https://app.xprediction.online`, `DATABASE_URL`→livebets-db, `REDIS_URL`→livebets-redis.
   - F2 volumes: `livebets_clips:/var/lib/live-bets/clips`, `livebets_hls:/app/var/hls`.
2. **`x-backend-env` anchor** — add the 4 passthroughs the backend is missing today: `LIVEBETS_API_BASE` (`http://livebets:8000`), `LIVEBETS_API_KEY`, `LIVEBETS_DEFAULT_TABLE_ID`, `LIVEBETS_ENABLE_WEBHOOK=false`.
3. **`deploy/Caddyfile`** — add `{$LIVEBETS_DOMAIN} { encode zstd gzip; reverse_proxy livebets:8000 }`; pass `LIVEBETS_DOMAIN` to the caddy service.
4. **`.env.prod.example`** — document the new vars (`LIVEBETS_DOMAIN`, `LIVEBETS_API_KEY`, `LIVEBETS_DEFAULT_TABLE_ID`, `LIVE_BETS_SERVER_KEY*`, `LIVE_BETS_ADMIN_PASSWORD`) and set `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC=https://live.xprediction.online/static/widget.js`.
5. **Frontend rebuild** — `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` is baked at build time, so the widget src requires `$C build frontend` + re-up.
6. **Runbook** — extend `DEMO-RUNBOOK-live-bets.md` (or a new `deploy-live-bets-vm.md`) with the VM steps.

### B. `live-bets` repo
1. `git cherry-pick c379ef8` (env-gated CORS, touches `live_bets/api/app.py` + `tests/unit/test_dev_cors.py`) onto `master`; run `tests/unit/test_dev_cors.py` (4).
2. `git push origin master` (28 local commits + the cherry-pick). **Side effect: Render staging auto-redeploys** — expected.

### C. DNS / OCI (Pol's console steps, I provide exact instructions)
1. Reserve a **static public IP** on the OCI instance (replace the ephemeral one).
2. Namecheap A-records → static IP for `app`, `api`, **and new `live`**.

## Phase 1 — betting-UI live on the VM (proven money path, public + TLS)

**Deliverable:** on `https://app.xprediction.online/live`, a logged-in demo player sees the live-bets widget (not the empty state), bets on an open round, and the XPredict wallet **debits on placed / credits on settle**. No video yet (`--no-hls`).

> **Honesty note:** the money path was proven **server-side only** (runbook §0.7: real `record_placed`, wallet 500→490). The **browser walk** (§D: widget → DOM `bet-placed`/`settled` events → mirror → balance moves in the island) was **never run** — F1 is the **first real in-browser E2E**. Budget for first-run surprises in the widget↔backend event wiring.

**Steps:** static IP + `live` A-record → cherry-pick+push CORS → build live-bets image on VM → bring up `livebets`/`-db`/`-redis` with real secrets + CORS → seed an **ACTIVE table** + mint a **full-scope `bootstrap-admin-key`** → write `.env.prod` (`LIVEBETS_API_BASE/KEY/DEFAULT_TABLE_ID`, widget src) → add backend passthroughs + Caddy vhost → rebuild frontend → `up -d`.

**Verify (browser, real):** player login → `/live` renders the widget → round enters BETTING → place bet → wallet drops by stake → settle credits/clears. Cross-check the `livebets_placed` ledger transfer + mirror row. Zero cold start.

## Phase 2 — real HLS video

**Deliverable:** the widget shows live traffic video synced to rounds, over TLS from `live.xprediction.online`, CORS-clean.

**Steps:** override the `livebets` command to `--hls --hls-out /app/var/hls` → verify the image's **ffmpeg ≠ 5.1.4** → place real **H.264, no-audio** clips on the `livebets_clips` volume at stable paths (start with the repo's `var/clip.mp4`/`sample.mp4`/`uat_clip.mp4`; `ffprobe`-verify codec) → **detector-free seed** of `clips` rows + `bucket_membership` pointing at the real files (the prod image has no CV detector, and the old synthetic seed uses `path=/dev/null` which ffmpeg can't read) → ensure the ACTIVE table's buckets reference real clips → re-up.

**Verify:** during a LIVE round, `master.m3u8` + `seg-*.m4s` appear under `var/hls/{table_id}/`; `GET https://live.xprediction.online/stream/{table}/master.m3u8` → 200 w/ CORS; the widget plays moving video in the browser. (Do **not** trust `/ready` `hls:ok` — that probe is a no-op.)

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| ffmpeg **5.1.4** rejected at channel start | Check `ffmpeg -version` in the built image; pin a non-5.1.4 build if needed (F2 gate) |
| `clips.path` is absolute, baked at seed → moving clips breaks HLS | Ingest/seed clips **in place** on the persistent `livebets_clips` volume; never move post-seed |
| `/ready` `hls:ok` is a no-op (doesn't detect ffmpeg/broken channel) | Verify video by **real playback** + segment files on disk, not `/ready` |
| Ephemeral IP changes on VM stop → DNS breaks | **Reserve static IP** (decision 3) |
| live-bets boots with placeholder secrets | `LIVE_BETS_ENV=prod` **fails fast** on placeholder `SERVER_KEY`/missing `ADMIN_PASSWORD` — provision real secrets in `.env.prod` first |
| Pushing live-bets master redeploys staging | Accepted (decision 4); staging should track master anyway |
| Widget WS/JSON cross-origin (`app.` → `live.`) never tested in-browser | CORS middleware covers JSON; verify the widget's **WSS** connects cross-origin (live-bets WS origin handling is unconfirmed) during the F1 browser walk — fix on the live-bets side if it rejects the `app.` origin |
| Extra RAM on the 12GB box | +3 small containers (pg/redis/app, remux-only) — comfortably within budget |

## Out of scope (YAGNI)

- live-bets split `serve-api`×N + `run-orchestrator` topology — a single `serve-all` is enough for one demo table.
- CV detector / real vehicle counting in prod — buckets hand-assigned for the demo.
- live-bets webhooks (`LIVEBETS_ENABLE_WEBHOOK=false`); the DOM-event mirror path is the money path.
- Server-side `/api/live/tables` list (JWT-gated, B2) — the widget mints a session and reads `rounds/current`; not needed.
- Multi-tenant / multi-origin CORS — single origin `https://app.xprediction.online`.

## Success criteria

- **F1:** `app.xprediction.online/live` shows the live widget for a logged-in demo player; a bet moves the XPredict wallet (debit→credit); zero cold start; no Render dependency.
- **F2:** the widget plays live HLS traffic video synced to rounds, served over TLS from `live.xprediction.online` with correct CORS.
