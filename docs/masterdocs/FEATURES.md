# FEATURES.md

**Project:** AD Assistant | **Version:** 1.1 | **Date:** 2026-07-09 | **Status:** Canonical design master
**Source of truth:** requirements spec v0.4 (modules 1 to 19, section 20); build contract sections 5, 8, 11

> Public document. No personal data. All figures are synthetic examples or statutory constants with provenance requirements.

---

## 1. Feature inventory (Modules 1 to 19)

### Module 1: Tasks and actions
The spine of the tool: a living action list with owners, dates, dependencies, checklists and comments that seeds itself from the standard England-and-Wales administration process and from the estate's own contents. Statuses run not_started, in_progress, blocked, waiting_third_party, done, cancelled; priorities low to critical; sources manual, template, auto_deadline, agent_suggested.
Key behaviours: a task cannot be completed while any blocking task is open (the UI shows why); template tasks are seeded per process step and tailored to estate contents (a new property spawns valuation and insurance tasks); auto-deadline tasks come from the deadlines engine; overdue and due-soon tasks surface on the dashboard and to assignees. Views: list, my tasks, calendar, board by status, and a dependency or critical-path view from death certificate to clearance. Export supported.
API: `GET/POST/PATCH /tasks`, `/task-comments`; suggestions arrive via `POST /agents/suggest-tasks` and become tasks only on approval.

### Module 2: Assets and liabilities
The complete register of what the deceased owned and owed, from a library card to a six-figure account. Each asset carries date-of-death value, valuation provenance (source and date), estimate-or-confirmed basis, ownership basis (sole, joint tenants with survivorship, tenants in common with share percentage), the auto-mapped IHT schedule, an RNRB-qualifying flag and a passes-outside-estate flag. Liabilities carry type, creditor, amount and an IHT-deductible flag.
Key behaviours: adding or editing any asset updates the net estate and the IHT assessment in the same view; survivorship assets are shown but excluded from the taxable total; valuation history is retained per asset for later CGT; archiving with a reason is the only removal.
API: `GET/POST/PATCH /assets`, `/liabilities`; valuation events recorded per asset; every write triggers re-evaluation (section 2 below).

### Module 3: Debtors and creditors
Money owed to the estate (debtors) and by the estate (creditors), each tracked to settlement, plus the statutory Section 27 creditor-notice workflow that protects the executors before they distribute.
Key behaviours: the claim deadline derives automatically (placement + 2 months) with a countdown; `safe_to_distribute` is true only when the window is closed and creditors settled or provisioned; estate accounts will not mark residue safe to pay out until then; settled creditors and received debtors reconcile against the estate account and costs.
API: `GET/POST/PATCH /debtors`, `/creditors`; creditor-notice and claims managed within the creditors module.

### Module 4: Contacts and notification tracker
A simple CRM for everyone and every organisation involved, with an interaction log and a tracker of who needs telling, how and when. Categories span institutions (bank, NS&I, insurer, pension, utility, telecom, TV Licensing, streaming, council), officialdom (HMRC, probate registry, registrar), professionals (solicitor, accountant, valuer), personal services (GP, dentist, optician, employer, landlord, care agency) and estate parties (beneficiary, gift recipient, creditor, debtor, executor, membership).
Key behaviours: a dedicated notification-tracker view lists every contact where `notify_required` is true with status, method and date, answering "who to contact, when and how" on one screen; centralised routes are built in (Tell Us Once, The Gazette, HMRC, the probate service) plus the free bulk services (Death Notification Service, Life Ledger, Settld); each interaction can set a follow-up that becomes a task; contacts link bidirectionally to assets, liabilities, tasks, costs and documents.
API: `GET/POST/PATCH /contacts`, `/contact-interactions`.

### Module 5: Cost tracking
Every cost of administering the estate: who paid it, what it relates to, whether it is reimbursable, and its IHT treatment (funeral deductible; general admin not deductible but reducing residue). Feeds the estate accounts and a per-person reimbursement ledger (out of pocket versus reimbursed versus outstanding).
Key behaviours: co-executor alert on any cost recorded or edited (in-app, optional email; configurable threshold, default every cost); a costs-by-type view totals spend per category with an ECharts chart and a running total, filterable by date, payer and process step; every cost links to what caused it so the total is explainable line by line; the viewer is never notified and never sees cost-entry controls.
API: `GET/POST/PATCH /costs`; writes emit `audit_event` and co-executor `notification`.

