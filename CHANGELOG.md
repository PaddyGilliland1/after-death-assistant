# Changelog

All notable changes to AD Assistant are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Pre-1.0, breaking changes bump the minor version.

## [Unreleased]

## [0.10.0] - 2026-07-18

The knowledge assistant, rebuilt: a real conversation over the official guidance, grounded in your estate's own records, with honest citations and sensible guardrails. Plus a page of humans to call when an app is not enough.

### Added

- **Conversational knowledge assistant.** The one-shot Ask box is now a chat with named conversations and follow-up memory (per-conversation history with a rolling summary). Answers use Anthropic API-native citations: numbered markers sit next to the statements they support, every cited source lists the exact passages it was quoted for, and sources that were retrieved but not relied on are listed separately as related sources. Every answer ends with a "What the retrieved guidance does not cover" section, enforced by a validation contract with automatic retry.
- **Context harness.** The assistant sees the estate's live position on every turn: registers with estimate flags, task and timeline progress including executor comments, and the latest tax assessment. Key passages are pinned into an estate-wide pool that persists across conversations until the records change. Figures still come only from the registers and the deterministic engine; the assistant explains them and never invents them.
- **Optional semantic search.** A new admin Parameters page can switch on local embeddings (mixedbread mxbai-embed-large-v1 via fastembed, nothing leaves the machine). Off by default because the model is a large download with a real CPU load; enabling it runs a background backfill with progress reporting, and retrieval gains a pgvector arm alongside the always-available full-text baseline.
- **Corpus expansion to 77 sources.** Every document the app references elsewhere is now cached in the knowledge library, including NS&I bereavement and Premium Bonds guidance, Marie Curie, bereavement financial-support guides and the missing-accounts services, so the assistant answers from the same sources the app points at.
- **AI guardrails as audited parameters.** A fast-model scope check pauses questions that look unrelated to estate administration for user confirmation; a per-estate daily question limit caps cost; API calls carry explicit timeouts and a single retry. The scope check and daily limit are admin-editable parameters, and every change is audited with before and after values. Bounds are documented in the security policy.
- **When you need help page.** A verified directory of 17 support organisations, from Samaritans to the HMRC inheritance tax helpline, grouped as someone to talk to, practical help and money, armed forces families, and tax and probate. Phone numbers are tap-to-dial links with hours shown; every number was checked against the organisation's own website, with the verification date on the page and honest "check the website" notes where verification was blocked.

### Changed

- The assistant model is now `claude-sonnet-5` with prompt caching; the deterministic engine remains model-free.
- The defunct Experian Unclaimed Assets Register (closed 2022) was replaced by Gretel throughout the app and corpus.

### Fixed

- Tasks and timeline steps stay in sync in both directions, with a `reconcile-steps` CLI to repair drift from before the fix.
- Chat conversations are strictly estate-scoped.
- Test suite now 329 backend and 125 frontend tests.

## [0.9.0] - 2026-07-09

Initial public release: a complete, tested estate administration and inheritance tax tool for executors in England and Wales.

### Added

- **Deterministic IHT engine** with full excepted-estates logic (SI 2004/2543 as amended): nil rate band, residence nil rate band with the 2,000,000 taper, transferred allowances, the 36 per cent charity rate, and the hard rule that an RNRB claim forces a full IHT400. Pure, unit-tested Python; no LLM ever computes a figure.
- **Estate accounts** with the four-account structure (capital, administration, income, distribution), live beneficiary shares and an always-visible `is_balanced` reconciliation check.
- **29-table relational model** (PostgreSQL 16 + pgvector): estate, assets with valuation history, liabilities, debtors and creditors with the Section 27 notice workflow, contacts with the notification tracker, tasks with dependencies, costs, legacies and distributions, process steps, deadlines, documents, reliefs, administration-period tax, digital items, decisions, knowledge corpus, notifications, approvals, audit events and cross-record links.
- **83-endpoint REST API** (FastAPI, Pydantic v2 at every boundary) covering all registers, the IHT workbench, estate summary and accounts, knowledge search and Q&A, agent drafting, approvals, exports, audit, activity, global search and GDPR export/erase.
- **19-module React UI** (React 18, Vite, TypeScript, Tailwind + shadcn/ui, ECharts): dashboard with timeline progress and re-evaluation alerts, tasks with a status chart, all registers, estate accounts, the IHT workbench, knowledge library, drafts, timeline, reliefs, administration tax, tracing, digital assets, veteran checklist, executor decision log, and settings with audit and search.
- **Knowledge library** with provenance-tracked ingestion from official and support-organisation sources across 12 domains (gov.uk under the Open Government Licence, The Gazette, NHS England, nidirect and bereavement references, each with its licence recorded; multi-page gov.uk guides followed; hash-diff versioning with change flags), hybrid retrieval (full text plus pgvector with reciprocal rank fusion), and **cited plain-English Q&A** that refuses to answer beyond the cached corpus. `scripts/fetch-knowledge.sh` fetches the starter corpus into a new installation.
- **Five draft-only LangGraph agent graphs** (knowledge ingest, IHT narration, forms draft, guidance Q&A, next actions), each with read/draft-only tools and human approval gates. Nothing is ever sent, filed or paid by code; guardrail tests assert it.
- **PDF exports**: estate accounts, IHT draft content sheet, IHT30 clearance draft, and approved notification letters.
- **RBAC via Cloudflare Access** with full JWT validation (`Cf-Access-Jwt-Assertion` verified against the team's signing keys; forged headers rejected; fail closed when unconfigured). Server-side roles: admin, executor, viewer; executor-private records; a development sign-in shim strictly for `DEV_AUTH=true`.
- **UK GDPR endpoints**: complete open-format JSON estate export, and admin-only estate erasure with explicit confirmation.
- **Backups**: `python -m app.cli_backup` (create, list, verify) producing `pg_dump` archives with sha256 manifests, plus a documented restore drill.
- **Immutable audit trail** covering writes, approvals and sensitive reads; co-executor notifications; soft delete everywhere except GDPR erasure.
- **Production image**: single Dockerfile serving API and SPA from one container, Alembic migrations at start, Railway deployment via `railway.toml`.
- **Test suite: 307 backend and 119 frontend tests**, including the executable IHT test table and the agent guardrail contract.

[Unreleased]: https://github.com/PaddyGilliland1/after-death-assistant/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/PaddyGilliland1/after-death-assistant/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/PaddyGilliland1/after-death-assistant/releases/tag/v0.9.0
