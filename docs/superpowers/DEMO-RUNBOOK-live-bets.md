# Demo Runbook — XPredict × live-bets (LB-C)

Stand up both stacks so a player can bet on **live-bets** from inside **XPredict**
end-to-end, then watch the XPredict wallet balance move. This runbook is
copy-pasteable. PowerShell on Windows; adapt quoting for bash.

> **Status of this runbook (2026-06-06).** The durable harness artifacts are
> done and verified: live-bets dev CORS (Task 1, in the live-bets repo on branch
> `feat/dev-cors-for-embed`), corrected `.env.example` files (Task 2), and a
> seeded ACTIVE demo table + key.
>
> **UPDATE — Stage 2 (2026-06-06): a CLEAN, ISOLATED demo instance was stood up
> and the full money path was PROVEN.** Everything that was blocked in Stage 1 on
> Agus's *stale* shared volume (B1 schema drift, B3 pre-existing admin key) is
> GONE on a fresh volume. See **§0 (Isolated demo instance)** for the exact
> commands + verified results, including:
>   - rounds OPEN on the clean instance (`table actor spawned` + a `BETTING_OPEN`
>     round that cycles to `SETTLED`),
>   - a full-scope `bootstrap-admin-key` minted (no refusal — fresh DB),
>   - the XPredict ledger DEBITED end-to-end (wallet 500.00 → 490.00, escrow
>     0.00 → 10.00) via the real `LiveBetsBridge.record_placed` path.
>
> The one corrected finding: **`GET /tables` is JWT-gated, not operator-key
> scoped** — an operator key returns 401; the working credential is a session
> JWT (see §0.6 + the revised **B2**). The original §A–§E below (against Agus's
> :8001 stack) are retained as the shared-stack reference; for the demo, use §0.

Ports (verified): live-bets host **:8001** (container :8000), Postgres **:15432**,
Redis **:6381**. XPredict backend **:8000**, frontend **:3000**, Postgres :5432,
Redis :6379. No clashes.

---

## 0. Isolated demo instance (RECOMMENDED — clean, never touches Agus's stack)

This is the path used for the Stage-2 verification. It stands up a SEPARATE
live-bets instance under compose project **`livebets-demo`** on FREE ports
(app **:8002**, pg **:15433**, redis **:6382**) with a FRESH volume, so it cannot
inherit the schema drift on Agus's shared `live-bets_pgdata` and cannot collide
with his running `live-bets` project (:8001/:15432/:6381). It reuses the already
built `live-bets:dev` image (no rebuild).

> **Safety:** every command below is scoped with `-p livebets-demo`. NEVER run a
> bare `docker compose down` here, and never stop/rm a `live-bets-*` container or
> remove the shared `live-bets_*` volumes.

### 0.1 Bring it up (compose file: `demo/docker-compose.demo.yml`)

```powershell
cd C:\Users\pobom\ProyectosClaude\xpredict-livebets
docker compose -p livebets-demo -f demo/docker-compose.demo.yml up -d
# postgres + redis go healthy, then live-bets starts (depends_on: service_healthy).
```

The `live-bets:dev` image's default CMD runs `migrate && serve-all ... --no-hls`,
so a fresh DB is migrated automatically on first boot. Verify:

```powershell
curl http://localhost:8002/health    # {"status":"ok"}
curl http://localhost:8002/ready     # {"ready":true,"checks":{"postgres":"ok","redis":"ok","hls":"ok","tables":"ok"}}
```

**Verified — the schema drift (B1) is ABSENT on the fresh volume:**

```powershell
docker exec livebets-demo-postgres-1 psql -U live_bets -d live_bets -t -c "SELECT count(*) FROM information_schema.columns WHERE table_name='rounds' AND column_name='live_started_at_pdt';"
#  -> 1   (Agus's stale volume returns 0 — that was the B1 blocker)
```
Boot log shows `Migrations applied.` then the Supervisor reaching
`supervisor boot: spawning initial actors` (on the stale DB it died at
`starting recovery` with `UndefinedColumnError: live_started_at_pdt`).

### 0.2 Seed the demo wiring (operator + ACTIVE table + buckets + 9 clips)

