/*
  Resolves the estate under administration from GET /estate. The backend
  is single estate for now, but create payloads still carry an explicit
  estate_id, so every register form needs this id. A 404 resolves to null
  so pages degrade calmly while the backend catches up.
*/

import { useQuery } from "@tanstack/react-query"

import { api, isApiError } from "@/lib/api"
import type { Estate } from "@/lib/types"

export function useEstateId(): {
  estateId: string | null
  isLoading: boolean
} {
  const query = useQuery({
    queryKey: ["/estate"],
    queryFn: async () => {
      try {
        return await api.get<Estate>("/estate")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error) =>
      !(isApiError(error) && error.status === 404) && failureCount < 2,
  })

  return { estateId: query.data?.id ?? null, isLoading: query.isLoading }
}
