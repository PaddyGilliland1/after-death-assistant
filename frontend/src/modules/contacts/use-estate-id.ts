/*
  Resolves the id of the (single) estate from GET /estate. Create payloads
  must carry estate_id, so module pages use this before posting. Kept per
  module so each module stays self-contained.
*/

import { useQuery } from "@tanstack/react-query"

import { api, isApiError } from "@/lib/api"
import type { Estate } from "@/lib/types"

export function useEstateId(): string | null {
  const { data } = useQuery({
    queryKey: ["/estate", "settings"],
    queryFn: async () => {
      try {
        return await api.get<Estate>("/estate")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
    staleTime: 5 * 60 * 1000,
  })
  return data?.id ?? null
}