`scripts/seed_demo_operator.py` isn't bundled in the image — copy it in and run it
against the in-network DB (`postgres:5432`). `BCRYPT_COST=4` keeps it fast.

```powershell
docker cp C:\Users\pobom\ProyectosClaude\live-bets\scripts\seed_demo_operator.py livebets-demo-live-bets-1:/tmp/seed_demo_operator.py
docker exec -e DATABASE_URL="postgresql://live_bets:live_bets@postgres:5432/live_bets" -e BCRYPT_COST=4 livebets-demo-live-bets-1 python /tmp/seed_demo_operator.py
# -> ACTIVE demo table created: 71bf84f9-391f-49bc-90d6-e98506913e9b  (capture this table_id)
```

> The key this script prints is `lbk_sandbox_…` with `bets:place` ONLY — do NOT
> use it for reads. Use the full-scope `bootstrap-admin-key` token (0.3) in
> `.env.local`.

### 0.3 Mint a FULL-SCOPE operator key (no refusal on a fresh DB — B3 gone)

```powershell
docker exec livebets-demo-live-bets-1 live-bets bootstrap-admin-key --operator-slug xpredict-demo --display-name "XPredict Demo (LB-C)"
# -> Operator: 24fc640c-...  API key:  lbk_live_<48hex>   (ALL scopes, unlimited rate; shown ONCE)
```
On the fresh instance there is no pre-existing `webhooks:manage` key, so this
SUCCEEDS (on Agus's shared stack it refused — B3).

### 0.4 Verify rounds OPEN (the make-or-break check)

```powershell
docker exec livebets-demo-live-bets-1 live-bets list-tables
# -> 71bf84f9-...  ACTIVE  demo  'Demo Table (Phase 11 WIDGET-08)'  betting=30s live=20s settling=10s
curl http://localhost:8002/status
# -> {"clip_library_size":9,"active_tables":1,...}
docker exec livebets-demo-postgres-1 psql -U live_bets -d live_bets -c "SELECT id, state FROM rounds WHERE table_id='71bf84f9-391f-49bc-90d6-e98506913e9b' ORDER BY betting_opens_at DESC LIMIT 3;"
# -> a BETTING_OPEN round (and SETTLED ones as cycles complete)
docker logs livebets-demo-live-bets-1 2>&1 | Select-String "table actor spawned"
# -> {"event": "table actor spawned", ... "table_id": "71bf84f9-...", ...}
```
**VERIFIED:** the Supervisor's 5s poll spawned a TableActor for the new ACTIVE
table and rounds open + cycle (`BETTING_OPEN` → … → `SETTLED`).

### 0.5 Verify the operator key on the operator-scoped routes (bets:read)

```powershell
$KEY = "lbk_live_<48hex>"; $TID = "71bf84f9-391f-49bc-90d6-e98506913e9b"
curl "http://localhost:8002/v2/tables/$TID" -H "X-API-Key: $KEY"   # 200 + table JSON (proves bets:read; the sandbox key 403'd here)
```
A placed bet's id can then be fetched: `GET /v2/bets/{id}` with the same key → 200
(bets:read), NOT 403.

### 0.6 IMPORTANT — `GET /tables` (list) is JWT-gated, NOT operator-key scoped

The bridge router's `list_tables` calls live-bets **`GET /tables`** (the plural
list). That route depends on `get_current_user_id` → `verify_token` (an **HS256
JWT**), not `require_scopes`. So an **operator key returns 401**, regardless of
header:

```powershell
curl "http://localhost:8002/tables" -H "Authorization: Bearer $KEY"  # 401 invalid token (key is not a JWT)
curl "http://localhost:8002/tables" -H "X-API-Key: $KEY"             # 401 missing bearer token (route ignores X-API-Key)
```

The **working credential for `GET /tables` is a session JWT** (its `sub` must be a
UUID so `verify_token` accepts it). Mint one and it returns the envelope:

