# XPredict backend — multi-stage build for prod (api / worker / beat / flower)
# All four services share the same image; docker-compose overrides CMD per service.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

# System deps: curl for healthcheck probes, build-essential for psycopg2-binary
# (pre-built wheels exist on linux/amd64, but linux/arm64 may need the toolchain).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Install uv (the dep manager — D-08)
RUN pip install --no-cache-dir "uv>=0.5"

WORKDIR /app

# --- Dependency layer (cached) ---
# Copy only the dependency manifests first so layer reuse kicks in
# on code-only changes.
COPY pyproject.toml uv.lock* /app/

# Prod image: deps only, no dev tools (--no-dev) and a frozen lockfile
# Dev image overrides this stage via the `dev` target below.
RUN uv sync --frozen --no-dev || uv sync --no-dev

# --- App code ---
COPY . /app

# Use uv's managed venv as PATH
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

# Default command (compose overrides this for worker/beat/flower)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Dev target — includes dev deps (pytest, ruff, mypy, etc.)
# Use via: docker compose build --target dev backend
# ---------------------------------------------------------------------------
FROM base AS dev
RUN uv sync || true
