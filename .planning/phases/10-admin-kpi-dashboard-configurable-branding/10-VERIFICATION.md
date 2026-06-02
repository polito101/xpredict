---
phase: 10-admin-kpi-dashboard-configurable-branding
verified: 2026-05-31T12:00:00Z
status: passed
score: 14/14 must-haves verified
overrides_applied: 1
override_note: "2026-06-01 — Pol (PM) consciously deferred the 4 human-verification items (live re-skin, admin landing, logo upload, mobile responsive) to live/Phase-11 testing and authorized shipping the PR. 14/14 automated must-have truths PASS. Deferred items tracked in 10-HUMAN-UAT.md (blocked_by: server) and re-runnable via /gsd-verify-work 10."
human_verification:
  - test: "Cambiar la paleta en /admin/branding y navegar a la home del player"
    expected: "Las variables --brand-primary/--brand-secondary se actualizan sin rebuild ni redeploy (SC#5/ADD-06)"
    why_human: "Requiere servidor Docker en marcha, navegador real y comparar los CSS vars antes/después del cambio de paleta"
  - test: "Iniciar sesión como admin y verificar que el redirect post-login aterriza en el dashboard KPI"
    expected: "La página /admin muestra las 5 cards (24h volume, DAU, active markets, pending resolutions, House P&L) y el chart de Recharts — no la lista de usuarios (ADD-01/SC#1)"
    why_human: "Requiere sesión de admin real + browser para confirmar que adminLoginAction → redirect('/admin') aterriza en el KPI dashboard y no en otro componente"
  - test: "Subir un logo SVG válido (<=256 KB) desde /admin/branding y navegar como player"
    expected: "El header del player muestra el <img src=/branding/logo> en lugar del wordmark XPredict; al navegar a otra ruta el logo persiste (ADD-05/ADD-06)"
    why_human: "Flujo de upload de archivo + visualización cross-origin requiere navegador real; no es verificable con grep ni build check"
  - test: "Verificar el aspecto visual del KPI dashboard en viewport mobile (<640px)"
    expected: "Las 5 cards se apilan en grid-cols-1; el chart VolumeChart mantiene la altura h-64; no hay overflow horizontal"
    why_human: "Responsividad visual requiere herramientas de browser o viewport testing"
---

# Fase 10: Admin KPI Dashboard & Configurable Branding — Verification Report

**Phase Goal:** "Replace the admin login landing page with a KPI dashboard (the 'is this platform healthy?' 5-second pulse), and give the operator runtime-configurable branding (logo, palette, brand name) — the white-label sales wedge."
**Verified:** 2026-05-31T12:00:00Z
**Status:** passed (14/14 automated; 4 human checks deferred — see Override below)
**Re-verification:** No — initial verification

---

## Override — Human Verification Deferred (2026-06-01)

**Decision (Pol, PM):** Ship Phase 10 with the 4 human-verification items deferred to live / Phase 11 testing. Status flipped `human_needed → passed` on this basis (`overrides_applied: 1`).

**Rationale:**
- 14/14 must-have observable truths PASS via automated verification (see Goal Achievement below).
- Code review complete (`10-REVIEW.md` + `10-REVIEW-FIX.md`, iteration 2).
- The 4 deferred items are human-only gates requiring a running server + real browser (live palette re-skin, admin post-login landing, logo upload+display, mobile <640px responsive). They are recorded in `10-HUMAN-UAT.md` as `blocked_by: server` — **prerequisite gates, not defects** — and re-runnable via `/gsd-verify-work 10`.
- Mobile responsiveness (item 4) is additionally re-covered by Phase 11 (Hardening: mobile ≥360px validation). The security scan (gitleaks/bandit/npm audit/OWASP ZAP) is roadmapped to Phase 11.

