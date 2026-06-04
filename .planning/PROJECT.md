# XPredict

## What This Is

XPredict es una plataforma white-label de mercados de predicción. Los usuarios finales apuestan (con play money en v1) sobre eventos del mundo real: política, deportes, cripto, cultura. Para el operador (cliente futuro del SaaS), es un producto llave-en-mano para ofrecer prediction markets bajo su marca sin construir nada. La demo actual sirve para vender el concepto a un primer operador antes de invertir en multi-tenancy real.

## Core Value

El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de mercados de Polymarket y propios de la casa) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca — sin construir ni operar la pieza técnica.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**v1.0 MVP** (shipped 2026-06-04, Phases 1-12):
- ✓ Replicar y mostrar los top 25 mercados activos de Polymarket con sus odds actualizadas — v1.0
- ✓ Consumir resoluciones de Polymarket para liquidar automáticamente los mercados replicados — v1.0
- ✓ Admin puede crear, editar y resolver manualmente mercados "house" propios — v1.0
- ✓ Usuario puede registrarse, iniciar sesión y mantener sesión persistente (auth production-grade) — v1.0
- ✓ Usuario puede apostar con saldo virtual sobre cualquier mercado abierto — v1.0
- ✓ Wallet con transaction log auditable (depósitos, apuestas, liquidaciones, retiros virtuales) — v1.0
- ✓ Liquidación correcta de apuestas cuando se resuelve un mercado (payout, P&L, audit log) — v1.0
- ✓ Admin/CRM: ver usuarios, recargar saldo, banear, ver historial de actividad — v1.0
- ✓ Admin dashboard con métricas básicas (volumen apostado, usuarios activos, P&L de la casa) — v1.0
- ✓ Branding configurable a nivel de instancia (logo, paleta) — v1.0

**v1.1 Demo Polish** (shipped 2026-06-04, Fases A-E):
- ✓ White-label real: `--brand-*` propagado a TODA la superficie de jugador (CTAs, links, odds, charts) + tipografía de marca (`next/font`) + motion (`framer-motion`) — v1.1
- ✓ Seed & demo harness: un comando levanta una demo creíble (markets abiertos y resueltos, bets con P&L, histórico de odds); otro la resetea — v1.1
- ✓ Pulido jugador + operador: header-nav, microinteracciones, estados de carga/éxito/error no-silenciosos, loading skeletons admin, tablas responsive — v1.1
- ✓ Guion de venta + QA happy-path para una demo en vivo infalible — v1.1

### Active

<!-- Current scope. Empty between milestones — populate when v2.0 is scoped. -->

Ninguno activo — v1.0 + v1.1 enviados. Próximo milestone (v2.0) sin definir. Candidatos diferidos en Out of Scope (multi-tenancy real, dinero real, multi-outcome). Ejecuta `/gsd-new-milestone` para definir el siguiente.

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Dinero real / fiat / cripto** — v1 es play money. Real money exige licencia de juego (DGOJ en España), KYC, AML, integración con pasarela. Decisión: validar UX/venta antes de meterse en regulación.
- **Multi-tenancy real** — single-tenant en v1. Cuando entre el primer operador haremos refactor explícito. (Riesgo aceptado: trabajo extra en v2.)
- **Aplicaciones móviles nativas** — solo web responsive en v1. iOS/Android cuando haya validación comercial.
- **Integración live-bets** — defer hasta que live-bets v3 esté disponible. Source separado que se enchufa después.
- **Catálogo completo de Polymarket** — solo top 25 al inicio. Catálogo grande añade UX (búsqueda, filtros, paginación) que no aporta a la venta inicial.
- **Wallets cripto / on-chain / USDC** — Polymarket es solo fuente de datos/oráculo, no participamos en su economía on-chain.
- **Trading secundario / orderbook** — solo apuesta simple a precio actual (no se puede vender una posición antes de la resolución). Simplifica enormemente la lógica financiera.
- **Notificaciones push / email transaccional avanzado** — emails básicos sí (verificación, password reset). Marketing/engagement por email, no.
- **Programa de referidos / códigos promocionales** — nice-to-have, no esencial para la primera demo.

