---
phase: 10-admin-kpi-dashboard-configurable-branding
fixed_at: 2026-06-01T00:00:00Z
review_path: .planning/phases/10-admin-kpi-dashboard-configurable-branding/10-REVIEW.md
iteration: 2
fix_scope: all
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report (Iteration 2)

**Fixed at:** 2026-06-01
**Source review:** `.planning/phases/10-admin-kpi-dashboard-configurable-branding/10-REVIEW.md`
**Iteration:** 2
**Scope:** `all` — Info findings IN-01..IN-05 (WR-01..WR-04 were fixed in iteration 1)

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

## Fixed Issues

### IN-01: Literal de evento de login obsoleto en `KNOWN_EVENT_TYPES`

**Files modified:** `backend/app/core/audit/schemas.py`
**Commit:** `7577528`
**Applied fix:** Removed `"auth.login_started"` and `"auth.login_failed"` from `KNOWN_EVENT_TYPES` and replaced them with `"auth.session_started"` (the real event emitted since Phase 2 per `auth/router.py:175`). Added a comment explaining the rename so the intent is clear to future editors.

---

### IN-02: `_load_singleton` y helper de logo-url duplicados entre routers

**Files modified:** `backend/app/branding/repo.py` (new file), `backend/app/branding/admin_router.py`, `backend/app/branding/router.py`
**Commit:** `0061372`
**Applied fix:** Created `backend/app/branding/repo.py` exporting `load_singleton` (the ordered `SELECT … ORDER BY created_at ASC LIMIT 1` read, preserving the WR-03 fix from iteration 1) and `logo_url_for`. Both `admin_router.py` and `router.py` now import from `repo.py` — their local `_load_singleton` and `_logo_url_for` definitions were removed, along with the now-unused `from sqlalchemy import select` in `router.py`. The inline `/branding/logo` string in the PUT response's `has_logo` branch was kept (operates on a bool, not a row) with a clarifying comment.

---

### IN-03: Magic numbers en validación de logo y en el chart

**Files modified:** `frontend/src/components/admin/branding-form.tsx`, `frontend/src/components/admin/volume-chart.tsx`
**Commit:** `82b66e1`
**Applied fix:**
- `branding-form.tsx`: Added a 3-line comment above `LOGO_MAX_BYTES = 256 * 1024` explicitly documenting that it mirrors `backend/_MAX_LOGO_BYTES = 262144` and that the frontend cannot import the Python constant directly — kept in sync by convention, backend is the gate.
- `volume-chart.tsx`: Added a 3-line comment on the `Math.round(parseFloat(b.volume) * 100) / 100` expression explaining that the `÷100` factor rounds to 2 decimal places for Y-axis display intentionally, and that kpi-card.tsx still shows the full 4 dp.

---

### IN-04: SVG servido sin headers de defensa en profundidad

**Files modified:** `backend/app/branding/router.py`
**Commit:** `14d4dbf`
**Applied fix:** Extended the `Response` headers in `get_branding_logo` to include `Content-Disposition: inline` and `Content-Security-Policy: default-src 'none'; sandbox` alongside the existing `X-Content-Type-Options: nosniff`. Added a comment explaining the defense-in-depth rationale: the current `<img>`-only usage is safe regardless, but these headers remove any script execution surface if the URL is ever navigated to directly or embedded via `<object>`/`<embed>`.

---

### IN-05: `formatMoney("")` produce `$0.0000` silenciosamente

**Files modified:** `frontend/src/components/admin/kpi-card.tsx`
**Commit:** `ce3dcab`
**Applied fix:** Added an early guard in `formatMoney` that returns `"$—"` (em-dash placeholder) when the trimmed input is empty or does not match a valid signed decimal number (`/^[+-]?\d+(\.\d+)?$/`). A real `"0"` from the backend still passes the guard and renders as `"$0.0000"` per UI-SPEC A-ZERO. The docblock was updated to document the guard and the distinction from the real-zero case.

---

## Skipped Issues

None — all five in-scope Info findings were fixed.

## Reference: Iteration 1 (WR-01..WR-04, scope=critical_warning)

Iteration 1 fixed all four warnings. See git log for commits `06d08f5` (WR-01), `0d840ab` (WR-02), `e4c248c` (WR-03), `7299f1e` (WR-04).

---

_Fixed: 2026-06-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
