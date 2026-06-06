# Runbook — XPrediction live demo on one Hetzner VM (zero cold start)

Stand up the **whole** XPrediction platform on a single always-on VM for a live
sales-meeting demo. Everything runs 24/7 in Docker — no serverless, nothing that
sleeps, no cold starts anywhere — behind Caddy with real TLS so the prospect gets
`https://` pages and a `wss://` live-price feed.

This is the **reliability-first** path: one box, exact parity with the repo's
Docker images, self-hosted Postgres + Redis (no Neon scale-to-zero, no Upstash
command-meter). It doubles as a real staging environment.

> Files used here (all committed): [`docker-compose.prod.yml`](../../docker-compose.prod.yml),
> [`frontend/Dockerfile.prod`](../../frontend/Dockerfile.prod),
> [`deploy/Caddyfile`](../../deploy/Caddyfile), [`deploy/prod-init.sh`](../../deploy/prod-init.sh),
> [`.env.prod.example`](../../.env.prod.example).

## What runs

```
                         Internet
                            │  (DNS A records → VM public IP)
        app.your-domain ───┤   api.your-domain
                            ▼
                    ┌──────────────┐   :80/:443, auto-TLS (Let's Encrypt)
                    │    Caddy     │
                    └──┬────────┬──┘
            app.* ─────┘        └───── api.* (+ /ws WebSocket upgrade)
                    ▼                         ▼
              ┌───────────┐            ┌──────────────┐
              │ frontend  │  SSR/SA →  │   backend    │  FastAPI + WS
              │ next start│  (internal)│  (uvicorn)   │
              └───────────┘            └──────┬───────┘
                                              │ compose network
                      ┌───────────────┬───────┴───────┬───────────────┐
                      ▼               ▼               ▼               ▼
                  ┌────────┐    ┌────────┐      ┌──────────┐    ┌──────────┐
                  │  db    │    │ redis  │      │  worker  │    │   beat   │
                  │ pg16   │    │ 7      │      │ celery   │    │ celery   │
                  └────────┘    └────────┘      └──────────┘    └──────────┘
```

8 containers: `caddy`, `frontend`, `backend`, `worker`, `beat`, `db`, `redis`
(+ the one-shot init jobs). All `restart: unless-stopped` → survive a VM reboot.

## Prerequisites

