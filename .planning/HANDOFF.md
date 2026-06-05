# HANDOFF — live operational state

> **Updated:** 2026-06-05 (Phase 16 closeout — PR opened + CI 7/7 green) · **Milestone:** v1.2 Credible Catalog · **Phase 16 of 18 — DONE: PR [#30](https://github.com/polito101/xpredict/pull/30) OPEN, CI 7/7 GREEN, MERGEABLE → MERGE READY, awaiting Pol's review/merge**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."
> Verify live state from git (`git log`, `origin/main`, `gh pr ...`), not these docs alone — they can drift.

---

## TL;DR

**Phase 16 (Catalog & Event API + House Event CRUD) is COMPLETE: executed (5/5 plans), code-reviewed (0 blockers; WR-01/WR-04 fixed + tested, WR-02/03 accepted), verified 18/18 must-haves / 4-of-4 success criteria — and shipped to PR [#30](https://github.com/polito101/xpredict/pull/30).** The PR is OPEN, **all 7 CI checks are GREEN**, `mergeable=MERGEABLE` with **0 drift** vs `origin/main` (merged the 4 Phase-13/14 fixes Pol landed mid-flight) — the only remaining action is **Pol's review/merge** (`reviewDecision=REVIEW_REQUIRED`; `main` is protected). **Status: MERGE READY.**

---

## Phase 16 — exact status

- **Branch / PR:** `gsd/phase-16-catalog-event-api-house-event-crud` (forked off `origin/main` @ `bda571f`, then merged current `origin/main` so it is **0 behind**). **PR [#30](https://github.com/polito101/xpredict/pull/30) OPEN**, `mergeable=MERGEABLE`, `mergeStateStatus=BLOCKED` ONLY by `reviewDecision=REVIEW_REQUIRED`. Opened via `gh` (the worktree session lacks the `create_pull_request` MCP — the documented GOTCHA; repo CLAUDE.md permits `gh pr create`; only Pol merges).
- **Delivers (BRW-01..05 + EVA-01/02 + the EVA-03..06 HTTP surface):**
  - **`app/catalog/`** (new) — `CatalogService` (Approach B: two bounded `LIMIT 100` queries over standalone `markets` + ≥2-child `market_groups`, merged in Python; local `pg_trgm` ILIKE search; status/sort/category filters; every combo bounded/empty-safe) + `public_catalog_router` (`GET /api/v1/catalog`, `/categories`, `/events/{slug}`).
  - **`app/settlement/event_router.py` + `event_schemas.py`** (new) + `event_service.py` (additive: `create_house_event` / `update_house_event` / `event_has_bets`) — `POST/PATCH /admin/events` (create + `EXISTS(bets)`→423 edit-lock) and `POST /admin/events/{id}/{resolve,void,reverse}` (stateless two-step confirm + ValueError→HTTP map, exposing the **unchanged** Phase-15 `EventService`).
  - **`app/main.py`** — both routers registered (deferred import). Legacy `GET /api/v1/markets` preserved (back-compat).
- **Tests:** 31 new tests (catalog 12 + event-admin 10 + settle 9, incl. spike-004 `drift_count==0` on every settled path) + the legacy back-compat assertion — green per-module; the Linux `backend` CI job ran the **full suite + ruff + mypy GREEN**.
- **Code review** (`16-REVIEW.md`, status `resolved`): 0 blockers. WR-01 (outcome-replace hardening: `synchronize_session=False` + `expunge_all` + test), WR-04 (child question on rename) FIXED; WR-02/WR-03 ACCEPTED (consistent with `create_market` precedent / astronomically unlikely).
- **Verification** (`16-VERIFICATION.md`): status `passed`, **18/18 must-haves**, 4/4 success criteria — verified against the real code.

## Post-PR validation — DONE (the "audit before merge-ready" gate)

- **Drift:** 0 behind `origin/main` (merged the 4 Phase-13/14 fixes Pol landed after the fork; no conflicts — different files). ✓
- **CI: 7/7 GREEN** — `backend` ✓ (full Linux `uv run pytest` + ruff + mypy, 1m50s), `bandit` ✓, `pip-audit` ✓, `pnpm-audit` ✓, `gitleaks (full history)` ✓, `prod-migration-dry-run` ✓, `zap-baseline` ✓. ✓
- **Mergeability:** `MERGEABLE`, `BLOCKED` only by the required review (Pol). ✓
- **Invariants:** purely additive — new `app/catalog/` package + new event router/schemas + additive `event_service` methods + 4-line `main.py` wiring; Phase-15 `resolve/void/reverse` + settlement primitives + migrations 0 diff; zero new deps, no new migration. ✓

## CI / environment notes

- **Windows worktree is unreliable for full-suite backend verification:** `uv run pytest` flakes (testcontainers connection drops — hit a one-off `500`/connection-error during this phase that did NOT reproduce in isolation or on Linux CI). **Verify per-module locally; trust Linux CI.** Execution ran inline (no nested worktrees — `use_worktrees=false`, reverted, not committed).

## What NOT to touch

- Don't re-open / re-verify Phase 16 — it's engineering-complete; the only open action is Pol's merge.
- Don't push to `main` or self-merge — PR-only; **only Pol merges**.
- Don't modify the Phase-15 `EventService.resolve_event/void_event/reverse_event`, the settlement primitives, or migrations — Phase 16 left them byte-for-byte unchanged (it composes them over HTTP).

## Recommended next session — Phase 17 (after #16's PR merges)

- **Phase 17 = Catalog browse UI, event detail & admin event ops** — reqs EVT-02..05, BRW-06 (+ P2-01..03 stretch). The **frontend** for everything Phase 16 exposed: browse/search/filter UI, the multi-outcome event-detail page (per-outcome rows + price history), the admin event-ops UI (create/edit/resolve/void/reverse), all white-label `--brand-*`. First **frontend** phase of v1.2 → expect `/gsd-ui-phase` to generate a UI-SPEC.
- **Prereq:** start ONLY after Pol merges the Phase-16 PR, from a fresh `origin/main` checkout. New session, repo-rooted.
- **Kickoff:** `/gsd-autonomous phase 17` (single-phase, 1 PR — the same flow that worked for 13/14/15/16).

## Standing deferred items (carried from v1.0/v1.1, unchanged)

| Category | Item | Status |
|----------|------|--------|
| legal (gating) | Spanish counsel review of ToS + token policy | Open — **not deferrable** before any live operator demo |
| human-UAT | Phase 12 `12-HUMAN-UAT.md` | 3 scenarios open |
| verification | Phases 03 / 04 / 05 | 3 VERIFICATION.md missing (backends shipped) |
