#!/usr/bin/env bash
# XPredict SC#3 "Demo Trap" guard — fail the build when dev config leaks into
# APPLICATION SOURCE (Phase 11, PITFALLS.md §"How to verify you haven't fallen
# into the trap"). Mirrors bin/dev: shebang + `set -euo pipefail`.
#
# This app has NO `DEBUG` flag. Its config shape (backend/app/core/config.py) is
# `ENVIRONMENT: Literal["dev","staging","prod"]` + an `is_dev` property. So the
# guard targets `ENVIRONMENT=dev` plus hardcoded `localhost` / `127.0.0.1` that
# would survive a staging/prod boot — NOT a `DEBUG=True` string that does not
# exist here.
#
# SCOPE (Pitfall 1 allow-list): only `backend/app` and `frontend/src` are
# scanned (NOT the whole repo). docker-compose.yml healthcheck probes
# (http://localhost:8000/healthz, :8025, :5555, :3000) are LEGITIMATE
# intra-container loopback; .env.example carries intentional dev defaults; the
# tests dir, .zap/ and docs/ hold fixtures/examples. None of those are grepped,
# because `grep -r` is rooted at the two app dirs and test files are excluded
# below.
#
# NARROWING (documented per 11-01-PLAN <acceptance_criteria> NOTE FOR EXECUTOR):
# the clean tree already contains four classes of LEGITIMATE, intentional
# localhost references that constraint 1 (no refactors) forbids editing, so the
# localhost/IP rule is filtered through an allow-list of exactly those classes:
#   1. frontend dev-fallback idiom — `process.env.X || "http://localhost:8000"`
#      (and the `ws://` variant) across Server Components + lib helpers
#      (frontend/src/lib/api.ts, app/wallet/page.tsx, hooks/use-market-socket.ts …).
#   2. the lone quoted-URL continuation line of a MULTI-line `||` fallback
#      (e.g. frontend/src/lib/api.ts:92, branding-public.ts:54).
#   3. comment / docstring lines (Python `#`, TS `//` / `*` / `/*`), incl.
#      double-backtick RST inline-code examples like ``redis://localhost:6379/0``
#      in backend/app/auth/rate_limit.py.
#   4. typed config DEFAULTS — `NAME: <type> = "...localhost..."` — the
#      intentional Settings dev defaults (backend/app/core/config.py:71
#      `FRONTEND_BASE_URL: str = "http://localhost:3000"`).
# A NEW hardcoded leak with no env-var indirection and no type annotation —
# e.g. a fresh `host = "localhost"` — is NOT matched by any allow-list class and
# still fails the build. That is the guard's PURPOSE: catch NEW prod-bound dev
# config, not the pre-existing intentional dev-fallbacks.
# The `ENVIRONMENT=dev` rule is applied across BOTH roots with NO allow-list (it
# has zero legitimate occurrences in app source — config.py declares it as a
# typed annotation default `ENVIRONMENT: Literal[...] = "dev"`, which this regex
# does not match because of the `:` annotation before any `=`).

set -euo pipefail

# Run from the repo root so the two scan roots resolve regardless of caller cwd.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

SCAN_ROOTS=(backend/app frontend/src)
INCLUDES=(--include='*.py' --include='*.ts' --include='*.tsx')
# Test files are out of scope (verify-only / fixtures) — never flagged.
EXCLUDES=(--exclude='*.test.ts' --exclude='*.test.tsx' --exclude='test_*.py' --exclude='*_test.py')

# Rule A — ENVIRONMENT=dev anywhere in app source (no legitimate occurrence).
#          `|| true` so grep's exit-1-on-no-match does not abort under `set -e`.
env_dev=$(grep -rnE 'ENVIRONMENT *= *.?dev' \
  "${SCAN_ROOTS[@]}" "${INCLUDES[@]}" "${EXCLUDES[@]}" || true)

# Rule B — hardcoded localhost / 127.0.0.1, MINUS the four allow-listed classes
#          documented above. Each `grep -vE` strips one class; whatever survives
#          is a genuine NEW hardcoded dev URL.
#            1. `||` env-fallback idiom:        X || "http://localhost:8000"
#            2. lone quoted-URL continuation of a multi-line `||` fallback
#            3. comment / docstring lines (Python #, TS // /* *, RST ``..``)
#            4. typed config default:           NAME: <type> = "http://localhost..."
localhost_raw=$(grep -rnE 'localhost|127\.0\.0\.1' \
  "${SCAN_ROOTS[@]}" "${INCLUDES[@]}" "${EXCLUDES[@]}" || true)
localhost_hits=$(printf '%s\n' "${localhost_raw}" \
  | grep -vE '\|\|[[:space:]]*"[a-z]+://(localhost|127\.0\.0\.1)' \
  | grep -vE ':[0-9]+:[[:space:]]*"[a-z]+://(localhost|127\.0\.0\.1)[^"]*"[,]?[[:space:]]*$' \
  | grep -vE ':[0-9]+:[[:space:]]*(#|//|\*|/\*)' \
  | grep -vE ':[0-9]+:.*``[^`]*(localhost|127\.0\.0\.1)' \
  | grep -vE ':[0-9]+:[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*:[[:space:]]*[A-Za-z][][A-Za-z0-9_. ,"|]*[[:space:]]*=[[:space:]]*"[a-z]+://(localhost|127\.0\.0\.1)' \
  | grep -vE '^[[:space:]]*$' || true)

violations=""
[[ -n "${env_dev}" ]] && violations+="${env_dev}"$'\n'
[[ -n "${localhost_hits}" ]] && violations+="${localhost_hits}"$'\n'

# Trim a possible trailing blank line before the emptiness test.
violations="$(printf '%s' "${violations}" | sed '/^[[:space:]]*$/d')"

if [[ -n "${violations}" ]]; then
  echo "::error::Hardcoded dev URL or ENVIRONMENT=dev found in application source:"
  echo "${violations}"
  exit 1
fi

echo "OK: no hardcoded localhost / ENVIRONMENT=dev in application source."
