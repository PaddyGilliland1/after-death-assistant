# Build Contract Validation Report

**Scope:** validation of the build contract (`claude-code-build-prompt.md`) against the Requirements Specification v0.4 (Modules 1 to 19 and sections 20 to 25) and the Technical Thesis v0.2.
**Date:** 6 July 2026.
**Method:** full read of all three documents, line-by-line cross-check of the contract's guardrails, data model (section 6), IHT engine (section 7), API surface (section 8), agents (section 9), knowledge sources (section 10) and build order (section 11) against the specification, plus independent recomputation of every numeric test case.

This report contains no personal data. It references documents and section numbers only.

---

## 1. IHT logic verification: contract section 7 against spec section 21

### 1.1 Constants

| Constant | Contract section 7 | Spec section 21 | Verdict |
|---|---|---|---|
| NRB | 325,000 | 325,000 | Match |
| RNRB | 175,000 | 175,000 | Match |
| Taper threshold | 2,000,000 | 2m taper (IHT-1) | Match |
| Standard rate | 40 per cent | 40 per cent implied by worked figures | Match |
| Reduced charity rate | 36 per cent at charity_share >= 0.10 | 36 per cent if 10 per cent or more passes to charity (IHT-2) | Match |

### 1.2 Formula checks

- **Taper:** `rnrb_max = max(rnrb_max - (net_value - TAPER_THRESHOLD) / 2, 0)`. One pound of RNRB lost for every two pounds over 2m, floored at zero. Matches IHT-1 and the thesis pseudocode. Verified: at net 2.1m with full transfer, rnrb_max reduces from 350,000 to 300,000. Correct.
- **RNRB cap:** `rnrb = min(rnrb_max, residence_to_descendants_value)`. Matches IHT-1 ("capped at the home value passing to descendants"). Correct.
- **Charity rate:** rate switches to 0.36 at a charity share of 10 per cent or more. Matches IHT-2. Note: the statutory test is 10 per cent of the "baseline amount" (a defined component of the estate), not a simple share of net value. The contract mirrors the spec's simplification, so there is no contradiction, but the simplification should be documented in the engine and revisited if a charity legacy ever becomes material. Advisory only.
- **Excepted-estate rule:** `must_file_iht400 = claims_rnrb or not is_excepted(estate, constants)`. Matches IHT-3 and the section 21 critical callout that any RNRB claim forces a full IHT400. The contract also mandates the test asserting `claims_rnrb=True` implies `must_file_iht400=True`. Correct and well guarded.
- **Taxable amount:** `taxable = max(net_value - exempt_transfers - allowance, 0)`. Algebraically identical to the thesis form (chargeable = net minus exempt transfers, then subtract allowance, floor at zero). Consistent.

### 1.3 Executable test cases (independently recomputed)

All five contract test cases were recomputed independently. All pass.

| net_value | tnrb | trnrb | residence | Expected allowance | Recomputed | Expected tax | Recomputed | Verdict |
|---|---|---|---|---|---|---|---|---|
| 960,000 | 1.0 | 1.0 | 340,000 | 990,000 | 990,000 | 0 | 0 | Pass |
| 1,000,000 | 1.0 | 1.0 | 380,000 | 1,000,000 | 1,000,000 | 0 | 0 | Pass |
| 1,020,000 | 1.0 | 1.0 | 400,000 | 1,000,000 | 1,000,000 | 8,000 | 8,000 | Pass |
| 1,060,000 | 1.0 | 1.0 | 340,000 | 990,000 | 990,000 | 28,000 | 28,000 | Pass |
| 960,000 | 0.5 | 0.5 | 340,000 | 750,000 | 750,000 | 84,000 | 84,000 | Pass |

The contract's test table also matches the thesis section 5 test table row for row. The spec Module 6 worked residue example (net estate less legacies and gifts, split between the residuary shares) was recomputed independently and reproduces the spec's stated figures exactly. The estate-accounts unit-test target in contract section 7 is consistent with it.

### 1.4 IHT logic findings

| Ref | Finding | Severity |
|---|---|---|
| IHT-A | `is_excepted(estate, constants)` is referenced but its criteria are defined nowhere in the contract, the spec or the thesis (gross value limits, exempt-estate limits, foreign and trust property conditions). The engine is built first in P0, so this must be pinned down, even if only as a conservative stub that returns False with a documented reason. | Must resolve |
| IHT-B | `claims_rnrb` is an engine input but is not a field on the `estate` table in section 6, and no derivation is stated (for example: true when any asset is `rnrb_qualifying` and `residence_to_descendants_value > 0`). Define the derivation before P0 tests are written. | Must resolve |
| IHT-C | The spec (Module 14 and the section 3 enrichment table) says "Module 14 and the IHT engine take a downsizing input" for the RNRB downsizing addition. The contract section 7 engine has no downsizing input; only the `relief` table carries `rnrb_downsizing`. Add a downsizing input (even if defaulted to zero) so the engine signature does not need a breaking change later. | Should resolve before P1 |
| IHT-D | Spec section 21 covers gifts within 7 years of death and taper relief on failed gifts. The engine has `exempt_transfers` but no chargeable-lifetime-transfer input. The spec itself calls this minor for the target estate, so acceptable, but record it as a documented engine limitation. | Advisory |
| IHT-E | Statutory nuances simplified consistently in both documents (charity baseline amount, taper measured on the estate before reliefs): document in the engine docstring with source citations. | Advisory |

