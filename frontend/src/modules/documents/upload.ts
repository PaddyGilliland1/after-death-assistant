/*
  Multipart upload helpers for the documents module. The shared api client
  (src/lib/api.ts) is JSON only, so file uploads build a FormData body and
  call fetch directly, reusing the same base URL, dev auth header and
  error shape (ApiError) so callers handle failures uniformly.
*/

import { API_URL, ApiError, DEV_USER_STORAGE_KEY } from "@/lib/api"

export interface DocumentUploadInput {
  file: File
  title: string
  /** Document type code, e.g. "will" or "valuation". Optional. */
  type?: string
  /** Roles that may see the document. Empty means every role. */
  accessRoles: string[]
  /** Hidden from the viewer role entirely when true. */
  executorPrivate: boolean
}

function devAuthHeaders(): Record<string, string> {
  if (!import.meta.env.DEV) return {}
  try {
    const devUser = window.localStorage.getItem(DEV_USER_STORAGE_KEY)
    return devUser ? { "X-Dev-User": devUser } : {}
  } catch {
    return {}
  }
}

async function postFormData<T>(path: string, form: FormData): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { Accept: "application/json", ...devAuthHeaders() },
      body: form,
    })
  } catch (cause) {
    throw new ApiError(
      0,
      "Could not reach the server. Please check your connection and try again.",
      cause,
    )
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    let detail: unknown
    try {
      detail = await response.json()
      if (detail && typeof detail === "object") {
        const field = (detail as Record<string, unknown>).detail
        if (typeof field === "string" && field.length > 0) message = field
      }
    } catch {
      detail = undefined
    }
    throw new ApiError(response.status, message, detail)
  }

  return (await response.json()) as T
}

/** Uploads a new document (version 1) with POST /documents. */
export function uploadDocument<T>(input: DocumentUploadInput): Promise<T> {
  const form = new FormData()
  form.append("file", input.file)
  form.append("title", input.title)
  if (input.type) form.append("type", input.type)
  form.append("access_roles", input.accessRoles.join(","))
  form.append("executor_private", String(input.executorPrivate))
  return postFormData<T>("/documents", form)
}

/** Attaches a new file version with POST /documents/{id}/versions. */
export function uploadDocumentVersion<T>(
  documentId: string,
  file: File,
): Promise<T> {
  const form = new FormData()
  form.append("file", file)
  return postFormData<T>(`/documents/${documentId}/versions`, form)
}

/** URL that streams the stored file, for a download link. */
export function documentDownloadUrl(documentId: string): string {
  return `${API_URL}/documents/${documentId}/download`
}