## Context

**Estado actual (2026-06-04).** v1.0 MVP (Phases 1-12) y v1.1 Demo Polish (Fases A-E) **enviados y cerrados** — todo en `main`. Producto: prediction market white-label play-money, production-grade, con demo pulida y white-label real en la superficie de jugador. Sigue en **modo venta** (sin operador comprometido, sin multi-tenancy real, sin dinero real). Próximo milestone (v2.0) sin definir. Historial de fases archivado en `.planning/milestones/v1.0-phases/`; resúmenes en `.planning/MILESTONES.md`.

**Origen.** Proyecto greenfield iniciado 2026-05-25 por Pol Bonet (PM/Tech Lead) y Cuco (Dev). Workflow colaborativo GSD con Linear + Slack + GitHub configurado en `.claude/`.

**Por qué Polymarket como fuente.** Polymarket es la referencia mundial de prediction markets, tiene un catálogo masivo, una Gamma API REST pública y consistente, y un sistema de oráculo (UMA) que resuelve mercados de forma fiable. Usarlo como fuente de datos + oráculo de resolución nos da credibilidad de catálogo sin tocar blockchain, sin custodia de cripto, y sin tener que construir un sistema de resolución desde cero.

**Por qué play money con seguridad de producción.** Es la trampa común en demos: hacer algo "rápido y sucio" porque "es solo demo". Pero cuando un comprador serio mira el código, ve la trampa. La decisión de Pol es construir la base como si fuera real (audit log, wallet con doble entrada contable, transacciones ACID, auth con hash moderno) pero sin conectar pasarela real. El día que se venda, se conecta Stripe sin tocar el core.

**Ecosistema técnico relacionado.** Pol tiene en producción [live-bets](../../live-bets/) — plataforma de apuestas en directo sobre tráfico de coches (Python + FastAPI + Postgres + Redis + Docker). XPredict comparte stack precisamente para que la integración futura sea trivial (mismos modelos pydantic, mismos patrones, mismas convenciones).

**Equipo y nivel.** Pol es PM y experto suficiente en Python/FastAPI. Cuco es el Dev (perfil técnico exacto TBD — se asume frontend razonable o aprendizaje rápido).

## Constraints