**IHT verdict: the contract's engine logic, constants and all test arithmetic are correct and consistent with spec section 21. Two definitional gaps (IHT-A, IHT-B) must be closed because the engine is the first thing built.**

---

## 2. Data model: contract section 6 against spec section 23 entity appendix

Every entity in the spec appendix maps to a contract table:

| Spec section 23 entity | Contract section 6 table | Coverage |
|---|---|---|
| Estate | estate | Full, plus constants_version and charity_share_pct |
| Task | task (+ task_comment) | Full |
| Asset | asset (+ valuation_event for valuation history) | Full except `notes` (see DM-3) |
| Liability | liability | Full |
| Debtor | debtor | Full |
| Creditor | creditor (+ creditor_notice, notice_claim) | Full, Section 27 workflow included |
| Contact | contact (+ contact_interaction) | Full except `data_protection_note` (see DM-2) |
| Cost | cost | Full |
| Beneficiary / Legacy | beneficiary_legacy | Full |
| Distribution | distribution | Full |
| ProcessStep | process_step | Full |
| Deadline | deadline | Full |
| IHTAssessment | iht_assessment | Full (snapshot json plus constants_version) |
| KnowledgeDoc | knowledge_doc (+ knowledge_chunk) | Full |
| Document | document | Full |
| AuditEvent | audit_event | Full |

The contract adds relief, admin_tax, digital_item, notification, approval and a generic link table, all required by Modules 14, 15, 17, 13 and the approval flow. The generic link table satisfies the appendix's cross-linking requirement.

### Data model findings

| Ref | Finding | Severity |
|---|---|---|
| DM-1 | **Decision log missing.** Module 19 requires "each key decision with date, rationale and who agreed, attributable and immutable". The contract has a frontend `executor` module but no `decision` table and no API route. This is a named, core-phase spec requirement with no backing entity. | Must resolve |
| DM-2 | **Executor-private flag missing.** Spec section 2 says individual records can be flagged executor-private and hidden from the viewer, and the viewer sees everything "minus executor-private items". Only `document.access_roles` supports this. Add a shared `executor_private` boolean (or extend access_roles) across business tables, enforced server-side. This is an RBAC correctness issue, so it belongs in P1. | Must resolve |
| DM-3 | Minor field omissions: `contact.data_protection_note` (Module 4), free-text `notes` on asset, debtor and liability (spec module tables). Cheap to add now, disruptive later. | Should resolve |
| DM-4 | Cost category, asset status and other enums are named in the spec module tables but the contract lists only the field. Acceptable (the contract defers detail to the spec), but the builder must take the enums from the spec, not invent them. | Advisory |

---

## 3. Requirements coverage: Modules 1 to 19 and sections 20 to 25

Contract section 5 explicitly commits to all Modules 1 to 19, the section 20 re-evaluation logic and the section 25 checklist seed, and the build order (section 11) sequences all of it. Checked module by module, the following items in the spec are missed or only partially carried by the contract:

| Ref | Module / section | Gap | Severity |
|---|---|---|---|
| RQ-1 | Section 2 and section 22 (NFR) | **Estate export and full-estate deletion** ("Export and delete estate": admin yes, executor with confirmation; UK GDPR export and deletion; open-format export under Portability). No endpoint, table hook or phase mentions it. | Must resolve (can land in P3, but must be in the contract) |
| RQ-2 | Module 9, IHT-8 | **Professional-review checkpoint, on by default.** Also listed as a thesis risk mitigation for the near-threshold estate. Absent from the contract entirely. Small feature (a flag on the assessment plus a blocking banner), high protective value. | Should resolve before P1 |
| RQ-3 | Module 13 and thesis section 7 | **Audit of views.** Spec: "who created, changed, viewed or approved what". Contract section 8 only says "writes emit an audit_event". Read-access auditing of sensitive records (documents at minimum) is dropped. | Should resolve |
| RQ-4 | Module 5 | **Cost-alert threshold configuration** (default every cost, option only above a set amount). Contract carries the alert but not the configurable threshold. | Minor |
| RQ-5 | Module 4 | Rule "each interaction can set a follow-up that becomes a task" not stated in the contract (the field exists; the task-creation behaviour is not). Bulk notification services (Death Notification Service, Life Ledger, Settld) named in the spec as tracked routes are not mentioned; they arrive via the section 25 seed, so low risk. | Minor |
| RQ-6 | Module 1 | Views list (calendar, board, critical path) and task export not restated. Critical path is named twice in the spec. Treat the spec's views list as binding. | Minor |
| RQ-7 | Module 8 | Late-payment interest note against the IHT payment date not mentioned. | Minor |
| RQ-8 | Module 16 | Tracing completeness indicator not restated (contract has the tracing module; the indicator is spec acceptance). | Minor |
| RQ-9 | Section 22 | Encryption at rest for database and documents is a spec NFR and thesis commitment; the contract never states it (host-level defaults may cover the database, but document storage needs an explicit decision). Daily backups appear only as a P3 word ("backups"); the spec requires a tested restore. | Should resolve |
| RQ-10 | Module 19 | Executor's year (12-month no-compulsion note against distribution) and the 12-year record-retention-then-purge note are not carried. Both are notes or derived deadlines, cheap to include with DM-1. | Minor |

