# AD Assistant

**AD Assistant (After Death Assistant), a shared web application for executors administering an estate in England and Wales.**

Track every asset, liability, debtor, creditor, cost, contact and action; keep a live, transparent trial balance and per-beneficiary share; keep a correct, current inheritance tax assessment; hold the HMRC forms and guidance in-app; and draft the paperwork for human approval.

## What it is (and is not)

This tool **informs and drafts. It is not advice, and nothing is filed automatically.**

- Agents draft; a person approves; a person submits or sends. No HMRC filing, no email or letter dispatch, no payment, ever happens from code.
- All IHT and estate-accounts maths live in a pure, deterministic, unit-tested module. No LLM computes a figure.
- Every tax constant and guidance item carries its source URL and fetch date.
- Executors and admins write; viewers are strictly read-only, enforced server-side.

## Your data stays yours

The repository contains schema and synthetic seed data only. Real estate data lives in a local, git-ignored `seed/` file and in your own self-hosted database. Nothing personal is ever committed.

## Documentation

| Document | What it covers |
|---|---|
| [User guide](docs/USER_GUIDE.md) | Using the tool as an executor: every module, step by step, in plain words |
| [Installation guide](docs/INSTALL.md) | Self-hosting, local development, seeding, the knowledge library, upgrades |
| [Deployment guide](docs/DEPLOY.md) | Production on Railway with Cloudflare Access, backups, restore drill |
| [Synopsis](docs/SYNOPSIS.html) | A one-page visual overview of the whole system |
| [Changelog](CHANGELOG.md) | Release history |
| [Security policy](SECURITY.md) | Security posture, reporting vulnerabilities, known limits |
| [Design masters](docs/masterdocs/) | Architecture, features, data model, agents, processes |

## Versioning

Current release: **v0.9.0**. The project follows [semantic versioning](https://semver.org/); pre-1.0, breaking changes bump the minor version and are noted in the changelog.

## Stack

Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2 + SQLModel / Alembic / LangGraph agents / PostgreSQL 16 + pgvector / React 18 + Vite + TypeScript / Tailwind + shadcn/ui / Cloudflare Access auth / Railway deploy.

## Self-host in one command

```bash
cp .env.example .env    # fill in values
docker compose up
```

That starts PostgreSQL 16 with pgvector (host port 5474), the FastAPI backend (http://localhost:8471) and the Vite frontend (http://localhost:5173), all local. Set `DEV_AUTH=true` and a `USER_ROLES` mapping in `.env` so the dev login shim knows who you are. See `CONTRIBUTING.md` for the development workflow.

## Deploy to production

The root `Dockerfile` builds one production image (frontend built with pnpm, backend served by uvicorn, Alembic migrations at start) and `railway.toml` deploys it to Railway, with Cloudflare Access in front for login. The full walkthrough, environment variable table, backup schedule and restore drill are in `docs/DEPLOY.md`.

Backups and portability: `python -m app.cli_backup create` takes a `pg_dump` with a sha256 manifest and `verify` checks it; `GET /estate/export` returns the entire estate as open-format JSON; `POST /estate/erase` (admin only, explicit confirmation) permanently deletes it. Your data stays yours, and it can leave with you.

## Jurisdiction

England and Wales rules live behind `backend/app/domain/jurisdiction/` so other regimes can be added without touching the core engine.

## Licence

MIT. UK Government content ingested by the knowledge library is used under the Open Government Licence with attribution.
