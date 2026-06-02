---
phase: 10-admin-kpi-dashboard-configurable-branding
plan: 03
subsystem: frontend
tags: [branding, white-label, admin-form, rhf, zod, server-action, multipart, sonner, vitest]

# Dependency graph
requires:
  - phase: 10-admin-kpi-dashboard-configurable-branding
    plan: 01
    provides: "GET/PUT /api/v1/admin/tenant-config (Bearer-gated, multipart logo, hex 422), TenantConfigRead shape"
  - phase: 08-admin-crm-user-management-audit-log-viewer
    provides: "admin-api.ts use-server Bearer-forward pattern (admin_jwt cookie -> Authorization Bearer), admin-types.ts type-separation, recharge-form.tsx RHF+zod analog"
provides:
  - "/admin/branding route (Server Component, force-dynamic) pre-filling the current persisted config"
  - "BrandingForm (RHF+zod) with ColorField live swatch + LogoUploadField object-URL preview + client hex/logo mirror"
  - "branding-admin-api.ts use-server lib: fetchTenantConfig() GET + updateTenantConfig() multipart PUT, Bearer forwarded server-side, status preserved in thrown Error"
  - "branding-types.ts: TenantConfigRead + BrandingUpdateInput (use-server type-separation)"
affects: [10-04 admin-nav Branding link, 10-05 player runtime theming]

# Tech tracking
tech-stack:
  added: []   # zero new packages — all frontend deps already present (RESEARCH §Standard Stack)
  patterns:
    - "use-server admin Bearer-forward reused verbatim from admin-api.ts (admin_jwt HttpOnly cookie -> Authorization Bearer, server-side only) — T-10-11 mitigation"
    - "Multipart PUT via FormData with NO manual Content-Type (fetch derives the multipart boundary)"
    - "Client zod/size/type checks are UX-only; server is authoritative (D-09) — a 422 thrown error maps to inline FormMessage on the hex fields"
    - "ColorField = FormControl-wrapped Input + sibling swatch <div> (swatch OUTSIDE FormControl so the Slot id lands on the labellable <input>)"
    - "Logo object-URL preview via URL.createObjectURL rendered through <img src> (SVG-in-img never executes script — T-10-13), revoked on unmount"

key-files:
  created:
    - frontend/src/lib/branding-types.ts
    - frontend/src/lib/branding-admin-api.ts
    - frontend/src/components/admin/branding-form.tsx
    - frontend/src/app/admin/branding/page.tsx
    - frontend/src/components/admin/branding-form.test.tsx
  modified: []

key-decisions:
  - "ColorField puts the swatch <span> OUTSIDE FormControl: the shadcn FormControl is a Radix Slot that forwards the FormItem id to its FIRST child; a wrapping <div> would steal the label association and make getByLabelText fail. Swatch sibling + FormControl-wrapped Input keeps the label bound to the real <input>."
  - "422 thrown error -> setError on BOTH hex fields with the UI-SPEC hex copy. The endpoint's only field-level 422 is the hex pattern; brand_name (min 1) and logo (size/type) are also server-validated, but the client mirror blocks those before submit, so the 422 branch surfaces the hex contract."
  - "Logo client pre-check ORDER: content-type allowlist -> 256KB size cap (mirrors the Plan 10-01 server order). A bad/oversize file blocks submit and clears the staged file; it never silently PUTs an invalid logo."
  - "Page degrades to XPredict defaults (#4f46e5/#0ea5e9) on a fetch failure rather than crashing — defensive fallback, consistent with the public /branding/current default behavior in 10-01."

patterns-established:
  - "use-server branding lib mirrors admin-api.ts 1:1; shared types live in a sibling non-use-server module (Next constraint)."
  - "Form field with an auxiliary visual (swatch): keep the auxiliary element a sibling of FormControl so label/aria associations stay on the input."

requirements-completed: [ADD-05]

# Metrics
duration: ~14 min
completed: 2026-05-31
---

# Phase 10 Plan 03: Admin Branding Form (Slice A — Frontend) Summary

**Una página `/admin/branding` (Server Component `force-dynamic`) que pre-carga la config persistida vía un helper `"use server"` con reenvío de Bearer, más un `BrandingForm` RHF+zod (nombre de marca + `ColorField` primario/secundario con swatch en vivo + `LogoUploadField` con preview por object-URL) que hace un PUT multipart al endpoint admin de Plan 10-01. El servidor es autoritativo sobre la validación (D-09); el cliente espeja hex/logo solo para UX. Implementa ADD-05 (mitad operador), D-07, D-09 y el contrato de copy/spacing/color del 10-UI-SPEC.**

## Performance

- **Duration:** ~14 min
- **Tasks:** 3 (TDD: RED → use-server lib + types → BrandingForm + page GREEN)
- **Files created/modified:** 5 (5 created, 0 modified)

## Accomplishments

