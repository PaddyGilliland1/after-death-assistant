/*
  Create and edit forms for the administration tax module, built on the
  shared EntityForm: one for a tax year record and one for a capital gains
  disposal within a year. Callers map validated values to payloads with
  the helpers in admin-tax-meta.ts and perform the mutation.
*/

import {
  EntityForm,
  type EntityField,
} from "@/components/shared/entity-form"

import {
  disposalFormDefaults,
  disposalFormSchema,
  yearFormDefaults,
  yearFormSchema,
  type AdminTaxYear,
  type CgtDisposal,
  type DisposalFormValues,
  type YearFormValues,
} from "./admin-tax-meta"

const yearFields: EntityField<YearFormValues>[] = [
  {
    name: "tax_year",
    label: "Tax year",
    kind: "text",
    placeholder: "For example: 2025-26",
    description:
      "Written as YYYY-NN. The complex estate flag and the ISA exemption end date are derived by the server.",
  },
  {
    name: "income_total",
    label: "Income total",
    kind: "money",
    required: false,
    description: "Estate income arising in this tax year.",
  },
]

export interface YearFormProps {
  /** When set, the form edits this year record; otherwise it creates one. */
  year?: AdminTaxYear
  onSubmit: (values: YearFormValues) => Promise<void>
  onCancel: () => void
}

export function YearForm({ year, onSubmit, onCancel }: YearFormProps) {
  return (
    <EntityForm<YearFormValues>
      schema={yearFormSchema}
      fields={yearFields}
      defaultValues={yearFormDefaults(year)}
      onSubmit={onSubmit}
      onCancel={onCancel}
      submitLabel={year ? "Save changes" : "Add tax year"}
    />
  )
}

const disposalFields: EntityField<DisposalFormValues>[] = [
  {
    name: "description",
    label: "Description",
    kind: "text",
    placeholder: "For example: sale of 12 Example Street",
  },
  { name: "disposal_date", label: "Disposal date", kind: "date" },
  { name: "proceeds", label: "Proceeds", kind: "money", required: false },
  { name: "gain", label: "Gain", kind: "money", required: false },
]

export interface DisposalFormProps {
  /** When set, the form edits this disposal; otherwise it creates one. */
  disposal?: CgtDisposal
  onSubmit: (values: DisposalFormValues) => Promise<void>
  onCancel: () => void
}

export function DisposalForm({
  disposal,
  onSubmit,
  onCancel,
}: DisposalFormProps) {
  return (
    <EntityForm<DisposalFormValues>
      schema={disposalFormSchema}
      fields={disposalFields}
      defaultValues={disposalFormDefaults(disposal)}
      onSubmit={onSubmit}
      onCancel={onCancel}
      submitLabel={disposal ? "Save changes" : "Add disposal"}
    />
  )
}
