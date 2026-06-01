---
phase: 10-admin-kpi-dashboard-configurable-branding
fixed_at: 2026-06-01T00:00:00Z
review_path: .planning/phases/10-admin-kpi-dashboard-configurable-branding/10-REVIEW.md
iteration: 1
fix_scope: critical_warning
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Fase 10: Code Review Fix Report

**Fixed at:** 2026-06-01
**Source review:** `.planning/phases/10-admin-kpi-dashboard-configurable-branding/10-REVIEW.md`
**Iteration:** 1
**Scope:** `critical_warning` — Critical (0) + Warning (WR-01..WR-04). Info findings (IN-01..IN-05) out of scope, untouched.

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0
- Status: all_fixed

## Fixed Issues

### WR-01: Logo read entirely into memory before the 256 KB cap (memory DoS)

**Files modified:** `backend/app/branding/admin_router.py`
**Commit:** `06d08f5`
**Applied fix:** In `update_tenant_config`, replaced the unbounded `data = await logo.read()`
with a bounded `data = await logo.read(_MAX_LOGO_BYTES + 1)` followed by an explicit
`len(data) > _MAX_LOGO_BYTES` → 422 reject BEFORE any further processing. This caps the
buffered body at 256 KB + 1 byte, so an authenticated admin can no longer exhaust worker
memory with a multi-GB multipart. The existing `len(data) > _MAX_LOGO_BYTES` guard inside
`_validate_logo` was left in place as harmless defense-in-depth (and because the function's
docstring documents it as validating size); with the upstream bounded read it can never be
reached with oversized input.
**Verification:** ruff clean on the changed file (the only ruff findings in the backend tree
are 3 pre-existing RUF002 ambiguous-MINUS-SIGN warnings in `kpi_service.py` docstrings, present
at HEAD and unrelated to this change).

### WR-02: `split_part(actor, ':', 2)` cast to UUID with no guard — a malformed actor 500s the whole KPI endpoint

**Files modified:** `backend/app/admin/kpi_service.py`
**Commit:** `0d840ab`
**Applied fix:** In `dau()`, replaced the open-prefix guard `AuditLog.actor.like("user:%")`
with the exact-form regex `AuditLog.actor.op("~")(r"^user:[0-9a-fA-F-]{36}$")`. `LIKE 'user:%'`
matched a bare `'user:'` (the `%` matches the empty string), whose `split_part('user:', ':', 2)`
returns `''`, and `CAST('' AS uuid)` raises `invalid input syntax for type uuid`, taking down the
entire KPI endpoint (500) — not just the DAU card. Since `audit_log` is append-only, such a
degenerate row could not be deleted. The regex gates the cast so only a `user:` + 36-char UUID
actor reaches it. The `cast(...)` is unchanged (still correct for well-formed actors).
**Verification:** ruff clean on the new lines (the new explanatory comment, including its `→`
arrow, produced no RUF002/RUF003 finding). Logic verified by reasoning: the regex is strictly
narrower than the previous `LIKE`, and every real `auth.session_started` actor (`user:{uuid}`)
still matches; not run against Postgres locally (no local DB) — the change is a filter
tightening, semantically safe.

### WR-03: `_load_singleton` `LIMIT 1` without `ORDER BY` is non-deterministic

**Files modified:** `backend/app/branding/admin_router.py`, `backend/app/branding/router.py`
**Commit:** `e4c248c`
**Applied fix:** Added `.order_by(TenantConfig.created_at.asc())` before `.limit(1)` in BOTH
`_load_singleton` implementations (admin router + public router). `tenant_id` is nullable, so the
`UNIQUE(tenant_id)` constraint permits multiple `tenant_id IS NULL` rows in Postgres; without an
ORDER BY the admin editor and the public reader could resolve different rows. Ordering by
`created_at asc` makes both deterministically resolve the same (oldest) row. The model has a
`created_at` column (`server_default=func.now()`), so the ordering is well-defined.
**Verification:** ruff clean on both changed files.
**Note (deferred, out of scope):** The review also suggested making `tenant_id NOT NULL` (or a
partial unique index) so the `UNIQUE` actually enforces the documented single-row invariant.
That is a schema/migration change beyond the deterministic-read fix and is left for a follow-up
(it would touch `models.py` + a new Alembic migration; not a warning-level code fix).

