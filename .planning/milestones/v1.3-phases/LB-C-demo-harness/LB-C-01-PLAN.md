---
phase: LB-C-demo-harness
plan: 01
type: execute
wave: 1
depends_on: []
spans_two_repos: true
files_modified:
  # live-bets repo (separate, branch off master) — dev CORS
  - "C:/Users/pobom/ProyectosClaude/live-bets/live_bets/api/app.py"
  - "C:/Users/pobom/ProyectosClaude/live-bets/tests/ (a small CORS test)"
  # xpredict-livebets worktree — env + runbook
  - ".env.example"
  - "frontend/.env.example"
  - ".env.local  (gitignored — created, NOT committed)"
  - "docs/superpowers/DEMO-RUNBOOK-live-bets.md"
requirements:
  - LB-C-SC1   # live-bets reachable on :8001 with dev CORS for http://localhost:3000
  - LB-C-SC2   # operator key with bets:place + catalog:read + bets:read; a live table exists
  - LB-C-SC3   # xpredict env (.env.local) points at :8001 with real key + table id; .env.example corrected
  - LB-C-SC4   # a runbook brings up both stacks + walks the demo; server-side money path verified as far as feasible
---

<objective>
Stand up the demo harness so a player can bet on live-bets from XPredict end-to-end. This is operational + a tiny cross-repo code change — NOT a big code phase. Deliver the reliable artifacts firmly (dev CORS on live-bets, corrected env, a tested runbook); ATTEMPT the Docker bring-up + verification best-effort and report blockers honestly (do NOT fake success).
</objective>

