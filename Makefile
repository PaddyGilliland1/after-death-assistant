# AD Assistant development conveniences.
.PHONY: dev up down logs sync backend test lint migrate revision frontend

# Full dev stack (db + backend + frontend)
dev up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

# Backend, local (no Docker)
sync:
	cd backend && uv sync

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8471

test:
	cd backend && uv run python -m pytest

lint:
	cd backend && uv run ruff check .

# Alembic (requires a reachable database)
migrate:
	cd backend && uv run alembic upgrade head

revision:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

# Frontend, local (owned by the frontend agent; convenience only)
frontend:
	cd frontend && pnpm dev
