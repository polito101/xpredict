# Phase 19 — Handoff (for Pol)

> **Status: Frontend Complete · Backend Integration Ready · Production Handoff Ready.**
> Branch `gsd/phase-19-premium-experience` (PR [#33](https://github.com/polito101/xpredict/pull/33)).
> This phase is **frontend-only**. No backend / API / settlement / catalog / auth /
> wallet / portfolio / contract / flow changes were made (one exception: a pure
> `ruff format` of the already-merged v1.3 livebets files — no logic — to unblock CI).

The goal of this document: you open the branch, point it at the **definitive
backend**, and know exactly what is ready and what is left.

---

## 1. Brand / logo

- **Visible brand = "XPrediction"** everywhere (metadata, navbar wordmark, footer,
  landing, auth, admin shell). **Technical names stay "XPredict/xpredict"** — the
  `xpredict_session` cookie, `BACKEND_URL`/`NEXT_PUBLIC_*` env vars, the repo, and
  internal identifiers are unchanged (no contract churn).
- The navbar/admin wordmark is **runtime-driven** (`/branding/current` →
  `brand_name`). The frontend maps the legacy default `"XPredict"` (and empty) →
  `"XPrediction"` for display, so the canonical site reads "XPrediction" even
  before the backend is updated. **To make it authoritative, set the definitive
  backend's `tenant_config.brand_name = "XPrediction"`** (one row; or via
  `/admin/branding`). Real operator names still override (white-label intact).
- **Logo (action required — 1 file):** every product-mark surface (navbar default,
  hero core + mobile mark, auth, admin) renders the official asset through
  `components/brand/logo-mark.tsx` (`LogoMark`), which loads
  **`frontend/public/brand/xprediction-logo.png`**. **Drop the official PNG at that
  exact path** and the real asset appears everywhere with no code change. Until the
  file exists, `LogoMark` falls back to the faithful vector `x-mark.tsx` (nothing
  broken). The official PNG could not be committed from chat (a pasted image can't
  be written to disk from this side; the filesystem had no saved copy) — so this
  one drop is the only remaining step. See `frontend/public/brand/README.md`.
  (The white-label OPERATOR logo is separate: uploaded via `/admin/branding`,
  served at `/branding/logo`, and rendered over the default mark in the navbar.)

---

## 2. The ONE backend blocker (must fix before a definitive backend boots)

**Divergent Alembic migration tree (pre-existing on `main`, from the v1.3
Live-Bets merge — NOT this PR).** Two migrations both chain from `0010`:
`0011_livebets_bridge` and `0011_phase13_market_groups` ⇒ **two heads** ⇒
`alembic upgrade head` fails and `backend-ci` is red (`test_migration_0011`).

➡️ **Fix on `main` (backend owner):** add an `alembic merge` migration over the two
heads, **or** re-point `0011_livebets_bridge.down_revision` to the v1.2 head
(`0011_phase13_market_groups`) and update `test_migration_0011`. `livebets_bridge`
is additive + independent, so linearizing after v1.2 is schema-safe. Once `main`
is green, re-merge `main` here and this branch's `backend` check goes green too.

(I also `ruff format`-ed the 5 livebets files here — that was the *first* backend
failure; the migration tree is the *second*.)

---

## 3. Per-screen backend dependency matrix

All data is consumed through the **existing v1.2/v1.3 contracts** (unchanged).
"Old runtime" = the `xpredict-run` docker stack currently up (a pre-Phase-16
checkout: no `/catalog`, `/categories`, `/events`, no live-bets). "Definitive" =
any v1.2+ backend (ideally v1.3 for `/live`).

| Screen | Auth | Endpoints consumed | Old runtime | Definitive backend |
|--------|------|--------------------|-------------|--------------------|
| `/` landing | public | `GET /branding/current`, `GET /api/v1/catalog?sort=volume`, `GET /api/v1/categories` (all best-effort) | ✅ renders; demo stats/featured **degrade** (no `/catalog`) | ✅ full (real stats + featured) |
| `/login` `/register` `/forgot-password` `/reset-password` `/verify-email` | public | `POST /auth/*` (Server Actions) | ✅ works | ✅ works |
| `/markets` (grid) | session | `GET /api/v1/catalog`, `GET /api/v1/categories` | ❌ "Failed to load markets" (no catalog API) | ✅ full grid (MarketCard + EventCard) |
| `/markets/[slug]` | session | `GET /api/v1/markets/{slug}`, `/price-history`, `/activity`, WS `/ws/markets/{id}`, `POST /bets` | ✅ detail works (markets exist); WS needs same-origin CORS | ✅ full |
| `/events/[slug]` | session | `GET /api/v1/events/{slug}` (+ child market reads) | ❌ "Event not found" (no events API) | ✅ full |
| `/wallet` | session (verified) | `GET /wallet/me/balance`, `/wallet/me/transactions` | ✅ works (verified user) | ✅ full |
| `/portfolio` | session (verified) | `GET /bets/me/portfolio` | ✅ works (empty until bets) | ✅ full |
| `/live` | session | `fetchLiveSession` + `recordLivePlaced/Settled` + `getLiveBalance` (v1.3 live-bets) + widget `<script>` | ⚠️ graceful "No live table configured" empty state | ✅ with v1.3 live-bets backend + widget env |
| `/admin/login` | public | `POST /admin/auth/login` | ✅ works (needs an admin) | ✅ works |
| `/admin/*` (dashboard, users, markets, events, audit, branding) | admin Bearer | `GET/POST /api/v1/admin/*`, `/admin/markets|events/*`, KPI, audit, tenant-config | ⚠️ needs a seeded admin; some endpoints are pre-Phase-16 | ✅ full |

**Auth gate (middleware `proxy.ts`):** `/markets·/events·/portfolio·/wallet·/live`
→ redirect to `/login` without `xpredict_session`; `/admin/*` → `/admin/login`
without `admin_jwt`. `/`, `/login`, `/register`, `/api/*` are public.

---

## 4. What Pol needs to do to finish integration (no frontend code changes)

1. **Fix the migration tree on `main`** (§2), then re-merge `main` here → green CI.
2. **Point the frontend env at the definitive backend:**
   - `BACKEND_URL` (server-side; e.g. `http://backend:8000`)
   - `NEXT_PUBLIC_API_URL` (browser; for the logo `<img>`)
   - `NEXT_PUBLIC_WS_URL` (live odds WebSocket)
   - Backend **CORS / WS origin** (`FRONTEND_BASE_URL`) must equal the frontend
     origin, or browser WS + client refetch are blocked (SSR is unaffected).
3. **Brand:** set `tenant_config.brand_name = "XPrediction"` (+ optionally upload
   the official logo via `/admin/branding`).
4. **Seed/verify demo data** (catalog markets + events + a verified demo player +
   an admin) so `/markets`, `/events`, `/portfolio`, `/admin` show real data.
5. **`/live`:** provide the v1.3 live-bets backend + the widget env
   (`NEXT_PUBLIC_*` widget src + table id) for a populated live table; otherwise it
   stays in the (correct) empty state.

---

## 5. Temporary limitations (today, against the OLD runtime backend only)

- `/markets` grid, `/events`, `/admin` dashboard data, and `/live` populated state
  are unavailable **only because the currently-running docker backend predates the
  Phase-16 catalog API + v1.3 live-bets** — they all resolve once a v1.2/v1.3
  backend is connected. The frontend code is complete and correct for them.
- Portfolio positions don't yet show the underlying market name/link (no public
  by-id market endpoint exists). Out of scope for Phase 19; a future small backend
  read (or folding title into the portfolio DTO) would enable it.

---

## 6. Verification (this branch)

- ✅ `pnpm typecheck` clean · ✅ `pnpm lint` 0 errors · ✅ `pnpm vitest run` **238/238**
  (37 frontend + 3 v1.3 live test files) · ✅ `next build --webpack` (16 routes).
- ✅ CI `frontend` PASS (Linux) + security/audit checks PASS.
- ❌ CI `backend` — the pre-existing migration-tree blocker (§2), not this PR.
- ✅ Visual QA (desktop/tablet/mobile) of landing/hero/login/markets/wallet/
  portfolio/admin served from the production build (`next start` → `:3100` against
  the live backend `:8000`, demo user `review01@demo.xpredict`).

**No further functional work is intended on this branch.** It is ready for Pol to
connect the definitive backend and merge (after the §2 migration fix on `main`).