```powershell
# POST /v2/sessions with the operator key (player_ref = a UUID) -> session_token (eyJ...)
# GET /tables  -H "Authorization: Bearer <session_token>"  -> 200 {"tables":[{"id":"71bf84f9-...","status":"ACTIVE",...}]}
```
VERIFIED 200 with the `{tables:[…]}` envelope. **Consequence for the bridge:**
the XPredict client (`backend/app/integrations/livebets/client.py`) sends the
operator key as `X-API-Key`, so `GET /api/live/tables` → `GET /tables` would 401
even with a full-scope key. The widget/demo doesn't depend on `/api/live/tables`
(it mints a session and reads `rounds/current` with that JWT); but if the bridge
needs a server-side table list, it must use a session JWT or live-bets must add an
operator-key-scoped list route. See revised **B2**.

### 0.7 The money path, PROVEN end-to-end (XPredict ledger debited)

With the XPredict backend up + migrated (§C runs `alembic upgrade head`, applying
`0011_livebets_bridge`), the real `POST /api/live/bets/{bet_id}/placed` path
(`LiveBetsBridge.record_placed`) was exercised against this clean instance:

1. Seed a verified XPredict player + fund the wallet to **500.00**.
2. Mint a live-bets session (`player_ref = the XPredict user id`), place a bucket
   bet (stake 10.00) on the OPEN round → live-bets bet `PENDING`.
3. `record_placed` verifies the bet via live-bets `GET /v2/bets/{id}` (bets:read),
   then debits `user_wallet → livebets_escrow` via the double-entry writer.

**Before/after (verified in the XPredict ledger):**

| account | before | after |
|---|---|---|
| player `user_wallet` | **500.0000** | **490.0000** (− stake 10.00) |
| `livebets_escrow` (`…00b1`) | **0.0000** | **10.0000** (+ stake 10.00) |

Transfer `livebets_placed` (key `livebets:<bet_id>:placed`) has the balanced legs
(debit wallet 10.0000 / credit escrow 10.0000); the `livebets_bets` mirror row is
`status=PENDING, stake=10.0000`. `MirrorResult.applied=True`.

### 0.8 Tear down (safe — scoped to this project only)

```powershell
docker compose -p livebets-demo -f demo/docker-compose.demo.yml down -v   # -v drops ONLY demo_pgdata
```

---

## A. Bring up live-bets on :8001 (with embed CORS)

live-bets runs `serve-all` (API + per-table orchestrator + webhook dispatcher)
in one dev container. `docker-compose.yml` maps host :8001 → container :8000.

### A.0 (one-time) apply the dev CORS branch

The embed CORS is env-gated and lives on a branch in the **live-bets** repo:

```powershell
cd C:\Users\pobom\ProyectosClaude\live-bets
git checkout feat/dev-cors-for-embed   # branch off master; Pol reviews/merges
```

When `LIVE_BETS_CORS_ORIGINS` is set, `create_app` adds a `CORSMiddleware` with
that exact origin allowlist (no wildcard, `allow_credentials=False`). When unset,
no middleware is added — zero behavior change. (Test:
`tests/unit/test_dev_cors.py`, 4 passing.)

### A.1 set the CORS origin + start the stack

The browser widget on `http://localhost:3000` calls :8001 cross-origin
(fetch + WS + HLS), so the live-bets container needs `LIVE_BETS_CORS_ORIGINS`.
Add it to the `live-bets` service in `docker-compose.yml` (under `environment:`):

```yaml
  live-bets:
    environment:
      LIVE_BETS_CORS_ORIGINS: "http://localhost:3000"
```

Then:

```powershell
cd C:\Users\pobom\ProyectosClaude\live-bets
docker compose up -d --build      # rebuild so the CORS branch + current code are in the image
docker compose ps                 # postgres+redis healthy, live-bets up
```

> **Important — do not blow away a stack someone else is using.** If `docker ps`
> already shows `live-bets-live-bets-1`, a teammate (Agus) may be running it.
> Check `docker logs live-bets-live-bets-1 --since 5m` before `docker compose
> down`/`--build`. Coordinate first.

### A.2 wait for health

```powershell
curl http://localhost:8001/health    # {"status":"ok"}
curl http://localhost:8001/ready     # {"ready":true,"checks":{"postgres":"ok","redis":"ok","hls":"ok","tables":"ok"}}
```

