---
phase: 10-admin-kpi-dashboard-configurable-branding
plan: 04
subsystem: frontend
tags: [kpi, dashboard, recharts, area-chart, admin-nav, money-as-string, use-server, vitest, sessionstorage]

# Dependency graph
requires:
  - phase: 10-admin-kpi-dashboard-configurable-branding
    plan: 02
    provides: "GET /api/v1/admin/dashboard/kpis?window=24h|7d|30d (admin-gated) -> KpiResponse (5 cards + ≤30 volume_buckets, MoneyStr money fields, negative P&L valid)"
  - phase: 10-admin-kpi-dashboard-configurable-branding
    plan: 03
    provides: "/admin/branding route (the nav Branding link target); branding-admin-api.ts use-server Bearer-forward analog"
  - phase: 08-admin-crm-user-management-audit-log-viewer
    provides: "admin-api.ts use-server adminApiFetch (admin_jwt cookie -> Authorization Bearer), users/page.tsx Server-Component force-dynamic + try/catch degrade, admin-nav.tsx LINKS+active styling, recharge-form.tsx shadcn import style"
  - phase: 09-market-detail-price-history
    provides: "price-history-chart.tsx (Recharts ResponsiveContainer-in-h-64 + WindowToggle + <2-points empty state) and its react-is-sentinel vitest (ResizeObserver + getBoundingClientRect jsdom stubs)"
provides:
  - "/admin KPI dashboard landing (replaces the placeholder) — five KpiCards + 30-day Recharts AreaChart, reached via the EXISTING adminLoginAction -> redirect(\"/admin\")"
  - "kpi-api.ts use-server fetchKpis(window) — admin_jwt Bearer-forwarded GET /api/v1/admin/dashboard/kpis?window="
  - "kpi-types.ts: KpiResponse + VolumeBucket (money fields typed string end-to-end)"
  - "KpiCard + KpiGrid + HousePnlCard (color-by-sign from string), DauWindowToggle (24h/7d/30d), VolumeChart (+VolumeChartEmptyState), KpiDashboard client wrapper, AdminDefaultRoute sessionStorage flag"
  - "admin-nav.tsx: leading Dashboard (exact-match) + Branding links — makes Plan 10-03's branding page reachable from the nav"
affects: [11-observability-alerting, phase-10 verification/code-review]

# Tech tracking
tech-stack:
  added: []   # zero new packages — recharts ^3.8.1 + react-is 19.2.6 (pnpm.overrides) already present
  patterns:
    - "use-server admin Bearer-forward reused verbatim from admin-api.ts (admin_jwt HttpOnly cookie -> Authorization Bearer, server-side only) — T-10-15 mitigation; client KpiDashboard calls the exported async action, never reads the cookie"
    - "Recharts in a fixed h-64 parent + react-is pinned via pnpm.overrides (untouched) — the not-blank smoke test (svg path.recharts-area-area) is the sentinel — T-10-16 mitigation"
    - "Money-as-string end to end: formatMoney + isNegativeMoney are pure string ops (no parseFloat/Number for storage); the chart parseFloats for DISPLAY only inside data.map"
    - "Server Component fetches the initial KpiResponse + passes it to a client wrapper that owns the DAU window state; the toggle refetches via the use-server action in a useTransition (mirrors price-history parent-owns-window)"
    - "sessionStorage default-route flag is WRITTEN (UX hint) and NEVER READ by any auth/redirect path — T-10-14 mitigation; authoritative landing stays adminLoginAction's existing redirect"

key-files:
  created:
    - frontend/src/lib/kpi-types.ts
    - frontend/src/lib/kpi-api.ts
    - frontend/src/components/admin/kpi-card.tsx
    - frontend/src/components/admin/kpi-card.test.tsx
    - frontend/src/components/admin/dau-window-toggle.tsx
    - frontend/src/components/admin/volume-chart.tsx
    - frontend/src/components/admin/volume-chart.test.tsx
    - frontend/src/components/admin/kpi-dashboard.tsx
    - frontend/src/components/admin/admin-default-route.tsx
  modified:
    - frontend/src/app/admin/page.tsx
    - frontend/src/components/admin/admin-nav.tsx

