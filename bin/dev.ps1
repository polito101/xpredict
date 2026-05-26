# XPredict dev loop — Windows PowerShell entrypoint (PLT-10).
#
# Brings the 8-service docker-compose stack up with healthchecks waiting,
# then applies Alembic migrations against the now-healthy Postgres.
# Companion POSIX entrypoint: `bin/dev`.
#
# Prerequisites: Docker Desktop, uv, pnpm. `.env.local` must exist at the
# repo root (copy from `.env.example` and fill in any secrets); compose
# reads variables from it transparently.

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

if (-not (Test-Path ".env.local")) {
    Write-Host "ERROR: .env.local not found at the repo root." -ForegroundColor Red
    Write-Host "       Copy .env.example to .env.local and edit any secrets."
    exit 1
}

Write-Host "-> Starting docker compose stack (8 services, awaiting healthchecks)..."
docker compose up -d --wait
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "-> Running Alembic migrations..."
docker compose exec -T backend uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "OK: XPredict dev stack ready" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:3000"
Write-Host "  Backend:  http://localhost:8000  (/healthz, /readyz, /_sentry-test)"
Write-Host "  Flower:   http://localhost:5555"
Write-Host "  Mailpit:  http://localhost:8025"
Write-Host ""
Write-Host "  Stop:     docker compose down"
Write-Host "  Reset DB: docker compose down -v; .\bin\dev.ps1"
