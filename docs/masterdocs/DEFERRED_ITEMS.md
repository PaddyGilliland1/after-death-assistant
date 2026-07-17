# DEFERRED_ITEMS.md

**Project:** AD Assistant | **Version:** 1.0 | **Date:** 2026-07-06 | **Status:** Running log (append, do not delete rows)
**Source of truth:** requirements spec v0.4 section 24 (assumptions, out of scope); distillation findings from the master-doc pass

> Public document. No personal data. Estate-specific assumptions are stated generically; the real particulars live in the permanently private data overlay repo.

---

## 1. Out of scope (v1, from spec section 24)

| Item | Note |
|---|---|
| Automated filing to HMRC or the probate service; automated sending of any message | Always human-submitted. This is a guardrail, not a backlog item; it does not get "un-deferred". |
| Financial or legal advice | The tool informs and drafts only. Positioning is explicit in the README. |
| Jurisdictions other than England and Wales | Design leaves room to extend via `domain/jurisdiction/`; Scotland, Northern Ireland and other regimes are contributor territory. |
| Will drafting and trust administration | |
| Bank and HMRC API integrations (Open Banking, HMRC APIs) | Manual entry with provenance for v1. |

## 2. Assumptions to confirm (spec section 24, stated generically)

These drive real figures and must be confirmed against documents before the numbers are relied on. Each maps to a seeded verification task.

| # | Assumption | Why it matters | Confidence |
|---|---|---|---|
| A1 | The late spouse left everything to the deceased, so both the NRB and RNRB transfer at 100% | A large slice of the total allowance; if the transfer percentage is lower, tax may be due | Medium |
| A2 | The residue splits equally between the residuary beneficiaries | Drives the live beneficiary shares in the estate accounts | Medium |
| A3 | The small equal-value gifts are legacies in the will, not recent lifetime gifts | Affects the 7-year add-back; small either way, but must be classified | Medium |
| A4 | Unquoted club shareholdings pass to the clubs; the clubs' charitable or CASC status is unknown | Exemption treatment and the 36% charity-rate test | Low |
| A5 | No pension pots with death benefits exist | Currently outside the estate; note the announced April 2027 change bringing unused pensions into IHT | Low |
| A6 | The residence passes wholly to direct descendants | Required for the RNRB claim | High |
| A7 | The late spouse's will did not create a nil-rate-band discretionary trust | Such a trust could reduce or remove the transferred allowances. Verify the will and the IHT402 percentage. **Highest-value check in the project.** | Medium |
| A8 | The deceased did not sell or downsize a home, or move into care, after 8 July 2015 | If they did, an RNRB downsizing addition may be claimable | Low |
| A9 | No quoted shareholdings are likely to be sold at a loss within 12 months | IHT35 loss relief could otherwise reclaim overpaid tax | Low |
| A10 | Whether a service pension was in payment is unconfirmed | Drives the veteran-module notifications, arrears and cessation | Low |

## 3. Open questions and spec ambiguities (from the master-doc distillation)

