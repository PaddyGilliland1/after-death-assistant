/*
  Zod schemas, field lists and default values for the asset, liability and
  valuation forms. Field names and shapes follow AssetCreate,
  LiabilityCreate and ValuationEventCreate in
  backend/app/schemas/registers.py, which is authoritative for payloads.
*/

import type { DefaultValues } from "react-hook-form"
import { z } from "zod"

import type { EntityField } from "@/components/shared/entity-form"
import {
  optionsFromEnum,
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
import type { Asset, Liability } from "@/lib/types"

export const OWNERSHIP_VALUES = [
  "sole",
  "joint_tenants",
  "tenants_in_common",
] as const

export const VALUE_BASIS_VALUES = ["estimate", "confirmed"] as const

/*
  Asset.category is free text on the server; this curated list keeps
  entries consistent. "Other" covers anything unusual.
*/
export const ASSET_CATEGORY_VALUES = [
  "property",
  "bank_account",
  "savings",
  "nsandi",
  "investments",
  "shares",
  "pension",
  "life_policy",
  "vehicle",
  "household_contents",
  "cash",
  "digital_asset",
  "business_interest",
  "other",
] as const

const CATEGORY_LABELS: Record<string, string> = { nsandi: "NS&I" }

/** Optional percentage between 0 and 100, kept as a string for the API. */
const zOptionalPct = () =>
  z
    .string()
    .trim()
    .refine(
      (value) =>
        value === "" ||
        (/^\d{1,3}(\.\d{1,4})?$/.test(value) && Number(value) <= 100),
      "Enter a percentage between 0 and 100",
    )

/* ------------------------------------------------------------------ asset */

export const assetSchema = z.object({
  description: zText("Enter a short description"),
  category: zEnumField(ASSET_CATEGORY_VALUES, "Choose a category"),
  sub_type: zOptionalText(),
  holder_contact_id: zOptionalText(),
  account_reference: zOptionalText(),
  ownership: zEnumField(OWNERSHIP_VALUES),
  tic_share_pct: zOptionalPct(),
  dod_value: zOptionalMoney(),
  value_basis: zEnumField(VALUE_BASIS_VALUES),
  valuation_source: zOptionalText(),
  valuation_date: zOptionalDate(),
  current_or_realised_value: zOptionalMoney(),
  realised_date: zOptionalDate(),
  income_since_death: zOptionalMoney(),
  iht_schedule: zOptionalText(),
  rnrb_qualifying: zCheckbox(),
  passes_outside_estate: zCheckbox(),
  status: zOptionalText(),
})

export type AssetFormValues = z.infer<typeof assetSchema>

export function assetFields(
  contactOptions: SelectOption[],
): EntityField<AssetFormValues>[] {
  return [
    {
      name: "description",
      label: "Description",
      kind: "text",
      placeholder: "For example: Example Bank current account",
    },
    {
      name: "category",
      label: "Category",
      kind: "select",
      options: optionsFromEnum(ASSET_CATEGORY_VALUES, CATEGORY_LABELS),
    },
    { name: "sub_type", label: "Sub type", kind: "text", required: false },
    {
      name: "holder_contact_id",
      label: "Holder",
      kind: "select",
      options: contactOptions,
      required: false,
      description: "The organisation or person holding the asset.",
    },
    {
      name: "account_reference",
      label: "Account reference",
      kind: "text",
      required: false,
    },
    {
      name: "ownership",
      label: "Ownership",
      kind: "select",
      options: optionsFromEnum(OWNERSHIP_VALUES),
    },
    {
      name: "tic_share_pct",
      label: "Share of ownership (%)",
      kind: "text",
      required: false,
      description: "Only needed for tenants in common.",
    },
    {
      name: "dod_value",
      label: "Value at date of death",
      kind: "money",
      required: false,
    },
    {
      name: "value_basis",
      label: "Value basis",
      kind: "select",
      options: optionsFromEnum(VALUE_BASIS_VALUES),
    },
    {
      name: "valuation_source",
      label: "Valuation source",
      kind: "text",
      required: false,
      placeholder: "For example: estate agent appraisal",
    },
    {
      name: "valuation_date",
      label: "Valuation date",
      kind: "date",
      required: false,
    },
    {
      name: "current_or_realised_value",
      label: "Current or realised value",
      kind: "money",
      required: false,
    },
    {
      name: "realised_date",
      label: "Realised date",
      kind: "date",
      required: false,
    },
    {
      name: "income_since_death",
      label: "Income since death",
      kind: "money",
      required: false,
    },
    {
      name: "iht_schedule",
      label: "IHT schedule",
      kind: "text",
      required: false,
      description: "IHT400 schedule reference, for example IHT405.",
    },
    {
      name: "rnrb_qualifying",
      label: "Qualifies for the residence nil rate band",
      kind: "checkbox",
    },
    {
      name: "passes_outside_estate",
      label: "Passes outside the estate",
      kind: "checkbox",
    },
    {
      name: "status",
      label: "Status",
      kind: "text",
      required: false,
      placeholder: "For example: notified, valued, realised",
    },
  ]
}

export const assetCreateDefaults: DefaultValues<AssetFormValues> = {
  description: "",
  category: undefined,
  sub_type: "",
  holder_contact_id: "",
  account_reference: "",
  ownership: "sole",
  tic_share_pct: "",
  dod_value: "",
  value_basis: "estimate",
  valuation_source: "",
  valuation_date: "",
  current_or_realised_value: "",
  realised_date: "",
  income_since_death: "",
  iht_schedule: "",
  rnrb_qualifying: false,
  passes_outside_estate: false,
  status: "",
}

export function assetEditDefaults(
  asset: Asset,
): DefaultValues<AssetFormValues> {
  return {
    description: asset.description,
    category: asset.category as AssetFormValues["category"],
    sub_type: asset.sub_type ?? "",
    holder_contact_id: asset.holder_contact_id ?? "",
    account_reference: asset.account_reference ?? "",
    ownership: asset.ownership,
    tic_share_pct: asset.tic_share_pct ?? "",
    dod_value: asset.dod_value ?? "",
    value_basis: asset.value_basis,
    valuation_source: asset.valuation_source ?? "",
    valuation_date: asset.valuation_date ?? "",
    current_or_realised_value: asset.current_or_realised_value ?? "",
    realised_date: asset.realised_date ?? "",
    income_since_death: asset.income_since_death ?? "",
    iht_schedule: asset.iht_schedule ?? "",
    rnrb_qualifying: asset.rnrb_qualifying,
    passes_outside_estate: asset.passes_outside_estate,
    status: asset.status ?? "",
  }
}

/* -------------------------------------------------------------- liability */

export const liabilitySchema = z.object({
  type: zText("Enter the type of liability"),
  creditor_contact_id: zOptionalText(),
  amount: zMoney(),
  as_at_date: zOptionalDate(),
  status: zOptionalText(),
  iht_deductible: zCheckbox(),
})

export type LiabilityFormValues = z.infer<typeof liabilitySchema>

export function liabilityFields(
  contactOptions: SelectOption[],
): EntityField<LiabilityFormValues>[] {
  return [
    {
      name: "type",
      label: "Type",
      kind: "text",
      placeholder: "For example: credit card, utility arrears",
    },
    {
      name: "creditor_contact_id",
      label: "Creditor",
      kind: "select",
      options: contactOptions,
      required: false,
      description: "Who the money is owed to.",
    },
    { name: "amount", label: "Amount", kind: "money" },
    { name: "as_at_date", label: "Amount as at", kind: "date", required: false },
    {
      name: "status",
      label: "Status",
      kind: "text",
      required: false,
      placeholder: "For example: outstanding, settled",
    },
    {
      name: "iht_deductible",
      label: "Deductible for inheritance tax",
      kind: "checkbox",
    },
  ]
}

export const liabilityCreateDefaults: DefaultValues<LiabilityFormValues> = {
  type: "",
  creditor_contact_id: "",
  amount: "",
  as_at_date: "",
  status: "",
  iht_deductible: true,
}

export function liabilityEditDefaults(
  liability: Liability,
): DefaultValues<LiabilityFormValues> {
  return {
    type: liability.type,
    creditor_contact_id: liability.creditor_contact_id ?? "",
    amount: liability.amount ?? "",
    as_at_date: liability.as_at_date ?? "",
    status: liability.status ?? "",
    iht_deductible: liability.iht_deductible,
  }
}

/* -------------------------------------------------------------- valuation */

export const valuationSchema = z.object({
  value: zMoney(),
  basis: zEnumField(VALUE_BASIS_VALUES),
  source: zOptionalText(),
  date: zDate("Enter the valuation date"),
})

export type ValuationFormValues = z.infer<typeof valuationSchema>

export const valuationFields: EntityField<ValuationFormValues>[] = [
  { name: "value", label: "Value", kind: "money" },
  {
    name: "basis",
    label: "Basis",
    kind: "select",
    options: optionsFromEnum(VALUE_BASIS_VALUES),
  },
  {
    name: "source",
    label: "Source",
    kind: "text",
    required: false,
    placeholder: "For example: closing statement",
  },
  { name: "date", label: "Valuation date", kind: "date" },
]

export const valuationDefaults: DefaultValues<ValuationFormValues> = {
  value: "",
  basis: "estimate",
  source: "",
  date: "",
}