### A.3 migrate (serve-all auto-migrates; this is the explicit form)

```powershell
docker exec live-bets-live-bets-1 live-bets migrate
```

> After migrate, sanity-check the schema the orchestrator depends on (this is the
> exact column whose absence is breaking the running stack — see B1):
> ```powershell
> docker exec live-bets-postgres-1 psql -U live_bets -d live_bets -t -c "SELECT count(*) FROM information_schema.columns WHERE table_name='rounds' AND column_name='live_started_at_pdt';"
> ```
> Must print `1`. If it prints `0`, STOP and fix per B1 before continuing — the
> orchestrator will crash on boot and never open rounds.

### A.4 mint a full-scope operator key

`bootstrap-admin-key` mints a key with **all** scopes (`bets:place` +
`catalog:read` + `bets:read` + …). It is idempotent and **refuses** if an active
admin key already exists:

```powershell
docker exec live-bets-live-bets-1 live-bets bootstrap-admin-key `
  --operator-slug xpredict-demo --display-name "XPredict Demo (LB-C)"
# -> prints: "API key:  lbk_live_<48hex>"  (shown ONCE — capture it now)
```

If it refuses with `An active 'webhooks:manage' key already exists (key_id=...)`,
the stack already has an admin key (e.g. from a prior smoke test). On a stack you
own you may rotate it: `docker exec live-bets-live-bets-1 live-bets revoke-key
<key_id>` then re-run bootstrap. **Do not revoke a key on a shared stack you don't
own.** (This is exactly the blocker hit during LB-C — see B3.)

> The `scripts/seed_demo_operator.py` script (used in A.6) mints a key with
> `bets:place` **only** — fine for placing bets, **not** for `GET
> /v2/catalog/tables` / `GET /v2/bets/{id}` reads. Use `bootstrap-admin-key`
> for the key you put in `.env.local`.

### A.5 ingest clips (optional if you seed synthetic clips in A.6)

`ingest-batch` walks `*.mp4` and indexes them. Real clips live in
`live-bets/var/{clip.mp4,sample.mp4,uat_clip.mp4}` and
`live-bets/tests/fixtures/clips/`:

```powershell
docker cp C:\Users\pobom\ProyectosClaude\live-bets\var live-bets-live-bets-1:/tmp/clips
docker exec live-bets-live-bets-1 live-bets ingest-batch /tmp/clips
```

For a deterministic demo you can skip real clips entirely — the seed script in
A.6 inserts 9 synthetic clips with known counts + bucket membership (the stub
detector only needs the count, not real video).

### A.6 create the demo table + buckets + clips (one script)

`scripts/seed_demo_operator.py` is idempotent (`ON CONFLICT DO NOTHING`) and
creates: the `demo` operator + a sandbox key, the `demo` source, one **ACTIVE**
`demo` table, `calibrated-v1` buckets, **9 synthetic clips**, and their
`bucket_membership`. Run it from the host against the mapped DB port:

```powershell
cd C:\Users\pobom\ProyectosClaude\live-bets
$env:DATABASE_URL = "postgresql://live_bets:live_bets@localhost:15432/live_bets"
$env:BCRYPT_COST  = "4"     # fast hashing for dev; default 12
uv run python scripts/seed_demo_operator.py
# prints: operator_id, sandbox key (bets:place only), table_id, source_id=demo
```

Get the `table_id`:

```powershell
docker exec live-bets-live-bets-1 live-bets list-tables
# -> <uuid>  ACTIVE  demo  'Demo Table (Phase 11 WIDGET-08)'  betting=30s live=20s settling=10s
```

### A.7 verify the orchestrator is opening rounds

This is the make-or-break check for the demo. After the table is ACTIVE the
Supervisor should spawn a TableActor within ~5s and open a round:

```powershell
docker exec live-bets-postgres-1 psql -U live_bets -d live_bets -c "SELECT id, state, betting_opens_at FROM rounds WHERE table_id='<table_id>' ORDER BY betting_opens_at DESC LIMIT 3;"
docker logs live-bets-live-bets-1 2>&1 | Select-String "table actor spawned"
```

You want ≥1 round and a `table actor spawned` log line. **If you get 0 rounds and
no spawn line, the orchestrator died at boot — go to B1.**

### A.8 verify the key + table over HTTP (full-scope key from A.4)

```powershell
$KEY = "lbk_live_<48hex>"   # from A.4
curl "http://localhost:8001/v2/tables/<table_id>" -H "X-API-Key: $KEY"     # 200 + table JSON (proves bets:read + table exists)
# If a round is open, fetch a bet to prove bets:read on /v2/bets/{id} as well.
```

> With the **sandbox** (bets:place-only) key this returns
> `403 SCOPE_MISMATCH {"required_scopes":["bets:read"],...}` — verified during
> LB-C. That 403 still proves the key authenticates and the table id resolves;
> it is only the *read* scope that's missing.

---

## B. Configure XPredict env

`.env.local` is gitignored. The committed `.env.example` files now point at :8001
(`LIVEBETS_API_BASE=http://localhost:8001`,
`NEXT_PUBLIC_LIVEBETS_WIDGET_SRC=http://localhost:8001/static/widget.js`).

