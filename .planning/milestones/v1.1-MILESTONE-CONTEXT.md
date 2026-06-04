---
milestone: v1.1
name: Demo Polish
status: drafted (pending v1.0 close)
driver: sales-mode demo polish
created: 2026-06-03
depends_on: "Phase 12 (v1.0 closure — admin market-ops UI + player resolution display)"
approved_by: Pol
---

# Milestone v1.1 — "Demo Polish"

## Goal

Elevar el demo de XPredict de *"funciona end-to-end"* a *"se vende solo"*: acabado
premium y **white-label real**, para cerrar la venta a un primer operador.
Modo venta — sin multi-tenancy ni dinero real. Es un milestone de **ACABADO**, no de
features nuevas.

## Driver / Context

Seguimos en modo venta-demo (no hay operador comprometido aún). Objetivo de Pol:
*"una demo pulida a la perfección"*. v1.1 se construye **ENCIMA** de la fase de cierre
de v1.0 (Phase 12), que arregla los 3 blockers funcionales (admin gestiona/resuelve
markets, player ve la resolución) — v1.1 da esos por hechos y los pule.

## Key findings (mapeo de frontend, 2026-06-03)

1. **White-label cosmético** — el theming está cableado (layout inyecta `--brand-*`),
   pero esos tokens solo se consumen en **2 sitios** (dot del logo + stroke del chart
   admin). Cambiar la marca de operador apenas pinta. **Item de mayor ROI de venta.**
2. **Cero seed data** — `make seed` es no-op literal; solo existe `create_admin.py`.
   Una demo en frío muestra TODAS las pantallas del jugador vacías. **Bloqueante (entregable #0).**
3. El admin CRM (tablas) es lo más pulido; el jugador degrada errores en silencio
   (wallet/portfolio muestran "0"/vacío indistinguible de fallo de carga).
4. Sin navegación de jugador (header-nav), sin animaciones (no framer-motion),
   system font (sin next/font), sin boundaries globales (not-found/global-error).

Stack frontend: Next 16.2 (App Router/RSC) · React 19 · Tailwind v4 (config en globals.css)
· shadcn/ui new-york · TanStack Table · Recharts · sonner · lucide. Sin librería de motion.

## Target features — 5 fases

> Numeración la fija el roadmapper, **continuando** tras la fase de cierre de v1.0.

### Fase A — Design system brand-aware (fundación)
Propagar `--brand-*` a los primitivos (button/CTA "Place bet", links, badges, focus,
odds bar, charts) + tipografía de marca (`next/font`) + tokens de motion (framer-motion).
**Criterio:** cambiar la paleta en `/admin/branding` re-skinea TODA la UI del jugador
(CTAs, links, odds, charts), verificado con 2 paletas distintas.

### Fase B — Seed & demo harness (entregable #0)
Script de seed realista (usuarios, markets house+mirrored, abiertos **y resueltos**,
bets con P&L, histórico de odds para charts) + `demo-reset`.
**Criterio:** un comando levanta una demo creíble con cero pantallas vacías; otro la resetea.

### Fase C — Pulido jugador
Header-nav (Markets·Wallet·Portfolio·sesión), microinteracciones (cards, odds live,
confirm-bet), estados de éxito con peso (post-bet/settle), errores no-silenciosos +
loading states en wallet/portfolio, `not-found`/`global-error` con marca, responsive.
**Criterio:** recorrido jugador completo sin baches ni degradación silenciosa.

### Fase D — Pulido operador *(depende de Phase 12 mergeada)*
Subir el admin (incl. markets/resolve UI que entrega Phase 12) a la consistencia premium
del CRM: loading states faltantes (dashboard/branding/detalle), tablas responsive,
panel completo sin placeholders muertos.
**Criterio:** el panel que el comprador usaría se siente terminado y potente.

### Fase E — QA de demo / guion
Guion de venta paso a paso, QA E2E cross-browser + responsive, performance, cuentas
pre-pobladas. El happy-path infalible.
**Criterio:** una demo en vivo siguiendo el guion no falla nunca.

## Scope decisions (aprobadas por Pol, 2026-06-03)

1. **Animaciones: SÍ** — añadir `framer-motion` (hoy no hay librería de motion).
2. **Tipografía: SÍ** — `next/font` con fuente premium (Geist o Inter) vs system font.
3. **Branding real: solo superficie JUGADOR** de momento (admin brand-aware en Fase D).
4. **Versión: v1.1 "Demo Polish"** — se reserva v2.0 para multi-tenant/real-money.

## Out of scope (→ backlog / v2.0+)

- **Multi-tenancy real** — v2.0 (el "refactor explícito" de PROJECT.md).
- **Dinero real / Stripe** — v2.0+ (regulación DGOJ/KYC/AML; diferido a propósito).
- **Multi-outcome markets** — cambio de modelo (CHECK binary-only en DB, settlement, odds, UI); merece milestone propio.
- **Catálogo ancho** — search/filtros/paginación más allá del top-25 (Pol ya lo descartó en v1 por "no aporta a la venta inicial").

## Orden / dependencias

- **A → B → C** son independientes de Phase 12; pueden arrancar antes de que v1.0 cierre.
- **D** y el pulido del player-resolution-display dependen de Phase 12 mergeada.
- **Materialización formal** (`/gsd-new-milestone v1.1`) DEBE esperar a
  `/gsd-complete-milestone v1.0` (que requiere Phase 12 mergeada): `gsd-new-milestone`
  ejecuta `phases.clear` (borraría el dir de Phase 12) y resetea STATE asumiendo v1.0 cerrado.