- **Tech stack**: Python 3.12 + FastAPI + SQLAlchemy + Postgres 16 + Redis + Celery (backend); Next.js 15 + TypeScript + Tailwind + shadcn/ui (frontend) — fijado por integración futura con live-bets (Python) y por exigencia de calidad de UI para la venta.
- **Security**: Production-grade desde v1 — Argon2/bcrypt para passwords, JWT/sesiones seguras, transacciones ACID, audit log inmutable, sin secretos en código, rate-limiting.
- **Tenancy**: Single-tenant en v1, pero schema preparado (campos `tenant_id` fantasma se valorará durante diseño de DB).
- **Money model**: Solo play money. Nada de dinero real ni cripto en v1 (decisión explícita para evitar regulación).
- **Polymarket data source**: Gamma API REST pública (gamma-api.polymarket.com), polling cada N segundos vía Celery. No on-chain.
- **Auth provider**: Self-hosted (FastAPI-users o equivalente). Sin dependencia de SaaS externo de auth (Clerk/Auth0) porque white-label SaaS futuro no debe forzar al cliente operador a pagar a un tercero.
- **Deploy target inicial**: Docker + docker-compose para dev local; staging en Fly.io o Railway (TBD).
- **Timeline**: Sin presión de fecha. "Hazlo bien" — calidad sobre velocidad.
- **Repo**: Mono-repo (`xpredict/`) con `backend/` y `frontend/` como subcarpetas. Git en GitHub. Linear para issues. Slack para notificaciones.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Polymarket como inspiración + oráculo, no como reseller | Evita custodia cripto, KYC, complejidad on-chain. Catálogo creíble sin pagar nada. | ✓ Good — Phases 6-7: Gamma sync (top-25) + UMA auto-resolution shipped, sin tocar on-chain |
| Play money en v1 con arquitectura production-grade | Valida UX/venta sin entrar en regulación. Cero deuda técnica el día que se conecte Stripe. | Confirmed — Phase 01: money-column lint + NUMERIC(18,4) + Decimal alias shipped, CI enforces at every PR |
| House markets con resolución manual desde admin | Mantiene el sistema simple. Admin tiene control total sobre outcomes de mercados propios. | ✓ Good — Phases 4/5/12: house CRUD + resolve/reverse UI con justificación + two-step confirm |
| Single-tenant en v1, refactor a multi-tenant en v2 | Velocidad ahora. Pol acepta el coste de refactor consciente. | Confirmed — Phase 01: tenant_id ghost column on audit_log + feature_flags; schema seam in place |
| Stack: FastAPI (backend) + Next.js (frontend) | UI necesita parecer SaaS real para vender; backend Python para integrar live-bets más adelante. | Confirmed — Phase 01: 8-service docker-compose (FastAPI + Next.js 15) boots in one command, all health checks green |
| Auth self-hosted (FastAPI-users) | White-label SaaS no debe forzar al operador a pagar Clerk/Auth0 también. | ✓ Confirmed — Phase 2: Argon2id, email verify, password reset, refresh-token rotation + rate-limiting shipped |
| Top 25 mercados de Polymarket al inicio (no catálogo completo) | Suficiente para la demo, evita UX cara (search/filters/paginación) que no aporta a la venta. | ✓ Good — Phase 6: top-25 mirror shipped; catálogo ancho sigue fuera de scope (v2) |
| Demo sin timeline ni presión de fecha | Calidad sobre velocidad — el demo debe convencer a un comprador, no llegar a tiempo. | ✓ Good — v1.0 + v1.1 enviados manteniendo calidad production-grade, sin atajos |
| v1.1 ejecutado fuera del grid numerado (worktrees + PRs) antes de materializar el milestone | Fases A→C independientes de Phase 12 podían arrancar antes del cierre de v1.0; se evitó el `phases.clear` destructivo de `/gsd-new-milestone`. | ⚠️ Revisit — funcionó pero dejó `.planning/` desincronizado; reconciliado el 2026-06-04. Materializar milestones ANTES de ejecutar en el futuro |
| Workflow colaborativo GSD con Linear + Slack | Pol = PM aprueba PRs, Cuco = Dev ejecuta fases. 1 PR por fase, AI review automático. | Confirmed — Phase 01 ejecutada en ~83 min con GSD full-cycle (discuss → plan → execute → verify → review) |
| uv (Python) + pnpm (Node) como gestores de dependencias | Velocidad de resolución + lockfiles deterministas en CI/docker | Confirmed — Phase 01: ambos integrados en docker multi-stage y GitHub Actions sin fricción |
| Celery Beat con RedBeat scheduler (Redis distributed lock) | Evita que dos instancias de beat corran en paralelo en deploy multi-pod | Confirmed — Phase 01: bug encontrado y corregido (flag -S conflictaba con señal beat_init; eliminado) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-04 after v1.0 + v1.1 milestone close. v1.0 MVP (Phases 1-12) and v1.1 Demo Polish (Fases A-E) both shipped and archived — see MILESTONES.md; phase history in milestones/v1.0-phases/. Reconciliation: v1.1 was executed off the formal grid (worktrees + PRs #19/#22/#23/#24) and is now recorded. Next: scope v2.0 via /gsd-new-milestone. Carried-forward items in STATE.md › Deferred Items (incl. non-deferrable Spanish legal review of ToS/token policy before any live operator demo).*
