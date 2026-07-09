# PROCESSES.md

**Project:** AD Assistant | **Version:** 1.0 | **Date:** 2026-07-06 | **Status:** Canonical design master
**Source of truth:** requirements spec v0.4 (modules 7, 8, 10, 13; sections 20, 25); build contract sections 8 to 10; technical thesis section 4

> Public document. No personal data. Deadlines are given as derivation formulas, never as resolved dates for a real estate.

---

## 1. Estate administration process timeline (England and Wales)

The ordered process the tool carries, death certificate to clearance. Each step links to its tasks, contacts, costs and guidance, and derives its status from its tasks. The section 25 master checklist (cross-checked against gov.uk, Age UK, Marie Curie, Citizens Advice and MoneyHelper) seeds the task list against these steps, so the list is worked, not just read.

| # | Step | Notes and derived deadlines |
|---|---|---|
| 1 | Confirm the death | Verification by a healthcare professional; medical examiner scrutiny and the MCCD; if referred to the coroner, await the interim certificate (an inquest can delay registration). |
| 2 | Register the death | Within 5 days; order several certified copies; give the green form to the funeral director. |
| 3 | Arrange the funeral | Check for a prepaid plan and recorded wishes; DWP Funeral Expenses Payment only if a person on a qualifying benefit is paying. |
| 4 | Secure property and belongings | Care for pets; insure the empty home and tell the insurer it is unoccupied (high-risk step, auto-creates tasks); claim the Council Tax Class F exemption. |
| 5 | Tell Us Once | Within 28 days of the reference number (DWP, HMRC, Passport Office, DVLA, council, public-sector pensions, Veterans UK); then notify the organisations it does not cover via the contacts module. |
| 6 | Locate the will and codicils | Confirm the executors. |
| 7 | Value the estate | Assets, liabilities, date-of-death balances, RICS property valuation. |
| 8 | Assess IHT | Deterministic engine; determine full IHT400 versus excepted route. |
| 9 | Open an executors' bank account | |
| 10 | Complete IHT400 and schedules | Arrange payment (Direct Payment Scheme or instalments). IHT payment due by the end of the 6th month after death; IHT400 due within 12 months of the end of the month of death. |
| 11 | Submit IHT400; wait for the HMRC code | About 20 working days. |
| 12 | Apply for probate; receive the grant | Online application; probate fee tracked in costs. |
| 13 | Collect assets | Close accounts; sell or transfer the property. |
| 14 | Place the Section 27 creditor notice | The Gazette plus a local paper; claims window = placement + 2 months; settle debts and creditors. |
| 15 | Finalise income tax and CGT to date | Administration-period tax module; 60-day rule on residential gains. |
| 16 | Prepare estate accounts; interim distributions | Guarded by `safe_to_distribute`. |
| 17 | Wait out the claims window; final distribution | 6 months from the grant (Inheritance (Provision for Family and Dependants) Act claims); executor's year noted. |
| 18 | Apply for the IHT30 clearance certificate; retain records | Retention around 12 years, then purge. |

Running alongside: bereavement support (Cruse Bereavement Support, Age UK, Marie Curie, Sue Ryder, the GP) and benefit checks.

### Statutory deadline derivations (`domain/deadlines.py`)

| Deadline | Derivation |
|---|---|
| Pay any IHT | end of the 6th month after death |
| Deliver IHT400 | within 12 months of the end of the month of death |
| Tell Us Once | 28 days from the registration reference number |
| Creditor-notice window | placement + 2 months |
| Claims window | 6 months from the grant |
| CGT on a residential-property sale | report and pay within 60 days of completion |
| Deed of variation | within 2 years of death |
| Share loss relief (IHT35) | sale within 12 months of death |
| Land loss relief (IHT38) | sale within 4 years of death |

Reminders are configurable per deadline and per task. Late-payment interest on IHT is noted against the payment date; the rate is a provenance-tracked constant, never hard-coded without source and date.

## 2. Draft to human approval flow

The single most important operational rule: **nothing agent-produced is final, filed or sent without a person approving it, and nothing is ever filed or sent by code.**

