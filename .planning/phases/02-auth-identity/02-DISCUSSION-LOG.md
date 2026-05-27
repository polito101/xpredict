# Phase 2: Auth & Identity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-26
**Phase:** 2-Auth & Identity
**Areas discussed:** fastapi-users vs hand-rolled, Email SMTP, Users schema, Admin bootstrapping/Frontend

---

## fastapi-users vs hand-rolled

| Option | Description | Selected |
|--------|-------------|----------|
| fastapi-users v14 | Lib battle-tested, dual-backend, Argon2id built-in, email verify + reset incluidos. Ahorra ~400 líneas. | ✓ |
| Hand-rolled (passlib + PyJWT) | Control total, patrón modular puro, ~600-800 líneas extra. | |

**User's choice:** fastapi-users v14

---

### Integración con Base SQLAlchemy

| Option | Description | Selected |
|--------|-------------|----------|
| Herencia múltiple `User(SQLAlchemyBaseUserTableUUID, Base)` | Patrón oficial de fastapi-users. tenant_id se añade normalmente. | ✓ |
| You decide | Claude elige el patrón. | |

**User's choice:** Herencia múltiple (recomendado)

---

### Backends player vs admin

| Option | Description | Selected |
|--------|-------------|----------|
| Dos instancias FastAPIUsers (Cookie + Bearer) | Una por surface. is_admin guard en routers admin. AUTH-07 y AUTH-09. | ✓ |
| Una instancia con lógica custom en middleware | Menos instancias pero fricciona con patrones de fastapi-users. | |

**User's choice:** Dos instancias (recomendado)

---

### Refresh token strategy

| Option | Description | Selected |
|--------|-------------|----------|
| DatabaseStrategy custom + tabla refresh_tokens | Reuse detection, revocación verificable en DB, cumple AUTH-09. | ✓ |
| JWTStrategy puro (access tokens cortos, sin refresh en DB) | Más simple pero NO cumple AUTH-09 ni el success criteria #3/#4. | |

**User's choice:** DatabaseStrategy (recomendado)

---

## Email SMTP

| Option | Description | Selected |
|--------|-------------|----------|
| Resend | Free tier 3000/mes, SDK Python oficial, excelente deliverability, fácil. | ✓ |
| SendGrid | Clásico, free tier 100/día, más complejo. | |
| Postmark | Mejor deliverability transaccional, más caro. | |
| AWS SES | Más barato a escala, requiere verificación dominio, sandbox. | |

**User's choice:** Resend

---

### Integración con fastapi-users

| Option | Description | Selected |
|--------|-------------|----------|
| ResendEmailSender custom (BaseEmailSender protocol) | Switch por ENVIRONMENT. dev→Mailpit SMTP, staging/prod→Resend API. | ✓ |
| SMTP genérico apuntando a Resend relay | Funciona pero pierde API features (webhooks, logs). | |

**User's choice:** ResendEmailSender custom (recomendado)

---

### Templates de email

| Option | Description | Selected |
|--------|-------------|----------|
| HTML simple inline | Sin Jinja2, branding básico, mantenible. | ✓ |
| Texto plano | Funcional pero sin aspecto profesional para demo. | |
| Jinja2 templates en ficheros separados | Phase 10 añade branding configurable de todos modos. | |

**User's choice:** HTML simple inline (recomendado)

---

## Users Schema

### Campos de ban en Phase 2

| Option | Description | Selected |
|--------|-------------|----------|
| Incluir is_active + banned_at nullable ahora | Evita ALTER TABLE en Phase 8. fastapi-users built-in is_active reaprovechado. | ✓ |
| Solo campos Phase 2, ALTER en Phase 8 | YAGNI estricto pero crea dependencia inter-fase. | |

**User's choice:** Incluir is_active + banned_at ahora (recomendado)

---

### is_superuser vs is_admin

| Option | Description | Selected |
|--------|-------------|----------|
| Mantener is_superuser internamente, exponer is_admin en API | Sin parchear fastapi-users. | ✓ |
| Columna is_admin en DB, parchar fastapi-users | Más limpio semánticamente, más fricción con la lib. | |

**User's choice:** is_superuser interno / is_admin en API (recomendado)

---

### display_name en Phase 2

| Option | Description | Selected |
|--------|-------------|----------|
| Sí, display_name nullable ahora | Phase 3 (wallet) y Phase 8 (CRM) lo necesitan. Evita ALTER TABLE. | ✓ |
| No, añadir en fases posteriores | YAGNI estricto. | |

**User's choice:** Sí, display_name nullable (recomendado)

---

## Admin Bootstrapping / Frontend

### Creación del primer admin

| Option | Description | Selected |
|--------|-------------|----------|
| Script bin/create-admin.py desde .env | Idempotente, documentado en README. FIRST_ADMIN_EMAIL + FIRST_ADMIN_PASSWORD. | ✓ |
| Management CLI (typer/click) | Más flexible, overkill para Phase 2. | |
| Migración Alembic con credenciales hardcoded | Desaconsejable — gitleaks lo marcaría. | |

**User's choice:** Script bin/create-admin.py (recomendado)

---

### Frontend auth — rutas vs modales

| Option | Description | Selected |
|--------|-------------|----------|
| Rutas Next.js dedicadas (/login, /register, ...) | Linkables desde emails, server components, shadcn/ui. | ✓ |
| Modales sobre homepage | Más fluido SPA pero complica redirects desde emails. | |

**User's choice:** Rutas dedicadas (recomendado)

---

### Panel admin — mismo Next.js vs app separada

| Option | Description | Selected |
|--------|-------------|----------|
| /admin/* rutas en el mismo Next.js | Layout separado, middleware protege rutas, un solo deploy. | ✓ |
| App Next.js separada frontend/admin/ | Aislamiento total pero duplica build config. | |

**User's choice:** /admin/* en el mismo Next.js (recomendado)

---

## Claude's Discretion

Ninguna área quedó a discreción de Claude — todas las decisiones fueron seleccionadas explícitamente por el usuario.

## Deferred Ideas

- Wallet creation on registration → Phase 3
- Sign-up bonus → Phase 5
- Ban/unban UI → Phase 8 (columnas creadas ahora)
- Branding configurable en emails → Phase 10
- OAuth / social login → out of scope v1
- Passkeys / WebAuthn → out of scope v1
