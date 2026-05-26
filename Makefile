# XPredict Makefile (D-47) — POSIX dev shortcuts.
# Windows users: invoke `bin\dev.ps1` directly instead (GNU Make not required).

.PHONY: dev down test lint format db.shell db.reset seed help

help:
	@echo "XPredict — common targets:"
	@echo "  make dev       — start the 8-service stack + run alembic upgrade head"
	@echo "  make down      — docker compose down"
	@echo "  make test      — backend pytest + frontend vitest"
	@echo "  make lint      — ruff + mypy + money-lint + frontend lint + typecheck"
	@echo "  make format    — ruff format (backend) + pnpm lint --fix (frontend)"
	@echo "  make db.shell  — psql into the running db container"
	@echo "  make db.reset  — docker compose down -v + bin/dev (destroys volumes)"
	@echo "  make seed      — Phase 1 has no seed data beyond Alembic feature flags"

dev:
	./bin/dev

down:
	docker compose down

test:
	cd backend && uv run pytest tests/ -x
	cd frontend && pnpm test

lint:
	cd backend && uv run ruff check app/ scripts/ tests/ alembic/
	cd backend && uv run mypy app/
	cd backend && uv run python scripts/lint_money_columns.py
	cd frontend && pnpm lint && pnpm typecheck

format:
	cd backend && uv run ruff format app/ scripts/ tests/ alembic/
	cd frontend && pnpm lint --fix || true

db.shell:
	docker compose exec db psql -U xpredict -d xpredict

db.reset:
	docker compose down -v
	./bin/dev

seed:
	@echo "Phase 1 has no seed data beyond Alembic-managed feature flags."