key-decisions:
  - "House P&L is ONE card (HousePnlCard) showing both Today and All-time, each colored by sign — keeps the grid at FIVE cards (UI-SPEC: P&L is a single card with two sub-captions), not six."
  - "Sign + money formatting are read from the STRING (isNegativeMoney = leading '-' AND a 1-9 digit remaining; formatMoney pads 4 dp via string ops) — no parseFloat/Number for storage; '-0.0000' counts as zero (emerald), not negative."
  - "VolumeChart stroke/fill = var(--brand-primary, #059669) so the chart re-skins live with operator branding (Plan 10-05) while keeping the emerald-600 fallback (UI-SPEC A-CHART) — react-is pnpm.overrides pin untouched."
  - "The DAU refetch runs in a useTransition and keeps the last good payload on a transient failure; the initial hard-error case is handled by the Server Component (KPI-load-error copy), not the client wrapper."
  - "admin-nav /admin link uses an EXACT match (pathname === \"/admin\"); a startsWith(\"/admin/\") would mark Dashboard active on every admin sub-route. The other links keep the prefix behavior."

patterns-established:
  - "Recharts AreaChart admin KPI chart mirrors the Phase-9 price-history chart 1:1 (ResponsiveContainer-in-h-64, same-height empty state, react-is sentinel test); swap LineChart->AreaChart, probability->volume, ts->day."
  - "Server-Component-fetches-initial + client-wrapper-owns-window-state + use-server-action-refetch: the canonical pattern for an interactive admin metric surface fed by a Bearer-gated endpoint."

requirements-completed: [ADD-01, ADD-02, ADD-03]

# Metrics
duration: ~6 min
completed: 2026-05-31
---

# Phase 10 Plan 04: KPI Dashboard (Slice C — Frontend) Summary

**El placeholder de `/admin` ahora ES el dashboard de KPIs: cinco `KpiCard` (24h volume, DAU con toggle 24h/7d/30d inline, active markets, pending resolutions, House P&L Today + All-time) + un `AreaChart` de Recharts de los buckets de volumen diario a 30 días con su empty state a la misma altura `h-64`, alimentado por un helper `"use server"` que reenvía el Bearer de admin a `GET /api/v1/admin/dashboard/kpis?window=` de Plan 10-02. El nav admin gana un link `Dashboard` (leading, match exacto) + `Branding`, y un flag `sessionStorage` marca `/admin` como landing. El dinero viaja y se renderiza como string end-to-end; un P&L negativo va en rojo, positivo en esmeralda. Implementa ADD-01 + ADD-02 + ADD-03 (frontend), D-01/D-02/D-06/D-11 y el contrato dashboard del 10-UI-SPEC.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-31T08:40:24Z
- **Completed:** 2026-05-31T08:46:24Z
- **Tasks:** 3 (TDD: RED Wave-0 test → lib+types+components GREEN → page+nav+flag build GREEN)
- **Files created/modified:** 11 (9 created, 2 modified)

## Accomplishments

