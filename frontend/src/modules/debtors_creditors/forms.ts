/*
  Zod schemas, field lists and default values for the debtor, creditor,
  creditor notice and notice claim forms. Field names and shapes follow
  DebtorCreate, CreditorCreate, CreditorNoticeCreate and NoticeClaimCreate
  in backend/app/schemas/registers.py, which is authoritative.
*/

import type { DefaultValues } from "react-hook-form"
import { z } from "zod"

import type { EntityField } from "@/components/shared/entity-form"
import {
  optionsFromEnum,
  zOptionalDate,
  zOptionalMoney,
  zOptionalText,
  zText,
} from "@/components/shared/form-schema"
import type { Creditor, Debtor } from "@/lib/types"

import type { CreditorNotice } from "./types"

/*
  priority_class is free text on the server; this list follows the
  statutory order of payment for an insolvent estate.
*/
export const PRIORITY_CLASS_VALUES = [
  "secured",
  "funeral_expenses",
  "testamentary_expenses",
  "preferential_debts",
  "ordinary_debts",
  "interest",
  "deferred_debts",
] as const

/** Claim states offered in the UI; "open" keeps a claim blocking. */
export const CLAIM_STATUS_VALUES = [
  "open",
  "resolved",
  "rejected",
  "withdrawn",
  "paid",
  "settled",
  "closed",
] as const

/* ----------------------------------------------------------------- debtor */

export const debtorSchema = z.object({
  type: zText("Enter the type of amount owed"),
  amount_expected: zOptionalMoney(),
  amount_received: zOptionalMoney(),
  status: zOptionalText(),
  expected_date: zOptionalDate(),
})

export type DebtorFormValues = z.infer<typeof debtorSchema>

export const debtorFields: EntityField<DebtorFormValues>[] = [
  {
    name: "type",
    label: "Type",
    kind: "text",
    placeholder: "For example: tax repayment, pension arrears",
  },
  {
    name: "amount_expected",
    label: "Amount expected",
    kind: "money",
    required: false,
  },
  {
    name: "amount_received",
    label: "Amount received",
    kind: "money",
    required: false,
  },
  {
    name: "status",
    label: "Status",
    kind: "text",
    required: false,
    placeholder: "For example: expected, received",
  },
  {
    name: "expected_date",
    label: "Expected date",
    kind: "date",
    required: false,
  },
]

export const debtorCreateDefaults: DefaultValues<DebtorFormValues> = {
  type: "",
  amount_expected: "",
  amount_received: "",
  status: "",
  expected_date: "",
}

export function debtorEditDefaults(
  debtor: Debtor,
): DefaultValues<DebtorFormValues> {
  return {
    type: debtor.type,
    amount_expected: debtor.amount_expected ?? "",
    amount_received: debtor.amount_received ?? "",
    status: debtor.status ?? "",
    expected_date: debtor.expected_date ?? "",
  }
}

/* --------------------------------------------------------------- creditor */

export const creditorSchema = z.object({
  type: zText("Enter the type of claim"),
  amount_claimed: zOptionalMoney(),
  amount_agreed: zOptionalMoney(),
  amount_paid: zOptionalMoney(),
  status: zOptionalText(),
  priority_class: zOptionalText(),
})

export type CreditorFormValues = z.infer<typeof creditorSchema>

export const creditorFields: EntityField<CreditorFormValues>[] = [
  {
    name: "type",
    label: "Type",
    kind: "text",
    placeholder: "For example: funeral account, utility arrears",
  },
  {
    name: "amount_claimed",
    label: "Amount claimed",
    kind: "money",
    required: false,
  },
  {
    name: "amount_agreed",
    label: "Amount agreed",
    kind: "money",
    required: false,
  },
  { name: "amount_paid", label: "Amount paid", kind: "money", required: false },
  {
    name: "status",
    label: "Status",
    kind: "text",
    required: false,
    placeholder: "For example: claimed, agreed, paid",
  },
  {
    name: "priority_class",
    label: "Priority class",
    kind: "select",
    options: optionsFromEnum(PRIORITY_CLASS_VALUES),
    required: false,
    description: "The statutory order of payment class.",
  },
]

export const creditorCreateDefaults: DefaultValues<CreditorFormValues> = {
  type: "",
  amount_claimed: "",
  amount_agreed: "",
  amount_paid: "",
  status: "",
  priority_class: "",
}

export function creditorEditDefaults(
  creditor: Creditor,
): DefaultValues<CreditorFormValues> {
  return {
    type: creditor.type,
    amount_claimed: creditor.amount_claimed ?? "",
    amount_agreed: creditor.amount_agreed ?? "",
    amount_paid: creditor.amount_paid ?? "",
    status: creditor.status ?? "",
    priority_class: creditor.priority_class ?? "",
  }
}

/* ----------------------------------------------------------------- notice */

export const noticeSchema = z.object({
  gazette_ref: zOptionalText(),
  gazette_date: zOptionalDate(),
  local_paper: zOptionalText(),
  local_date: zOptionalDate(),
})

export type NoticeFormValues = z.infer<typeof noticeSchema>

export const noticeFields: EntityField<NoticeFormValues>[] = [
  {
    name: "gazette_ref",
    label: "Gazette reference",
    kind: "text",
    required: false,
    placeholder: "For example: notice 4021987",
  },
  {
    name: "gazette_date",
    label: "Gazette date",
    kind: "date",
    required: false,
  },
  {
    name: "local_paper",
    label: "Local paper",
    kind: "text",
    required: false,
    placeholder: "For example: the local weekly paper",
  },
  {
    name: "local_date",
    label: "Local paper date",
    kind: "date",
    required: false,
    description:
      "The claim deadline is derived automatically as two months and a day from the later notice date.",
  },
]

export const noticeCreateDefaults: DefaultValues<NoticeFormValues> = {
  gazette_ref: "",
  gazette_date: "",
  local_paper: "",
  local_date: "",
}

export function noticeEditDefaults(
  notice: CreditorNotice,
): DefaultValues<NoticeFormValues> {
  return {
    gazette_ref: notice.gazette_ref ?? "",
    gazette_date: notice.gazette_date ?? "",
    local_paper: notice.local_paper ?? "",
    local_date: notice.local_date ?? "",
  }
}

/* ------------------------------------------------------------------ claim */

export const claimSchema = z.object({
  claimant: zText("Enter who made the claim"),
  amount: zOptionalMoney(),
  status: zOptionalText(),
})

export type ClaimFormValues = z.infer<typeof claimSchema>

export const claimFields: EntityField<ClaimFormValues>[] = [
  {
    name: "claimant",
    label: "Claimant",
    kind: "text",
    placeholder: "For example: Example Energy Ltd",
  },
  { name: "amount", label: "Amount", kind: "money", required: false },
  {
    name: "status",
    label: "Status",
    kind: "select",
    options: optionsFromEnum(CLAIM_STATUS_VALUES),
    required: false,
    description: "Leave blank for a new claim; it counts as open.",
  },
]

export const claimCreateDefaults: DefaultValues<ClaimFormValues> = {
  claimant: "",
  amount: "",
  status: "",
}
