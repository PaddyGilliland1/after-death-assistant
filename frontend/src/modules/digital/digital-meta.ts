/*
  Digital assets module constants, types, form schema and payload mapping.
  Field names follow the P2 API contract for /digital (online accounts,
  subscriptions and services); the backend schema in
  backend/app/schemas/trackers.py remains authoritative once it lands.
*/

import { z } from "zod"

import {
  zCheckbox,
  zOptionalMoney,
  zOptionalText,
  zText,
} from "@/components/shared/form-schema"

/** The CRUD path: the backend router serves /digital-items, while the
 *  recurring total lives at GET /digital/recurring-total. */
export const DIGITAL_ITEMS_PATH = "/digital-items"

/** A digital account or service, as returned by GET /digital-items
 *  (DigitalItemRead in backend/app/schemas/trackers.py). */
export interface DigitalAsset {
  id: string
  estate_id: string
  created_at: string
  updated_at: string
  created_by: string
  archived_at: string | null
  archive_reason: string | null
  service: string
  type: string | null
  login_known: boolean
  action: string | null
  recurring_amount: string | null
  status: string | null
}

/** Query key for the recurring total, nested under /digital-items so
 *  create, update and archive mutations refresh it too. */
export const recurringTotalKey = [DIGITAL_ITEMS_PATH, "recurring-total"] as const

/** Reads the total out of GET /digital/recurring-total, whatever the
 *  exact JSON shape the backend settles on. */
export function readRecurringTotal(response: unknown): string | number | null {
  if (typeof response === "string" || typeof response === "number") {
    return response
  }
  if (response && typeof response === "object") {
    const record = response as Record<string, unknown>
    for (const key of ["recurring_total", "total", "amount"]) {
      const value = record[key]
      if (typeof value === "string" || typeof value === "number") return value
    }
  }
  return null
}

/* ----------------------------------------------------------------- form */

export const digitalFormSchema = z.object({
  service: zText("Enter the name of the service"),
  type: zOptionalText(),
  login_known: zCheckbox(),
  action: zOptionalText(),
  recurring_amount: zOptionalMoney(),
  status: zOptionalText(),
})

export type DigitalFormValues = z.infer<typeof digitalFormSchema>

/** Default form values, from an existing record when editing. */
export function digitalFormDefaults(asset?: DigitalAsset): DigitalFormValues {
  return {
    service: asset?.service ?? "",
    type: asset?.type ?? "",
    login_known: asset?.login_known ?? false,
    action: asset?.action ?? "",
    recurring_amount: asset?.recurring_amount ?? "",
    status: asset?.status ?? "",
  }
}

/** Maps validated form values to the create/update payload shape. */
export function toDigitalPayload(values: DigitalFormValues) {
  return {
    service: values.service,
    type: values.type || null,
    login_known: values.login_known,
    action: values.action || null,
    recurring_amount: values.recurring_amount || null,
    status: values.status || null,
  }
}
