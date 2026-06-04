# Phase 6: Polymarket Sync (Catalog Replication) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 6-Polymarket Sync (Catalog Replication)
**Areas discussed:** Market list sorting, Source badge design, Market disappearance & lifecycle

---

## Market List Sorting

| Option | Description | Selected |
|--------|-------------|----------|
| House markets al final | Primero los 25 de Polymarket por volumen, después los house por fecha | |
| House markets con volume=0 | Aparecen al fondo del ranking naturalmente | |
| House markets primero | House markets arriba (por fecha desc), luego Polymarket por volumen 24h | ✓ |

**User's choice:** House markets primero (free-text: "los de la casa se mostraran los primeros por defecto por ahora")
**Notes:** Decisión de producto — el operador quiere sus mercados propios siempre destacados sobre el contenido replicado.

---

## Source Badge Design

| Option | Description | Selected |
|--------|-------------|----------|
| Badge discreto | Chip pequeño abajo-derecha: "Polymarket" con link o "House" sin link | ✓ |
| Badge prominente | Banner superior con icono: "Synced from Polymarket" con link | |
| Tú decides | Claude elige el diseño que mejor encaje con shadcn/ui | |

**User's choice:** Badge discreto
**Notes:** No distrae del contenido principal de la card.

---

## Market Disappearance & Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Se queda visible | Mercado sigue OPEN y visible aunque salga del top-25 | |
| Se oculta del listado | Flag `in_top25=false`, no aparece en lista pero sigue en DB | |
| Top-25 rotation con persistencia | Se actualizan con cada poll, se guardan en DB, home muestra solo top-25 vivo | ✓ |

**User's choice:** Top-25 rotation (free-text: "para esta version quiero que se vayan actualizando, deberan guardarse en bd si osi por si la gente apuesta")
**Notes:** Mercados que caen del top-25 persisten en DB por apuestas. Visibles en portfolio aunque no en home. Visión futura: copiar mercados de Polymarket pero apuestas in-house.

---

## Portfolio Visibility (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Sí, vía portfolio | Mercado no en home pero accesible en portfolio y por URL directa | ✓ |
| Tú decides | Claude diseña el flujo más lógico | |

**User's choice:** Sí, vía portfolio (free-text: "si en el portfolio se mostrara toda la actividad. mas tarde implementaremos busqueda y categorias de mercados")
**Notes:** Búsqueda y categorías vendrán en fase futura.

---

## Claude's Discretion

- Gamma client architecture (httpx.AsyncClient lifecycle, tenacity retry, timeouts)
- Redis dedupe lock (TTL, key pattern, auto-expiry)
- Pydantic parser extra mode toggle (dev vs staging)
- Market card layout (shadcn/ui conventions)
- Slug generation for mirrored markets
- Migration naming and test organization
- VCR fixture strategy

## Deferred Ideas

- **Búsqueda y categorías de mercados** — future phase
- **Copia completa de mercados Polymarket con apuestas in-house** — v2
