# DEPLOY.md

**Project:** AD Assistant
**Scope:** production deployment (Railway + Cloudflare Access), backups and the restore drill.
**Companion:** `docs/masterdocs/ARCHITECTURE.md` (design), `.env.example` (variable reference), `railway.toml` (Railway build and deploy settings).

> This document contains no personal data. Every email address and domain shown is a placeholder.

---

## 1. What gets deployed

One container, built from the root `Dockerfile`, serves everything:

- **Stage 1** (node:20) builds the React frontend with pnpm (`VITE_API_URL` is empty, so the SPA calls the API on its own origin).
- **Stage 2** (python:3.12-slim) installs the backend with uv, adds the PostgreSQL 16 client tools (for `pg_dump` backups) and copies the built frontend into `/app/frontend_dist`.
- At start the container runs `alembic upgrade head`, then `uvicorn app.prod:app`. `app.prod` wraps the API app from `app.main` and serves the SPA (with an index.html fallback for client-side routes) whenever `FRONTEND_DIST` points at the build output.

`railway.toml` tells Railway to build that Dockerfile, health-check `/health` and restart on failure.

## 2. Railway setup, step by step

1. **Create the project.** In Railway, create a project and add:
   - a **PostgreSQL** database. The knowledge library needs the `pgvector` extension, so use Railway's pgvector-enabled Postgres template (or confirm `CREATE EXTENSION vector;` succeeds on the instance).
   - a **service from this GitHub repository**. Railway picks up `railway.toml` and builds the root `Dockerfile`.
2. **Attach a volume** to the app service, mounted at `/data`. It holds uploaded documents and backups. Set `STORAGE_LOCAL_PATH=/data`.
3. **Set the environment variables** on the app service (table in section 3). The database URL must use the asyncpg driver, so compose it from Railway's reference variables rather than copying `DATABASE_URL` verbatim:

   ```
   DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}
   ```

4. **Deploy.** The first deploy runs the Alembic migrations. Confirm `/health` returns `{"status": "ok"}`.
5. **Add the public hostname.** Use a custom domain whose DNS is managed by Cloudflare (required for Cloudflare Access, section 4). Point a proxied (orange-cloud) CNAME at the Railway service's target.

## 3. Environment variables (production)

| Variable | Value in production | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` (see above) | asyncpg driver required |
| `DEV_AUTH` | **`false` (MUST)** | `true` would let anyone impersonate any user via the `X-Dev-User` header. `app.prod` logs a prominent warning at startup if `DEV_AUTH` is true while a `RAILWAY_*` variable is set. |
| `USER_ROLES` | `alice@example.com:admin,bob@example.com:executor,carol@example.com:viewer` | Server-side email-to-role mapping; roles are `admin`, `executor`, `viewer`. An email absent from this list gets 403 even after passing Cloudflare Access. |
| `CF_ACCESS_TEAM_DOMAIN` | `yourteam.cloudflareaccess.com` | From Cloudflare Zero Trust settings |
| `CF_ACCESS_AUD` | the application's AUD tag | From the Access application overview |
| `STORAGE_BACKEND` | `local` | R2 backend is not implemented yet |
| `STORAGE_LOCAL_PATH` | `/data` | The mounted Railway volume; backups land in `/data/backups` |
| `FRONTEND_DIST` | `/app/frontend_dist` | Already set in the image; do not override unless serving a different build |
| `PORT` | (injected by Railway) | uvicorn binds to it; falls back to 8471 |
| `ANTHROPIC_API_KEY` | your key | Agent graphs |
| `EMBEDDING_MODEL` | embedding model id | Knowledge library |
| `FRONTEND_ORIGIN` | `https://your-app-domain.example` | CORS; with the SPA served from the same origin this is belt and braces |

## 4. Cloudflare Access in front

Cloudflare Access performs the login; the backend maps the authenticated email to a role. Steps:

1. In **Cloudflare Zero Trust**, note your team domain (`yourteam.cloudflareaccess.com`).
2. **Add an Access application** (type: self-hosted) for the app hostname, e.g. `estate.example.com`.
3. Create an **Allow policy** listing the executors', admin's and viewer's email addresses (Include: Emails). Access sends a one-time PIN or uses your configured identity providers.
4. Copy the application's **AUD tag** into `CF_ACCESS_AUD`, and the team domain into `CF_ACCESS_TEAM_DOMAIN`.
5. Keep the DNS record **proxied** so every request traverses Cloudflare; Access injects `Cf-Access-Authenticated-User-Email` towards the origin.
6. Roles are then assigned by `USER_ROLES` (section 3). Someone who passes Access but is not in `USER_ROLES` gets 403: both lists must be maintained together.