- **ADD-01 — /admin is the KPI dashboard landing.** El placeholder de Phase 02-05 se reemplazó por un Server Component `force-dynamic` que hace `await fetchKpis("24h")` y renderiza el `KpiDashboard`. El operador llega aquí por el `redirect("/admin")` EXISTENTE de `adminLoginAction` (lib/auth.ts, sin tocar) — este plan NO añade ningún redirect; hace que `/admin` SEA el dashboard. Un flag `sessionStorage` (`admin_default_route` = `/admin`) marca el landing como UX hint a través de sesiones.
- **ADD-02 (frontend) — cinco KPI cards.** `KpiGrid` rinde 24h bet volume, Daily active users (con el toggle inline), Active markets, Pending resolutions y el `HousePnlCard` (Today + All-time). El dinero se muestra desde el string vía `formatMoney` (string ops, nunca `parseFloat` para storage); un P&L negativo va `text-red-500`, positivo/cero `text-emerald-600`; los ceros de fresh-deploy se ven como `$0.0000`, nunca "N/A". Un `kpi-card.test.tsx` guarda esta lógica de color + display.
- **ADD-03 (frontend) — Recharts AreaChart 30 días.** `VolumeChart` rinde los buckets diarios en un padre `h-64` fijo via `ResponsiveContainer`; con `<1` bucket muestra `VolumeChartEmptyState` ("No activity yet" / "Volume appears here as players place bets.") a la misma altura — nunca un eje en blanco. Stroke/fill `var(--brand-primary, #059669)` para que el chart se re-skinee con el branding (Plan 10-05) manteniendo el fallback esmeralda.
- **D-05 toggle DAU** — `DauWindowToggle` (24h/7d/30d, default 24h, `h-11` 44px touch target, `aria-pressed`) copiado del `WindowToggle` de price-history; el `KpiDashboard` cliente refetchea vía `fetchKpis(window)` en una `useTransition` y actualiza DAU + chart.
- **admin-nav (OWNED por este plan)** — link `Dashboard` leading con match EXACTO (`pathname === "/admin"`, no `startsWith` que lo marcaría activo en cada sub-ruta) + link `Branding` → la página de Plan 10-03 es ahora alcanzable desde el nav.
- **T-10-15 Bearer server-side** — `fetchKpis` vive en el módulo `"use server"` `kpi-api.ts`; lee `admin_jwt` con `cookies()` server-side; el `KpiDashboard` cliente llama a la acción exportada y nunca puede leer la cookie HttpOnly.
- **Verificación GREEN** — `volume-chart.test.tsx` (react-is sentinel `svg path.recharts-area-area` + empty state + toggle) y `kpi-card.test.tsx` (red-500/emerald-600 + `$0.0000`-no-N/A + money-string-verbatim) pasan 11/11; `pnpm build` exit 0 (`/admin` + `/admin/branding` compilan como rutas dinámicas `ƒ`).

## Task Commits

Cada tarea se commiteó atómicamente (ciclo TDD):

1. **Task 1: Wave-0 RED test** — `07b197e` (test) — `volume-chart.test.tsx` con el sentinel react-is (`svg path.recharts-area-area`), el empty state a `h-64` con la copy exacta del UI-SPEC, el título del chart y el `DauWindowToggle` 24h/7d/30d (default 24h, `aria-pressed`); copia los stubs `ResizeObserver` + `getBoundingClientRect` verbatim. Falla RED por módulos inexistentes.
2. **Task 2: lib + types + componentes GREEN** — `947b0fb` (feat) — `kpi-types.ts` (money fields string), `kpi-api.ts` (`"use server"` `fetchKpis`), `kpi-card.tsx` (`KpiCard`/`KpiGrid`/`HousePnlCard` + `formatMoney`/`isNegativeMoney`), `kpi-card.test.tsx`, `dau-window-toggle.tsx`, `volume-chart.tsx`. 11/11 vitest GREEN.
3. **Task 3: página + nav + flag, build GREEN** — `0e18221` (feat) — `kpi-dashboard.tsx` (wrapper cliente con estado de window + refetch en transition), `admin/page.tsx` (Server Component `force-dynamic` reemplazando el placeholder, try/catch → copy de error), `admin-nav.tsx` (Dashboard leading exact-match + Branding), `admin-default-route.tsx` (flag sessionStorage UX-only). `pnpm build` exit 0.

**Plan metadata:** committed con este SUMMARY.

## Files Created/Modified

