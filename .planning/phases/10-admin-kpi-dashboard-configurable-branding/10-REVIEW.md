---
phase: 10-admin-kpi-dashboard-configurable-branding
reviewed: 2026-05-31T00:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - backend/app/admin/kpi_service.py
  - backend/app/admin/kpi_router.py
  - backend/app/admin/kpi_schemas.py
  - backend/app/branding/models.py
  - backend/app/branding/admin_router.py
  - backend/app/branding/router.py
  - backend/app/branding/schemas.py
  - backend/alembic/versions/0009_phase10_tenant_config.py
  - backend/app/main.py
  - frontend/src/app/admin/page.tsx
  - frontend/src/app/admin/branding/page.tsx
  - frontend/src/app/layout.tsx
  - frontend/src/app/globals.css
  - frontend/src/components/admin/branding-form.tsx
  - frontend/src/components/admin/kpi-card.tsx
  - frontend/src/components/admin/kpi-dashboard.tsx
  - frontend/src/components/admin/volume-chart.tsx
  - frontend/src/components/admin/dau-window-toggle.tsx
  - frontend/src/components/admin/admin-nav.tsx
  - frontend/src/components/admin/admin-default-route.tsx
  - frontend/src/components/brand-logo.tsx
  - frontend/src/lib/branding-admin-api.ts
  - frontend/src/lib/branding-public.ts
  - frontend/src/lib/branding-types.ts
  - frontend/src/lib/kpi-api.ts
  - frontend/src/lib/kpi-types.ts
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Fase 10: Code Review Report

**Reviewed:** 2026-05-31
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Se revisaron los 27 ficheros de la Fase 10 (KPI dashboard de admin + branding white-label
configurable) centrando el ataque en las cuatro superficies de riesgo señaladas: la inyección
de hex en el bloque `<style>` server-rendered (XSS), los endpoints públicos sin autenticación,
la validación del upload de logo, y la disciplina de dinero (Decimal/string, nunca float).

**Veredicto general: implementación sólida en los puntos críticos.** Las dos superficies XSS
están correctamente cerradas: los hex se validan server-side (`^#[0-9a-fA-F]{6}$`) ANTES de
persistir y antes de interpolarse en el `<style>` (un hex de 6 dígitos no puede contener `<`,
`>`, `}` ni comillas, así que no hay break-out de `</style>`), y el logo SVG se sirve solo vía
`<img>` con `X-Content-Type-Options: nosniff` (SVG en `<img>` no ejecuta script). El gating de
admin (`current_active_admin`) está correctamente cableado y cubierto por tests negativos
(401 sin Bearer, 403 con Bearer de player). La disciplina de dinero es correcta de extremo a
extremo (Decimal → `MoneyStr` string en backend; `string` en el wire y formateo display-only
en el frontend, sin `parseFloat` para almacenamiento). Las dos fórmulas corregidas (House P&L
kind-filtered con netting de reversals, y DAU como UNION de bettors + logins) son correctas y
están bien testeadas.

No se encontraron BLOCKERS. Los hallazgos son robustez (DoS por upload sin tope previo de
tamaño, cast de UUID sin guarda) y calidad (duplicación, magic numbers, un literal de evento
obsoleto que convive con el correcto).

## Warnings

### WR-01: El logo se lee entero en memoria ANTES de comprobar el cap de 256 KB (DoS de memoria)

**File:** `backend/app/branding/admin_router.py:159` (y `_validate_logo`, líneas 65-97)
**Issue:** En `update_tenant_config` se hace `data = await logo.read()` (lectura completa del
upload a memoria) y solo DESPUÉS, dentro de `_validate_logo`, se comprueba
`len(data) > _MAX_LOGO_BYTES`. No hay ningún tope de tamaño de body upstream en `main.py`
(no se inspecciona `Content-Length`, no hay middleware de límite de request). Un admin
autenticado puede enviar un multipart de varios GB y el worker lo bufferiza entero antes del
rechazo 422 → agotamiento de memoria del proceso. El blast radius está acotado a admins
autenticados (la dependencia de auth corre antes), por eso es WARNING y no BLOCKER, pero el
cap "256 KB" no protege contra el coste que pretende limitar.
**Fix:** Rechazar por `Content-Length` antes de leer el cuerpo, o leer de forma acotada:
```python
# En update_tenant_config, antes de logo.read():
if logo is not None:
    # Cota dura ANTES de bufferizar: leer 1 byte de más que el cap y abortar.
    data = await logo.read(_MAX_LOGO_BYTES + 1)
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Logo must be 256 KB or smaller.",
        )
    if data:
        logo_content_type = _validate_logo(logo.content_type, data)
        logo_bytes = data
```
(Idealmente, además, un límite global de tamaño de request en el stack ASGI.)