| # | Item | Detail | Suggested resolution |
|---|---|---|---|
| Q1 | Role name mismatch | Thesis section 2 maps emails to "executor, contributor, viewer"; requirements section 2 and the build contract define admin, executor, viewer. No "contributor" appears anywhere else. | Use admin / executor / viewer (contract wins). |
| Q2 | Repo name mismatch | Build contract section 4 roots the repository tree at a legacy name derived from the first estate instance; the actual code repo is `ad-assistant` with the private `AD-estate` overlay. | Follow the two-repo pattern in project CLAUDE.md; treat the contract's root name as historical. |
| Q3 | Timeline step count | Spec section 3 says a "16-step" timeline; Module 7 lists 18 steps. | Build the 18 listed steps; the count in the summary row is stale. |
| Q4 | `is_excepted()` rules unspecified | The engine calls `is_excepted(estate, constants)` but neither document enumerates the excepted-estate tests (gross value limits, exempt-estate limit, foreign assets, trusts, gifts). Only the RNRB-forces-IHT400 rule is explicit. | Encode the full excepted-estate rules in `domain/jurisdiction/` from the cached gov.uk guidance, with provenance; flag as a P0/P1 design task. |
| Q5 | Taper input definition | The pseudocode tapers RNRB on `net_value`. HMRC tapers on the estate value before reliefs and exemptions, which can differ from the net-estate-for-probate figure the accounts produce. Which "net value" feeds the taper needs pinning down. | Define both values explicitly in the engine's input schema; document the choice with a source. |
| Q6 | Charity 36% rate simplification | `rate = 0.36 if charity_share >= 0.10` is a simplification of the statutory baseline-amount test (10% of the "baseline amount", a defined component figure, not of the whole estate). | Acceptable for v1 given no charity share is currently expected; record the simplification in the engine docstring and here. |
| Q7 | Two sources of RNRB input | `estate.residence_to_descendants_value` is a stored field, while assets carry `rnrb_qualifying` flags. The reconciliation (derive the estate field from flagged assets, or manual override) is unspecified. | Derive from flagged assets with a manual-override field; re-evaluation must recompute it. |
| Q8 | Lifetime gifts have no entity | IHT403 is in the knowledge seed list and the engine takes `exempt_transfers`, but the data model has no lifetime-gift table; `beneficiary_legacy` models will legacies only. The 7-year add-back and gift exemptions have nowhere structured to live. | Either extend `beneficiary_legacy` with a lifetime-gift kind or add a small `gift` entity; needed before IHT403 drafting. |
| Q9 | `charity_share_pct` duplication | Stored on `estate` but derivable from exempt legacies. Risk of drift. | Treat the stored field as a manual override with the derived value shown; or compute-only. |
| Q10 | No user table | `notification.user_id` and task `assignees[]` reference users, but the model defines no user entity (identity comes from Cloudflare Access emails). | Add a minimal `app_user` (email, role, display name) or store emails directly; decide at P0 modelling time. |
| Q11 | Executor-private flag not in the contract model | Spec section 2 allows flagging individual records executor-private (hidden from the viewer); the contract's table list only gives `document.access_roles`. | Add a nullable `visibility` or `executor_private` column on business tables, or handle via the link table; decide at P0. |
| Q12 | Relief enum naming drift | Contract: `iht35/iht38/rnrb_downsizing/bpr_apr`; spec Module 14: `iht35_share_loss/iht38_land_loss/rnrb_downsizing/bpr_apr_flag`. | Standardise on the contract's shorter names. |
| Q13 | RNRB downsizing input missing from the engine | Module 14 says the engine "takes a downsizing input", but the pseudocode signature has none. | Add an explicit optional downsizing-addition input to the engine schema when the relief module lands (P2). |
| Q14 | Fast-follow vs all-in-MVP framing | Spec section 3 marks Q&A, auto-filled PDFs and letters as "fast-follow"; the contract says MVP is everything, phased P0 to P3 for order only. | Contract wins: all in scope, order per P0 to P3. |
| Q15 | Volatile constants need provenance plumbing | Probate fee (rise scheduled mid-July 2026, subject to approval), IHT late-payment interest rate, the informal-route thresholds, the April 2026 BPR/APR cap and the April 2027 pension change are all date-sensitive. | All must come from the versioned knowledge library with change flags; never hard-code without source and fetch date. |
| Q16 | Thesis knowledge seed list is a subset | The thesis omits IHT411/IHT412 and the loss-relief, admin-tax, deeds-of-variation and probate-fee sources that the contract section 10 includes. | Contract section 10 is the seed registry. |
| Q17 | Notification letters have no template inventory | `POST /agents/draft-letter` exists, but no document lists which letter templates (bank notification, registrar, insurer, and so on) ship. | Derive the template set from the contact categories and section 25 checklist during P3; log the chosen set here. |
| Q18 | ADO project not yet created | Work-item tracking for this repo is pending; commits use the pending convention until the project exists. | Create the ADO project before P0 build starts. |