**Origin exposure warning (current limitation).** The backend trusts the `Cf-Access-Authenticated-User-Email` header; it does not yet validate the accompanying `Cf-Access-Jwt-Assertion` JWT against `CF_ACCESS_TEAM_DOMAIN`/`CF_ACCESS_AUD` (a known deferred hardening item; the settings already exist for it). Until that lands, anyone who can reach the Railway origin directly could forge the header. Mitigate now by not publishing the `*.up.railway.app` hostname and serving only via the Cloudflare-proxied domain; close it properly by adding JWT validation or fronting the origin with a Cloudflare Tunnel so it is unreachable except through Cloudflare.

## 5. Backups (RQ-9)

### Taking a backup

The container ships `pg_dump` (PostgreSQL 16 client) and a CLI:

```bash
python -m app.cli_backup create        # pg_dump (custom format) + sha256 manifest
python -m app.cli_backup list          # newest first
python -m app.cli_backup verify <file> # sha256 vs manifest AND pg_restore --list
```

Backups are written to `STORAGE_LOCAL_PATH/backups` (the Railway volume, `/data/backups`), named `ad_backup_<UTC timestamp>.dump` with an `ad_backup_<timestamp>.manifest.json` alongside carrying the sha256, size and source database.

### Scheduling on Railway

Two workable approaches; pick one and check it runs:

1. **Scheduled Railway service (recommended).** Add a second service from the same repo and image, attach the SAME volume at `/data`, set the same `DATABASE_URL`/`STORAGE_LOCAL_PATH`, give it a cron schedule (daily, e.g. `30 02 * * *`) and the start command `python -m app.cli_backup create`. The service runs, writes the dump to the shared volume and exits.
2. **External pg_dump.** From a trusted machine, run `railway connect postgres` (or use the database's TCP proxy) and `pg_dump --format=custom` to local disk on a daily cron. This keeps a copy off-platform, which is also your protection against losing the Railway project itself.

Whichever you choose, copy backups off the volume periodically (they live next to the documents they protect): `railway ssh` + download, or run approach 2 weekly in addition.

### Restore drill (tested restore, not assumed)

The automated test `backend/tests/test_hardening.py::TestBackups` performs a create + verify round trip against a live database whenever `pg_dump`/`pg_restore` are on PATH (it SKIPS with a clear reason when they are not, so a machine without postgresql-client still runs the rest of the suite). Beyond that, rehearse a full restore quarterly:

```bash
# 1. Verify the artefact first
python -m app.cli_backup verify ad_backup_<timestamp>.dump

# 2. Restore into a scratch database (never straight over production)
createdb -h <host> -U <user> ad_restore_drill
pg_restore --no-owner --dbname postgresql://<user>:<pw>@<host>:5432/ad_restore_drill \
    /data/backups/ad_backup_<timestamp>.dump

# 3. Sanity-check the restored data
psql -d ad_restore_drill -c "SELECT count(*) FROM estate;"
psql -d ad_restore_drill -c "SELECT count(*) FROM audit_event;"

# 4. Drop the scratch database
dropdb -h <host> -U <user> ad_restore_drill
```

Document the date and outcome of each drill. A backup that has never been restored is a hope, not a backup. Note that the database backup covers rows only: uploaded document files live on the volume under `STORAGE_LOCAL_PATH` and are covered by copying the volume contents (the off-platform copy above).

## 6. UK GDPR endpoints (operational notes)

- `GET /estate/export` (admin and executor): complete JSON export of every estate-scoped table, for portability and for a belt-and-braces export before any risky operation.
- `POST /estate/erase` (admin only, body `{"confirm": "<exact estate name>"}`): **hard-deletes** every row of the estate in one transaction and removes stored files. This is the only hard-delete in the application. The audit trail is deleted with the estate; the erasure itself is recorded as a warning line in the application log (estate id and row counts only). **Take a backup and an export first if there is any chance the data is needed again.**

## 7. Deploy checklist

```
[ ] Postgres (pgvector) provisioned; DATABASE_URL uses postgresql+asyncpg://
[ ] Volume mounted at /data; STORAGE_LOCAL_PATH=/data
[ ] DEV_AUTH=false            (startup warning fires if not)
[ ] USER_ROLES set and matches the Access policy emails
[ ] Cloudflare Access app created; CF_ACCESS_TEAM_DOMAIN + CF_ACCESS_AUD set
[ ] Custom domain proxied through Cloudflare; Railway domain not shared
[ ] /health returns ok; app loads through the Access login
[ ] Backup schedule created; first backup verified (cli_backup verify)
[ ] Restore drill performed and dated
```