### WR-02: `split_part(actor, ":", 2)` casteado a UUID sin guarda — un actor malformado revienta el query de DAU

**File:** `backend/app/admin/kpi_service.py:180-186`
**Issue:** El cálculo de DAU parsea el user id de `audit_log.actor` con
`cast(func.split_part(AuditLog.actor, ":", 2), PG_UUID(as_uuid=True))` filtrando por
`AuditLog.actor.like("user:%")`. El `LIKE "user:%"` matchea también `"user:"` (el `%` casa con
vacío), y `split_part("user:", ":", 2)` devuelve `""`; `CAST('' AS uuid)` lanza un error de
Postgres (`invalid input syntax for type uuid`), que tumba TODO el endpoint de KPIs (500), no
solo la card de DAU. Hoy todos los `auth.session_started` se emiten como `user:{uuid}` real
(verificado en `auth/router.py:175`), así que el riesgo es bajo, pero una sola fila de auditoría
con actor degenerado (o un evento futuro reutilizando el prefijo) rompe el dashboard entero.
Como `audit_log` es append-only, una fila mala no se puede borrar.
**Fix:** Endurecer el filtro a la forma exacta de UUID o castear de forma segura:
```python
).where(
    AuditLog.event_type == AUTH_SESSION_STARTED,
    AuditLog.occurred_at >= lo,
    # 'user:' + 36 chars de UUID — evita el match de 'user:' vacío.
    AuditLog.actor.op("~")(r"^user:[0-9a-fA-F-]{36}$"),
)
```
(o usar `split_part(...)` con un `NULLIF(..., '')` y filtrar los NULL antes del cast).

### WR-03: `_load_singleton` con `SELECT ... LIMIT 1` sin `ORDER BY` no garantiza "la" fila

**File:** `backend/app/branding/admin_router.py:62` y `backend/app/branding/router.py:31`
**Issue:** Ambos `_load_singleton` hacen `select(TenantConfig).limit(1)` sin `ORDER BY`. El
invariante de fila única se apoya solo en `UNIQUE(tenant_id)` con `tenant_id` por defecto al
`TENANT_DEFAULT`. Pero `tenant_id` es **nullable** (modelo `models.py:65-69` y migración
`0009:63-68`) y el `UNIQUE` sobre una columna nullable permite múltiples filas con
`tenant_id IS NULL` en Postgres. Si por cualquier camino (semilla futura, inserción manual,
v2 multi-tenant temprano) aparece más de una fila, `LIMIT 1` sin orden devuelve una fila
no-determinista: el admin podría editar una fila y el público leer otra. El PUT también
"semilla si ausente" basándose en este mismo read no-determinista, pudiendo crear duplicados
con `tenant_id` distinto.
**Fix:** Hacer el read determinista y/o forzar el invariante de unicidad real:
```python
return (
    await session.execute(
        select(TenantConfig).order_by(TenantConfig.created_at.asc()).limit(1)
    )
).scalar_one_or_none()
```
Y considerar `tenant_id NOT NULL` (o un índice único parcial) para que el `UNIQUE` realmente
imponga la fila única que documenta el modelo.

### WR-04: El frontend pierde el código de estado real del error y degrada 401/403 a "campos inválidos"

**File:** `frontend/src/lib/branding-admin-api.ts:53-55,87-89` + `frontend/src/components/admin/branding-form.tsx:199-212`
**Issue:** `updateTenantConfig` lanza `Error("API error: <status>")`. El form solo distingue
`status.includes("422")`; cualquier otro fallo (401 sesión expirada, 403, 500) cae al `else`
genérico ("Couldn't save branding. Check the fields and try again."), mensaje que culpa a los
campos cuando el problema real es de sesión/servidor. Peor: un 422 por `brand_name` vacío o
demasiado largo (`Field(min_length=1, max_length=120)` en `schemas.py:30`) se mapea a un error
de hex en AMBOS campos de color (`form.setError("primary_hex"/"secondary_hex", HEX_MESSAGE)`),
señalando un error inexistente en los colores en lugar de en el nombre. El comentario afirma
que "hex es el único 422 a nivel de campo", lo cual es falso dado el contrato del schema.
**Fix:** Propagar el detalle estructurado del backend (FastAPI ya devuelve `exc.errors()` con
`loc`) y mapear el error al campo correcto; para 401/403 mostrar un toast de sesión y redirigir
a login en vez del mensaje de "revisa los campos".