Create `C:\Users\pobom\ProyectosClaude\xpredict-livebets\.env.local` (copy the
base vars from `.env.example`, then set the live-bets block):

```dotenv
LIVEBETS_API_BASE=http://localhost:8001
LIVEBETS_API_KEY=lbk_live_<48hex>            # the FULL-SCOPE key from A.4
LIVEBETS_DEFAULT_TABLE_ID=<table_id>         # from A.6/A.7
LIVEBETS_ENABLE_WEBHOOK=false
# frontend:
NEXT_PUBLIC_LIVEBETS_WIDGET_SRC=http://localhost:8001/static/widget.js
```

> An `.env.local` was created during LB-C with the real `table_id`
> (`1d3be465-4120-456e-9cc0-25405c7d7c8d`) and the real **sandbox**
> (bets:place-only) key. Replace `LIVEBETS_API_KEY` with a full-scope
> `bootstrap-admin-key` token before running the read paths (§E).
> **Never commit `.env.local`.**

---

## C. Bring up XPredict (backend :8000 + frontend :3000)

```powershell
cd C:\Users\pobom\ProyectosClaude\xpredict-livebets
.\bin\dev.ps1                 # backend :8000 + frontend :3000 (+ docker infra)
```

Run XPredict migrations (alembic) — this applies `0011_livebets_bridge`:

```powershell
cd C:\Users\pobom\ProyectosClaude\xpredict-livebets\backend
uv run alembic upgrade head
```

Sanity:

```powershell
curl http://localhost:8000/health
curl http://localhost:3000          # Next.js up
```

---

## D. The demo walk (browser — Pol's manual step)

1. Open `http://localhost:3000`, log in as a seeded player (e.g.
   `FIRST_ADMIN_*` from `.env.local`, or a seeded demo player).
2. Note the wallet balance.
3. Go to `http://localhost:3000/live`. The live-bets widget (`widget.js` from
   :8001) loads. If you see "Live widget not configured",
   `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` is unset — fix §B and rebuild the frontend.
4. Wait for a round to enter **BETTING** (30s window per the demo table). Place a
   bet in the widget (e.g. over/under).
5. Watch the XPredict wallet balance **drop by the stake** (the LB-A server-side
   mirror debits the XPredict ledger via `POST /api/live/bets/{bet_id}/placed`).
6. When the round settles, a win credits the wallet back (via
   `POST /api/live/bets/{bet_id}/settled`).

> This walk requires open rounds (A.7) **and** a working `GET /api/live/tables`
> (B2). Both are currently blocked — see Troubleshooting.

---

## E. Server-side money-path check (programmatic — no browser)

If both stacks are up *and* B1/B2 are resolved, verify the money path without the
UI. The XPredict bridge is mounted at `/api/live`:

- `GET  /api/live/tables`            → lists live-bets tables (server-side, uses `LIVEBETS_API_KEY`; needs catalog:read)
- `POST /api/live/session`           → mints a live-bets player session token
- `POST /api/live/bets/{id}/placed`  → mirrors a placed bet → **debits the XPredict ledger**
- `POST /api/live/bets/{id}/settled` → mirrors settlement → credits/clears

