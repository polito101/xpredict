# XPredict frontend (Phase 1 dev profile).
#
# Builds the Next.js 15 + React 19 + Tailwind 4 image consumed by the
# docker-compose `frontend` service wired up in Plan 01-03. Phase 1 runs
# `pnpm dev` so hot-reload via the bind-mounted source works; staging will
# swap CMD to `pnpm build && pnpm start` (per CONTEXT D-02 / RESEARCH Open
# Question 2).

FROM node:20-alpine

# Enable corepack + pin pnpm to a Node-20-compatible version (pnpm@latest =
# pnpm 11+ which requires Node ≥22.13). pnpm 9.15.x matches the lockfile
# committed by Plan 01-02 and supports Node 20-alpine.
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

# Copy lockfile + manifest first so dep installs are cached separately from
# source changes. --frozen-lockfile guarantees reproducibility in CI.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy the rest of the source tree. In docker-compose dev the host bind-mount
# overlays /app, but the COPY remains valid for one-shot builds (CI / staging).
COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]
