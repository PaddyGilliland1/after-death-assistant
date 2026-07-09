/*
  Generic typed TanStack Query CRUD hooks for the AD Assistant API.

  Conventions (one hook family per resource path, e.g. "/assets"):
  - list    GET    {path}
  - get     GET    {path}/{id}
  - create  POST   {path}
  - update  PATCH  {path}/{id}
  - archive POST   {path}/{id}/archive with { reason }  (soft delete)

  Every mutation invalidates all queries under [path], so lists and details
  refetch after a change. A 404 on a read resolves to null rather than an
  error, so pages degrade calmly while the backend catches up.
*/

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query"

import { api, isApiError } from "@/lib/api"

/** Query keys for a resource path. All keys nest under [path]. */
export const resourceKeys = {
  all: (path: string) => [path] as const,
  list: (path: string) => [path, "list"] as const,
  detail: (path: string, id: string) => [path, "detail", id] as const,
}

function retryUnlessNotFound(failureCount: number, error: unknown): boolean {
  if (isApiError(error) && error.status === 404) return false
  return failureCount < 2
}

async function getOrNull<T>(path: string): Promise<T | null> {
  try {
    return await api.get<T>(path)
  } catch (error) {
    if (isApiError(error) && error.status === 404) return null
    throw error
  }
}

/**
 * Lists a resource. Resolves to null (not an error) when the endpoint is
 * not implemented yet, so callers can show a calm placeholder.
 */
export function useResourceList<T>(
  path: string,
  options?: { enabled?: boolean; refetchInterval?: number },
): UseQueryResult<T[] | null> {
  return useQuery<T[] | null>({
    queryKey: resourceKeys.list(path),
    queryFn: () => getOrNull<T[]>(path),
    retry: retryUnlessNotFound,
    ...options,
  })
}

/** Fetches a single record by id. Null when the record does not exist. */
export function useResource<T>(
  path: string,
  id: string | null | undefined,
): UseQueryResult<T | null> {
  return useQuery<T | null>({
    queryKey: resourceKeys.detail(path, id ?? ""),
    queryFn: () => getOrNull<T>(`${path}/${id}`),
    enabled: Boolean(id),
    retry: retryUnlessNotFound,
  })
}

/** Creates a record with POST {path} and refreshes everything under it. */
export function useCreateResource<T, TInput = Partial<T>>(path: string) {
  const queryClient = useQueryClient()

  return useMutation<T, Error, TInput>({
    mutationFn: (input) => api.post<T>(path, input),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: resourceKeys.all(path) }),
  })
}

export interface UpdateInput<TInput> {
  id: string
  data: TInput
}

/** Updates a record with PATCH {path}/{id} and refreshes the resource. */
export function useUpdateResource<T, TInput = Partial<T>>(path: string) {
  const queryClient = useQueryClient()

  return useMutation<T, Error, UpdateInput<TInput>>({
    mutationFn: ({ id, data }) => api.patch<T>(`${path}/${id}`, data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: resourceKeys.all(path) }),
  })
}

export interface ArchiveInput {
  id: string
  reason: string
}

/**
 * Archives (soft deletes) a record with POST {path}/{id}/archive and a
 * reason. Nothing is physically deleted; the server records archived_at
 * and archive_reason.
 */
export function useArchiveResource<T = unknown>(path: string) {
  const queryClient = useQueryClient()

  return useMutation<T, Error, ArchiveInput>({
    mutationFn: ({ id, reason }) =>
      api.delete<T>(`${path}/${id}`, { reason }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: resourceKeys.all(path) }),
  })
}
