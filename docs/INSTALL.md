# AD Assistant Installation Guide

How to get AD Assistant running: one-command self-hosting, a local development setup, seeding data, loading the knowledge library, production deployment and upgrades.

**Companions:** `docs/USER_GUIDE.md` (using the tool), `docs/DEPLOY.md` (production on Railway with Cloudflare Access), `CONTRIBUTING.md` (development workflow).

---

## 1. Prerequisites

| Path | You need |
|---|---|
| Self-host (recommended) | Docker with the compose plugin. Nothing else. |
| Local development | Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20+, pnpm 10, and Docker (for PostgreSQL) or your own PostgreSQL 16 with the pgvector extension |
| Optional | An Anthropic API key, only for the Ask assistant and letter or narration drafting. Everything else, including the deterministic tax engine and the form-draft PDF, works without one. |

## 2. Self-host in one command

```bash
cp .env.example .env    # then fill in the values (see the table in section 4)
docker compose up
```

That starts three services:

| Service | Where |
|---|---|
| PostgreSQL 16 with pgvector | host port **5474** |
| FastAPI backend | http://localhost:8471 |
| React frontend (Vite) | http://localhost:5173 |

Open http://localhost:5173. With `DEV_AUTH=true` in `.env`, the app shows a development sign-in screen; enter an email address that appears in your `USER_ROLES` mapping (for example `admin@example.com` if you mapped it to `admin`) and you are in.

The unusual host ports (5474 for Postgres, 8471 for the API) are deliberate defaults to avoid colliding with other stacks; change them in `docker-compose.yml` if you prefer.

## 3. Local development setup

Run the pieces natively for a faster edit-reload loop:

```bash
# Database only (or point DATABASE_URL at your own Postgres 16 + pgvector)
docker compose up db

# Backend (port 8471)
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8471

# Frontend (port 5173)
cd frontend
pnpm install
pnpm dev
```

Notes:

- Vite serves on **5173** and will pick **5174** automatically if 5173 is busy; if that happens, set `FRONTEND_ORIGIN=http://localhost:5174` in `.env` so CORS matches.
- The backend settings read a `.env` from the directory you run it in, and real environment variables always win. For standalone backend runs, copy or symlink the root `.env` into `backend/` (`ln -s ../.env backend/.env`) or export the variables. `DATABASE_URL` in `.env.example` already points at the compose database on 5474.
- Tests: `cd backend && uv run pytest tests/ -v` and `cd frontend && pnpm test`.

## 4. Environment variables

Copy `.env.example` to `.env` and never commit `.env`. The variables that matter:

| Variable | Purpose | Dev value |
|---|---|---|
| `DATABASE_URL` | Postgres connection string; must use the `postgresql+asyncpg://` driver | `postgresql+asyncpg://postgres:postgres@localhost:5474/ad_assistant` |
| `DEV_AUTH` | `true` enables the development sign-in (the `X-Dev-User` shim). **MUST be `false` in production.** | `true` |
| `USER_ROLES` | Server-side email-to-role mapping, `email:role` pairs separated by commas; roles are `admin`, `executor`, `viewer` | `admin@example.com:admin,exec@example.com:executor` |
| `ANTHROPIC_API_KEY` | Only for the Ask assistant, letter drafting and narration. Leave empty and those features report "not configured" calmly; everything else works. | empty |
| `EMBEDDING_MODEL` | Embedding provider for semantic search; `local` uses a free on-device model. Embeddings only ever run when switched on from Admin, Parameters (off by default: the local model is a ~0.6 GB one-time download and not every machine can run it); search falls back to full-text while off | `local` |
| `STORAGE_BACKEND` / `STORAGE_LOCAL_PATH` | Where uploaded documents and backups are stored | `local` / `./storage` |
| `BACKEND_PORT` | Backend port | `8471` |
| `FRONTEND_ORIGIN` | CORS origin for the dev frontend | `http://localhost:5173` |
| `CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` | Cloudflare Access JWT validation; production only | empty |

The full production table, including Railway specifics, is in `docs/DEPLOY.md` section 3.

## 5. Seeding data

Three ways to get an estate into the database; pick one.

### 5.1 The demo estate (fastest look around)

```bash
# In compose:
docker compose exec backend python -m app.cli seed-demo
# Or locally:
cd backend && uv run python -m app.cli seed-demo
```

Loads a fully synthetic demonstration estate (generic names, round numbers) plus the 41-step process checklist, so every module has something to show. Safe for any environment; it touches nothing real. `--force-fresh` wipes previously seeded rows and reseeds, but refuses to run if any user-entered data exists.

### 5.2 Your own seed file

```bash
python -m app.cli seed --file /path/to/your-seed.json
```

