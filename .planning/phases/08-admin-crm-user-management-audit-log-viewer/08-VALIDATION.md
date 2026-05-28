---
phase: 8
slug: admin-crm-user-management-audit-log-viewer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-28
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (backend), vitest (frontend) |
| **Config file** | `backend/pyproject.toml` / `frontend/vitest.config.ts` |
| **Quick run command** | `cd backend && uv run pytest tests/admin/ -x -q` |
| **Full suite command** | `cd backend && uv run pytest tests/ -x -q && cd ../frontend && pnpm test` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/admin/ -x -q`
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | ADU-01 | — | N/A | integration | `uv run pytest tests/admin/test_user_list.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ADU-02 | — | N/A | integration | `uv run pytest tests/admin/test_user_detail.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ADU-04 | T-8-ban | Banned user login returns 403, bets rejected, recharge rejected | integration | `uv run pytest tests/admin/test_ban.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ADU-05 | T-8-csv | CSV injection chars prefixed with single quote | unit | `uv run pytest tests/admin/test_csv_export.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ADU-06 | — | N/A | integration | `uv run pytest tests/admin/test_audit_log.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ADD-04 | T-8-auth | All admin endpoints require is_admin=true | integration | `uv run pytest tests/admin/test_admin_auth.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/admin/__init__.py` — admin test package
- [ ] `backend/tests/admin/conftest.py` — shared fixtures (admin user, regular user, banned user, test client)
- [ ] `backend/tests/admin/test_user_list.py` — stubs for ADU-01
- [ ] `backend/tests/admin/test_user_detail.py` — stubs for ADU-02
- [ ] `backend/tests/admin/test_ban.py` — stubs for ADU-04
- [ ] `backend/tests/admin/test_csv_export.py` — stubs for ADU-05
- [ ] `backend/tests/admin/test_audit_log.py` — stubs for ADU-06
- [ ] `backend/tests/admin/test_admin_auth.py` — stubs for ADD-04

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| TanStack Table UX (pagination, sorting, search) | ADU-01 | Visual interaction quality | Open /admin/users, verify table renders, sort by columns, page through results |
| User detail page tabs (Profile, Wallet, Bets) | ADU-02 | Visual layout verification | Open /admin/users/{id}, verify all tabs render with correct data |
| Audit log JSON payload expandable UI | ADU-06 | Visual interaction | Open /admin/audit-log, click expand on a row, verify JSON renders |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
