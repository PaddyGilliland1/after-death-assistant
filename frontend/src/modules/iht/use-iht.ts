/*
  Types and hooks for the IHT workbench. Shapes mirror
  backend/app/schemas/iht.py (IhtAssessmentRead, IhtSchedulesRead) and
  backend/app/schemas/estate.py (EstateSettingsRead, EstateSettingsUpdate),
  which are authoritative.

  Money and rates arrive as strings (backend Decimal serialised to JSON)
  and are passed through untouched. Reads resolve a 404 to null so the
  workbench degrades calmly while the backend catches up.
*/

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query"

import { api, isApiError } from "@/lib/api"
import type { IsoDate, IsoDateTime, Money, Uuid } from "@/lib/types"

/* ---------------------------------------------------------------- types */

/** A persisted IHT assessment snapshot: engine inputs plus every figure
 *  the deterministic engine produced. */
export interface IhtAssessment {
  id: Uuid
  estate_id: Uuid
  created_at: IsoDateTime
  constants_version: string
  jurisdiction_code: string
  /** The engine's input snapshot; net_value is a money string. */
  inputs: Record<string, unknown>
  nrb: Money
  rnrb_max: Money
  rnrb: Money
  allowance: Money
  taxable: Money
  /** Decimal rate fraction, for example "0.40". */
  rate: string
  tax: Money
  is_excepted: boolean
  must_file_iht400: boolean
  required_schedules: string[]
}

/** A required supplementary schedule with a plain-English reason. */
export interface IhtScheduleItem {
  code: string
  reason: string
}

/** Required schedules derived by the engine in the latest assessment. */
export interface IhtSchedules {
  assessment_id: Uuid
  assessed_at: IsoDateTime
  must_file_iht400: boolean
  schedules: IhtScheduleItem[]
}

/** The estate settings row (GET /estate). null on the tri-state facts
 *  means unknown, which the engine treats cautiously. */
export interface EstateSettings {
  id: Uuid
  name: string
  date_of_death: IsoDate | null
  grant_date: IsoDate | null
  constants_version: string | null
  nrb: Money | null
  rnrb: Money | null
  taper_threshold: Money | null
  tnrb_pct: string
  trnrb_pct: string
  residence_to_descendants_value: Money | null
  charity_share_pct: string
  claims_rnrb: boolean | null
  gifts_with_reservation: boolean | null
  foreign_assets_value: Money | null
  trust_property_value: Money | null
  specified_transfers_value: Money | null
  created_at: IsoDateTime
  updated_at: IsoDateTime
}

/**
 * Writable estate settings (PUT /estate). The backend applies only the
 * keys present, so optional keys are omitted to leave a value unchanged,
 * while an explicit null clears it back to unknown. The tri-state facts
 * are always sent explicitly so "Derive automatically" and "Unknown"
 * serialise as null rather than being silently dropped.
 */
export interface EstateSettingsUpdate {
  date_of_death?: IsoDate | null
  tnrb_pct?: string
  trnrb_pct?: string
  residence_to_descendants_value?: Money | null
  charity_share_pct?: string
  claims_rnrb: boolean | null
  gifts_with_reservation: boolean | null
  foreign_assets_value?: Money | null
  trust_property_value?: Money | null
  specified_transfers_value?: Money | null
}

/* ---------------------------------------------------------------- hooks */

function useGetOrNull<T>(
  key: readonly unknown[],
  path: string,
): UseQueryResult<T | null> {
  return useQuery<T | null>({
    queryKey: key,
    queryFn: async () => {
      try {
        return await api.get<T>(path)
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

/** The latest assessment snapshot; null until one has been computed. */
export function useIhtAssessment() {
  return useGetOrNull<IhtAssessment>(["/iht", "assessment"], "/iht/assessment")
}

/** The required schedules for the latest assessment; null until one exists. */
export function useIhtSchedules() {
  return useGetOrNull<IhtSchedules>(["/iht", "schedules"], "/iht/schedules")
}

/** The estate settings; null when no estate has been set up yet. */
export function useEstateSettings() {
  return useGetOrNull<EstateSettings>(["/estate", "settings"], "/estate")
}

/**
 * POST /iht/recompute: the engine reassesses from the registers and
 * persists a new snapshot. Refetches the assessment, the schedules and
 * the estate queries afterwards.
 */
export function useRecomputeIht() {
  const queryClient = useQueryClient()

  return useMutation<IhtAssessment, Error, void>({
    mutationFn: () => api.post<IhtAssessment>("/iht/recompute"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["/iht"] })
      void queryClient.invalidateQueries({ queryKey: ["/estate"] })
    },
  })
}

/**
 * PUT /estate: updates the settings. The server re-evaluates the IHT
 * position on a settings change, so the IHT queries refetch too.
 */
export function useUpdateEstateSettings() {
  const queryClient = useQueryClient()

  return useMutation<EstateSettings, Error, EstateSettingsUpdate>({
    mutationFn: (input) => api.put<EstateSettings>("/estate", input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["/estate"] })
      void queryClient.invalidateQueries({ queryKey: ["/iht"] })
    },
  })
}