**Acknowledged risk:** visual/runtime confirmation of the 4 items was not performed pre-merge. Owner: Pol.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | La página /admin es el KPI dashboard (no el placeholder) y aterriza allí tras el login de admin | ✓ VERIFIED | `frontend/src/app/admin/page.tsx` es un async Server Component con `force-dynamic` que renderiza `<KpiDashboard initial={kpis}>`. `frontend/src/lib/auth.ts` contiene `redirect("/admin")` en `adminLoginAction` (línea 363). El placeholder anterior ha sido reemplazado. |
| 2 | El dashboard muestra 5 cards: 24h volume, DAU, active markets, pending resolutions, House P&L today + cumulative | ✓ VERIFIED | `KpiGrid` en `kpi-card.tsx` renderiza las 5 cards desde `KpiResponse`. El endpoint `GET /api/v1/admin/dashboard/kpis` devuelve todos los campos (verificado en `kpi_router.py` + `kpi_schemas.py`). |
| 3 | El chart de 30 días usa Recharts (AreaChart en contenedor h-64 fijo) y muestra un empty state cuando no hay datos | ✓ VERIFIED | `volume-chart.tsx` importa `AreaChart, ResponsiveContainer` de recharts; el parent tiene `className="h-64 w-full"`; `<1 bucket → VolumeChartEmptyState` con el copy exacto "No activity yet" / "Volume appears here as players place bets." |
| 4 | El toggle DAU 24h/7d/30d refetch el endpoint con ?window= y actualiza DAU + chart | ✓ VERIFIED | `DauWindowToggle` levanta el window seleccionado a `KpiDashboard` (vía `onChange`). `KpiDashboard.onWindowChange` llama `fetchKpis(next)` con el nuevo window y hace `setKpis(fresh)`. `fetchKpis` construye la URL con `?window=${window}`. |
| 5 | Los valores monetarios se serializan como strings en todo el pipeline (nunca floats JSON) | ✓ VERIFIED | Backend: `KpiResponse` usa `MoneyStr` (alias de `Decimal` serializado como string). Frontend: `kpi-types.ts` tipifica `volume_24h`, `house_pnl_today`, `house_pnl_cumulative` como `string`. `formatMoney` hace manipulación de string sin `parseFloat` para almacenamiento. |
| 6 | P&L negativo se muestra en red-500, positivo/cero en emerald-600 | ✓ VERIFIED | `isNegativeMoney` y la lógica de `cn(colorBySign && (negative ? "text-red-500" : "text-emerald-600"))` en `kpi-card.tsx`. `HousePnlCard` aplica la misma lógica. Test `kpi-card.test.tsx` existe y cubre este comportamiento (82/82 vitest green según evidencia del orquestador). |
| 7 | Admin PUT /api/v1/admin/tenant-config valida hex inválido (422) y logo oversized/wrong-type (422) | ✓ VERIFIED | `TenantConfigUpdate` usa `Field(pattern=_HEX)` con `extra="forbid"`. `_validate_logo` en `admin_router.py` comprueba content-type allowlist + magic bytes + cap `_MAX_LOGO_BYTES = 262144`. Tests `test_tenant_config.py` + `test_tenant_config_negative.py` cubren estos casos (backend 68 branding + 9 kpi tests green). |
| 8 | GET /branding/current es público y devuelve exactamente {brand_name, primary_hex, secondary_hex, logo_url} sin campos sensibles | ✓ VERIFIED | `branding_router.get("/branding/current")` no tiene `Depends(current_active_admin)`. Responde con `BrandingPublic` que tiene exactamente los 4 campos (sin bytes, tenant_id, timestamps). Test `test_branding_public.py` verifica el campo set exacto. |
| 9 | GET /branding/logo sirve los bytes con Content-Type correcto + X-Content-Type-Options: nosniff | ✓ VERIFIED | `get_branding_logo` devuelve `Response(content=row.logo_bytes, media_type=row.logo_content_type, headers={"X-Content-Type-Options": "nosniff"})` o 404 si no hay logo. |
| 10 | Player Bearer → 403, sin Bearer → 401 en /api/v1/admin/tenant-config | ✓ VERIFIED | Ambos endpoints GET/PUT del `tenant_config_admin_router` tienen `Depends(current_active_admin)`. `test_tenant_config_negative.py` cubre los dos casos. |
| 11 | El admin puede ver el formulario de branding en /admin/branding pre-llenado con los valores actuales | ✓ VERIFIED | `frontend/src/app/admin/branding/page.tsx` es un async Server Component con `force-dynamic` que awaita `fetchTenantConfig()` y pasa `initial` a `<BrandingForm>`. `BrandingForm` inicializa RHF con `defaultValues: { brand_name: initial.brand_name, ... }`. |
| 12 | La navegación admin incluye "Dashboard" (exact-match activo en /admin) y "Branding" (/admin/branding) | ✓ VERIFIED | `admin-nav.tsx` tiene `{ href: "/admin", label: "Dashboard", exact: true }` y `{ href: "/admin/branding", label: "Branding" }`. La lógica activa usa `pathname === "/admin"` para Dashboard (exact) y `startsWith` para el resto. |
| 13 | El root layout del player inyecta las CSS vars --brand-primary/--brand-secondary por cada navegación (no-store) | ✓ VERIFIED | `layout.tsx` es async, awaita `fetchBrandingPublic()` con `cache: "no-store"` y renderiza `<style>{\`:root{--brand-primary:${b.primary_hex};--brand-secondary:${b.secondary_hex};}\`}</style>` en `<head>`. `globals.css` define los fallbacks en `:root` y los mapea en `@theme inline`. |
| 14 | El header del player muestra el logo del operador (o el wordmark XPredict como fallback) | ✓ VERIFIED | `BrandLogo` en `brand-logo.tsx` renderiza `<img src="${publicApiBase()}${logoUrl}">` cuando `logoUrl` es no-nulo, o el wordmark de texto con el fallback `"XPredict"`. Montado en `layout.tsx` con `<BrandLogo brandName={b.brand_name} logoUrl={b.logo_url} />`. |