Flow:

1. `GET /api/live/tables` (XPredict) returns the demo table.
2. `POST /api/live/session` mints a session token.
3. Place a bet on live-bets `POST /v2/bets` (Bearer session token) on an OPEN round.
4. `POST /api/live/bets/{bet_id}/placed` (XPredict) → confirm the XPredict ledger
   debited (the LB-A mirror). Check the wallet balance before/after.

> **Not executed during LB-C** — blocked by B1 (no open rounds → nothing to bet
> on) and B2 (`GET /api/live/tables` → 404 against the current live-bets API).

---

## Troubleshooting (blockers actually hit during LB-C, with exact errors)

### B1 — Orchestrator never opens rounds: `live_started_at_pdt` missing (RESOLVED on a clean instance)

> **RESOLVED for the demo (Stage 2).** This was drift on Agus's *stale* shared
> volume only. On the clean `livebets-demo` instance (§0, FRESH `demo_pgdata`
> volume) the column is present (`SELECT count(*) ... = 1`), the Supervisor reaches
> `spawning initial actors`, and rounds open + cycle. The notes below remain for
> anyone who hits this on the shared :8001 stack.

**Symptom.** The demo table is ACTIVE (`live-bets list-tables` shows it, `/status`
shows `active_tables:1`, `clip_library_size:9`) but `rounds` stays empty (0 rows)
and there is **no** `table actor spawned` log line. The widget never gets a round
to bet on.

**Root cause (verified).** At Supervisor boot, `serve-all` runs
`recover_rounds(...)` BEFORE spawning any TableActor. On the running container that
query throws:

```
asyncpg.exceptions.UndefinedColumnError: column "live_started_at_pdt" does not exist
db.statement: SELECT ... chosen_clip_id, live_started_at_pdt, rtp_target, ...
              FROM rounds WHERE state NOT IN ('SETTLED','CANCELLED','ARCHIVED')
              ORDER BY betting_opens_at
```

The Supervisor logs `supervisor boot: starting recovery` and then dies on this
exception — it never reaches `supervisor boot: spawning initial actors` or the 5s
polling loop, so **no table (old or new) ever gets an actor or a round.**

The code (`live_bets/repositories/rounds.py`, `models.py`, `tables/actor.py`,
`hls/*`) references `rounds.live_started_at_pdt`. Migration
`migrations/008_hls_per_table.sql` adds it
(`ALTER TABLE rounds ADD COLUMN IF NOT EXISTS live_started_at_pdt TIMESTAMPTZ`).
On the running DB, `008_hls_per_table.sql` **is recorded** in `schema_migrations`,
yet the column is **absent** — the migration state and the actual schema have
drifted (something dropped/recreated `rounds` after 008 ran; note `schema_migrations`
also skips 019/020/021). This is a defect in the running stack's database, not in
the LB-C changes.

**Verify:**
```powershell
docker exec live-bets-postgres-1 psql -U live_bets -d live_bets -t -c "SELECT count(*) FROM information_schema.columns WHERE table_name='rounds' AND column_name='live_started_at_pdt';"   # 0 = broken
docker logs live-bets-live-bets-1 2>&1 | Select-String "starting recovery","spawning initial actors","UndefinedColumnError"
```

