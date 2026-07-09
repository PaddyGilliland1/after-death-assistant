/*
  Administration period tax constants, types, form schemas and payload
  mapping. One record per tax year holds the income position, the complex
  estate flag, the ISA exemption end date and the CGT disposals list; the
  60 day reporting deadlines arrive derived from the server. The backend
  schema in backend/app/schemas/trackers.py remains authoritative.
*/

import { z } from "zod"

import {
  zDate,
  zOptionalMoney,
  zText,
} from "@/components/shared/form-schema"

/** The API path for the module. Verified against the backend router. */
export const ADMIN_TAX_PATH = "/admin-tax"

/** One capital gains disposal, stored in the year record's JSON list. */
export interface CgtDisposal {
  description?: string | null
  disposal_date?: string | null
  proceeds?: string | null
  gain?: string | null
  [key: string]: unknown
}

/** A derived 60 day reporting deadline for a disposal. */
export interface Cgt60DayDeadline {
  disposal_date: string
  deadline: string
  basis: string
}

/** One tax year of the administration period, from GET /admin-tax
 *  (AdminTaxRead in backend/app/schemas/trackers.py). estate_complex,
 *  complex_reasons, cgt_60day_deadlines and isa_exemption_end are all
 *  derived by the server and never written from here. */
export interface AdminTaxYear {
  id: string
  estate_id: string
  created_at: string
  updated_at: string
  created_by: string
  archived_at: string | null
  archive_reason: string | null
  tax_year: string
  income_total: string | null
  estate_complex: boolean | null
  complex_reasons?: string[]
  isa_exemption_end: string | null
  cgt_disposals: CgtDisposal[]
  cgt_60day_deadlines?: Cgt60DayDeadline[]
}

/** The reasons the estate is treated as complex, read tolerantly. */
export function complexReasons(year: AdminTaxYear): string[] {
  const raw = year.complex_reasons
  if (Array.isArray(raw)) return raw.filter((item) => typeof item === "string")
  return []
}

/* ------------------------------------------------------------ year form */

const TAX_YEAR_PATTERN = /^\d{4}-\d{2}$/

export const yearFormSchema = z.object({
  tax_year: zText("Enter the tax year").regex(
    TAX_YEAR_PATTERN,
    "Enter the tax year as YYYY-NN, for example 2025-26",
  ),
  income_total: zOptionalMoney(),
})

export type YearFormValues = z.infer<typeof yearFormSchema>

export function yearFormDefaults(year?: AdminTaxYear): YearFormValues {
  return {
    tax_year: year?.tax_year ?? "",
    income_total: year?.income_total ?? "",
  }
}

export function toYearPayload(values: YearFormValues) {
  return {
    tax_year: values.tax_year,
    income_total: values.income_total || null,
  }
}

/* -------------------------------------------------------- disposal form */

export const disposalFormSchema = z.object({
  description: zText("Describe what was disposed of"),
  disposal_date: zDate("Enter the date of disposal"),
  proceeds: zOptionalMoney(),
  gain: zOptionalMoney(),
})

export type DisposalFormValues = z.infer<typeof disposalFormSchema>

export function disposalFormDefaults(
  disposal?: CgtDisposal,
): DisposalFormValues {
  return {
    description:
      typeof disposal?.description === "string" ? disposal.description : "",
    disposal_date:
      typeof disposal?.disposal_date === "string"
        ? disposal.disposal_date
        : "",
    proceeds: typeof disposal?.proceeds === "string" ? disposal.proceeds : "",
    gain: typeof disposal?.gain === "string" ? disposal.gain : "",
  }
}

export function toDisposalEntry(values: DisposalFormValues): CgtDisposal {
  return {
    description: values.description,
    disposal_date: values.disposal_date,
    proceeds: values.proceeds || null,
    gain: values.gain || null,
  }
}
