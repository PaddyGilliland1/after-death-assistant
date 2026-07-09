/*
  Shapes and tolerant readers for agent drafts, matching the landed
  backend contract (backend/app/api/agent_drafts.py and
  backend/app/schemas/agents.py):

  - GET /agents/drafts returns PendingDraftOut rows keyed by approval_id
    with draft_kind, draft_id (the draft document), title, created_at
    and created_by. The payload is NOT in the listing.
  - The draft content is stored as JSON in the documents vault; reading
    GET /documents/{draft_id}/download yields {draft_kind, payload}.
  - Kinds: "iht400_draft" (forms), "notification_letter" (letter),
    "task_suggestions" (tasks), "iht_narration" (narration text).
  - POST /agents/drafts/{approval_id}/approve takes {accepted?: number[]}
    where accepted lists the task-suggestion indices to materialise;
    omitted means all of them.

  Readers stay tolerant of small field differences so the page degrades
  calmly rather than crashing on a shape drift.
*/

import { humaniseCode } from "@/components/shared/formatters"

export type DraftKind = "form" | "letter" | "tasks" | "narration" | "other"

/** One row of GET /agents/drafts (PendingDraftOut). */
export interface PendingDraft {
  approval_id: string
  entity_ref?: string | null
  draft_kind?: string | null
  /** The draft document id; its download is the JSON payload. */
  draft_id?: string | null
  title?: string | null
  created_at?: string | null
  created_by?: string | null
  [key: string]: unknown
}

/** One flattened field row of a drafted form, for display. */
export interface FormFieldRow {
  key: string
  fieldRef: string
  label: string
  value: string
  source: string
}

/** One drafted form (the IHT400 or one schedule) ready to render. */
export interface FormDraftView {
  form: string | null
  title: string | null
  rows: FormFieldRow[]
  gaps: string[]
}

export interface TaskSuggestion {
  title: string
  description: string | null
  dueDate: string | null
  priority: string | null
}

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/**
 * Unwraps a stored draft file ({draft_kind, payload}) to its payload.
 * Content passed in any other shape is returned as it is.
 */
export function unwrapDraftFile(content: unknown): unknown {
  const record = asRecord(content)
  if (record && "payload" in record && "draft_kind" in record) {
    return record.payload
  }
  return content
}

/** Resolves the broad kind of a draft from its draft_kind code. */
export function draftKind(draft: PendingDraft): DraftKind {
  const raw = String(
    draft.draft_kind ?? draft.kind ?? draft.type ?? "",
  ).toLowerCase()
  if (raw.includes("narration")) return "narration"
  if (raw.includes("form") || raw.includes("iht400")) return "form"
  if (raw.includes("letter")) return "letter"
  if (raw.includes("task") || raw.includes("suggest")) return "tasks"
  return "other"
}

export function kindLabel(kind: DraftKind): string {
  switch (kind) {
    case "form":
      return "Form"
    case "letter":
      return "Letter"
    case "tasks":
      return "Tasks"
    case "narration":
      return "Narration"
    default:
      return "Draft"
  }
}

function gapText(gap: unknown): string | null {
  if (typeof gap === "string") return asText(gap)
  const record = asRecord(gap)
  if (!record) return null
  const item =
    asText(record.item) ??
    asText(record.message) ??
    asText(record.reason) ??
    asText(record.label) ??
    asText(record.field_ref)
  const action = asText(record.action)
  if (item && action) return `${item}. ${action}`
  return item ?? action
}

function fieldRows(fields: unknown, formKey: string): FormFieldRow[] {
  if (!Array.isArray(fields)) return []
  const rows: FormFieldRow[] = []
  fields.forEach((entry, index) => {
    const field = asRecord(entry)
    if (!field) return
    const value = field.value
    rows.push({
      key: `${formKey}-${index}`,
      fieldRef: asText(field.field_ref) ?? asText(field.ref) ?? "",
      label: asText(field.label) ?? asText(field.field_ref) ?? "Field",
      value:
        value === null || value === undefined
          ? ""
          : typeof value === "object"
            ? JSON.stringify(value)
            : String(value),
      source: asText(field.source_entity) ?? asText(field.source) ?? "",
    })
  })
  return rows
}