- **ADD-05 (UI de operador)** — el admin abre `/admin/branding` y ve el nombre de marca + ambos hex + (futuro) logo pre-rellenados desde el backend; edita nombre/paleta/logo; guarda; recibe un toast de éxito. La paleta inválida y los logos malos muestran errores inline claros.
- **Contrato 10-UI-SPEC honrado al pie de la letra** — copy exacta (`Brand name`, `Primary color`, `Secondary color`, `Logo`, helper `PNG, JPEG, WebP or SVG. Max 256 KB.`, CTA `Save branding`, toasts y mensajes de error verbatim), shell `mx-auto max-w-6xl px-6 py-12`, campos `gap-4`, H1 `text-3xl font-semibold tracking-tight` + subtext, y un submit `Save branding` de variante **default no-destructiva** (A-SAVE).
- **Bearer server-side (T-10-11)** — el token `admin_jwt` se lee solo en el módulo `"use server"` (`cookies()`); el componente cliente llama a la acción exportada y nunca puede leer la cookie HttpOnly. Reutiliza el patrón probado de `admin-api.ts`.
- **PUT multipart (contrato 10-01)** — `updateTenantConfig` envía `brand_name` + 2 hex + `logo` opcional como `FormData` sin Content-Type manual (fetch deriva el boundary). El status del backend se preserva en el `Error` lanzado (`"API error: 422"`) para que el form ramifique en 422.
- **TDD** — 7/7 tests vitest en GREEN: pre-fill + swatch en vivo, swatch se actualiza al teclear, hex inválido muestra FormMessage y NO llama a la acción, submit válido llama a la acción una vez + toast de éxito, preview de logo `<img>`, logo grande → copy de cap, logo de tipo malo → copy de allowlist.
- **Build de Next exit 0** — `/admin/branding` aparece como ruta `ƒ` (server-rendered on demand, coherente con `force-dynamic`).

## Task Commits

Cada tarea se commiteó atómicamente (ciclo TDD):

1. **Task 1: vitest RED** — `62f8084` (test) — `branding-form.test.tsx` con los cuatro contratos de `<behavior>` contra la copy exacta del UI-SPEC; mockea la acción `updateTenantConfig` (sin red) + `sonner`; stub de `URL.createObjectURL`. Falla RED por módulo inexistente.
2. **Task 2: lib use-server + types** — `d83f927` (feat) — `branding-types.ts` (`TenantConfigRead` + `BrandingUpdateInput`) + `branding-admin-api.ts` (`"use server"`, `fetchTenantConfig` GET, `updateTenantConfig` PUT multipart, Bearer reenviado, status preservado).
3. **Task 3: BrandingForm + page GREEN** — `370c16b` (feat) — `branding-form.tsx` (RHF+zod, `ColorField` + `LogoUploadField`) + `admin/branding/page.tsx` (Server Component `force-dynamic`). 7/7 vitest GREEN; build exit 0.

**Plan metadata:** committed con este SUMMARY.

## Files Created/Modified

- `frontend/src/lib/branding-types.ts` — tipos planos `TenantConfigRead { brand_name, primary_hex, secondary_hex, logo_url }` + `BrandingUpdateInput { brand_name, primary_hex, secondary_hex, logo? }`. Separados del módulo `"use server"` (constraint de Next).
- `frontend/src/lib/branding-admin-api.ts` — módulo `"use server"`: `bearerHeader()` lee `admin_jwt` server-side; `fetchTenantConfig()` GET (no-store, Bearer); `updateTenantConfig()` PUT `FormData` multipart (sin Content-Type manual). Status del backend preservado en el `Error`.
- `frontend/src/components/admin/branding-form.tsx` — `"use client"`: `BrandingForm` RHF+zod (hex `^#[0-9a-fA-F]{6}$`), `ColorField` (Input + swatch en vivo, neutral en inválido), `LogoUploadField` (file input PNG/JPEG/WebP/SVG + preview `<img>` object-URL + pre-check 256KB/allowlist). Submit `Save branding` default-variant + `Loader2`; 422 → FormMessage inline; toasts de éxito/fallo.
- `frontend/src/app/admin/branding/page.tsx` — Server Component `force-dynamic`, shell `max-w-6xl px-6 py-12`, H1 `Branding` + subtext, `await fetchTenantConfig()` con try/catch degradando a defaults, renderiza `<BrandingForm initial={...} />`.
- `frontend/src/components/admin/branding-form.test.tsx` — 7 tests vitest cubriendo los cuatro `<behavior>` contra la copy exacta del UI-SPEC.

## Decisions Made

