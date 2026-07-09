/*
  Create and edit form for a cost, built on the shared EntityForm. The
  caller maps validated values to a payload with toCostPayload and
  performs the mutation.
*/

import {
  EntityForm,
  type EntityField,
} from "@/components/shared/entity-form"
import type { Cost } from "@/lib/types"

import {
  costFormDefaults,
  costFormSchema,
  ihtTreatmentOptions,
  type CostFormValues,
} from "./cost-meta"

const fields: EntityField<CostFormValues>[] = [
  {
    name: "description",
    label: "Description",
    kind: "text",
    placeholder: "For example: probate application fee",
  },
  {
    name: "category",
    label: "Category",
    kind: "text",
    placeholder: "For example: funeral, probate, valuation",
  },
  { name: "amount", label: "Amount", kind: "money" },
  { name: "vat", label: "VAT", kind: "money", required: false },
  { name: "date", label: "Date", kind: "date" },
  {
    name: "paid_by",
    label: "Paid by",
    kind: "text",
    required: false,
    placeholder: "Who paid this cost",
  },
  {
    name: "payment_method",
    label: "Payment method",
    kind: "text",
    required: false,
  },
  {
    name: "reimbursable",
    label: "Reimbursable",
    kind: "checkbox",
    description: "Tick when the payer should be repaid from the estate.",
  },
  { name: "reimbursed", label: "Reimbursed", kind: "checkbox" },
  {
    name: "reimbursed_date",
    label: "Reimbursed date",
    kind: "date",
    required: false,
  },
  {
    name: "iht_treatment",
    label: "IHT treatment",
    kind: "select",
    options: ihtTreatmentOptions,
    description:
      "Funeral costs are deductible for inheritance tax; administration costs are not.",
  },
  {
    name: "executor_private",
    label: "Private to executors",
    kind: "checkbox",
  },
]

export interface CostFormProps {
  /** When set, the form edits this cost; otherwise it creates one. */
  cost?: Cost
  onSubmit: (values: CostFormValues) => Promise<void>
  onCancel: () => void
}

export function CostForm({ cost, onSubmit, onCancel }: CostFormProps) {
  return (
    <EntityForm<CostFormValues>
      schema={costFormSchema}
      fields={fields}
      defaultValues={costFormDefaults(cost)}
      onSubmit={onSubmit}
      onCancel={onCancel}
      submitLabel={cost ? "Save changes" : "Add cost"}
    />
  )
}