function singleFormView(entry: unknown, formKey: string): FormDraftView {
  const record = asRecord(entry)
  const gaps: string[] = []
  if (Array.isArray(record?.gaps)) {
    for (const gap of record.gaps) {
      const text = gapText(gap)
      if (text) gaps.push(text)
    }
  }
  return {
    form: asText(record?.form),
    title: asText(record?.title),
    rows: fieldRows(record?.sections ?? record?.fields, formKey),
    gaps,
  }
}

/**
 * Reads a forms-draft payload into per-form views. The landed shape is
 * {forms: [{form, title, sections: [...], gaps: [...]}], narrative};
 * a single {form, sections, gaps} object is tolerated too.
 */
export function formDraftViews(payload: unknown): FormDraftView[] {
  const unwrapped = unwrapDraftFile(payload)
  const record = asRecord(unwrapped)
  if (Array.isArray(record?.forms)) {
    return record.forms.map((entry, index) =>
      singleFormView(entry, `form-${index}`),
    )
  }
  if (record?.sections || record?.form) {
    return [singleFormView(record, "form-0")]
  }
  return []
}

/** The optional plain-English cover note of a forms-draft payload. */
export function formNarrativeOf(payload: unknown): string | null {
  const record = asRecord(unwrapDraftFile(payload))
  return asText(record?.narrative)
}

/** Reads letter or narration text, whichever field carries it. */
export function letterTextOf(payload: unknown): string | null {
  const unwrapped = unwrapDraftFile(payload)
  if (typeof unwrapped === "string") return asText(unwrapped)
  const record = asRecord(unwrapped)
  if (!record) return null
  return (
    asText(record.letter_text) ??
    asText(record.narration) ??
    asText(record.text) ??
    asText(record.letter) ??
    asText(record.body) ??
    asText(record.content)
  )
}

/** Account or policy references a letter draft quotes, if any. */
export function letterReferencesOf(payload: unknown): string[] {
  const record = asRecord(unwrapDraftFile(payload))
  const references = record?.references
  if (!Array.isArray(references)) return []
  return references.filter(
    (entry): entry is string => typeof entry === "string" && entry.length > 0,
  )
}

/** Reads task suggestions from a payload, whichever key carries them. */
export function suggestionsOf(payload: unknown): TaskSuggestion[] {
  const unwrapped = unwrapDraftFile(payload)
  let entries: unknown[] = []
  if (Array.isArray(unwrapped)) {
    entries = unwrapped
  } else {
    const record = asRecord(unwrapped)
    if (record) {
      for (const key of ["suggestions", "tasks", "proposed_tasks", "items"]) {
        const value = record[key]
        if (Array.isArray(value)) {
          entries = value
          break
        }
      }
    }
  }

  const suggestions: TaskSuggestion[] = []
  for (const entry of entries) {
    if (typeof entry === "string") {
      if (entry.trim()) {
        suggestions.push({
          title: entry,
          description: null,
          dueDate: null,
          priority: null,
        })
      }
      continue
    }
    const record = asRecord(entry)
    if (!record) continue
    suggestions.push({
      title:
        asText(record.title) ??
        asText(record.text) ??
        asText(record.name) ??
        "Suggested task",
      description: asText(record.description),
      dueDate: asText(record.due_date),
      priority: asText(record.priority),
    })
  }
  return suggestions
}

/** A short human summary of a draft row, for the list. */
export function draftSummary(draft: PendingDraft): string {
  const title = asText(draft.title)
  if (title) return title
  switch (draftKind(draft)) {
    case "form":
      return "Form draft"
    case "letter":
      return "Letter draft"
    case "tasks":
      return "Task suggestions"
    case "narration":
      return "Assessment narration draft"
    default: {
      const raw = asText(String(draft.draft_kind ?? draft.kind ?? ""))
      return raw ? humaniseCode(raw) : "Draft"
    }
  }
}

/** The wording of the approve confirmation. Guardrail 1 made visible. */
export const APPROVAL_MEANING =
  "Approval records your decision. Nothing is sent or filed by this application; you remain responsible for submitting documents to HMRC or sending letters yourself."

/** The calm message for a 503 from an LLM-dependent endpoint. */
export const ASSISTANT_NOT_CONFIGURED =
  "The drafting assistant is not configured yet."
