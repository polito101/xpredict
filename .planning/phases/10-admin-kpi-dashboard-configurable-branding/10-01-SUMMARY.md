---
phase: 10-admin-kpi-dashboard-configurable-branding
plan: 01
subsystem: api
tags: [branding, white-label, tenant-config, fastapi, sqlalchemy, alembic, pydantic, audit, multipart-upload]

# Dependency graph
requires:
  - phase: 08-admin-crm-user-management-audit-log-viewer
    provides: current_active_admin Bearer gate, AuditService.record (sole audit writer), MissingGreenlet admin.id capture pattern, _helpers.seed_user/auth/client, test_auth_negative.py 403/401 analog
  - phase: 03-wallet-double-entry-ledger
    provides: admin write-router shape (audit-then-commit), idempotent ON CONFLICT singleton seed (migration 0004), tenant_id ghost + TENANT_DEFAULT literal
  - phase: 01-scaffold-foundations
    provides: tenant_id ghost-column convention, single-Alembic-head invariant, Money-lint gate, session-loop test discipline
provides:
  - tenant_config single-row branding table (migration 0009, chained off head 0008)
  - TenantConfig ORM model (tenant_id ghost + UNIQUE(tenant_id) = single-row v1 / one-per-tenant v2 seam)
  - GET/PUT /api/v1/admin/tenant-config (Bearer-gated, audited admin.branding_updated, multipart logo with size+content-type+magic-byte validation)
  - public GET /branding/current (4-field payload, no bytes) + GET /branding/logo (bytes + Content-Type + nosniff)
  - branding Pydantic schemas (TenantConfigUpdate extra=forbid + hex pattern, TenantConfigRead, BrandingPublic)
affects: [10-03 admin branding form UI, 10-05 frontend runtime theming, multi-tenant v2]

# Tech tracking
tech-stack:
  added: []   # zero new packages this phase (all stdlib/existing deps)
  patterns:
    - "Single-row table enforced via UNIQUE(tenant_id) — the documented single-tenant→multi-tenant seam (D-07)"
    - "Multipart logo upload validated out-of-band: 256KB hard cap + content-type allowlist + leading magic-byte sniff (no Pillow, no image decode — DoS-safe)"
    - "Server-side hex allowlist ^#[0-9a-fA-F]{6}$ via Pydantic Field(pattern=) at the persist boundary (the <style>-injection guard for Plan 10-05)"
    - "Raw-bytes FastAPI Response(content=bytes, media_type=, headers nosniff) for binary serving"

key-files:
  created:
    - backend/app/branding/__init__.py
    - backend/app/branding/models.py
    - backend/app/branding/schemas.py
    - backend/app/branding/admin_router.py
    - backend/app/branding/router.py
    - backend/alembic/versions/0009_phase10_tenant_config.py
    - backend/tests/admin/test_tenant_config.py
    - backend/tests/admin/test_tenant_config_negative.py
    - backend/tests/branding/__init__.py
    - backend/tests/branding/test_branding_public.py
  modified:
    - backend/app/main.py
    - backend/app/core/audit/schemas.py

key-decisions:
  - "Single-row enforced via UNIQUE(tenant_id) + idempotent ON CONFLICT (tenant_id) DO NOTHING singleton seed; PUT updates the row in place (seeds if absent) — never a duplicate insert."
  - "Logo validation order: content-type allowlist → 256KB size cap → magic-byte sniff. SVG accepted under the cap + allowlist only (text/xml, no magic check), served via <img>+nosniff so it cannot execute script (T-10-02)."
  - "Public /branding/current returns safe XPredict defaults when the row is absent (fresh unseeded DB) so the player UI never breaks; the migration seeds the singleton so this is a defensive fallback."
  - "Branding schemas.py + both routers OMIT the postponed-annotations future import (FastAPI 3.13 Annotated[Depends]/Form/UploadFile + Pydantic v2 Field(pattern=) forward-ref hazard)."

patterns-established:
  - "Single-row config table: tenant_id ghost + UNIQUE(tenant_id), in-place UPDATE-or-seed write path."
  - "Untrusted binary upload: allowlist + size cap + magic-byte sniff, served with X-Content-Type-Options: nosniff."

requirements-completed: [ADD-05, ADD-06]

# Metrics
duration: 6 min
completed: 2026-05-31
---

# Phase 10 Plan 01: Configurable Branding Backend Slice A Summary

