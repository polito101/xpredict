---
phase: 10
slug: admin-kpi-dashboard-configurable-branding
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-31
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Test seams + Wave 0 gaps are detailed in `10-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend, testcontainers for integration) / vitest (frontend) |
| **Config file** | `backend/pyproject.toml` / `frontend/vitest.config.ts` |
| **Quick run command** | `cd backend && .venv/Scripts/python.exe -m pytest -q -m "not integration"` |
| **Full suite command** | `cd backend && .venv/Scripts/python.exe -m pytest` + `cd frontend && corepack pnpm vitest run` |
| **Estimated runtime** | ~TBD — backend integration subset (`tests/admin`, `tests/branding`) is testcontainer-bound (~40s cold testcontainer spin-up + a few s per file); frontend vitest files run in <5s each. Confirm at Wave 0. |

---

## Sampling Rate

- **After every task commit:** Run quick (non-integration) suite for the touched side. Backend code-producing tasks additionally run the named integration file once a testcontainer is warm.
- **After every plan wave:** Run full suite.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** TBD — gated by the testcontainer cold start (~40s) on the backend integration legs; frontend legs are <5s.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T1 | 10-01 | 1 | ADD-05, ADD-06 | T-10-05, T-10-06 | Wave 0 RED: tenant-config CRUD + public branding + SC#6 401/403 negative tests exist and fail RED | integration | `cd backend; .venv/Scripts/python.exe -m pytest tests/admin/test_tenant_config.py tests/admin/test_tenant_config_negative.py tests/branding/test_branding_public.py -x` | ❌ W0 | ⬜ pending |
| T2 | 10-01 | 1 | ADD-05 | T-10-01 | Single Alembic head; money-lint clean; `extra=forbid` + hex pattern reject at schema level; `schemas.py` omits `from __future__` (Pydantic v2 Field(pattern=) forward-ref) | integration | `cd backend; .venv/Scripts/python.exe -m alembic heads; .venv/Scripts/python.exe scripts/lint_money_columns.py` | ❌ W0 | ⬜ pending |
| T3 | 10-01 | 1 | ADD-05, ADD-06 | T-10-01, T-10-02, T-10-03, T-10-04, T-10-05, T-10-06 | GREEN: hex/logo 422 rejections; logo size cap + content-type allowlist + magic-byte check; nosniff on logo; player→403/401; audit before commit; routers + schemas omit `from __future__` | integration | `cd backend; .venv/Scripts/python.exe -m pytest tests/admin/test_tenant_config.py tests/admin/test_tenant_config_negative.py tests/branding/test_branding_public.py -x` | ❌ W0 | ⬜ pending |
| T1 | 10-02 | 2 | ADD-02, ADD-03 | T-10-10 | Wave 0 RED: KPI integration tests (P&L net incl. reversal, DAU UNION, pending predicate, active markets, 24h volume, money-as-string, window=bogus→422) + 30-day synthetic seeder exist and fail RED | integration | `cd backend; .venv/Scripts/python.exe -m pytest tests/admin/test_kpi.py -x` | ❌ W0 | ⬜ pending |
| T2 | 10-02 | 2 | ADD-02, ADD-03 | T-10-10 | Corrected P&L (kind-filtered net flow, no `house_expense`); DAU on `auth.session_started` (not `auth.login_started`); money as MoneyStr; import-clean; money-lint clean | unit | `cd backend; .venv/Scripts/python.exe scripts/lint_money_columns.py; .venv/Scripts/python.exe -c "import app.admin.kpi_service, app.admin.kpi_schemas"` | ❌ W0 | ⬜ pending |
| T3 | 10-02 | 2 | ADD-02, ADD-03 | T-10-07, T-10-08, T-10-09 | GREEN: admin-gated KPI endpoint; window Literal 422 before service; router omits `from __future__`; INFO query-time log | integration | `cd backend; .venv/Scripts/python.exe -m pytest tests/admin/test_kpi.py -x` | ❌ W0 | ⬜ pending |
| T1 | 10-03 | 2 | ADD-05 | T-10-12 | Wave 0 RED: BrandingForm test (pre-fill, invalid-hex inline blocks submit, valid submit calls action, logo preview/reject) exists and fails RED | unit | `cd frontend; corepack pnpm vitest run src/components/admin/branding-form.test.tsx` | ❌ W0 | ⬜ pending |
| T2 | 10-03 | 2 | ADD-05 | T-10-11 | use-server admin Bearer-forward (admin_jwt server-side only); types separated; no new typecheck errors in the two files | unit | `cd frontend; corepack pnpm typecheck 2>&1 \| grep -E "branding-admin-api\|branding-types" \|\| echo "no type errors in branding lib"` | ❌ W0 | ⬜ pending |
| T3 | 10-03 | 2 | ADD-05 | T-10-12, T-10-13 | GREEN: RHF+zod hex mirror; logo object-URL preview via `<img>` (no DOM inlining); 422→inline FormMessage; exact UI-SPEC copy; build compiles | unit | `cd frontend; corepack pnpm vitest run src/components/admin/branding-form.test.tsx` | ❌ W0 | ⬜ pending |
| T1 | 10-04 | 3 | ADD-03 | T-10-16 | Wave 0 RED: VolumeChart not-blank (react-is sentinel) + empty-state + DAU toggle tests exist and fail RED | unit | `cd frontend; corepack pnpm vitest run src/components/admin/volume-chart.test.tsx` | ❌ W0 | ⬜ pending |
| T2 | 10-04 | 3 | ADD-02, ADD-03 | T-10-15, T-10-16 | GREEN: Recharts not-blank in h-64 parent + empty state (exact copy) + 24h/7d/30d toggle; money typed as string (no parseFloat for storage); KpiCard color logic (negative P&L → `red-500`, positive → `emerald-600`); react-is pin untouched; admin_jwt Bearer forwarded server-side via fetchKpis | unit | `cd frontend; corepack pnpm vitest run src/components/admin/volume-chart.test.tsx src/components/admin/kpi-card.test.tsx` | ❌ W0 | ⬜ pending |
| T3 | 10-04 | 3 | ADD-01, ADD-02, ADD-03 | T-10-14 | GREEN: `/admin` is the KPI dashboard landing (depends on existing adminLoginAction→`/admin` redirect); Dashboard nav link with EXACT-match active for `/admin`; sessionStorage default-route flag is a UX hint only (never read by any auth/redirect path); build compiles | manual + unit (build) | `cd frontend; corepack pnpm build` | ❌ W0 | ⬜ pending |
| T1 | 10-05 | 2 | ADD-06 | T-10-17 | Wave 0 RED: public branding fetch test (200→typed object; non-ok→throw so layout falls back) exists and fails RED | unit | `cd frontend; corepack pnpm vitest run src/lib/branding-public.test.ts` | ❌ W0 | ⬜ pending |
| T2 | 10-05 | 2 | ADD-06 | T-10-17 | GREEN: public no-store fetch (per-navigation freshness, not a use-server module) + DEFAULT_BRANDING fallback; globals.css `--brand-*` tokens on :root + @theme inline mapping | unit | `cd frontend; corepack pnpm vitest run src/lib/branding-public.test.ts` | ❌ W0 | ⬜ pending |
| T3 | 10-05 | 2 | ADD-06 | T-10-01, T-10-02, T-10-18 | GREEN: async root layout injects ONLY server-validated opaque hex tokens into `<style>` (no other untrusted string concatenated); safe fallback on fetch failure; logo via `<img>` + nosniff; build compiles | manual + unit (build) | `cd frontend; corepack pnpm build` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*File Exists legend: ✅ = test file already present in the repo · ❌ W0 = created by the plan's Wave 0 (RED) task before implementation.*

---

## Wave 0 Requirements

From `10-RESEARCH.md` §Validation Architecture (§Wave 0 Gaps + §Test Seams). These test stubs / fixtures MUST exist (and fail RED) before the implementing tasks run:

- [ ] `backend/tests/branding/__init__.py` + `backend/tests/branding/test_branding_public.py` — ADD-06 public `GET /branding/current` + `GET /branding/logo` (nosniff) seam (10-01 T1).
- [ ] `backend/tests/admin/test_tenant_config.py` — ADD-05 CRUD round-trip + hex 422 + oversized/wrong-type logo 422 seam (10-01 T1).
- [ ] `backend/tests/admin/test_tenant_config_negative.py` — SC#6 player-Bearer→403 / no-Bearer→401, mirroring `tests/admin/test_auth_negative.py` `_routes()`/`_call` (10-01 T1).
- [ ] `backend/tests/admin/_helpers.py` extension — the **30-day synthetic bet seeder** (N bets across a configurable `created_at` span), a house-market seeder (status × deadline), and an `auth.session_started` / `auth.admin_login_started` audit-row seeder, for the chart-bucket + volume/DAU windows (10-02 T1). This is the shared fixture the KPI tests depend on.
- [ ] `backend/tests/admin/test_kpi.py` — ADD-02/03 seams: **House P&L** (settle via `SettlementService.resolve_market`, assert net `settle_loss − settle_winnings`; reverse → returns to pre-settlement value — the highest-value correctness test), **DAU** (bet-only ∪ login-only ∪ both = 3; admin login excluded; window varies), **pending resolutions** (deadline×status matrix, DRAFT excluded), active markets, 24h volume, money-as-string on the wire, window=bogus→422 (10-02 T1).
- [ ] `frontend/src/components/admin/volume-chart.test.tsx` — Recharts not-blank (react-is sentinel via the price-history-chart ResizeObserver/getBoundingClientRect stubs) + `<1`-bucket empty state at h-64 + 24h/7d/30d toggle (10-04 T1).
- [ ] `frontend/src/components/admin/kpi-card.test.tsx` (or extend volume-chart test task) — KpiCard color logic: negative House P&L → `red-500`, positive → `emerald-600`; money values rendered from string input (no `parseFloat` for storage). Mirror `price-history-chart.test.tsx` setup (10-04 T2).
- [ ] `frontend/src/components/admin/branding-form.test.tsx` — pre-fill, invalid-hex inline error blocks submit, valid submit calls the mocked PUT action, logo preview + size/type reject copy (10-03 T1).
- [ ] `frontend/src/lib/branding-public.test.ts` — 200→typed branding object; non-ok→throw (so the root layout's try/catch applies DEFAULT_BRANDING) (10-05 T1).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Palette swap re-skins player UI on next navigation (no rebuild) | ADD-06 / SC#5 | Cross-process runtime behavior; visual | Change palette in `/admin/branding` → navigate the player UI → confirm `--brand-*` vars + colors updated with no rebuild/redeploy |
| Login lands the admin on `/admin` dashboard | ADD-01 / SC#1 | Server-Action redirect + cross-page navigation; the redirect lives in the existing `adminLoginAction` (`frontend/src/lib/auth.ts` → `redirect("/admin")`) | Sign in at `/admin/login` → confirm the landing page is the KPI dashboard (five cards + chart), not the user list; confirm the sessionStorage `admin_default_route` flag is set as a UX hint only |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task above has an automated command)
- [ ] Wave 0 covers all MISSING references (the checklist above must be created + RED before implementation tasks)
- [x] No watch-mode flags (all commands are one-shot `vitest run` / `pytest -x` / `pnpm build`)
- [ ] Feedback latency confirmed (gated by testcontainer cold start ~40s — confirm at Wave 0)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending — `wave_0_complete: false` until the Wave 0 RED stubs above are created.
</content>
