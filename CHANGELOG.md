# Changelog

All notable changes to AD Assistant are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Pre-1.0, breaking changes bump the minor version.

## [Unreleased]

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

[Unreleased]: https://github.com/PaddyGilliland1/ad-assistant/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/PaddyGilliland1/ad-assistant/releases/tag/v0.9.0
