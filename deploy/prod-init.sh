#!/usr/bin/env bash
# XPredict demo — one-time (and idempotent) data bootstrap for the prod stack.
#
# Runs the three ordered steps the schema + seed need, each in a throwaway
# container that exits when done (db/redis come up first via depends_on):
#   1. alembic upgrade head   — build/upgrade the schema (+ ledger singletons)
#   2. create_admin.py        — seed the first superuser from FIRST_ADMIN_* (NO-OP if it exists)
#   3. seed_demo.py           — ~15 markets / 81 bets of believable demo data (idempotent-ish)
#
# All three are safe to re-run. To wipe + re-seed the demo dataset only, run:
#   docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend python bin/seed_demo.py --reset
#
# Run from the repo root on the VM, AFTER `... build` and BEFORE `... up -d`:
#   ./deploy/prod-init.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env.prod ]; then
	echo "ERROR: .env.prod not found in repo root. Copy .env.prod.example and fill it in first." >&2
	exit 1
fi

COMPOSE=(docker compose --env-file .env.prod -f docker-compose.prod.yml)

echo "==> [1/3] alembic upgrade head"
"${COMPOSE[@]}" run --rm backend alembic upgrade head

echo "==> [2/3] create first admin (idempotent)"
"${COMPOSE[@]}" run --rm backend python bin/create_admin.py

echo "==> [3/3] seed demo dataset (~15 markets / 81 bets; skipped if already seeded)"
# seed_demo.py exits 1 when the demo data already exists; under `set -e` that
# would abort a re-run, so treat a non-zero exit as "already seeded" (no-op) and
# keep this script genuinely safe to re-run. Use --reset to wipe + re-seed.
if ! "${COMPOSE[@]}" run --rm backend python bin/seed_demo.py; then
	echo "    (demo already seeded — existing data left intact; to wipe + re-seed:"
	echo "     ${COMPOSE[*]} run --rm backend python bin/seed_demo.py --reset )"
fi

echo "==> Done. Now: ${COMPOSE[*]} up -d"