- `frontend/src/lib/kpi-types.ts` — `KpiResponse` (5 cards + `volume_buckets`) + `VolumeBucket`; todos los money fields tipados `string` (nunca `number`).
- `frontend/src/lib/kpi-api.ts` — módulo `"use server"`: `fetchKpis(window)` reenvía `admin_jwt` Bearer a `GET /api/v1/admin/dashboard/kpis?window=` con `cache:"no-store"`; status preservado en el `Error` lanzado.
- `frontend/src/components/admin/kpi-card.tsx` — `KpiCard`, `KpiGrid` (5 cards, `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6`), `HousePnlCard` (Today/All-time color-by-sign), `formatMoney` + `isNegativeMoney` (string ops, sin float-para-storage). Labels `text-sm text-zinc-500`, values `text-2xl font-semibold tabular-nums`.
- `frontend/src/components/admin/kpi-card.test.tsx` — guarda la lógica de color (negativo red-500 / positivo+cero emerald-600), el `$0.0000`-no-N/A y el money-string verbatim (sin round-trip parseFloat).
- `frontend/src/components/admin/dau-window-toggle.tsx` — `DauWindowToggle` 24h/7d/30d (default 24h), `flex gap-1` `role="group"`, cada botón `variant secondary/ghost` + `aria-pressed` + `h-11`; `onChange` lifta el window al padre.
- `frontend/src/components/admin/volume-chart.tsx` — `VolumeChart` (`"use client"`, AreaChart en `h-64` parent, `var(--brand-primary, #059669)` stroke/fill, X axis `day`, parseFloat display-only) + `VolumeChartEmptyState` (`<1` bucket, misma altura). Título "Bet volume — last 30 days". react-is pin sin tocar.
- `frontend/src/components/admin/volume-chart.test.tsx` — sentinel react-is + empty state + toggle (Wave-0).
- `frontend/src/components/admin/kpi-dashboard.tsx` — `"use client"` wrapper: estado de window (default 24h), refetch via `fetchKpis` en `useTransition`, compone `KpiGrid` (toggle inline) + `VolumeChart`.
- `frontend/src/components/admin/admin-default-route.tsx` — `"use client"` diminuto que setea `sessionStorage.admin_default_route = "/admin"` (UX hint; nunca leído por auth/redirect — T-10-14).
- `frontend/src/app/admin/page.tsx` — Server Component `force-dynamic` reemplazando el placeholder; H1 "Dashboard" + subtext "Your platform at a glance.", `await fetchKpis("24h")` en try/catch (fallo → "Couldn't load dashboard metrics. Refresh the page to try again."), renderiza `<KpiDashboard initial={kpis} />` + `<AdminDefaultRoute />`.
- `frontend/src/components/admin/admin-nav.tsx` — `LINKS` con `Dashboard` (leading, `exact: true`) + `Branding`; la lógica activa usa `pathname === "/admin"` para el exacto y `startsWith` para el resto. Estilo `cn(...)` activo/inactivo sin cambios.

## Decisions Made

- **House P&L = UNA card, no dos.** El UI-SPEC lista "five cards" y describe P&L como una card con sub-captions Today/All-time. Implementé `HousePnlCard` mostrando ambos valores (cada uno coloreado por signo) en lugar de dos cards separadas, manteniendo el grid en cinco cards.
- **Signo y formato de dinero desde el string.** `isNegativeMoney` = leading `-` con un dígito 1-9 restante (así `-0.0000` cuenta como cero → esmeralda, no rojo); `formatMoney` rellena 4 decimales por manipulación de string. Cero strict respeto al contrato money-as-string de CLAUDE.md.
- **`var(--brand-primary)` con fallback emerald.** El stroke/fill del chart usa el token de branding para re-skinearse en vivo cuando Plan 10-05 inyecte la paleta del operador, con `#059669` como fallback (UI-SPEC A-CHART) si el token no está. El pin react-is de `pnpm.overrides` no se tocó.
- **Refetch en `useTransition`, error duro en el servidor.** El toggle DAU refetchea en una transición y conserva el último payload bueno ante un fallo transitorio; el caso de error inicial duro lo cubre el Server Component con la copy de KPI-load-error, no el wrapper cliente.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] El plan invoca `corepack pnpm ...`; `corepack` no está en el PATH del Bash de este host Windows**
- **Found during:** Task 1 (primer comando de verificación)
- **Issue:** Los `<verify>`/`<verification>` del plan usan `corepack pnpm vitest run ...` y `corepack pnpm build`. `corepack` no está disponible en el PATH del Bash de este host (mismo entorno que vieron Plans 10-01/10-02/10-03 — anotado en sus SUMMARYs y en el prompt de frontend_notes).
- **Fix:** Ejecuté `pnpm vitest run ...` y `pnpm build` directamente con `pnpm` 9.15.0 (el mismo binario que `corepack pnpm` resolvería, misma versión exacta del lockfile). Sin cambio de comportamiento ni de contrato.
- **Files modified:** ninguno (solo invocación de herramienta).
- **Verification:** los tests pasan 11/11 y `pnpm build` exit 0 igual.

### Documentation note (not a code deviation)

- **Cards lógicas vs. items del grid.** Las "five cards" del UI-SPEC se rinden como 5 items de grid (`HousePnlCard` es la quinta). Mi `KpiGrid` declara seis `KpiCard`/`HousePnlCard` slots en la primera redacción y se corrigió a cinco antes de cualquier commit (P&L como una sola card). Sin impacto en commits — el código commiteado ya rinde cinco cards.

