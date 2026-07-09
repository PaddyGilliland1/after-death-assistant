/*
  The liabilities register: money the estate owed at the date of death and
  since, with the IHT deductibility flag that feeds the tax calculation.
*/

import type { DataTableColumn } from "@/components/shared/data-table"
import { humaniseCode } from "@/components/shared/formatters"
import type { SelectOption } from "@/components/shared/form-schema"
import type { Liability } from "@/lib/types"

import {
  liabilityCreateDefaults,
  liabilityEditDefaults,
  liabilityFields,
  liabilitySchema,
  type LiabilityFormValues,
} from "./forms"
import { emptyToNull, omitEmpty } from "./payload"
import {
  RegisterSection,
  type DetailFieldDef,
} from "./register-section"

export interface LiabilitiesSectionProps {
  estateId: string | null
  contactOptions: SelectOption[]
  contactName: (id: string | null) => string | null
}

export function LiabilitiesSection({
  estateId,
  contactOptions,
  contactName,
}: LiabilitiesSectionProps) {
  const columns: DataTableColumn<Liability>[] = [
    { key: "type", header: "Type", value: (row) => humaniseCode(row.type) },
    {
      key: "creditor",
      header: "Creditor",
      value: (row) => contactName(row.creditor_contact_id),
    },
    { key: "amount", header: "Amount", value: (row) => row.amount, kind: "money" },
    {
      key: "as_at_date",
      header: "As at",
      value: (row) => row.as_at_date,
      kind: "date",
    },
    {
      key: "status",
      header: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
      kind: "badge",
    },
    {
      key: "iht_deductible",
      header: "IHT deductible",
      value: (row) => (row.iht_deductible ? "Yes" : "No"),
    },
  ]

  const detailFields: DetailFieldDef<Liability>[] = [
    { label: "Type", value: (row) => humaniseCode(row.type) },
    {
      label: "Creditor",
      value: (row) => contactName(row.creditor_contact_id),
    },
    { label: "Amount", value: (row) => row.amount, kind: "money" },
    { label: "Amount as at", value: (row) => row.as_at_date, kind: "date" },
    {
      label: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
    },
    {
      label: "Deductible for inheritance tax",
      value: (row) => row.iht_deductible,
      kind: "boolean",
    },
  ]

  return (
    <RegisterSection<Liability, LiabilityFormValues>
      title="Liabilities"
      description="Money the estate owes, including debts outstanding at the date of death."
      path="/liabilities"
      itemLabel="liability"
      addLabel="Add liability"
      tableLabel="Liabilities register"
      filterLabel="Filter liabilities"
      emptyTitle="No liabilities recorded yet."
      emptyMessage="Add debts as statements and final bills arrive."
      columns={columns}
      estateId={estateId}
      formSchema={liabilitySchema}
      formFields={liabilityFields(contactOptions)}
      createDefaults={liabilityCreateDefaults}
      editDefaults={liabilityEditDefaults}
      toCreatePayload={(values, estate) =>
        omitEmpty({ ...values, estate_id: estate })
      }
      toUpdatePayload={(values) => emptyToNull({ ...values })}
      detailTitle={(row) => humaniseCode(row.type) || "Liability"}
      detailFields={detailFields}
    />
  )
}
