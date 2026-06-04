# XPredict

## What This Is

XPredict es una plataforma white-label de mercados de predicción. Los usuarios finales apuestan (con play money en v1) sobre eventos del mundo real: política, deportes, cripto, cultura. Para el operador (cliente futuro del SaaS), es un producto llave-en-mano para ofrecer prediction markets bajo su marca sin construir nada. La demo actual sirve para vender el concepto a un primer operador antes de invertir en multi-tenancy real.

## Core Value

El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de mercados de Polymarket y propios de la casa) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca — sin construir ni operar la pieza técnica.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- v1 hypotheses. Building toward these. -->

- [ ] Replicar y mostrar los top 25 mercados activos de Polymarket con sus odds actualizadas
- [ ] Consumir resoluciones de Polymarket para liquidar automáticamente los mercados replicados
- [ ] Admin puede crear, editar y resolver manualmente mercados "house" propios
- [ ] Usuario puede registrarse, iniciar sesión y mantener sesión persistente (auth production-grade)
- [ ] Usuario puede apostar con saldo virtual sobre cualquier mercado abierto
- [ ] Wallet con transaction log auditable (depósitos, apuestas, liquidaciones, retiros virtuales)
- [ ] Liquidación correcta de apuestas cuando se resuelve un mercado (payout, P&L, audit log)
- [ ] Admin/CRM: ver usuarios, recargar saldo, banear, ver historial de actividad
- [ ] Admin dashboard con métricas básicas (volumen apostado, usuarios activos, P&L de la casa)
- [ ] Branding configurable a nivel de instancia (logo, paleta) — semilla para multi-tenant v2

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
| Polymarket como inspiración + oráculo, no como reseller | Evita custodia cripto, KYC, complejidad on-chain. Catálogo creíble sin pagar nada. | — Pending |
| Play money en v1 con arquitectura production-grade | Valida UX/venta sin entrar en regulación. Cero deuda técnica el día que se conecte Stripe. | Confirmed — Phase 01: money-column lint + NUMERIC(18,4) + Decimal alias shipped, CI enforces at every PR |
| House markets con resolución manual desde admin | Mantiene el sistema simple. Admin tiene control total sobre outcomes de mercados propios. | — Pending |
| Single-tenant en v1, refactor a multi-tenant en v2 | Velocidad ahora. Pol acepta el coste de refactor consciente. | Confirmed — Phase 01: tenant_id ghost column on audit_log + feature_flags; schema seam in place |
| Stack: FastAPI (backend) + Next.js (frontend) | UI necesita parecer SaaS real para vender; backend Python para integrar live-bets más adelante. | Confirmed — Phase 01: 8-service docker-compose (FastAPI + Next.js 15) boots in one command, all health checks green |
| Auth self-hosted (FastAPI-users) | White-label SaaS no debe forzar al operador a pagar Clerk/Auth0 también. | — Pending (Phase 02) |
| Top 25 mercados de Polymarket al inicio (no catálogo completo) | Suficiente para la demo, evita UX cara (search/filters/paginación) que no aporta a la venta. | — Pending |
| Demo sin timeline ni presión de fecha | Calidad sobre velocidad — el demo debe convencer a un comprador, no llegar a tiempo. | — Pending |
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
*Last updated: 2026-06-04 after Phase 12 (Admin Market Operations UI & Player Resolution Display) — v1.0 closure phase complete: STL-06 player resolution display, admin market-management UI (list/create/edit/close), admin resolve/reverse/force-settle two-step dialogs, and per-market stake limits (BET-06). All 11 phase requirements verified at code level; code-review blocker CR-01 (BET-06 persistence) fixed in cb55197; 3 PM-accepted human-verify items tracked in 12-HUMAN-UAT.md. Pending before archive: /gsd-secure-phase 12 → ship (rebase onto diverged origin/main) → v1.0 re-audit.*