- **Swatch fuera de `FormControl`.** El `FormControl` de shadcn es un Radix `Slot` que reenvía el `id` del `FormItem` a su PRIMER hijo. Un `<div>` envolvente robaba la asociación del label (el `<div>` no es etiquetable → `getByLabelText("Primary color")` fallaba). El swatch como hermano + `FormControl` envolviendo solo el `<Input>` mantiene el label ligado al `<input>` real.
- **422 → `setError` en ambos hex.** El único 422 a nivel de campo del endpoint es el patrón hex; `brand_name` (min 1) y logo (size/type) también se validan en servidor, pero el espejo cliente los bloquea antes del submit, así que la rama 422 expone el contrato hex.
- **Pre-check de logo en orden allowlist → cap** (espeja el orden del servidor en 10-01). Un archivo malo/grande bloquea el submit y limpia el archivo staged; nunca hace PUT de un logo inválido.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `ColorField` rompía la asociación label↔input (swatch dentro de `FormControl`)**
- **Found during:** Task 3 (GREEN run inicial — 3 tests de color en rojo)
- **Issue:** El `<div className="flex">` que envolvía swatch + Input dentro de `FormControl` recibía el `id` del label (el `Slot` lo pasa al primer hijo), dejando el `<input>` sin asociar. `getByLabelText("Primary color")` fallaba con "element associated with this label (`<div />`) is non-labellable".
- **Fix:** Mover el swatch `<span>` a hermano del `FormControl`; el `FormControl` envuelve solo el `<Input>`, así el `id` aterriza en el `<input>` etiquetable.
- **Files modified:** frontend/src/components/admin/branding-form.tsx
- **Commit:** 370c16b

**2. [Rule 1 - Bug] El test de logo de tipo malo no podía ejercitar el pre-check (filtro `accept` de user-event)**
- **Found during:** Task 3 (GREEN run inicial — test wrong-type logo en rojo)
- **Issue:** `userEvent.upload` con `applyAccept` por defecto (`true`) descarta un archivo cuyo `type` no matchea el `accept` del input (verificado empíricamente: `FILES_LENGTH=0` para un PDF en un input de imágenes). El `onChange` nunca recibía el archivo, así que el pre-check de allowlist del componente no corría y el copy no aparecía.
- **Fix:** `userEvent.setup({ applyAccept: false })` SOLO en ese caso, para ejercitar el pre-check defensivo del componente (un archivo puede llegar por el picker "todos los archivos" o drag-drop). El componente conserva su `accept` para la UX del navegador real; el pre-check JS es la defensa que el test afirma.
- **Files modified:** frontend/src/components/admin/branding-form.test.tsx
- **Commit:** 370c16b

---

**Total deviations:** 2 auto-fixed (2 bugs, ambos en el ciclo GREEN de Task 3).
**Impact on plan:** Sin scope creep. El fix #1 es el comportamiento correcto del patrón shadcn Form; el fix #2 es fidelidad del harness de test al comportamiento que el propio test afirma. Sin cambios de copy ni de contrato.

## Issues Encountered

- **`corepack` no está en PATH** en el Bash de este host Windows; `pnpm` 9.15.0 está disponible directamente, así que el plan `corepack pnpm ...` se ejecutó como `pnpm ...` (mismo binario, mismo resultado). El backend de 10-01/10-02 vio lo mismo; sin impacto en el contrato.
- **Aviso de Sentry en el build** (`onRouterTransitionStart` hook recomendado) — pre-existente, no bloqueante, fuera de alcance (Phase 11 pulido de Sentry).

## Authentication Gates

None — el Bearer de admin es el gate existente de Phase 8 (`admin_jwt` cookie → `current_active_admin`), reenviado server-side. No se requirió auth externa.

## User Setup Required

None — cero paquetes nuevos; cada dependencia ya estaba presente.

## Threat Flags

None — toda la superficie introducida (un form admin que hace PUT multipart, un GET pre-fetch, un preview de logo por object-URL) está cubierta por el `<threat_model>` del plan (T-10-11 Bearer server-side, T-10-12 validación cliente UX-only/servidor autoritativo, T-10-13 preview `<img>` sin ejecución de script). Sin endpoints/paths nuevos en trust boundaries más allá del contrato de 10-01.

## Known Stubs

None — el form está completamente cableado a la acción real `updateTenantConfig`; el preview usa un object-URL real; los defaults de la página son un fallback defensivo documentado (no datos placeholder fluyendo a la UI). La consumo del logo por el player (re-skin runtime) es Plan 10-05, declarado como out-of-scope aquí por el plan.

## Next Phase Readiness

- **Plan 10-04 (admin-nav)** añade el link "Branding" → `/admin/branding`; la ruta ya existe y es alcanzable por URL directa (NAV NOTE del plan: verificar 10-03 en aislamiento NO debe marcar la ausencia del link de nav como defecto).
- **Plan 10-05 (runtime theming del player)** consume la paleta/logo que este form persiste vía el endpoint público `/branding/current` + `/branding/logo` de 10-01.
- Sin blockers.

## Self-Check: PASSED

- Los 5 archivos creados existen en disco (verificado).
- Los 3 commits de tarea están en el historial (`62f8084`, `d83f927`, `370c16b`).
- `<verification>` del plan re-corrida: 7/7 vitest GREEN; `pnpm build` exit 0 (`/admin/branding` compila como ruta dinámica); `grep -E "use server|admin_jwt"` matchea ambos; `grep -F "Save branding"` y `grep -F "Enter a valid hex color, e.g. #4F46E5."` matchean. Sin errores de typecheck nuevos (único error repo-wide = DEF-FE-01 orphan `middleware.test.ts`, pre-existente y fuera de alcance).

---
*Phase: 10-admin-kpi-dashboard-configurable-branding*
*Completed: 2026-05-31*
