# Security Policy

AD Assistant handles some of the most sensitive data a family holds. This document states the security posture plainly: what the tool does to protect that data, what it deliberately cannot do, how to report a vulnerability, and the limits we know about.

## Posture

### Roles are enforced server-side

Every request is authorised on the server against a fixed role (admin, executor, viewer) resolved from the authenticated email via the `USER_ROLES` mapping. The viewer role is strictly read-only and never receives notifications. Individual records can be flagged executor-private and are then withheld from viewers at the API layer. The client is never trusted: hiding a button is a courtesy, the 403 is the control.

### Cloudflare Access JWT validation, fail closed

In production, identity comes from Cloudflare Access. The backend does **not** trust the plain `Cf-Access-Authenticated-User-Email` header: it validates the signed `Cf-Access-Jwt-Assertion` JWT against the team's public signing keys (JWKS), checking signature, audience (`CF_ACCESS_AUD`), issuer (`CF_ACCESS_TEAM_DOMAIN`) and expiry, and takes the identity from the JWT's email claim. Forged headers are rejected. If `DEV_AUTH=false` and Cloudflare Access is not configured, the application **fails closed**: no identity resolves and every request is 401, rather than silently trusting a forgeable header. Implementation: `backend/app/core/cf_access.py`, with tests.

### No personal data in the repository

The public repository contains schema, code and synthetic seed data only. Real estate data lives in each installation's own database and in git-ignored local files. This is a hard policy: pull requests containing personal data are closed, and the repository history was audited before publication. See `CONTRIBUTING.md`.

### Draft-only agents

The LLM agent graphs can read estate data and produce drafts. They have **no tools that send, file or pay**: no email dispatch, no HMRC or probate filing, no payment initiation exists anywhere in `backend/app/agents/`. Every draft creates an approval-pending record and stays a draft until a person approves it. These are not conventions; `backend/tests/test_agent_guardrails.py` enumerates every registered tool and asserts the absence of send/file/pay reachability, and asserts that every drafting path creates an approval record. Separately, no LLM ever computes a tax or accounting figure; all money maths is deterministic, pure and unit-tested (`backend/app/domain/`).

### Audit trail

Every create, change and approval writes an immutable audit event (actor, action, entity, before, after, timestamp). Sensitive reads are audited too: document downloads and access to executor-private metadata. Soft delete with a reason is the only removal in normal operation, so the record stays complete.

### UK GDPR export and erase

`GET /estate/export` returns the entire estate as open-format JSON (portability). `POST /estate/erase` (admin only, with explicit confirmation of the estate name) permanently deletes every estate row and stored file in one transaction; it is the single hard-delete in the application and is recorded in the application log without personal data.

### Backups

`python -m app.cli_backup` produces `pg_dump` archives with sha256 manifests; `verify` recomputes the hash and structurally checks the archive. The restore path is tested in CI where the client tools are present, and a quarterly restore drill is documented in `docs/DEPLOY.md`.

## AI usage guardrails

The knowledge chat calls an external model API (Anthropic). Basic
protections are built in and the tunable ones are parameters on the
admin Params page, audited on change:

- Scope check: a small, fast model classifies each question; unrelated
  questions stop and ask for confirmation before any expensive call runs
  or anything is stored. Fails open so a broken check never blocks a
  grieving user. Toggleable (default on).
- Daily question limit per estate (default 200, adjustable): a hard
  ceiling on usage and cost, HTTP 429 beyond it, resets at midnight UTC.
- Bounded calls: 120 second client timeout, one SDK retry, capped answer
  tokens, at most two contract-validation attempts per answer, question
  length capped at 2,000 characters.
- No-retrieval short-circuit: when nothing relevant is in the library
  and no pinned context exists, the refusal is served without calling
  the model at all.
- Grounding contract: citations are machine-extracted, figures must come
  from the guidance or the app's own records, and answers must declare
  what the guidance does not cover.

## Reporting a vulnerability

Please report vulnerabilities privately through **GitHub security advisories**: on the repository page, Security, then "Report a vulnerability". Do not open a public issue for a security problem.

Include what you can: affected endpoint or component, reproduction steps, impact as you understand it. You can expect an acknowledgement within a few days. Given the sensitivity of the data this tool holds, good-faith reports are genuinely appreciated and will be credited in the fix notes unless you prefer otherwise.

## Known limits (honest list)

- **Single-estate assumption.** The schema scopes every row by estate id, but the application currently operates one estate per installation; there is no per-estate authorisation boundary between multiple estates in one database. Do not host multiple unrelated estates on one installation.
- **No rate limiting yet.** The API has no built-in throttling; brute-force and abuse protection currently relies on Cloudflare Access sitting in front (which keeps unauthenticated traffic away entirely). Self-hosters exposing the API another way should add their own limiter.
- **The development shim must never run in production.** `DEV_AUTH=true` trusts an `X-Dev-User` header for identity, which lets anyone impersonate anyone. It exists for local development only. The production entry point logs a prominent warning if it detects `DEV_AUTH=true` in a production-like environment, and the deploy checklist requires `DEV_AUTH=false`, but the ultimate control is configuration: verify it.
- **Object storage encryption is platform-level.** Database and volume encryption at rest are provided by the hosting platform, not by the application; application-level encryption of stored documents is a candidate hardening item.
- **The origin should still only be reachable through Cloudflare.** JWT validation closes the forged-header hole, but not exposing the raw origin hostname remains good practice (defence in depth, and it keeps unauthenticated traffic off the app entirely).

## Scope note

This tool informs and drafts; it is not advice, and it never files or sends anything. Security reports about making it do those things by design will be declined: the absence of those capabilities is the security model.