### WR-04: Frontend loses the real HTTP status and degrades 401/403 to "invalid fields"

**Files modified:** `frontend/src/lib/branding-admin-api.ts`, `frontend/src/lib/branding-types.ts`,
`frontend/src/components/admin/branding-form.tsx`
**Commit:** `7299f1e`
**Applied fix:**
- `branding-admin-api.ts` (`"use server"`): `fetchTenantConfig` / `updateTenantConfig` now throw a
  structured error built by a new `buildApiError(res)` helper instead of the flat
  `Error("API error: <status>")`. For a 422 it parses FastAPI's structured `detail` (the
  `exc.errors()` array with `loc`) via a new `parseFieldErrors()` into a `{field: message}` map
  keyed to the actual offending form field (`brand_name` / `primary_hex` / `secondary_hex`). The
  thrown `Error.message` is a JSON payload `{kind, status, fieldErrors}` so the structured info
  survives the Server-Action → client boundary (Error objects are otherwise opaque across it).
- `branding-types.ts`: added the `BrandingApiError` type and a pure `parseBrandingApiError(err)`
  decoder (placed here because a `"use server"` file may only export async functions). It JSON-
  decodes the thrown message and falls back to extracting a 3-digit status from the legacy string
  form, so an unexpected error never crashes the handler.
- `branding-form.tsx`: the submit `catch` now decodes `{status, fieldErrors}` and branches:
  401/403 → a session-expired toast (no longer "check the fields"); 422 → maps each server field
  error to the field that actually failed (`brand_name` gets its real message; the hex fields get
  the friendlier `HEX_MESSAGE`) instead of blanket-setting both color fields; any other failure
  (5xx / network) → a "server problem, try again" toast.
**Verification:** `pnpm typecheck` passes clean across the whole frontend; the 7 existing
`branding-form.test.tsx` behavior-contract tests still pass (success path, invalid-hex blocking,
logo pre-checks intact). ESLint could not be run in isolation (this repo is on Next 16 — `next lint`
was removed, and invoking the flat-config eslint directly hits a plugin-compat crash unrelated to
this change); the TypeScript typecheck is the authoritative static gate and is green.

> **Requires human verification (logic/behavior):** WR-04 is a UI behavior change whose
> correctness is only partially covered by the existing tests (they assert the success path and
> client pre-checks, not the new 401/403/422-field-mapping branches). Two things warrant a human
> confirming at runtime:
> 1. The 422 field-mapping and 401/403 session-toast branches behave as intended against a live
>    backend (e.g. submit an over-long `brand_name`, or an expired session).
> 2. The cross-boundary error propagation: Next.js scrubs **uncaught** Server-Action error
>    messages to an opaque digest in **production** builds. In dev the JSON message passes through
>    (and the tests mock the action, so they're unaffected). If production builds turn out to
>    strip the message, the decoder degrades gracefully to `status: null` → the generic
>    "server problem" toast (no worse than before, and never a misleading per-field error). A
>    fully production-robust alternative is to change the action to *return* a discriminated-union
>    result rather than throw — deliberately not done here because it would change the action's
>    return contract and break the existing "resolves → success" test assumptions. Flagging for a
>    human to decide whether the dev-correct + prod-graceful-degradation behavior is acceptable, or
>    whether to follow up with the return-result refactor.

## Skipped Issues

None — all four in-scope warnings were fixed.

## Out-of-scope (not attempted)

The five Info findings (IN-01 stale `auth.login_*` event literal, IN-02 `_load_singleton`/logo-url
duplication, IN-03 magic numbers, IN-04 SVG CSP defense-in-depth, IN-05 `formatMoney` non-numeric
guard) are below the `critical_warning` fix scope and were intentionally left untouched.

---

_Fixed: 2026-06-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
