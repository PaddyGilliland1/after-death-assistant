# AGENT_DESIGN.md

**Project:** AD Assistant | **Version:** 1.0 | **Date:** 2026-07-06 | **Status:** Canonical design master
**Source of truth:** build contract section 9; technical thesis section 4; requirements spec v0.4 modules 9 and 10

> Public document. No personal data.

---

## 1. Design stance

Five focused LangGraph graphs, each with narrow tools and one hard rule: **produce a draft, request approval, never act externally.** Agents research, explain and draft. A person approves anything final, filed or sent. All agent code lives in `backend/app/agents/`; every agent action is audit-logged.

Two absolute rules sit above everything here:

1. **No LLM computes a figure.** The IHT and estate-accounts maths live in the pure, deterministic, unit-tested domain core (`domain/iht_engine.py`, `domain/estate_accounts.py`). Agents may explain figures; they may never produce them. `iht_narration` narrates the engine's `Assessment` object; it never calculates.
2. **No send, no file, no payment.** Tools are read and draft only. There is no tool in any graph's toolset that can dispatch email or letters, file with HMRC or the probate service, or move money. Humans do those things, outside the system, after approval.

## 2. The five graphs

### 2.1 knowledge_ingest
**Purpose:** keep the cached guidance corpus current. Fetches the registered gov.uk pages and published PDFs, stores them with source URL, fetch date and content hash, extracts text, chunks, embeds into pgvector.
**Trigger:** scheduled and on demand (`POST /knowledge/ingest`, admin only).
**Tools (read/draft only):** fetch registered source, store raw file to object storage, extract text, chunk, embed, upsert knowledge_doc and knowledge_chunk rows, hash-diff against the stored version.
**Change handling:** a hash difference bumps the version and raises a "source changed" flag so tax constants and process steps get human review.
**Human approval:** ingestion itself is mechanical and does not draft user-facing output, but constant changes surfaced by the change flag are applied only after human confirmation; the flag is the interrupt point.
**Provenance:** every stored item carries Open Government Licence attribution, source URL and fetch date.

### 2.2 iht_narration
**Purpose:** turn the deterministic engine's `Assessment` (allowances, taxable amount, tax, route, required schedules, inputs, constants version) into a plain-English, cited, line-by-line breakdown a person can check.
**Hard rule:** it **never computes figures**. Its only numeric inputs are fields of the `Assessment` snapshot produced by `iht_engine.assess()`. If a number is not in the snapshot, the narration cannot state it.
**Tools (read only):** read the current `iht_assessment` snapshot, read knowledge_doc citations for the rules it references (NRB, RNRB, taper, charity rate, IHT400-vs-excepted).
**Human approval interrupt:** the narration is stored as a draft with an approval-pending record; it is shown as a draft with sources until approved.

### 2.3 forms_draft
**Purpose:** map estate data to the IHT400 and the required schedules; produce a completed-form draft (fill a PDF template) for review; list any gaps (missing values, unconfirmed estimates).
**Trigger:** `POST /agents/draft-form`.
**Tools (read/draft only):** read registers and the current assessment, read the required-schedules checklist, fill PDF form templates, write the draft to the documents vault as `completed_form` (draft state), create the approval-pending record.
**Human approval interrupt:** explicit LangGraph interrupt before the draft is marked reviewable-final; a person approves before the PDF is treated as final, and a person submits it to HMRC. Figures on the form come from the registers and the engine, never from the model.

### 2.4 guidance_qa
**Purpose:** answer plain-English questions ("how do I complete box X") using **only** the cached official guidance corpus.
**Trigger:** `POST /knowledge/qa`.
**Tools (read only):** hybrid retrieval (Postgres full text + pgvector cosine, reranked) over knowledge_chunk; read knowledge_doc metadata for citation.
**Hard rules:** always cite the source item and its fetch date; refuse to advise beyond the source ("the cached guidance does not cover that" rather than improvising); no general-knowledge answers about tax law.
**Human approval:** answers are informational and cited, not drafts of outbound artefacts, so no approval record is required; the citation requirement and corpus restriction are the guardrails, and interactions are audit-logged.

### 2.5 next_actions
**Purpose:** propose tasks and dependencies from the process timeline and current estate state (for example: a new property suggests valuation, insurance and council-tax tasks; an approaching deadline suggests its preparation tasks).
**Trigger:** `POST /agents/suggest-tasks`.
**Tools (read/draft only):** read process steps, tasks, registers and deadlines; draft task suggestions with proposed dependencies, owners and dates.
**Human approval interrupt:** suggestions are drafts with an approval-pending record; they become real tasks (source = `agent_suggested`) only when an executor accepts them.

## 3. Approval interrupt placement

Approval gates are **explicit LangGraph interrupt nodes**, not conventions:

```
[gather context] -> [draft] -> [store draft + create approval-pending record]
        -> ||INTERRUPT: human review||
        -> approved? -> [mark final, audit_event]
        -> edited?   -> loop to [draft] with feedback
        -> rejected? -> [archive draft with reason]
```

| Graph | Interrupt point |
|---|---|
| knowledge_ingest | "source changed" flag before any constant or process-step update is applied |
| iht_narration | before the narration is shown as anything other than draft |
| forms_draft | before the filled PDF is marked final |
| guidance_qa | none (read-only, cited answers); corpus restriction is the guardrail |
| next_actions | before suggestions become tasks |

## 4. Guardrail test contract

`backend/tests/test_agent_guardrails.py` must assert, and stay green in every phase:

1. **No send/file/pay reachability:** for every graph, enumerate the registered toolset and assert that no tool can call an external send, file or payment function. No email dispatch, no HMRC or probate filing, no payment initiation exists anywhere in `app/agents/`.
2. **Every draft creates an approval-pending record:** invoking any drafting path (`draft-form`, `draft-letter`, `suggest-tasks`, narration) results in a row in `approval` with no `approved_by`, and the artefact is in draft state until that row is completed.
3. Supporting assertions from the domain contract: `claims_rnrb=True` forces `must_file_iht400=True` in the engine (the critical rule the agents must never talk around); narration contains no figure absent from the `Assessment` snapshot.

These tests are part of the definition of done for every phase, not a later add-on.

## 5. Operational notes

- Agent runs are audit-logged (actor = the requesting user, action, entity, timestamp).
- Drafts are stored server-side (documents vault or the relevant table), never emailed out by the system.
- Agent output always displays its provenance: sources cited with fetch dates, and a visible draft state until approval.
- Model access is via `ANTHROPIC_API_KEY`; embeddings via `EMBEDDING_MODEL` (see ARCHITECTURE.md environment table).
- The viewer role cannot invoke any agent endpoint; executor and admin can (server-side enforcement).
