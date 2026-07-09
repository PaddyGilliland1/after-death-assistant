# ARCHITECTURE.md

**Project:** AD Assistant (estate administration and IHT tool, England and Wales)
**Version:** 1.1 | **Date:** 2026-07-09 | **Status:** Canonical design master
**Sources:** build contract (claude-code-build-prompt.md), requirements spec v0.4, technical thesis v0.2, project CLAUDE.md
**Precedence on conflict:** build contract > technical thesis > requirements summaries > this document

> This document ships in the public repository. It contains no personal data. All values shown anywhere in the master set are synthetic examples.

---

## 1. System overview

A small, well-shaped web application for a handful of trusted users administering one estate: deterministic tax logic at the core, a typed REST API, a React interface, and LangGraph agents that research and draft but never act without human approval. One estate, sensitive data, and a hard requirement to get the HMRC paperwork right. Every choice below follows from that: correctness and provenance over cleverness, a proven hosting path, and a firm human-approval gate on anything final, filed or sent.

```
Browser (executors, admin, viewer)
        |
        v
Cloudflare Access  (email login, free; injects Cf-Access-Authenticated-User-Email)
        |
        v
FastAPI backend (Python 3.12) .......... port 8471 (dev)
  |-- app/api/            REST routers per module, RBAC enforced server-side
  |-- app/domain/         PURE deterministic core: iht_engine, estate_accounts,
  |                       deadlines, jurisdiction/ (no I/O, no LLM, unit-tested)
  |-- app/agents/         5 LangGraph graphs, read/draft-only tools,
  |                       human-approval interrupts
  |-- app/ingest/         knowledge pipeline + source registry
  |-- app/services/       notifications (in-app + optional email)
        |
        +--> PostgreSQL 16 + pgvector   (single datastore: structured data
        |                                AND knowledge-library embeddings)
        +--> Object storage             (documents vault, cached source PDFs;
                                         local volume dev, R2/Railway volume prod)

React 18 + Vite + TypeScript frontend .. port 5173 (dev)
  Tailwind + shadcn/ui, ECharts, TanStack Query, React Router
  src/modules/{dashboard,tasks,assets,debtors_creditors,contacts,costs,
               accounts,iht,knowledge,documents,timeline,reliefs,admin_tax,
               tracing,digital,veteran,executor}/
```

Key structural decisions:

| Decision | Rationale |
|---|---|
| Single Postgres with pgvector, no separate vector DB | Corpus is small (dozens of gov.uk pages, low thousands of chunks). One datastore to run, back up and self-host. Retrieval sits behind an interface so a large multi-estate deployment could swap in a dedicated vector store without touching the rest. |
| Pure Python domain core, separate from agents | The numbers must never depend on a model. `iht_engine.py`, `estate_accounts.py` and `deadlines.py` are pure functions with no I/O, fully unit-tested. |
| Cloudflare Access, not app-managed passwords | Free, email-based, no credentials to hold, clean read-only for the viewer, revoke in one click. |
| LangGraph for agents | Explicit graph, human-in-the-loop interrupts for approval gates, tool guardrails. |
| Jurisdiction isolation | England and Wales rules live behind `backend/app/domain/jurisdiction/`; the core engine stays regime-agnostic so contributors can add Scotland, Northern Ireland or other regimes. |

## 2. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + SQLModel, Alembic |
| Agents | LangGraph |
| Database | PostgreSQL 16 + pgvector extension |
| Object storage | Local volume (dev); Cloudflare R2 or Railway volume (prod) |
| Frontend | React 18, Vite, TypeScript, Tailwind + shadcn/ui, ECharts, TanStack Query, React Router |
| Auth edge | Cloudflare Access (optional Cloudflare Tunnel for local) |
| Deploy | Railway (app + managed Postgres); docker-compose for dev |
| Licence | MIT; repository private until verified clean of personal data, then public |

## 3. Process and deployment model

### Development
`docker compose up` starts three services:

