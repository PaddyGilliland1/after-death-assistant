# AD Assistant backend, dev-focused image (uv-managed, Python 3.12).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies first for layer caching, then the project itself.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project

COPY . .
RUN uv sync

EXPOSE 8471

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8471"]
