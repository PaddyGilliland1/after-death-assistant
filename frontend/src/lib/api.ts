/*
  Typed fetch wrapper for the AD Assistant API.

  In development it forwards an X-Dev-User header from localStorage to match
  the backend dev auth shim (DEV_AUTH=true). In production, Cloudflare Access
  provides identity and no dev header is sent.
*/

const DEFAULT_API_URL = "http://localhost:8471"

export const API_URL: string = import.meta.env.VITE_API_URL ?? DEFAULT_API_URL

/** Key under which the development user email is stored in localStorage. */
export const DEV_USER_STORAGE_KEY = "ad-dev-user"

/** Normalised error thrown for any failed request. */
export class ApiError extends Error {
  /** HTTP status code, or 0 when the server could not be reached. */
  readonly status: number
  /** Parsed response body, when the server returned one. */
  readonly detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
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

async function parseErrorBody(response: Response): Promise<{
  message: string
  detail: unknown
}> {
  const fallback = `Request failed with status ${response.status}`
  try {
    const body: unknown = await response.json()
    if (body && typeof body === "object") {
      const record = body as Record<string, unknown>
      const detailField = record.detail ?? record.message ?? record.error
      if (typeof detailField === "string" && detailField.length > 0) {
        return { message: detailField, detail: body }
      }
      return { message: fallback, detail: body }
    }
    return { message: fallback, detail: body }
  } catch {
    return { message: fallback, detail: undefined }
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...devAuthHeaders(),
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json"
  }

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (cause) {
    throw new ApiError(
      0,
      "Could not reach the server. Please check your connection and try again.",
      cause,
    )
  }

  if (!response.ok) {
    const { message, detail } = await parseErrorBody(response)
    throw new ApiError(response.status, message, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string, body?: unknown) => request<T>("DELETE", path, body),
}