**Score:** 14/14 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/branding/models.py` | TenantConfig single-row model | ✓ VERIFIED | Clase `TenantConfig` con `UniqueConstraint("tenant_id")`, `LargeBinary` logo_bytes, ghost tenant_id, timestamps. |
| `backend/app/branding/schemas.py` | TenantConfigUpdate + TenantConfigRead + BrandingPublic | ✓ VERIFIED | Los 3 schemas presentes; `_HEX = r"^#[0-9a-fA-F]{6}$"`; `extra="forbid"` en Update; sin `from __future__ import annotations`. |
| `backend/alembic/versions/0009_phase10_tenant_config.py` | DDL + idempotent seed, chained off 0008 | ✓ VERIFIED | `down_revision = "0008_phase8_user_created_at"`; crea tabla + `INSERT ... ON CONFLICT (tenant_id) DO NOTHING` con el TENANT_DEFAULT. |
| `backend/app/branding/admin_router.py` | GET/PUT admin-gated, audited | ✓ VERIFIED | `tenant_config_admin_router` con `Depends(current_active_admin)` en ambos endpoints; `AuditService.record(..., event_type="admin.branding_updated")`; `admin_id` capturado antes del commit. |
| `backend/app/branding/router.py` | GET /branding/current + GET /branding/logo públicos | ✓ VERIFIED | `branding_router` sin auth dependency; `/branding/current` retorna `BrandingPublic`; `/branding/logo` sirve bytes con nosniff. |
| `backend/app/admin/kpi_service.py` | 5 agregados KPI + 30d buckets | ✓ VERIFIED | `get_kpis`, `house_pnl` (kind-filtered), `dau` (UNION bets+logins, `AUTH_SESSION_STARTED`), `active_markets`, `pending_resolutions`, `volume_24h`, `daily_volume_buckets`. Importa `TRANSFER_SETTLE_*`/`TRANSFER_REVERSE_*` y `HOUSE_*_ACCOUNT_ID` (no hardcoded strings). |
| `backend/app/admin/kpi_schemas.py` | KpiResponse + VolumeBucket con MoneyStr | ✓ VERIFIED | Importa `MoneyStr` de `app.wallet.schemas`; todos los campos monetarios son `MoneyStr`. |
| `backend/app/admin/kpi_router.py` | GET /api/v1/admin/dashboard/kpis?window= gated | ✓ VERIFIED | `kpi_router` con `Depends(current_active_admin)`; `window: Literal["24h","7d","30d"]` defaulting "24h"; structlog INFO con elapsed_ms; sin `from __future__ import annotations`. |
| `frontend/src/app/admin/page.tsx` | KPI dashboard reemplaza el placeholder | ✓ VERIFIED | `force-dynamic`; async Server Component; awaita `fetchKpis("24h")`; renderiza `<KpiDashboard initial={kpis} />` o el error copy. |
| `frontend/src/app/admin/branding/page.tsx` | Página de branding Server Component | ✓ VERIFIED | `force-dynamic`; awaita `fetchTenantConfig()`; pasa `initial` a `<BrandingForm>`. |
| `frontend/src/components/admin/branding-form.tsx` | RHF+zod BrandingForm con ColorField + LogoUploadField | ✓ VERIFIED | `"use client"`; RHF + zodResolver; ColorField con live swatch; LogoUploadField con object-URL preview + client pre-check; "Save branding" submit button variant default. |
| `frontend/src/lib/branding-admin-api.ts` | use server Bearer-forwarding fetch+PUT | ✓ VERIFIED | `"use server"`; lee `admin_jwt` cookie vía `cookies()`; `fetchTenantConfig` (GET) y `updateTenantConfig` (PUT multipart). |
| `frontend/src/components/admin/kpi-card.tsx` | KpiCard + KpiGrid (5 cards, responsive) | ✓ VERIFIED | `KpiCard`, `HousePnlCard`, `KpiGrid` (grid-cols-1 sm:grid-cols-2 lg:grid-cols-3); `formatMoney` string-only; `isNegativeMoney` para colorBySign. |
| `frontend/src/components/admin/volume-chart.tsx` | Recharts AreaChart en h-64 + empty state | ✓ VERIFIED | `"use client"`; `ResponsiveContainer` en `div.h-64`; `<1 bucket → VolumeChartEmptyState`; stroke/fill `var(--brand-primary)`; parseFloat solo para display. |
| `frontend/src/components/admin/admin-nav.tsx` | Dashboard (leading, exact-match) + Branding links | ✓ VERIFIED | LINKS array incluye Dashboard con `exact: true` y Branding; lógica activa `pathname === "/admin"` para exact. |
| `frontend/src/app/layout.tsx` | Async root layout inyectando brand CSS vars | ✓ VERIFIED | Async; `let b = DEFAULT_BRANDING; try { b = await fetchBrandingPublic(); }` + `<style>` block en `<head>`; `<BrandLogo>` montado en header. |
| `frontend/src/app/globals.css` | --brand-* tokens en :root + @theme inline | ✓ VERIFIED | `--brand-primary: #4f46e5; --brand-secondary: #0ea5e9;` en `:root`; `--color-brand-primary: var(--brand-primary)` en `@theme inline`. |
| `frontend/src/lib/branding-public.ts` | public no-store fetch + DEFAULT_BRANDING | ✓ VERIFIED | `fetchBrandingPublic` usa `cache: "no-store"`; NO es `"use server"`; `DEFAULT_BRANDING` exportado. |
| `frontend/src/components/brand-logo.tsx` | BrandLogo con img/wordmark fallback | ✓ VERIFIED | Renderiza `<img src="${publicApiBase()}${logoUrl}">` o wordmark; fallback a "XPredict" si `brandName.trim()` vacío. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/app/main.py` | branding admin + public routers | `app.include_router` | ✓ WIRED | Líneas 183-203: `include_router(tenant_config_admin_router)` + `include_router(branding_router)` |
| `backend/app/main.py` | `kpi_router` | `app.include_router` | ✓ WIRED | Línea 193: `app.include_router(kpi_router)` |
| `backend/app/branding/admin_router.py` | `AuditService.record` | `admin.branding_updated` event | ✓ WIRED | Líneas 188-198; `actor=f"user:{admin_id}"` capturado antes del commit (MissingGreenlet safe). |
| `backend/app/branding/admin_router.py` | `current_active_admin` | Depends gate en GET + PUT | ✓ WIRED | Ambos endpoints tienen `admin: Annotated[User, Depends(current_active_admin)]` |
| `backend/app/admin/kpi_service.py` | settlement transfer-kind constants | `TRANSFER_SETTLE_LOSS/WINNINGS/REVERSE_*` | ✓ WIRED | Importados de `app.settlement.constants`; nunca hardcoded strings. |
| `backend/app/admin/kpi_service.py` | `auth.session_started` audit event | Filtro en DAU UNION | ✓ WIRED | `AUTH_SESSION_STARTED = "auth.session_started"` (no el stale `auth.login_*`). |
| `frontend/src/app/admin/page.tsx` | `GET /api/v1/admin/dashboard/kpis` | `fetchKpis` "use server" Bearer-forwarded | ✓ WIRED | `fetchKpis` en `kpi-api.ts` construye `?window=` URL con Bearer from `admin_jwt` cookie. |
| `frontend/src/app/layout.tsx` | `GET /branding/current` | `fetchBrandingPublic()` per navigation cache no-store | ✓ WIRED | `await fetchBrandingPublic()` en el async layout; `branding-public.ts` usa `cache: "no-store"`. |
| `frontend/src/app/layout.tsx` | `:root --brand-*` CSS vars | `<style>` block con hexes validados | ✓ WIRED | `<style>{\`:root{--brand-primary:${b.primary_hex};--brand-secondary:${b.secondary_hex};}\`}</style>` |
| `frontend/src/components/brand-logo.tsx` | `GET /branding/logo` | `<img src=/branding/logo>` | ✓ WIRED | `src={\`${publicApiBase()}${logoUrl}\`}` cuando `logoUrl` presente. |
| `frontend/src/lib/branding-admin-api.ts` | `admin_jwt` cookie → Bearer | `cookies()` server-side | ✓ WIRED | `"use server"` module; `bearerHeader()` lee `admin_jwt` con `cookies()`. |
| `frontend/src/components/admin/branding-form.tsx` | `PUT /api/v1/admin/tenant-config` | form submit llama `updateTenantConfig` | ✓ WIRED | `onSubmit` llama `updateTenantConfig({...})` del `"use server"` action. |
| `frontend/src/lib/auth.ts` | `redirect("/admin")` | `adminLoginAction` post-login | ✓ WIRED | Línea 363 confirmada: `redirect("/admin")` — este plan NO añade redirect nuevo; hace que /admin sea el dashboard. |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `frontend/src/app/admin/page.tsx` | `kpis: KpiResponse` | `fetchKpis("24h")` → `GET /api/v1/admin/dashboard/kpis` → `get_kpis(session)` → queries reales sobre bets/markets/entries/audit_log | Sí — queries DB reales vía SQLAlchemy async | ✓ FLOWING |
| `frontend/src/app/layout.tsx` | `b: BrandingPublic` | `fetchBrandingPublic()` → `GET /branding/current` → `_load_singleton(session)` → SELECT sobre tenant_config | Sí — query real; fallback a DEFAULT_BRANDING en error | ✓ FLOWING |
| `frontend/src/components/admin/kpi-dashboard.tsx` | `kpis` state | Inicial desde Server Component; refetch vía `fetchKpis(next)` en `onWindowChange` | Sí — mismo endpoint backend | ✓ FLOWING |
| `frontend/src/app/admin/branding/page.tsx` | `initial: TenantConfigRead` | `fetchTenantConfig()` → `GET /api/v1/admin/tenant-config` → SELECT tenant_config | Sí — fallback a DEFAULT_CONFIG en error | ✓ FLOWING |

---

### Behavioral Spot-Checks

Step 7b: SKIPPED — el orquestador ya ejecutó la suite completa con Docker up y confirmó:
- backend branding tests: 68 passed
- backend kpi tests: 9 passed
- frontend vitest: 82/82 passed
- `pnpm build`: exit 0
- Los 5 fallos restantes son pre-existentes (3x WS/Redis fase 9, 1x concurrencia fase 3, 1x gitleaks histórico)

---

### Probe Execution

Step 7c: No se declaran probes explícitos en los PLANs de esta fase. Los tests de integración son el mecanismo equivalente y están documentados como green por el orquestador.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| ADD-01 | 10-04 | Admin landing page after login is the KPI dashboard, not the user list | ✓ SATISFIED | `/admin/page.tsx` reemplaza el placeholder con `KpiDashboard`; `adminLoginAction → redirect("/admin")` confirmado. |
| ADD-02 | 10-02, 10-04 | KPI dashboard shows 5 cards (24h volume, DAU, active markets, pending resolutions, house P&L today + cumulative) | ✓ SATISFIED | `KpiResponse` tiene los 6 campos (hoy + cumulative = 1 card con 2 sub-valores); `KpiGrid` renderiza las 5 cards. |
| ADD-03 | 10-02, 10-04 | KPI uses Recharts for volume-over-time, daily granularity 30 days | ✓ SATISFIED | `VolumeChart` usa `AreaChart` de recharts en contenedor `h-64`; `daily_volume_buckets` buckea por `date_trunc('day')`; empty state a <1 bucket. |
| ADD-05 | 10-01, 10-03 | Admin can configure brand name, logo, primary/secondary palette — single-row TenantConfig | ✓ SATISFIED | `TenantConfig` model + migration 0009; admin router PUT/GET en `/api/v1/admin/tenant-config`; `BrandingForm` con ColorField + LogoUploadField en `/admin/branding`. |
| ADD-06 | 10-01, 10-05 | Player UI reads branding at runtime; changes apply on next navigation (no rebuild) | ✓ SATISFIED | Root layout async awaita `/branding/current` con `cache: "no-store"` e inyecta `<style>:root{...}</style>`; `globals.css` define fallbacks. |

Requisitos adicionales en REQUIREMENTS.md marcados `[x]` que coinciden con esta fase: ADD-01, ADD-02, ADD-03, ADD-05, ADD-06 — todos marcados como completados.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/branding/admin_router.py` | 159 | `await logo.read()` sin cota upstream antes de bufferizar | ⚠️ Warning | Un admin puede enviar un multipart de varios GB; el cap de 256 KB se comprueba DESPUÉS de bufferizar en memoria. Blast radius acotado a admins autenticados. Documentado como WR-01 en el code review. |
| `backend/app/admin/kpi_service.py` | 181-186 | `cast(split_part(actor, ":", 2), PG_UUID)` sin guarda exacta — `"user:"` vacío produce `CAST('' AS uuid)` → error Postgres | ⚠️ Warning | Hoy todos los `auth.session_started` emiten `user:{uuid}` válido, riesgo bajo. Si una fila de audit_log tiene actor degenerado, tumba todo el endpoint de KPIs. Documentado como WR-02. |
| `backend/app/branding/admin_router.py` | 62 | `SELECT ... LIMIT 1` sin `ORDER BY` en `_load_singleton` | ⚠️ Warning | `tenant_id` es nullable → `UNIQUE` permite múltiples filas `NULL` en Postgres. Sin orden, resultado no-determinista si hay >1 fila. Documentado como WR-03. |
| `frontend/src/lib/branding-admin-api.ts` | 53-55 | 422 genérico mapeado a errores de hex; 401/403/500 muestran "check the fields" | ⚠️ Warning | Error de sesión expirada muestra mensaje incorrecto; 422 por `brand_name` largo se asigna a campos de color. Documentado como WR-04. |

Ningún TBD/FIXME/XXX sin referencia a issue encontrado en archivos de la fase. Sin BLOCKERS por anti-patterns.

---

### Human Verification Required

Los siguientes items requieren entorno Docker en marcha y navegador real (no verificables con grep ni build checks):

#### 1. Live re-skin del player sin rebuild (SC#5/ADD-06)

**Test:** Iniciar sesión como admin en `/admin/branding`, cambiar la paleta (ej. primary a `#e11d48`), guardar. Luego navegar a la home del player como usuario no autenticado.
**Expected:** El color primario del header (el dot en BrandLogo + cualquier elemento con `bg-brand-primary`) cambia al nuevo hex sin reiniciar el servidor ni hacer redeploy.
**Why human:** Requiere Docker en marcha, browser real, inspección de CSS computed `--brand-primary` antes y después.

#### 2. Dashboard KPI como landing tras login de admin (SC#1/ADD-01)

**Test:** Ir a `/admin/login`, iniciar sesión con credenciales de admin válidas, observar la página a la que redirige el `adminLoginAction`.
**Expected:** Aterriza en `/admin` y ve las 5 cards KPI + chart de Recharts (no la lista de usuarios de fases anteriores).
**Why human:** El redirect ya está en el código, pero la experiencia real de landing requiere una sesión de admin activa + browser.

#### 3. Upload y visualización de logo (ADD-05 + ADD-06)

**Test:** En `/admin/branding`, subir un PNG válido (<=256 KB). Guardar. Navegar a la home del player.
**Expected:** El header del player muestra el `<img>` con el logo en lugar del wordmark XPredict; el logo persiste en navegaciones sucesivas.
**Why human:** Flujo de upload de archivo + visualización cross-origin (frontend → backend `/branding/logo`) no es verificable con grep.

#### 4. Aspecto responsive del KPI dashboard

**Test:** Abrir `/admin` (autenticado) en un viewport de 360px de ancho.
**Expected:** Las 5 cards se apilan verticalmente (grid-cols-1); el VolumeChart mantiene altura h-64; no hay overflow horizontal.
**Why human:** Responsividad visual requiere browser/devtools con viewport resize.

---

### Gaps Summary

No se han encontrado brechas en la implementación. Todos los artefactos existen, son sustanciales, están cableados y los datos fluyen desde fuentes reales. Los 4 hallazgos de código (WR-01..04) son warnings documentados en el REVIEW.md y clasificados como non-blocking por el code reviewer; ninguno impide el objetivo de la fase.

Los únicos items abiertos son de verificación humana (comportamiento runtime real que no puede comprobarse estáticamente).

---

_Verified: 2026-05-31T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