### Module 6: Estate accounts and beneficiary shares
The transparent trial balance: capital account (assets at date-of-death value less deductible liabilities and funeral = net estate for probate), administration account (net estate plus realisation gains or losses, minus admin costs, minus IHT, minus pecuniary and specific legacies = residue), income account (administration-period income less expenses and tax), distribution account (residue and income split by residuary share, less interim distributions = balance due).
Key behaviours: the trial balance always reconciles (assets = liabilities + costs + legacies + tax + residue) with a visible imbalance indicator; beneficiary entitlements recalculate live on any change to assets, costs, legacies or tax; interim distributions are guarded by the creditor-notice and claims-window checks; final estate accounts export to PDF for residuary beneficiaries to approve. Worked shape: net estate, less admin costs and any IHT, less pecuniary and specific legacies and exempt gifts, gives the residue, which splits by each residuary share and updates live as confirmed figures replace estimates.
API: `GET /estate/accounts` (trial balance), `GET/POST/PATCH /beneficiary-legacies`, `/distributions`.

### Module 7: Process timeline and who-to-contact
The administration as an ordered England-and-Wales process, death certificate to clearance (18 steps; see PROCESSES.md for the full list). Each step links to its tasks, contacts, costs and the relevant guidance, and derives its status from linked tasks.
Key behaviours: per-step status, deadline and one-click access to guidance; steps expose blockers via the task dependency graph; bereavement support routes (Cruse, Age UK, Marie Curie, Sue Ryder, the GP) and benefit checks surface alongside the process.
API: `GET/POST/PATCH /process-steps`.

### Module 8: Deadlines and reminders
A small engine (`domain/deadlines.py`) that derives statutory dates from the date of death and the grant date and drives reminders and auto-created tasks: IHT payment (end of the 6th month after death), IHT400 delivery (12 months from the end of the month of death), Tell Us Once (28 days from the reference number), creditor-notice window (placement + 2 months), claims window (6 months from grant), CGT on property sale (60 days from completion), deed of variation (2 years from death), IHT35 share loss (12 months from death), IHT38 land loss (4 years from death).
Key behaviours: reminders configurable per deadline and per task; overdue and due-soon items surface on the dashboard and to assignees; late-payment interest on IHT is noted against the payment date (rate is a provenance-tracked constant).
API: `GET/POST/PATCH /deadlines`.

### Module 9: IHT assessment workbench
Computes the position from the registers with the deterministic engine, states the reporting route and presents a line-by-line breakdown a person can check, constants version-stamped to source. Requirements: NRB and transferred NRB; RNRB and transferred RNRB capped at the home value passing to descendants, with the 2m taper; chargeable estate, taxable amount, estimated tax; the 36% reduced rate when 10% or more passes to charity; excepted-estate versus full IHT400 determination applying the hard rule that any RNRB claim forces a full IHT400; the required-schedules checklist derived from estate contents; deadline feed to Module 8; an optional professional-review checkpoint, on by default given thin margins near the threshold.
Key behaviours: never a model-computed figure; every recompute snapshots to `iht_assessment`; drafting of completed forms is a later phase behaviour via the forms_draft agent (human approved).
API: `POST /iht/recompute`, `GET /iht/assessment`, `GET /iht/schedules`.

### Module 10: Knowledge library and ingestion
Pulls HMRC forms, form notes and gov.uk guidance into the tool: readable in-app, version-stamped, searchable, and the base for cited plain-English Q&A. Pipeline: source registry, fetch (Open Government Licence, raw stored in object storage), extract text, chunk, embed, store in Postgres + pgvector. Seed sources: IHT400 and notes; schedules IHT402, IHT403, IHT405, IHT406, IHT407, IHT411, IHT412, IHT435, IHT436; RNRB and transfer guidance; RNRB downsizing; excepted-estate and probate valuation; paying IHT (deadlines, reference, Direct Payment Scheme, instalments); Tell Us Once; The Gazette Section 27; IHT30 clearance; IHT35/IHT38 loss relief; administration-period income tax and CGT (60-day rule); deeds of variation (IOV2); probate fees.
Key behaviours: hybrid retrieval (Postgres full text plus pgvector cosine, reranked) always citing the source item and fetch date; Q&A answers only from the cached corpus and refuses advice beyond the source; scheduled and on-demand refresh with hash-diff "source changed" flags so tax constants and process steps stay current; cached copies readable even if gov.uk is unavailable, with clear attribution and no implication of HMRC endorsement.
API: `GET /knowledge/search`, `GET /knowledge/docs/{id}`, `POST /knowledge/ingest` (admin), `POST /knowledge/qa`.

