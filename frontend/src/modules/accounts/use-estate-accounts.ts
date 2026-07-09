/*
  Hook for GET /estate/accounts, the trial balance drawn up by the
  backend's pure domain module. Mirrors backend/app/schemas/estate.py
  (EstateAccountsRead / AccountsDistributionRead), which is authoritative.

  Money arrives as strings (backend Decimal serialised to JSON) and is
  passed through untouched: nothing here computes. A 404 resolves to null
  so the page can show a calm placeholder while the backend catches up.
*/

import { useQuery, type UseQueryResult } from "@tanstack/react-query"

import { api, isApiError } from "@/lib/api"
import type { Money, Uuid } from "@/lib/types"

/** One residuary beneficiary's position. residuary_share is a decimal
 *  fraction such as "0.5"; the rest are money strings. */
export interface AccountsDistribution {
  beneficiary_id: Uuid
  residuary_share: string
  entitlement: Money
  interim_received: Money
  remaining_due: Money
}

/** The drawn-up estate accounts (four-account structure) plus the
 *  reconciliation flag. */
export interface EstateAccounts {
  net_estate: Money
  capital_account: Money
  income_account: Money
  administration_account: Money
  legacies_total: Money
  residue: Money
  distribution_account: Money
  distributions: AccountsDistribution[]
  is_balanced: boolean
}

/**
 * Fetches the estate accounts. A 404 (endpoint or estate not there yet)
 * resolves to null rather than an error.
 */
export function useEstateAccounts(): UseQueryResult<EstateAccounts | null> {
  return useQuery<EstateAccounts | null>({
    queryKey: ["/estate", "accounts"],
    queryFn: async () => {
      try {
        return await api.get<EstateAccounts>("/estate/accounts")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
    retry: (failureCount, error) => {
      if (isApiError(error) && error.status === 404) return false
      return failureCount < 2
    },
  })
}