## Recon (baked in — verified against the repos; do not re-derive)
- **live-bets dev runs on host `:8001`** (`docker-compose.yml` maps `8001:8000`; Postgres `:15432`, Redis `:6381`) — NO clash with xpredict (:8000/:3000, pg 5432, redis 6379). The earlier `:8080` assumption was WRONG.
- **`serve-all`** runs API + orchestrator/ticker + HLS in one dev container (`docker compose up`). `migrate` runs migrations. start.sh shows the staging variant uses `--bus redis --no-hls`.
- **Operator key with the scopes we need** (`bets:place` for /v2/sessions, `catalog:read` for /v2/catalog/tables, `bets:read` for /v2/bets/{id}): use **`live-bets bootstrap-admin-key`** — it mints a key with ALL scopes (idempotent: refuses if an active admin key exists). NOTE: `scripts/seed_demo_operator.py` mints a key with `bets:place` ONLY → insufficient for verification; do not rely on it for the key (it is fine for creating the demo operator/table).
- **Table:** `live-bets create-table ...` (or `seed_demo_operator.py` which inserts an ACTIVE 'demo' table). `list-tables` → the `table_id`.
- **Clips exist:** `live-bets/var/{clip.mp4,sample.mp4,uat_clip.mp4}` and `live-bets/tests/fixtures/clips/`. `ingest-batch <dir>` walks `*.mp4`. The ingested clips must be reachable by the demo table's source/bucket for the orchestrator to open rounds — VERIFY this wiring during bring-up (clip → bucket → table source) and report if rounds don't open.
- **Pre-fund likely automatic:** `repositories/users.py` creates a user with `balance = 1000.00` by default → enough for demo bets; verify, only top-up if needed.
- **CORS gap:** `app.py` adds only `SlowAPIMiddleware`, no CORS. The browser widget on :3000 calls :8001 (fetch/WS/HLS) cross-origin → blocked without CORS. (Server-side xpredict→:8001 calls don't need CORS.)

## Tasks

### Task 1 — live-bets dev CORS (SEPARATE REPO, branch off master)
In `C:/Users/pobom/ProyectosClaude/live-bets` (currently on `master`, clean): create a branch `feat/dev-cors-for-embed` off `master` (do NOT commit on master). Add an **env-gated** CORS middleware in `create_app` (`live_bets/api/app.py`): read `LIVE_BETS_CORS_ORIGINS` (comma-separated origins) from the environment; if set, `app.add_middleware(CORSMiddleware, allow_origins=[...], allow_methods=["*"], allow_headers=["*"], allow_credentials=False)` (specific origins, not `*`; credentials off — the widget authenticates with a Bearer session token, not cookies). If the env is unset/empty, add nothing (zero behavior change — safe default). Import `from fastapi.middleware.cors import CORSMiddleware`. Add a focused test (mirror an existing app test): with `LIVE_BETS_CORS_ORIGINS=http://localhost:3000` set, an `OPTIONS`/cross-origin request to a route returns the `access-control-allow-origin: http://localhost:3000` header; with it unset, no CORS header. Run the live-bets test for that file (`.venv\Scripts\python.exe -m pytest <file>` or the project's runner). Commit on the branch (default identity + Claude co-author trailer; NOT Agustin). Do NOT push / open a PR (Pol does that). This is the only live-bets change.

### Task 2 — xpredict env (worktree)
- Fix `.env.example`: `LIVEBETS_API_BASE=http://localhost:8001` (was `:8080`).
- Fix `frontend/.env.example`: `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC=http://localhost:8001/static/widget.js`.
- Create `.env.local` (repo root, **gitignored — never commit**) with the demo values: `LIVEBETS_API_BASE=http://localhost:8001`, `LIVEBETS_API_KEY=<the bootstrap-admin-key token from Task 3>`, `LIVEBETS_DEFAULT_TABLE_ID=<table id from Task 3>`, `LIVEBETS_ENABLE_WEBHOOK=false`, plus the existing required base vars (copy from `.env.example`) and `frontend` needs `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC=http://localhost:8001/static/widget.js`. Commit ONLY the two `.env.example` fixes (the `.env.local` stays gitignored).

### Task 3 — bring up live-bets + provision (BEST-EFFORT; report blockers, don't fake)
In `C:/Users/pobom/ProyectosClaude/live-bets`: `docker compose up -d` (brings up postgres:15432, redis:6381, live-bets:8001 running serve-all). Wait for health. Then (against the running container or via the CLI with `DATABASE_URL`/`REDIS_URL` pointing at the mapped ports):
1. `live-bets migrate` (if serve-all didn't already).
2. `live-bets bootstrap-admin-key` → capture the printed token → into `.env.local` `LIVEBETS_API_KEY`.
3. `live-bets ingest-batch <clips dir>` (e.g. `var/` or `tests/fixtures/clips/`) — confirm clips index `done`.
4. Create a table: `seed_demo_operator.py` (demo operator + 'demo' table + 'demo' source) OR `live-bets create-table ...`; ensure the table's source/bucket matches the ingested clips so the orchestrator opens rounds. `live-bets list-tables` → capture the `table_id` → `.env.local` `LIVEBETS_DEFAULT_TABLE_ID`.
5. Verify with curl: `GET http://localhost:8001/v2/catalog/tables -H "X-API-Key: <key>"` returns the table (proves catalog:read + the table). If a round is open, `GET /v2/bets/{id}` scope works with the key (bets:read).
If Docker is unavailable/contended (Agus may be using it), or clips→rounds don't wire up, or HLS/ffmpeg fails — STOP that sub-step, record the exact error in the runbook's Troubleshooting, and continue with the other tasks. The harness artifacts (CORS, env, runbook) are the durable deliverable.

### Task 4 — demo runbook (worktree)
Write `docs/superpowers/DEMO-RUNBOOK-live-bets.md`: exact, copy-pasteable steps to (a) bring up live-bets on :8001 WITH `LIVE_BETS_CORS_ORIGINS=http://localhost:3000` (docker compose / env), migrate, bootstrap-admin-key, ingest-batch, create table, get table_id; (b) set xpredict `.env.local` (the LIVEBETS_* + widget src); (c) bring up xpredict (`bin\dev.ps1` / docker compose, backend :8000 + frontend :3000) + alembic upgrade (runs migration `0011_livebets_bridge`); (d) the demo walk: log in as a seeded player → `/live` → place a bet in the widget → watch the XPredict wallet balance move; (e) a Troubleshooting section capturing any blocker hit in Task 3 (ports, Docker, clips→rounds, CORS, HLS). Commit.

### Task 5 — verify the money path as far as feasible (BEST-EFFORT)
If both stacks come up: a server-side check — from xpredict, `/api/live/tables` returns the table, `/api/live/session` mints a token; place a programmatic bet via live-bets `/v2/bets` (Bearer session token) then call xpredict `/api/live/bets/{bet_id}/placed` and confirm the XPredict ledger debited (the LB-A mirror). Document the result in the runbook. If full bring-up isn't achievable here, say so plainly — the browser walk is Pol's manual step per the runbook.

## HARD CONSTRAINTS
- The live-bets change is on its OWN branch in the live-bets repo (off `master`); never commit to live-bets `master`; never push / open a PR. The xpredict commits go on `gsd/livebets-demo` in the worktree.
- **NEVER commit `.env.local` or any real API key** (it's gitignored; keep it that way; the key is printed once — put it only in `.env.local`).
- Do NOT touch `.planning/ROADMAP.md`/`STATE.md`/`MILESTONES.md`; do NOT run `gsd-sdk`/`gsd-tools.cjs`.
- pnpm (if touched): standalone 9.15.0 only, never corepack.
- Report blockers with exact errors; do NOT fabricate a working bring-up or a passing verification. Best-effort sub-steps that fail must be documented, not faked.
- Write `LB-C-01-SUMMARY.md`.