### Module 11: Documents vault
Secure storage for the estate's own documents (death certificate, will, grant, valuations, statements, correspondence, completed forms, receipts, notices), linked to the records they belong to. Encrypted at rest, versioned, role-restricted, access logged, soft delete only.
Key behaviours: any record can show its attached documents; the viewer sees only permitted files.
API: `GET/POST/PATCH /documents`.

### Module 12: Dashboard
The at-a-glance home screen, balanced across the whole administration, not just tax: open tasks by owner with overdue and due-soon plus the next critical-path step; money in and out (debtors outstanding, creditors to settle, costs to date, reimbursements owed); estate position (gross, liabilities, net, provisional beneficiary entitlements, ECharts); outstanding notifications; deadline countdowns; tax status (estimated IHT, headroom to the threshold, the IHT400-required flag shown prominently); data completeness (confirmed versus estimated values); re-evaluation alerts.
API: `GET /estate/summary`.

### Module 13: Audit, activity and search
Immutable audit log (who created, changed, viewed or approved what, and when); an activity feed of recent changes; global search across tasks, assets, contacts, costs, documents and knowledge with type filters; an approvals register of every draft approved before it was treated as final; and the notifications service (cost recorded, asset added, approval needed, deadline due), in-app and optional email, never to the viewer.
API: `GET /audit`, `GET /activity`, `GET /search`, `GET /notifications`, `POST /approvals`.

### Module 14: Reliefs and reclaims tracker
Watches for falls in value and other reliefs so overpaid tax can be reclaimed; real money is lost if no one tracks the windows. Covers IHT35 (qualifying quoted shares or unit trusts sold within 12 months of death at an overall loss, all such sales netted), IHT38 (land or buildings sold within 4 years of death below probate value), the RNRB downsizing addition (a qualifying home sold, given away or downsized since 8 July 2015 with descendants inheriting), and a business/agricultural relief flag if any such asset appears (noting the April 2026 cap of 100% relief at 1m combined).
Key behaviours: marking a property sold below probate value within 4 years raises an IHT38 opportunity with its deadline and an estimated reclaim; both loss reliefs yield cash back only if IHT was actually paid, otherwise they reduce the value used on the account.
API: `GET/POST/PATCH /reliefs`.

### Module 15: Administration-period tax tracker
Income tax and CGT arising while the estate is administered, with the reporting route and hard deadlines. Rules: income under 500 in a tax year, nothing to report; informal route if the estate was under 2.5m, total income and CGT tax under 10,000 and asset sales under 500,000 in any one tax year, otherwise the estate is complex and registers for the Trust and Estate route; gains above probate value use the estate's own annual exempt amount for the year of death and the two following years; a residential-property gain must be reported and paid within 60 days of completion (hard deadline, auto-creates a task); ISAs stay tax-free until the estate closes or 3 years from death (asset flag so the exemption is not lost).
API: `GET/POST/PATCH /admin-tax`.

### Module 16: Asset tracing and completeness
Confidence that nothing has been missed, using free official services rather than paid reclaim firms: My Lost Account (lost bank, building society and NS&I accounts), the Pension Tracing Service, the Unclaimed Assets Register (life policies and pensions), and a document sweep (post, email, statements, tax records, safe deposit box, subscriptions, loyalty schemes, digital wallets).
Key behaviours: each service becomes a task with the service as a contact; a tracing step in the timeline with a completeness indicator; an explicit warning never to pay a reclaim firm because these searches are free.
Surface: rendered through tasks, contacts and the timeline (no dedicated entity).

### Module 17: Digital assets, subscriptions and memberships
Captures the non-financial digital life and the recurring payments to stop, from a library card to a photo library: email, cloud photos, social media, subscriptions, memberships, loyalty schemes, domains, digital wallets. Each item carries whether the login is known, an action (cancel, memorialise, transfer, close, download) and a status.
Key behaviours: recurring costs surface for cancellation and feed the cost module; links to contact and cost records.
API: `GET/POST/PATCH /digital-items`.