No contradictions of the spec were found: everywhere the contract states behaviour, it agrees with the spec. All gaps above are omissions, not conflicts.

---

## 4. Internal inconsistencies

| Ref | Where | Inconsistency | Severity |
|---|---|---|---|
| IC-1 | Contract sections 6 and 7 | `claims_rnrb` used by the engine but absent from the data model (see IHT-B). | Must resolve |
| IC-2 | Contract sections 6 and 8 | `creditor_notice` and `notice_claim` tables exist and `safe_to_distribute` guards Module 6 distributions, but the API surface lists no creditor-notice routes. The Section 27 workflow is unreachable as specified. | Must resolve |
| IC-3 | Contract sections 4, 5 and 8 | The frontend module list has no surface for Module 13 (audit, activity, global search, approvals register, notifications) even though the API exposes /audit, /activity, /search, /notifications and the definition of done includes "audit and notifications". Name the surface (a module or an agreed placement in dashboard/admin). | Should resolve |
| IC-4 | Contract section 8 | Re-evaluation fires on "any change to an asset, liability or the estate settings", but no estate-settings endpoint (GET/PUT /estate) is listed. | Should resolve |
| IC-5 | Contract section 7 | `estate_accounts.py` formula covers capital, administration and distribution but omits the Income account from the Module 6 four-account structure (income received less income expenses and tax, distributed with residue). The data exists (`asset.income_since_death`, `admin_tax`); the formula and `is_balanced` must include it or the trial balance will not reconcile once income arrives. | Must resolve |
| IC-6 | Thesis section 2 | Thesis API layer names roles "executor, contributor, viewer"; spec section 2 and the contract use admin, executor, viewer. The contract is right; the thesis is stale. | Doc fix |
| IC-7 | Thesis header and footer | Thesis v0.2 header says companion to Requirements Spec v0.3 in the meta, v0.1 in the subtitle and footer; the contract cites spec v0.4. Version references are stale in the thesis. | Doc fix |
| IC-8 | Spec HTML | The spec's HTML title tag still says v0.2 while the document is v0.4. | Doc fix |
| IC-9 | Naming drift | The engine input is `residence_to_descendants_value` (contract), `home_value_to_descendants` (thesis), "home value passing to descendants" (spec). Contract is internally consistent; adopt its name. | Doc fix |

---

## 5. Repository hygiene check

The contract, spec and thesis contain personal identifiers and estate specifics, and they sit in the project root as symlinks. Verified: `.gitignore` explicitly excludes `claude-code-build-prompt.md`, `requirements-spec.html`, `technical-thesis.html` and `seed/`. Correct as configured. Two cautions: the exclusions are by exact filename, so renamed or additional private documents would not be caught (consider a git-ignored `docs/private/` convention), and the two seed files delivered alongside this report were checked to contain generic process content and public source metadata only.

Excluded from the ingestion source registry deliverable: the Practical Law and STEP references in spec section 24. They are requirement provenance, not ingestable corpus (proprietary licences, no OGL). The nidirect and LITRG pages are included with their licence terms flagged.

---

## 6. Conclusion: GO / NO-GO

**Verdict: GO, conditional on the P0/P1 blockers below.** The contract is a faithful, internally coherent compression of the spec: every module is committed, the build order matches the thesis phasing, the guardrails match the spec principles, and every line of IHT arithmetic verifies exactly. The defects found are omissions and definitional gaps, not contradictions.

**Must resolve before or during P0 (engine is built first):**
1. Define `is_excepted` criteria or a documented conservative stub (IHT-A).
2. Define the `claims_rnrb` derivation and its home in the data model (IHT-B / IC-1).
3. Decide the RNRB downsizing input on the engine signature (IHT-C).

**Must resolve before P1 completes (P1 is declared "usable"):**
4. Add the Module 19 decision-log entity and routes (DM-1).
5. Add the executor-private flag with server-side enforcement (DM-2).
6. Add creditor-notice API routes so the Section 27 workflow and the distribution guard are reachable (IC-2).
7. Include the Income account in `estate_accounts.py` and the `is_balanced` identity (IC-5).

**Resolve by P3:** estate export and deletion (RQ-1), professional-review checkpoint default-on (RQ-2), view auditing for sensitive records (RQ-3), encryption-at-rest and tested-restore statements (RQ-9), Module 13 frontend surface (IC-3), estate-settings endpoint (IC-4).

Everything else listed is minor or documentation hygiene and does not gate the build.
