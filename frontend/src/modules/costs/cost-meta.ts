/*
  Cost module constants, form schema and payload mapping. Field names
  mirror backend/app/schemas/tasks_costs.py (CostCreate/CostUpdate and
  CostsByType), which remains authoritative.
*/

import { z } from "zod"

import {
  zCheckbox,
  zDate,
  zEnumField,
  zMoney,
  zOptionalDate,
  zOptionalMoney,
  zOptionalText,
  zText,
  type SelectOption,
} from "@/components/shared/form-schema"
import type { Cost, IhtTreatment } from "@/lib/types"

export const IHT_TREATMENTS = [
  "funeral_deductible",
  "admin_not_deductible",
] as const satisfies readonly IhtTreatment[]

export const ihtTreatmentOptions: SelectOption[] = [
  { value: "funeral_deductible", label: "Funeral (deductible)" },
  { value: "admin_not_deductible", label: "Administration (not deductible)" },
]

/** Human readable label for an IHT treatment value. */
export function ihtTreatmentLabel(treatment: string): string {
  return (
    ihtTreatmentOptions.find((option) => option.value === treatment)?.label ??
    treatment
  )
}

/* ----------------------------------------------------------------- form */

export const costFormSchema = z.object({
  description: zText("Enter a description of the cost"),
  category: zText("Enter a category"),
  amount: zMoney(),
  vat: zOptionalMoney(),
  date: zDate("Enter the date of the cost"),
  paid_by: zOptionalText(),
  payment_method: zOptionalText(),
  reimbursable: zCheckbox(),
  reimbursed: zCheckbox(),
  reimbursed_date: zOptionalDate(),
  iht_treatment: zEnumField(IHT_TREATMENTS),
  executor_private: zCheckbox(),
})

export type CostFormValues = z.infer<typeof costFormSchema>

/** Default form values, from an existing cost when editing. */
export function costFormDefaults(cost?: Cost): CostFormValues {
  return {
    description: cost?.description ?? "",
    category: cost?.category ?? "",
    amount: cost?.amount ?? "",
    vat: cost?.vat ?? "",
    date: cost?.date ?? "",
    paid_by: cost?.paid_by ?? "",
    payment_method: cost?.payment_method ?? "",
    reimbursable: cost?.reimbursable ?? false,
    reimbursed: cost?.reimbursed ?? false,
    reimbursed_date: cost?.reimbursed_date ?? "",
    iht_treatment: cost?.iht_treatment ?? ("" as IhtTreatment),
    executor_private: cost?.executor_private ?? false,
  }
}

/** Maps validated form values to the CostCreate/CostUpdate shape. */
export function toCostPayload(values: CostFormValues) {
  return {
    description: values.description,
    category: values.category,
    amount: values.amount,
    vat: values.vat || null,
    date: values.date,
    paid_by: values.paid_by || null,
    payment_method: values.payment_method || null,
    reimbursable: values.reimbursable,
    reimbursed: values.reimbursed,
    reimbursed_date: values.reimbursed_date || null,
    iht_treatment: values.iht_treatment,
    executor_private: values.executor_private,
  }
}

/* -------------------------------------------------------------- by type */

/** Shape of GET /costs/by-type: sums of stored cost amounts. */
export interface CostsByType {
  by_category: { category: string; total: string | number }[]
  by_iht_treatment: { iht_treatment: string; total: string | number }[]
}

export const costsByTypeKey = ["/costs", "by-type"] as const
