---
phase: 12
slug: admin-market-operations-ui-and-player-resolution-display
status: verified
threats_open: 0
asvs_level: 2
created: 2026-06-04
---

# Phase 12 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (6 STRIDE registers across 12-01..12-06-PLAN.md); mitigations verified present in `main..HEAD` by gsd-security-auditor on 2026-06-04.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| settlement tx → markets row | Winner/source/justification written inside the settlement ACID transaction; a mid-tx failure must leave NO partial resolution | resolution result (winner, justification) |
| public read → player browser | `get_market_public` surfaces RESOLVED markets but must not leak admin-only fields | public market + 3 resolution fields (no identities) |
| admin browser → Next server action | `admin_jwt` is an HttpOnly cookie; the wrapper reads it server-side and forwards a Bearer header — the token never crosses into client JS | admin Bearer token (server-side only) |
| Next server action → FastAPI admin endpoints | CRUD prefix `/api/v1` vs bare settlement prefix differ; a wrong prefix silently 404s and can mask an auth bug | admin CRUD + settlement mutations |
| player browser → /bets | The per-market stake limit is a client UX mirror; the authoritative bound is enforced server-side in `place_bet` | bet stake (money, on the wire as string) |
| player cookie → /bets/me/portfolio | The own-payout read is self-scoped by the player's own HttpOnly cookie; it must never expose another user's result | own bet result / P&L |
| public market read → rendered justification | Operator-authored justification shown to all players; must be output-encoded (no XSS) | operator text (escaped React text) |
| admin justification input → audit/settlement | Justification is mandatory + persisted; the backend enforces `min_length=1` | settlement justification (audited) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-12-01 | Tampering | settlement resolve transaction | mitigate | Winner cols written inside `session.begin()` ACID tx; adapter sets on caller's session with no separate commit — all-or-nothing (`settlement/service.py:110,224-230`, `settlement/adapters.py:44-50`) | closed |
| T-12-02 | Information Disclosure | `get_market_public` RESOLVED branch | mitigate | `MarketRead` exposes only winner/source/justification/`resolved_at` — no resolver UUID, no admin identity, no per-user payout (`markets/router.py:167-173`, `markets/schemas.py:135-141`) | closed |
| T-12-03 | Tampering | stake money columns | mitigate | `Numeric(18,4)` nullable + string-or-None `field_serializer`; money-lint enforced (`markets/models.py:146-153`, `markets/schemas.py:149-153`, migration 0010) | closed |
| T-12-04 | Repudiation | settlement audit row | accept | `AuditService.record` byte-unchanged; records resolver/winner/justification/payout inside the tx (`settlement/service.py:235-248,373-383`) | closed |
| T-12-05 | Information Disclosure | `admin_jwt` → client JS | mitigate | `"use server"` reads HttpOnly `admin_jwt` server-side via `bearerHeader()`; only JSON result crosses to client (`admin-markets-api.ts:25,53-60`) | closed |
| T-12-06 | Tampering / Repudiation | wrong-prefix → silent 404 | mitigate | URL-contract test asserts CRUD keeps `/api/v1` and settlement is bare via `not.toContain("/api/v1")` (`admin-markets-api.test.ts:106,118,127`) | closed |
| T-12-07 | Elevation of Privilege | non-admin reaching market mutations | accept (backend-owned) | `current_active_admin` superuser Bearer gate on every mutation (`markets/router.py:43,98,127`, `auth/admin_router.py:89-91`) | closed |
| T-12-08 | Tampering | client bypass of per-market stake limit | mitigate | Authoritative server check in `BetService.place_bet` raises `StakeOutOfRange` → 422 before any write (`bets/service.py:84,98-101`, `bets/router.py:110-111`) | closed |
| T-12-09 | Tampering | money coerced to float (bet entry) | mitigate | Stake stays a string on the wire; `Number()` used only for the bound compare, never storage (`bet-schemas.ts:41-49`, `order-entry-form.tsx:129-130,177`) | closed |
| T-12-10 | Denial of Service | absurd per-market max enabling a huge stake | accept | Per-market max is operator-set; global `BET_MAX_STAKE` ceiling fallback + wallet `CHECK(balance>=0)` bound the actual debit (`bets/service.py:98-99,124-125`) | closed |
| T-12-11 | Information Disclosure | resolution panel leaking another user's payout | mitigate | Own-result via `/bets/me/portfolio` self-scoped by the player's session cookie (no `user_id` param), filtered by `market_id` after SSR (`markets/[slug]/page.tsx:119-136`, `bets/router.py:129-144`) | closed |
| T-12-12 | Tampering / XSS | HTML injection via public justification | mitigate | Rendered as escaped React text `{justification}`; no `dangerouslySetInnerHTML` (grep: only comments) (`market-resolution-panel.tsx:170`) | closed |
| T-12-13 | Information Disclosure | session cookie crossing to client JS | mitigate | Cookie read server-side in the Server Component; only `isAuthenticated` boolean + rendered result reach client (`markets/[slug]/page.tsx:176-178`) | closed |
| T-12-14 | Elevation of Privilege | non-admin reaching market CRUD | accept (backend-owned) | `current_active_admin` gates create/list/get/update (`markets/router.py:43,55,84,98`); `test_create_market_non_admin_returns_403` | closed |
| T-12-15 | Tampering | client bypassing field constraints (criteria-lock) | mitigate | Backend raises `423 CRITERIA_LOCKED` once bets exist + `MarketCreate/Update` Field bounds; form disable + 422 map is UX-only (`markets/service.py:136-143`, `markets/schemas.py:67-99`) | closed |
| T-12-16 | Tampering | money (stake limits) as float | mitigate | Min/Max stay strings, `Number()` only for the client min≤max compare; backend `Numeric(18,4)` (`market-form.tsx:57-65,121`, `markets/models.py:146-153`) | closed |
| T-12-17 | Information Disclosure | `admin_jwt` → client JS (form) | mitigate | All CRUD funnels through the `"use server"` `admin-markets-api.ts`; no direct fetch / cookie access in the client component (`market-form.tsx:45,220,236`) | closed |
| T-12-18 | Repudiation | resolve/reverse/force-settle without a justification | mitigate | Backend `min_length=1` on all three settlement schemas + client empty-block with `role="alert"` (`settlement/schemas.py:28,47,66`, settlement dialogs) | closed |
| T-12-19 | Tampering / Repudiation | wrong-prefix settlement call silently 404s | mitigate | Dialogs call only the bare-prefix 12-02 wrappers, guarded by `admin-markets-api.test.ts` (`{resolve,reverse,force-settle}-dialog.tsx`) | closed |
| T-12-20 | Elevation of Privilege | non-admin reaching resolve/reverse/force-settle | accept (backend-owned) | `current_active_admin` on all three settlement endpoints (`settlement/router.py:63,103,137`) | closed |
| T-12-21 | Tampering | re-resolve after reverse corrupts the ledger (idempotency collision) | mitigate (UX) | Reverse dialog copy: "It does not re-open the market for a clean re-resolution" — v1 limitation surfaced, not silently invited (`reverse-settlement-dialog.tsx:106-107`) | closed |
| T-12-SC | Tampering (supply-chain) | npm/pip/cargo installs | mitigate | Zero dependency-manifest churn in `main..HEAD` (package.json / pnpm-lock.yaml / pyproject.toml / uv.lock all empty) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-12-01 | T-12-04 | Settlement audit row is byte-unchanged; the audit trail (resolver, winner, justification, timestamps) remains the system of record — no new repudiation surface introduced. | Pol Bonet (PM) | 2026-06-04 |
| AR-12-02 | T-12-07 | Market mutations are backend-owned; gated by `current_active_admin` (superuser Bearer) from prior phases. This phase adds only the client wrappers, no new endpoint. | Pol Bonet (PM) | 2026-06-04 |
| AR-12-03 | T-12-10 | Per-market max is operator-set behind an admin gate; the global `BET_MAX_STAKE` ceiling plus the wallet `CHECK(balance>=0)` bound the actual debit. | Pol Bonet (PM) | 2026-06-04 |
| AR-12-04 | T-12-14 | Market CRUD is backend-owned; the `current_active_admin` superuser gate is verified and the client layer adds no endpoint. | Pol Bonet (PM) | 2026-06-04 |
| AR-12-05 | T-12-20 | Settlement actions are backend-owned; `current_active_admin` on all three endpoints is verified and the client adds no endpoint. | Pol Bonet (PM) | 2026-06-04 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-04 | 22 | 22 | 0 | gsd-security-auditor (opus) via /gsd-secure-phase |

**Audit notes (2026-06-04):**
- Mode: State B — register authored at plan time (`register_authored_at_plan_time: true`); auditor verified each mitigation is present in `main..HEAD`, did not scan for new threats.
- Review-time gap CR-01 (BET-06 stake limits validated/sent but never persisted, which would have rendered T-12-08/T-12-16 non-functional) was independently confirmed fixed in commit `cb55197`: `markets/service.py:57-58,166-171` now persist `min_stake`/`max_stake`; `markets/schemas.py:50-64` enforces `gt=0` + `min≤max`; regression-guarded by `test_{create,update}_persists_stake_limits` and the `422` range/zero-bound tests (`tests/markets/test_admin_router.py:330,389,456,494`).
- Unregistered flags: none. Only `12-05-SUMMARY.md` carries a `## Threat Flags` section and it states "None"; the other five summaries declare no new attack surface.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-04
