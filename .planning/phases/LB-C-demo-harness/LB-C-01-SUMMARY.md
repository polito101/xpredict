---
phase: LB-C-demo-harness
plan: 01
subsystem: demo-harness
spans_two_repos: true
tags: [cors, env, runbook, docker, live-bets, integration]
requires:
  - live-bets repo on master (clean) for the CORS branch
  - xpredict-livebets worktree on gsd/livebets-demo
provides:
  - live-bets env-gated dev CORS (branch feat/dev-cors-for-embed, NOT merged/pushed)
  - corrected .env.example files (:8001) on gsd/livebets-demo
  - gitignored .env.local with real demo table id + real (bets:place-only) key
  - docs/superpowers/DEMO-RUNBOOK-live-bets.md
affects:
  - live-bets API CORS behavior (opt-in only; zero change when env unset)
  - XPredict live-bets bridge demo configuration
tech-stack:
  added: []
  patterns:
    - env-gated middleware (LIVE_BETS_CORS_ORIGINS) — zero behavior change when unset
key-files:
  created:
    - C:/Users/pobom/ProyectosClaude/live-bets/tests/unit/test_dev_cors.py
    - C:/Users/pobom/ProyectosClaude/xpredict-livebets/.env.local (gitignored — NOT committed)
    - docs/superpowers/DEMO-RUNBOOK-live-bets.md
  modified:
    - C:/Users/pobom/ProyectosClaude/live-bets/live_bets/api/app.py
    - .env.example
    - frontend/.env.example
decisions:
  - Read LIVE_BETS_CORS_ORIGINS directly from os.environ in create_app (not via Settings) to keep zero-impact + avoid coupling to strict Settings validation / test-factory mode.
  - Did NOT restart/rebuild/down Agus's 16h-running live-bets stack; worked against it read-mostly + via the idempotent seed script only.
  - Did NOT revoke the existing admin key to force bootstrap-admin-key (would disrupt the shared stack); used the bets:place-only sandbox key instead and documented the gap.
  - Did NOT ALTER Agus's DB / re-run migrations to fix the live_started_at_pdt drift (architectural/destructive to in-flight Phase 21 work); documented as a runbook blocker.
metrics:
  duration_minutes: 16
  tasks_completed: 4
  tasks_blocked_documented: 1
  files_created: 3
  files_modified: 3
  completed: 2026-06-06
---

# Phase LB-C Plan 01: Demo Harness Summary

Stood up the durable LB-C demo harness — env-gated dev CORS on live-bets (tested),
corrected `:8001` env, a real seeded demo table + key, and a copy-pasteable demo
runbook — while honestly reporting that the live bring-up of the *demo itself* is
blocked by a pre-existing schema-drift bug in the running live-bets container
(orchestrator never opens rounds) plus an XPredict↔live-bets API-path mismatch.

---

## STAGE 2 OUTCOME (2026-06-06) — clean isolated instance: rounds open + money path PROVEN

Stage 1's two live blockers were artifacts of Agus's **stale shared volume** and a
**shared stack with a pre-existing admin key** — NOT defects in the demo wiring.
Stage 2 proved this by standing up a CLEAN, ISOLATED instance and running the full
path end-to-end. Agus's `live-bets` project was never touched (verified up 17h
throughout).

**New durable deliverable:** `demo/docker-compose.demo.yml` — a self-contained
compose (project **`livebets-demo`**) that reuses `live-bets:dev` on FREE ports
(app **:8002**, pg **:15433**, redis **:6382**) with a FRESH `demo_pgdata` volume.
Standalone (not `extends:` the live-bets compose) specifically to avoid the
port-list MERGE that would re-bind Agus's :8001/:15432/:6381.

**Verified on the clean instance (all green):**
- Bring-up: `docker compose -p livebets-demo -f demo/docker-compose.demo.yml up -d`
  → pg+redis healthy, live-bets healthy; image default CMD auto-migrated the fresh
  DB. `/ready` all-ok, `schema_migrations`=25.
- **B1 GONE:** `rounds.live_started_at_pdt` is present (count=1, vs 0 on the stale
  volume); boot log reaches `supervisor boot: spawning initial actors` (no
  `UndefinedColumnError`).