---

**Total deviations:** 1 auto-fixed (1 blocking — herramienta `corepack`→`pnpm`, sin cambio de contrato).
**Impact on plan:** Cero scope creep. Las tres tareas se ejecutaron tal cual el plan; la única desviación es la invocación de la herramienta de empaquetado, idéntica a la de los planes hermanos de Phase 10.

## Issues Encountered

- **Warning de Recharts `width(-1) height(-1)` en stderr bajo jsdom.** Aparece en el test del chart (el mismo benigno que el análogo `price-history-chart.test.tsx` produce): jsdom no implementa layout real, así que el primer pase mide -1 antes de que el stub de `ResizeObserver` dispare el box 640×256. El sentinel `path.recharts-area-area` se renderiza igual y el test pasa GREEN — no es un fallo, es ruido de stderr esperado.
- **Aviso de Sentry en el build** (`onRouterTransitionStart` hook recomendado) — pre-existente, no bloqueante, fuera de alcance (pulido de Sentry en Phase 11). Lo vieron también 10-03.

## Authentication Gates

None — el Bearer de admin es el gate existente de Phase 8 (`admin_jwt` cookie → `current_active_admin`), reenviado server-side por `fetchKpis`. No se requirió auth externa.

## User Setup Required

None — cero paquetes nuevos. `recharts ^3.8.1` y `react-is 19.2.6` (con `pnpm.overrides`) ya estaban en `package.json` (T-10-SC: "No new packages this phase" — sin checkpoint de legitimidad de paquete).

## Threat Flags

None — toda la superficie introducida (un dashboard admin que hace un GET Bearer-gated, un toggle cliente que refetchea la misma acción, un chart Recharts, un flag sessionStorage) está cubierta por el `<threat_model>` del plan. Mitigaciones aplicadas: T-10-14 (flag escrito, nunca leído por auth — grep confirma que `admin_default_route` solo aparece en `admin-default-route.tsx`); T-10-15 (Bearer en el `"use server"` `kpi-api.ts`, la cookie HttpOnly nunca llega al cliente); T-10-16 (react-is pin intacto + `ResponsiveContainer` en `h-64` + el not-blank smoke test como sentinel). Sin endpoints/paths nuevos en trust boundaries.

## Known Stubs

None — el dashboard está cableado al endpoint real `GET /api/v1/admin/dashboard/kpis` de Plan 10-02; los valores money se muestran desde los strings del payload; el empty state del chart es el valor vacío correcto (`<1` bucket), no un placeholder. La página degrada a la copy de KPI-load-error en fallo de fetch (fallback defensivo documentado, no datos placeholder fluyendo a la UI).

## Next Phase Readiness

- **Plan 10-05 (runtime theming del player)** — el `VolumeChart` ya consume `var(--brand-primary)`, así que cuando 10-05 inyecte el `<style>:root{--brand-primary:...}` el chart se re-skinea sin más cambios.
- **Verificación / code-review de Phase 10** — los tres slices frontend (10-03 branding, 10-04 dashboard) y los backend (10-01/10-02) están completos; el nav admin enlaza Dashboard + Branding y la página de branding es alcanzable.
- Sin blockers. Cero nuevas dependencias; el lockfile no cambió.

## Self-Check: PASSED

- Los 9 archivos creados + 2 modificados existen en disco.
- Los 3 commits de tarea están en el historial (`07b197e`, `947b0fb`, `0e18221`).
- `<verification>` del plan re-corrida: 11/11 vitest GREEN; `pnpm build` exit 0 (`/admin` + `/admin/branding` rutas `ƒ`); `grep -F "dashboard/kpis" kpi-api.ts` = 2; `grep -F 'redirect("/admin")' auth.ts` = 1 (intacto); `grep -rln "admin_default_route" src/` = solo `admin-default-route.tsx`; `grep -F "h-64" volume-chart.tsx` matchea; `grep -E "red-500|emerald-600" kpi-card.test.tsx` matchea (5 emerald, 3 red).

---
*Phase: 10-admin-kpi-dashboard-configurable-branding*
*Completed: 2026-05-31*
