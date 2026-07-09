import { useQuery } from "@tanstack/react-query"

import { api, isApiError } from "@/lib/api"
import type { EstateSummary } from "@/lib/types"

export type { EstateSummary }

/**
 * Fetches the dashboard aggregates from GET /estate/summary. A 404 from a
 * backend that has not yet implemented the endpoint resolves to null rather
 * than an error, so the dashboard shows a calm placeholder instead of
 * failing.
 */
export function useEstateSummary() {
  return useQuery<EstateSummary | null>({
    queryKey: ["estate", "summary"],
    queryFn: async () => {
      try {
        return await api.get<EstateSummary>("/estate/summary")
      } catch (error) {
        if (isApiError(error) && error.status === 404) {
          return null
        }
        throw error
      }
    },
    retry: (failureCount, error) => {
      if (isApiError(error) && error.status === 404) return false
      return failureCount < 2
    },
  })
}