- A **Hetzner Cloud** account.
- A **domain you control** (any registrar) so you can add two DNS records and get
  valid TLS. No domain? See [Appendix A — Cloudflare Tunnel](#appendix-a--no-domain-cloudflare-tunnel).
- An SSH key on your machine.
- ~30–45 min for the first deploy. Provision **at least a day before** the meeting.

**Cost:** Hetzner bills **hourly**. A CAX21 is ~€7.99/mo, so running it only for the
demo week ≈ **~€2**, and you can delete it after (or keep it as staging). ARM64 is
fine — all XPrediction images build/run on `arm64` (psycopg2 has aarch64 wheels;
the frontend is pure JS).

---

## Step 1 — Create the VM

Hetzner Cloud Console → **Add Server**:
- **Location:** Nuremberg/Falkenstein/Helsinki (EU). For an Americas audience, you'll
  still get fine latency; Caddy/Cloudflare can edge-cache if needed.
- **Image:** Ubuntu 24.04.
- **Type:** Shared vCPU → **Arm64 (Ampere)** → **CAX21** (4 vCPU / 8 GB). This
  comfortably runs the ~3–5 GB stack. (CAX11/4 GB also works for a seeded-only
  demo; CAX21 is the safe pick when also running the live Gamma sync.)
- **SSH key:** add yours.
- **Firewall:** create/attach one allowing inbound **22, 80, 443** only.
- Create, then note the **public IPv4**.

## Step 2 — DNS

At your DNS provider, add two **A records** → the VM's public IP:

| Type | Name  | Value (VM IP)   |
|------|-------|-----------------|
| A    | `app` | `203.0.113.10`  |
| A    | `api` | `203.0.113.10`  |

Wait for them to resolve (`nslookup app.your-domain.com`). Caddy can't issue TLS
until they point at the box.

## Step 3 — Prepare the server

SSH in (`ssh root@VM_IP`) and:

```bash
# Firewall (belt-and-suspenders alongside Hetzner's cloud firewall)
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

# Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# Git
apt-get update && apt-get install -y git
```

## Step 4 — Clone & configure

```bash
git clone https://github.com/polito101/xpredict.git
cd xpredict
# Use a STABLE checkout (main, or the merged demo-deploy PR) — never a worktree.

cp .env.prod.example .env.prod
nano .env.prod
```

Fill `.env.prod` (see its inline comments). Generate secrets **on the VM**:

```bash
openssl rand -base64 36   # → POSTGRES_PASSWORD
openssl rand -base64 48   # → SECRET_KEY  (and set ADMIN_JWT_PUBLIC_SECRET to the SAME value)
```

Must-get-right values:
- `APP_DOMAIN=app.your-domain.com`, `API_DOMAIN=api.your-domain.com`, `ACME_EMAIL=`a real inbox.
- `NEXT_PUBLIC_API_URL=https://api.your-domain.com`, `NEXT_PUBLIC_WS_URL=wss://api.your-domain.com`.
- **`FRONTEND_BASE_URL=https://app.your-domain.com`** — exact, no trailing slash. The
  backend checks the browser's `Origin` against this for **both CORS and the live
  WebSocket**; any mismatch (trailing slash, `www`, http) silently kills the price feed.
- `SECRET_KEY` — a fresh ≥32-char secret. (`ADMIN_JWT_PUBLIC_SECRET` is currently
  unused by the frontend; set it equal as a harmless default — it is **not**
  load-bearing today.)
- `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` (you'll log into `/admin` with these).

## Step 5 — Build, initialize, launch

```bash
# 1. Build all images (ARM64; first build ~5–10 min)
docker compose --env-file .env.prod -f docker-compose.prod.yml build

# 2. Schema + first admin + demo dataset (idempotent; brings db/redis up first)
chmod +x deploy/prod-init.sh
./deploy/prod-init.sh

# 3. Start the whole stack
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# 4. Watch health until all are healthy/started
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

Caddy issues TLS certs automatically on first start (needs DNS resolving + 80/443
open — Steps 2–3). Within ~30 s you should reach `https://app.your-domain.com`.

## Step 6 — (Optional) pre-load the ~1900-market live catalog

For the "scale" part of the demo, let the Celery **beat** scheduler run the curated
Gamma/Polymarket sync. It fires **automatically every 5 min** (task
`poll_polymarket_events`), so just bring the stack up **a few hours (or the day)
before** the meeting and the catalog fills itself. To force one **now** instead of
waiting:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec worker \
  celery -A app.celery_app call app.integrations.polymarket.tasks.poll_polymarket_events
```

Verify it's populating:
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec db \
  psql -U xpredict -d xpredict -c "select count(*) from markets;"
```

> **Demo content = both.** `seed_demo.py` (Step 5) gives ~15 curated house markets /
> 81 bets so portfolio/wallet/admin screens are rich and load instantly; the Gamma
> sync adds the large live catalog. Run the click-through on the seeded data and use
> the synced catalog to show scale — you never depend on a sync firing *during* the call.

## Step 7 — Dry run (the day before — do this!)

A self-managed box has no HA, so rehearse:
1. Open `https://app.your-domain.com` — every page you'll show (home, a market detail,
   portfolio, wallet, `/admin` login).
2. On a market-detail page, confirm the **live price WebSocket connects** (browser
   DevTools → Network → WS shows `wss://api.your-domain.com/ws/markets/...` status 101).
   If it fails with 1008, your `FRONTEND_BASE_URL` doesn't exactly match the page origin.
3. Log into `/admin` with `FIRST_ADMIN_*`.
4. `docker compose ... ps` — all `healthy`.
5. Take a **Hetzner snapshot** as a restore point.

Because everything is always-on, there's no cold start to pre-warm — but reload the
app once right before the meeting as a final sanity check.

---

## Operations cheatsheet

```bash
C="docker compose --env-file .env.prod -f docker-compose.prod.yml"
$C ps                      # status/health
$C logs -f backend         # tail a service
$C restart beat            # restart the scheduler (do this after any schedule change)
$C exec db pg_dump -U xpredict xpredict > backup_$(date +%F).sql   # DB backup
$C down                    # stop (keeps named volumes/data)
$C down -v                 # stop AND DELETE all data (careful)
```

Update to newer code: `git pull` → `$C build` → `$C up -d` (data persists in volumes).

## Teardown after the demo

- **Keep as staging:** leave it running (~€8/mo), or stop the server in Hetzner to
  pause billing for compute (volume/IP still bill a little).
- **Done with it:** take a final snapshot/backup, then **delete the server** to stop
  billing. Re-create from the snapshot later if needed.

---

## Troubleshooting

- **TLS cert not issued / browser warning:** DNS not resolving to the VM yet, or
  80/443 blocked. Check `dig app.your-domain.com`, the Hetzner firewall, and
  `$C logs caddy`.
- **Live price WebSocket won't connect (closes 1008):** `FRONTEND_BASE_URL` ≠ the
  exact browser origin. It must be `https://app.your-domain.com` with no trailing
  slash, matching what the browser address bar shows. Fix `.env.prod`, then
  `$C up -d` to recreate the backend.
- **WS connects but no price movement:** the worker/beat aren't producing updates —
  `$C ps` (worker+beat healthy?), `$C logs worker beat`. On a redeploy where the
  schedule changed, `$C restart beat` (redbeat persists the old schedule in Redis).
- **Admin login rejected though credentials are right:** the admin gate is the
  backend's `current_active_admin` (a DB-backed bearer token keyed on `SECRET_KEY`);
  the Next.js edge proxy only checks `admin_jwt` cookie *presence*. Check (a) the
  `FIRST_ADMIN_*` superuser actually seeded (`$C logs backend`; re-run
  `./deploy/prod-init.sh`), (b) you didn't rotate `SECRET_KEY` after first boot (that
  invalidates existing tokens — just log in again), (c) backend is healthy.
  `ADMIN_JWT_PUBLIC_SECRET` is **not** involved in admin login.
- **Frontend build fails (`pnpm build`):** the proven combo is Node 20 + pnpm
  9.15.0 (the Dockerfile pins it) — matches green CI. If it OOMs on a tiny VM, use
  CAX21 (8 GB), not CAX11.
- **`out of memory` under load:** scale up the Hetzner type in-place (CAX21 → CAX31);
  data persists.

## Appendix A — No domain? Cloudflare Tunnel

If you can't add DNS A records (or don't want to expose ports), run a **Cloudflare
Tunnel** instead of Caddy's public listener:
1. Add your domain to Cloudflare (free), or use a Cloudflare-managed hostname.
2. `cloudflared tunnel create xpredict-demo`, route `app.` and `api.` hostnames to
   the tunnel.
3. Point the tunnel ingress at the containers (`http://localhost:3000` for app,
   `http://localhost:8000` for api) — publish those ports to localhost in an
   override, and drop the `caddy` service. Cloudflare terminates TLS at its edge, so
   `https://`/`wss://` still work. Keep `FRONTEND_BASE_URL` = the public app hostname.

Caddy + your own subdomains is simpler; reach for the tunnel only if a public domain
isn't an option.
