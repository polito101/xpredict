# Phase 11: Hardening & Operator-Demo Gate - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** Discuss skipped (operator decision) — hard scope constraints captured directly below

<domain>
## Phase Boundary

Final gate before any operator demo, on the already-consolidated F1–F10 base
(`origin/main @ 0fb3fee`). Validate mobile responsiveness end-to-end, tune Sentry
alert rules and rate limits, execute the PITFALLS.md "Looks Done But Isn't"
checklist as a documented audit, ship a prod-migration dry-run + security scan in
CI, and scaffold the regulatory/ToS posture. This is a CLOSURE / HARDENING phase —
no new product features.
</domain>

<decisions>
## Implementation Decisions — HARD SCOPE CONSTRAINTS (operator-set, non-negotiable)

1. **No new features, no refactors, no architecture changes.** Hardening,
   verification, CI/observability, and scaffolding ONLY.

2. **Legal / ToS (SC#6) = STRUCTURE + BASE + NOTES ONLY.** Create skeletons:
   `docs/regulatory.md` (section scaffold + notes on what counsel must review), a
   ToS placeholder, and an operator-agreement template stub. Do NOT write deep
   legal content or expand the regulatory scope. The actual Spanish-counsel review
   is an EXTERNAL deferred dependency — out of this phase.

3. **Backend test-isolation / `backend-ci` pytest residual is OUT OF SCOPE.** It is
   owned by a SEPARATE track (Pol), as the follow-up to PR #16
   (`tests/wallet/test_concurrent_transfers.py::test_50_concurrent_overdraft`;
   DEF-03-01 isolation debt). Phase 11 MUST NOT touch backend tests, the wallet
   test suite, or re-fix that issue. The "Looks Done But Isn't" wallet / ledger /
   concurrency items are VERIFY-ONLY / documentation, coordinated with Pol — never
   re-implemented here.

4. **CI hotfix PR #16 stays untouched.** Phase 11 builds on top of `origin/main`
   (F1–F10); it neither modifies nor depends on PR #16's branch.

5. Security scan adds `bandit` (Python), `pnpm/npm audit`, and an OWASP ZAP
   baseline against `/auth/*` and `/bets/*` to CI; `gitleaks` is already green.

### Claude's Discretion
Within the boundaries above, implementation details (script structure, CI wiring,
Sentry alert-rule definitions, responsive-QA method) are at Claude's discretion,
guided by ROADMAP success criteria, PITFALLS.md, and existing repo conventions.
</decisions>

<code_context>
## Existing Code Insights

Consolidated base = `origin/main @ 0fb3fee` (F1–F10 merged). Single Alembic head
`0009_phase10_tenant_config`. CI workflows live in `.github/workflows/`
(`backend-ci.yml`, `frontend-ci.yml`, `security.yml`). `gitleaks` already passes;
frontend CI is green on this base. backend-ci pytest has a pre-existing isolation
failure owned by Pol (constraint 3). Full codebase mapping happens during
plan-phase research.
</code_context>

<specifics>
## Specific Ideas — the 6 success criteria (closure-scoped)

1. Responsive QA 360–768px across home, market detail, bet flow, portfolio, wallet
   history, auth — audit + CSS/layout-only fixes (no feature change).
2. Execute the PITFALLS.md "Looks Done But Isn't" checklist as a documented audit
   (wallet/ledger/concurrency items = verify-only; coordinate with Pol).
3. `prod-migration-dry-run` CI job: staging-style env, boot, bet→settle E2E, fail
   on hardcoded dev URLs / DEBUG=True.
4. Security scan in CI: bandit + pnpm/npm audit + OWASP ZAP baseline (auth + bets).
5. Sentry alert rules for the 4 critical scenarios (settlement failure, Polymarket
   sync error-rate spike, reconciliation drift, auth-abuse spike), synthetically
   triggered.
6. Regulatory SCAFFOLD only: `docs/regulatory.md` skeleton + ToS placeholder +
   operator-agreement template stub + counsel-review notes (per constraint 2).
</specifics>

<deferred>
## Deferred Ideas

- Spanish legal counsel review of ToS + token policy (external; not in this phase).
- Backend test-isolation / `backend-ci` pytest greening (Pol's separate track).
- Any feature work, refactors, or architecture changes.
</deferred>