### Module 18: Veteran and service benefits
Where the deceased served in the armed forces, specific notifications and support routes are checked (the v1 checklist ships RAF routes; other services follow the same pattern): Armed Forces Pension Scheme notification if a service pension was held (payments stop, arrears or a short continuation may apply), RAF Benevolent Fund and RAF Association for bereavement support, Royal British Legion and SSAFA for possible funeral-cost help, and War Pension or Armed Forces Compensation only if an award was in payment.
Key behaviours: rendered as contacts and tasks so the checklist is worked and logged, not just read.
Surface: seeded contacts and tasks (no dedicated entity).

### Module 19: Executor protection and decisions
Protects the executors and records the decisions they make, which matters when beneficiaries take different forms of legacy. Covers the Section 27 notice (Module 3), optional missing-beneficiary and estate indemnity insurance (recorded if taken), an attributable and immutable decision log, the executor's year (beneficiaries cannot compel distribution within 12 months of death, noted against distribution), the deed-of-variation window (2 years from death, deadline tracked), and record retention (about 12 years, then purge).
Surface: decision log entries, deadlines, tasks and cost records.

## 2. Re-evaluation logic (spec section 20)

On adding or changing any asset, liability or estate setting, the tool:

1. **Recomputes immediately:** net estate, beneficiary shares and the IHT assessment (`POST /iht/recompute` fires automatically).
2. **Re-derives what is required:** which schedules apply, whether a full IHT400 is now needed, and which tasks and contacts follow (a new property spawns valuation, insurance and council-tax tasks; a new account spawns a notify-and-get-balance task and a contact). Reliefs and deadlines refresh.
3. **Raises a re-evaluation alert on a material change.** Material is configurable, defaults:
   - crossing the tax threshold (NRB line) either way,
   - crossing the 2,000,000 taper threshold,
   - a change of excepted-estate status,
   - the home value crossing the RNRB cap,
   - any single change above a set amount (default 10,000).
4. **Snapshots every recompute** (`iht_assessment`), so the executors can see how the position and the requirements changed and why.

## 3. API surface (build contract section 8)

Standard CRUD routers: assets, liabilities, debtors, creditors, contacts, contact-interactions, tasks, costs, beneficiary-legacies, distributions, documents, process-steps, deadlines, reliefs, admin-tax, digital-items. Plus:

| Endpoint | Purpose |
|---|---|
| `GET /me` | role resolved from Cloudflare Access |
| `GET /estate/summary` | dashboard aggregates |
| `GET /estate/accounts` | trial balance |
| `POST /iht/recompute`, `GET /iht/assessment`, `GET /iht/schedules` | IHT workbench |
| `GET /knowledge/search`, `GET /knowledge/docs/{id}`, `POST /knowledge/ingest` (admin), `POST /knowledge/qa` | knowledge library |
| `POST /agents/draft-form`, `POST /agents/draft-letter`, `POST /agents/suggest-tasks` | each returns a **draft**; `POST /approvals` accepts it |
| `GET /notifications`, `GET /audit`, `GET /activity`, `GET /search` | cross-cutting |

Every write emits an `audit_event` and, where relevant, a `notification` to the other executors.

## 4. Build order and definition of done (build contract sections 5 and 11)

MVP = the whole thing. Phasing is for build order and speed, not scope cut.

| Phase | Contents | Exit test |
|---|---|---|
| **P0 skeleton** | Repo, docker-compose, FastAPI + React scaffold, Postgres + pgvector, CF Access shim, models + Alembic, seed loader. `iht_engine` + tests green. | `test_iht_engine.py` table passes (constants NRB 325,000, RNRB 175,000, taper 2,000,000); app boots end to end. |
| **P1 core registers + money** | Assets, liabilities, debtors, creditors, contacts + notification tracker, tasks + dependencies, costs + alerts + by-type view, estate accounts + beneficiary shares, dashboard, documents, timeline + section 25 checklist seeded, deadlines engine, re-evaluation. | **Usable at end of P1**: add assets, see the position, know what HMRC requires. `estate_accounts.is_balanced` always reconciles. |
| **P2 tax depth + knowledge** | IHT workbench UI, schedule checklist, reliefs tracker, admin-tax tracker, tracing, digital assets, veteran and executor modules, knowledge ingest + viewer + Q&A. | Cited Q&A over the cached corpus; reliefs and 60-day CGT tasks auto-raise. |
| **P3 automation + polish** | forms_draft (IHT400/schedule PDFs), draft notification letters, estate-accounts and clearance PDF export, audit hardening, backups, accessibility pass (WCAG 2.2 AA), Railway deploy + Cloudflare Access. | Guardrail tests green (no send/file/pay tool reachable; every draft creates an approval-pending record); deployed. |