## 4. Deferred beyond v1 (candidate roadmap, non-committal)

| Item | Source |
|---|---|
| Multi-estate support (the schema scopes by `estate_id` already; UI and onboarding do not) | Implied by open-source strategy |
| Swappable vector store (Weaviate/Qdrant) behind the retrieval interface for large deployments | Thesis section 6 |
| Additional jurisdiction modules (Scotland, Northern Ireland) | Thesis section 10 |
| AGPL relicensing question if hosted forks should stay open | Thesis section 10 (MIT chosen in the contract; decision recorded) |

## 5. Running log

Append new rows as items are deferred, decided or closed. Do not delete rows; strike state changes by updating Status.

| Date | Item | Source | Status |
|---|---|---|---|
| 2026-07-06 | Master doc set created; sections 1 to 4 above seeded from spec v0.4, thesis v0.2 and the build contract | masterdocs pass | Open |
| 2026-07-06 | Q1 to Q18 logged as open questions for the validation report | masterdocs pass | Open |
| 2026-07-06 | A1 to A10 to be seeded as verification tasks at P1 | spec section 24 | Open |
| 2026-07-06 | lifetime_gift table missing; seed gifts are skipped with a logged warning and cannot inform the engine's exempt_transfers | P1 seeding agent | Open |
| 2026-07-06 | exempt_transfers hardcoded 0 in IHT input assembly; should derive from beneficiary_legacy exempt_or_chargeable and lifetime gifts | P1 money agent | Open |
| 2026-07-06 | realisation_gains left 0 in accounts assembly pending a derivation rule (current_or_realised_value vs dod_value on realised assets) | P1 money agent | Open |
| 2026-07-06 | asset.category free text mapped to engine AssetCategory in service; consider enum or dedicated column migration | P1 money agent | Open |
| 2026-07-06 | estate.trust_count absent; settled property treated conservatively (never excepted while trust structure unknown) | P1 money agent | Open |
| 2026-07-06 | creditor_notice.safe_to_distribute stored flag can go stale after a deadline passes; the live guard endpoint is the authority | P1 registers agent | Open |
| 2026-07-06 | Suggested indexes: contact (notify_required, notification_status), notification (user_id, read_at), cost (estate_id, category) | P1 people agent | Open |
| 2026-07-06 | Document download cannot carry the X-Dev-User header in dev; fine in prod (CF Access cookies) | P1 frontend agent | Open |
| 2026-07-06 | Frontend: shared register-section and useEstate deserve promotion to components/shared; EntityForm post-submit reset; ui/dialog forwardRef warning | P1 frontend agents | Open |
| 2026-07-06 | Cloudflare Access JWT validation (Cf-Access-Jwt-Assertion vs CF_ACCESS_AUD) not yet implemented in core/auth.py; header trusted as CF-set; mitigation documented in DEPLOY.md section 4 | P3 hardening agent | Open |
| 2026-07-06 | forms_draft field refs are semantic (IHT400.net_value), not HMRC box numbers; official PDF template filling is a follow-on | P3 agents agent | Open |
| 2026-07-06 | Agent graphs use per-request MemorySaver; approval completes via endpoint rather than literal thread resumption; persistent checkpointer would enable resume | P3 agents agent | Open |
| 2026-07-06 | POST /knowledge/ingest commits changed doc versions immediately; routing through the knowledge_ingest graph would add the approval gate | P3 agents agent | Open |
| 2026-07-06 | relief.window_basis returned as derived field; consider a model column; IHT35/38 window derivations should migrate from schemas/trackers.py into the domain module | P2 trackers agent | Open |
| 2026-07-17 | POST /knowledge/qa (one-shot) retained for API compatibility; the UI now uses the conversational /knowledge/chat with native citations. Consider deprecation once external users confirm no dependence | knowledge chat rebuild | Open |
| 2026-07-17 | ChatSource lacks form_code (old QASource had it); chat sources cannot show the form badge | chat frontend agent | Open |
