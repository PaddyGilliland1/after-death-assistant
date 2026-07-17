/*
  Knowledge library types and helpers. Shapes follow the P2 API contract
  for /knowledge (search, docs, qa, ingest); the backend schema in
  backend/app/schemas/knowledge.py remains authoritative once it lands.
*/

/** One search hit from GET /knowledge/search?q=. */
export interface KnowledgeSearchHit {
  doc_id: string
  doc_title: string
  form_code: string | null
  source_url: string | null
  licence: string | null
  fetch_date: string | null
  chunk_text: string
  chunk_index: number
  score: number
}

/** A cached document from GET /knowledge/docs (and /docs/{id}). */
export interface KnowledgeDoc {
  id: string
  title?: string | null
  doc_title?: string | null
  form_code?: string | null
  source_url?: string | null
  licence?: string | null
  fetch_date?: string | null
  extracted_text?: string | null
  [key: string]: unknown
}

/** One cited source in a QA answer. */
export interface QaSource {
  licence?: string | null
  fetch_date?: string | null
  relation?: "direct" | "referenced"
  n: number
  doc_title: string
  source_url: string | null
  form_code: string | null
}

/** Response of POST /knowledge/qa. */
export interface QaResponse {
  answer: string
  sources: QaSource[]
  refused: boolean
}

/** Display title for a doc, whichever key the backend uses. */
export function docTitle(doc: KnowledgeDoc): string {
  if (typeof doc.title === "string" && doc.title) return doc.title
  if (typeof doc.doc_title === "string" && doc.doc_title) return doc.doc_title
  return "Untitled document"
}

/** True when a licence string refers to the Open Government Licence. */
export function isOgl(licence: string | null | undefined): boolean {
  if (!licence) return false
  const value = licence.toLowerCase()
  return value.includes("ogl") || value.includes("open government")
}

export const OGL_LINE =
  "Contains public sector information licensed under the Open Government Licence."

export const GUIDANCE_DISCLAIMER =
  "Guidance only, not legal or tax advice. Answers cite the cached official sources."

/* ----------------------------------------------------------------- chat */

/*
  Conversational Q&A shapes. The backend contract is authoritative:
  backend/app/schemas/qa_chat.py (ChatRequest, ChatSource, ChatMessageOut,
  ChatResponse, ConversationOut).
*/

/** A source shown with an assistant chat message. Cited sources carry a
 *  number and the exact quoted passages; related (retrieved, not cited)
 *  sources have no number. */
export interface ChatSource {
  n: number | null
  doc_title: string
  source_url: string
  licence?: string | null
  fetch_date?: string | null
  quotes: string[]
  relation: "retrieved" | "pinned"
}

/** One message in a conversation (GET /knowledge/chats/{id}/messages). */
export interface ChatMessage {
  id: string
  role: string
  content: string
  sources_cited: ChatSource[]
  related_sources: ChatSource[]
  created_at: string
}

/** Response of POST /knowledge/chat. */
export interface ChatResponse {
  conversation_id: string
  message: ChatMessage
}

/** One conversation from GET /knowledge/chats (most recent first). */
export interface ChatConversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

/** The exact closing heading every assistant answer ends with; the text
 *  after it is pinned below the message body so the safety caveats stay
 *  visible. Must match NOT_COVERED_HEADING in
 *  backend/app/services/qa_chat.py. */
export const NOT_COVERED_HEADING = "What the retrieved guidance does not cover"

/* --------------------------------------------------------------- ingest */

/** One per-source outcome from POST /knowledge/ingest (IngestReport in
 *  backend/app/schemas/knowledge.py), read tolerantly. */
export interface IngestSourceResult {
  source_key?: string
  source?: string
  name?: string
  url?: string
  doc_title?: string
  status?: string
  changed?: boolean
  chunk_count?: number
  ok?: boolean
  detail?: string
  error?: string
  [key: string]: unknown
}

/** Normalises the ingest response to a list, whatever its exact shape. */
export function ingestResults(response: unknown): IngestSourceResult[] {
  if (Array.isArray(response)) return response as IngestSourceResult[]
  if (response && typeof response === "object") {
    const record = response as Record<string, unknown>
    for (const key of ["results", "sources", "items"]) {
      const value = record[key]
      if (Array.isArray(value)) return value as IngestSourceResult[]
    }
  }
  return []
}

export function ingestSourceLabel(result: IngestSourceResult): string {
  for (const key of ["source_key", "source", "name", "doc_title", "url"] as const) {
    const value = result[key]
    if (typeof value === "string" && value) return value
  }
  return "Source"
}

export function ingestSourceStatus(result: IngestSourceResult): string {
  if (typeof result.status === "string" && result.status) return result.status
  if (result.ok === true) return "ok"
  if (result.ok === false) return "failed"
  return ""
}