- Seeded demo operator + ACTIVE table `71bf84f9-391f-49bc-90d6-e98506913e9b` +
  buckets + 9 clips (`seed_demo_operator.py`, run inside the container vs
  `postgres:5432`, `BCRYPT_COST=4`).
- **B3 GONE:** `bootstrap-admin-key --operator-slug xpredict-demo` SUCCEEDED (fresh
  DB, no refusal) → full-scope `lbk_live_…` key (key_id `29dda0936a8bc797`, ALL
  scopes, unlimited rate).
- **Rounds OPEN:** `table actor spawned` for the demo table; a `BETTING_OPEN` round
  that cycles to `SETTLED`. `/status` `active_tables:1`, `clip_library_size:9`.
- **bets:read:** `GET /v2/tables/<id>` → 200, `GET /v2/bets/<id>` → 200 with the
  full-scope key (the sandbox key 403'd `/v2/tables/<id>` in Stage 1).
- **Bet placed:** session JWT → `POST /v2/bets` (bucket, `low`, stake 10) → 201.
- **XPredict stack up + migrated:** `docker compose --env-file .env.local up -d
  --wait` (8/8 healthy, project `xpredict-livebets`); `alembic upgrade head`
  applied through `0011_livebets_bridge` (escrow singleton + `livebets_bets`).
- **MONEY PATH PROVEN (XPredict ledger debited):** drove the real
  `LiveBetsBridge.record_placed` (the code `POST /api/live/bets/{id}/placed` runs)
  for a seeded verified player funded to 500.00. It verified the bet via live-bets
  `GET /v2/bets/{id}` then posted the double-entry debit:
  **player `user_wallet` 500.00 → 490.00**, **`livebets_escrow` 0.00 → 10.00**,
  balanced `livebets_placed` transfer, mirror row `PENDING`, `applied=True`.

**Corrected finding (B2 reframed):** the old `/v2/catalog/tables` 404 is already
fixed in the XPredict client (it now calls `GET /tables`). The remaining mismatch
is the AUTH SCHEME: **`GET /tables` is JWT-gated** (`get_current_user_id` →
`verify_token`), not operator-scoped — so the operator key the client sends as
`X-API-Key` returns **401** (verified both header styles). The working credential
is a **session JWT** (UUID `sub`) → `GET /tables` returns the `{tables:[…]}`
envelope (verified 200). This does NOT block the demo (the widget reads
`rounds/current` with a session JWT; the money path uses `/v2/tables/{id}` +
`/v2/bets/{id}` with the operator key). If a server-side `/api/live/tables` list
is wanted later, the bridge must use a session JWT or live-bets must add an
operator-scoped list route. Logged in the runbook (§0.6 + revised B2).

**`.env.local` (gitignored, NEVER committed):** repointed to the clean instance —
`LIVEBETS_API_BASE=http://localhost:8002`, `LIVEBETS_API_KEY=<full-scope lbk_live_…>`
(only key_id `29dda0936a8bc797` appears in any committed text),
`LIVEBETS_DEFAULT_TABLE_ID=71bf84f9-…`,
`NEXT_PUBLIC_LIVEBETS_WIDGET_SRC=http://localhost:8002/static/widget.js`.
Re-verified gitignored + the full key string absent from all tracked files.

**What was NOT run:** the browser UI walk (§D) — Pol's manual step; every
server-side prerequisite is now green.

## What shipped (durable, verified)

### Task 1 — live-bets dev CORS (separate repo, `feat/dev-cors-for-embed`)
- Added an **env-gated** `CORSMiddleware` in `live_bets/api/app.py::create_app`,
  reading `LIVE_BETS_CORS_ORIGINS` (comma-separated exact origins) from
  `os.environ`. Set → middleware with the explicit allowlist,
  `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=False` (no
  wildcard origin; credentials off because the widget uses a Bearer session
  token, not cookies). Unset/empty → no middleware added (zero behavior change;
  safe prod default).
- Added `tests/unit/test_dev_cors.py` (mirrors `test_openapi_security.py`'s
  `_build_test_app`). **4/4 pass:** header present when env set, header absent
  when unset, OPTIONS preflight answered, foreign origin refused.
- Commit `c379ef8` on `feat/dev-cors-for-embed` (off `master`). Author `Pol Bonet`
  (NOT Agustin) + Claude co-author trailer. **No push, no PR** (Pol's step).
- `uv run` created `.venv/` (gitignored) + `uv.lock` (left **untracked**, not
  committed — out of Task 1 scope).

### Task 2 — XPredict env (worktree, `gsd/livebets-demo`)
- `.env.example`: `LIVEBETS_API_BASE=http://localhost:8001` (was `:8080`).
- `frontend/.env.example`: `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC=http://localhost:8001/static/widget.js`.
- Created `.env.local` (repo root, **gitignored — NOT committed**) with the base
  vars + the live-bets block: real `LIVEBETS_DEFAULT_TABLE_ID`
  (`1d3be465-4120-456e-9cc0-25405c7d7c8d`), the real `LIVEBETS_API_KEY`
  (a `lbk_sandbox_…` token, key_id `3a99be6baf431219`, bets:place-only — the
  full secret lives ONLY in the gitignored `.env.local`, never in any committed
  file), `LIVEBETS_ENABLE_WEBHOOK=false`, widget src.
- Commit `85dae73` — **only** the two `.env.example` files. `.env.local` verified
  gitignored + invisible to git after the real-key edit.

### Task 4 — demo runbook (worktree, `gsd/livebets-demo`)
- `docs/superpowers/DEMO-RUNBOOK-live-bets.md` (415 lines): bring up live-bets on
  :8001 with `LIVE_BETS_CORS_ORIGINS`, migrate, `bootstrap-admin-key`,
  ingest-batch, `seed_demo_operator.py`, get table id; set XPredict `.env.local`;
  bring up XPredict (`bin/dev.ps1` + alembic `0011_livebets_bridge`); browser demo
  walk; server-side money-path check; a **Troubleshooting** section with the EXACT
  errors hit (B1–B7); and a verified-vs-documented status table.
- Commit `592ece1`.

## Best-effort results (attempted, blockers reported honestly — not faked)

### Task 3 — bring up live-bets + provision
Docker daemon was up. The live-bets stack was **already running** (Agus's,
`live-bets-live-bets-1` up 16h on :8001; pg :15432 + redis :6381 healthy). Per the
constraints I did **not** restart/down/rebuild it. Worked against it.

**Succeeded (verified):**
- Ran `scripts/seed_demo_operator.py` (idempotent, demo-scoped) from the host
  against `localhost:15432`. Created the `demo` operator
  (`fe5c402d-…`), an ACTIVE `demo` **table** (`1d3be465-4120-456e-9cc0-25405c7d7c8d`),
  the `demo` source, `calibrated-v1` buckets, **9 synthetic clips**, and 9
  `bucket_membership` rows.
- `/status` moved `active_tables` 0→1, `clip_library_size` 0→9. `live-bets
  list-tables` shows the ACTIVE table.
- HTTP key/table check: `GET http://localhost:8001/v2/tables/<id>` with the seed
  key → `403 SCOPE_MISMATCH {"required_scopes":["bets:read"],"provided_scopes":["bets:place"]}`.
  This **proves** the key authenticates and the table id resolves; only the read
  *scope* is missing.

**Blocked (exact errors captured in the runbook):**
- **bootstrap-admin-key REFUSED** (B3): `An active 'webhooks:manage' key already
  exists (key_id=c7161506608bad0b)` — the shared stack already has an admin key
  (`e2e-admin`). I did not revoke it (would disrupt the shared stack), so I could
  not mint a full-scope key. Used the `bets:place`-only sandbox key instead.
- **Orchestrator opens NO rounds** (B1): the demo table is ACTIVE but `rounds` is
  empty and there is **no** `table actor spawned` log line. Root cause (verified
  from logs): at boot `serve-all`'s Supervisor runs `recover_rounds()` first,
  which throws
  `asyncpg.exceptions.UndefinedColumnError: column "live_started_at_pdt" does not exist`
  (the recovery SELECT references it; the column is absent from the running DB's
  `rounds` table even though migration `008_hls_per_table.sql` — which adds it via
  `ADD COLUMN IF NOT EXISTS` — is recorded in `schema_migrations`; the migration
  state and schema have drifted, and `schema_migrations` also skips 019/020/021).
  The Supervisor dies before spawning any actor, so no rounds open for any table.
  This is a defect in the running stack's DB, not in the LB-C changes; fixing it
  means recreating the stack or hand-patching Agus's live DB — neither is safe to
  do to his in-flight Phase 21 work.

### Task 5 — server-side money path
**Not run — blocked by the same root causes, with evidence (not faked):**
- B1 means there are **0 open rounds**, so there is nothing to place a real bet on.
- B2: the XPredict client
  (`backend/app/integrations/livebets/client.py::list_tables`) calls live-bets
  `GET /v2/catalog/tables`, which **404s** on the current live-bets API
  (verified: `/v2/catalog/tables` and `/catalog/tables` both → `404 Not Found`;
  live-bets exposes tables at `/tables` (JWT) and `/v2/tables/{id}` (operator key,
  `bets:read`), and catalog only has `/catalog/sources` + `/catalog/clips`). So
  `GET /api/live/tables` on XPredict would 404 even with a full-scope key.
  Reconciling this contract is a team decision and is **out of scope** for LB-C's
  CORS-only live-bets change (hard constraint: live-bets change = Task 1 only).

## Deviations from Plan

### Auto-handled / corrected recon
**1. [Rule 1 — recon correction] `/v2/catalog/tables` does not exist on live-bets.**
- **Found during:** Task 3 verification.
- **Issue:** The plan's verification step used `GET /v2/catalog/tables`. That path
  404s; the real table endpoints are `GET /tables` (JWT) and `GET /v2/tables/{id}`
  (operator key, `bets:read`). The catalog router only has `sources` + `clips`.
- **Action:** Verified the table via `GET /v2/tables/<id>` instead (403 scope proof).
  Documented the correct paths AND the XPredict-client mismatch (B2) in the runbook.
- **Files:** none changed (recon/doc correction only).

**2. [Rule 3-excluded — shared-stack safety] Did not mutate Agus's running stack.**
- **Found during:** Task 3 (stack already up 16h).
- **Decision:** Did not `docker compose down/--build`, did not revoke the existing
  admin key, did not ALTER `rounds` / re-run migrations on the live DB. These
  would disrupt a teammate's in-flight work (Rule 4 architectural / explicit
  constraint). Captured the blockers honestly instead. The idempotent,
  demo-scoped `seed_demo_operator.py` was the only mutation (adds an isolated
  `demo` operator/table/source — does not touch Agus's `e2e-admin`/`test-*` rows).

**3. [Scope log] Pre-existing live-bets defects observed, left untouched.**
- `recover_rounds` schema drift (B1) and `/openapi.json` 500
  (`PydanticUserError`, B4) are pre-existing in the running image and unrelated to
  the CORS change. Logged in the runbook Troubleshooting; not fixed (out of scope —
  live-bets change is CORS-only).

## Known Stubs / Caveats
- `.env.local` `LIVEBETS_API_KEY` is a real but **bets:place-only** key. Sufficient
  for the player money-path (sessions + bets); insufficient for catalog/bets reads.
  Pol must swap in a `bootstrap-admin-key` full-scope token on a clean stack
  (runbook §A.4 / §B). Clearly caveated inline in `.env.local`.
- `.env.local` `LIVEBETS_DEFAULT_TABLE_ID` is real and the table is ACTIVE, but it
  has 0 open rounds until B1 is fixed.

## Security notes
- `.env.local` (contains a real API key) is gitignored and was **never staged/
  committed** — re-verified after the real-key edit (`git check-ignore` + status).
- live-bets CORS is opt-in, origin-scoped (no `*`), credentials off — no widening
  of the trust boundary when the env var is unset (prod default).

## Self-Check: PASSED
- Files verified present: `tests/unit/test_dev_cors.py`, `.env.local` (gitignored),
  `docs/superpowers/DEMO-RUNBOOK-live-bets.md`, `LB-C-01-SUMMARY.md`, both
  `.env.example`, `live_bets/api/app.py`.
- Commits verified: `c379ef8` (live-bets CORS, `feat/dev-cors-for-embed`),
  `85dae73` (env, `gsd/livebets-demo`), `592ece1` (runbook, `gsd/livebets-demo`).
- `.env.local` confirmed gitignored and never staged/committed.
