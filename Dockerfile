# AD Assistant production image (Railway deploys this root Dockerfile).
#
# Multi-stage:
#   1. node:20  - pnpm build of the React frontend (static dist/)
#   2. python:3.12-slim - uv-managed backend, PostgreSQL 16 client tools
#      (pg_dump/pg_restore for app.cli_backup), plus the frontend dist.
#
# The container serves BOTH the API and the SPA from one process:
# uvicorn app.prod:app mounts the built frontend (FRONTEND_DIST) with an
# index.html fallback for client-side routes. Alembic migrations run at
# container start, then uvicorn binds to $PORT (Railway) or 8471.

# ---------------------------------------------------------------- stage 1
FROM node:20-slim AS frontend-build

WORKDIR /build
RUN npm install -g pnpm@10

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
# Empty VITE_API_URL makes the app call the API on its own origin, which is
# exactly right here: the same container serves both.
ENV VITE_API_URL=""
RUN pnpm build

# ---------------------------------------------------------------- stage 2
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# PostgreSQL 16 client tools from the PGDG repository: pg_dump must be at
# least the server's major version, and the Debian release the base image
# tracks may ship an older one. The codename is read from the image itself
# (python:3.12-slim moved from bookworm to trixie in 2025).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc]" \
        "http://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first for layer caching, then the project itself. No dev group.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

# The built SPA, served by app.prod via FRONTEND_DIST.
COPY --from=frontend-build /build/dist /app/frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist

EXPOSE 8471

# Migrate, then serve. Railway injects PORT; 8471 is the local fallback.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.prod:app --host 0.0.0.0 --port ${PORT:-8471}"]