Loads your estate, assets, legacies and settings from a JSON file in the same shape as `backend/seed_templates/demo_estate_seed.json` (use it as the template). Keep your real seed file **outside the repository** or in the git-ignored `seed/` directory; never commit personal data. After seeding, run a recompute (`POST /iht/recompute`) or simply open the IHT page, which recomputes on change.

### 5.3 Just use the UI

Start empty. Create the estate settings on the Inheritance tax page, then add assets, liabilities, contacts and the rest through the interface. The process checklist can be seeded on its own, and every register works from an empty start. This is the right path for a real estate: enter data as documents arrive, with valuations marked estimate or confirmed.

## 6. Loading the knowledge library

The knowledge library (HMRC forms, notes and guidance, read in-app with cited Q&A) starts empty. **Each installation fetches the content from the canonical official and support-organisation sources** rather than the repository redistributing it: the gov.uk material is Crown copyright under the Open Government Licence, and the other sources carry their own licences, recorded per entry in the registry. You always get the current versions, and the pipeline records provenance (source URL, fetch date, content hash) on every document. Multi-page gov.uk guides are followed page by page.

The registry spans 12 domains: 26 gov.uk entries (the IHT400 and its schedules, RNRB and transfer guidance including IHT435, excepted estates, paying IHT, Tell Us Once, clearance, loss reliefs, administration-period tax and more), plus The Gazette (Section 27 notices), NHS England (the medical examiner and MCCD process), nidirect, and bereavement references from Age UK, Marie Curie, Citizens Advice, the Death Notification Service and Life Ledger. Two sites block automated fetching (LITRG and MoneyHelper) and are marked visit-manually in the registry.

The easy way is the bundled script, which auto-detects whether you are running docker compose or a local venv:

```bash
scripts/fetch-knowledge.sh                 # everything in the source registry
scripts/fetch-knowledge.sh IHT400 IHT405   # named sources only
scripts/fetch-knowledge.sh --force         # refresh even if sources are unchanged
```

Prerequisites: the database is up, an estate exists (section 5), and you have internet access. Run it again any time; hash-diff versioning keeps history when guidance changes.

Equivalents, if you prefer:

- **In-app:** the admin-only **Ingest** button on the Knowledge library's Library tab (which calls `POST /knowledge/ingest`).
- **CLI directly:** `python -m app.cli_ingest` (accepts named source keys and `--force`).

`ANTHROPIC_API_KEY` is **not** needed for ingest or search; it is only needed for the Ask assistant and drafting.

## 7. Production

Production deployment (a single container on Railway, PostgreSQL with pgvector, a volume for documents and backups, and Cloudflare Access providing email one-time-PIN login in front) is documented step by step in **`docs/DEPLOY.md`**, including the environment table, the backup schedule and the restore drill. The short version:

- The root `Dockerfile` builds one image: the frontend built with pnpm, the backend served by uvicorn, Alembic migrations at container start.
- `railway.toml` deploys that image to Railway and health-checks `/health`.
- `DEV_AUTH` **must** be `false`; identity then comes from the validated Cloudflare Access JWT, and requests without a valid JWT are rejected.

## 8. Upgrading

```bash
git pull
cd backend && uv run alembic upgrade head    # apply any new migrations
```

Then rebuild and restart whatever you run:

- **Compose:** `docker compose up --build` (the backend container runs migrations at start, so the manual Alembic step is optional there).
- **Railway:** redeploy; the image applies migrations automatically at container start.
- **Local dev:** `uv sync` and `pnpm install` pick up dependency changes.

Take a backup before upgrading a production database: `python -m app.cli_backup create`, then `verify` (see `docs/DEPLOY.md` section 5). Schema migrations are additive by policy, but a verified backup makes that a fact rather than a promise.

## 9. Towards an installable release

This repository currently installs from source. The direction of travel for versioned releases:

- **Tagged GitHub releases.** Each release is a git tag with release notes drawn from `CHANGELOG.md`, so an installation can pin a version rather than tracking the main branch.
- **The one-image Dockerfile as the unit of install.** The root `Dockerfile` already produces a single self-contained image (frontend, backend, migrations); publishing that image per release makes `docker run` plus a database the whole installation.
- **A Railway deploy-from-repo flow.** `railway.toml` is already in place; a templated "deploy this repository" path with the checklist in `docs/DEPLOY.md` is the intended low-effort hosted route.
- **Semantic versioning, starting at v0.9.0.** The 0.9 series signals a complete, tested tool that has not yet earned the stability promises of a 1.0: a good start, not a finished promise. Breaking schema or API changes bump the minor version pre-1.0 and will be noted in the changelog with migration steps.