**Fix (on a stack you own — DO NOT run against a teammate's live DB):**
- Cleanest: recreate the stack from current code so migrations build `rounds`
  consistently: `docker compose down -v` (drops volumes — **destroys data**) then
  `docker compose up -d --build`. Re-run A.3–A.7.
- Or, if you must keep the volume, re-apply the column by hand and restart so the
  Supervisor reboots its recovery:
  ```powershell
  docker exec live-bets-postgres-1 psql -U live_bets -d live_bets -c "ALTER TABLE rounds ADD COLUMN IF NOT EXISTS live_started_at_pdt TIMESTAMPTZ;"
  docker restart live-bets-live-bets-1
  ```
  Then re-check A.7. (Only do this if the rest of the schema matches the code —
  if the drift is broader, a clean rebuild is safer.)

### B2 — `GET /api/live/tables` → `GET /tables` is JWT-gated (operator key returns 401)

> **Path mismatch already fixed in the client; the live issue is the AUTH SCHEME.**
> The XPredict client now calls the REAL path **`GET /tables`** (not the old
> `/v2/catalog/tables`, which 404'd) — see
> `backend/app/integrations/livebets/client.py::list_tables` line ~166. The
> remaining mismatch is credential type, verified on the clean instance in §0.6.

**Root cause (verified, Stage 2).** `GET /tables` depends on
`get_current_user_id` → `verify_token`, i.e. it requires an **HS256 JWT** whose
`sub` is a UUID. It is NOT an operator-scope route. The client sends the operator
key as `X-API-Key`, so:

```
GET http://localhost:8002/tables  -H "X-API-Key: <opkey>"        -> 401 missing bearer token (route ignores X-API-Key)
GET http://localhost:8002/tables  -H "Authorization: Bearer <opkey>" -> 401 invalid token   (operator key is not a JWT)
GET http://localhost:8002/tables  -H "Authorization: Bearer <session-JWT>" -> 200 {tables:[...]}   (WORKS)
GET http://localhost:8002/v2/tables/<id> -H "X-API-Key: <opkey>"  -> 200 (operator-scoped single-table sibling; bets:read)
```

**Impact.** `GET /api/live/tables` would 401 even with a full-scope operator key.
But the demo does NOT require it: the widget mints a session and uses
`GET /tables/{id}/rounds/current` with that **session JWT**, and the server-side
money-path uses `GET /v2/tables/{id}` / `GET /v2/bets/{id}` (operator key). So this
does not block the demo (the money path was proven, §0.7).

**Fix (team decision — out of scope for LB-C's CORS-only live-bets change).** If a
server-side table *list* is needed via `/api/live/tables`, either:
- repoint `LiveBetsClient.list_tables` to mint a session JWT and call `GET /tables`
  with it (the working credential), or
- add an operator-key-scoped list route to live-bets (`GET /v2/tables`), or
- have the bridge enumerate via `GET /v2/tables/{id}` for the known
  `LIVEBETS_DEFAULT_TABLE_ID`.
Whoever owns the bridge contract should pick one; it is not a CORS/env fix.

### B3 — `bootstrap-admin-key` refuses (active admin key exists) (RESOLVED on a clean instance)

> **RESOLVED for the demo (Stage 2).** A FRESH `livebets-demo` DB has no
> pre-existing `webhooks:manage` key, so `bootstrap-admin-key` SUCCEEDS and mints
> a full-scope `lbk_live_…` token (§0.3). This only bites on a shared stack that
> already has an admin key.

**Symptom.**
```
Error: An active 'webhooks:manage' key already exists (key_id=c7161506608bad0b).
Use `live-bets revoke-key c7161506608bad0b` first if you are rotating.
```

**Cause.** The stack already has an active admin key (e.g. the `e2e-admin`
operator from a smoke test, or a teammate's bootstrap). `bootstrap-admin-key` is
idempotent and refuses a second mint by design (privilege-escalation guard).

**Fix.** On a stack you own: `docker exec live-bets-live-bets-1 live-bets
revoke-key <key_id>` then re-run bootstrap. On a shared stack: **don't** revoke
someone else's key — use a clean stack (`docker compose down -v && up`), or get
the existing full-scope key from its owner. During LB-C the only full-scope path
was blocked here, so `.env.local` was filled with the `bets:place`-only sandbox
key from `seed_demo_operator.py` (sufficient for the bet/session money path, not
for catalog reads).

### B4 — `GET /openapi.json` → 500 on live-bets (cosmetic)

**Symptom.** `curl http://localhost:8001/openapi.json` → `500 Internal Server
Error` with `pydantic.errors.PydanticUserError: TypeAdapter[... 'Config | None'
...] is not fully defined`.

**Cause.** FastAPI tries to build a request-model TypeAdapter for a route whose
signature uses the `Config | None` forward-ref; the type isn't rebuilt. Pre-existing
in the running image; unrelated to CORS/env. **Impact:** Swagger/OpenAPI doc only —
the actual API routes work. Safe to ignore for the demo; file separately against
live-bets if the doc is needed.

### B5 — Widget shows "Live widget not configured"

`NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` is unset/empty in the frontend env. Set it to
`http://localhost:8001/static/widget.js` (§B) and rebuild/restart the frontend
(Next.js bakes `NEXT_PUBLIC_*` at build time).

### B6 — CORS errors in the browser console (blocked cross-origin)

The live-bets container was started without `LIVE_BETS_CORS_ORIGINS`, so no CORS
middleware was added. Set `LIVE_BETS_CORS_ORIGINS=http://localhost:3000` on the
`live-bets` service (§A.1) and `docker compose up -d` to recreate it. Verify:
```powershell
curl -i "http://localhost:8001/health" -H "Origin: http://localhost:3000" | Select-String "access-control-allow-origin"
# -> access-control-allow-origin: http://localhost:3000
```

### B7 — pnpm (frontend)

Use the standalone **pnpm 9.15.0** only. Never `corepack pnpm` (resolves to a
destructive 11.x that wipes `node_modules` and rewrites the lockfile).

---

## What is verified (LB-C honest status — updated after Stage 2)

Stage 2 stood up the clean `livebets-demo` instance (§0) and proved the path that
Stage 1 could only document. The shared-stack blockers (B1, B3) do not occur on a
fresh volume; B2 was reduced to a documented auth-scheme note (does not block the
demo).

| Item | Status |
|---|---|
| live-bets dev CORS (env-gated middleware) | **VERIFIED** — `tests/unit/test_dev_cors.py` 4/4 pass. |
| `demo/docker-compose.demo.yml` (isolated `livebets-demo`) | **VERIFIED** — committed on `gsd/livebets-demo`; brings up pg :15433 / redis :6382 / app :8002 on a fresh `demo_pgdata` volume; never touches Agus's `live-bets` project. |
| Clean instance up + migrations on fresh DB | **VERIFIED** — `/health` ok, `/ready` all-ok, `Migrations applied.`, `schema_migrations`=25, `rounds.live_started_at_pdt` present (count=1 — no drift). |
| `.env.local` updated (gitignored) | **VERIFIED** — `:8002`, real **full-scope** `lbk_live_…` key, demo `table_id` `71bf84f9-…`, widget src `:8002`; never committed (only `key_id` 29dda0936a8bc797 referenced here). |
| Demo table + 9 clips + buckets seeded | **VERIFIED** — `list-tables` shows 1 ACTIVE table; `/status` `active_tables:1`, `clip_library_size:9`. |
| Full-scope key via `bootstrap-admin-key` | **VERIFIED (B3 gone)** — fresh DB, no refusal; minted `lbk_live_…` with ALL scopes, unlimited rate. |
| Orchestrator opens rounds | **VERIFIED (B1 gone)** — `table actor spawned` for the demo table + a `BETTING_OPEN` round that cycles to `SETTLED`. |
| Operator key on operator routes (bets:read) | **VERIFIED** — `GET /v2/tables/<id>` → 200; `GET /v2/bets/<id>` → 200 (sandbox key 403'd; full-scope key 200). |
| `GET /tables` (list) | **VERIFIED + corrected (B2)** — JWT-gated: operator key → 401; session JWT → 200 `{tables:[…]}`. Does not block the demo. |
| Bet placed on an open round | **VERIFIED** — session JWT → `POST /v2/bets` (bucket, `low`, stake 10) → 201, `balance_after` 990.00 (live-bets paper wallet). |
| XPredict stack up + `0011_livebets_bridge` | **VERIFIED** — `docker compose --env-file .env.local up -d --wait` (8/8 healthy); `alembic upgrade head` applies through `0011_livebets_bridge`. |
| Server-side money path (XPredict ledger debit) | **VERIFIED** — real `LiveBetsBridge.record_placed`: wallet **500.00 → 490.00**, `livebets_escrow` **0.00 → 10.00**, balanced `livebets_placed` transfer, mirror row PENDING, `applied=True`. |
| Browser demo walk (§D) | **NOT RUN** — Pol's manual UI step; all server-side prerequisites are now green on the clean instance. |