**Single-row `tenant_config` model + migration 0009 (off head 0008), an audited Bearer-gated admin CRUD router (GET/PUT `/api/v1/admin/tenant-config`) with server-side hex + multipart-logo (size/content-type/magic-byte) validation, and a public branding consumption surface (`GET /branding/current` + `GET /branding/logo` with nosniff).**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-31T07:58:52Z
- **Completed:** 2026-05-31T08:05:13Z
- **Tasks:** 3 (TDD: RED → model/migration/schemas → routers GREEN)
- **Files created/modified:** 12 (10 created, 2 modified)

## Accomplishments

- **ADD-05** — admin saves brand name + primary/secondary hex (+ optional logo) to the single `tenant_config` row via `PUT /api/v1/admin/tenant-config`; the row persists and updates in place (no duplicate). Invalid hex (`not ^#[0-9a-fA-F]{6}$`) → 422; oversized (>256KB) logo → 422 "Logo must be 256 KB or smaller."; wrong content-type → 422 "Logo must be a PNG, JPEG, WebP, or SVG file." (SC#4).
- **ADD-06 (backend half)** — public `GET /branding/current` returns exactly `{brand_name, primary_hex, secondary_hex, logo_url}` (no bytes, no tenant_id, no timestamps — T-10-06); `GET /branding/logo` serves the stored bytes with the stored `Content-Type` + `X-Content-Type-Options: nosniff` (T-10-02), 404 when no logo set. This is the Plan 10-05 runtime-theming consumption surface.
- **SC#6** — player Bearer → 403 and no Bearer → 401 on both GET and PUT `/api/v1/admin/tenant-config` (T-10-05), enforced by `current_active_admin`.
- **Single Alembic head preserved** — migration 0009 chains off `0008_phase8_user_created_at`; `alembic heads` reports exactly one head.
- **Audit trail** — every PUT writes `admin.branding_updated` (actor `user:{admin_id}` captured before commit, payload includes `logo_changed`) via `AuditService.record` then `session.commit()`.

## Task Commits

Each task was committed atomically (TDD cycle):

1. **Task 1: Wave-0 failing tests (RED)** — `3cc326b` (test) — three test files (tenant-config CRUD, negative 403/401, public branding) failing 404 against the not-yet-built endpoints.
2. **Task 2: model + migration 0009 + schemas** — `c0ad476` (feat) — TenantConfig model (tenant_id ghost + UNIQUE), migration 0009 (single head off 0008, idempotent singleton seed), three schemas.
3. **Task 3: admin + public routers, main.py wiring (GREEN)** — `b36f173` (feat) — audited admin CRUD router, public branding router, main.py wiring, `admin.branding_updated` added to `KNOWN_EVENT_TYPES`. All 8 Wave-0 tests GREEN.

**Plan metadata:** committed with this SUMMARY.

## Files Created/Modified

- `backend/app/branding/models.py` — `TenantConfig` single-row model: UUID PK, `brand_name` Text, `primary_hex`/`secondary_hex` String(7), `logo_bytes` LargeBinary + `logo_content_type` String(64), timestamps, `tenant_id` ghost + `UNIQUE(tenant_id)`.
- `backend/alembic/versions/0009_phase10_tenant_config.py` — `tenant_config` DDL + idempotent `INSERT ... ON CONFLICT (tenant_id) DO NOTHING` singleton seed (XPredict / `#4f46e5` / `#0ea5e9`), `down_revision = "0008_phase8_user_created_at"`.
- `backend/app/branding/schemas.py` — `TenantConfigUpdate` (extra=forbid + `Field(pattern=^#[0-9a-fA-F]{6}$)`), `TenantConfigRead`, `BrandingPublic`. Omits the postponed-annotations future import.
- `backend/app/branding/admin_router.py` — `GET/PUT /api/v1/admin/tenant-config`, `current_active_admin`-gated; multipart PUT with hex validation + logo size/content-type/magic-byte checks; audited; updates the single row in place.
- `backend/app/branding/router.py` — public `GET /branding/current` (4-field payload) + `GET /branding/logo` (bytes + Content-Type + nosniff).
- `backend/app/main.py` — wired `tenant_config_admin_router` (admin group) + `branding_router` (public, last).
- `backend/app/core/audit/schemas.py` — added `admin.branding_updated` to `KNOWN_EVENT_TYPES` (audit-viewer dropdown nicety).
- `backend/tests/admin/test_tenant_config.py`, `test_tenant_config_negative.py`, `backend/tests/branding/__init__.py`, `test_branding_public.py` — Wave-0 integration tests.

## Decisions Made

- **Logo validation is allowlist → size cap → magic-byte sniff, no image decode.** Avoids Pillow / decompression-bomb risk (T-10-03); SVG is treated as untrusted text/xml (no magic check) and only ever served via `<img src>` + nosniff so it cannot execute script (T-10-02).
- **Empty multipart file parts are ignored** (`if data:`) — an empty `logo` field means "no logo change", not a validation error, so a PUT that only updates the palette never wipes an existing logo.
- **`/branding/current` falls back to XPredict defaults** when the singleton row is absent (defensive — the migration always seeds it, but a fresh test DB or a future reset never breaks the player UI).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reworded schemas.py docstring so the future-import acceptance grep passes**
- **Found during:** Task 2 (schemas)
- **Issue:** The Task 2 acceptance criterion checks `grep -L "from __future__ import annotations" app/branding/schemas.py` returns the filename. My docstring explained the rule using the exact literal string `from __future__ import annotations`, which `grep` matched even though there was no actual import statement — so `grep -L` did NOT return the filename (false-positive textual match), failing the acceptance check.
- **Fix:** Reworded the docstring to say "the postponed-annotations future import" instead of the literal string. The file still has no actual future import; `grep -L` now returns `app/branding/schemas.py` and `grep -c` returns 0. Applied the same wording to both router docstrings preemptively (their Task 3 acceptance grep would have had the identical hazard).
- **Files modified:** backend/app/branding/schemas.py (and admin_router.py / router.py docstrings)
- **Verification:** `grep -L "from __future__ import annotations" app/branding/schemas.py app/branding/admin_router.py app/branding/router.py` returns all three filenames; `grep -rn "^from __future__ import annotations"` on the three files returns nothing (exit 1).
- **Committed in:** c0ad476 (schemas) + b36f173 (routers)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** Cosmetic docstring wording only — no behavior change. The acceptance grep is now reliable. No scope creep.

## Issues Encountered

- **Testcontainer teardown ResourceWarnings** (unclosed asyncpg sockets at interpreter exit) appear after the test run on Windows. These are pre-existing harness noise (asyncpg `__del__` cleanup races the proactor event-loop shutdown), not test failures — all 8 branding tests pass GREEN and the full admin+branding suite is 68/68 green.

## Authentication Gates

None — no external auth required this phase (the admin Bearer is the existing Phase 8 `current_active_admin` gate, exercised by the test seeds).

## User Setup Required

None — no external service configuration. Zero new packages added (every dependency was already present).

## Threat Flags

None — all surface introduced (admin CRUD, public branding reads, logo bytes) is covered by the plan's `<threat_model>` (T-10-01..T-10-06). Mitigations applied: hex `Field(pattern=)` allowlist (T-10-01), logo nosniff + `<img>`-only consumption (T-10-02), 256KB cap (T-10-03), content-type allowlist + magic bytes (T-10-04), `current_active_admin` gate + SC#6 negative test (T-10-05), exact public field set (T-10-06).

## Known Stubs

None — every endpoint is fully wired to the `tenant_config` row. No placeholder data, no hardcoded empties flowing to a response.

## Next Phase Readiness

- **Plan 10-03 (admin branding form UI)** can consume `GET/PUT /api/v1/admin/tenant-config` (multipart PUT: `brand_name`, `primary_hex`, `secondary_hex`, optional `logo` file).
- **Plan 10-05 (frontend runtime theming)** can consume the public `GET /branding/current` (palette + name + logo_url) and `GET /branding/logo` (bytes via `<img src>`). The server-side hex allowlist is the guard that makes injecting the hexes into a `<style>` block safe.
- No blockers. Migration 0009 is single-head; integration tests are green against the testcontainer Postgres (Docker required locally — available this run).

## Self-Check: PASSED

- All 10 created files exist on disk (verified below).
- All 3 task commits present in git history (`3cc326b`, `c0ad476`, `b36f173`).
- Plan `<verification>` re-run: 8/8 branding tests GREEN; `alembic heads` = single `0009_phase10_tenant_config (head)`; money-lint exits 0; `grep -L` returns all three router/schema filenames.

---
*Phase: 10-admin-kpi-dashboard-configurable-branding*
*Completed: 2026-05-31*