```
Agent drafts (form, letter, narration, task suggestions)
   -> stored as DRAFT with sources cited
   -> approval-pending record created (approval table)  [enforced by guardrail test]
   -> notification raised to executors ("approval needed")
   -> executor reviews in the UI: sees the draft, its sources, and any listed gaps
   -> approve (POST /approvals) or edit and re-draft
   -> marked FINAL, audit_event recorded (who approved, when)
   -> a HUMAN submits to HMRC / posts the letter / makes the payment, outside the system
```

An optional professional-review checkpoint sits on the IHT output, on by default, given how close a near-threshold estate can sit to the line.

## 3. Re-evaluation trigger flow (spec section 20)

```
Write to asset / liability / estate settings
   -> POST /iht/recompute fires automatically
   -> net estate, beneficiary shares, IHT assessment recomputed (deterministic engine)
   -> requirements re-derived: schedules, IHT400-vs-excepted route, spawned tasks
      and contacts (new property -> valuation, insurance, council-tax tasks;
      new account -> notify-and-get-balance task + contact)
   -> reliefs and deadlines refreshed
   -> material-change check (configurable):
        crossed the NRB line either way?
        crossed the 2,000,000 taper threshold?
        excepted-estate status changed?
        home value crossed the RNRB cap?
        single change above the default 10,000?
   -> if material: re-evaluation alert to executors (dashboard + notification)
   -> snapshot written to iht_assessment (inputs, allowances, taxable, tax,
      route, required schedules, constants_version)
```

Snapshots make the position auditable over time: the executors can always see how the requirements changed and why.

## 4. Knowledge ingestion pipeline

```
source registry (seed list in FEATURES.md Module 10)
   -> fetch          public gov.uk pages and published PDFs; Open Government
                     Licence, attributed; raw stored in object storage
   -> extract text   for the in-app viewer and retrieval
   -> chunk
   -> embed          EMBEDDING_MODEL; vectors into pgvector
   -> store          knowledge_doc (source_url, title, form_code, topic,
                     jurisdiction, fetch_date, content_hash, version, licence)
                     + knowledge_chunk rows

refresh (scheduled + on demand)
   -> re-fetch -> hash diff against stored content_hash
   -> on change: bump version, raise "source changed" flag
      so tax constants and process steps get reviewed and stay current

retrieve
   -> query -> Postgres full text (tsvector) + pgvector cosine similarity
   -> rerank -> answer with citation (source item + fetch date, always)
```

Rules: Q&A answers only from the cached corpus and refuses advice beyond the source; cached copies remain readable in-app even if gov.uk is unavailable, with clear attribution and no implication of HMRC endorsement.

## 5. Notification flow to co-executors

```
Trigger events: cost recorded or edited, asset added, approval needed,
                deadline due or overdue, re-evaluation alert, source changed
   -> app/services/notifications.py creates a notification row per recipient
   -> recipients: the OTHER executors and admin (never the actor's own echo
      unless configured; NEVER the viewer role)
   -> delivery: in-app (GET /notifications, read_at tracking)
                + optional email if enabled
   -> cost alerts have a configurable threshold: default every cost,
      option to alert only above a set amount
```

Acceptance shape: when executor A records a cost, executor B is notified and the costs-by-type view and running total update. The viewer is never notified and cannot see cost-entry controls.

## 6. Audit trail

- **Immutable audit log:** every create, change, view and approval writes an `audit_event` (actor, action, entity, before, after, timestamp). Emitted by the API layer on every write; agent actions are audit-logged too.
- **Approvals register:** every draft that was approved, by whom and when, before it was treated as final, filed or sent.
- **Activity feed:** recent changes across the estate, for the executors to follow day to day.
- **Soft delete only:** archiving with a reason is the only removal, so nothing is ever lost from the record.
- **Attribution:** every change is tied to the verified Cloudflare Access identity (or the dev-shim user in development).

## 7. Operational hygiene

- Daily backups of database and documents, with a tested restore.
- Migrations via Alembic; schema changes require backup first.
- Full estate export and deletion supported (UK GDPR posture for living beneficiaries' data).
- Record retention around 12 years post-administration, then purge.