## Info

### IN-01: Literal de evento de login obsoleto convive con el real en `KNOWN_EVENT_TYPES`

**File:** `backend/app/core/audit/schemas.py:31-32`
**Issue:** `KNOWN_EVENT_TYPES` lista `"auth.login_started"` / `"auth.login_failed"`, pero el
login real de player emite `"auth.session_started"` (verificado en `auth/router.py:175` y usado
correctamente por `kpi_service.AUTH_SESSION_STARTED`). El dropdown de filtro de la audit-log
ofrece un tipo de evento que nunca se emite y NO ofrece `auth.session_started`, que sí existe.
Inconsistencia entre el taxonomía documentada y la realmente emitida.
**Fix:** Sustituir/añadir `"auth.session_started"` en la lista y eliminar el `auth.login_*`
muerto (o documentar por qué se conserva).

### IN-02: `_load_singleton` y los constantes de logo duplicados entre los dos routers de branding

**File:** `backend/app/branding/admin_router.py:60-62` y `backend/app/branding/router.py:30-31`
**Issue:** `_load_singleton` está copiado verbatim en `admin_router.py` y `router.py`. La
lógica de URL de logo (`"/branding/logo" if ... else None`) aparece tres veces
(admin_router `_logo_url_for`, admin_router PUT línea 205, router línea 52). Divergencia futura
fácil.
**Fix:** Extraer `_load_singleton` y el helper de logo-url a un módulo compartido de branding
(p. ej. `app/branding/repo.py`).

### IN-03: Magic numbers en la validación de logo y en el chart

**File:** `backend/app/branding/admin_router.py:47` y `frontend/src/components/admin/volume-chart.tsx:69`
**Issue:** `_MAX_LOGO_BYTES = 262144` se repite como literal `262144 + 1` en el test, y el
mismo cap vive duplicado en el frontend como `256 * 1024` (`branding-form.tsx:54`). En el chart,
`Math.round(parseFloat(b.volume) * 100) / 100` usa `100` mágico para redondear a 2 dp de
display (sobre un valor que el contrato dice tener 4 dp). No es un bug (es display-only,
documentado), pero el redondeo a 2 dp del eje pierde precisión visual respecto al `$x.xxxx`
de las cards.
**Fix:** Centralizar el cap de logo en una constante compartida de config; documentar el
redondeo a 2 dp del eje como decisión explícita o alinearlo con los 4 dp de las cards.

### IN-04: SVG servido con su propio `image/svg+xml` desde el origen del backend

**File:** `backend/app/branding/router.py:64-68` + `admin_router.py:48,79`
**Issue:** El SVG se acepta sin sniff de magic-byte (es texto/XML) y se sirve con
`media_type="image/svg+xml"` + `nosniff`. Renderizado solo vía `<img>` (en `brand-logo.tsx`),
un SVG NO ejecuta script, así que la cadena actual es segura. Queda como nota defensiva: si en
el futuro alguien enlazara `/branding/logo` directamente como navegación top-level (no `<img>`),
o lo embebiera con `<object>`/`<embed>`, un SVG con `<script>` sí ejecutaría en el origen del
backend. El `nosniff` no impide la ejecución de un `image/svg+xml` declarado.
**Fix:** (defensa en profundidad) servir el logo con `Content-Disposition: inline` +
`Content-Security-Policy: default-src 'none'; sandbox` en la respuesta de `/branding/logo`, o
servirlo desde un dominio de assets separado.

### IN-05: `formatMoney("")` y entrada no numérica producen `$0.0000` silenciosamente

**File:** `frontend/src/components/admin/kpi-card.tsx:32-40`
**Issue:** `formatMoney` es pura manipulación de string sin validar que la entrada sea un
número. `formatMoney("")` → `"$0.0000"`; `formatMoney("abc")` → `"$abc.0000"`. El contrato
garantiza que la entrada siempre es un Decimal serializado, así que en la práctica no se da,
pero un cambio futuro en el backend que envíe `null`/`""` mostraría un cero falso (o basura)
en vez de un estado de error. Defensa-en-profundidad menor.
**Fix:** Guardar contra entrada vacía/no numérica devolviendo un placeholder explícito (o
loggear) en lugar de fabricar `$0.0000`.

---

_Reviewed: 2026-05-31_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
