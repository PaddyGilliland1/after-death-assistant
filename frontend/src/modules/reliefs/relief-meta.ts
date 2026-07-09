/*
  Reliefs module constants, types, form schema and payload mapping.
  Field names follow the P2 API contract for /reliefs (loss reliefs and
  reclaims with their qualifying windows); the backend schema in
  backend/app/schemas/trackers.py remains authoritative once it lands.
*/

import { z } from "zod"

import {
  zEnumField,
  zOptionalDate,
  zOptionalMoney,
  zOptionalText,
  type SelectOption,
} from "@/components/shared/form-schema"

export const RELIEF_TYPES = [
  "iht35",
  "iht38",
  "rnrb_downsizing",
  "bpr_apr",
] as const

export type ReliefType = (typeof RELIEF_TYPES)[number]

/** A relief or reclaim being tracked, as returned by GET /reliefs
 *  (ReliefRead in backend/app/schemas/trackers.py). window_basis and
 *  reclaim_note are derived on read and never written. */
export interface Relief {
  id: string
  estate_id: string
  created_at: string
  updated_at: string
  created_by: string
  archived_at: string | null
  archive_reason: string | null
  relief_type: ReliefType
  asset_id: string | null
  probate_value: string | null
  sale_value: string | null
  sale_date: string | null
  window_deadline: string | null
  window_basis: string | null
  potential_reclaim: string | null
  reclaim_note?: string | null
  status: string | null
}

/** One watchlist entry from GET /reliefs/watchlist
 *  (ReliefWatchlistItem in backend/app/schemas/trackers.py). */
export interface ReliefWatchlistItem {
  id: string
  estate_id: string
  relief_type: ReliefType
  asset_id: string | null
  window_deadline: string
  days_remaining: number
  potential_reclaim: string | null
  status: string | null
}

export const reliefTypeOptions: SelectOption[] = [
  { value: "iht35", label: "IHT35 loss on sale of shares" },
  { value: "iht38", label: "IHT38 loss on sale of land" },
  { value: "rnrb_downsizing", label: "RNRB downsizing addition" },
  { value: "bpr_apr", label: "Business or agricultural relief" },
]

/** Short label for the relief type badge column. */
const reliefTypeBadges: Record<ReliefType, string> = {
  iht35: "IHT35 shares",
  iht38: "IHT38 land",
  rnrb_downsizing: "RNRB downsizing",
  bpr_apr: "BPR/APR",
}

export function reliefTypeBadgeLabel(type: string): string {
  return reliefTypeBadges[type as ReliefType] ?? type
}

export function reliefTypeLabel(type: string): string {
  return (
    reliefTypeOptions.find((option) => option.value === type)?.label ?? type
  )
}

/* ----------------------------------------------------------------- form */

export const reliefFormSchema = z.object({
  relief_type: zEnumField(RELIEF_TYPES, "Choose the type of relief"),
  asset_id: zOptionalText(),
  probate_value: zOptionalMoney(),
  sale_value: zOptionalMoney(),
  sale_date: zOptionalDate(),
  window_deadline: zOptionalDate(),
  potential_reclaim: zOptionalMoney(),
  status: zOptionalText(),
})

export type ReliefFormValues = z.infer<typeof reliefFormSchema>

/** Default form values, from an existing relief when editing. */
export function reliefFormDefaults(relief?: Relief): ReliefFormValues {
  return {
    relief_type: relief?.relief_type ?? ("" as ReliefType),
    asset_id: relief?.asset_id ?? "",
    probate_value: relief?.probate_value ?? "",
    sale_value: relief?.sale_value ?? "",
    sale_date: relief?.sale_date ?? "",
    window_deadline: relief?.window_deadline ?? "",
    potential_reclaim: relief?.potential_reclaim ?? "",
    status: relief?.status ?? "",
  }
}

/** Maps validated form values to the create/update payload shape. */
export function toReliefPayload(values: ReliefFormValues) {
  return {
    relief_type: values.relief_type,
    asset_id: values.asset_id || null,
    probate_value: values.probate_value || null,
    sale_value: values.sale_value || null,
    sale_date: values.sale_date || null,
    window_deadline: values.window_deadline || null,
    potential_reclaim: values.potential_reclaim || null,
    status: values.status || null,
  }
}

/** Query key for the deadline watchlist, nested under /reliefs so
 *  create, update and archive mutations refresh it too. */
export const reliefWatchlistKey = ["/reliefs", "watchlist"] as const

/** Whole days from today until an ISO date. Negative when past. */
export function daysUntil(date: string, todayIso: string): number {
  const target = new Date(`${date}T00:00:00Z`).getTime()
  const today = new Date(`${todayIso}T00:00:00Z`).getTime()
  return Math.round((target - today) / 86_400_000)
}