**Definition of done (whole build):** all modules 1 to 19, the section 20 re-evaluation logic, and the section 25 after-death checklist seeded as tasks; registers, contacts CRM with notification tracker, tasks with dependencies, cost tracking with co-executor alerts and costs-by-type view, estate accounts with live beneficiary shares, IHT workbench with the deterministic engine and route determination, knowledge library (ingest + viewer + cited Q&A), draft IHT400/schedule and notification-letter generation (human approved), process timeline, deadlines engine, reliefs and admin-tax trackers, asset tracing, digital assets, veteran checklist, executor protection, dashboard, audit and notifications, RBAC via Cloudflare Access. Deploys to Railway.

**Engine test vectors** (synthetic, from the build contract; they lock behaviour, they do not state anyone's tax):

| net_value | tnrb_pct | trnrb_pct | residence_to_descendants | expected allowance | expected tax |
|---|---|---|---|---|---|
| 960,000 | 1.0 | 1.0 | 340,000 | 990,000 | 0 |
| 1,000,000 | 1.0 | 1.0 | 380,000 | 1,000,000 | 0 |
| 1,020,000 | 1.0 | 1.0 | 400,000 | 1,000,000 | 8,000 |
| 1,060,000 | 1.0 | 1.0 | 340,000 | 990,000 | 28,000 |
| 960,000 | 0.5 | 0.5 | 340,000 | 750,000 | 84,000 |

Also asserted: any estate with `claims_rnrb=True` returns `must_file_iht400=True` (the critical rule); taper reduces RNRB above 2m; the 36% rate triggers at charity share >= 10%.

## 5. Changes since version 1.0 (as built, 2026-07-09)

Feature-level deltas landed after the v1.0 design pass; behaviours above stand unless amended here.

- **Knowledge ingest follows multi-page guides.** gov.uk splits guides (for example paying inheritance tax) across part pages; ingest fetches the landing page plus every same-guide part page, storing one document with the combined text. A `force` flag on `POST /knowledge/ingest` (and the `python -m app.cli_ingest --force` CLI) re-ingests sources whose content hash is unchanged. `scripts/fetch-knowledge.sh` wraps the CLI for one-command corpus loading (auto-detects compose versus local venv). The source registry spans 12 domains: 26 gov.uk entries plus The Gazette, NHS England, nidirect and bereavement references (Age UK, Marie Curie, Citizens Advice, Death Notification Service, Life Ledger), each entry recording its own licence; LITRG and MoneyHelper block automated fetching and are marked visit-manually.
- **Q&A retrieval degrades gracefully.** When embeddings are unavailable (no `EMBEDDING_MODEL`), retrieval falls back to reciprocal rank fusion over per-term full-text lists rather than a single ORed `ts_rank`, so a chunk matching a rare term outranks one that merely repeats common terms. With embeddings, full text and pgvector cosine results are merged with the same rank fusion.
- **Assistant model.** The Q&A and drafting graphs run on Claude Sonnet 5 (`claude-sonnet-5`); the deterministic engine remains model-free.
- **Dev sign-in screen.** When a development build cannot identify the user (`GET /me` returns 401/403 under `DEV_AUTH=true`), the frontend shows a sign-in card that stores the chosen email for the `X-Dev-User` shim. Never rendered in production, where identity arrives from Cloudflare Access before the app loads.
- **Dashboard timeline progress card.** A labelled progress bar (deliberately not a chart) shows how far through the administration the estate is and names the current step, from `GET /process/timeline`.
- **Tasks status chart.** A small ECharts donut of open work by status on the Tasks page (SVG renderer, fixed-order validated palette, with a visually hidden data table for screen readers).
- **PDF exports (Module 6/9/13 surfaces).** `POST /exports/*` renders the estate accounts, an IHT draft content sheet, an IHT30 clearance application draft, and approved notification letters to PDF; each export creates a document row and an audit event. Draft PDFs are marked as drafts; figures come from the registers and the engine only.
- **UK GDPR endpoints.** `GET /estate/export` (open-format JSON of every estate-scoped table) and `POST /estate/erase` (admin-only, confirmed, the one hard delete). Detail in ARCHITECTURE.md section 3.