| Service | Port | Notes |
|---|---|---|
| PostgreSQL 16 + pgvector | **5474** (host) -> 5432 (container) | single datastore, structured data + embeddings; 5432/5433 are taken by other local projects |
| Backend (FastAPI + Uvicorn) | **8471** | avoid 8000/8007/8464, taken by other local projects |
| Frontend (Vite dev server) | **5173** | proxies API calls to 8471 |

Standalone: `cd backend && uvicorn app.main:app --reload --port 8471` and `cd frontend && pnpm dev`.

### Production
Deployed as **one container** built from the root `Dockerfile` (multi-stage: node:20 pnpm-builds the frontend; python:3.12-slim runs the uv-managed backend with the PostgreSQL 16 client tools and the built SPA copied in). Step-by-step guide: `docs/DEPLOY.md`.

- **Entry point:** `uvicorn app.prod:app`. `app/prod.py` wraps the API app from `app/main.py` (which stays dev/API-only and is never edited for deployment) and serves the built frontend when `FRONTEND_DIST` points at it: real files (Vite's hashed `/assets/` bundles) are served ahead of the API routers, unknown paths fall back to `index.html` so client-side routes survive reloads. It also logs a prominent startup warning if `DEV_AUTH=true` while a `RAILWAY_*` variable is set.
- **Railway** hosts the container and managed Postgres (pgvector-enabled); `railway.toml` selects the Dockerfile build, health-checks `/health` and restarts on failure. A Railway **volume** mounted at `/data` (`STORAGE_LOCAL_PATH=/data`) holds uploaded documents and backups. Railway injects `PORT`; the image falls back to 8471.
- **Cloudflare Access** sits in front of the public hostname (proxied DNS); only authenticated emails reach the app, and `USER_ROLES` maps each email to a role server-side. The origin must not be reachable except through Cloudflare until Access JWT validation lands (see DEPLOY.md section 4).
- **Alembic migrations run at container start** (`alembic upgrade head` before uvicorn).
- TLS in transit; encryption at rest for the database and volume is provided by the platform. Secrets live only in environment configuration.

### Backups and restore (RQ-9)
- `python -m app.cli_backup create` runs `pg_dump` (custom format) into `STORAGE_LOCAL_PATH/backups`, timestamped, with a JSON manifest carrying the sha256. `list` enumerates backups; `verify <file>` recomputes the sha256 against the manifest AND runs `pg_restore --list` on the archive. Implementation: `backend/app/services/backup.py`.
- Scheduled daily on Railway (cron service sharing the volume) or via an external `pg_dump`; copies are taken off-platform. The restore is **tested, not assumed**: an automated create+verify round trip runs in `backend/tests/test_hardening.py` (skipped with a stated reason when `pg_dump` is not on PATH), and a quarterly full restore drill into a scratch database is documented in `docs/DEPLOY.md` section 5.
- The database dump covers rows only; uploaded document files are covered by copying the volume contents.

### UK GDPR endpoints (RQ-1)
- `GET /estate/export` (admin and executor): complete JSON export of every estate-scoped table (iterates the model metadata, so new tables are exported automatically; Decimals exported as exact strings). Audited.
- `POST /estate/erase` (admin only, body `{"confirm": "<exact estate name>"}`): **the one hard-delete in the application**. Deletes every estate row in reverse FK dependency order inside a single transaction, then the estate row, then removes stored files best-effort. Soft delete is not erasure. Because the audit rows die with the estate, the erasure is recorded as a survivor line in the application log (estate id and row counts only, no personal data).
- Sensitive reads are audited (RQ-3): every document download emits a `download` audit event; reading executor-private document metadata emits `view_private`.

## 4. Authentication and authorisation

### Flow (production)
1. User hits the app URL; Cloudflare Access intercepts and performs email-based login.
2. Cloudflare injects `Cf-Access-Authenticated-User-Email` on every request to the origin.
3. FastAPI middleware in `app/main.py` resolves the identity and maps the email to a role via `USER_ROLES` (`app/core/auth.py`). **The plain header is not trusted in production:** `app/core/cf_access.py` validates the accompanying `Cf-Access-Jwt-Assertion` JWT against the team's public signing keys (JWKS fetched from the team domain and cached), checking signature, audience (`CF_ACCESS_AUD`), issuer and expiry, and takes the email from the JWT claim. Forged headers are rejected. With `DEV_AUTH=false` and Cloudflare Access unconfigured, the app **fails closed** (no identity resolves; every request is 401). The origin-exposure warning in earlier revisions of DEPLOY.md section 4 predates this landing; keeping the origin reachable only through Cloudflare remains good defence in depth.
4. `GET /me` returns the resolved role; every router enforces role permissions server-side. **Never trust the client.**

### Roles

| Capability | Admin | Executor | Viewer |
|---|---|---|---|
| View all estate data | Yes | Yes | Read-only, minus executor-private items |
| Add and edit records | Yes | Yes | No |
| Approve drafts, forms, letters | Yes | Yes | No |
| Configure estate settings and roles | Yes | Limited | No |
| Export and delete estate | Yes | With confirmation | No |

Individual records can be flagged executor-private to hide them from the viewer. The viewer is never sent notifications and never sees write controls. Every change is attributed and logged (see PROCESSES.md, audit trail).

### Dev shim
When `DEV_AUTH=true`, the backend trusts an `X-Dev-User` header instead of Cloudflare. This flag MUST be false in production; the middleware refuses the shim path when it is.

## 5. Storage model

| Store | Holds | Notes |
|---|---|---|
| PostgreSQL (relational) | All business tables (see DATA_MODEL.md), audit events, approvals, notifications, knowledge metadata | UUID PKs, audit columns, soft delete, `estate_id` scoping |
| PostgreSQL (pgvector) | `knowledge_chunk.embedding` vectors | Hybrid retrieval: tsvector full-text + cosine similarity, reranked, always cited |
| Object storage | Documents vault files, raw cached source PDFs/pages (`file_key`, `raw_file_key`) | Encrypted at rest, versioned, role-restricted access, soft delete only |

Data-protection posture: living beneficiaries' data is personal data under UK GDPR. Minimise what is held, restrict by role, support full estate export and deletion. Retain estate records around 12 years for HMRC and executor protection, then purge.

## 6. Two-repo pattern (public code, private data overlay)

| Repo | Location | Visibility | Holds |
|---|---|---|---|
| `ad-assistant` (code) | `/home/paddy/projects/AD` | private now, **public at gift time** | code, schema, synthetic seed, these master docs; clean by construction |
| `AD-estate` (data overlay) | `/home/paddy/projects/AD-estate` | **permanently private** | real personal data: handoff documents, `seed/`, generated drafts |

The code repo contains gitignored **symlinks** into the data overlay (`claude-code-build-prompt.md`, `requirements-spec.html`, `technical-thesis.html`, `seed`), so everything reads from its expected path but git never sees the content. Anything generated during real estate work that contains personal data is committed to the data overlay, never to the code repo. The real seed file lives at `seed/` (gitignored); the repo ships a synthetic seed only.

Before flipping the code repo public: full history audit (gitleaks plus a manual scan for names and values). Never `git add -f` a gitignored path.

## 7. Environment variables

From `.env.example` (never commit `.env`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (asyncpg driver) |
| `DEV_AUTH` | `true` enables the `X-Dev-User` dev shim; MUST be `false` in prod |
| `CF_ACCESS_TEAM_DOMAIN` | Cloudflare Access team domain, e.g. `yourteam.cloudflareaccess.com` |
| `CF_ACCESS_AUD` | Cloudflare Access application audience tag (JWT validation) |
| `USER_ROLES` | Server-side email-to-role mapping: `email:role,email:role` (roles `admin`, `executor`, `viewer`) |
| `ANTHROPIC_API_KEY` | LLM for the agent graphs |
| `EMBEDDING_MODEL` | Embedding model id for pgvector chunks |
| `STORAGE_BACKEND` | `local` (dev) or R2 |
| `STORAGE_LOCAL_PATH` | Local object-storage path (dev) |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | Cloudflare R2 (prod) |
| `BACKEND_PORT` | 8471 |
| `FRONTEND_ORIGIN` | CORS origin, `http://localhost:5173` in dev |
| `FRONTEND_DIST` | Directory the production wrapper (`app/prod.py`) serves the built SPA from; set in the Dockerfile |
| `PORT` | Injected by Railway; uvicorn binds to it (falls back to 8471) |

## 8. Repository structure (code repo)

```
backend/
  app/main.py              FastAPI app, identity middleware, role resolution
  app/prod.py              production wrapper: API + built SPA in one container
  app/core/cf_access.py    Cloudflare Access JWT validation (fail closed)
  app/api/                 routers per module (FEATURES.md section on API)
  app/models/              SQLModel tables (DATA_MODEL.md)
  app/domain/iht_engine.py deterministic IHT: assess(estate, constants) -> Assessment
  app/domain/estate_accounts.py  trial balance + beneficiary shares, is_balanced
  app/domain/deadlines.py  statutory date derivations
  app/domain/jurisdiction/ England-and-Wales rules, isolated
  app/agents/              LangGraph graphs + tools (AGENT_DESIGN.md)
  app/ingest/              knowledge pipeline + source registry
  app/services/notifications.py  co-executor alerts
  migrations/              Alembic
  tests/                   pytest, incl. test_iht_engine.py and test_agent_guardrails.py
frontend/
  src/modules/             one directory per module
  src/lib/api.ts, src/lib/auth.ts, src/components/
seed/                      GITIGNORED symlink to the private data overlay
docker-compose.yml  .env.example  LICENSE (MIT)  README.md  CONTRIBUTING.md
docs/masterdocs/           this design master set
```

## 9. Non-negotiable guardrails (architectural invariants)

1. **No automated filing or sending.** Agents draft; a person approves; a person submits or sends. No HMRC filing, no email or letter dispatch, no payment, from code.
2. **Deterministic money.** IHT and estate-accounts maths live in the pure, unit-tested domain core. No LLM computes a figure; agents explain figures only.
3. **Provenance.** Every tax constant and guidance item carries its source URL and fetch date. Agent output is a draft until an approval record exists.
4. **Roles enforced server-side.** Executor and admin write; viewer strictly read-only.
5. **No personal data in git.** Schema and synthetic seed only in the code repo.
6. **UK English throughout UI and content. No em dashes.**
7. **Accessibility:** WCAG 2.2 AA target. Calm, plain interface suited to bereavement.

## 10. Changes since version 1.0 (as built, 2026-07-09)

Structural deltas landed after the v1.0 design pass; everything above stands unless amended here.

- **Cloudflare Access JWT validation shipped** (`app/core/cf_access.py`): signature, audience, issuer and expiry checks against the team JWKS (cached, refreshed on unknown key id), identity taken from the JWT email claim, fail-closed when production auth is unconfigured. Section 4 above reflects the as-built behaviour; the deferred-item row in DEFERRED_ITEMS.md is superseded.
- **Assistant model pinned to Claude Sonnet 5** (`claude-sonnet-5`) for the agent graphs and knowledge Q&A (`app/agents/llm.py`, `app/api/knowledge.py`). Deterministic money remains model-free.
- **Ingest pipeline follows multi-page gov.uk guides** (landing page plus part pages combined into one document) and supports a `force` re-ingest flag; `scripts/fetch-knowledge.sh` is the operator entry point. Retrieval merges full-text and vector results with reciprocal rank fusion, and falls back to per-term rank fusion when embeddings are not configured.
- **Frontend additions:** the development sign-in screen (rendered only when `DEV_AUTH` identity is missing in dev; never in production), the dashboard timeline progress card (`GET /process/timeline`), and the tasks status donut (ECharts, SVG renderer, screen-reader table).
- Already reflected above (sections 3 and 8) and re-confirmed as built: `app/prod.py` single-container SPA serving with the static-first dispatcher, the `app.cli_backup` create/list/verify CLI, and the UK GDPR export and erase endpoints.
